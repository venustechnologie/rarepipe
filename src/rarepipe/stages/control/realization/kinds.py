"""The closed vocabularies of the physical-realization layer.

No numbers. There is no probability of success, no efficacy score and no model-generated
confidence anywhere in this layer, because none of them would be derived from a justifiable
distribution. Everything a realization can be is one of the words below.
"""
from __future__ import annotations

from enum import StrEnum


class RealizationResult(StrEnum):
    """How far a required transformation got towards a physical implementation.

    Only the first is a chain of real components with sufficient evidence, and even that is a
    candidate: it is not a demonstrated treatment and does not become one by being reported.
    """

    GROUNDED_REALIZATION_CANDIDATE = "GROUNDED_REALIZATION_CANDIDATE"
    PARTIAL_REALIZATION = "PARTIAL_REALIZATION"
    NO_GROUNDED_REALIZATION = "NO_GROUNDED_REALIZATION"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    UNSAFE_REALIZATION = "UNSAFE_REALIZATION"
    NOT_REPRESENTABLE = "NOT_REPRESENTABLE"


REALIZATION_MEANING: dict[RealizationResult, str] = {
    RealizationResult.GROUNDED_REALIZATION_CANDIDATE:
        "every required transformation has a chain of real components whose evidence entitles the "
        "claim at the burden this bypass carries — a candidate for discussion, not a demonstrated "
        "treatment",
    RealizationResult.PARTIAL_REALIZATION:
        "some required transformations are grounded and at least one is not; the missing piece is "
        "named exactly, which reduces the open problem to it",
    RealizationResult.NO_GROUNDED_REALIZATION:
        "no evidence-backed way to implement the required transformations was found in this "
        "registry and this evidence inventory — a statement about what we hold, not about biology",
    RealizationResult.CONTEXT_MISMATCH:
        "a mechanism exists, but the evidence for it was obtained with a different agent or in a "
        "different compartment or system than the one required",
    RealizationResult.EVIDENCE_INSUFFICIENT:
        "a plausible proposal exists, but the evidence does not entitle turning it into a "
        "transformation of the model",
    RealizationResult.UNSAFE_REALIZATION:
        "the required function is produced by a route that enters a forbidden state",
    RealizationResult.NOT_REPRESENTABLE:
        "the mechanism needs variables the current state model cannot represent",
}


class Entitlement(StrEnum):
    """What the evidence entitles us to say about one capability claim.

    Derived from the support level and scope the repository already records for the citation, never
    from what a primitive asserts about itself. A component cannot grade its own evidence.
    """

    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"


class PrimitiveClass(StrEnum):
    """What kind of real piece this is. Representable does not mean obtainable."""

    GENE = "gene"
    PROTEIN = "protein"
    ENZYME = "enzyme"
    METABOLITE = "metabolite"
    SMALL_MOLECULE = "small_molecule"
    PHARMACEUTICAL = "pharmaceutical"
    RNA = "rna"
    PROTEIN_INTERACTION = "protein_interaction"
    REGULATORY_ELEMENT = "regulatory_element"
    CELLULAR_PROCESS = "cellular_process"
    ENGINEERED_CELL = "engineered_cell"
    SYNTHETIC_CIRCUIT = "synthetic_circuit"
    OTHER = "other"


class Effect(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    SET = "set"
    NO_EFFECT = "no_effect"


OPPOSITE = {Effect.INCREASE: Effect.DECREASE, Effect.DECREASE: Effect.INCREASE}


class EpistemicBurden(StrEnum):
    """How strong a claim this realization is making, from what it proposes to replace.

    Substituting a mechanism the model records as established is a far stronger claim than
    substituting one it records as unresolved, so it has to meet a higher evidence bar. The burden
    is read from the relationship being bypassed; a proposer does not get to set it.
    """

    BYPASSES_UNRESOLVED_RELATIONSHIP = "BYPASSES_UNRESOLVED_RELATIONSHIP"
    BYPASSES_ASSUMED_RELATIONSHIP = "BYPASSES_ASSUMED_RELATIONSHIP"
    BYPASSES_SUPPORTED_RELATIONSHIP = "BYPASSES_SUPPORTED_RELATIONSHIP"
    BYPASSES_ESTABLISHED_RELATIONSHIP = "BYPASSES_ESTABLISHED_RELATIONSHIP"


# What entitlement a step must reach for the realization to count as grounded, given the burden.
# Replacing a well-supported natural mechanism demands evidence that stands on its own;
# CONDITIONAL is only ever enough where the thing being replaced is itself unsettled.
SUFFICIENT_ENTITLEMENT: dict[EpistemicBurden, frozenset[Entitlement]] = {
    EpistemicBurden.BYPASSES_UNRESOLVED_RELATIONSHIP:
        frozenset({Entitlement.SUPPORTED, Entitlement.CONDITIONAL}),
    EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP:
        frozenset({Entitlement.SUPPORTED, Entitlement.CONDITIONAL}),
    EpistemicBurden.BYPASSES_SUPPORTED_RELATIONSHIP:
        frozenset({Entitlement.SUPPORTED}),
    EpistemicBurden.BYPASSES_ESTABLISHED_RELATIONSHIP:
        frozenset({Entitlement.SUPPORTED}),
}

BURDEN_OF_STATUS: dict[str, EpistemicBurden] = {
    "unresolved": EpistemicBurden.BYPASSES_UNRESOLVED_RELATIONSHIP,
    "assumed": EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP,
    "established": EpistemicBurden.BYPASSES_ESTABLISHED_RELATIONSHIP,
}
