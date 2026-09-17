"""Exomiser native output → Candidate objects.

Reads the structured TSV outputs (TSV_GENE ranks genes per mode of inheritance;
TSV_VARIANT carries the variants, with CONTRIBUTING_VARIANT marking those that
produced the gene's score). The JSON output is preserved as a native artifact but
not parsed: Exomiser documents it as an internal representation with no schema.

Nothing is reranked, rescored or filtered here.
"""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

from rarepipe.stages.baseline.model import Candidate, CandidatePhase, ContributingVariant

COMP_HET_MODELS = ("COMP_HET",)
TRUTHY = {"1", "true", "TRUE", "yes", "Y"}


def _f(row: dict, key: str) -> float | None:
    v = (row.get(key) or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _i(row: dict, key: str) -> int | None:
    v = (row.get(key) or "").strip()
    return int(v) if v.lstrip("-").isdigit() else None


def _s(row: dict, key: str) -> str | None:
    v = (row.get(key) or "").strip()
    return v or None


def variant_ref(contig: str, start: str, ref: str, alt: str) -> str:
    return hashlib.sha256(f"{contig}:{start}:{ref}:{alt}".encode()).hexdigest()[:12]


def read_tsv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{(k or "").strip().lstrip("#"): v for k, v in row.items()} for row in csv.DictReader(fh, delimiter="\t")]


def build_candidates(genes_tsv: Path, variants_tsv: Path) -> list[Candidate]:
    gene_rows = read_tsv(genes_tsv)
    variant_rows = read_tsv(variants_tsv)

    by_gene_moi: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in variant_rows:
        if (row.get("CONTRIBUTING_VARIANT") or "").strip() in TRUTHY:
            by_gene_moi[(row.get("GENE_SYMBOL", ""), row.get("MOI", ""))].append(row)

    candidates: list[Candidate] = []
    for row in gene_rows:
        symbol, moi = row.get("GENE_SYMBOL", ""), row.get("MOI", "")
        rank = _i(row, "RANK")
        if rank is None or not symbol:
            continue
        contributing = [
            ContributingVariant(
                variant_ref=variant_ref(v.get("CONTIG", ""), v.get("START", ""), v.get("REF", ""), v.get("ALT", "")),
                source_filter_status=_s(v, "FILTER") or ".",
                solver_variant_score=_f(v, "EXOMISER_VARIANT_SCORE"),
                functional_class=_s(v, "FUNCTIONAL_CLASS"),
                clinvar_interpretation=_s(v, "CLINVAR_PRIMARY_INTERPRETATION"),
                clinvar_star_rating=_i(v, "CLINVAR_STAR_RATING"),
                max_frequency_percent=_f(v, "MAX_FREQ"),
                max_pathogenicity_score=_f(v, "MAX_PATH"),
                acmg_classification=_s(v, "EXOMISER_ACMG_CLASSIFICATION"),
                contig=_s(v, "CONTIG"), position=_i(v, "START"), ref=_s(v, "REF"), alt=_s(v, "ALT"),
                hgvs=_s(v, "HGVS"), genotype=_s(v, "GENOTYPE"), rs_id=_s(v, "RS_ID"),
            )
            for v in by_gene_moi.get((symbol, moi), [])
        ]
        is_comp_het = any(tag in moi for tag in COMP_HET_MODELS)
        evidence = {k: v for k, v in row.items() if k.endswith("_EVIDENCE") and (v or "").strip()}
        for k in ("HUMAN_PHENO_SCORE", "MOUSE_PHENO_SCORE", "FISH_PHENO_SCORE", "WALKER_SCORE", "OMIM_SCORE", "MATCHES_CANDIDATE_GENE"):
            if (row.get(k) or "").strip():
                evidence[k] = row[k].strip()
        candidates.append(Candidate(
            rank=rank, gene_symbol=symbol, gene_id=_s(row, "ENTREZ_GENE_ID") or _s(row, "ID"), inheritance_model=moi,
            p_value=_f(row, "P-VALUE"), score_combined=_f(row, "EXOMISER_GENE_COMBINED_SCORE"),
            score_phenotype=_f(row, "EXOMISER_GENE_PHENO_SCORE"), score_variant=_f(row, "EXOMISER_GENE_VARIANT_SCORE"),
            contributing_variants=contributing, contributing_variant_count=len(contributing),
            is_variant_pair=is_comp_het and len(contributing) == 2,
            phase=CandidatePhase() if is_comp_het and len(contributing) >= 2 else None,
            any_contributing_variant_non_pass=any(v.source_filter_status not in ("PASS", ".") for v in contributing),
            solver_evidence=evidence,
        ))
    candidates.sort(key=lambda c: (c.rank, c.gene_symbol, c.inheritance_model))
    return candidates


def contigs_in_output(variants_tsv: Path) -> list[str]:
    return sorted({(r.get("CONTIG") or "").strip() for r in read_tsv(variants_tsv) if (r.get("CONTIG") or "").strip()})


def find_outputs(output_dir: Path, prefix: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for suffix, key in ((".genes.tsv", "genes_tsv"), (".variants.tsv", "variants_tsv"), (".json", "json")):
        matches = sorted(output_dir.glob(f"{prefix}*{suffix}"))
        if matches:
            found[key] = matches[0]
    return found
