"""Stage 05 — generate one Track 1 submission package, and later record its result.

The stage does not upload anything. It produces a file a person submits deliberately,
and a snapshot that fixes what the pipeline knew beforehand.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.digest import semantic_digest
from rarepipe.core.provenance import software_provenance
from rarepipe.core.redaction import clear_restricted
from rarepipe.stages.track1 import epcr as epcr_mod
from rarepipe.stages.track1 import export, methods, select
from rarepipe.stages.track1.model import (
    BRANCHES,
    MAX_ROWS,
    PROBAND_ID,
    EpcrSchedule,
    Execution,
    ExternalValidationResult,
    Provenance,
    ScoredResult,
    SelectionRule,
    SubmissionFile,
    SubmissionRow,
    SubmissionState,
    SubmissionVariant,
    Track1SubmissionPackage,
    ValidationSnapshot,
)

CSV_NAME = "track1_submission.csv"
METHODS_NAME = "track1_methods.md"
MANIFEST_NAME = "submission_manifest.json"
PACKAGE_NAME = "track1_submission_package.private.json"
SNAPSHOT_NAME = "validation_snapshot.json"
RESULT_NAME = "external_validation_result.json"
LOG = "export_track1.log"


class Track1UsageError(ValueError):
    pass


@dataclass
class ExportRequest:
    raw_candidate_set: Path
    adjudication: Path
    output: Path
    proband_id: str = PROBAND_ID
    official_scorer: Path | None = None
    llm_disclosure: str | None = None
    submitter: str | None = None
    argv: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    package: Track1SubmissionPackage
    manifest: Track1SubmissionPackage
    csv_text: str
    run_dir: Path


def _load(path: Path) -> dict:
    if not path.exists():
        raise Track1UsageError(f"not found: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise Track1UsageError(f"not valid JSON: {path} ({exc})") from exc


def _git_dirty() -> bool | None:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


def _describe() -> str | None:
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always"], cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _leading_row(adjudication: dict, alias_map: dict[str, str] | None) -> SubmissionRow:
    """Row 1: the adjudicated hypothesis, as one compound-heterozygous row."""
    variants = adjudication.get("variants", [])
    if len(variants) != 2:
        raise Track1UsageError(f"expected two adjudicated variants, found {len(variants)}")
    missing = [v["role"] for v in variants if not all(v.get(k) for k in ("contig", "position", "ref", "alt"))]
    if missing:
        raise Track1UsageError(f"adjudicated variant(s) {missing} lack exact identity; pass the PRIVATE artifact")
    payload = [{"chrom": select.ucsc_contig(v["contig"], alias_map), "pos": int(v["position"]),
                "ref": v["ref"].upper(), "alt": v["alt"].upper(), "source_contig": v["contig"],
                "hgvs": v.get("hgvs"), "functional_class": v.get("molecular_consequence")} for v in variants]
    payload.sort(key=select.coordinate_key)
    summary = adjudication.get("evidence_summary", {})
    src = adjudication.get("provenance", {}).get("source_hypothesis", {})
    notes = (f"Adjudicated hypothesis: {adjudication.get('gene_symbol')} "
             f"{adjudication.get('inheritance_model')}; mechanism {summary.get('molecular_mechanistic', 'n/a')}; "
             f"phase {adjudication.get('phase', {}).get('status', 'unresolved')}")
    return SubmissionRow(rank=1, epcr=1.0, configuration="candidate_compound_heterozygous",
                         gene_symbol=adjudication.get("gene_symbol"), inheritance_model=adjudication.get("inheritance_model"),
                         finding_type="primary", notes=notes[:200],
                         variants=[SubmissionVariant(**p) for p in payload],
                         selected_by="adjudicated_hypothesis", profiles_supporting=src.get("profiles_supporting", []),
                         best_profile_rank=src.get("solver_rank"),
                         phase=adjudication.get("phase", {}).get("status", "unresolved"))


def run_export(req: ExportRequest, console: Console | None = None) -> ExportResult:
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)

    console.step(1, 5, "Freezing the validation snapshot...")
    candidates = _load(req.raw_candidate_set)
    adjudication = _load(req.adjudication)
    if adjudication.get("visibility") != "private":
        raise Track1UsageError("the adjudication artifact must be the private one; the sanitized one has no coordinates")
    case_id = adjudication.get("case_id")
    assembly = next((v.get("assembly") for v in adjudication.get("variants", []) if v.get("assembly")), None)
    if not assembly:
        raise Track1UsageError("no assembly recorded on the adjudicated variants")
    src = adjudication.get("provenance", {}).get("source_hypothesis", {})
    software = software_provenance()
    snapshot = ValidationSnapshot(
        intake_run=candidates.get("provenance", {}).get("source_case", {}).get("case_manifest_run_id"),
        normalization_run=src.get("normalized_case_run_id"),
        baseline_run=src.get("raw_candidate_set_run_id") or candidates.get("execution", {}).get("run_id"),
        adjudication_run=adjudication.get("execution", {}).get("run_id"),
        baseline_digest=candidates.get("semantic_digest"), adjudication_digest=adjudication.get("semantic_digest"),
        git_commit=software.source_control.commit, git_describe=_describe(), git_dirty=_git_dirty(),
        created_before_ground_truth_query=True, created_at=started.isoformat())
    snapshot_json = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
    snapshot_digest = "sha256:" + hashlib.sha256(snapshot_json.encode()).hexdigest()
    console.info(f"baseline {snapshot.baseline_run} · adjudication {snapshot.adjudication_run}")
    console.info(f"commit {snapshot.git_commit} ({snapshot.git_describe}), dirty={snapshot.git_dirty}")
    if snapshot.git_dirty:
        console.warn("the working tree has uncommitted changes — the snapshot's commit does not fully describe this run")

    console.step(2, 5, "Building rows...")
    leading = _leading_row(adjudication, None)
    exclude = select.configuration_key([v.model_dump() for v in leading.variants])
    ranked = select.rank_configurations(candidates, exclude, None)
    rows = [leading]
    for entry in ranked[: MAX_ROWS - 1]:
        rows.append(SubmissionRow(
            rank=len(rows) + 1, epcr=1.0, configuration=entry["configuration"], gene_symbol=entry["gene_symbol"],
            inheritance_model=entry["inheritance_model"] or "unspecified", finding_type="primary",
            notes=(f"Baseline candidate; reported by {len(entry['profiles'])} of "
                   f"{len(candidates.get('results', []))} profiles; best solver rank {entry['best_profile_rank']}")[:200],
            variants=[SubmissionVariant(**v) for v in entry["variants"]], selected_by="baseline_stability_rule",
            profiles_supporting=entry["profiles"], best_profile_rank=entry["best_profile_rank"],
            phase="unresolved", variants_dropped=entry["variants_dropped"]))
    values = epcr_mod.schedule(len(rows))
    for row, value in zip(rows, values, strict=True):
        row.epcr = value
    console.info(f"{len(rows)} row(s): rank 1 {rows[0].gene_symbol} (adjudicated), "
                 f"{len(rows) - 1} from the baseline rule")

    console.step(3, 5, "Rendering and validating the predictions file...")
    csv_text = export.render_csv(req.proband_id, rows)
    run = RunDirectory(req.output, run_id).open()
    csv_path = run.write_text(CSV_NAME, csv_text)
    checks = export.checks(req.proband_id, rows, csv_text)
    scorer = export.run_official_parser(req.official_scorer, csv_path, rows)
    valid = all(c.passed for c in checks) and (scorer.parsed_ok is not False)
    for c in checks:
        (console.ok if c.passed else console.fail)(f"{c.check}" + (f" — {c.detail}" if c.detail and not c.passed else ""))
    if scorer.available:
        (console.ok if scorer.parsed_ok else console.fail)(
            f"official evaluation.py parsed the file: {scorer.rows_parsed} row(s), order preserved={scorer.ranks_as_submitted}"
            if scorer.parsed_ok else f"official evaluation.py rejected the file: {scorer.error}")
    else:
        console.warn("official evaluation.py was not run (pass --official-scorer)")

    console.step(4, 5, "Assembling the package...")
    prediction_digest = "sha256:" + hashlib.sha256(csv_text.encode()).hexdigest()
    stem = f"{req.submitter}_rarepipe-exomiser-adjudicated.csv" if req.submitter else "rarepipe-exomiser-adjudicated.csv"
    package = Track1SubmissionPackage(
        visibility="private", case_id=case_id, proband_id=req.proband_id, assembly=assembly, rows=rows,
        selection_rule=SelectionRule(
            description=("Row 1 is the Stage 04 adjudicated hypothesis. Rows 2–10 come from Stage 03 by a rule fixed "
                         "before generation, using cross-profile robustness rather than a new ranker."),
            steps=select.SELECTION_STEPS, profiles_considered=[r.get("profile_id") for r in candidates.get("results", [])],
            deduplication="configurations are keyed by their variant set, so the same set found under several profiles or "
                          "inheritance models collapses to one row",
            tie_breaks=select.TIE_BREAKS, rows_considered=ranked[0]["considered"] if ranked else 0, rows_emitted=len(rows)),
        epcr_schedule=EpcrSchedule(description=epcr_mod.DESCRIPTION, values=values),
        checks=checks, official_scorer=scorer, valid=valid,
        files=[], submission=SubmissionState(recommended_upload_filename=stem),
        provenance=Provenance(software=software, validation_snapshot=snapshot, snapshot_digest=snapshot_digest,
                              prediction_digest=prediction_digest),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3),
                            raw_candidate_set_path=str(req.raw_candidate_set.resolve()),
                            adjudication_path=str(req.adjudication.resolve()), argv=req.argv))

    console.step(5, 5, "Writing the methods report and manifest...")
    sanitized_adj = json.loads(canonical_json(adjudication)) if isinstance(adjudication, dict) else adjudication
    methods_text = methods.render(package, sanitized_adj, candidates,
                                  req.llm_disclosure or methods.DEFAULT_LLM_DISCLOSURE)
    run.write_text(METHODS_NAME, methods_text)
    run.write_text(SNAPSHOT_NAME, json.dumps(snapshot.model_dump(mode="json"), indent=2) + "\n")
    package.files = [
        SubmissionFile(name=CSV_NAME, sha256=prediction_digest, bytes=len(csv_text.encode()),
                       contains_case_specific_identity=True),
        SubmissionFile(name=METHODS_NAME, sha256="sha256:" + hashlib.sha256(methods_text.encode()).hexdigest(),
                       bytes=len(methods_text.encode())),
        SubmissionFile(name=SNAPSHOT_NAME, sha256=snapshot_digest, bytes=len(snapshot_json.encode())),
    ]
    package.semantic_digest = semantic_digest(package, exclude={"execution"})
    manifest = package.model_copy(deep=True)
    clear_restricted(manifest)
    manifest.visibility = "sanitized"
    manifest.semantic_digest = semantic_digest(manifest, exclude={"execution"})
    run.write_text(PACKAGE_NAME, canonical_json(package))
    run.write_text(MANIFEST_NAME, canonical_json(manifest))

    console.ok(f"run {run_id}: {len(rows)} row(s), valid={valid}")
    console.line()
    console.line("READY_TO_SUBMIT" if valid else "NOT_VALID_DO_NOT_SUBMIT")
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return ExportResult(package=package, manifest=manifest, csv_text=csv_text, run_dir=run.seal())


@dataclass
class RecordRequest:
    package_run: Path
    output: Path
    match: str
    raw_response: str
    full_match_rank: int | None = None
    partial_match_rank: int | None = None
    rank_points: float | None = None
    f_max: float | None = None
    f_max_threshold: float | None = None
    n_predictions_at_f_max: int | None = None
    submission_number: int = 1
    argv: list[str] = field(default_factory=list)


def record_result(req: RecordRequest, console: Console | None = None) -> tuple[ExternalValidationResult, Path]:
    """Capture the evaluator's answer as case state. Nothing upstream is changed by it."""
    console = console or Console()
    package = _load(req.package_run / MANIFEST_NAME)
    match = req.match.upper()
    if match not in BRANCHES:
        raise Track1UsageError(f"match must be FULL, PARTIAL or NONE; got {req.match!r}")
    branch, action = BRANCHES[match]
    result = ExternalValidationResult(
        case_id=package["case_id"], submission_number=req.submission_number,
        submission_package_run_id=package["execution"]["run_id"],
        prediction_digest=package["provenance"]["prediction_digest"],
        snapshot_digest=package["provenance"]["snapshot_digest"],
        result=ScoredResult(match=match, full_match_rank=req.full_match_rank, partial_match_rank=req.partial_match_rank,
                            rank_points=req.rank_points, f_max=req.f_max, f_max_threshold=req.f_max_threshold,
                            n_predictions_at_f_max=req.n_predictions_at_f_max),
        raw_response=req.raw_response, received_at=utc_now().isoformat(), branch=branch, branch_action=action)
    result.semantic_digest = semantic_digest(result, exclude=set())
    run = RunDirectory(req.output, new_run_id(utc_now())).open()
    run.write_text(RESULT_NAME, canonical_json(result))
    console.ok(f"{match} recorded against submission {req.submission_number} ({result.prediction_digest[:19]}…)")
    console.line()
    console.line(f"BRANCH {branch}")
    console.line(action)
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return result, run.seal()
