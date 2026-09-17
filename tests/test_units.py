"""Unit tests: build determination, format sniffing, HPO parsing, schema contract."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from rarepipe.stages.intake import formats, phenotype
from rarepipe.stages.intake.manifest import CaseManifest, Contig, Format, GenomeBuild
from rarepipe.stages.intake.reference import BUILD_LENGTHS, determine_build
from rarepipe.stages.intake.schema import schema_json

ROOT = Path(__file__).resolve().parents[1]


def contigs(build, prefix="chr", keys=("1", "2", "3", "X")):
    return [Contig(name=f"{prefix}{k}", length=BUILD_LENGTHS[build][k]) for k in keys]


# ── genome build ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("build", [GenomeBuild.GRCH37, GenomeBuild.GRCH38, GenomeBuild.T2T_CHM13])
def test_length_fingerprint_high_confidence(build):
    call = determine_build(contigs(build))
    assert (call.value, call.confidence.value) == (build, "high")


def test_numeric_grch37_with_hs37d5_is_decoy_flavour():
    call = determine_build(contigs(GenomeBuild.GRCH37, prefix="") + [Contig(name="hs37d5", length=35477943)])
    assert call.value == GenomeBuild.GRCH37_DECOY
    assert call.naming_convention.value == "numeric"


def test_hg19_chrM_marker():
    call = determine_build(contigs(GenomeBuild.GRCH37) + [Contig(name="chrM", length=16571)])
    assert call.value == GenomeBuild.GRCH37 and "hg19_style_chrM_16571" in call.markers


def test_names_without_lengths_are_unknown_even_with_chr_prefix():
    call = determine_build([Contig(name="chr1"), Contig(name="chr2")])
    assert (call.value, call.confidence.value) == (GenomeBuild.UNKNOWN, "insufficient")


def test_claim_without_lengths_is_low_confidence():
    call = determine_build([Contig(name="chr1")], [("##reference", "file:///refs/Homo_sapiens_assembly38.fasta")])
    assert (call.value, call.confidence.value) == (GenomeBuild.GRCH38, "low")
    assert all("/refs/" not in e for e in call.evidence)  # raw claim (a path) is never echoed


def test_claim_contradicting_lengths_is_flagged():
    call = determine_build(contigs(GenomeBuild.GRCH38), [("##reference", "hg19.fa")])
    assert call.value == GenomeBuild.GRCH38 and call.claim_conflict and call.confidence.value == "medium"


def test_few_contigs_is_medium():
    call = determine_build(contigs(GenomeBuild.GRCH38, keys=("1",)))
    assert (call.value, call.confidence.value) == (GenomeBuild.GRCH38, "medium")


def test_mixed_lengths_are_custom_not_forced():
    mixed = contigs(GenomeBuild.GRCH38, keys=("1", "2")) + contigs(GenomeBuild.GRCH37, keys=("3", "X"))
    assert determine_build(mixed).value == GenomeBuild.CUSTOM


def test_refseq_accession_names_fingerprint_by_length_at_medium():
    acc = [Contig(name=f"NC_0000{i:02d}.11", length=BUILD_LENGTHS[GenomeBuild.GRCH38][str(i)]) for i in (1, 2, 3, 4)]
    call = determine_build(acc)
    assert (call.value, call.confidence.value) == (GenomeBuild.GRCH38, "medium")


# ── formats ──────────────────────────────────────────────────────────────────


def test_plain_gzip_vcf_is_not_bgzf(tmp_path):
    p = tmp_path / "x.vcf.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
    s = formats.sniff(p, Format.VCF)
    assert (s.format, s.compression.value) == (Format.VCF, "gzip")


def test_text_named_bam_is_mismatch(tmp_path):
    p = tmp_path / "x.bam"
    p.write_text("not a bam\n")
    s = formats.sniff(p, formats.extension_format(p.name))
    assert s.format == Format.TEXT and formats.is_mismatch(Format.BAM, s.format)


def test_txt_holding_tsv_is_not_mismatch():
    assert not formats.is_mismatch(Format.TEXT, Format.TSV)


def test_empty_file(tmp_path):
    p = tmp_path / "empty.vcf"
    p.write_bytes(b"")
    assert formats.sniff(p, Format.VCF).format == Format.EMPTY


# ── phenotype ────────────────────────────────────────────────────────────────


def test_tsv_with_excluded_column(tmp_path):
    p = tmp_path / "hpo.tsv"
    p.write_text("hpo_id\tlabel\texcluded\nHP:0001250\tSeizure\tfalse\nHP:0001263\tDelay\ttrue\nHP:0000252\tMicro\t\n")
    assert phenotype.looks_like_phenotype(p, Format.TSV)
    md, _ = phenotype.inspect_phenotype(p, "A", Format.TSV)
    assert (md.observed_count, md.excluded_count, md.polarity_unspecified_count) == (1, 1, 1)


def test_not_prefix_marks_excluded_but_bullet_does_not(tmp_path):
    p = tmp_path / "hpo.txt"
    p.write_text("- HP:0001250\nNOT HP:0001263\n")
    md, _ = phenotype.inspect_phenotype(p, "A", Format.TEXT)
    assert (md.excluded_count, md.polarity_unspecified_count) == (1, 1)


def test_readme_mentioning_one_term_is_not_a_phenotype_file(tmp_path):
    p = tmp_path / "README.txt"
    p.write_text("This dataset\ncontains a child's genome.\nPhenotypes use HPO, e.g. HP:0001250.\nSee the portal.\n")
    assert not phenotype.looks_like_phenotype(p, Format.TEXT)


# ── schema contract ──────────────────────────────────────────────────────────


def test_committed_schema_matches_code():
    committed = (ROOT / "schemas" / "case_manifest.schema.json").read_text()
    assert committed == schema_json(), "run: uv run rarepipe schema --output schemas/case_manifest.schema.json"


def test_schema_marks_restricted_fields():
    text = schema_json()
    assert json.loads(text)["title"] == "CaseManifest"
    assert text.count('"restricted": true') >= 10


def test_manifest_round_trips_through_schema(build_case, intake):
    result = intake(build_case("J_trio_with_pedigree"))
    raw = (result.run_dir / "case_manifest.private.json").read_text()
    assert CaseManifest.model_validate_json(raw).semantic_digest == result.manifest.semantic_digest


# ── block-gzip tail integrity (Illumina FASTQ without BGZF EOF marker) ──────


def test_block_gzip_tail_check(tmp_path):
    from rarepipe.testing.fixtures import write_fastq_gz

    ok = write_fastq_gz(tmp_path / "ok.fastq.gz", lane=1, read=1, n=3000, block_gzip=True)
    assert formats.sniff(ok, Format.FASTQ).compression.value == "bgzf"
    assert not formats.has_bgzf_eof(ok) and formats.block_gzip_tail_intact(ok)
    cut = tmp_path / "cut.fastq.gz"
    data = ok.read_bytes()
    cut.write_bytes(data[: len(data) - 100])
    assert not formats.block_gzip_tail_intact(cut)
