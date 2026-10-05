"""The repair ledger for this case: what was believed, why it was withdrawn, and what replaced it.

Four repairs, all at the evidence layer. Nothing downstream was edited by hand; every verdict in
this repository was recomputed from the repaired evidence, and `recompile.py` reports the deltas.

The two repairs the audit forced are not symmetrical. One withdrew a refutation, which made the
result **weaker** — the route it refuted is now an assertion with no evidence either way. The other
connected a human trial that was already in the repository and attached to nothing, which moved a
compartment objection to a tissue objection. Neither was chosen to improve an answer.
"""
from __future__ import annotations

import json
from pathlib import Path

from rarepipe.stages.control.discovery.external.citation_audit import AttributionState
from rarepipe.stages.control.evidence_repair.records import (
    BaselineState, EvidenceRepair, RecoveryAttempt, RecoveryOutcome, RepairKind, RepairLedger,
)

LEDGER_VERSION = "mva-evidence-repair-v1"

# The baseline is recorded data, not source literals. It was observed by running the pipeline
# before the repair, and it lives in `data/evidence_repair/baseline.json` so that its digests can be
# cross-checked against the artifacts committed at that commit — which a test does. A digest written
# into source is a claim nothing verified; one read from a file that git can corroborate is not.
BASELINE_PATH = Path(__file__).resolve().parents[5] / "data/evidence_repair/baseline.json"


def _baseline() -> tuple[str, dict]:
    payload = json.loads(BASELINE_PATH.read_text())
    return payload["captured_at_commit"], payload["layers"]


_PROJECT_SEARCH = (
    "the plan seed (prospective/seed.py, hypothesis H04)",
    "the local mechanism corpus ids MC_0001 to MC_0013, which the project uses for curated "
    "artifacts instead of bare identifiers",
    "the simulator chain's own reference constants",
    "the commit that introduced the citation (stage10 prospective plans)",
    "the earlier PRD response that already flagged both seed citations as having no retrieval record",
)
_RECOVERY_QUERIES = (
    '("nicotinic acid" OR niacin) AND (BUBR1 OR BUB1B)',
    '("nicotinic acid" OR niacin) AND "spindle assembly checkpoint"',
    '("nicotinic acid" OR niacin) AND ("mitotic checkpoint" OR aneuploidy)',
    '"nicotinic acid" AND SIRT2',
    'niacin AND "chromosome missegregation"',
)


def ledger() -> RepairLedger:
    recovery_r1 = RecoveryAttempt(
        searched_in_project=_PROJECT_SEARCH, external_queries=_RECOVERY_QUERIES,
        outcome=RecoveryOutcome.NO_INTENDED_REFERENCE_FOUND,
        finding=("The local mechanism corpus holds nothing about this precursor — every entry is "
                 "about the protein and the disease — so no curated artifact was mis-transcribed "
                 "into a bare identifier. A targeted search returned work on oocytes, ovarian "
                 "ageing and reviews, and nothing reporting a null effect of this precursor on the "
                 "protein. No substitute was adopted."))
    none_needed = RecoveryAttempt(
        searched_in_project=("not applicable: this repair connects a reference the repository "
                             "already held",),
        outcome=RecoveryOutcome.NOT_ATTEMPTED,
        finding=("Nothing was missing to recover. The reference was present in the repository and "
                 "attached to no edge of the causal chain."))

    repairs = (
        EvidenceRepair(
            repair_id="REPAIR_R1", kind=RepairKind.RETIRE_ATTRIBUTION,
            edge_id="nicotinic_acid_exposure->bubr1_abundance",
            previous_claim_version="MVA_001_niacin_bubr1_v1 @ 4f9de0a",
            previous_source_assignment="PMID:42543917 (UNVERIFIED: no retrieval record)",
            previous_verdict="contradicted",
            previous_scope_note=("the closest related nicotinic-acid experiment was null and "
                                 "reported no measurement of the chain"),
            audit_verdict=AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION,
            reason_for_invalidation=(
                "The citation was retrieved and is a study of white adipocytes adapting to cooler "
                "temperatures. Its stored text contains neither 'niacin' nor 'nicotinic' nor any "
                "spelling of the protein, so it cannot report a null effect of one on the other."),
            new_version="MVA_001_niacin_bubr1_v1 @ repair-r1",
            new_source_assignment="", new_support_level="asserted_only",
            new_scope_note="no retrieved source addresses this relation in either direction",
            computed_not_chosen=(
                "The support level is what the chain's own validator permits once the citation is "
                "withdrawn: an edge with no evidence reference may only be asserted_only. It was "
                "not relabelled as supported, and it was not deleted — deleting it would have "
                "hidden a hypothesis the case still holds."),
            recovery=recovery_r1),
        EvidenceRepair(
            repair_id="REPAIR_R2", kind=RepairKind.CONNECT_EVIDENCE,
            edge_id="nicotinic_acid_exposure->nad_intracellular",
            previous_claim_version="MVA_001_niacin_bubr1_v1 @ 4f9de0a",
            previous_source_assignment="none; the reference was in the repository and cited by no edge",
            previous_verdict="not represented; the only route to the intracellular pool was the "
                             "blood-to-cell transfer, recorded as a different compartment",
            audit_verdict=None,
            reason_for_invalidation=(
                "The previous state was not wrong, it was incomplete: a human trial already held in "
                "the repository measured the tissue pool, which is the compartment the blood-only "
                "route cannot speak to, and it was connected to nothing."),
            new_version="MVA_001_niacin_bubr1_v1 @ repair-r2",
            new_source_assignment="PMID:32386566", new_support_level="human_experimental",
            new_scope_note=("muscle NAD of adult-onset mitochondrial myopathy patients reached the "
                            "level of matched controls; human skeletal muscle, not the cell type "
                            "this case requires"),
            computed_not_chosen=(
                "The edge is recorded at the context the source supports and no wider. The cell "
                "type remains a transfer gap rather than a resolved step, and the scope note and "
                "caveat travel with the verdict, so the human-supported reading cannot be detached "
                "from the tissue it was measured in."),
            recovery=none_needed),
        EvidenceRepair(
            repair_id="REPAIR_R3", kind=RepairKind.LIFT_STALE_LABEL,
            edge_id="nicotinic_acid_exposure->nad_whole_blood",
            previous_claim_version="MVA_001_niacin_bubr1_v1 @ 4f9de0a",
            previous_source_assignment="PMID:42628241 (UNVERIFIED: no retrieval record)",
            previous_verdict="human_experimental, capped by an unverified-citation label",
            audit_verdict=AttributionState.SUPPORTS_ATTRIBUTION,
            reason_for_invalidation=(
                "The label said the citation had no retrieval record. It has one now, and the "
                "retrieved text states the attributed effect in so many words, so the label itself "
                "had become stale and was capping a claim the document supports."),
            new_version="MVA_001_niacin_bubr1_v1 @ repair-r3",
            new_source_assignment="PMID:42628241", new_support_level="human_experimental",
            new_scope_note="whole-blood NAD in healthy adults",
            computed_not_chosen=(
                "Only the retrieval label changed. The support level, the compartment and the scope "
                "are what they were, so nothing downstream gains strength from this beyond no "
                "longer being discounted for a missing retrieval that has since happened."),
            recovery=none_needed),
        EvidenceRepair(
            repair_id="REPAIR_R4", kind=RepairKind.RETIRE_ATTRIBUTION,
            edge_id="cell_death->division_rate",
            previous_claim_version="MVA_001_niacin_bubr1_v1 @ 4f9de0a",
            previous_source_assignment="PMID:20516114",
            previous_verdict="model_experimental",
            previous_scope_note="population-level consequence",
            audit_verdict=AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION,
            reason_for_invalidation=(
                "Found by running the backward audit over every load-bearing citation rather than "
                "only the one that had already failed. The cited document's stored text mentions "
                "neither cell death nor division rate in any recorded spelling, so it does not "
                "address this relation. Re-checked against the full article (PMC2887387, 31654 "
                "characters), retrieved after this repair was first written because the open "
                "question was whether only the stored abstract was at fault: cell death, "
                "apoptosis, viability, proliferation, division rate, doubling, caspase, annexin "
                "and clonogenic survival occur zero times in it. The paper measures chromosome "
                "segregation, not cell loss, so no part of it can carry this relation."),
            new_version="MVA_001_niacin_bubr1_v1 @ repair-r4",
            new_source_assignment="", new_support_level="asserted_only",
            new_scope_note="population-level consequence; no retrieved source addresses it",
            computed_not_chosen=(
                "Retiring an unsupported label is the conservative action; keeping it would have "
                "been the aggressive one. The edge survives as an assertion rather than being "
                "deleted."),
            # The open question here was whether retrieving the full article would restore the
            # attribution. It has been retrieved and it does not, so the edge keeps the
            # conservative label as a model assumption and no decision is outstanding.
            recovery=none_needed),
    )
    commit, layers = _baseline()
    return RepairLedger(
        ledger_version=LEDGER_VERSION, repairs=repairs,
        baseline=BaselineState(captured_at_commit=commit, layers=layers),
        audit_summary=layers["grounded_claims"]["backward_audit"])
