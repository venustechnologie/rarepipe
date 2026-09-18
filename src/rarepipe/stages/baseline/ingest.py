"""Exomiser native output → Candidate objects.

One correction learned from the real solver: Exomiser's TSV `FILTER` column reports
*its own* filter status (always PASS for a surviving variant), not the source VCF's
FILTER field. Taking it at face value would relabel an MQ40 variant as PASS. The
source label is therefore read back from the source VCF at that exact locus.


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

import pysam

pysam.set_verbosity(0)

from rarepipe.stages.baseline.model import Candidate, CandidatePhase, ContributingVariant

# Exomiser's TSV writes the mode of inheritance abbreviated (AD/AR/XD/XR/MT), not the long
# AUTOSOMAL_RECESSIVE_COMP_HET form used in analysis configuration. A recessive candidate carrying
# exactly two heterozygous contributing variants IS the compound-heterozygous configuration; looking
# for "COMP_HET" in this column finds nothing and silently reports zero pairs.
RECESSIVE_MODELS = {"AR", "XR", "AUTOSOMAL_RECESSIVE_COMP_HET", "X_RECESSIVE_COMP_HET",
                    "AUTOSOMAL_RECESSIVE_HOM_ALT", "X_RECESSIVE_HOM_ALT"}
HETEROZYGOUS_GENOTYPES = {"0/1", "1/0", "0|1", "1|0"}
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


class SourceFilterLookup:
    """FILTER as it stands in the source VCF, by exact locus+alleles. Targeted tabix fetches only."""

    def __init__(self, vcf_path: Path | None):
        self._vcf = None
        self._cache: dict[tuple, str] = {}
        if vcf_path and Path(vcf_path).is_file():
            try:
                self._vcf = pysam.VariantFile(str(vcf_path))
            except (OSError, ValueError):
                self._vcf = None

    def _names(self, contig: str) -> list[str]:
        return [contig, contig[3:] if contig.startswith("chr") else f"chr{contig}"]

    def get(self, contig: str, pos: int, ref: str, alt: str) -> str:
        key = (contig, pos, ref, alt)
        if key in self._cache:
            return self._cache[key]
        label = "unknown"
        if self._vcf and pos:
            for name in self._names(contig):
                try:
                    for rec in self._vcf.fetch(name, max(pos - 1, 0), pos):
                        if rec.pos == pos and rec.ref == ref and alt in (rec.alts or ()):
                            label = ";".join(rec.filter.keys()) or "."
                            break
                    else:
                        continue
                    break
                except (ValueError, OSError):
                    continue
        self._cache[key] = label
        return label

    def close(self) -> None:
        if self._vcf:
            self._vcf.close()


def build_candidates(genes_tsv: Path, variants_tsv: Path, source_vcf: Path | None = None) -> list[Candidate]:
    gene_rows = read_tsv(genes_tsv)
    variant_rows = read_tsv(variants_tsv)
    source_filters = SourceFilterLookup(source_vcf)

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
                source_filter_status=source_filters.get(_s(v, "CONTIG") or "", _i(v, "START") or 0, _s(v, "REF") or "", _s(v, "ALT") or ""),
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
        recessive = moi.strip().upper() in RECESSIVE_MODELS
        het_genotypes = [v.genotype for v in contributing if (v.genotype or "").strip() in HETEROZYGOUS_GENOTYPES]
        is_comp_het_configuration = recessive and len(contributing) == 2 and len(het_genotypes) == 2
        evidence = {k: v for k, v in row.items() if k.endswith("_EVIDENCE") and (v or "").strip()}
        for k in ("HUMAN_PHENO_SCORE", "MOUSE_PHENO_SCORE", "FISH_PHENO_SCORE", "WALKER_SCORE", "OMIM_SCORE", "MATCHES_CANDIDATE_GENE"):
            if (row.get(k) or "").strip():
                evidence[k] = row[k].strip()
        candidates.append(Candidate(
            rank=rank, gene_symbol=symbol, gene_id=_s(row, "ENTREZ_GENE_ID") or _s(row, "ID"), inheritance_model=moi,
            p_value=_f(row, "P-VALUE"), score_combined=_f(row, "EXOMISER_GENE_COMBINED_SCORE"),
            score_phenotype=_f(row, "EXOMISER_GENE_PHENO_SCORE"), score_variant=_f(row, "EXOMISER_GENE_VARIANT_SCORE"),
            contributing_variants=contributing, contributing_variant_count=len(contributing),
            is_variant_pair=is_comp_het_configuration,
            phase=CandidatePhase() if recessive and len(contributing) >= 2 else None,
            any_contributing_variant_non_pass=any(v.source_filter_status not in ("PASS", ".") for v in contributing),
            solver_evidence=evidence,
        ))
    candidates.sort(key=lambda c: (c.rank, c.gene_symbol, c.inheritance_model))
    source_filters.close()
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
