"""Synthetic Exomiser outputs and a fake solver, so Stage 03's logic is testable offline.

The fake solver reacts to the two things the profile matrix varies — the HPO set and
whether `failedVariantFilter` is present — exactly as a real solver would:

  SYNGENE1  compound-het pair, both variants PASS        → every profile
  SYNGENE2  single variant, AD, PASS                     → every profile
  SYNGENE3  single variant whose FILTER is MQ40          → only when non-PASS permitted
  SYNGENE4  compound-het pair, PASS                      → only with the wider HPO set

Gene symbols are invented. Tests that need the real solver live in
tests/test_baseline_solver.py and are skipped unless one is provisioned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

GENE_COLUMNS = [
    "RANK", "ID", "GENE_SYMBOL", "ENTREZ_GENE_ID", "MOI", "P-VALUE", "EXOMISER_GENE_COMBINED_SCORE",
    "EXOMISER_GENE_PHENO_SCORE", "EXOMISER_GENE_VARIANT_SCORE", "HUMAN_PHENO_SCORE", "MOUSE_PHENO_SCORE",
    "OMIM_SCORE", "MATCHES_CANDIDATE_GENE", "HUMAN_PHENO_EVIDENCE",
]
VARIANT_COLUMNS = [
    "RANK", "ID", "GENE_SYMBOL", "ENTREZ_GENE_ID", "MOI", "P-VALUE", "EXOMISER_GENE_COMBINED_SCORE",
    "EXOMISER_GENE_PHENO_SCORE", "EXOMISER_GENE_VARIANT_SCORE", "EXOMISER_VARIANT_SCORE", "CONTRIBUTING_VARIANT",
    "WHITELIST_VARIANT", "VCF_ID", "RS_ID", "CONTIG", "START", "END", "REF", "ALT", "CHANGE_LENGTH", "QUAL", "FILTER",
    "GENOTYPE", "FUNCTIONAL_CLASS", "HGVS", "EXOMISER_ACMG_CLASSIFICATION", "CLINVAR_PRIMARY_INTERPRETATION",
    "CLINVAR_STAR_RATING", "MAX_FREQ", "MAX_PATH",
]


@dataclass
class SynthGene:
    symbol: str
    entrez: str
    moi: str
    variants: list[tuple[str, int, str, str, str]]  # contig, pos, ref, alt, filter
    combined: float
    pheno: float
    variant_score: float
    requires_non_pass: bool = False
    requires_wide_hpo: bool = False


# Loci deliberately match records in the Stage 02 fixture VCF (normalize_fixtures.RECORDS), so the
# source-FILTER lookup resolves real labels: 1:10010 is LowQual there, everything else is PASS.
SYNTH_GENES = [
    SynthGene("SYNGENE1", "100001", "AUTOSOMAL_RECESSIVE_COMP_HET",
              [("1", 10001, "A", "G", "PASS"), ("1", 10005, "C", "CT", "PASS")], 0.9321, 0.8712, 0.9900),
    SynthGene("SYNGENE2", "100002", "AUTOSOMAL_DOMINANT", [("2", 20000, "G", "A", "PASS")], 0.7412, 0.6103, 0.9500),
    SynthGene("SYNGENE3", "100003", "AUTOSOMAL_DOMINANT", [("1", 10010, "GTA", "G", "LowQual")], 0.6620, 0.5330, 0.9100,
              requires_non_pass=True),
    SynthGene("SYNGENE4", "100004", "AUTOSOMAL_RECESSIVE_COMP_HET",
              [("1", 10020, "AC", "GT", "PASS"), ("1", 10040, "A", "G", "PASS")], 0.5840, 0.7001, 0.8800,
              requires_wide_hpo=True),
]


def _row(columns: list[str], values: dict) -> str:
    return "\t".join(str(values.get(c, "")) for c in columns)


def write_outputs(output_dir: Path, prefix: str, *, non_pass_permitted: bool, wide_hpo: bool) -> None:
    genes = [g for g in SYNTH_GENES if (non_pass_permitted or not g.requires_non_pass) and (wide_hpo or not g.requires_wide_hpo)]
    genes = sorted(genes, key=lambda g: -g.combined)
    gene_lines, variant_lines = ["\t".join(GENE_COLUMNS)], ["\t".join(VARIANT_COLUMNS)]
    for rank, g in enumerate(genes, start=1):
        shared = {"RANK": rank, "ID": f"{g.symbol}_{g.moi}", "GENE_SYMBOL": g.symbol, "ENTREZ_GENE_ID": g.entrez, "MOI": g.moi,
                  "P-VALUE": round(0.001 * rank, 5), "EXOMISER_GENE_COMBINED_SCORE": g.combined,
                  "EXOMISER_GENE_PHENO_SCORE": g.pheno, "EXOMISER_GENE_VARIANT_SCORE": g.variant_score}
        gene_lines.append(_row(GENE_COLUMNS, {**shared, "HUMAN_PHENO_SCORE": g.pheno, "MOUSE_PHENO_SCORE": 0.5,
                                              "OMIM_SCORE": 1.0, "MATCHES_CANDIDATE_GENE": 0,
                                              "HUMAN_PHENO_EVIDENCE": f"synthetic phenotype match for {g.symbol}"}))
        for contig, pos, ref, alt, filt in g.variants:
            variant_lines.append(_row(VARIANT_COLUMNS, {
                **shared, "EXOMISER_VARIANT_SCORE": g.variant_score, "CONTRIBUTING_VARIANT": 1, "WHITELIST_VARIANT": 0,
                "RS_ID": "rs000000", "CONTIG": contig, "START": pos, "END": pos + len(ref) - 1, "REF": ref, "ALT": alt,
                "CHANGE_LENGTH": len(alt) - len(ref), "QUAL": 500.0, "FILTER": filt, "GENOTYPE": "0/1",
                "FUNCTIONAL_CLASS": "missense_variant", "HGVS": f"{g.symbol}:c.100A>G:p.(Lys34Arg)",
                "EXOMISER_ACMG_CLASSIFICATION": "UNCERTAIN_SIGNIFICANCE", "CLINVAR_PRIMARY_INTERPRETATION": "NOT_PROVIDED",
                "CLINVAR_STAR_RATING": 0, "MAX_FREQ": 0.0012, "MAX_PATH": 0.97}))
        # a non-contributing variant, which must never become a contributing one
        variant_lines.append(_row(VARIANT_COLUMNS, {**shared, "EXOMISER_VARIANT_SCORE": 0.1, "CONTRIBUTING_VARIANT": 0,
                                                    "CONTIG": g.variants[0][0], "START": g.variants[0][1] + 5000, "REF": "A", "ALT": "T",
                                                    "FILTER": "PASS", "GENOTYPE": "0/1", "FUNCTIONAL_CLASS": "synonymous_variant"}))
    (output_dir / f"{prefix}.genes.tsv").write_text("\n".join(gene_lines) + "\n")
    (output_dir / f"{prefix}.variants.tsv").write_text("\n".join(variant_lines) + "\n")
    (output_dir / f"{prefix}.json").write_text('{"note": "synthetic native output"}\n')


def fake_run_job(install, *, sample: Path, analysis: Path, output_options: Path, vcf: Path, assembly: str,
                 output_dir: Path, output_prefix: str, properties: Path, log_path: Path, max_heap="7g", timeout_seconds=0):
    """Stand-in for exomiser.run_job: reads the generated documents and writes matching outputs."""
    from rarepipe.stages.baseline.exomiser import RunOutcome

    steps = yaml.safe_load(analysis.read_text())["steps"]
    non_pass_permitted = not any("failedVariantFilter" in s for s in steps)
    ids = [f["type"]["id"] for f in yaml.safe_load(sample.read_text())["phenotypicFeatures"]]
    wide_hpo = "HP:0000007" in ids  # the mode-of-inheritance term, present only in the wider profiles
    output_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(output_dir, output_prefix, non_pass_permitted=non_pass_permitted, wide_hpo=wide_hpo)
    log_path.write_text("synthetic solver run\nProcessed 12 variants\nAnalysis complete\n")
    return RunOutcome(exit_code=0, wall_clock_seconds=1.0, peak_rss_bytes=2_000_000_000, log_path=log_path,
                      out_of_memory=False, rejected_input=False, timed_out=False, tail="Analysis complete")


def failing_run_job(reason: str):
    """Stand-in that fails the way a real solver fails (OOM / rejected input / crash)."""
    from rarepipe.stages.baseline.exomiser import RunOutcome

    texts = {
        "oom": "Exception in thread \"main\" java.lang.OutOfMemoryError: Java heap space\n",
        "rejected": "IllegalArgumentException: Unrecognised contig 'Un_KN707606v1_decoy'\n",
        "crash": "Something else went wrong\n",
    }

    def _run(install, *, log_path: Path, **kw):
        log_path.write_text(texts[reason])
        return RunOutcome(exit_code=1, wall_clock_seconds=5.0, peak_rss_bytes=7_000_000_000, log_path=log_path,
                          out_of_memory=reason == "oom", rejected_input=reason == "rejected", timed_out=False,
                          tail=texts[reason].strip())

    return _run


def fake_installation(tmp_path: Path):
    from rarepipe.stages.baseline.exomiser import Installation

    home = tmp_path / "exomiser"
    (home / "data" / "2602_hg38").mkdir(parents=True, exist_ok=True)
    (home / "data" / "2602_phenotype").mkdir(parents=True, exist_ok=True)
    jar = home / "exomiser-cli-15.1.0.jar"
    jar.write_bytes(b"synthetic jar")
    return Installation(home=home, jar=jar, version="15.1.0", jar_sha256="0" * 64, java=Path("/usr/bin/java"),
                        java_version="openjdk 21.0.6 (synthetic)", data_dir=home / "data",
                        hg38_version="2602", phenotype_version="2602")
