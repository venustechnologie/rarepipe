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
    artifact: Annotated[str, typer.Option(help="case_manifest | normalized_case | case_assertions | raw_candidate_set | adjudicated_hypothesis | track1_submission_package | external_validation_result | mechanism_dossier")] = "case_manifest",
) -> None:
    """Emit an artifact's JSON Schema."""
    if artifact == "case_manifest":
        from rarepipe.stages.intake.schema import schema_json
    elif artifact == "raw_candidate_set":
        from rarepipe.stages.baseline.schema import schema_json
    elif artifact == "adjudicated_hypothesis":
        from rarepipe.stages.adjudicate.schema import schema_json
    elif artifact == "mechanism_dossier":
        from rarepipe.stages.mechanism.schema import schema_json
    elif artifact in ("track1_submission_package", "external_validation_result"):
        from rarepipe.stages.track1.schema import schema_json as _track1_schema

        def schema_json() -> str:
            return _track1_schema(artifact)
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


@app.command()
def adjudicate(
    raw_candidate_set: Annotated[Path, typer.Option(help="Stage 03 raw_candidate_set.private.json.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    gene: Annotated[str | None, typer.Option(help="Adjudicate this gene's candidate pair (default: the leading pair).")] = None,
    profile: Annotated[str, typer.Option(help="Which analysis profile's candidate to adjudicate.")] = "PROFILE_A",
    native_dir: Annotated[Path | None, typer.Option(help="Native solver output directory, if it has moved.")] = None,
    resources: Annotated[Path | None, typer.Option(help="Pinned evidence resources (ClinVar/ClinGen/UniProt/literature), read locally.")] = None,
    uniprot: Annotated[str | None, typer.Option(help="UniProt accession for the gene's protein, e.g. O60566.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Build an evidence dossier for one causal hypothesis. No diagnosis, no classification, nothing transmitted."""
    from rarepipe.stages.adjudicate.stage import AdjudicateRequest, AdjudicateUsageError, run_adjudication

    req = AdjudicateRequest(raw_candidate_set=raw_candidate_set, output=output, gene=gene, profile_id=profile,
                            native_dir=native_dir, resources=resources, uniprot_accession=uniprot, argv=sys.argv[:])
    try:
        result = run_adjudication(req, Console(quiet=quiet))
    except AdjudicateUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))


mechanism_app = typer.Typer(no_args_is_help=True, help="Stage 06 — molecular mechanism resolution.")
app.add_typer(mechanism_app, name="mechanism")


@mechanism_app.command("fetch-corpus")
def mechanism_fetch_corpus(
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable corpus run is created.")],
    select_top: Annotated[int, typer.Option(help="Documents kept per query, by relevance.")] = 6,
    page_size: Annotated[int, typer.Option(help="Records requested per query.")] = 25,
    full_text: Annotated[bool, typer.Option(help="Fetch open-access full text where available.")] = True,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Acquire the public literature corpus. Uses the network; never opens a case artifact."""
    from rarepipe.stages.mechanism.corpus_stage import FetchRequest, run_fetch

    result = run_fetch(FetchRequest(output=output, select_top=select_top, page_size=page_size,
                                    full_text=full_text, argv=sys.argv[:]), Console(quiet=quiet))
    typer.echo(str(result.run_dir))


research_app = typer.Typer(no_args_is_help=True, help="Human-in-the-loop research: tasks, evidence bundles, briefs, "
                                                     "and the import gate. The pipeline never calls a model.")
app.add_typer(research_app, name="research")


@research_app.command("create-task")
def research_create_task(
    research: Annotated[Path, typer.Option(help="Research workspace directory.")],
    question: Annotated[str, typer.Option(help="The research question this task answers.")],
    reason: Annotated[str, typer.Option(help="Why the pipeline needs it — which claim it would resolve.")],
    query: Annotated[list[str] | None, typer.Option(help="A public query to run. Repeat for several.")] = None,
    local_only: Annotated[bool, typer.Option(help="Answered locally against an existing corpus; nothing is transmitted.")] = False,
) -> None:
    """Record a KnowledgeTask. The pipeline owns the questions, whoever answers them."""
    from rarepipe.stages.mechanism.model import DisclosureLevel, KnowledgeTask
    from rarepipe.stages.mechanism.research import next_task_id, save_task, workspace

    for q in query or []:
        from rarepipe.stages.mechanism.retrieve import check_search_query

        try:
            check_search_query(q)
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(EXIT_USAGE)
    root = workspace(research)
    task = KnowledgeTask(
        id=next_task_id(root), question=question, reason=reason,
        disclosure_level=DisclosureLevel.LOCAL_ONLY if local_only else DisclosureLevel.PUBLIC_GENE_LEVEL,
        retrieval_plan=["local corpus search only"] if local_only else ["Europe PMC", "PMC open-access full text"],
        queries=list(query or []))
    typer.echo(str(save_task(root, task)))


@research_app.command("retrieve")
def research_retrieve(
    task: Annotated[str, typer.Option(help="KnowledgeTask id, e.g. KT_0003.")],
    research: Annotated[Path, typer.Option(help="Research workspace directory.")],
    corpus_run: Annotated[Path | None, typer.Option(help="Carve the bundle out of an existing corpus run instead of querying.")] = None,
    select_top: Annotated[int, typer.Option(help="Documents kept per query, by relevance.")] = 6,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Build the evidence bundle for a task: the documents, and only those, that answer it."""
    from rarepipe.stages.mechanism.research import ResearchError, bundle_from_corpus, load_task, save_task, workspace
    from rarepipe.stages.mechanism.retrieve import Corpus

    console = Console(quiet=quiet)
    root = workspace(research)
    try:
        kt = load_task(root, task)
    except ResearchError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    if corpus_run is None:
        target = root / "bundles" / kt.id
        target.mkdir(parents=True, exist_ok=True)
        corpus = Corpus(root=target)
        for q in kt.queries:
            corpus.run_query(q, kt.id, generated_by="human_operated_research", select_top=select_top, console=console)
        documents = [d.model_dump(mode="json") for d in corpus.documents.values()]
        import hashlib as _h
        import json as _j

        from rarepipe.core.artifacts import utc_now as _now
        from rarepipe.stages.mechanism.model import EvidenceBundle

        bundle = EvidenceBundle(bundle_id=kt.id, knowledge_task=kt.id, created_at=_now().isoformat(),
                                documents=[d["source_id"] for d in documents], queries=list(kt.queries),
                                characters=sum(d["characters_stored"] for d in documents),
                                digest="sha256:" + _h.sha256(_j.dumps(sorted(d["content_hash"] for d in documents)).encode()).hexdigest())
        (target / "bundle.json").write_text(_j.dumps({"bundle": bundle.model_dump(mode="json"),
                                                      "documents": documents}, indent=2, ensure_ascii=False) + "\n")
        kt.documents_found = bundle.documents
    else:
        bundle = bundle_from_corpus(corpus_run, kt, root)
    kt.status = "completed" if bundle.documents else "blocked"
    save_task(root, kt)
    typer.echo(str(root / "bundles" / kt.id))


@research_app.command("brief")
def research_brief(
    task: Annotated[str, typer.Option(help="KnowledgeTask id.")],
    research: Annotated[Path, typer.Option(help="Research workspace directory.")],
    template: Annotated[str, typer.Option(help="Prompt template name, e.g. evidence_extractor.")] = "evidence_extractor",
    output: Annotated[Path | None, typer.Option(help="Write the brief to a file instead of stdout.")] = None,
) -> None:
    """Emit the brief a person hands to an assistant: the rules, the documents, the return shape."""
    import json as _j

    from rarepipe.stages.mechanism.model import EvidenceBundle
    from rarepipe.stages.mechanism.research import ResearchError, load_prompt_template, load_task, render_brief

    try:
        kt = load_task(research, task)
        payload = _j.loads((research / "bundles" / kt.id / "bundle.json").read_text())
        text, template_id = load_prompt_template(template)
    except (ResearchError, FileNotFoundError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    brief = render_brief(kt, EvidenceBundle(**payload["bundle"]), payload["documents"], text, template_id)
    if output:
        output.write_text(brief)
        typer.echo(str(output))
    else:
        typer.echo(brief, nl=False)


@research_app.command("import-analysis")
def research_import_analysis(
    analysis: Annotated[Path, typer.Option(help="The YAML an assistant produced, after your review.")],
    research: Annotated[Path, typer.Option(help="Research workspace directory.")],
    adjudication_run: Annotated[Path | None, typer.Option(help="Stage 04 private artifact, for checking exact-variant scope claims locally.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Validate a proposed analysis against the evidence store. Proposals prove themselves or are rejected."""
    import json as _j

    from rarepipe.stages.mechanism.research import ResearchError, import_analysis, save_analysis
    from rarepipe.stages.mechanism.stage import residue_needles

    console = Console(quiet=quiet)
    needles: list[str] = []
    if adjudication_run:
        needles, _ = residue_needles(_j.loads(adjudication_run.read_text()))
    existing = len(list((research / "analyses").glob("LLMRS_*.json"))) if (research / "analyses").exists() else 0
    try:
        result = import_analysis(research, analysis, residue_needles=needles, session_index=existing + 1)
    except ResearchError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    for claim in result.accepted_claims:
        console.ok(f"{claim.id} accepted · scope {claim.scope.value} · {len(claim.evidence)} verified citation(s)")
    for bad in result.rejected:
        console.fail(f"rejected ({bad.reason}): {bad.statement[:70]} — {bad.detail}")
    path = save_analysis(research, result)
    console.line()
    console.line(f"{len(result.accepted_claims)} accepted, {len(result.rejected)} rejected")
    typer.echo(str(path))
    if result.rejected and not result.accepted_claims:
        raise typer.Exit(EXIT_BLOCKED)


@mechanism_app.command("resolve")
def mechanism_resolve(
    corpus_run: Annotated[Path, typer.Option(help="A sealed corpus run directory from `mechanism fetch-corpus`.")],
    adjudication_run: Annotated[Path, typer.Option(help="Stage 04 adjudicated_hypothesis.private.json.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    validation: Annotated[Path | None, typer.Option(help="Stage 05 external_validation_result.json, if the causal pair was validated.")] = None,
    research: Annotated[Path | None, typer.Option(help="Research workspace whose validated imported analyses to include.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Resolve the molecular mechanism from the local corpus. Offline; no intervention reasoning."""
    from rarepipe.stages.mechanism.model import Status
    from rarepipe.stages.mechanism.stage import MechanismUsageError, ResolveRequest, run_resolve

    req = ResolveRequest(corpus_run=corpus_run, adjudication=adjudication_run, output=output,
                         validation=validation, research_dir=research, argv=sys.argv[:])
    try:
        result = run_resolve(req, Console(quiet=quiet))
    except MechanismUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    if result.dossier.status is Status.BLOCKED:
        raise typer.Exit(EXIT_BLOCKED)


export_app = typer.Typer(no_args_is_help=True, help="Generate external submission packages. Nothing is uploaded — a person submits.")
app.add_typer(export_app, name="export")


@export_app.command("track1")
def export_track1(
    candidate_run: Annotated[Path, typer.Option(help="Stage 03 raw_candidate_set.private.json.")],
    adjudication_run: Annotated[Path, typer.Option(help="Stage 04 adjudicated_hypothesis.private.json.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    normalized_case: Annotated[Path | None, typer.Option(help="Stage 02 normalized_case.sanitized.json — completes the intake→submission provenance chain.")] = None,
    proband_id: Annotated[str, typer.Option(help="Proband identifier the evaluator accepts.")] = "PROBAND01",
    official_scorer: Annotated[Path | None, typer.Option(help="The challenge's public evaluation.py, run locally on our file (no answer key).")] = None,
    submitter: Annotated[str | None, typer.Option(help="Username or team name, used only to suggest an upload filename.")] = None,
    llm_disclosure: Annotated[str | None, typer.Option(help="Override the AI-assistance disclosure line in the methods report.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Build a Track 1 submission package: predictions CSV, methods report, manifest, frozen snapshot."""
    from rarepipe.stages.track1.stage import ExportRequest, Track1UsageError, run_export

    req = ExportRequest(raw_candidate_set=candidate_run, adjudication=adjudication_run,
                        normalized_case=normalized_case, output=output,
                        proband_id=proband_id, official_scorer=official_scorer, submitter=submitter,
                        llm_disclosure=llm_disclosure, argv=sys.argv[:])
    try:
        result = run_export(req, Console(quiet=quiet))
    except Track1UsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    if not result.package.valid:
        raise typer.Exit(EXIT_BLOCKED)


@app.command("record-validation")
def record_validation(
    package_run: Annotated[Path, typer.Option(help="The sealed run directory produced by `export track1`.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    match: Annotated[str, typer.Option(help="FULL | PARTIAL | NONE, as the evaluator reported it.")],
    response: Annotated[Path, typer.Option(help="File containing the evaluator's response, captured verbatim.")],
    full_match_rank: Annotated[int | None, typer.Option(help="Rank of the full match, if reported.")] = None,
    partial_match_rank: Annotated[int | None, typer.Option(help="Rank of the partial match, if reported.")] = None,
    rank_points: Annotated[float | None, typer.Option(help="Rank points, as reported.")] = None,
    f_max: Annotated[float | None, typer.Option(help="F-max, as reported.")] = None,
    f_max_threshold: Annotated[float | None, typer.Option(help="EPCR threshold at F-max, if reported.")] = None,
    submission_number: Annotated[int, typer.Option(help="Which of the allowed submissions this was.")] = 1,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Record the evaluator's answer as case state, and name the branch it puts the case into."""
    from rarepipe.stages.track1.stage import RecordRequest, Track1UsageError, record_result

    if not response.exists():
        typer.echo(f"error: not found: {response}", err=True)
        raise typer.Exit(EXIT_USAGE)
    req = RecordRequest(package_run=package_run, output=output, match=match, raw_response=response.read_text(),
                        full_match_rank=full_match_rank, partial_match_rank=partial_match_rank,
                        rank_points=rank_points, f_max=f_max, f_max_threshold=f_max_threshold,
                        submission_number=submission_number, argv=sys.argv[:])
    try:
        result, run_dir = record_result(req, Console(quiet=quiet))
    except Track1UsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(run_dir))


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
