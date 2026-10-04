"""A grounded capability, and the fact that only one function may build one.

`CapabilityCandidate -> GroundedCapability` is a transition the deterministic validators perform
and nobody else. Three things enforce that:

* the object requires `GROUNDED_CAPABILITY` provenance;
* the proposals gate refuses to assign that type to any proposal, from any proposer;
* `build` is the only function that constructs one, and it refuses unless every validator passed.

The capability also records what it is *not* entitled to. `support_level`, `validity_domain`,
`known_caveats` and `forbidden_dependencies_satisfied` travel with it, so a later consumer cannot
read it as a stronger claim than the one that was established.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.discovery.gaps import RequiredContext
from rarepipe.stages.control.discovery.kinds import (
    CapabilityEntitlement, VerificationLevel,
)
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.kinds import Effect
from rarepipe.stages.simulate.chain import Support


class NotEntitled(ValueError):
    """An attempt to build a capability from a candidate that did not pass the validators."""


class GroundedCapability(Immutable):
    capability_id: str = Field(min_length=1)
    gap_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    physical_primitive: str = Field(min_length=1)
    input: str = Field(min_length=1)
    output: str = Field(min_length=1)
    output_value: str = Field(
        "", description="For a categorical output, the value the capability holds it at. Required "
                        "when the direction is SET, so a capability cannot be composed without "
                        "saying what it sets.")
    direction: Effect
    mechanism: str = Field(min_length=20)
    context: RequiredContext
    cell_type: str = Field(min_length=1)
    scale: str = Field(min_length=1)
    evidence_claims: tuple[str, ...] = Field(min_length=1)
    references: tuple[str, ...] = ()
    support_level: Support
    entitlement: CapabilityEntitlement
    verification: tuple[VerificationLevel, ...] = Field(min_length=1)
    validity_domain: str = Field(min_length=1)
    known_caveats: tuple[str, ...] = ()
    known_confounders: tuple[str, ...] = ()
    known_off_targets: tuple[str, ...] = ()
    forbidden_dependencies_satisfied: tuple[str, ...] = Field(
        (), description="The dependencies the gap forbade, which the ancestry check confirmed are "
                        "absent upstream of the output under this mechanism.")
    causal_depth: int = Field(
        ge=1, description="Steps from the actuator to the output. Not a quality score: a deeper "
                          "chain has more dependencies that each need their own grounding.")
    provenance: Provenance

    @model_validator(mode="after")
    def _only_the_builder_makes_these(self):
        if self.direction is Effect.SET and not self.output_value:
            raise ValueError(f"{self.capability_id}: a SET capability must say what value it sets")
        if self.provenance.epistemic_type is not EpistemicType.GROUNDED_CAPABILITY:
            raise ValueError(
                f"{self.capability_id}: a grounded capability carries GROUNDED_CAPABILITY "
                "provenance, which the proposals gate refuses to assign — so no proposer can "
                "construct one")
        if self.entitlement not in {CapabilityEntitlement.GROUNDED,
                                    CapabilityEntitlement.CONDITIONAL}:
            raise ValueError(
                f"{self.capability_id}: a capability cannot be built at entitlement "
                f"{self.entitlement.value}")
        if (self.entitlement is CapabilityEntitlement.GROUNDED
                and VerificationLevel.CAPABILITY_ENTITLED_FOR_CONTEXT not in self.verification):
            raise ValueError(
                f"{self.capability_id}: GROUNDED requires entitlement for the required context; a "
                "source that is verified and says the right thing is still not that")
        return self


class CapabilityRegistry(Immutable):
    capabilities: tuple[GroundedCapability, ...] = ()

    @model_validator(mode="after")
    def _unique(self):
        ids = [c.capability_id for c in self.capabilities]
        if len(set(ids)) != len(ids):
            raise ValueError("capability ids must be unique")
        return self

    def for_output(self, output: str) -> tuple[GroundedCapability, ...]:
        return tuple(c for c in self.capabilities if c.output == output)

    def with_added(self, new: tuple[GroundedCapability, ...]) -> "CapabilityRegistry":
        known = {c.capability_id for c in self.capabilities}
        return CapabilityRegistry(capabilities=tuple(sorted(
            [*self.capabilities, *(c for c in new if c.capability_id not in known)],
            key=lambda c: c.capability_id)))
