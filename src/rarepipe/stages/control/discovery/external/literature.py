"""The scientific literature provider: a frozen corpus snapshot, read offline.

It answers a functional specification with the claims an agent read out of documents that were
actually retrieved. It grades nothing. Every hit carries its verbatim span, the context the
observation was made in, the dependencies the source itself declares, and what the source says it
does not establish — so the validators can refuse it for the right reason rather than a vague one.

Three states are kept apart, because collapsing them is how a search failure becomes a biological
claim:

* the provider could not run — `PROVIDER_UNAVAILABLE`;
* it ran and the index returned nothing — `SEARCH_RETURNED_ZERO_RESULTS`;
* it ran, returned documents, and no claim in them survived the validators.

Only the third says anything about the evidence, and even then only about this corpus.
"""
from __future__ import annotations

from pathlib import Path

from rarepipe.stages.control.discovery.external import corpus as C
from rarepipe.stages.control.discovery.external.claims import CandidateClaim
from rarepipe.stages.control.discovery.gaps import SearchSpecification
from rarepipe.stages.control.discovery.providers import ProviderReport, SourceHit
from rarepipe.stages.simulate.chain import Support

# A retrieved claim's support level, from the kind of evidence its grade represents. The chain's
# vocabulary is reused so one scale runs through the whole compiler.
_GRADE_SUPPORT = {
    "CAUSAL_EXPERIMENTAL": Support.HUMAN_EXPERIMENTAL,
    "MECHANISTIC": Support.MODEL_EXPERIMENTAL,
    "PERTURBATION_SUPPORTED": Support.MODEL_EXPERIMENTAL,
    "ASSOCIATION": Support.CLASS_LEVEL,
}


class LiteratureProvider:
    name = "scientific_literature"

    def __init__(self, directory: Path, snapshot: C.CorpusSnapshot,
                 claims: tuple[CandidateClaim, ...]) -> None:
        self.directory = directory
        self.snapshot = snapshot
        self.claims = claims

    def _hit(self, claim: CandidateClaim) -> SourceHit | None:
        document = self.snapshot.document(claim.source_id)
        if document is None:
            return None
        lattice = claim.context
        # The most specific system the observation was made in, taken from the lattice rather than
        # assembled from several of its dimensions. Concatenating species and cell type produces a
        # string that no gap can match, and the species, tissue and disease-state differences belong
        # in transfer gaps, which is where they are reported.
        system = lattice.cell_type or lattice.tissue or lattice.experimental_system
        return SourceHit(
            provider=self.name, source_id=claim.source_id,
            reference=document.pmid and f"PMID:{document.pmid}" or claim.source_id,
            verified=True, claim=f"{claim.subject} {claim.relation}",
            claim_subject=claim.subject, claim_input=claim.subject,
            claim_output=claim.object, claim_direction=claim.direction,
            measured_in_compartment=lattice.compartment, measured_in_system=system,
            measured_with=lattice.perturbation_type,
            support=_GRADE_SUPPORT[claim.causal_grade.value],
            caveat=claim.limitation,
            span=f"{document.source_id}: {document.title}",
            claim_id=claim.claim_id, quoted_span=claim.source_span,
            document_digest=document.content_digest, document_title=document.title,
            document_url=document.url, causal_grade=claim.causal_grade, lattice=lattice,
            declared_dependencies=claim.declared_dependencies,
            asserts_independence_from=claim.asserts_independence_from,
            limitation=claim.limitation, claimed_state=claim.claimed_state,
            measurement=claim.measurement)

    def find(self, spec: SearchSpecification) -> ProviderReport:
        outcomes = self.snapshot.outcomes_for(spec.gap_id)
        documents = self.snapshot.for_gap(spec.gap_id)
        hits, related, unresolved = [], [], []
        for claim in self.claims:
            hit = self._hit(claim)
            if hit is None:
                # A claim citing a document this corpus does not hold. Counted and reported rather
                # than dropped: a citation that resolves to nothing is an event, not a non-event.
                unresolved.append(f"{claim.claim_id} cites {claim.source_id}, which the snapshot "
                                  "does not contain")
                continue
            (hits if (claim.gap_id == spec.gap_id and claim.object == spec.required_output)
             else related).append(hit)

        ran = [o for o in outcomes if o.outcome.value == "RESULTS_RETURNED"]
        zero = [o for o in outcomes if o.outcome.value == "SEARCH_RETURNED_ZERO_RESULTS"]
        unavailable = [o for o in outcomes if o.outcome.value == "PROVIDER_UNAVAILABLE"]
        refused = [o for o in outcomes if o.outcome.value == "QUERY_REFUSED"]
        if unavailable and not ran:
            note = (f"{len(unavailable)} queries could not reach the index. That is a provider "
                    "failure, not an absence of evidence")
        elif not outcomes:
            note = (f"the snapshot holds no queries for {spec.gap_id}; this provider was not run for "
                    "this gap")
        else:
            note = (f"{len(ran)} queries returned results, {len(zero)} returned none, "
                    f"{len(unavailable)} could not reach the index, {len(refused)} were refused by "
                    "the disclosure or therapy guard. "
                    f"{len(documents)} documents screened, {len(hits)} claims extracted for this "
                    "output. A negative verdict here is bounded by exactly this")
        if unresolved:
            note += ". " + "; ".join(unresolved)
        return ProviderReport(
            provider=self.name, corpus_size=len(documents),
            corpus_description=(f"corpus snapshot {self.snapshot.corpus_version} from "
                                f"{self.snapshot.index}; {self.snapshot.full_text_policy}"),
            hits=tuple(sorted(hits, key=lambda h: h.claim_id)),
            related=tuple(sorted(related, key=lambda h: h.claim_id)), note=note,
            queries=tuple({"query_id": o.query_id, "query": o.query, "dimension": o.dimension,
                           "outcome": o.outcome.value, "results": o.results,
                           "selected": o.selected, "note": o.note} for o in outcomes),
            accounting={"queries_issued": len(outcomes), "queries_with_results": len(ran),
                        "queries_zero_results": len(zero), "queries_refused": len(refused),
                        "provider_unavailable": len(unavailable),
                        "sources_retrieved": len(documents),
                        "claims_extracted": len(hits),
                        "claims_citing_absent_documents": len(unresolved)})

    def documents(self) -> dict[str, str]:
        """Stored text per source, for the span-grounding check."""
        return {d.source_id: C.text_of(self.directory, d) for d in self.snapshot.documents}
