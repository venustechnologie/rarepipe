"""Physical primitives: real pieces of the biological Lego, stored by what they can do.

The important information about a primitive is never "this is drug X". It is "this piece can make
this change, acting with this, in this place, and here is the claim it rests on". So a capability
cites **evidence edges from the repository's own inventory**, not a free-text reference it could
have invented, and it does not carry its own grade: the entitlement is computed from what the
repository already recorded about that claim.

A capability also declares what it needs and what it breaks. Those two fields are what let the
compiler notice that two primitives cannot be composed because one destroys a precondition of the
other — a conflict that is invisible if components are only lists of effects.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.evidence import EvidenceInventory
from rarepipe.stages.control.realization.kinds import Effect, PrimitiveClass

_PRIMITIVE_TYPES = {EpistemicType.BUILDING_BLOCK_CAPABILITY, EpistemicType.LITERATURE_EVIDENCE,
                    EpistemicType.INFERRED_HYPOTHESIS}


class Capability(Immutable):
    """One change this primitive can make, and the claim that entitles saying so."""

    capability_id: str = Field(min_length=1)
    claim: str = Field(min_length=10, description="What it does, mechanistically.")
    acts_on: str = Field(
        "", description="The node it acts through. Empty means the primitive is applied directly, "
                        "so this capability is an origin of the chain.")
    acts_by: Effect = Field(
        Effect.INCREASE,
        description="The direction in which it changes `acts_on`. With the cited claim's own sign "
                    "this fixes the expected effect, so a capability cannot claim an effect its "
                    "evidence does not imply.")
    affects: str = Field(min_length=1, description="The node or state variable it moves.")
    effect: Effect
    to: str | None = Field(
        None, description="The value it holds `affects` at. Required whenever `affects` is a "
                          "variable the safety region refers to, so a safety interaction cannot be "
                          "left implicit.")
    agent: str = Field("", description="What it acts with, where that is what makes the claim.")
    compartment: str = Field("", description="Where it acts, where that is what makes the claim.")
    evidence_edges: tuple[str, ...] = Field(
        (), description="Claims in the repository's inventory. Empty means nothing supports this "
                        "capability, which the checks report rather than tolerate.")
    requires: tuple[str, ...] = Field((), description="Nodes that must already hold.")
    destroys: tuple[str, ...] = Field(
        (), description="Preconditions this capability breaks, so conflicts are detectable.")

    @model_validator(mode="after")
    def _coherent(self):
        if self.affects == self.acts_on:
            raise ValueError(f"{self.capability_id}: a capability cannot act on what it affects")
        if self.effect is Effect.SET and self.to is None:
            raise ValueError(f"{self.capability_id}: SET must say what value it sets")
        return self


class PhysicalPrimitive(Immutable):
    primitive_id: str = Field(min_length=1)
    primitive_class: PrimitiveClass
    identity: str = Field(min_length=1, description="What it is, in words a scientist would use.")
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    required_context: str = Field(min_length=1)
    cell_type: str = Field(min_length=1)
    biological_scale: str = Field(min_length=1)
    reversibility: str = Field(min_length=1)
    temporal_properties: str = Field(
        min_length=1, description="What is known about timing. 'unknown' is an answer; a number "
                                  "nobody measured is not.")
    delivery_requirements: str = Field(min_length=1)
    known_dependencies: tuple[str, ...] = ()
    known_off_targets: tuple[str, ...] = ()
    known_safety_effects: tuple[str, ...] = ()
    evidence: str = Field(min_length=1, description="What stands behind it, with its limit.")
    validity_domain: str = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    feasibility_status: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type not in _PRIMITIVE_TYPES:
            raise ValueError(
                f"{self.primitive_id}: a physical primitive carries BUILDING_BLOCK_CAPABILITY, "
                "LITERATURE_EVIDENCE or INFERRED_HYPOTHESIS provenance")
        ids = [c.capability_id for c in self.capabilities]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.primitive_id}: capability ids must be unique")
        return self

    def capability(self, capability_id: str) -> Capability:
        for item in self.capabilities:
            if item.capability_id == capability_id:
                return item
        raise KeyError(f"{self.primitive_id} has no capability {capability_id!r}")


class UnknownPrimitive(ValueError):
    """A step names a primitive that is not in the registry."""


class PhysicalPrimitiveRegistry(Immutable):
    primitives: tuple[PhysicalPrimitive, ...] = ()

    @model_validator(mode="after")
    def _unique(self):
        ids = [p.primitive_id for p in self.primitives]
        if len(set(ids)) != len(ids):
            raise ValueError("primitive ids must be unique")
        return self

    def check(self, inventory: EvidenceInventory) -> None:
        """Every cited claim must exist in the inventory. This is where invention is caught."""
        for primitive in self.primitives:
            for capability in primitive.capabilities:
                for edge_id in capability.evidence_edges:
                    inventory.edge(edge_id)

    def get(self, primitive_id: str) -> PhysicalPrimitive:
        for primitive in self.primitives:
            if primitive.primitive_id == primitive_id:
                return primitive
        raise UnknownPrimitive(
            f"no physical primitive {primitive_id!r} in this registry; a component nobody declared "
            "cannot be part of a realization")

    def affecting(self, node: str) -> tuple[tuple[str, Capability], ...]:
        return tuple(sorted(((p.primitive_id, c) for p in self.primitives
                             for c in p.capabilities if c.affects == node),
                            key=lambda pair: (pair[0], pair[1].capability_id)))
