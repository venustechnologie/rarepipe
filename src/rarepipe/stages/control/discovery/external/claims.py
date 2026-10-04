"""Candidate claims extracted from retrieved sources, with the context they were observed in.

A claim is proposed by an agent reading a document and is worth nothing until three separate things
hold: the span it cites exists verbatim in the stored document, the relation it asserts matches the
interface, and the context it was observed in is the one required. This module carries the first and
third; the validators decide the second.

**Independence is never a default.** A newly discovered entity has no ancestry in the repository's
inventory, so a forbidden-dependency check over that inventory alone would pass vacuously for every
new entity — which would make "we found a bypass" the automatic answer for anything unfamiliar. So a
claim declares the dependencies its own source states, those become edges in the ancestry graph, and
a bypass candidate whose independence no source asserts is recorded as `INDEPENDENCE_UNESTABLISHED`.
Absence of a recorded link is not evidence of absence.

The same applies to the span itself: if the text supporting a claim names the forbidden dependency,
independence cannot be certified from that text, whatever the claim says about itself.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.kinds import Effect


class CausalGrade(StrEnum):
    """What kind of relation the evidence supports. An association does not become a capability."""

    ASSOCIATION = "ASSOCIATION"
    PERTURBATION_SUPPORTED = "PERTURBATION_SUPPORTED"
    MECHANISTIC = "MECHANISTIC"
    CAUSAL_EXPERIMENTAL = "CAUSAL_EXPERIMENTAL"


# A capability asserting A -> B needs evidence compatible with causation, or an explicit limitation.
CAUSAL_ENOUGH = {CausalGrade.PERTURBATION_SUPPORTED, CausalGrade.MECHANISTIC,
                 CausalGrade.CAUSAL_EXPERIMENTAL}


class ContextVerdict(StrEnum):
    EXACT_CONTEXT = "EXACT_CONTEXT"
    COMPATIBLE_CONTEXT = "COMPATIBLE_CONTEXT"
    TRANSFER_REQUIRED = "TRANSFER_REQUIRED"
    INCOMPATIBLE_CONTEXT = "INCOMPATIBLE_CONTEXT"


class ContextLattice(Immutable):
    """Where an observation was made, dimension by dimension. Empty means the source did not say."""

    species: str = ""
    cell_type: str = ""
    tissue: str = ""
    developmental_state: str = ""
    disease_state: str = ""
    compartment: str = ""
    experimental_system: str = ""
    perturbation_type: str = ""

    def dimension(self, name: str) -> str:
        return getattr(self, name)

    @property
    def recorded(self) -> tuple[str, ...]:
        return tuple(name for name in ("species", "cell_type", "tissue", "developmental_state",
                                      "disease_state", "compartment", "experimental_system",
                                      "perturbation_type") if getattr(self, name))


# Explicit compartment compatibility. The PRD requires the transfer rule to be stated rather than
# inferred, so this table is the whole rule. A tissue-homogenate measurement of a metabolite that is
# overwhelmingly intracellular is compatible with an intracellular-pool requirement; whole blood is
# not, because it includes plasma and so can rise without any cell's content changing. That
# distinction is exactly why the abundance route was reported as compartment-mismatched.
COMPARTMENT_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "intracellular pool": ("intracellular (tissue homogenate)", "cellular pool"),
}


def compartment_verdict(demonstrated: str, required: str) -> ContextVerdict:
    if not demonstrated or not required:
        return ContextVerdict.TRANSFER_REQUIRED
    if demonstrated.strip().lower() == required.strip().lower():
        return ContextVerdict.EXACT_CONTEXT
    allowed = COMPARTMENT_COMPATIBILITY.get(required.strip().lower(), ())
    if any(demonstrated.strip().lower() == item.lower() for item in allowed):
        return ContextVerdict.COMPATIBLE_CONTEXT
    return ContextVerdict.INCOMPATIBLE_CONTEXT


class TransferGap(Immutable):
    """A first-class object, not a warning. It can become literature to find, or an experiment."""

    gap_id: str
    dimension: str
    demonstrated_in: str = Field(min_length=1)
    required: str = Field(min_length=1)
    missing: str = Field(min_length=1, description="What would have to be shown for it to transfer.")

    @property
    def summary(self) -> str:
        return (f"{self.dimension}: demonstrated in {self.demonstrated_in}, required "
                f"{self.required}; missing {self.missing}")


class CandidateClaim(Immutable):
    """One relation an agent read out of one retrieved document."""

    claim_id: str = Field(min_length=1)
    gap_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1, description="A document in the corpus snapshot.")
    subject: str = Field(min_length=1, description="The entity the claim is about.")
    relation: str = Field(min_length=3)
    object: str = Field(min_length=1, description="What the relation acts on, in our vocabulary.")
    direction: Effect
    claimed_state: str = Field(
        "", description="The qualitative state claimed, where the gap asks for one. Left empty when "
                        "the source reports a change rather than a restored state.")
    causal_grade: CausalGrade
    context: ContextLattice
    declared_dependencies: tuple[str, ...] = Field(
        (), description="Dependencies the source itself states for this mechanism. These become "
                        "edges in the ancestry graph, which is how a new entity gets an ancestry "
                        "at all.")
    asserts_independence_from: tuple[str, ...] = Field(
        (), description="Entities the source explicitly says the mechanism does not require. Only an "
                        "explicit statement counts; silence is not independence.")
    source_span: str = Field(
        min_length=20,
        description="Verbatim text from the stored document. Checked character for character, so a "
                    "paraphrase fails rather than passes.")
    measurement: str = Field(min_length=3, description="What was actually measured.")
    limitation: str = Field("", description="What the source itself says it does not establish.")
    extracted_by: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type is not EpistemicType.INFERRED_HYPOTHESIS:
            raise ValueError(
                f"{self.claim_id}: an extracted claim is an INFERRED_HYPOTHESIS until the validators "
                "ground it; the extraction is a reading, not a finding")
        if self.subject == self.object:
            raise ValueError(f"{self.claim_id}: subject and object cannot be the same node")
        return self


def span_is_grounded(claim: CandidateClaim, document_text: str) -> bool:
    """The cited span must exist in the stored document. Whitespace is normalised; wording is not."""
    normalise = lambda text: " ".join(text.split()).lower()  # noqa: E731
    return normalise(claim.source_span) in normalise(document_text)


def names_forbidden(claim: CandidateClaim, forbidden_terms: tuple[str, ...]) -> tuple[str, ...]:
    """Forbidden entities named in the supporting span itself.

    If the text that supports a claim names the thing a bypass must avoid, independence cannot be
    certified from that text — regardless of what the claim says about itself.
    """
    haystack = f"{claim.source_span} {claim.relation}".lower()
    return tuple(sorted({term for term in forbidden_terms if term.lower() in haystack}))
