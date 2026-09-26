"""Approval verification against regulators' own data.

A candidate does not survive because a paper, a database or an assistant called it "a drug". It
survives because a regulator's own record says an active ingredient is marketed, and that record is
fetched, timestamped and stored.

Two public authorities are used: RxNorm (US NLM) to normalise the ingredient and give it a stable
identifier, and the openFDA NDC directory to establish that finished human drug products carrying
that ingredient are actually marketed in the US.

The jurisdiction is preserved rather than assumed away. "Not found in the US directory" means
exactly that — it is not evidence that something is unapproved in the EU, Japan or anywhere else,
and the record says so in its own note field.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.discovery.model import ApprovalRecord

RXNORM = "https://rxnav.nlm.nih.gov/REST/rxcui.json?name={name}&search=1"
OPENFDA_NDC = 'https://api.fda.gov/drug/ndc.json?search=active_ingredients.name:"{name}"&limit=5'
UA = {"User-Agent": "rarepipe-approval-verification"}
UNVERIFIED_ELSEWHERE = ("Only the US directory was queried. Absence here is not evidence that the ingredient is "
                        "unapproved in other jurisdictions; it means non-US approval is unverified.")


def _get(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as resp:
        return json.load(resp)


def verify(ingredient: str, *, cache_dir: Path | None = None) -> ApprovalRecord:
    """Is this active ingredient marketed, by whose authority, and where?"""
    name = ingredient.strip()
    cache_path = (cache_dir / f"{name.lower().replace(' ', '_')}.json") if cache_dir else None
    if cache_path and cache_path.exists():
        return ApprovalRecord(**json.loads(cache_path.read_text()))

    record = ApprovalRecord(ingredient=name, retrieved_at=utc_now().isoformat(),
                            query=f'RxNorm name={name}; openFDA active_ingredients.name="{name}"',
                            note=UNVERIFIED_ELSEWHERE)
    try:
        rx = _get(RXNORM.format(name=urllib.parse.quote(name)))
        rxcuis = (rx.get("idGroup") or {}).get("rxnormId") or []
        if rxcuis:
            record.identifiers["rxcui"] = rxcuis[0]
    except Exception as exc:
        record.note += f" RxNorm lookup failed ({type(exc).__name__})."

    try:
        ndc = _get(OPENFDA_NDC.format(name=urllib.parse.quote(name.upper())))
        results = ndc.get("results") or []
        finished = [r for r in results if r.get("finished") and "HUMAN" in (r.get("product_type") or "")]
        if finished:
            record.verified = True
            record.jurisdictions = ["US"]
            record.authority_source = "openFDA NDC directory (US FDA)"
            record.identifiers["marketing_category"] = finished[0].get("marketing_category", "")
            if finished[0].get("application_number"):
                record.identifiers["application_number"] = finished[0]["application_number"]
            record.indications_sampled = sorted({r.get("generic_name", "") for r in finished})[:5]
            total = (ndc.get("meta") or {}).get("results", {}).get("total")
            if total:
                record.identifiers["us_products"] = str(total)
    except Exception:
        # openFDA answers 404 for "no match", which is the answer, not a failure.
        record.note = ("No finished human drug product carrying this active ingredient was found in the US NDC "
                       "directory. " + UNVERIFIED_ELSEWHERE)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(record.model_dump(mode="json"), indent=1) + "\n")
    return record
