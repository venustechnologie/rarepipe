"""The frozen rule that turns Stage 03 output into rows 2–10.

Row 1 is the adjudicated hypothesis. The rest are not re-investigated: they are read off
the baseline in a way that is deterministic, documented, and reproducible, using the
stability information Stage 03 already produced rather than a new ranker invented here.
"""

from __future__ import annotations

import re
from typing import Any

from rarepipe.stages.baseline.ingest import RECESSIVE_MODELS

CHROM_ORDER = {**{str(i): i for i in range(1, 23)}, "X": 23, "Y": 24, "M": 25, "MT": 25}

SELECTION_STEPS = [
    "Take every candidate configuration reported by any of the four Stage 03 analysis profiles.",
    "Reduce each candidate to the variants the submission format can carry: a recessive candidate with two or "
    "more contributing heterozygous variants becomes a pair (the two highest solver variant scores); every "
    "other candidate becomes its single highest-scoring variant.",
    "Key each configuration by its variant set, so the same configuration found under several profiles, "
    "inheritance models or ranks collapses to one row.",
    "Drop any configuration that is a subset of one already emitted — a single allele of a pair we have "
    "already submitted is not an independent hypothesis, and it cannot earn a point the pair does not "
    "already earn, so the row is better spent on a different candidate.",
    "Order by robustness across profiles: number of profiles reporting the configuration (descending), then "
    "best rank achieved in any profile (ascending), then mean rank across the profiles reporting it (ascending).",
    "Emit the top 9.",
]
TIE_BREAKS = [
    "gene symbol, alphabetically",
    "genomic coordinate of the first allele (chromosome order, then position, then REF, then ALT)",
]


def ucsc_contig(name: str, alias_map: dict[str, str] | None = None) -> str:
    """The evaluator compares chromosome strings literally, and its template is chr-prefixed."""
    n = name.strip()
    if n.startswith("chr"):
        return "chrM" if n in ("chrMT",) else n
    if n in ("MT", "M"):
        return "chrM"
    if re.fullmatch(r"\d{1,2}|X|Y", n):
        return f"chr{n}"
    if alias_map and n in alias_map:
        return ucsc_contig(alias_map[n])
    raise ValueError(f"cannot express contig {name!r} in the UCSC-style naming the evaluator expects")


def coordinate_key(v: dict[str, Any]) -> tuple:
    c = str(v.get("chrom") or v.get("contig") or "")
    c = c[3:] if c.startswith("chr") else c
    return (CHROM_ORDER.get(c, 99), c, int(v.get("pos") or v.get("position") or 0),
            str(v.get("ref") or ""), str(v.get("alt") or ""))


def _emitted_variants(cand: dict, alias_map: dict[str, str] | None) -> tuple[list[dict], int]:
    """The variants this candidate contributes to a submission row, and how many were dropped."""
    variants = [v for v in cand.get("contributing_variants", []) if v.get("contig") and v.get("position")]
    if not variants:
        return [], 0
    recessive = cand.get("inheritance_model") in RECESSIVE_MODELS or cand.get("is_variant_pair")
    ordered = sorted(variants, key=lambda v: (-(v.get("solver_variant_score") or 0.0), coordinate_key(v)))
    keep = ordered[:2] if (recessive and len(ordered) >= 2) else ordered[:1]
    out = []
    for v in keep:
        out.append({"chrom": ucsc_contig(v["contig"], alias_map), "pos": int(v["position"]),
                    "ref": (v.get("ref") or "").upper(), "alt": (v.get("alt") or "").upper(),
                    "source_contig": v["contig"], "hgvs": v.get("hgvs"),
                    "solver_variant_score": v.get("solver_variant_score"),
                    "functional_class": v.get("functional_class")})
    return sorted(out, key=coordinate_key), len(variants) - len(keep)


def configuration_key(variants: list[dict]) -> frozenset:
    return frozenset((v["chrom"], v["pos"], v["ref"], v["alt"]) for v in variants)


def rank_configurations(raw_candidate_set: dict, exclude: frozenset, alias_map: dict[str, str] | None = None) -> list[dict]:
    """Every distinct configuration the baseline proposed, ordered by the frozen rule above."""
    seen: dict[frozenset, dict] = {}
    considered = 0
    for result in raw_candidate_set.get("results", []):
        profile = result.get("profile_id")
        if result.get("status") != "COMPLETED" and not result.get("candidates"):
            continue
        for cand in result.get("candidates", []):
            variants, dropped = _emitted_variants(cand, alias_map)
            if not variants:
                continue
            considered += 1
            key = configuration_key(variants)
            if key == exclude:
                continue
            entry = seen.setdefault(key, {
                "variants": variants, "gene_symbol": cand.get("gene_symbol"),
                "inheritance_model": cand.get("inheritance_model"), "profiles": [], "ranks": [],
                "variants_dropped": dropped,
                "configuration": "candidate_compound_heterozygous" if len(variants) == 2 else "single_variant",
            })
            if profile not in entry["profiles"]:
                entry["profiles"].append(profile)
            entry["ranks"].append(int(cand.get("rank", 10**6)))

    ordered = sorted(
        seen.values(),
        key=lambda e: (-len(e["profiles"]), min(e["ranks"]), sum(e["ranks"]) / len(e["ranks"]),
                       e["gene_symbol"] or "", coordinate_key(e["variants"][0])),
    )
    for e in ordered:
        e["best_profile_rank"] = min(e["ranks"])
        e["profiles"] = sorted(e["profiles"])
    return [dict(e, considered=considered) for e in ordered]
