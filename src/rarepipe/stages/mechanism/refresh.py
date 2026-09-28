"""Stage 06F — reopen the frozen corpus as a new run and recover evidence it could not reach.

The frozen corpus is never modified. This builds a sibling run that copies it, re-attempts full text
for every document stored as abstract only, attempts listed supplementary files, and records — per
document — what became available, what did not, and why. "Still unavailable" is a recorded state, not
a silent gap, and bot-detection pages are recorded as exactly that: never solved, never bypassed.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from pydantic import BaseModel, Field

from rarepipe.core.artifacts import RunDirectory, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.stages.mechanism.retrieve import PMC_EFETCH_URL, UA, _get, fetch_full_text

SUPPLEMENT_URL = "https://pmc.ncbi.nlm.nih.gov/articles/instance/{pmc_number}/bin/{href}"
CHALLENGE = re.compile(r"recaptcha|captcha|challenge", re.I)


class SupplementRecord(BaseModel):
    href: str
    label: str = ""
    state: str = Field(description="retrieved | inaccessible_bot_challenge | inaccessible | not_parsable")
    note: str = ""
    characters: int = 0
    content_hash: str | None = None


class RefreshRecord(BaseModel):
    """What happened to one document when we tried again."""

    source_id: str
    pmcid: str | None = None
    before: str = "abstract_only"
    after: str = Field(description="full_text_recovered | still_abstract_only | no_pmcid")
    reason: str = ""
    characters_before: int = 0
    characters_after: int = 0
    content_hash_after: str | None = None
    retrieved_at: str
    supplements: list[SupplementRecord] = Field(default_factory=list)


def _supplements(pmcid: str, xml: str, docs_dir: Path, source_id: str) -> list[SupplementRecord]:
    out: list[SupplementRecord] = []
    for i, match in enumerate(re.finditer(r"<supplementary-material[^>]*>(.*?)</supplementary-material>", xml, re.S), 1):
        href = re.search(r'xlink:href="([^"]+)"', match.group(0))
        if not href:
            continue
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip()[:120]
        url = SUPPLEMENT_URL.format(pmc_number=pmcid.removeprefix("PMC"), href=href.group(1))
        try:
            raw = _get(url)
        except Exception as exc:
            out.append(SupplementRecord(href=href.group(1), label=label, state="inaccessible",
                                        note=f"{type(exc).__name__}"))
            continue
        if not raw.startswith(b"%PDF"):
            head = raw[:4000].decode("utf-8", "replace")
            state = "inaccessible_bot_challenge" if CHALLENGE.search(head) else "inaccessible"
            note = ("the repository answered with a bot-detection challenge instead of the file. It was not "
                    "solved or bypassed; a person can download the file and place it in the workspace"
                    if state == "inaccessible_bot_challenge" else "the response was not the file")
            out.append(SupplementRecord(href=href.group(1), label=label, state=state, note=note))
            continue
        try:
            import io

            from pypdf import PdfReader

            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
        except Exception as exc:
            out.append(SupplementRecord(href=href.group(1), label=label, state="not_parsable",
                                        note=type(exc).__name__))
            continue
        path = docs_dir / f"{source_id.replace(':', '_')}__supp{i}.txt"
        path.write_text(text)
        out.append(SupplementRecord(href=href.group(1), label=label, state="retrieved", characters=len(text),
                                    content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest()))
    return out


def ingest_local_supplement(corpus_run: Path, source_id: str, pdf_path: Path, label: str = "") -> SupplementRecord:
    """For files a person fetched by hand — the legitimate route past a bot challenge."""
    import io

    from pypdf import PdfReader

    raw = pdf_path.read_bytes()
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    existing = sorted((corpus_run / "docs").glob(f"{source_id.replace(':', '_')}__supp*.txt"))
    path = corpus_run / "docs" / f"{source_id.replace(':', '_')}__supp{len(existing) + 1}.txt"
    path.write_text(text)
    return SupplementRecord(href=pdf_path.name, label=label or "supplied by a person", state="retrieved",
                            note=f"ingested from a local file supplied by a person ({pdf_path.name})",
                            characters=len(text),
                            content_hash="sha256:" + hashlib.sha256(raw).hexdigest())


def refresh(frozen_corpus: Path, output: Path, console: Console | None = None,
            supplied: dict[str, list[Path]] | None = None) -> Path:
    """``supplied`` maps a source id to supplement files a person downloaded by hand."""
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)
    index = json.loads((frozen_corpus / "corpus_index.json").read_text())
    run = RunDirectory(output, run_id).open()
    docs_dir = run.staging / "docs"
    shutil.copytree(frozen_corpus / "docs", docs_dir)
    for junk in docs_dir.glob("._*"):
        junk.unlink()

    records: list[RefreshRecord] = []
    targets = [d for d in index["documents"] if not d["full_text"]]
    console.step(1, 2, f"Re-attempting full text for {len(targets)} abstract-only document(s)...")
    for doc in targets:
        stored = docs_dir / f"{doc['source_id'].replace(':', '_')}.txt"
        before = stored.read_text() if stored.exists() else ""
        now = utc_now().isoformat()
        if not doc.get("pmcid"):
            records.append(RefreshRecord(source_id=doc["source_id"], after="no_pmcid", retrieved_at=now,
                                         reason="no PMC identifier: no licensed full-text route exists for it",
                                         characters_before=len(before), characters_after=len(before)))
            console.info(f"{doc['source_id']:16} no PMCID")
            continue
        body, note = fetch_full_text(doc["pmcid"])
        if not body:
            records.append(RefreshRecord(source_id=doc["source_id"], pmcid=doc["pmcid"], after="still_abstract_only",
                                         reason=note, retrieved_at=now, characters_before=len(before),
                                         characters_after=len(before)))
            console.info(f"{doc['source_id']:16} still abstract only — {note[:70]}")
            continue
        text = f"{doc.get('title', '')}\n\n{before}\n\n{body}"
        stored.write_text(text)
        doc["full_text"] = True
        doc["access_note"] = note
        doc["characters_stored"] = len(text)
        doc["content_hash"] = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        supplements = []
        try:
            xml = _get(PMC_EFETCH_URL.format(pmc_number=doc["pmcid"].removeprefix("PMC"))).decode("utf-8", "replace")
            supplements = _supplements(doc["pmcid"], xml, docs_dir, doc["source_id"])
        except Exception:
            pass
        records.append(RefreshRecord(source_id=doc["source_id"], pmcid=doc["pmcid"], after="full_text_recovered",
                                     reason=note, retrieved_at=now, characters_before=len(before),
                                     characters_after=len(text), content_hash_after=doc["content_hash"],
                                     supplements=supplements))
        console.ok(f"{doc['source_id']:16} recovered {len(text):,} chars; "
                   f"{len(supplements)} supplement(s): {', '.join(s.state for s in supplements) or 'none listed'}")

    for source_id, paths in (supplied or {}).items():
        record = next((r for r in records if r.source_id == source_id), None)
        if record is None:
            record = RefreshRecord(source_id=source_id, before="full_text", after="full_text_recovered",
                                   reason="unchanged; supplement supplied by a person", retrieved_at=utc_now().isoformat())
            records.append(record)
        for pdf in paths:
            supp = ingest_local_supplement(run.staging, source_id, pdf)
            blocked = next((s for s in record.supplements if s.href == pdf.name and s.state != "retrieved"), None)
            if blocked:
                record.supplements.remove(blocked)
                supp.note += f"; the automated attempt had been: {blocked.state}"
            record.supplements.append(supp)
            console.ok(f"{source_id:16} supplement {pdf.name}: {supp.characters:,} chars, supplied by a person")

    console.step(2, 2, "Writing the refreshed corpus...")
    index["refreshed_from"] = {"corpus_run": frozen_corpus.name, "corpus_digest": index.get("corpus_digest")}
    index["refresh"] = [r.model_dump(mode="json") for r in records]
    index["created_at"] = started.isoformat()
    index["corpus_digest"] = "sha256:" + hashlib.sha256(json.dumps(
        {"documents": sorted(d["content_hash"] for d in index["documents"])}, sort_keys=True).encode()).hexdigest()
    run.write_text("corpus_index.json", json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    recovered = sum(1 for r in records if r.after == "full_text_recovered")
    console.ok(f"run {run_id}: {recovered} of {len(records)} recovered in {time.monotonic() - t0:.0f}s")
    run.write_text("refresh.log", "\n".join(console.log_lines) + "\n")
    return run.seal()
