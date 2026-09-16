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
def schema(output: Annotated[Path | None, typer.Option(help="Write to file instead of stdout.")] = None) -> None:
    """Emit the CaseManifest JSON Schema."""
    from rarepipe.stages.intake.schema import schema_json

    text = schema_json()
    if output:
        output.write_text(text)
    else:
        typer.echo(text, nl=False)


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
