"""Backward grounding: audit every load-bearing citation against the document itself.

The forward rule refuses a new claim whose source does not say what the claim says. Run backwards
over the claims a system already believes, it finds the same error in things nobody was questioning —
which is how this audit found that one of the case's own citations cannot support the attribution
built on it.

**The rule is asymmetric, and that is what makes a blunt test safe.** An abstract that mentions
neither the input nor the output of a relation is not about that relation, whatever else it is about.
An abstract that mentions both might be. So this audit can disqualify an attribution; it cannot
confirm one. Every verdict says which it is doing.

**Attributions are derived from the chain, not listed by hand.** Each cited edge contributes one
attribution, and the literature spellings of its endpoints come from one table, so an edge added or
re-cited in the chain is audited automatically and the audit cannot fall behind its source.

Full text is not stored, so a term absent from an abstract may simply not have been mentioned. One
endpoint missing is therefore `PARTIALLY_SUPPORTS_ATTRIBUTION` with that limit stated; both missing
is a disqualification.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from rarepipe.stages.control.discovery.external.corpus import CorpusSnapshot
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.simulate.chain import CausalChain, Support

# How the literature spells each node of the chain. Explicit, because deriving spellings from a
# variable name by string munging would both miss terms and invent matches.
NODE_TERMS: dict[str, tuple[str, ...]] = {
    "nicotinic_acid_exposure": ("nicotinic acid", "niacin"),
    "nad_whole_blood": ("blood NAD", "whole blood", "circulating NAD"),
    "nad_intracellular": ("muscle NAD", "tissue NAD", "intracellular NAD", "cellular NAD"),
    "sirt2_activity": ("SIRT2", "sirtuin"),
    "k668_acetylation": ("acetylation", "acetylated", "deacetyl", "K668"),
    "bubr1_abundance": ("BubR1", "BUBR1", "BUB1B"),
    "bubr1_residual_function": ("BubR1", "BUBR1", "BUB1B"),
    "checkpoint_activation": ("checkpoint", "mitotic arrest"),
    "checkpoint_silencing": ("checkpoint", "silencing", "mitotic exit"),
    "chromosome_alignment": ("alignment", "congression", "kinetochore"),
    "missegregation": ("missegregation", "segregation", "chromosome instability",
                       "chromatid separation"),
    "total_aneuploidy": ("aneuploid", "aneuploidy"),
    "cell_death": ("cell death", "apoptosis", "viability", "senescence"),
    "division_rate": ("proliferation", "division", "growth", "lifespan"),
}

# A reference asked to carry at least this many distinct relations is carrying more than one abstract
# can distinguish between, once any of them is only partially supported.
AMBIGUITY_THRESHOLD = 3


class AttributionState(StrEnum):
    SUPPORTS_ATTRIBUTION = "SUPPORTS_ATTRIBUTION"
    PARTIALLY_SUPPORTS_ATTRIBUTION = "PARTIALLY_SUPPORTS_ATTRIBUTION"
    DOES_NOT_SUPPORT_ATTRIBUTION = "DOES_NOT_SUPPORT_ATTRIBUTION"
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    SOURCE_MISSING = "SOURCE_MISSING"
    ATTRIBUTION_AMBIGUOUS = "ATTRIBUTION_AMBIGUOUS"


DISQUALIFYING = {AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION, AttributionState.SOURCE_MISSING}


class Check(Immutable):
    name: str
    outcome: str = Field(description="pass | fail | not_machine_checkable")
    detail: str


class Attribution(Immutable):
    """One cited edge of the chain, and what its citation is being asked to support."""

    edge_id: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    attributed: str = Field(min_length=10)
    input_node: str
    output_node: str
    input_terms: tuple[str, ...]
    output_terms: tuple[str, ...]
    support: Support
    scope_note: str = ""
    load_bearing_for: tuple[str, ...] = Field(
        (), description="What downstream conclusions rest on this edge.")


class CitationAudit(Immutable):
    ref: str
    edge_id: str
    attributed: str
    source_id: str = ""
    title: str = ""
    verdict: AttributionState
    checks: tuple[Check, ...] = ()
    terms_present: tuple[str, ...] = ()
    terms_absent: tuple[str, ...] = ()
    attributions_on_this_ref: int = 1
    chain_marks_unverified: bool = False
    chain_label_is_stale: bool = Field(
        False, description="True when the chain marks the citation as having no retrieval record and "
                           "retrieval has since resolved it. The label itself then needs repairing.")
    consequence: str

    @property
    def disqualifies(self) -> bool:
        return self.verdict in DISQUALIFYING


def _present(text: str, term: str) -> bool:
    return any(option.lower() in text.lower() for option in term.split("|"))


def _matched(text: str, terms: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    present = tuple(t for t in terms if _present(text, t))
    return present, tuple(t for t in terms if t not in present)


def attributions(chain: CausalChain) -> tuple[Attribution, ...]:
    """Every cited edge of the chain. Derived, so the audit cannot fall behind its source."""
    out: list[Attribution] = []
    for edge in chain.edges:
        if not edge.evidence_ref:
            continue
        ref = edge.evidence_ref.split(" ")[0]
        out.append(Attribution(
            edge_id=f"{edge.source}->{edge.target}", ref=ref,
            attributed=f"{edge.mechanism}"[:200],
            input_node=edge.source, output_node=edge.target,
            input_terms=NODE_TERMS.get(edge.source, (edge.source.replace("_", " "),)),
            output_terms=NODE_TERMS.get(edge.target, (edge.target.replace("_", " "),)),
            support=edge.support, scope_note=edge.scope_note))
    return tuple(sorted(out, key=lambda a: (a.ref, a.edge_id)))


def audit(snapshot: CorpusSnapshot, texts: dict[str, str],
          chain: CausalChain | None = None) -> tuple[CitationAudit, ...]:
    from rarepipe.stages.simulate.mva import mva_chain
    chain = chain if chain is not None else mva_chain()
    items = attributions(chain)
    per_ref: dict[str, int] = {}
    for item in items:
        per_ref[item.ref] = per_ref.get(item.ref, 0) + 1

    out: list[CitationAudit] = []
    for item in items:
        document = next((d for d in snapshot.documents
                         if d.pmid and f"PMID:{d.pmid}" == item.ref), None)
        if document is None or document.source_id not in texts:
            out.append(CitationAudit(
                ref=item.ref, edge_id=item.edge_id, attributed=item.attributed,
                verdict=AttributionState.SOURCE_MISSING,
                attributions_on_this_ref=per_ref[item.ref],
                checks=(Check(name="source exists", outcome="fail",
                              detail="not present in the corpus snapshot"),),
                consequence=("the citation was not retrieved, so the attribution rests on nothing "
                             "this compiler can inspect")))
            continue

        text = f"{document.title}\n{texts[document.source_id]}"
        unverified = "UNVERIFIED" in (
            next((e.evidence_ref or "" for e in chain.edges
                  if f"{e.source}->{e.target}" == item.edge_id), ""))
        input_present, input_absent = _matched(text, item.input_terms)
        output_present, output_absent = _matched(text, item.output_terms)
        both_absent = not input_present and not output_present
        one_absent = bool(input_present) != bool(output_present)

        checks = [
            Check(name="source exists", outcome="pass", detail=f"retrieved as {document.title!r}"),
            Check(name="retrieval record exists",
                  outcome="pass" if document.retrieved_at and document.content_digest else "fail",
                  detail=f"retrieved {document.retrieved_at}, digest {document.content_digest}"),
            Check(name="attributed input appears",
                  outcome="pass" if input_present else "fail",
                  detail=(f"{list(input_present)} present" if input_present
                          else f"none of {list(item.input_terms)} appears")),
            Check(name="attributed output appears",
                  outcome="pass" if output_present else "fail",
                  detail=(f"{list(output_present)} present" if output_present
                          else f"none of {list(item.output_terms)} appears")),
            Check(name="claimed direction supported", outcome="not_machine_checkable",
                  detail=("direction is established by a grounded span where one exists; an "
                          "abstract's prose is not parsed for it")),
            Check(name="experimental context matches the recorded scope",
                  outcome="not_machine_checkable",
                  detail=(f"the chain records the scope as {item.scope_note!r}; whether the "
                          "document's own context matches it is a reading, not a string match")),
            Check(name="claim follows from the source", outcome="not_machine_checkable",
                  detail="this is the judgement a scientist makes; the audit bounds it, not more"),
        ]

        # The term checks come first. An unverified citation may still be about the right thing;
        # a document that is not about the relation cannot support it however well verified it is.
        # Ordering these the other way round let the weaker fact hide the decisive one.
        if both_absent:
            verdict = AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION
            consequence = (f"the document mentions neither {item.input_node} nor {item.output_node} "
                           "in any of their recorded spellings, so what is stored is not about this "
                           "relation. The attribution is disqualified as stored; since full text is "
                           "not kept, the remedy may be retrieving the full article rather than "
                           "dropping the edge")
        elif one_absent and per_ref[item.ref] >= AMBIGUITY_THRESHOLD:
            verdict = AttributionState.ATTRIBUTION_AMBIGUOUS
            consequence = (f"this reference is attributed {per_ref[item.ref]} distinct relations and "
                           "one endpoint of this one is absent from the abstract, so which of them "
                           "the source actually supports cannot be isolated from what is stored")
        elif one_absent:
            verdict = AttributionState.PARTIALLY_SUPPORTS_ATTRIBUTION
            consequence = ("one endpoint of the relation is absent from the abstract. Full text is "
                           "not stored, so this may be scope rather than a mismatch; it is not a "
                           "disqualification and it is not a confirmation")
        elif unverified and document is None:
            verdict = AttributionState.SOURCE_UNVERIFIED
            consequence = ("the chain marks this citation as having no retrieval record and nothing "
                           "retrieved resolves it, so nothing resting on it may be stated as "
                           "verified")
        else:
            verdict = AttributionState.SUPPORTS_ATTRIBUTION
            consequence = ("both endpoints appear, so the document can be about this relation. That "
                           "is necessary and not sufficient: this audit disqualifies attributions, "
                           "it does not confirm them")
        if unverified:
            consequence += (". The chain marks this citation as having no retrieval record; "
                            "retrieval has now resolved it, so that label is itself stale")

        out.append(CitationAudit(
            ref=item.ref, edge_id=item.edge_id, attributed=item.attributed,
            source_id=document.source_id, title=document.title, verdict=verdict,
            checks=tuple(checks), terms_present=tuple(sorted(input_present + output_present)),
            terms_absent=tuple(sorted(input_absent + output_absent)),
            attributions_on_this_ref=per_ref[item.ref], chain_marks_unverified=unverified,
            chain_label_is_stale=unverified and document is not None,
            consequence=consequence))
    return tuple(sorted(out, key=lambda a: (a.ref, a.edge_id)))
