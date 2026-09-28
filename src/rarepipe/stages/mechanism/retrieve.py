"""Corpus acquisition. The only networked part of Stage 06, and it never sees the case.

Queries are gene-, protein- and disease-level. Each one passes the Stage 04 disclosure guard
and a therapy filter before it is sent, so neither the child's variants nor a drug hunt can
leave through this door. Full text is stored only where it is legitimately available; a
paywalled paper is recorded as exactly that.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.adjudicate.disclosure import DisclosureRefused, check_query
from rarepipe.stages.mechanism.model import QueryRecord, RetrievedDocument

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
PMC_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc_number}&retmode=xml"
# Licence language under which PMC permits machine reading. Anything else is not stored.
TEXT_MINING_LICENCES = re.compile(r"text mining|creativecommons|CC BY|open access|open-access", re.I)
UA = {"User-Agent": "rarepipe-mechanism-retrieval"}

# PRD 006 §38-39: agents must not drift into intervention search.
THERAPY_TERMS = re.compile(
    r"\b(drug|drugs|treatment|therapy|therapeutic|therapeutics|repurpos\w*|inhibitor|agonist|antagonist|"
    r"compound screen|small molecule|gene therapy|crispr|mrna (therapy|replacement)|dosing|clinical trial)\b", re.I)

RELEVANCE_TERMS = {
    "patient": 4, "patient-derived": 5, "fibroblast": 4, "lymphoblastoid": 4, "primary cells": 3,
    "mosaic variegated aneuploidy": 4, "premature chromatid separation": 4, "constitutional aneuploidy": 3,
    "checkpoint": 3, "spindle assembly checkpoint": 4, "mitotic checkpoint": 4, "kinetochore": 3,
    "protein level": 3, "protein abundance": 4, "western blot": 3, "immunoblot": 3, "stability": 2,
    "rescue": 4, "complementation": 4, "knockdown": 2, "sirna": 2, "hypomorph": 3,
    "missense": 3, "kinase domain": 4, "kinase activity": 3, "truncating": 3, "nonsense": 2, "frameshift": 2,
    "nonsense-mediated decay": 4, "chromosome missegregation": 3, "chromosome alignment": 3, "aneuploidy": 2,
    "functional": 2, "assay": 2, "mutation": 1,
}
PENALTY_TERMS = {"review": -3, "meta-analysis": -3, "prognosis": -3, "immune infiltration": -4,
                 "expression in cancer": -3, "biomarker": -2, "bioinformatic analysis": -3}


class RetrievalRefused(ValueError):
    pass


def check_search_query(query: str) -> str:
    """Two gates: no case identity out, no intervention search in."""
    check_query(query)
    if THERAPY_TERMS.search(query):
        raise RetrievalRefused(
            f"query looks like intervention search, which Stage 06 must not start: {query!r}")
    return query


def _get(url: str, timeout: int = 90) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as resp:
        return resp.read()


def search(query: str, page_size: int = 25) -> list[dict]:
    params = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": page_size, "resultType": "core"})
    payload = json.loads(_get(f"{SEARCH_URL}?{params}"))
    return payload.get("resultList", {}).get("result", [])


def relevance(record: dict) -> tuple[int, list[str]]:
    """Deterministic triage. Records why a paper was selected, as the PRD requires of any triage."""
    text = f"{record.get('title', '')} {record.get('abstractText', '')}".lower()
    score, reasons = 0, []
    for term, weight in RELEVANCE_TERMS.items():
        if term in text:
            score += weight
            if weight >= 3:
                reasons.append(term)
    for term, weight in PENALTY_TERMS.items():
        if term in text:
            score += weight
    if (record.get("pubType") or "").lower().find("review") >= 0:
        score -= 3
    return score, reasons


def strip_xml(xml: str) -> str:
    body = re.sub(r"<(ref-list|back|front)\b.*?</\1>", " ", xml, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    body = body.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", body).strip()


def fetch_full_text(pmcid: str) -> tuple[str | None, str]:
    """Licensed full text only. No scraping, no paywall circumvention (PRD 006 §19).

    Europe PMC's open-access endpoint first; then NCBI PMC, which serves some articles Europe PMC
    flags as not open access — but only when the article's own licence permits text mining, and the
    licence is recorded in the access note so the permission travels with the text.
    """
    try:
        raw = _get(FULLTEXT_URL.format(pmcid=pmcid)).decode("utf-8", "replace")
        if "<body" in raw:
            return strip_xml(raw), "open-access full text retrieved from Europe PMC"
    except Exception:
        pass
    try:
        raw = _get(PMC_EFETCH_URL.format(pmc_number=pmcid.removeprefix("PMC"))).decode("utf-8", "replace")
    except Exception as exc:
        return None, f"full text not available from Europe PMC or NCBI PMC ({type(exc).__name__})"
    if "<body" not in raw:
        return None, "NCBI PMC returned no article body: full text is not available under a permitting licence"
    licence = re.search(r"<license[^>]*>(.*?)</license>", raw, re.S)
    licence_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", licence.group(1))).strip() if licence else ""
    if not TEXT_MINING_LICENCES.search(licence_text):
        return None, "NCBI PMC full text exists but its licence does not state text-mining permission; not stored"
    return strip_xml(raw), f"full text retrieved from NCBI PMC under its stated licence: {licence_text[:180]}"


@dataclass
class Corpus:
    root: Path
    documents: dict[str, RetrievedDocument] = field(default_factory=dict)
    queries: list[QueryRecord] = field(default_factory=list)

    def doc_dir(self) -> Path:
        d = self.root / "docs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def store(self, record: dict, query: str, task_id: str | None, want_full_text: bool) -> RetrievedDocument:
        pmid = str(record.get("pmid") or record.get("id") or "")
        source_id = f"PMID:{pmid}" if pmid else f"EPMC:{record.get('id')}"
        if source_id in self.documents:
            return self.documents[source_id]
        pmcid = record.get("pmcid")
        text = (record.get("abstractText") or "").strip()
        access = "abstract and metadata only"
        full = False
        if want_full_text and pmcid:
            body, access = fetch_full_text(pmcid)
            if body:
                text = f"{record.get('title', '')}\n\n{text}\n\n{body}"
                full = True
        payload = text or (record.get("title") or "")
        path = self.doc_dir() / f"{source_id.replace(':', '_')}.txt"
        path.write_text(payload)
        doc = RetrievedDocument(
            source_id=source_id, source_type="journal_article", title=(record.get("title") or "").strip(),
            pmid=pmid or None, pmcid=pmcid, doi=record.get("doi"), journal=record.get("journalTitle"),
            pub_year=int(record["pubYear"]) if str(record.get("pubYear", "")).isdigit() else None,
            url=f"https://europepmc.org/article/MED/{pmid}" if pmid else None,
            retrieved_at=utc_now().isoformat(), query=query,
            content_hash="sha256:" + hashlib.sha256(payload.encode()).hexdigest(),
            full_text=full, access_note=access, characters_stored=len(payload),
            is_review="review" in (record.get("pubType") or "").lower(), local_path=str(path))
        self.documents[source_id] = doc
        return doc

    def run_query(self, query: str, task_id: str | None, *, generated_by: str, select_top: int = 6,
                  min_score: int = 4, page_size: int = 25, want_full_text: bool = True,
                  console=None, validator=None) -> list[RetrievedDocument]:
        # Stage 08 supplies its own validator: the therapy filter is lifted there, the
        # case-identity guard never is.
        (validator or check_search_query)(query)
        try:
            results = search(query, page_size=page_size)
        except Exception as exc:
            self.queries.append(QueryRecord(query=query, generated_by=generated_by, executed_on="Europe PMC",
                                            timestamp=utc_now().isoformat(), results=0, selected=0,
                                            knowledge_task=task_id, rejection_reason=f"{type(exc).__name__}: {exc}"))
            if console:
                console.warn(f"query failed: {query} ({type(exc).__name__})")
            return []
        scored = sorted(((relevance(r)[0], r) for r in results), key=lambda x: -x[0])
        chosen = [r for score, r in scored if score >= min_score][:select_top]
        if not chosen and scored:  # an identifier query returns one record with no keyword density
            chosen = [r for _, r in scored[:1]] if query.startswith("EXT_ID:") else []
        stored = [self.store(r, query, task_id, want_full_text) for r in chosen]
        self.queries.append(QueryRecord(query=query, generated_by=generated_by, executed_on="Europe PMC",
                                        timestamp=utc_now().isoformat(), results=len(results), selected=len(stored),
                                        knowledge_task=task_id, rejected=len(results) - len(stored),
                                        rejection_reason="below relevance threshold" if len(results) > len(stored) else None))
        if console:
            full = sum(1 for d in stored if d.full_text)
            console.info(f"{query[:58]:60} {len(results):3} hits → {len(stored)} kept ({full} full text)")
        time.sleep(0.34)  # be a good citizen of a public API
        return stored
