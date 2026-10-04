"""A corpus snapshot: what retrieval actually brought back, frozen so compilation is reproducible.

Retrieval and compilation are separate steps on purpose. Hitting a live index at compile time would
make every report unreproducible and would make CI depend on somebody else's uptime, so the
networked step writes a versioned snapshot and the compiler reads only that. Same snapshot, same
version, same verdict.

What a snapshot holds is public literature: titles, identifiers, journals, years and abstracts. Full
text is **not** stored, even where the licence would permit it, which bounds this phase honestly: a
claim whose support lives only in a figure or a methods section cannot be grounded here, and the
report says so rather than guessing from an abstract.

A provider that could not run and a provider that ran and found nothing are different facts, and the
snapshot records which happened per query. Neither becomes "no such capability exists".
"""
from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from rarepipe.stages.control.provenance import Immutable


class QueryOutcome(StrEnum):
    RESULTS_RETURNED = "RESULTS_RETURNED"
    SEARCH_RETURNED_ZERO_RESULTS = "SEARCH_RETURNED_ZERO_RESULTS"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    QUERY_REFUSED = "QUERY_REFUSED"


class ExternalDocument(Immutable):
    """One retrieved source. Everything here is public literature metadata."""

    source_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    journal: str = ""
    pub_year: int | None = None
    url: str = ""
    retrieved_at: str = Field(min_length=1)
    retrieved_by_query: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    characters_stored: int = 0
    full_text: bool = False
    access_note: str = ""
    is_review: bool = False
    relative_path: str = Field(min_length=1, description="Path inside the snapshot, never absolute.")


class QueryOutcomeRecord(Immutable):
    gap_id: str
    query_id: str
    query: str
    dimension: str
    generated_by: str
    executed_on: str
    timestamp: str
    outcome: QueryOutcome
    results: int = 0
    selected: int = 0
    source_ids: tuple[str, ...] = ()
    note: str = ""


class CorpusSnapshot(Immutable):
    corpus_version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    index: str = Field(min_length=1, description="The external index that was searched.")
    full_text_policy: str = Field(min_length=1)
    queries: tuple[QueryOutcomeRecord, ...] = ()
    documents: tuple[ExternalDocument, ...] = ()
    citation_checks: tuple[dict, ...] = Field(
        (), description="Identifier lookups for citations the repository already rests on.")

    def document(self, source_id: str) -> ExternalDocument | None:
        return next((d for d in self.documents if d.source_id == source_id), None)

    def for_gap(self, gap_id: str) -> tuple[ExternalDocument, ...]:
        wanted = {sid for q in self.queries if q.gap_id == gap_id for sid in q.source_ids}
        return tuple(d for d in self.documents if d.source_id in wanted)

    def outcomes_for(self, gap_id: str) -> tuple[QueryOutcomeRecord, ...]:
        return tuple(q for q in self.queries if q.gap_id == gap_id)


def snapshot_path(root: Path, corpus_version: str) -> Path:
    return root / "data" / "literature" / corpus_version


def save(snapshot: CorpusSnapshot, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return manifest


def load(directory: Path) -> CorpusSnapshot:
    return CorpusSnapshot(**json.loads((directory / "manifest.json").read_text()))


def text_of(directory: Path, document: ExternalDocument) -> str:
    """The stored text of a retrieved source. Spans are grounded against exactly this."""
    return (directory / document.relative_path).read_text()
