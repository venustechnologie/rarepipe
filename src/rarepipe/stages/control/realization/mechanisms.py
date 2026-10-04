"""A mechanistic realization: one candidate physical way to implement an abstract transformation.

The decomposition this layer exists to enforce is:

    required function  ->  mechanism  ->  biological operation  ->  physical piece

Skipping to the last step is what makes a drug name feel like an answer, so a realization is a
sequence of steps, each of which names the primitive it uses and the capability of that primitive it
relies on. The causal content lives in the capability, which is where the evidence is, so a step
cannot assert a different effect than the claim it rests on.

A transformation with no direct realization is not a dead end: it may declare the sub-transformations
it reduces to, and each of those is compiled in turn. That is how `restore chromosome alignment`
becomes two smaller problems rather than one unanswerable one.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.kinds import Effect

_REALIZATION_TYPES = {EpistemicType.PROPOSED_ARCHITECTURE, EpistemicType.INFERRED_HYPOTHESIS,
                      EpistemicType.BUILDING_BLOCK_CAPABILITY}


class Step(Immutable):
    step_id: str = Field(min_length=1)
    uses_primitive: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    rationale: str = Field(min_length=10)


class MechanisticRealization(Immutable):
    realization_id: str = Field(min_length=1)
    required_transformation: str = Field(min_length=1)
    target_variable: str = Field(min_length=1)
    target_value: str = Field(min_length=1)
    required_effect: Effect
    mechanism: str = Field(min_length=20, description="The physical story, not the outcome.")
    steps: tuple[Step, ...] = ()
    agent: str = Field(
        "", description="What this realization actually administers. The chain's `different_agent` "
                        "label is about the intervention, so the substitution is checked against "
                        "this and not against whatever a capability happens to declare — otherwise "
                        "a chain giving one compound would inherit the evidence of another.")
    context_system: str = Field(
        min_length=1, description="The system this realization has to work in — the case's, not "
                                  "whatever the cited experiments happened to use.")
    decomposes_into: tuple[str, ...] = Field(
        (), description="Sub-transformations this one reduces to when no direct chain exists. Each "
                        "is compiled in turn.")
    unknown_steps: tuple[str, ...] = Field(
        (), description="Steps the proposer knows are missing. Declared, not discovered.")
    safety_dependencies: tuple[str, ...] = ()
    confound_observables: tuple[str, ...] = Field(
        (), description="What must be measured for this realization's readout to mean anything.")
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type not in _REALIZATION_TYPES:
            raise ValueError(f"{self.realization_id}: a realization carries PROPOSED_ARCHITECTURE, "
                             "INFERRED_HYPOTHESIS or BUILDING_BLOCK_CAPABILITY provenance")
        if not self.steps and not self.decomposes_into:
            raise ValueError(
                f"{self.realization_id}: a realization with neither steps nor a decomposition "
                "claims a mechanism and supplies none")
        ids = [s.step_id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.realization_id}: step ids must be unique")
        return self

    @property
    def primitives(self) -> tuple[str, ...]:
        return tuple(sorted({s.uses_primitive for s in self.steps}))
