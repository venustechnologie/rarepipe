"""What an agent may produce: a mechanism hypothesis, or a candidate. Never a capability.

A candidate is a proposal that *claims* a capability. It carries what the proposer asserts — the
entity, the input, the output, the direction, the context — separately from what any source says, so
the validators can compare the two. That separation is the whole mechanism: a candidate cannot
present a sentence and then use the same sentence to certify itself.

`CapabilityCandidate.status` starts and stays `PROPOSED`. Nothing in this module can advance it.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.discovery.gaps import RequiredContext
from rarepipe.stages.control.discovery.kinds import CandidateStatus
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.kinds import Effect

_CANDIDATE_TYPES = {EpistemicType.INFERRED_HYPOTHESIS, EpistemicType.MECHANISM_HYPOTHESIS,
                    EpistemicType.BUILDING_BLOCK_CAPABILITY, EpistemicType.LITERATURE_EVIDENCE}


class MechanismHypothesis(Immutable):
    """"What kinds of mechanism could do this?" — a class of answer, not an entity."""

    hypothesis_id: str = Field(min_length=1)
    gap_id: str = Field(min_length=1)
    mechanism_class: str = Field(min_length=3)
    statement: str = Field(min_length=20)
    avoids: tuple[str, ...] = Field(
        (), description="Forbidden dependencies this hypothesis claims not to route through. The "
                        "claim is checked against the ancestry graph, not believed.")
    rationale: str = Field(min_length=10)
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type is not EpistemicType.MECHANISM_HYPOTHESIS:
            raise ValueError(f"{self.hypothesis_id}: a mechanism hypothesis carries "
                             "MECHANISM_HYPOTHESIS provenance and nothing stronger")
        return self


class CapabilityCandidate(Immutable):
    candidate_id: str = Field(min_length=1)
    gap_id: str = Field(min_length=1)
    proposed_mechanism: str = Field(min_length=20)
    proposed_entity_or_process: str = Field(min_length=1)
    required_inputs: tuple[str, ...] = ()
    claimed_output: str = Field(min_length=1)
    claimed_direction: Effect
    claimed_value: str = ""
    context: RequiredContext
    biological_scale: str = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    possible_confounders: tuple[str, ...] = ()
    possible_safety_effects: tuple[str, ...] = ()
    supporting_evidence_refs: tuple[str, ...] = Field(
        (), description="Source ids returned by a provider. Not free text, and not a citation the "
                        "proposer typed: an id that must resolve to a hit.")
    from_hypothesis: str = ""
    status: CandidateStatus = CandidateStatus.PROPOSED
    provenance: Provenance

    @model_validator(mode="after")
    def _a_candidate_is_only_ever_proposed(self):
        if self.status is not CandidateStatus.PROPOSED:
            raise ValueError(
                f"{self.candidate_id}: a candidate is constructed as PROPOSED. Only the "
                "deterministic validators decide anything else, and they build a separate object")
        if self.provenance.epistemic_type not in _CANDIDATE_TYPES:
            raise ValueError(f"{self.candidate_id}: a candidate may not carry "
                             f"{self.provenance.epistemic_type.value} provenance")
        if self.claimed_output in self.required_inputs:
            raise ValueError(f"{self.candidate_id}: output cannot be one of its own inputs")
        return self
