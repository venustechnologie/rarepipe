#!/usr/bin/env python3
"""The networked step: run the gaps' query plans against a real external index, freeze a snapshot.

Run this deliberately. Compilation never touches the network — it reads the snapshot this writes, so
the same snapshot gives the same verdict and CI needs no connectivity.

Every query passes the repository's existing guards before it leaves: the Stage 04 case-identity
guard, which no phase lifts, and the therapy filter, so a functional search cannot drift into an
intervention hunt. Abstracts and metadata only; full text is not stored.

    uv run python tools/control/retrieve_capability_evidence.py [--corpus-version mva-external-v1]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.core.artifacts import utc_now  # noqa: E402
from rarepipe.stages.adjudicate.disclosure import DisclosureRefused  # noqa: E402
from rarepipe.stages.control.discovery import mva_gaps  # noqa: E402
from rarepipe.stages.control.discovery.external import corpus as C  # noqa: E402
from rarepipe.stages.control.discovery.external.queryplan import (  # noqa: E402
    PLANNER_ID, PLANNER_VERSION, plan,
)
from rarepipe.stages.mechanism.retrieve import (  # noqa: E402
    RetrievalRefused, check_search_query, search,
)
from rarepipe.stages.mechanism.retrieve import relevance  # noqa: E402

INDEX = "Europe PMC REST (https://www.ebi.ac.uk/europepmc/webservices/rest/search)"
PROVIDER_ID, PROVIDER_VERSION = "scientific-literature-provider", "0.1.0"
FULL_TEXT_POLICY = ("abstracts and metadata only; full text is not stored, so a claim whose support "
                    "lives only in a figure or methods section cannot be grounded from this snapshot")
# Citations the repository already rests on. Verifying them is a stated deliverable: an unverified
# citation caps everything resting on it at conditional until it passes the normal pipeline.
REPO_CITATIONS = ("42628241", "42543917", "24825348", "20516114", "33207204", "32386566")


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _store(directory: Path, record: dict, query: str) -> C.ExternalDocument:
    pmid = str(record.get("pmid") or "")
    source_id = f"PMID:{pmid}" if pmid else f"EPMC:{record.get('id')}"
    title = _clean(record.get("title"))
    payload = f"{title}\n\n{_clean(record.get('abstractText'))}".strip()
    docs = directory / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    relative = f"docs/{source_id.replace(':', '_')}.txt"
    (directory / relative).write_text(payload + "\n")
    return C.ExternalDocument(
        source_id=source_id, source_type="journal_article", title=title or source_id,
        pmid=pmid, pmcid=record.get("pmcid") or "", doi=record.get("doi") or "",
        journal=_clean((record.get("journalInfo") or {}).get("journal", {}).get("title")
                       or record.get("journalTitle")),
        pub_year=int(record["pubYear"]) if str(record.get("pubYear", "")).isdigit() else None,
        url=f"https://europepmc.org/article/MED/{pmid}" if pmid else "",
        retrieved_at=utc_now().isoformat(), retrieved_by_query=query,
        content_digest="sha256:" + hashlib.sha256(payload.encode()).hexdigest(),
        characters_stored=len(payload), full_text=False,
        access_note="abstract and metadata from the search index",
        is_review="review" in (record.get("pubType") or "").lower(), relative_path=relative)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-version", default="mva-external-v1")
    parser.add_argument("--select-top", type=int, default=4)
    parser.add_argument("--min-score", type=int, default=5)
    args = parser.parse_args()

    directory = C.snapshot_path(ROOT, args.corpus_version)
    documents: dict[str, C.ExternalDocument] = {}
    outcomes: list[C.QueryOutcomeRecord] = []

    for gap in mva_gaps.gaps():
        for planned in plan(gap).queries:
            stamp = utc_now().isoformat()
            try:
                check_search_query(planned.query)
            except (DisclosureRefused, RetrievalRefused) as exc:
                outcomes.append(C.QueryOutcomeRecord(
                    gap_id=gap.gap_id, query_id=planned.query_id, query=planned.query,
                    dimension=planned.dimension, generated_by=PLANNER_ID, executed_on=INDEX,
                    timestamp=stamp, outcome=C.QueryOutcome.QUERY_REFUSED,
                    note=f"{type(exc).__name__}: {exc}"))
                print(f"  REFUSED {planned.query_id}: {exc}")
                continue
            try:
                results = search(planned.query, page_size=25)
            except Exception as exc:  # noqa: BLE001 — provider failure is a recorded fact
                outcomes.append(C.QueryOutcomeRecord(
                    gap_id=gap.gap_id, query_id=planned.query_id, query=planned.query,
                    dimension=planned.dimension, generated_by=PLANNER_ID, executed_on=INDEX,
                    timestamp=stamp, outcome=C.QueryOutcome.PROVIDER_UNAVAILABLE,
                    note=f"{type(exc).__name__}: {exc}"))
                print(f"  UNAVAILABLE {planned.query_id}: {type(exc).__name__}")
                continue
            scored = sorted(((relevance(r)[0], r) for r in results), key=lambda pair: -pair[0])
            chosen = [r for score, r in scored if score >= args.min_score][:args.select_top]
            stored = []
            for record in chosen:
                document = _store(directory, record, planned.query)
                documents.setdefault(document.source_id, document)
                stored.append(document.source_id)
            outcomes.append(C.QueryOutcomeRecord(
                gap_id=gap.gap_id, query_id=planned.query_id, query=planned.query,
                dimension=planned.dimension, generated_by=PLANNER_ID, executed_on=INDEX,
                timestamp=stamp,
                outcome=(C.QueryOutcome.RESULTS_RETURNED if results
                         else C.QueryOutcome.SEARCH_RETURNED_ZERO_RESULTS),
                results=len(results), selected=len(stored), source_ids=tuple(sorted(stored)),
                note=("the index returned nothing for this query" if not results else "")))
            print(f"  {gap.gap_id[:28]:28s} {planned.query_id} results={len(results):3d} "
                  f"kept={len(stored)}")

    checks = []
    for pmid in REPO_CITATIONS:
        query = f"EXT_ID:{pmid}"
        try:
            hits = search(check_search_query(query), page_size=1)
        except Exception as exc:  # noqa: BLE001
            checks.append({"citation": f"PMID:{pmid}", "status": "PROVIDER_UNAVAILABLE",
                           "note": f"{type(exc).__name__}: {exc}"})
            continue
        if not hits:
            checks.append({"citation": f"PMID:{pmid}", "status": "NOT_FOUND_IN_INDEX",
                           "note": "the identifier returned no record"})
            continue
        document = _store(directory, hits[0], query)
        documents.setdefault(document.source_id, document)
        checks.append({"citation": f"PMID:{pmid}", "status": "FOUND_IN_INDEX",
                       "title": document.title, "journal": document.journal,
                       "pub_year": document.pub_year, "source_id": document.source_id,
                       "note": "retrieved; whether it supports the claim attributed to it is a "
                               "separate question the grounding layer answers"})
        print(f"  citation PMID:{pmid}: {document.title[:62]}")

    snapshot = C.CorpusSnapshot(
        corpus_version=args.corpus_version, provider_id=PROVIDER_ID,
        provider_version=PROVIDER_VERSION, created_at=utc_now().isoformat(), index=INDEX,
        full_text_policy=FULL_TEXT_POLICY,
        queries=tuple(outcomes),
        documents=tuple(sorted(documents.values(), key=lambda d: d.source_id)),
        citation_checks=tuple(checks))
    manifest = C.save(snapshot, directory)
    print(f"\n{manifest.relative_to(ROOT)}: {len(snapshot.documents)} documents from "
          f"{len(snapshot.queries)} queries ({PLANNER_ID} v{PLANNER_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
