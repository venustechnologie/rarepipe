"""Approval verification against a regulator's approvals database.

The first version of this module inferred approval from the openFDA NDC Directory and was wrong.
The FDA says plainly that inclusion in that directory does not indicate approval, and the bug proved
it: an ingredient was marked approved on the strength of an `UNAPPROVED HOMEOPATHIC` listing whose
sampled indications were multivitamins and "Circulation Drops".

The rule now:

    Drugs@FDA application with an approved submission  →  approval evidence
    NDC Directory presence                             →  identity and marketing evidence only

It fails closed. An ingredient with a thousand marketed products and no approved application is
`verified: false`, and the record says why. Jurisdiction is preserved: only the US is queried, and
absence here is never evidence of non-approval elsewhere.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.discovery.model import ApprovalRecord

RXNORM = "https://rxnav.nlm.nih.gov/REST/rxcui.json?name={name}&search=1"
RXNORM_NAME = "https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
DRUGSFDA = 'https://api.fda.gov/drug/drugsfda.json?search=openfda.generic_name:"{name}"&limit=20'
OPENFDA_NDC = 'https://api.fda.gov/drug/ndc.json?search=active_ingredients.name:"{name}"&limit=5'
UA = {"User-Agent": "rarepipe-approval-verification"}

# Application prefixes that represent an FDA approval decision.
APPROVED_PREFIXES = ("NDA", "ANDA", "BLA")
# Categories that are explicitly NOT approvals, listed so the failure mode is visible in the record.
NON_APPROVAL_CATEGORIES = ("UNAPPROVED", "OTC MONOGRAPH", "DIETARY SUPPLEMENT", "HOMEOPATHIC", "EXPORT ONLY")
UNVERIFIED_ELSEWHERE = ("Only the US regulator was queried. Absence here is not evidence that the ingredient is "
                        "unapproved in other jurisdictions; it means non-US approval is unverified.")


def _get(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as resp:
        return json.load(resp)


def name_variants(ingredient: str, rxcui: str | None) -> list[str]:
    """Names to try against the approvals database, resolved by an authority rather than guessed.

    A regulator indexes its own generic name — "NIACIN" — while the literature says "nicotinic acid".
    RxNorm is the arbiter of that equivalence, so the synonym comes from RxNorm, not from an
    assistant's recollection of chemistry.
    """
    variants = [ingredient.strip()]
    base = re.sub(r"\s*\(.*?\)\s*", " ", ingredient).strip()
    if base and base not in variants:
        variants.append(base)
    for inner in re.findall(r"\(([^)]+)\)", ingredient):
        if inner.strip() and inner.strip() not in variants:
            variants.append(inner.strip())
    if rxcui:
        try:
            canonical = (_get(RXNORM_NAME.format(rxcui=rxcui)).get("properties") or {}).get("name")
            if canonical and canonical not in variants:
                variants.append(canonical)
        except Exception:
            pass
    return variants


def verify(ingredient: str, *, cache_dir: Path | None = None) -> ApprovalRecord:
    """Does a regulator's approvals database contain an approved application for this ingredient?"""
    name = ingredient.strip()
    cache_path = (cache_dir / f"{name.lower().replace(' ', '_').replace('/', '_')}.json") if cache_dir else None
    if cache_path and cache_path.exists():
        return ApprovalRecord(**json.loads(cache_path.read_text()))

    record = ApprovalRecord(
        ingredient=name, retrieved_at=utc_now().isoformat(),
        query=f'Drugs@FDA openfda.generic_name="{name}"; NDC active_ingredients.name="{name}"; RxNorm name={name}',
        note=UNVERIFIED_ELSEWHERE)

    try:
        rx = _get(RXNORM.format(name=urllib.parse.quote(name)))
        rxcuis = (rx.get("idGroup") or {}).get("rxnormId") or []
        if rxcuis:
            record.identifiers["rxcui"] = rxcuis[0]
    except Exception as exc:
        record.note += f" RxNorm lookup failed ({type(exc).__name__})."

    # ── approval evidence: an approved application, and nothing less ────────
    tried: list[str] = []
    for candidate in name_variants(name, record.identifiers.get("rxcui")):
        tried.append(candidate)
        try:
            payload = _get(DRUGSFDA.format(name=urllib.parse.quote(candidate)))
        except Exception:
            continue
        if payload.get("results"):
            record.identifiers["approvals_queried_as"] = candidate
            break
    else:
        payload = {}
    record.query += f"; Drugs@FDA name variants tried: {', '.join(tried)}"
    try:
        for result in payload.get("results", []):
            number = str(result.get("application_number", ""))
            if not number.startswith(APPROVED_PREFIXES):
                continue
            approved = [s for s in result.get("submissions", []) if s.get("submission_status") == "AP"]
            if not approved:
                continue
            products = [{"brand_name": p.get("brand_name"), "dosage_form": p.get("dosage_form"),
                         "marketing_status": p.get("marketing_status"), "route": p.get("route")}
                        for p in result.get("products", [])[:4]]
            record.applications.append({
                "application_number": number, "sponsor": result.get("sponsor_name"),
                "earliest_approval": min((s.get("submission_status_date", "") for s in approved), default=None),
                "approved_submissions": len(approved), "products": products})
        if record.applications:
            record.verified = True
            record.jurisdictions = ["US"]
            record.authority_source = "Drugs@FDA (US FDA approvals database)"
            first = sorted(record.applications, key=lambda a: a.get("earliest_approval") or "9999")[0]
            record.approval_basis = (f"{first['application_number']} ({first.get('sponsor')}), approved "
                                     f"{first.get('earliest_approval')}")
            record.identifiers["application_number"] = first["application_number"]
            record.canonical_ingredient = next(
                (p["brand_name"] for a in record.applications for p in a["products"] if p.get("brand_name")), name)
            record.indications_sampled = sorted({p.get("dosage_form") or "" for a in record.applications
                                                 for p in a["products"] if p.get("dosage_form")})[:5]
        else:
            record.note = ("No approved application for this active ingredient was found in Drugs@FDA. " +
                           UNVERIFIED_ELSEWHERE)
    except Exception:
        record.note = ("Drugs@FDA returned no approved application for this active ingredient. " +
                       UNVERIFIED_ELSEWHERE)

    # ── identity evidence only: marketed products, never approval ──────────
    try:
        ndc = _get(OPENFDA_NDC.format(name=urllib.parse.quote(name.upper())))
        results = ndc.get("results") or []
        categories = sorted({r.get("marketing_category", "") for r in results})
        record.marketed_products_identity = {
            "source": "openFDA NDC Directory",
            "total_products": (ndc.get("meta") or {}).get("results", {}).get("total"),
            "marketing_categories_sampled": categories,
            "non_approval_categories_present": [c for c in categories
                                                if any(bad in c.upper() for bad in NON_APPROVAL_CATEGORIES)],
            "note": ("Directory presence establishes that products exist and are marketed. The FDA states that "
                     "inclusion does not indicate approval, so this can never set `verified`.")}
    except Exception:
        record.marketed_products_identity = {"source": "openFDA NDC Directory", "total_products": 0,
                                             "note": "no marketed product found; this is identity evidence only"}

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(record.model_dump(mode="json"), indent=1) + "\n")
    return record
