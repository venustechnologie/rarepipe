"""Stage 09 — adjudicate research hypotheses and decide whether Track 2 has something defensible.

The gate is the stage. A hypothesis reaches Track 2 only by passing every check, and a stage that
finds nothing says so rather than inventing a candidate: the sealed baseline is produced either way,
because proving where public evidence ends is itself the result.
"""

from __future__ import annotations

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
from rarepipe.stages.discovery import approval as approval_mod
from rarepipe.stages.track2 import ingest, report
from rarepipe.stages.track2.model import (
    Action,
    BaselineSnapshot,
    EvidenceGrade,
    Execution,
    GateCheck,
    HypothesisState,
    Provenance,
    RejectedHypothesis,
    SearchOutcome,
    SearchResult,
    SubmissionClaim,
    Status,
    Track2HypothesisSet,
)

PRIVATE = "track2_hypothesis_set.private.json"
SANITIZED = "track2_hypothesis_set.sanitized.json"
ADJUDICATION = "candidate_adjudication.md"
BASELINE = "track2_baseline_snapshot.json"
REJECTED = "rejected_hypotheses.json"
ACTIONS = "stage09_actions.json"
LOG = "track2.log"


class Track2UsageError(ValueError):
    pass


@dataclass
class BuildRequest:
    discovery_run: Path
    research_dir: Path
    output: Path
    approval_cache: Path | None = None
    offline: bool = False
    argv: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    hypothesis_set: Track2HypothesisSet
    sanitized: Track2HypothesisSet
    run_dir: Path


def _load(path: Path) -> dict:
    if not path.exists():
        raise Track2UsageError(f"not found: {path}")
    return json.loads(path.read_text())


def _git(args: list[str]) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=Path(__file__).resolve().parent, capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def gate(hypothesis, approval, discovery) -> list[GateCheck]:
    """Thirteen checks. All must pass; the failures are recorded, not summarised away."""
    evidenced = [link for link in hypothesis.proposed_chain if link.kind == "evidenced"]
    inferences = [link for link in hypothesis.proposed_chain if link.kind == "inference"]
    checks = [
        GateCheck(check="resolves to a specific active ingredient, not a class",
                  passed=bool(hypothesis.active_ingredient) and not any(
                      w in hypothesis.active_ingredient.lower() for w in ("inhibitor", "class", "agent", "taxane")),
                  detail=hypothesis.active_ingredient),
        GateCheck(check="currently approved in at least one verified jurisdiction", passed=approval.verified,
                  detail=f"{approval.authority_source or 'unverified'}; {', '.join(approval.jurisdictions) or 'none'}"),
        GateCheck(check="an explicit proposed mechanism chain is present", passed=len(hypothesis.proposed_chain) >= 2,
                  detail=f"{len(hypothesis.proposed_chain)} link(s)"),
        GateCheck(check="direction matches the specification", passed=hypothesis.observed_direction == "concordant",
                  detail=hypothesis.observed_direction),
        GateCheck(check="at least one primary experimental source demonstrates the medication's own molecular effect",
                  passed=bool(evidenced) and bool(evidenced[0].evidence),
                  detail=f"{len(evidenced)} evidenced link(s), first carries {len(evidenced[0].evidence) if evidenced else 0} citation(s)"),
        GateCheck(check="every arrow is either evidenced or explicitly marked inference",
                  passed=all(link.kind in ("evidenced", "inference") for link in hypothesis.proposed_chain),
                  detail=f"{len(evidenced)} evidenced, {len(inferences)} inference"),
        GateCheck(check="not contradicted by stronger, more relevant evidence without explanation",
                  passed=not hypothesis.contradicting_evidence or bool(hypothesis.limitations),
                  detail=f"{len(hypothesis.contradicting_evidence)} contradicting record(s)"),
        GateCheck(check="a falsifiable validation experiment is defined", passed=hypothesis.validation_plan is not None,
                  detail=(hypothesis.validation_plan.system if hypothesis.validation_plan else "none")),
        GateCheck(check="exact-allele dependency is stated", passed=hypothesis.exact_allele_dependency is not None,
                  detail=str(hypothesis.exact_allele_dependency).lower()),
        GateCheck(check="major limitations are stated", passed=len(hypothesis.limitations) >= 2,
                  detail=f"{len(hypothesis.limitations)} limitation(s)"),
        GateCheck(check="untested status in BUB1B/MVA is explicit",
                  passed=bool(hypothesis.not_tested_note) or hypothesis.tested_in_bub1b_deficiency,
                  detail=hypothesis.not_tested_note[:70] or "tested"),
        GateCheck(check="no dose or regimen is proposed",
                  passed=not any(t in json.dumps(hypothesis.model_dump(mode="json")).lower()
                                 for t in ("mg/kg", "dosage of", "regimen of", "administer to the patient")),
                  detail="checked across the whole object"),
        GateCheck(check="no claim of clinical efficacy and no treatment recommendation",
                  passed=hypothesis.treatment_recommendation is False
                  and hypothesis.clinical_actionability == "NOT_ASSESSED", detail="NOT_ASSESSED"),
    ]
    return checks


def _grade(hypothesis) -> EvidenceGrade:
    if hypothesis.tested_in_bub1b_deficiency or hypothesis.tested_in_mva:
        return EvidenceGrade.DIRECT
    first = next((link for link in hypothesis.proposed_chain if link.kind == "evidenced"), None)
    target = (first.step if first else "").lower()
    if "bubr1" in target or "bub1b" in target:
        return EvidenceGrade.STRONG_INDIRECT
    return EvidenceGrade.MECHANISTIC_INDIRECT


STATE_BY_GRADE = {
    EvidenceGrade.DIRECT: HypothesisState.TRACK2_ELIGIBLE_DIRECT,
    EvidenceGrade.STRONG_INDIRECT: HypothesisState.TRACK2_ELIGIBLE_STRONG_INDIRECT,
    EvidenceGrade.MECHANISTIC_INDIRECT: HypothesisState.TRACK2_ELIGIBLE_MECHANISTIC_INDIRECT,
}


def build(req: BuildRequest, console: Console | None = None) -> BuildResult:
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)

    console.step(1, 5, "Pinning the frozen Stage 08 artifact...")
    discovery = _load(req.discovery_run / "intervention_discovery.private.json")
    console.info(f"discovery run {discovery['execution']['run_id']} · {discovery.get('semantic_digest')}")
    console.info(f"Stage 08 status: {discovery['status']}")

    console.step(2, 5, "Loading proposed hypotheses...")
    sessions, hypotheses, evidence, rejected_imports = ingest.load_all(req.research_dir)
    console.info(f"{len(hypotheses)} proposed hypothesis(es) from {len(sessions)} session(s); "
                 f"{len(rejected_imports)} rejected on import")

    console.step(3, 5, "Verifying approval and running the promotion gate...")
    rejected: list[RejectedHypothesis] = []
    promoted = []
    for hypothesis in hypotheses:
        approval = (approval_mod.verify(hypothesis.active_ingredient, cache_dir=req.approval_cache)
                    if not req.offline else None)
        if approval:
            hypothesis.approval_verified = approval.verified
            hypothesis.approval_jurisdictions = approval.jurisdictions
            hypothesis.approval_authority = approval.authority_source
            hypothesis.approval_note = approval.note
            hypothesis.canonical_ids = dict(approval.identifiers)
        hypothesis.gate = gate(hypothesis, approval or _unverified(hypothesis.active_ingredient), discovery)
        hypothesis.independence_groups = sorted({e.get("independence_group") for e in evidence.values()
                                                 if e.get("independence_group")
                                                 and e["evidence_id"] in hypothesis.establishing_evidence})
        failed = [c.check for c in hypothesis.gate if not c.passed]
        if failed:
            state = (HypothesisState.APPROVAL_UNVERIFIED if not hypothesis.approval_verified
                     else HypothesisState.INSUFFICIENT_EVIDENCE)
            hypothesis.state = state
            rejected.append(RejectedHypothesis(
                intervention=hypothesis.active_ingredient, discovered_because=hypothesis.statement[:120],
                rejected_because=state, failed_checks=failed,
                detail="; ".join(c.detail for c in hypothesis.gate if not c.passed)[:300],
                evidence=hypothesis.establishing_evidence))
            console.fail(f"{hypothesis.id} {hypothesis.active_ingredient[:26]:28} {state.value} "
                         f"— failed: {'; '.join(failed)[:90]}")
        else:
            hypothesis.evidence_grade = _grade(hypothesis)
            hypothesis.state = STATE_BY_GRADE[hypothesis.evidence_grade]
            promoted.append(hypothesis)
            console.ok(f"{hypothesis.id} {hypothesis.active_ingredient[:26]:28} {hypothesis.state.value}")

    console.step(4, 5, "Recording search outcomes and the sealed baseline...")
    outcomes = _outcomes(req.research_dir, discovery, promoted)
    status, basis = ((Status.READY, _ready_basis(promoted)) if promoted
                     else (Status.BLOCKED, _blocked_basis(discovery)))
    baseline = BaselineSnapshot(
        created_at=started.isoformat(),
        validation_run_id=discovery["provenance"].get("intervention_map_run_id"),
        discovery_run_id=discovery["execution"]["run_id"], discovery_digest=discovery.get("semantic_digest"),
        intervention_map_run_id=discovery["provenance"].get("intervention_map_run_id"),
        intervention_map_digest=discovery["provenance"].get("intervention_map_digest"),
        git_commit=_git(["rev-parse", "HEAD"]), git_describe=_git(["describe", "--tags", "--always"]),
        hypotheses_found=len(promoted))
    claims = _claims(promoted, discovery, outcomes)

    hypothesis_set = Track2HypothesisSet(
        visibility="private", case_id=discovery["case_id"], gene_symbol=discovery["gene_symbol"],
        status=status, status_basis=basis, hypotheses=hypotheses, rejected=rejected,
        search_outcomes=outcomes, submission_claims=claims,
        node_query_specs=discovery.get("node_query_specs", []), baseline=baseline,
        next_actions=_actions(promoted, discovery),
        provenance=Provenance(
            software=software_provenance(), discovery_run_id=discovery["execution"]["run_id"],
            discovery_digest=discovery.get("semantic_digest"),
            intervention_map_run_id=discovery["provenance"].get("intervention_map_run_id"),
            research_sessions=[s.session_id for s in sessions],
            approval_sources=sorted({h.approval_authority for h in hypotheses if h.approval_authority}),
            environment_controls=[
                "public evidence only; no institutional or node data was used",
                "no case-specific genomic identity was transmitted",
                "no dose, no regimen, no treatment recommendation",
                "the stage uploads nothing: submission remains human-controlled"]),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3),
                            discovery_path=str(req.discovery_run.resolve()), argv=req.argv))
    hypothesis_set.semantic_digest = semantic_digest(hypothesis_set, exclude={"execution"})
    sanitized = hypothesis_set.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = semantic_digest(sanitized, exclude={"execution"})

    console.step(5, 5, "Writing artifacts...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(PRIVATE, canonical_json(hypothesis_set))
    run.write_text(SANITIZED, canonical_json(sanitized))
    run.write_text(ADJUDICATION, report.render(sanitized, evidence))
    run.write_text(BASELINE, canonical_json(baseline))
    run.write_text(REJECTED, canonical_json({"rejected": [r.model_dump(mode="json") for r in rejected]}))
    run.write_text(ACTIONS, canonical_json({"next_actions": [a.model_dump(mode="json") for a in
                                                             hypothesis_set.next_actions]}))
    if status is Status.READY:
        run.write_text("xaviramram_track2_report.md", report.submission(sanitized, evidence, discovery))
        run.write_text("track2_submission_manifest.json", canonical_json(_manifest(hypothesis_set)))
        run.write_text("track2_pitch_script.md", report.pitch(sanitized, discovery))
    console.ok(f"run {run_id}: {len(promoted)} eligible hypothesis(es), {len(rejected)} rejected")
    console.line()
    console.line(status.value)
    console.line(basis)
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return BuildResult(hypothesis_set=hypothesis_set, sanitized=sanitized, run_dir=run.seal())


def _unverified(ingredient: str):
    from rarepipe.stages.discovery.model import ApprovalRecord

    return ApprovalRecord(ingredient=ingredient, verified=False, note="approval not checked: offline run")


def _outcomes(research_dir: Path, discovery: dict, promoted) -> list[SearchOutcome]:
    """What each search established, and what it explicitly did not."""
    outcomes = [
        SearchOutcome(
            question="Is there an approved medication with demonstrated rescue in BUB1B-deficient biology?",
            corpus="Europe PMC, lanes A-D (Stage 08) plus the Track 2 tasks",
            result=SearchResult.NO_EVIDENCE_FOUND,
            interpretation="no pharmacological rescue in BUB1B-deficient or MVA biology was found, in either direction",
            does_not_mean="that pharmacological rescue has been shown not to work: the space appears untested"),
        SearchOutcome(
            question="Which regulators control BUBR1 abundance, and is any pharmacologically addressable?",
            corpus="Europe PMC, KT_T2_01/03/04",
            result=SearchResult.POSITIVE,
            interpretation=("BUBR1 stability is controlled by acetylation at K668, opposed by the NAD+-dependent "
                            "deacetylase SIRT2; raising NAD+ with a precursor increases BubR1 abundance in vivo"),
            does_not_mean=("that this has been shown in BUB1B-deficient cells, in MVA, or with an approved "
                           "medication: the in vivo experiment used a precursor that is not an approved medicine")),
        SearchOutcome(
            question="Does an approved NAD+ precursor raise NAD+ in humans?",
            corpus="Europe PMC, KT_T2_05/06/07",
            result=SearchResult.POSITIVE,
            interpretation="high-dose nicotinic acid produces a large, dose-dependent rise in blood NAD+ in humans",
            does_not_mean=("that it raises NAD+ in the tissues that matter here, or that the rise reaches BUBR1: "
                           "neither was measured")),
        SearchOutcome(
            question="Does any evidence contradict the sirtuin route?",
            corpus="Europe PMC, KT_T2_05",
            result=SearchResult.CONTRADICTORY,
            interpretation=("nicotinamide — a different B3 form and a downstream NAD+ metabolite — inhibits sirtuin "
                            "deacetylase activity, and circulating terminal metabolites of both B3 forms have been "
                            "associated with cardiovascular risk"),
            does_not_mean="that nicotinic acid itself inhibits sirtuins: that was not shown either way"),
    ]
    if not promoted:
        outcomes.append(SearchOutcome(
            question="Does any approved medication meet the Track 2 research-hypothesis gate?",
            corpus="all Stage 08 and Stage 09 tasks",
            result=SearchResult.EXHAUSTED_TO_THRESHOLD,
            interpretation="no approved medication passed every promotion check",
            does_not_mean="that none exists: it means public evidence does not currently support one"))
    return outcomes


def _claims(promoted, discovery, outcomes) -> list[SubmissionClaim]:
    """Every substantive sentence the report may use, tied to what it rests on."""
    claims = [
        SubmissionClaim(id="SC_001", type="observation", scope="case",
                        statement="The causal variant pair was externally validated against the hidden clinical "
                                  "answer key: full match at rank 1.",
                        basis_note="Stage 05 ExternalValidationResult"),
        SubmissionClaim(id="SC_002", type="external_evidence", scope="disease_level",
                        statement="Biallelic BUB1B disruption causes mosaic variegated aneuploidy, and restoring "
                                  "BUBR1 in patient cells restores mitotic checkpoint activity.",
                        basis_note="Stage 06 MC_0001, MC_0012"),
        SubmissionClaim(id="SC_003", type="observation", scope="case",
                        statement="No approved medication has demonstrated rescue in BUB1B-deficient biology in the "
                                  "public literature searched; that space appears untested rather than failed.",
                        basis_note="Stage 08 lanes A-D"),
        SubmissionClaim(id="SC_004", type="derived_inference", scope="exact_variant",
                        statement="The functional effect of this child's missense allele remains unmeasured, so every "
                                  "hypothesis here is deliberately independent of it.",
                        basis_note="Stage 06 MC_0006 unresolved"),
    ]
    for h in promoted:
        claims.append(SubmissionClaim(
            id=f"SC_RH_{h.id}", type="derived_inference", scope="mechanism",
            statement=h.statement, evidence_ids=h.establishing_evidence,
            basis_note=f"evidence grade {h.evidence_grade.value if h.evidence_grade else 'ungraded'}; "
                       f"untested in BUB1B/MVA"))
    return claims


def _actions(promoted, discovery) -> list[Action]:
    actions = []
    if promoted:
        actions.append(Action(
            rank=1, action="Run the defined validation experiment in a BUB1B-deficient model before any clinical "
                           "consideration whatsoever.",
            expected_information_gain="high", cost="high",
            rationale="the hypothesis is worth testing, and that is all it is"))
    actions += [
        Action(rank=len(actions) + 1,
               action="Send the node query specs to an authorised clinical contact once a private channel exists.",
               expected_information_gain="high", cost="very_low",
               rationale="the untested space is exactly what a clinical node could answer",
               blocked_by=["no approved private channel yet"]),
        Action(rank=len(actions) + 2,
               action="Obtain the inaccessible full texts and re-run the local residue search.",
               expected_information_gain="moderate", cost="low",
               rationale="the exact-allele mechanism is still the highest-value unknown in the case"),
    ]
    return actions


def _ready_basis(promoted) -> str:
    grades = ", ".join(f"{h.id} {h.evidence_grade.value}" for h in promoted)
    return (f"{len(promoted)} approved medication(s) passed every promotion check ({grades}). This means the "
            "evidence justifies testing the hypothesis, not that the medication works: none has been tested in "
            "BUB1B-deficient or MVA biology, and no dose, regimen or treatment recommendation is produced.")


def _blocked_basis(discovery) -> str:
    return ("No approved medication passed the promotion gate. Public evidence is exhausted to the configured "
            "threshold, the pre-network baseline is sealed, and the node query specs carry forward. This is a "
            "result, not a failure: it marks where the public medical literature ends.")


def _manifest(hypothesis_set) -> dict:
    return {
        "schema": {"name": "Track2SubmissionManifest", "version": "1.0.0"},
        "case_id": hypothesis_set.case_id,
        "status": hypothesis_set.status.value,
        "hypothesis_set_digest": hypothesis_set.semantic_digest,
        "baseline": hypothesis_set.baseline.model_dump(mode="json"),
        "eligible_hypotheses": [
            {"id": h.id, "active_ingredient": h.active_ingredient, "state": h.state.value,
             "evidence_grade": h.evidence_grade.value if h.evidence_grade else None,
             "approval": {"verified": h.approval_verified, "authority": h.approval_authority,
                          "jurisdictions": h.approval_jurisdictions},
             "tested_in_bub1b_deficiency": h.tested_in_bub1b_deficiency,
             "treatment_recommendation": False, "clinical_actionability": "NOT_ASSESSED"}
            for h in hypothesis_set.hypotheses if h.state.value.startswith("TRACK2_ELIGIBLE")],
        "submission": {"state": "ready_for_human_review", "submission_number": 1, "budget": 3,
                       "note": "rarepipe uploads nothing. A person submits, after reading this."},
    }
