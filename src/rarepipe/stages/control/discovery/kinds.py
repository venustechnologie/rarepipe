"""The closed vocabularies of capability-gap discovery.

Three things are kept apart that are routinely collapsed, and the enums exist so they cannot be:

* **what a source says** versus **what it was measured in** versus **what we may therefore claim**
  (`VerificationLevel`);
* **a candidate** versus **a capability** (`CandidateStatus`);
* **not found in the universe we inspected** versus **does not exist in biology** — which is why
  every negative result class below names the universe rather than the world.

No numbers. There is no confidence, no probability and no score anywhere in this layer.
"""
from __future__ import annotations

from enum import StrEnum


class CapabilityEntitlement(StrEnum):
    """What the evidence entitles us to say about one candidate capability.

    `GROUNDED` is the only state that lets a candidate become a capability. `UNVERIFIED_SOURCE`
    exists because this case holds two citations with no retrieval record: a claim resting on one
    of them can reach `CONDITIONAL` at most, and no amount of downstream reasoning upgrades it.
    """

    GROUNDED = "GROUNDED"
    CONDITIONAL = "CONDITIONAL"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    CONTRADICTED = "CONTRADICTED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    UNVERIFIED_SOURCE = "UNVERIFIED_SOURCE"
    NOT_REPRESENTABLE = "NOT_REPRESENTABLE"


class VerificationLevel(StrEnum):
    """Three different claims, in increasing strength. A verified source proves a paper exists and
    says something; it does not prove the something is true here."""

    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    CLAIM_GROUNDED_IN_SOURCE = "CLAIM_GROUNDED_IN_SOURCE"
    CAPABILITY_ENTITLED_FOR_CONTEXT = "CAPABILITY_ENTITLED_FOR_CONTEXT"


class CandidateStatus(StrEnum):
    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"
    CONDITIONAL = "CONDITIONAL"
    GROUNDED = "GROUNDED"


class GapStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class GapResult(StrEnum):
    """How a gap ended. Every negative class is a statement about the inspected universe."""

    CAPABILITY_FOUND = "CAPABILITY_FOUND"
    PARTIAL_CAPABILITY = "PARTIAL_CAPABILITY"
    ONLY_DEPENDENT_CAPABILITIES_FOUND = "ONLY_DEPENDENT_CAPABILITIES_FOUND"
    CONTEXT_ONLY_CAPABILITY = "CONTEXT_ONLY_CAPABILITY"
    CONTRADICTED_CAPABILITY = "CONTRADICTED_CAPABILITY"
    NO_GROUNDED_CAPABILITY = "NO_GROUNDED_CAPABILITY"


GAP_MEANING: dict[GapResult, str] = {
    GapResult.CAPABILITY_FOUND:
        "at least one grounded piece satisfies the specification, including its forbidden "
        "dependencies — a candidate for a scientist to argue with, not a demonstrated intervention",
    GapResult.PARTIAL_CAPABILITY:
        "a chain exists and one transformation in it has no grounding; the ungrounded link is named",
    GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND:
        "candidates were found and every one of them depends, somewhere upstream, on exactly the "
        "thing the gap forbids — so no bypass was found, which is a sharper result than finding "
        "nothing",
    GapResult.CONTEXT_ONLY_CAPABILITY:
        "the transformation exists in the sources, in a compartment, agent or system incompatible "
        "with the one required",
    GapResult.CONTRADICTED_CAPABILITY:
        "the most relevant evidence contains a null or opposite result for this transformation",
    GapResult.NO_GROUNDED_CAPABILITY:
        "no admissible capability was found in the universe inspected. This is a statement about "
        "the sources connected to this compiler, never about biology",
}

# Which gap result follows from the best entitlement any candidate reached. Ordered worst-first so
# a scan can take the strongest.
RESULT_ORDER: dict[GapResult, int] = {
    GapResult.CAPABILITY_FOUND: 0,
    GapResult.PARTIAL_CAPABILITY: 1,
    GapResult.CONTEXT_ONLY_CAPABILITY: 2,
    GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND: 3,
    GapResult.CONTRADICTED_CAPABILITY: 4,
    GapResult.NO_GROUNDED_CAPABILITY: 5,
}


class RejectionReason(StrEnum):
    """Why a candidate did not become a capability. Each is a separate validator, not one verdict."""

    ENTITY_MISMATCH = "entity_mismatch"
    INPUT_MISMATCH = "input_mismatch"
    OUTPUT_MISMATCH = "output_mismatch"
    DIRECTION_MISMATCH = "direction_mismatch"
    COMPARTMENT_MISMATCH = "compartment_mismatch"
    AGENT_MISMATCH = "agent_mismatch"
    CONTEXT_MISMATCH = "context_mismatch"
    FORBIDDEN_DEPENDENCY = "forbidden_dependency"
    NO_PROVENANCE = "no_provenance"
    CONTRADICTED = "contradicted"
    UNVERIFIED_SOURCE = "unverified_source"
    NOT_IN_VOCABULARY = "not_in_vocabulary"
    UNSUPPORTED_INTERMEDIATE = "unsupported_intermediate"
    FORBIDDEN_STATE = "forbidden_state"
    FABRICATED = "fabricated"
    # External-evidence layer. Each is a distinct way a real source fails to establish a capability.
    SPAN_NOT_GROUNDED = "span_not_grounded"
    ASSOCIATION_ONLY = "association_only"
    EFFECT_IS_NOT_STATE = "effect_is_not_state"
    FORBIDDEN_NAMED_IN_SPAN = "forbidden_named_in_span"
    INDEPENDENCE_UNESTABLISHED = "independence_unestablished"
    SOURCE_NOT_INDEPENDENT = "source_not_independent"
