"""Where candidates come from, behind one interface, so the compiler does not care.

A provider answers a `SearchSpecification` with whatever its corpus actually contains. The compiler
is indifferent to the corpus, which is the point: a literature provider, a gene-function provider or
a compound-mechanism provider can be added later without the validation layer changing.

Only two providers exist in this phase, and neither can invent anything:

* **`RepositoryProvider`** searches the evidence inventory derived from the case's own causal chain.
  Its corpus is small — fifteen claims — and that is stated in every report, because "nothing found"
  from a fifteen-claim corpus means something very different from "nothing found" from a literature
  index.
* **`CuratedFileProvider`** reads claims a human curated into a file. It is unconfigured by default
  and contributes nothing, and it says so, so an absent corpus never reads as an exhausted one.

There is deliberately no provider that asks a language model what it remembers. A model's
recollection of a paper is not a source, and a layer built to refuse ungrounded claims must not
manufacture them at the point of entry.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import Field

from rarepipe.stages.control.discovery.gaps import SearchSpecification
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.realization.evidence import EvidenceInventory
from rarepipe.stages.control.realization.kinds import Effect
from rarepipe.stages.simulate.chain import Support


class SourceHit(Immutable):
    """One claim a provider found, reported as the source states it — not as the gap wants it."""

    provider: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    reference: str = Field("", description="A citation, or empty when the corpus has none.")
    verified: bool = Field(
        description="False when the corpus records no retrieval for the citation.")
    claim: str = Field(min_length=1)
    claim_subject: str = Field(min_length=1, description="The entity or node the claim is about.")
    claim_input: str = Field(min_length=1)
    claim_output: str = Field(min_length=1)
    claim_direction: Effect
    measured_with: str = ""
    measured_in_compartment: str = ""
    measured_in_system: str = ""
    support: Support
    caveat: str = ""
    span: str = Field("", description="Where in the source the claim was located.")

    def dimension(self, name: str) -> str:
        return {"agent": self.measured_with, "compartment": self.measured_in_compartment,
                "system": self.measured_in_system}[name]


class ProviderReport(Immutable):
    provider: str
    corpus_size: int
    corpus_description: str
    hits: tuple[SourceHit, ...] = ()
    related: tuple[SourceHit, ...] = Field(
        (), description="Claims the corpus holds that do not produce the required output but that a "
                        "multi-step candidate could cite. Candidates are enumerated from `hits`; "
                        "both are used to resolve a citation, so a chain can be audited rather "
                        "than refused as fabricated.")
    note: str = ""


@runtime_checkable
class CapabilitySourceProvider(Protocol):
    name: str

    def find(self, spec: SearchSpecification) -> ProviderReport:
        ...


class RepositoryProvider:
    """The case's own evidence inventory. It can return a claim or nothing; it cannot invent one."""

    name = "repository_inventory"

    def __init__(self, inventory: EvidenceInventory) -> None:
        self.inventory = inventory

    def _hit(self, edge) -> SourceHit:
        context = self.inventory.context(edge.ref)
        return SourceHit(
            provider=self.name, source_id=edge.edge_id, reference=edge.ref,
            verified=edge.verified, claim=edge.mechanism, claim_subject=edge.source,
            claim_input=edge.source, claim_output=edge.target, claim_direction=edge.effect,
            measured_with=context.measured_with if context else "",
            measured_in_compartment=context.measured_in_compartment if context else "",
            measured_in_system=context.measured_in_system if context else "",
            support=edge.support, caveat=edge.caveat,
            span=f"causal chain edge {edge.edge_id}; scope: {edge.scope or 'none recorded'}")

    def find(self, spec: SearchSpecification) -> ProviderReport:
        hits, related = [], []
        for edge in self.inventory.edges:
            if edge.target != spec.required_output:
                related.append(self._hit(edge))
                continue
            if spec.required_input and edge.source != spec.required_input:
                related.append(self._hit(edge))
                continue
            hits.append(self._hit(edge))
        return ProviderReport(
            provider=self.name, corpus_size=len(self.inventory.edges),
            corpus_description=("the evidence inventory derived from this case's causal chain; "
                                "five citations across fifteen claims"),
            hits=tuple(sorted(hits, key=lambda h: h.source_id)),
            related=tuple(sorted(related, key=lambda h: h.source_id)),
            note=("a corpus this small makes a negative result a statement about the corpus. "
                  "Nothing here is a literature search." if not hits else ""))


class CuratedFileProvider:
    """Claims a human curated into a file, so a scientist can extend the corpus without code.

    Unconfigured by default. An absent file contributes no hits and says so, because an empty
    corpus and an exhausted one must never read the same.
    """

    name = "curated_claims"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def find(self, spec: SearchSpecification) -> ProviderReport:
        if self.path is None or not self.path.exists():
            return ProviderReport(
                provider=self.name, corpus_size=0,
                corpus_description="a human-curated claim file",
                note=("not configured, so this provider contributed nothing. Its absence is not "
                      "evidence that no such claim exists"))
        records = json.loads(self.path.read_text())
        hits = tuple(SourceHit(provider=self.name, **record) for record in records
                     if record.get("claim_output") == spec.required_output)
        return ProviderReport(
            provider=self.name, corpus_size=len(records),
            corpus_description=f"human-curated claims from {self.path.name}",
            hits=tuple(sorted(hits, key=lambda h: h.source_id)))


def search(providers: tuple[CapabilitySourceProvider, ...],
           spec: SearchSpecification) -> tuple[ProviderReport, ...]:
    return tuple(provider.find(spec) for provider in providers)
