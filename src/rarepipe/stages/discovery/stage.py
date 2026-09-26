"""Stage 08 — assemble discovered interventions, their evidence, and what must not happen.

Candidates are built only from experiences that survived the import gate, approval is verified
against a regulator's own record, and direction decides the match. Nothing is ranked.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.digest import semantic_digest
from rarepipe.core.provenance import software_provenance
from rarepipe.core.redaction import clear_restricted
from rarepipe.stages.discovery import approval as approval_mod
from rarepipe.stages.discovery import ingest, report
from rarepipe.stages.discovery.model import (
    ApprovalRecord,
    CandidateState,
    Directness,
    Execution,
    InterventionDiscovery,
    Lane,
    MatchStatus,
    MechanismMatch,
    MechanisticReferenceCompound,
    MedicationCandidate,
    NodeQuerySpec,
    Outcome,
    Provenance,
    RejectedCandidate,
    RejectionReason,
    SearchRecord,
    Status,
)

PRIVATE = "intervention_discovery.private.json"
SANITIZED = "intervention_discovery.sanitized.json"
REPORT = "intervention_discovery.md"
LOG = "discovery.log"


class DiscoveryUsageError(ValueError):
    pass


@dataclass
class BuildRequest:
    intervention_map_run: Path
    research_dir: Path
    output: Path
    approval_cache: Path | None = None
    offline: bool = False
    argv: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    discovery: InterventionDiscovery
    sanitized: InterventionDiscovery
    run_dir: Path


def _load(path: Path) -> dict:
    if not path.exists():
        raise DiscoveryUsageError(f"not found: {path}")
    return json.loads(path.read_text())


def build(req: BuildRequest, console: Console | None = None) -> BuildResult:
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)

    console.step(1, 5, "Reading the frozen intervention map...")
    imap = _load(req.intervention_map_run / "intervention_map.private.json")
    if imap.get("status") != "INTERVENTION_LOGIC_READY_FOR_APPROVED_DRUG_SEARCH":
        raise DiscoveryUsageError(
            f"the intervention map is {imap.get('status')}: a drug search needs a specification to aim at")
    specs = {s["spec_id"]: s for s in imap["search_specs"]}
    forbidden = imap["forbidden_effects"]
    gene = imap["gene_symbol"]
    console.info(f"{len(specs)} search specification(s): {', '.join(specs)}; "
                 f"{len(forbidden)} forbidden direction(s)")

    console.step(2, 5, "Loading imported intervention experiences...")
    sessions, experiences, rejected_imports = ingest.load_all(req.research_dir)
    by_outcome = {o: [e for e in experiences if e.outcome is o] for o in Outcome}
    console.info(f"{len(experiences)} experience(s) from {len(sessions)} session(s): "
                 + ", ".join(f"{o.value} {len(v)}" for o, v in by_outcome.items() if v))
    if rejected_imports:
        console.warn(f"{len(rejected_imports)} proposed experience(s) were rejected on import")

    console.step(3, 5, "Verifying approval status...")
    ingredients = sorted({e.intervention_ingredient for e in experiences})
    approvals: dict[str, ApprovalRecord] = {}
    for ingredient in ingredients:
        if req.offline:
            approvals[ingredient] = ApprovalRecord(ingredient=ingredient, verified=False,
                                                   note="approval not verified: run was offline")
            continue
        record = approval_mod.verify(ingredient, cache_dir=req.approval_cache)
        approvals[ingredient] = record
        console.info(f"{ingredient[:38]:40} approved={str(record.verified).lower():5} "
                     f"{record.authority_source or 'no marketed US product found'}")

    console.step(4, 5, "Building candidates, rejections and reference compounds...")
    candidates, rejected, references = _assemble(experiences, approvals, specs, forbidden, gene, console)
    needs, node_specs = _gaps(experiences, candidates, gene)
    searches = _searches(req.research_dir)

    status, basis = _gate(candidates)
    discovery = InterventionDiscovery(
        visibility="private", case_id=imap["case_id"], gene_symbol=gene, status=status, status_basis=basis,
        candidates=candidates, experiences=experiences, reference_compounds=references, rejected=rejected,
        node_query_specs=node_specs, searches=searches, unresolved_evidence_needs=needs,
        provenance=Provenance(
            software=software_provenance(), intervention_map_run_id=imap["execution"]["run_id"],
            intervention_map_digest=imap.get("semantic_digest"), specifications_consumed=sorted(specs),
            research_sessions=[s.session_id for s in sessions],
            approval_sources=sorted({a.authority_source for a in approvals.values() if a.authority_source}),
            environment_controls=[
                "retrieval was gene-, mechanism-, disease- and drug-level; no case identity was transmitted",
                "approval verified against a regulator's own record, never because a source called it a drug",
                "no ranking, no dose, no treatment recommendation"]),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3),
                            intervention_map_path=str(req.intervention_map_run.resolve()), argv=req.argv))
    discovery.semantic_digest = semantic_digest(discovery, exclude={"execution"})
    sanitized = discovery.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = semantic_digest(sanitized, exclude={"execution"})

    console.step(5, 5, "Writing the discovery dossier...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(PRIVATE, canonical_json(discovery))
    run.write_text(SANITIZED, canonical_json(sanitized))
    run.write_text(REPORT, report.render(sanitized))
    console.ok(f"run {run_id}: {len(candidates)} candidate(s), {len(rejected)} rejected, "
               f"{len(references)} reference compound(s), {len(node_specs)} node query spec(s)")
    console.line()
    console.line(status.value)
    console.line(basis)
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return BuildResult(discovery=discovery, sanitized=sanitized, run_dir=run.seal())


def _assemble(experiences, approvals, specs, forbidden, gene, console):
    """One candidate per ingredient. Direction decides the match; approval decides survival."""
    candidates: list[MedicationCandidate] = []
    rejected: list[RejectedCandidate] = []
    references: list[MechanisticReferenceCompound] = []
    spec_id = next(iter(specs), "SPEC_001")
    spec = specs.get(spec_id, {})
    required = spec.get("desired_effect", "restore_toward_normal")

    for n, ingredient in enumerate(sorted({e.intervention_ingredient for e in experiences}), start=1):
        mine = [e for e in experiences if e.intervention_ingredient == ingredient]
        approval = approvals[ingredient]
        positive = [e.id for e in mine if e.outcome is Outcome.IMPROVED]
        negative = [e.id for e in mine if e.outcome is Outcome.NO_EFFECT]
        mixed = [e.id for e in mine if e.outcome is Outcome.MIXED]
        # Observed harm only. A lane-D find with no measured outcome is not harm, and an intervention
        # someone declined to give was never observed doing anything at all.
        harmful = [e.id for e in mine if e.outcome is Outcome.WORSENED]
        unknown = [e.id for e in mine if e.outcome is Outcome.UNKNOWN]

        if unknown and not (harmful or positive or negative or mixed):
            detail = ("flagged by the adversarial lane with no measured outcome: it was considered and withheld, "
                      "or discussed, but nobody observed what it did. Any mechanistic conflict is an inference, "
                      "not an observation")
            rejected.append(RejectedCandidate(
                intervention=ingredient, lane=mine[0].lane,
                discovered_because="found by the forbidden-direction lane",
                rejected_because=RejectionReason.OTHER, detail=detail, evidence=[e.id for e in mine]))
            candidates.append(MedicationCandidate(
                id=f"MED_{n:03d}", ingredient=ingredient, approval=approval, intervention_point="IP_001",
                specification=spec_id, required_direction=str(required),
                proposed_effect="none proposed",
                mechanism_match=MechanismMatch(
                    intervention=f"MED_{n:03d}", specification=spec_id, required_effect=str(required),
                    observed_or_reported_effect="no outcome was measured in the retrieved source",
                    direction="unknown", evidence_directness=_directness(mine),
                    establishing_evidence=[], related_evidence=[e.id for e in mine],
                    status=MatchStatus.NO_MATCH,
                    basis="no measured effect in either direction; this cannot match or contradict a specification"),
                experiences_unknown=[e.id for e in mine],
                independence_groups=sorted({e.independence_group for e in mine if e.independence_group}),
                state=CandidateState.INSUFFICIENT_EVIDENCE, adversarial_search_performed=True,
                adversarial_search_note="discovered by the adversarial lane itself",
                limitations=[detail] + [l for e in mine for l in e.limitations][:2]))
            console.info(f"MED_{n:03d} {ingredient[:32]:34} INSUFFICIENT_EVIDENCE (considered, never measured)")
            continue

        if harmful and not positive:
            conflict = ("reported to move the biology in a direction the mechanism forbids "
                        f"(weakening the checkpoint, or increasing missegregation in {gene}-relevant contexts)")
            rejected.append(RejectedCandidate(
                intervention=ingredient, lane=mine[0].lane,
                discovered_because="found by the forbidden-direction lane",
                rejected_because=RejectionReason.WRONG_DIRECTION, detail=conflict,
                evidence=[e.id for e in mine]))
            candidates.append(MedicationCandidate(
                id=f"MED_{n:03d}", ingredient=ingredient, approval=approval, intervention_point="IP_001",
                specification=spec_id, required_direction=str(required),
                proposed_effect="none proposed: this appears as a direction to avoid, not as a candidate",
                mechanism_match=MechanismMatch(
                    intervention=f"MED_{n:03d}", specification=spec_id, required_effect=str(required),
                    observed_or_reported_effect="weakens the checkpoint or increases missegregation",
                    direction="discordant", evidence_directness=_directness(mine),
                    establishing_evidence=[], related_evidence=[e.id for e in mine],
                    status=MatchStatus.NO_MATCH,
                    basis="direction is discordant with the specification, which disqualifies it regardless of "
                          "how well it engages the pathway"),
                experiences_harmful=harmful, experiences_unknown=unknown,
                forbidden_direction_conflict=conflict,
                independence_groups=sorted({e.independence_group for e in mine if e.independence_group}),
                state=CandidateState.CONTRADICTED,
                adversarial_search_performed=True,
                adversarial_search_note="discovered by the adversarial lane itself",
                limitations=([] if approval.verified else
                             ["approval is NOT verified for this name: it is a class, not an active ingredient. "
                              "Which specific approved members carry the reported effect is unasked."])
                            + [e.limitations[0] for e in mine if e.limitations][:2]))
            console.info(f"MED_{n:03d} {ingredient[:32]:34} CONTRADICTED (forbidden direction)")
            continue

        if not approval.verified:
            references.append(MechanisticReferenceCompound(
                id=f"REF_{n:03d}", ingredient=ingredient,
                what_it_showed="; ".join(e.intervention_intent or e.evidence_source.quote[:90] for e in mine)[:280],
                track2_eligible=False, proves_pharmacologic_modifiability=bool(positive or harmful),
                experiences=[e.id for e in mine]))
            rejected.append(RejectedCandidate(
                intervention=ingredient, lane=mine[0].lane,
                discovered_because="named in the retrieved experimental literature",
                rejected_because=RejectionReason.NOT_APPROVED,
                detail=approval.note, evidence=[e.id for e in mine]))
            console.info(f"REF_{n:03d} {ingredient[:32]:34} not approved → reference compound only")
            continue

        directness = _directness(mine)
        if positive and directness in (Directness.DIRECT_BUBR1, Directness.DEFICIENT_MODEL):
            status, state = MatchStatus.MATCH, CandidateState.MECHANISM_MATCH
        elif positive:
            status, state = MatchStatus.POSSIBLE, CandidateState.INSUFFICIENT_EVIDENCE
        else:
            status, state = MatchStatus.NO_MATCH, CandidateState.INSUFFICIENT_EVIDENCE
        candidates.append(MedicationCandidate(
            id=f"MED_{n:03d}", ingredient=ingredient, approval=approval, intervention_point="IP_001",
            specification=spec_id, required_direction=str(required),
            proposed_effect="; ".join(e.intervention_intent for e in mine if e.intervention_intent)[:200],
            mechanism_match=MechanismMatch(
                intervention=f"MED_{n:03d}", specification=spec_id, required_effect=str(required),
                observed_or_reported_effect="; ".join(e.evidence_source.quote[:80] for e in mine[:2]),
                direction="concordant" if positive else "unknown", evidence_directness=directness,
                establishing_evidence=positive, related_evidence=negative + mixed,
                status=status,
                basis=("direct evidence in the deficient biology" if directness is Directness.DEFICIENT_MODEL
                       else "evidence is not in the deficient biology; the bridge is not established")),
            experiences_positive=positive, experiences_negative=negative, experiences_mixed=mixed,
            independence_groups=sorted({e.independence_group for e in mine if e.independence_group}),
            state=state, limitations=[l for e in mine for l in e.limitations][:3]))
        console.info(f"MED_{n:03d} {ingredient[:32]:34} {state.value}")
    return candidates, rejected, references


def _directness(experiences) -> Directness:
    scores = {Directness.DIRECT_BUBR1: 0, Directness.DEFICIENT_MODEL: 1, Directness.RELATED_MODEL: 2,
              Directness.PATHWAY_ONLY: 3}
    best = Directness.PATHWAY_ONLY
    for e in experiences:
        text = f"{e.gene or ''} {e.model or ''} {e.mechanism or ''}".lower()
        if "bub1b" in text or "bubr1" in text:
            here = Directness.DEFICIENT_MODEL if ("deficien" in text or "mva" in text) else Directness.DIRECT_BUBR1
        elif e.disease and "aneuploid" in (e.disease or "").lower():
            here = Directness.RELATED_MODEL
        else:
            here = Directness.PATHWAY_ONLY
        if scores[here] < scores[best]:
            best = here
    return best


def _gaps(experiences, candidates, gene) -> tuple[list[str], list[NodeQuerySpec]]:
    """What we could not answer from public literature becomes a question for a future node."""
    needs = []
    specs = []
    if not any(c.state is CandidateState.MECHANISM_MATCH for c in candidates):
        needs.append(f"No approved intervention has evidence of restoring functional {gene}/BUBR1 or of improving a "
                     f"relevant endpoint in {gene}-deficient biology. Whether such an experience exists unpublished "
                     "is exactly what a clinical node could answer.")
        specs.append(NodeQuerySpec(
            id="NQS_001",
            question=(f"Has any approved medication been given to a patient with {gene}-associated mosaic variegated "
                      "aneuploidy, or a closely comparable chromosome-instability syndrome, with a recorded effect on "
                      "any cellular or clinical endpoint?"),
            desired_evidence=["intervention", "outcome", "endpoint", "timeframe"],
            useful_negative_result=True, patient_identity_required=False,
            arises_from="no mechanism-matching approved candidate found in public literature"))
    if not any(e.lane is Lane.B_DEFICIENT_RESCUE and e.outcome is Outcome.IMPROVED for e in experiences):
        needs.append("No pharmacological rescue of any endpoint in BUB1B-deficient cells was found. This is an "
                     "untested space, not a failed one: no experience was found either way.")
        specs.append(NodeQuerySpec(
            id="NQS_002",
            question=("Has any laboratory tested an approved medication against a mitotic-checkpoint or "
                      "aneuploidy endpoint in BUB1B-deficient or MVA patient-derived cells, with any outcome "
                      "including no effect?"),
            desired_evidence=["intervention", "endpoint", "outcome", "model"],
            useful_negative_result=True, patient_identity_required=False,
            arises_from="lane B returned no pharmacological rescue in the deficient biology"))
    needs.append("BUBR1 abundance is controlled in part by acetylation at K250, whose loss triggers degradation. "
                 "Whether any approved agent changes BUBR1 levels through that axis is unasked; it is a search "
                 "task, not a candidate.")
    return needs, specs


def _searches(research_dir: Path) -> list[SearchRecord]:
    records = []
    for path in sorted((research_dir / "tasks").glob("KT_*.json")):
        task = json.loads(path.read_text())
        reason = task.get("reason", "")
        if not reason.startswith("["):
            continue
        lane_value = reason.split("]")[0].lstrip("[")
        try:
            lane = Lane(lane_value)
        except ValueError:
            continue
        records.append(SearchRecord(lane=lane, knowledge_task=task["id"], queries=task.get("queries", []),
                                    documents=len(task.get("documents_found", [])),
                                    note=task.get("question", "")[:120]))
    return records


def _gate(candidates) -> tuple[Status, str]:
    matched = [c for c in candidates if c.state is CandidateState.MECHANISM_MATCH]
    possible = [c for c in candidates if c.state is CandidateState.INSUFFICIENT_EVIDENCE
                and c.mechanism_match and c.mechanism_match.status is MatchStatus.POSSIBLE]
    contradicted = [c for c in candidates if c.state is CandidateState.CONTRADICTED]
    if matched:
        return Status.CANDIDATES_FOUND, (
            f"{len(matched)} approved intervention(s) with verified approval and direction-concordant evidence in "
            "relevant biology. Stage 09 earns the comparison; nothing is ranked here.")
    if possible:
        return Status.LOW_CONFIDENCE_ONLY, (
            f"{len(possible)} approved intervention(s) with concordant but indirect evidence, and none demonstrated "
            "in the deficient biology. Stage 09 can still assess whether a Track 2 submission is defensible.")
    verified_contra = [c for c in contradicted if c.approval.verified]
    unverified_contra = [c for c in contradicted if not c.approval.verified]
    wrong_way = (f"{len(verified_contra)} approval-verified and {len(unverified_contra)} unverified "
                 f"intervention(s) were found moving the biology the wrong way"
                 if contradicted else "nothing was found moving the biology the wrong way either")
    return Status.NONE_FOUND, (
        "No approved intervention has direction-concordant evidence for the specification. " + wrong_way +
        ", which is a useful result for this child even though it is not a candidate. The absence of positive "
        "candidates is an absence of published evidence, not a demonstration that nothing works: lane B found no "
        "pharmacological attempt in this biology at all, in either direction.")
