"""rarepipe command-line interface."""

from __future__ import annotations

import hashlib
import json
import re
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
    artifact: Annotated[str, typer.Option(help="case_manifest | normalized_case | case_assertions | raw_candidate_set | adjudicated_hypothesis | track1_submission_package | external_validation_result | mechanism_dossier | intervention_map | intervention_discovery | track2_hypothesis_set")] = "case_manifest",
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
    elif artifact == "track2_hypothesis_set":
        import json as _json

        from rarepipe.stages.track2.model import Track2HypothesisSet

        def schema_json() -> str:
            return _json.dumps(Track2HypothesisSet.model_json_schema(by_alias=True), indent=2) + "\n"
    elif artifact == "intervention_discovery":
        import json as _json

        from rarepipe.stages.discovery.model import InterventionDiscovery

        def schema_json() -> str:
            return _json.dumps(InterventionDiscovery.model_json_schema(by_alias=True), indent=2) + "\n"
    elif artifact == "intervention_map":
        import json as _json

        from rarepipe.stages.intervention.model import InterventionMap

        def schema_json() -> str:
            return _json.dumps(InterventionMap.model_json_schema(by_alias=True), indent=2) + "\n"
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


track2_app = typer.Typer(no_args_is_help=True, help="Stage 09 — Track 2 research-hypothesis adjudication.")
app.add_typer(track2_app, name="track2")


@track2_app.command("import-hypotheses")
def track2_import_hypotheses(
    analysis: Annotated[Path, typer.Option(help="YAML of proposed research hypotheses, after your review.")],
    research: Annotated[Path, typer.Option(help="Research workspace holding the bundles.")],
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Validate proposed hypotheses arrow by arrow: every evidenced link must cite retrieved, verbatim text."""
    from rarepipe.stages.track2.ingest import IngestError, import_hypotheses, save

    console = Console(quiet=quiet)
    existing = _max_session(research / "hypotheses")
    try:
        result = import_hypotheses(research, analysis, session_index=existing + 1)
    except IngestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    for h in result.hypotheses:
        evidenced = sum(1 for link in h.proposed_chain if link.kind == "evidenced")
        console.ok(f"{h.id} {h.active_ingredient[:26]:28} {len(h.proposed_chain)} link(s), {evidenced} evidenced")
    for bad in result.rejected:
        console.fail(f"rejected ({bad.reason}): {bad.statement[:60]} — {bad.detail}")
    path = save(research, result)
    console.line()
    console.line(f"{len(result.hypotheses)} accepted, {len(result.rejected)} rejected")
    typer.echo(str(path))
    if result.rejected and not result.hypotheses:
        raise typer.Exit(EXIT_BLOCKED)


@track2_app.command("adjudicate")
def track2_adjudicate(
    discovery_run: Annotated[Path, typer.Option(help="A sealed Stage 08 discovery run directory.")],
    research: Annotated[Path, typer.Option(help="Research workspace with bundles and imported hypotheses.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    intervention_map_run: Annotated[Path | None, typer.Option(help="The Stage 07 run the pinned discovery consumed, to resolve the mechanism link.")] = None,
    mechanism_run: Annotated[Path | None, typer.Option(help="The Stage 06 run that map was built from; its residual-function assessment feeds the efficacy dependencies.")] = None,
    approval_cache: Annotated[Path | None, typer.Option(help="Cache directory for verified approval records.")] = None,
    offline: Annotated[bool, typer.Option(help="Skip approval verification (records it as unverified).")] = False,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Run the promotion gate and seal the pre-network baseline. Uploads nothing."""
    from rarepipe.stages.track2.model import Status
    from rarepipe.stages.track2.stage import BuildRequest, Track2UsageError, build

    try:
        result = build(BuildRequest(discovery_run=discovery_run, research_dir=research, output=output,
                                    intervention_map_run=intervention_map_run, mechanism_run=mechanism_run,
                                    approval_cache=approval_cache, offline=offline, argv=sys.argv[:]),
                       Console(quiet=quiet))
    except Track2UsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    if result.hypothesis_set.status is Status.BLOCKED:
        raise typer.Exit(EXIT_BLOCKED)


discovery_app = typer.Typer(no_args_is_help=True, help="Stage 08 — approved intervention and experience discovery.")
app.add_typer(discovery_app, name="discovery")


@discovery_app.command("import-experiences")
def discovery_import_experiences(
    analysis: Annotated[Path, typer.Option(help="YAML of intervention experiences, after your review.")],
    research: Annotated[Path, typer.Option(help="Research workspace holding the lane bundles.")],
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Validate proposed intervention experiences against the lane bundles, then store them."""
    from rarepipe.stages.discovery.ingest import IngestError, import_experiences, save

    console = Console(quiet=quiet)
    existing = _max_session(research / "experiences")
    try:
        result = import_experiences(research, analysis, session_index=existing + 1)
    except IngestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    for e in result.experiences:
        console.ok(f"{e.id} {e.intervention_ingredient[:30]:32} {e.outcome.value:10} lane {e.lane.value}")
    for bad in result.rejected:
        console.fail(f"rejected ({bad.reason}): {bad.statement[:60]} — {bad.detail}")
    path = save(research, result)
    console.line()
    console.line(f"{len(result.experiences)} accepted, {len(result.rejected)} rejected")
    typer.echo(str(path))
    if result.rejected and not result.experiences:
        raise typer.Exit(EXIT_BLOCKED)


@discovery_app.command("build")
def discovery_build(
    intervention_map_run: Annotated[Path, typer.Option(help="A sealed Stage 07 intervention run directory.")],
    research: Annotated[Path, typer.Option(help="Research workspace with lane bundles and imported experiences.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    approval_cache: Annotated[Path | None, typer.Option(help="Cache directory for verified approval records.")] = None,
    offline: Annotated[bool, typer.Option(help="Skip approval verification (records it as unverified).")] = False,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Assemble discovered interventions, their experiences, and what must not happen. Ranks nothing."""
    from rarepipe.stages.discovery.stage import BuildRequest, DiscoveryUsageError, build

    try:
        result = build(BuildRequest(intervention_map_run=intervention_map_run, research_dir=research,
                                    output=output, approval_cache=approval_cache, offline=offline,
                                    argv=sys.argv[:]), Console(quiet=quiet))
    except DiscoveryUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))


@app.command("intervention")
def intervention(
    mechanism_run: Annotated[Path, typer.Option(help="A sealed Stage 06 mechanism run directory.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    research: Annotated[Path | None, typer.Option(help="Research workspace, for recording which sessions informed this.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Build the InterventionMap: what a treatment would have to accomplish. Names no medication."""
    from rarepipe.stages.intervention.model import Status
    from rarepipe.stages.intervention.stage import BuildRequest, InterventionUsageError, build

    try:
        result = build(BuildRequest(mechanism_run=mechanism_run, output=output, research_dir=research,
                                    argv=sys.argv[:]), Console(quiet=quiet))
    except InterventionUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    if result.intervention_map.status is Status.BLOCKED:
        raise typer.Exit(EXIT_BLOCKED)


alphagenome_app = typer.Typer(no_args_is_help=True, help="AlphaGenome Atlas as a variant-mechanism evidence source.")
app.add_typer(alphagenome_app, name="alphagenome")


@alphagenome_app.command("fetch-region")
def alphagenome_fetch_region(
    output: Annotated[Path, typer.Option(help="Cache directory for the region's precomputed predictions.")],
    gene: Annotated[str | None, typer.Option(help="Public gene symbol whose locus to query, e.g. BUB1B.")] = None,
    interval: Annotated[str | None, typer.Option(help="Explicit public interval, chr15:40160000-40340000.")] = None,
    scorer: Annotated[list[str] | None, typer.Option(help="Atlas scorer to request. Repeat; omit to list what is available.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Query a PUBLIC gene region of the Atlas. Never opens a case artifact; nothing case-specific is sent."""
    from rarepipe.stages.mechanism.alphagenome import (
        AlphaGenomeError,
        RegionProvenance,
        cache_region,
        check_region_is_public,
        configured_provider,
        package_version,
        public_region,
    )

    console = Console(quiet=quiet)
    try:
        provider = configured_provider()
        if gene:
            region = public_region(gene)
        elif interval:
            chrom, span = interval.split(":")
            start, end = (int(x.replace(",", "")) for x in span.split("-"))
            region = RegionProvenance(chromosome=chrom, start=start, end=end, width=end - start,
                                      derived_from="operator-supplied public interval")
        else:
            typer.echo("error: pass --gene or --interval", err=True)
            raise typer.Exit(EXIT_USAGE)
        check_region_is_public(region)
        available = provider.available_scorers()
        if not scorer:
            console.info("available scorers: " + ", ".join(available))
            typer.echo("error: pass --scorer (repeatable) to fetch", err=True)
            raise typer.Exit(EXIT_USAGE)
        unknown = [s for s in scorer if s not in available]
        if unknown:
            typer.echo(f"error: unknown scorer(s) {unknown}; available: {available}", err=True)
            raise typer.Exit(EXIT_USAGE)
        console.info(f"querying {region.chromosome}:{region.start:,}-{region.end:,} "
                     f"({region.width:,} bp, ~{region.width * 3:,} hypothetical variants) for {len(scorer)} scorer(s)")
        predictions = provider.region_scores(region, list(scorer))
        path = cache_region(output, region, predictions, list(scorer), package_version())
    except AlphaGenomeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    console.ok(f"cached {len(predictions):,} public variant prediction(s)")
    typer.echo(str(path))


@alphagenome_app.command("match")
def alphagenome_match(
    cache: Annotated[Path, typer.Option(help="A region cache file from `fetch-region`.")],
    adjudication_run: Annotated[Path, typer.Option(help="Stage 04 adjudicated_hypothesis.private.json.")],
    output: Annotated[Path, typer.Option(help="Where to write the AlphaGenomeEvidence (private + sanitized).")],
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Match this case's alleles against a cached public region. Offline; nothing leaves the machine."""
    import json as _j

    from rarepipe.core.artifacts import canonical_json
    from rarepipe.core.redaction import clear_restricted
    from rarepipe.stages.mechanism.alphagenome import match_locally

    console = Console(quiet=quiet)
    adjudication = _j.loads(adjudication_run.read_text())
    if adjudication.get("visibility") != "private":
        typer.echo("error: local matching needs the private adjudication artifact", err=True)
        raise typer.Exit(EXIT_USAGE)
    evidence = match_locally(cache, adjudication.get("variants", []))
    output.mkdir(parents=True, exist_ok=True)
    for item in evidence:
        console.info(f"{item.variant_role}: {'matched' if item.local_match_found else 'NOT FOUND in the cached region'}"
                     + (f" · {len(item.scores)} score(s)" if item.local_match_found else ""))
    private = [e.model_dump(mode="json") for e in evidence]
    sanitized = []
    for item in evidence:
        copy = item.model_copy(deep=True)
        clear_restricted(copy)
        sanitized.append(copy.model_dump(mode="json"))
    (output / "alphagenome_evidence.private.json").write_text(canonical_json({"evidence": private}))
    (output / "alphagenome_evidence.sanitized.json").write_text(canonical_json({"evidence": sanitized}))
    typer.echo(str(output))


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
    intervention: Annotated[bool, typer.Option(help="Stage 08 lane: lifts the therapy-term filter. The case-identity guard still applies.")] = False,
) -> None:
    """Record a KnowledgeTask. The pipeline owns the questions, whoever answers them."""
    from rarepipe.stages.mechanism.model import DisclosureLevel, KnowledgeTask
    from rarepipe.stages.mechanism.research import ResearchError, next_task_id, save_task, workspace

    for q in query or []:
        from rarepipe.stages.discovery.lanes import check_intervention_query
        from rarepipe.stages.mechanism.retrieve import check_search_query

        validate = check_intervention_query if intervention else check_search_query
        try:
            validate(q)
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(EXIT_USAGE)
    root = workspace(research)
    task = KnowledgeTask(
        id=next_task_id(root), question=question, reason=reason,
        disclosure_level=DisclosureLevel.LOCAL_ONLY if local_only else DisclosureLevel.PUBLIC_GENE_LEVEL,
        retrieval_plan=(["local corpus search only"] if local_only else
                        ["Europe PMC", "PMC open-access full text"]
                        + (["intervention lane: therapy terms permitted, case identity never"] if intervention else [])),
        queries=list(query or []))
    try:
        path = save_task(root, task, allow_overwrite=False)
    except ResearchError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(path))


@research_app.command("adopt-task")
def research_adopt_task(
    task: Annotated[str, typer.Option(help="KnowledgeTask id as recorded in the corpus run, e.g. KT_0002.")],
    corpus_run: Annotated[Path, typer.Option(help="The corpus run that already answered it.")],
    research: Annotated[Path, typer.Option(help="Research workspace directory.")],
) -> None:
    """Bring a task the corpus run already retrieved into the workspace, with its evidence bundle."""
    import json as _j

    from rarepipe.stages.mechanism.model import KnowledgeTask
    from rarepipe.stages.mechanism.research import ResearchError, bundle_from_corpus, save_task, workspace

    index = _j.loads((corpus_run / "corpus_index.json").read_text())
    match = next((t for t in index["knowledge_tasks"] if t["id"] == task), None)
    if match is None:
        typer.echo(f"error: {corpus_run.name} has no task {task}", err=True)
        raise typer.Exit(EXIT_USAGE)
    kt = KnowledgeTask(**match)
    root = workspace(research)
    try:
        bundle = bundle_from_corpus(corpus_run, kt, root)
    except ResearchError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    kt.progress.retrieval = "complete" if bundle.documents else "blocked"
    kt.progress.deterministic_extraction = "complete"
    kt.state = kt.progress.state()
    save_task(root, kt)
    typer.echo(f"{root / 'bundles' / kt.id} ({len(bundle.documents)} document(s), state {kt.state.value})")


@research_app.command("retrieve")
def research_retrieve(
    task: Annotated[str, typer.Option(help="KnowledgeTask id, e.g. KT_0003.")],
    research: Annotated[Path, typer.Option(help="Research workspace directory.")],
    corpus_run: Annotated[Path | None, typer.Option(help="Carve the bundle out of an existing corpus run instead of querying.")] = None,
    select_top: Annotated[int, typer.Option(help="Documents kept per query, by relevance.")] = 6,
    min_score: Annotated[int, typer.Option(help="Relevance threshold for keeping a document.")] = 4,
    intervention: Annotated[bool, typer.Option(help="Stage 08 lane: lifts the therapy-term filter for this task's queries.")] = False,
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
        validator = None
        if intervention:
            from rarepipe.stages.discovery.lanes import check_intervention_query

            validator = check_intervention_query
        for q in kt.queries:
            corpus.run_query(q, kt.id, generated_by="human_operated_research", select_top=select_top,
                             min_score=min_score, console=console, validator=validator)
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
    synthesis_only: Annotated[bool, typer.Option(help="A synthesis pass: may only reconcile evidence earlier sessions already accepted.")] = False,
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
    existing = _max_session(research / "analyses")
    try:
        result = import_analysis(research, analysis, residue_needles=needles, session_index=existing + 1,
                                 synthesis_only=synthesis_only)
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


@mechanism_app.command("refresh-corpus")
def mechanism_refresh_corpus(
    corpus_run: Annotated[Path, typer.Option(help="The frozen corpus run to reopen. It is never modified.")],
    output: Annotated[Path, typer.Option(help="Directory under which the new corpus run is created.")],
    supplement: Annotated[list[str] | None, typer.Option(help="SOURCE_ID=path.pdf — a supplement a person downloaded by hand. Repeatable.")] = None,
    supplement_provenance: Annotated[list[Path] | None, typer.Option(help="JSON recording a supplied file's source, licence and publisher checksum (matched by delivered_filename). Repeatable.")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Reopen a frozen corpus as a new run: re-attempt licensed full text and supplements, record every outcome."""
    from rarepipe.stages.mechanism.refresh import refresh

    supplied: dict[str, list[Path]] = {}
    for item in supplement or []:
        source_id, _, path = item.partition("=")
        if not path or not Path(path).exists():
            typer.echo(f"error: --supplement expects SOURCE_ID=existing.pdf, got {item!r}", err=True)
            raise typer.Exit(EXIT_USAGE)
        supplied.setdefault(source_id, []).append(Path(path))
    import json as _j

    provenance = {}
    for path in supplement_provenance or []:
        record = _j.loads(path.read_text())
        provenance[record.get("delivered_filename") or path.stem] = record
    typer.echo(str(refresh(corpus_run, output, Console(quiet=quiet), supplied, provenance)))


@mechanism_app.command("resolve")
def mechanism_resolve(
    corpus_run: Annotated[Path, typer.Option(help="A sealed corpus run directory from `mechanism fetch-corpus`.")],
    adjudication_run: Annotated[Path, typer.Option(help="Stage 04 adjudicated_hypothesis.private.json.")],
    output: Annotated[Path, typer.Option(help="Directory under which a new immutable run directory is created.")],
    validation: Annotated[Path | None, typer.Option(help="Stage 05 external_validation_result.json, if the causal pair was validated.")] = None,
    research: Annotated[Path | None, typer.Option(help="Research workspace whose validated imported analyses to include.")] = None,
    alphagenome: Annotated[Path | None, typer.Option(help="Directory or file holding AlphaGenome evidence from `alphagenome match`.")] = None,
    compare_mechanism_run: Annotated[Path | None, typer.Option(help="A frozen mechanism run to compare this one against.")] = None,
    compare_track2_run: Annotated[Path | None, typer.Option(help="The frozen Track 2 run whose residual-function dependency is the baseline.")] = None,
    compare_label: Annotated[str, typer.Option(help="Name of the baseline, e.g. a release tag.")] = "",
    quiet: Annotated[bool, typer.Option(help="Suppress progress output.")] = False,
) -> None:
    """Resolve the molecular mechanism from the local corpus. Offline; no intervention reasoning."""
    from rarepipe.stages.mechanism.model import Status
    from rarepipe.stages.mechanism.stage import MechanismUsageError, ResolveRequest, run_resolve

    req = ResolveRequest(corpus_run=corpus_run, adjudication=adjudication_run, output=output,
                         validation=validation, research_dir=research, alphagenome=alphagenome,
                         compare_mechanism_run=compare_mechanism_run, compare_track2_run=compare_track2_run,
                         compare_label=compare_label, argv=sys.argv[:])
    try:
        result = run_resolve(req, Console(quiet=quiet))
    except MechanismUsageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_USAGE)
    typer.echo(str(result.run_dir))
    if result.dossier.status is Status.BLOCKED:
        raise typer.Exit(EXIT_BLOCKED)


def _max_session(folder: Path) -> int:
    """Highest LLMRS number already used — max, not count, so a removed file can never cause an overwrite."""
    numbers = [int(m.group(1)) for p in folder.glob("LLMRS_*.json") if (m := re.match(r"LLMRS_(\d+)", p.name))]
    return max(numbers, default=0) if folder.exists() else 0


export_app = typer.Typer(no_args_is_help=True, help="Generate external submission packages. Nothing is uploaded — a person submits.")
app.add_typer(export_app, name="export")

from rarepipe.stages.prospective.cli import app as prospective_app  # noqa: E402

app.add_typer(prospective_app, name="prospective")


@track2_app.command("check-pitch")
def track2_check_pitch(
    pitch: Annotated[Path, typer.Option(help="The pitch as edited by a person.")],
    claim_map: Annotated[Path, typer.Option(help="Reviewer's YAML mapping each sentence to artifact ids.")],
    run: Annotated[list[Path], typer.Option(help="A sealed run whose sanitized artifacts the pitch may cite. Repeatable.")],
    output: Annotated[Path, typer.Option(help="Where to write the check report (markdown).")],
) -> None:
    """Check that every sentence of an edited pitch traces to a sealed artifact. Never edits the pitch."""
    from rarepipe.stages.track2 import pitch_check as P

    results = P.check(pitch.read_text(), P.load_mapping(claim_map), P.artifact_text(run))
    output.write_text(P.render(pitch.name, results, run))
    failed = [r for r in results if r.fails]
    typer.echo(f"{output}\n{'PASS' if not failed else f'FAIL: {len(failed)} sentence(s)'}")
    if failed:
        raise typer.Exit(EXIT_BLOCKED)


@export_app.command("track2-package")
def export_track2_package(
    track2_run: Annotated[Path, typer.Option(help="A sealed Stage 09 run directory.")],
    output_zip: Annotated[Path, typer.Option(help="Where to write the package.")],
    submitter: Annotated[str, typer.Option(help="Prefix for the upload filenames.")],
    mechanism_run: Annotated[Path | None, typer.Option(help="Stage 06 run whose comparison and dossier report to include.")] = None,
    extra: Annotated[list[str] | None, typer.Option(help="ARCHIVE/PATH=local_file to add, e.g. verification/pytest.txt=out.txt. Repeatable.")] = None,
    note: Annotated[str, typer.Option(help="Free text for the README (what changed, for the reviewer).")] = "",
    pitch: Annotated[Path | None, typer.Option(help="A person's edited pitch to upload instead of the generated one. Its claim check must be supplied too.")] = None,
    pitch_check: Annotated[Path | None, typer.Option(help="The `track2 check-pitch` report for --pitch.")] = None,
) -> None:
    """Assemble a Track 2 package whose MANIFEST.sha256 verifies with `shasum -a 256 -c` as documented."""
    import json as _j

    from rarepipe.core.package import MANIFEST, VERIFY_COMMAND, PackageError, build

    t2 = _j.loads((track2_run / "track2_hypothesis_set.sanitized.json").read_text())
    baseline = t2.get("baseline") or {}
    report = next(track2_run.glob("*_track2_report.md"), None)
    files: dict[str, Path | str] = {
        f"upload/{submitter}_track2_report.md": report,
        f"upload/{submitter}_track2_pitch_script.md": track2_run / "track2_pitch_script.md",
        "verification/run_SHA256SUMS.txt": track2_run / "SHA256SUMS",
    }
    for name in ("track2_hypothesis_set.sanitized.json", "track2_baseline_snapshot.json",
                 "candidate_adjudication.md", "track2_submission_manifest.json"):
        files[f"records/{name}"] = track2_run / name
    if mechanism_run:
        for name in ("comparison_with_baseline.md", "mechanism_dossier.md"):
            if (mechanism_run / name).exists():
                files[f"records/stage06/{name}"] = mechanism_run / name
        files["verification/stage06_run_SHA256SUMS.txt"] = mechanism_run / "SHA256SUMS"
    if pitch:
        if not pitch_check or "**Result: PASS**" not in pitch_check.read_text():
            typer.echo("error: an edited pitch is uploaded only with a passing `track2 check-pitch` report", err=True)
            raise typer.Exit(EXIT_BLOCKED)
        files[f"upload/{submitter}_track2_pitch_script.md"] = pitch
        files["records/generated_pitch_script.md"] = track2_run / "track2_pitch_script.md"
        files["verification/pitch_claim_check.md"] = pitch_check
    if mechanism_run:
        for path in sorted(mechanism_run.glob("input_*.yaml")) + [mechanism_run / "direction_corrections.json"]:
            if path.exists():
                files[f"records/stage06/{path.name}"] = path
    for item in extra or []:
        arcname, _, path = item.partition("=")
        if not path or not Path(path).exists():
            typer.echo(f"error: --extra expects ARCHIVE/PATH=existing_file, got {item!r}", err=True)
            raise typer.Exit(EXIT_USAGE)
        files[arcname] = Path(path)
    missing = [a for a, p in files.items() if isinstance(p, Path | None) and (p is None or not p.exists())]
    if missing:
        typer.echo(f"error: missing from the run: {', '.join(missing)}", err=True)
        raise typer.Exit(EXIT_USAGE)
    root = output_zip.stem
    files["README.txt"] = "\n".join([
        f"TRACK 2 PACKAGE — {t2.get('case_id')} · {t2.get('status')}",
        f"Stage 09 run {track2_run.name} · digest {t2.get('semantic_digest')}",
        f"Built on commit {baseline.get('git_commit')} ({baseline.get('git_describe')}). "
        f"public_evidence_only: {baseline.get('public_evidence_only')} · "
        f"created_before_network_search: {baseline.get('created_before_network_search')}",
        f"Provenance: mechanism {baseline.get('mechanism_run_id')} → map {baseline.get('intervention_map_run_id')} "
        f"→ discovery {baseline.get('discovery_run_id')} → this run",
        "", *( [note, ""] if note else [] ),
        "upload/        the files a person submits",
        "records/       the sanitized artifacts the upload was generated from",
        "verification/  the sealed runs' own checksum lists, and anything else supplied",
        "",
        "VERIFY THE PACKAGE",
        f"  cd {root} && {VERIFY_COMMAND}",
        f"  {MANIFEST} lists every file in this folder by its path here, so every line should say OK.",
        "",
        "CROSS-CHECK AGAINST THE SEALED RUN",
        "  verification/run_SHA256SUMS.txt is the run directory's own list on the controlled drive. It also",
        "  names private files that are never exported, so do not run `shasum -c` against it here. Instead,",
        "  each records/ file's hash in MANIFEST.sha256 equals its line in run_SHA256SUMS.txt, and the two",
        "  upload files equal the run's *_track2_report.md and track2_pitch_script.md lines"
        + (" — except an edited pitch, which is checked by verification/pitch_claim_check.md instead; the generated "
           "one is kept as records/generated_pitch_script.md." if pitch else "."),
        *(["  records/stage06/ files likewise equal their lines in verification/stage06_run_SHA256SUMS.txt."]
          if mechanism_run else []),
        ""])
    try:
        build(output_zip, files, root)
    except PackageError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_BLOCKED)
    typer.echo(str(output_zip))


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


@app.command()
def reason(
    model_id: Annotated[str, typer.Option(help="Which compiled map to solve. Only MVA_001 is wired.")] = "MVA_001",
    target: Annotated[str | None, typer.Option(help="Node to solve for; defaults to the map's declared target.")] = None,
    horizon: Annotated[int, typer.Option(help="Maximum number of campaigns a policy may use.")] = 6,
    max_states: Annotated[int, typer.Option(help="Budget in state evaluations. Exhausting it reports NOT_ESTABLISHED/BUDGET, never FALSE.")] = 3_000_000,
    include_invalid_runs: Annotated[bool, typer.Option(help="Quantify over assay-validity failures as if they were results.")] = False,
    output: Annotated[Path | None, typer.Option(help="Write the full machine-readable answer here.")] = None,
) -> None:
    """Is there a contingent policy that reaches the target whatever the admissible results are?

    Runs with no language model anywhere in the path. That is the point: the mathematical result
    has to exist without one, and only then is it handed to a model for explanation.
    """
    if model_id != "MVA_001":
        typer.echo(f"error: no adapter for {model_id!r}; only MVA_001 is wired", err=True)
        raise typer.Exit(EXIT_USAGE)

    import importlib.util

    adapter_path = Path(__file__).resolve().parents[2] / "tools/control/solve_mva_policy.py"
    if not adapter_path.exists():
        typer.echo(f"error: adapter missing at {adapter_path}", err=True)
        raise typer.Exit(EXIT_USAGE)
    spec = importlib.util.spec_from_file_location("solve_mva_policy", adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    document = adapter.load()
    _, _, _, result = adapter.solve(document, horizon=horizon,
                                    include_non_informative=include_invalid_runs,
                                    max_states=max_states)
    answer = result.describe()
    verdict = answer["robust_reachable"]
    typer.echo(f"map              {adapter.digest()}")
    typer.echo(f"target           {answer['target']}")
    typer.echo(f"conditional      {answer['conditional_reachable']}")
    typer.echo(f"robust           {verdict}")
    typer.echo(f"minimal horizon  {answer['minimal_robust_horizon']}")
    typer.echo(f"none within      {answer['no_robust_policy_within']} campaigns (searched exhaustively)")
    typer.echo(f"mode             {answer['mode']}")
    typer.echo(f"recommended      {', '.join(answer['recommended_actions']) or 'none'}"
               f"  ({answer['tied_action_count']} tied)")
    typer.echo(f"states           {answer['trace']['states_considered']}"
               f"{'  BUDGET EXHAUSTED' if answer['trace']['budget_exhausted'] else ''}")
    for combo in answer["failure_certificates"].get("minimal_closing_combinations", [])[:8]:
        typer.echo("closes target    " + " + ".join(f"{c['branch']}={c['outcome']}" for c in combo))
    if output:
        output.write_text(json.dumps(answer, indent=2, sort_keys=True) + "\n")
        typer.echo(f"wrote            {output}")


def main() -> None:
    app()
