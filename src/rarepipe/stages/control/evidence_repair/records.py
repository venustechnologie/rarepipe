"""Versioned evidence repairs. The old state is kept, not overwritten.

A repair answers one question afterwards: *why did this edge used to be contradicted and now is not?*
So each one records the previous claim version, the previous source assignment, the previous verdict,
the reason for invalidation and the new version — and the new state is whatever the code computes
after the attribution is withdrawn, never a substitute chosen because it looks right.

`RecoveryAttempt` records the search for an intended reference before anything is retired. Two
outcomes are legitimate and both are recorded: the intended reference is found and goes through the
normal retrieval and grounding pipeline, or it is not found and the claim is left without evidence.
Inventing a replacement is neither.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from rarepipe.stages.control.discovery.external.citation_audit import AttributionState
from rarepipe.stages.control.provenance import Immutable


class RepairKind(StrEnum):
    RETIRE_ATTRIBUTION = "RETIRE_ATTRIBUTION"
    CONNECT_EVIDENCE = "CONNECT_EVIDENCE"
    LIFT_STALE_LABEL = "LIFT_STALE_LABEL"


class RecoveryOutcome(StrEnum):
    INTENDED_REFERENCE_RECOVERED = "INTENDED_REFERENCE_RECOVERED"
    NO_INTENDED_REFERENCE_FOUND = "NO_INTENDED_REFERENCE_FOUND"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class RecoveryAttempt(Immutable):
    """What was done to find the reference that was meant, before retiring the one that was used."""

    searched_in_project: tuple[str, ...] = Field(
        min_length=1, description="Places inside the project that were inspected for the intended "
                                  "reference: seeds, manifests, local artifact ids, commits.")
    external_queries: tuple[str, ...] = ()
    outcome: RecoveryOutcome
    recovered_reference: str = ""
    finding: str = Field(min_length=20)

    @model_validator(mode="after")
    def _coherent(self):
        if self.outcome is RecoveryOutcome.INTENDED_REFERENCE_RECOVERED and not self.recovered_reference:
            raise ValueError("a recovered reference must be named")
        if self.outcome is RecoveryOutcome.NO_INTENDED_REFERENCE_FOUND and self.recovered_reference:
            raise ValueError("nothing was recovered, so nothing may be named")
        return self


class EvidenceRepair(Immutable):
    repair_id: str = Field(min_length=1)
    kind: RepairKind
    edge_id: str = Field(min_length=1)

    previous_claim_version: str = Field(min_length=1)
    previous_source_assignment: str
    previous_verdict: str = Field(min_length=1)
    previous_scope_note: str = ""
    audit_verdict: AttributionState | None = None
    reason_for_invalidation: str = Field(min_length=20)

    new_version: str = Field(min_length=1)
    new_source_assignment: str = ""
    new_support_level: str = Field(min_length=1)
    new_scope_note: str = ""
    computed_not_chosen: str = Field(
        min_length=20,
        description="Why the new state is what the code computes rather than a substitute picked "
                    "because it looked right.")
    recovery: RecoveryAttempt
    needs_human_decision: str = Field(
        "", description="Set where retiring a label is the conservative move and a scientist may "
                        "want a different remedy, such as retrieving the full article.")


class BaselineState(Immutable):
    """The downstream state before the repair, recorded from the committed artifacts.

    Captured by running the pipeline at the commit named below, because once the evidence is repaired
    the previous verdicts can no longer be recomputed. A test asserts the recorded values match the
    committed reports at that commit.
    """

    captured_at_commit: str = Field(min_length=7)
    layers: dict = Field(min_length=1)


class RepairLedger(Immutable):
    ledger_version: str = Field(min_length=1)
    repairs: tuple[EvidenceRepair, ...] = Field(min_length=1)
    baseline: BaselineState
    audit_summary: dict = Field(
        default_factory=dict,
        description="Counts per attribution state from the backward audit that prompted the repairs.")

    def by_edge(self, edge_id: str) -> tuple[EvidenceRepair, ...]:
        return tuple(r for r in self.repairs if r.edge_id == edge_id)
