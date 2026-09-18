"""baseline_analysis stage: NormalizedCase → RawCandidateSet.

Contract
    input:   a *private* NormalizedCase, the source VCF it declares, a pinned Exomiser
             installation + data directory
    output:  <output>/<run_id>/{raw_candidate_set.private.json, raw_candidate_set.sanitized.json,
                                baseline_report.md, baseline.log, job YAMLs, SHA256SUMS}
             plus native solver outputs under <output>/native/<run_id>/ (restricted, delete-required)
    states:  BASELINE_ANALYSIS_COMPLETE | ..._WITH_WARNINGS | ..._BLOCKED

This is the first stage permitted to produce biological hypotheses — and it produces
none of its own: it records what Exomiser reported under four declared profiles.
No reranking, no gene shortlists, no disease name is ever passed to the solver.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.issues import Severity
from rarepipe.core.provenance import software_provenance
from rarepipe.core.redaction import clear_restricted
from rarepipe.resources.lock import sha256_file
from rarepipe.stages.baseline import compare, exomiser, ingest, profiles as prof, report
from rarepipe.stages.baseline.model import (
    SUPPORTED_NORMALIZED_MAJOR,
    BaselineIssueCode,
    Execution,
    Issue,
    ProfileResult,
    ProfileRuntime,
    Provenance,
    RawCandidateSet,
    SolverIdentity,
    SourceCase,
    Status,
)

PRIVATE = "raw_candidate_set.private.json"
SANITIZED = "raw_candidate_set.sanitized.json"
REPORT = "baseline_report.md"
LOG = "baseline.log"


class BaselineUsageError(ValueError):
    """Invalid invocation or unusable input artifact."""


@dataclass
class BaselineRequest:
    normalized_case: Path
    output: Path
    exomiser_home: Path | None = None
    exomiser_data: Path | None = None
    resources: Path | None = None
    profile_ids: list[str] = field(default_factory=list)
    max_heap: str = "7g"
    timeout_seconds: int = 6 * 3600
    case_root: Path | None = None
    dry_run: bool = False
    argv: list[str] = field(default_factory=list)


@dataclass
class BaselineResult:
    candidate_set: RawCandidateSet
    sanitized: RawCandidateSet
    run_dir: Path


def _issue(code: BaselineIssueCode, severity: Severity, message: str, **kw) -> Issue:
    return Issue(code=code.value, severity=severity, message=message, **kw)


def _digest(case: RawCandidateSet) -> str:
    data = case.model_dump(mode="json", by_alias=True, exclude={"execution", "semantic_digest"})
    return "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _load_normalized(path: Path) -> dict:
    if not path.is_file():
        raise BaselineUsageError("normalized-case file does not exist.")
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise BaselineUsageError("normalized case is not valid JSON.") from exc
    schema = data.get("schema", {})
    if schema.get("name") != "NormalizedCase" or str(schema.get("version", "")).split(".")[0] != SUPPORTED_NORMALIZED_MAJOR:
        raise BaselineUsageError(f"unsupported artifact: expected NormalizedCase {SUPPORTED_NORMALIZED_MAJOR}.x.")
    if data.get("visibility") != "private":
        raise BaselineUsageError("a sanitized NormalizedCase cannot be analysed; pass normalized_case.private.json.")
    return data


def resolve_source_vcf(norm: dict, case_root_override: Path | None) -> tuple[Path, str, str]:
    """(vcf path, asset id, expected sha256) — resolved through the artifact chain, never by
    walking the case directory, and verified against the digests Stage 01/02 recorded."""
    manifest_path = Path(norm["execution"].get("source_manifest_path") or "")
    if not manifest_path.is_file():
        raise BaselineUsageError("the CaseManifest referenced by this NormalizedCase is not at its recorded location.")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != norm["provenance"]["source_manifest"]["manifest_sha256"]:
        raise BaselineUsageError("the referenced CaseManifest no longer matches the digest recorded in the NormalizedCase.")
    manifest = json.loads(raw)
    asset_id = norm["genome"]["variant_source"]["asset_id"]
    asset = next(a for a in manifest["assets"] if a["asset_id"] == asset_id)
    root = case_root_override or Path(manifest["provenance"]["configuration"]["case_root"])
    return (root / asset["relative_path"]).resolve(), asset_id, asset["checksum_sha256"]


def run_baseline(req: BaselineRequest, console: Console | None = None) -> BaselineResult:
    console = console or Console()
    norm = _load_normalized(req.normalized_case)
    out = req.output.resolve()
    if out.is_relative_to(req.normalized_case.resolve().parent):
        raise BaselineUsageError("output must be outside the Stage 02 run directory.")

    started = utc_now()
    t0 = time.monotonic()
    run_id = new_run_id(started)
    native_root = (req.output / "native" / run_id).resolve()
    case = _run(req, console, norm, run_id, started, t0, native_root)

    sanitized = case.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = _digest(sanitized)

    console.step(6, 6, "Writing RawCandidateSet...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(PRIVATE, canonical_json(case))
    run.write_text(SANITIZED, canonical_json(sanitized))
    run.write_text(REPORT, report.render(sanitized))
    console.ok(f"run {run_id}: private + sanitized RawCandidateSet, report, log")
    console.line()
    console.line(case.status.value)
    if case.stability:
        console.line(f"\nStability across profiles: {case.stability.verdict} — {case.stability.verdict_basis}")
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return BaselineResult(candidate_set=case, sanitized=sanitized, run_dir=run.seal())


def _run(req: BaselineRequest, console: Console, norm: dict, run_id: str, started, t0: float, native_root: Path) -> RawCandidateSet:
    issues: list[Issue] = []

    # ── 1. upstream contract ────────────────────────────────────────────────
    console.step(1, 6, "Loading NormalizedCase...")
    caps = {c["capability"]: c for c in norm["readiness"]}
    vcf_ready = caps.get("vcf_based_prioritization", {}).get("ready")
    pheno_ready = caps.get("phenotype_based_prioritization", {}).get("ready")
    console.ok(f"NormalizedCase {norm['schema']['version']} run {norm['execution']['run_id']}: {norm['status']}")
    console.info(f"vcf_based_prioritization: {vcf_ready}; phenotype_based_prioritization: {pheno_ready}")
    if vcf_ready == "no" or pheno_ready == "no":
        issues.append(_issue(BaselineIssueCode.UPSTREAM_NOT_READY, Severity.BLOCKER,
                             "NormalizedCase reports a required capability as not ready.",
                             evidence=[f"vcf_based_prioritization={vcf_ready}", f"phenotype_based_prioritization={pheno_ready}"],
                             suggested_action="Resolve the blocking reasons recorded in Stage 02 before analysis."))

    vcf_path, asset_id, expected_sha = resolve_source_vcf(norm, req.case_root)
    if not vcf_path.is_file():
        issues.append(_issue(BaselineIssueCode.SOURCE_ASSET_CHANGED, Severity.BLOCKER, "The source VCF is not at its recorded location.",
                             suggested_action="Mount the case at its original location or pass --case-root."))
        actual_sha = None
    else:
        actual_sha = sha256_file(vcf_path)
        if actual_sha != expected_sha:
            issues.append(_issue(BaselineIssueCode.SOURCE_ASSET_CHANGED, Severity.BLOCKER,
                                 "The source VCF no longer matches the digest recorded upstream.",
                                 suggested_action="Re-run Stage 01 and Stage 02 before analysing."))
    console.ok(f"source VCF {asset_id}: {'verified' if actual_sha == expected_sha else 'MISMATCH'}")

    # ── 2. solver ───────────────────────────────────────────────────────────
    console.step(2, 6, "Locating pinned solver...")
    install = exomiser.locate(req.exomiser_home, req.exomiser_data) if req.exomiser_home else None
    if install is None:
        issues.append(_issue(BaselineIssueCode.SOLVER_UNAVAILABLE, Severity.BLOCKER,
                             "Exomiser installation or a Java 21+ runtime was not found.",
                             suggested_action="Provision Exomiser and pass --exomiser-home."))
        console.fail("Exomiser not available")
    elif not (install.hg38_version and install.phenotype_version):
        issues.append(_issue(BaselineIssueCode.SOLVER_DATA_UNAVAILABLE, Severity.BLOCKER,
                             "Exomiser data directory has no hg38 and phenotype data releases.",
                             suggested_action="Unzip the pinned data bundles into the data directory."))
        console.fail(f"Exomiser {install.version}: data incomplete")
    else:
        console.ok(f"Exomiser {install.version}; data hg38={install.hg38_version}, phenotype={install.phenotype_version}; {install.java_version}")

    pinned = _pinned_solver_resources(req.resources)
    solver = SolverIdentity(
        version=install.version if install else "unavailable", jar_sha256=install.jar_sha256 if install else None,
        hg38_data_version=install.hg38_version if install else None, phenotype_data_version=install.phenotype_version if install else None,
        java_version=install.java_version if install else None, java_max_heap=req.max_heap,
        distribution_sha256=pinned.get("exomiser_distribution"), data_sha256={k: v for k, v in pinned.items() if k.startswith("exomiser_data")},
    )
    if req.resources and not pinned:
        console.warn("no pinned Exomiser resources in the lock; solver identity rests on the jar digest and data versions alone")

    # ── 3. profiles ─────────────────────────────────────────────────────────
    console.step(3, 6, "Building analysis profiles...")
    terms = norm["phenotype"]["terms"]
    proband = _proband_label(norm)
    specs = [s for s in prof.PROFILE_SPECS if not req.profile_ids or s.profile_id in req.profile_ids]
    properties_text = prof.application_properties(install.data_dir, install.hg38_version, install.phenotype_version) if install and install.data_dir else ""
    built, run_inputs = [], {}
    native_root.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        ids, _ = prof.select_terms(terms, spec.phenotype_rule)
        profile_out = native_root / spec.profile_id.lower()
        profile_out.mkdir(parents=True, exist_ok=True)
        analysis_text, sample_text, output_text = prof.analysis_yaml(spec), prof.sample_yaml(proband, ids), prof.output_options_yaml()
        paths = {}
        for name, text in (("analysis.yml", analysis_text), ("sample.yml", sample_text),
                           ("output-options.yml", output_text), ("application.properties", properties_text)):
            (profile_out / name).write_text(text)
            paths[name] = profile_out / name
        prefix = f"{norm['case_id']}-{spec.profile_id.lower()}"
        run_inputs[spec.profile_id] = (paths, profile_out, prefix)
        built.append(prof.build_profile(spec, terms, analysis_text, sample_text, properties_text))
        console.info(f"{spec.profile_id}: {len(ids)} HPO term(s); failedVariantFilter={spec.failed_variant_filter}; analysisMode=PASS_ONLY")
    issues.append(_issue(BaselineIssueCode.PHENOTYPE_ASSUMPTION_APPLIED, Severity.INFO,
                         "Supplied HPO terms are used as features describing the child for this analysis; the case record still states polarity: unspecified.",
                         evidence=[prof.PHENOTYPE_ASSUMPTION.basis]))
    issues.append(_issue(BaselineIssueCode.ANALYSIS_ROLE_ASSUMED, Severity.INFO,
                         "The single sample is designated proband for this analysis only; no family structure is asserted.",))

    # ── 4. run ──────────────────────────────────────────────────────────────
    console.step(4, 6, "Running solver per profile (offline)...")
    results: list[ProfileResult] = []
    runtimes: list[ProfileRuntime] = []
    blocked = any(i.severity == Severity.BLOCKER for i in issues)
    for spec in specs:
        paths, profile_out, prefix = run_inputs[spec.profile_id]
        if blocked or req.dry_run or install is None:
            results.append(ProfileResult(profile_id=spec.profile_id, status="not_run",
                                         failure_reason="dry run" if req.dry_run else "prerequisites not met",
                                         candidate_count=0, candidates=[]))
            console.warn(f"{spec.profile_id}: not run")
            continue
        outcome = exomiser.run_job(
            install, sample=paths["sample.yml"], analysis=paths["analysis.yml"], output_options=paths["output-options.yml"],
            vcf=vcf_path, assembly=prof.GENOME_ASSEMBLY, output_dir=profile_out, output_prefix=prefix,
            properties=paths["application.properties"], log_path=profile_out / "exomiser.log",
            max_heap=req.max_heap, timeout_seconds=req.timeout_seconds)
        results.append(_ingest_profile(spec.profile_id, outcome, profile_out, prefix, norm, issues, runtimes, console, source_vcf=vcf_path))

    # ── 5. compare ──────────────────────────────────────────────────────────
    console.step(5, 6, "Comparing profiles...")
    stability = compare.compare(results, {p.profile_id: p.filter_policy.non_pass_records_permitted for p in built},
                                {p.profile_id: p.phenotype.term_count for p in built})
    if stability.verdict in ("unstable", "partially_stable"):
        issues.append(_issue(BaselineIssueCode.PROFILE_DISAGREEMENT, Severity.WARNING,
                             f"Candidate ranking is {stability.verdict.replace('_', ' ')} across analytical choices: {stability.verdict_basis}",
                             profile_ids=stability.profiles_compared))
    if stability.genes_only_when_non_pass_permitted:
        issues.append(_issue(BaselineIssueCode.NON_PASS_ONLY_CANDIDATE, Severity.WARNING,
                             f"{len(stability.genes_only_when_non_pass_permitted)} top candidate gene(s) appear only when non-PASS records are permitted.",
                             evidence=stability.genes_only_when_non_pass_permitted[:10],
                             suggested_action="Treat these as filter-policy dependent; their supporting variants failed upstream quality thresholds."))
    pair_count = sum(1 for r in results for c in r.candidates if c.is_variant_pair)
    if pair_count:
        issues.append(_issue(BaselineIssueCode.CANDIDATE_PHASE_UNRESOLVED, Severity.WARNING,
                             f"{pair_count} candidate(s) are compound-heterozygous configurations whose trans/cis phase is unresolved.",
                             suggested_action="Phase adjudication for specific candidate pairs is a later stage; read-backed PGT/PID was not consulted here."))
    multiallelic = (norm.get("genome", {}).get("variant_source") or {}).get("multiallelic_records") or 0
    if multiallelic and any(r.status == "completed" for r in results):
        issues.append(_issue(BaselineIssueCode.MULTIALLELIC_HANDLING_UNVERIFIED, Severity.WARNING,
                             f"The source VCF contains {multiallelic:,} multiallelic records; the solver's treatment of them is evidenced only by the synthetic fixture test, not measured on this case.",
                             suggested_action="If candidate variants come from multiallelic sites, verify their representation before trusting the call."))

    counts = {s.value: sum(1 for i in issues if i.severity == s) for s in Severity}
    status = (Status.BASELINE_ANALYSIS_BLOCKED if counts["BLOCKER"]
              else Status.BASELINE_ANALYSIS_COMPLETE_WITH_WARNINGS if counts["ACTION_REQUIRED"] or counts["WARNING"]
              else Status.BASELINE_ANALYSIS_COMPLETE)

    case = RawCandidateSet(
        visibility="private", case_id=norm["case_id"], status=status, profiles=built, results=results,
        stability=stability, issues=sorted(issues, key=lambda i: (i.severity.rank, i.code)), issue_counts=counts,
        provenance=Provenance(
            software=software_provenance(), solver=solver,
            source_case=SourceCase(case_id=norm["case_id"], normalized_case_run_id=norm["execution"]["run_id"],
                                   normalized_case_semantic_digest=norm.get("semantic_digest"),
                                   normalized_case_sha256=hashlib.sha256(req.normalized_case.read_bytes()).hexdigest(),
                                   source_vcf_asset_id=asset_id, source_vcf_sha256=expected_sha,
                                   assembly=(norm["genome"].get("reference") or {}).get("assembly", "unknown")),
            environment_controls=["no network access performed by baseline analysis", "source VCF opened read-only and never rewritten",
                                  "no variant rows written to logs or reports", "solver invoked as a child process inheriting the caller's sandbox"],
            execution_host={"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version()},
        ),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3), profile_runtimes=runtimes,
                            native_output_root=str(native_root), normalized_case_path=str(req.normalized_case.resolve()),
                            source_vcf_path=str(vcf_path), argv=req.argv),
    )
    case.semantic_digest = _digest(case)
    return case


def _pinned_solver_resources(resources: Path | None) -> dict[str, str]:
    """SHA-256 of the distribution and data bundles, from resources.lock.json (PRD 003 §11)."""
    if not resources:
        return {}
    from rarepipe.resources.lock import ResourceKind, load_lock

    lock = load_lock(resources)
    out: dict[str, str] = {}
    for entry in (lock.resources if lock else []):
        if entry.kind == ResourceKind.EXOMISER_DISTRIBUTION:
            out["exomiser_distribution"] = entry.sha256
        elif entry.kind == ResourceKind.EXOMISER_DATA:
            out[f"exomiser_data:{entry.version}"] = entry.sha256
    return out


def _proband_label(norm: dict) -> str:
    samples = norm["genome"]["samples"]
    labels = samples[0].get("source_labels") or []
    return labels[0] if labels else samples[0]["sample_id"]


def _ingest_profile(profile_id: str, outcome, profile_out: Path, prefix: str, norm: dict, issues: list[Issue],
                    runtimes: list[ProfileRuntime], console: Console, source_vcf: Path | None = None) -> ProfileResult:
    base = dict(profile_id=profile_id, exit_code=outcome.exit_code)
    runtimes.append(ProfileRuntime(profile_id=profile_id, wall_clock_seconds=outcome.wall_clock_seconds,
                                   peak_rss_bytes=outcome.peak_rss_bytes))
    if outcome.exit_code != 0:
        if outcome.out_of_memory:
            code, reason = BaselineIssueCode.SOLVER_OUT_OF_MEMORY, "solver exhausted the Java heap"
            action = (f"This host has limited RAM; Exomiser documents ~8 GB for genome-scale analysis. Raise --max-heap on a larger "
                      f"machine, or record this as the scientific result: the case cannot be analysed here as supplied.")
        elif outcome.rejected_input:
            code, reason = BaselineIssueCode.SOLVER_REJECTED_INPUT, "solver rejected the input as supplied"
            action = ("Do not rewrite the VCF here. Record the smallest missing capability (contig renaming, multiallelic "
                      "decomposition, reference binding) — that is what would justify an input-adaptation stage.")
        else:
            code, reason = BaselineIssueCode.SOLVER_RUN_FAILED, f"solver exited with code {outcome.exit_code}" + (" (timeout)" if outcome.timed_out else "")
            action = "Inspect the native solver log (restricted artifact); it is not copied into this artifact."
        issues.append(_issue(code, Severity.BLOCKER, f"{profile_id}: {reason}.", profile_ids=[profile_id], suggested_action=action))
        console.fail(f"{profile_id}: {reason} after {outcome.wall_clock_seconds}s (peak RSS {outcome.peak_rss_bytes / 1e9:.1f} GB)")
        return ProfileResult(**base, status="failed", failure_reason=reason, candidate_count=0, candidates=[])

    files = ingest.find_outputs(profile_out, prefix)
    if "genes_tsv" not in files or "variants_tsv" not in files:
        issues.append(_issue(BaselineIssueCode.SOLVER_RUN_FAILED, Severity.BLOCKER,
                             f"{profile_id}: solver exited cleanly but the expected TSV outputs are missing.", profile_ids=[profile_id]))
        console.fail(f"{profile_id}: outputs missing")
        return ProfileResult(**base, status="failed", failure_reason="expected outputs missing", candidate_count=0, candidates=[])

    candidates = ingest.build_candidates(files["genes_tsv"], files["variants_tsv"], source_vcf=source_vcf)
    contigs = ingest.contigs_in_output(files["variants_tsv"])
    source_contigs = {c["source_name"] for c in (norm["genome"].get("reference") or {}).get("contigs", []) if c.get("records")}
    result = ProfileResult(
        **base, status="completed", candidate_count=len(candidates), candidates=candidates,
        variants_in_source=(norm["genome"].get("variant_source") or {}).get("records_parsed"),
        variants_reported_by_solver=len(ingest.read_tsv(files["variants_tsv"])),
        contigs_absent_from_solver_output=sorted(source_contigs - set(contigs))[:50],
        native_output_files=sorted(p.relative_to(profile_out.parent).as_posix() for p in list(files.values()) + [outcome.log_path]),
        native_output_sha256={p.name: sha256_file(p) for p in sorted(files.values())},
    )
    if not candidates:
        issues.append(_issue(BaselineIssueCode.PROFILE_PRODUCED_NO_CANDIDATES, Severity.ACTION_REQUIRED,
                             f"{profile_id}: the solver completed but ranked no genes.", profile_ids=[profile_id]))
    pairs = sum(1 for c in candidates if c.is_variant_pair)
    console.ok(f"{profile_id}: {len(candidates)} ranked gene/MOI candidate(s), {pairs} compound-het pair(s), "
               f"{outcome.wall_clock_seconds}s, peak RSS {outcome.peak_rss_bytes / 1e9:.1f} GB")
    return result
