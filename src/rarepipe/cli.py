"""rarepipe command-line interface."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from rarepipe.core.console import Console

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Rare-disease case resolution pipeline.")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BLOCKED = 3


@app.callback()
def _root() -> None:
    """Rare-disease case resolution pipeline."""


@app.command()
def intake(
    case_root: Annotated[Path, typer.Option(help="Directory containing the case's files (read-only).")],
    case_id: Annotated[str, typer.Option(help="Case identifier, e.g. MVA_001.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    reference: Annotated[list[Path], typer.Option("--reference", help="Reference FASTA outside the case root (repeatable).")] = [],
    exclude: Annotated[list[str], typer.Option("--exclude", help="Glob of case-relative paths to ignore (repeatable).")] = [],
    primary_variant: Annotated[str | None, typer.Option(help="Case-relative path of the variant file downstream stages should use.")] = None,
    config: Annotated[Path | None, typer.Option(help="JSON file with any of: exclude_globs, primary_variant_asset, references, checksum_cache.")] = None,
    checksum_cache: Annotated[bool, typer.Option(help="Resume digests of unchanged files from <output>/.cache.")] = True,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Describe exactly what a case directory contains → CaseManifest + intake report."""
    from rarepipe.stages.intake.stage import IntakeRequest, IntakeUsageError, run_intake
    from rarepipe.stages.intake.manifest import Status

    cfg = {}
    if config:
        try:
            cfg = json.loads(config.read_text())
        except (OSError, ValueError) as exc:
            typer.echo(f"error: cannot read --config ({type(exc).__name__})", err=True)
            raise typer.Exit(EXIT_USAGE)
    req = IntakeRequest(
        case_root=case_root,
        case_id=case_id,
        output=output,
        exclude_globs=list(exclude) or list(cfg.get("exclude_globs", [])),
        primary_variant_asset=primary_variant or cfg.get("primary_variant_asset"),
        references=list(reference) or [Path(p) for p in cfg.get("references", [])],
        checksum_cache=checksum_cache if "checksum_cache" not in cfg else bool(cfg["checksum_cache"]) and checksum_cache,
        argv=sys.argv[:],
    )
    try:
        result = run_intake(req, Console(quiet=quiet))
    except IntakeUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    raise typer.Exit(EXIT_BLOCKED if result.manifest.status == Status.INTAKE_BLOCKED else EXIT_OK)


@app.command()
def schema(
    output: Annotated[Path | None, typer.Option(help="Write to file instead of stdout.")] = None,
    artifact: Annotated[str, typer.Option(help="case_manifest | normalized_case | case_assertions | raw_candidate_set")] = "case_manifest",
) -> None:
    """Emit an artifact's JSON Schema."""
    if artifact == "case_manifest":
        from rarepipe.stages.intake.schema import schema_json
    elif artifact == "raw_candidate_set":
        from rarepipe.stages.baseline.schema import schema_json
    elif artifact in ("normalized_case", "case_assertions"):
        from rarepipe.stages.normalize.schema import schema_json as _normalize_schema

        def schema_json() -> str:
            return _normalize_schema(artifact)
    else:
        typer.echo("error: unknown artifact", err=True)
        raise typer.Exit(EXIT_USAGE)
    text = schema_json()
    if output:
        output.write_text(text)
    else:
        typer.echo(text, nl=False)


@app.command()
def normalize(
    manifest: Annotated[Path, typer.Option(help="Stage 01 case_manifest.private.json.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    resources: Annotated[Path | None, typer.Option(help="Pinned resources directory (with resources.lock.json).")] = None,
    assertions: Annotated[Path | None, typer.Option(help="Optional CaseAssertions JSON.")] = None,
    case_root: Annotated[Path | None, typer.Option(help="Override the case root recorded in the manifest (assets are still SHA-256 verified).")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Turn a CaseManifest into an analysis-ready NormalizedCase (no diagnosis, no transformation)."""
    from rarepipe.stages.normalize.model import Status
    from rarepipe.stages.normalize.stage import NormalizeRequest, NormalizeUsageError, run_normalize

    req = NormalizeRequest(manifest=manifest, output=output, resources=resources, assertions=assertions, case_root=case_root, argv=sys.argv[:])
    try:
        result = run_normalize(req, Console(quiet=quiet))
    except NormalizeUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    raise typer.Exit(EXIT_BLOCKED if result.case.status == Status.NORMALIZATION_BLOCKED else EXIT_OK)


@app.command()
def baseline(
    normalized_case: Annotated[Path, typer.Option(help="Stage 02 normalized_case.private.json.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    exomiser_home: Annotated[Path | None, typer.Option(help="Exomiser CLI installation directory (contains exomiser-cli-*.jar).")] = None,
    exomiser_data: Annotated[Path | None, typer.Option(help="Exomiser data directory (defaults to <home>/data).")] = None,
    resources: Annotated[Path | None, typer.Option(help="Pinned resources directory whose lock records the Exomiser distribution/data digests.")] = None,
    profile: Annotated[list[str], typer.Option("--profile", help="Run only these profiles (repeatable), e.g. PROFILE_A.")] = [],
    max_heap: Annotated[str, typer.Option(help="Java max heap for the solver, e.g. 7g.")] = "7g",
    timeout_hours: Annotated[float, typer.Option(help="Per-profile timeout.")] = 6.0,
    case_root: Annotated[Path | None, typer.Option(help="Override the case root recorded upstream (the VCF is still SHA-256 verified).")] = None,
    dry_run: Annotated[bool, typer.Option(help="Write the job configuration for each profile without running the solver.")] = False,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Ask a mature solver (Exomiser) for candidate causal hypotheses under four declared profiles."""
    from rarepipe.stages.baseline.model import Status
    from rarepipe.stages.baseline.stage import BaselineRequest, BaselineUsageError, run_baseline

    req = BaselineRequest(normalized_case=normalized_case, output=output, exomiser_home=exomiser_home, exomiser_data=exomiser_data, resources=resources,
                          profile_ids=list(profile), max_heap=max_heap, timeout_seconds=int(timeout_hours * 3600),
                          case_root=case_root, dry_run=dry_run, argv=sys.argv[:])
    try:
        result = run_baseline(req, Console(quiet=quiet))
    except BaselineUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    raise typer.Exit(EXIT_BLOCKED if result.candidate_set.status == Status.BASELINE_ANALYSIS_BLOCKED else EXIT_OK)


resources_app = typer.Typer(no_args_is_help=True, help="Provision and pin external resources (the only networked commands).")
app.add_typer(resources_app, name="resources")


@resources_app.command("fetch-hpo")
def resources_fetch_hpo(
    resources: Annotated[Path, typer.Option(help="Resources directory.")],
    release: Annotated[str, typer.Option(help="HPO release tag (e.g. v2025-05-06) or 'latest'.")] = "latest",
) -> None:
    """Download hp.obo for a release from the official HPO GitHub releases and pin it. Uses the network."""
    from rarepipe.resources.fetch import fetch_hpo

    e = fetch_hpo(resources, release)
    typer.echo(f"pinned {e.name} {e.version} sha256={e.sha256} ({e.size_bytes} bytes)")


@resources_app.command("fetch-assembly-report")
def resources_fetch_assembly(
    resources: Annotated[Path, typer.Option(help="Resources directory.")],
    assembly: Annotated[str, typer.Option(help="Assembly release, e.g. GRCh38.p14.")] = "GRCh38.p14",
) -> None:
    """Download the NCBI assembly report and pin it. Uses the network."""
    from rarepipe.resources.fetch import fetch_assembly_report

    e = fetch_assembly_report(resources, assembly)
    typer.echo(f"pinned {e.name} {e.version} sha256={e.sha256} ({e.size_bytes} bytes)")


@resources_app.command("register")
def resources_register(
    resources: Annotated[Path, typer.Option(help="Resources directory.")],
    kind: Annotated[str, typer.Option(help="hpo_ontology | assembly_report")],
    file: Annotated[Path, typer.Option(help="File inside the resources directory.")],
    version: Annotated[str, typer.Option(help="Release/version string.")],
    name: Annotated[str, typer.Option(help="Human-readable name.")],
    source_url: Annotated[str | None, typer.Option(help="Where it came from.")] = None,
) -> None:
    """Pin a manually provisioned resource file (no network)."""
    from rarepipe.resources.lock import ResourceKind, register

    e = register(resources, ResourceKind(kind), file, name=name, version=version, source_url=source_url)
    typer.echo(f"pinned {e.name} {e.version} sha256={e.sha256}")


@resources_app.command("verify")
def resources_verify(resources: Annotated[Path, typer.Option(help="Resources directory.")]) -> None:
    """Check every pinned resource against its locked SHA-256 (no network)."""
    from rarepipe.resources.lock import load_lock, verify

    lock = load_lock(resources)
    if lock is None:
        typer.echo("error: no resources.lock.json", err=True)
        raise typer.Exit(EXIT_USAGE)
    bad = 0
    for e in lock.resources:
        status = verify(resources, e)
        bad += status != "verified"
        typer.echo(f"{status:18} {e.kind.value:16} {e.version:14} {e.path}")
    raise typer.Exit(1 if bad else 0)


@app.command("verify-run")
def verify_run(run_dir: Path) -> None:
    """Check a run directory's files against its SHA256SUMS seal."""
    sums = run_dir / "SHA256SUMS"
    if not sums.exists():
        typer.echo("error: SHA256SUMS not found", err=True)
        raise typer.Exit(EXIT_USAGE)
    bad = 0
    for line in sums.read_text().splitlines():
        digest, name = line.split("  ", 1)
        ok = hashlib.sha256((run_dir / name).read_bytes()).hexdigest() == digest
        bad += not ok
        typer.echo(f"{'OK  ' if ok else 'FAIL'} {name}")
    raise typer.Exit(1 if bad else 0)


@app.command()
def fixtures(
    output: Annotated[Path, typer.Option(help="Directory to create synthetic cases in.")],
    case: Annotated[list[str], typer.Option("--case", help="Fixture name (repeatable); default all.")] = [],
) -> None:
    """Materialize synthetic development cases (no real data)."""
    from rarepipe.testing.fixtures import CASES, build

    names = list(case) or list(CASES)
    for name in names:
        build(name, output / name, output / "_scratch" / name)
        typer.echo(f"{name}: {output / name}")


def main() -> None:
    app()
