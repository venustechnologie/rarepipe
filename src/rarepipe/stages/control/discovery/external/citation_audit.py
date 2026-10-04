"""Audit the citations the repository already rests on against the documents themselves.

The grounding layer refuses a new claim whose source does not say what the claim says. The same
check applied backwards is just as useful: the case's own causal chain attributes a mechanism to each
of its citations, and now that those citations have been retrieved, the attribution can be checked.

The rule is deterministic and deliberately blunt. For each attribution, a small set of terms must
appear in the retrieved document — the agent and the entity the attribution is about. A document that
contains none of them is not evidence for that attribution, whatever else it may be about. This
cannot confirm that an attribution is right; it can only show when one cannot be right, which is the
asymmetry that makes a blunt rule safe here.

The required terms are transcribed from the chain's own `mechanism` and `scope_note`, and a test
asserts every `edge_id` below still exists in the chain, so the table cannot drift from its source.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from rarepipe.stages.control.discovery.external.corpus import CorpusSnapshot
from rarepipe.stages.control.provenance import Immutable


class AuditVerdict(StrEnum):
    SUPPORTS_ATTRIBUTION = "SUPPORTS_ATTRIBUTION"
    DOES_NOT_SUPPORT_ATTRIBUTION = "DOES_NOT_SUPPORT_ATTRIBUTION"
    NOT_RETRIEVED = "NOT_RETRIEVED"


class Attribution(Immutable):
    edge_id: str = Field(min_length=1, description="The chain edge that cites this reference.")
    ref: str = Field(min_length=1)
    attributed: str = Field(min_length=10, description="What the chain attributes to it.")
    requires_terms: tuple[str, ...] = Field(
        min_length=1, description="Terms the document must contain for the attribution to be about "
                                  "it at all. Necessary, not sufficient.")


# One entry per cited edge in the case's chain. The terms are the agent and the entity each
# attribution is about.
ATTRIBUTIONS: tuple[Attribution, ...] = (
    Attribution(edge_id="nicotinic_acid_exposure->nad_whole_blood", ref="PMID:42628241",
                attributed="nicotinic acid raises circulating NAD precursor availability",
                requires_terms=("nicotinic acid", "NAD")),
    Attribution(edge_id="nicotinic_acid_exposure->bubr1_abundance", ref="PMID:42543917",
                attributed=("a null result for a direct nicotinic-acid effect on the altered "
                            "protein's abundance"),
                requires_terms=("niacin|nicotinic", "BubR1|BUB1B")),
    Attribution(edge_id="sirt2_activity->k668_acetylation", ref="PMID:24825348",
                attributed="the deacetylase acts on the altered protein at a specific residue",
                requires_terms=("SIRT2", "BubR1")),
    Attribution(edge_id="bubr1_residual_function->checkpoint_activation", ref="PMID:20516114",
                attributed="restored abundance supports checkpoint activation",
                requires_terms=("BUBR1|BubR1",)),
    Attribution(edge_id="bubr1_residual_function->checkpoint_silencing", ref="PMID:33207204",
                attributed="domain function supports checkpoint silencing and alignment",
                requires_terms=("BUBR1|BubR1",)),
)


class CitationAudit(Immutable):
    ref: str
    edge_id: str
    attributed: str
    source_id: str = ""
    title: str = ""
    verdict: AuditVerdict
    terms_present: tuple[str, ...] = ()
    terms_absent: tuple[str, ...] = ()
    consequence: str


def _present(text: str, term: str) -> bool:
    """A term with alternatives separated by `|` counts as present if any alternative appears."""
    return any(option.lower() in text.lower() for option in term.split("|"))


def audit(snapshot: CorpusSnapshot, texts: dict[str, str]) -> tuple[CitationAudit, ...]:
    out: list[CitationAudit] = []
    for attribution in ATTRIBUTIONS:
        document = next((d for d in snapshot.documents
                         if d.pmid and f"PMID:{d.pmid}" == attribution.ref), None)
        if document is None or document.source_id not in texts:
            out.append(CitationAudit(
                ref=attribution.ref, edge_id=attribution.edge_id,
                attributed=attribution.attributed, verdict=AuditVerdict.NOT_RETRIEVED,
                consequence=("the citation was not retrieved, so the attribution could not be "
                             "checked either way")))
            continue
        text = f"{document.title}\n{texts[document.source_id]}"
        present = tuple(t for t in attribution.requires_terms if _present(text, t))
        absent = tuple(t for t in attribution.requires_terms if not _present(text, t))
        supports = not absent
        out.append(CitationAudit(
            ref=attribution.ref, edge_id=attribution.edge_id, attributed=attribution.attributed,
            source_id=document.source_id, title=document.title,
            verdict=(AuditVerdict.SUPPORTS_ATTRIBUTION if supports
                     else AuditVerdict.DOES_NOT_SUPPORT_ATTRIBUTION),
            terms_present=present, terms_absent=absent,
            consequence=("the retrieved document is about the terms the attribution requires, so it "
                         "can be what the chain says it is"
                         if supports else
                         f"the retrieved document contains none of {list(absent)}, so it cannot be "
                         f"evidence for {attribution.attributed!r}. Everything the chain derives "
                         "from this edge rests on an attribution the document does not support")))
    return tuple(sorted(out, key=lambda a: a.ref))
