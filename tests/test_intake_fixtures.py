"""Expected outcomes for each synthetic fixture (PRD §39 A–F plus additional edge cases)."""

from __future__ import annotations

import pytest

from rarepipe.stages.intake.manifest import CramReferenceStatus, GenomeBuild, LogicalRole, Status


def codes(m, severity=None):
    return {i.code.value for i in m.issues if severity is None or i.severity.value == severity}


def test_A_healthy_intake_is_complete(build_case, intake):
    m = intake(build_case("A_healthy")).manifest
    assert m.status == Status.INTAKE_COMPLETE
    assert m.readiness.normalization_ready
    assert m.reference.genome_build.value == GenomeBuild.GRCH38
    assert m.reference.genome_build.confidence.value == "high"
    assert codes(m) == {"OPTIONAL_ALIGNMENTS_SUPPLIED", "PEDIGREE_UNAVAILABLE"}
    assert len(m.samples) == 1
    assert {o.via for o in m.samples[0].observed_in} == {"vcf_sample_column", "read_group_SM"}
    assert m.phenotype.available and m.phenotype.hpo_valid_identifier_count == 5
    assert m.pedigree.status == "unavailable"
    assert m.primary_inputs.primary_variant_selection == "only_candidate"
    rels = {(r.type.value) for r in m.relationships}
    assert rels == {"INDEX_OF"} and len(m.relationships) == 2
    assert all(a.checksum_sha256 and len(a.checksum_sha256) == 64 for a in m.assets)


def test_B_unknown_genome_build(build_case, intake):
    m = intake(build_case("B_unknown_build")).manifest
    assert m.status == Status.INTAKE_COMPLETE_WITH_WARNINGS
    assert "GENOME_BUILD_UNKNOWN" in codes(m, "ACTION_REQUIRED")
    vcf = next(a for a in m.assets if a.logical_role == LogicalRole.GENOMIC_VARIANTS)
    assert vcf.metadata.genome_build.value == GenomeBuild.UNKNOWN
    assert vcf.metadata.genome_build.confidence.value == "insufficient"
    # naming is recorded as evidence, never as a conclusion
    assert any("naming alone does not identify a build" in e for e in vcf.metadata.genome_build.evidence)


def test_C_missing_index(build_case, intake):
    m = intake(build_case("C_missing_index")).manifest
    assert "INDEX_MISSING" in codes(m, "ACTION_REQUIRED")
    assert m.status == Status.INTAKE_COMPLETE_WITH_WARNINGS
    vcf = next(a for a in m.assets if a.logical_role == LogicalRole.GENOMIC_VARIANTS)
    assert vcf.metadata.index.present is False


def test_D_reference_conflict_blocks(build_case, intake):
    m = intake(build_case("D_reference_conflict")).manifest
    assert m.status == Status.INTAKE_BLOCKED
    assert not m.readiness.normalization_ready
    assert "REFERENCE_BUILD_CONFLICT" in codes(m, "BLOCKER")
    assert m.reference.genome_build.value == GenomeBuild.UNKNOWN
    builds = {b.value for b in m.reference.per_asset}
    assert builds == {GenomeBuild.GRCH37, GenomeBuild.GRCH38}


def test_E_malformed_hpo(build_case, intake):
    m = intake(build_case("E_malformed_hpo")).manifest
    assert "HPO_TERM_MALFORMED" in codes(m, "WARNING")
    assert m.phenotype.hpo_valid_identifier_count == 2
    assert m.phenotype.hpo_malformed_identifier_count == 4


def test_F_unknown_auxiliary_files_are_recorded(build_case, intake):
    m = intake(build_case("F_unknown_auxiliary")).manifest
    unknown = [a for a in m.assets if a.logical_role == LogicalRole.UNKNOWN]
    assert len(unknown) == 2
    assert all(a.validation.status.value == "not_inspected" for a in unknown)
    assert sum(1 for i in m.issues if i.code.value == "UNKNOWN_FILE") == 2
    assert m.status == Status.INTAKE_COMPLETE_WITH_WARNINGS


def test_truncated_bam_blocks(build_case, intake):
    m = intake(build_case("G_truncated_bam")).manifest
    assert m.status == Status.INTAKE_BLOCKED
    assert codes(m, "BLOCKER") & {"ALIGNMENT_PARSE_FAILED", "ALIGNMENT_QUICKCHECK_FAILED"}


def test_cram_without_reference_requires_action(build_case, intake):
    m = intake(build_case("H_cram_without_reference")).manifest
    assert "CRAM_REFERENCE_UNAVAILABLE" in codes(m, "ACTION_REQUIRED")
    cram = next(a for a in m.assets if a.logical_role == LogicalRole.ALIGNED_READS)
    assert cram.metadata.cram_reference.status == CramReferenceStatus.UNAVAILABLE


def test_cram_with_reference_is_md5_verified(build_case, intake):
    m = intake(build_case("I_cram_with_reference")).manifest
    cram = next(a for a in m.assets if a.logical_role == LogicalRole.ALIGNED_READS)
    assert cram.metadata.cram_reference.status == CramReferenceStatus.AVAILABLE_VERIFIED_MD5
    assert "CRAM_REFERENCE_UNAVAILABLE" not in codes(m)
    assert any(r.type.value == "VERIFIED_REFERENCE_FOR" for r in m.relationships)


def test_cram_reference_via_external_flag(build_case, intake, tmp_path):
    case = build_case("H_cram_without_reference")
    ref = tmp_path / "scratch" / "H_cram_without_reference" / "synthetic_ref.fa"
    m = intake(case, references=[ref]).manifest
    cram = next(a for a in m.assets if a.logical_role == LogicalRole.ALIGNED_READS)
    assert cram.metadata.cram_reference.status == CramReferenceStatus.AVAILABLE_VERIFIED_MD5
    ext = [a for a in m.assets if a.external]
    assert ext and ext[0].retention_class.value == "external_reference" and ext[0].restricted is False


def test_trio_pedigree_relationships_are_explicit_only(build_case, intake):
    m = intake(build_case("J_trio_with_pedigree")).manifest
    assert m.pedigree.status == "available"
    assert len(m.pedigree.relationships) == 2
    assert {r.relation for r in m.pedigree.relationships} == {"child_of"}
    assert all(s.asserted_role == "unknown" for s in m.samples)
    # phenopacket polarity: absent `excluded` → observed; excluded: true → excluded
    assert (m.phenotype.observed_count, m.phenotype.excluded_count) == (2, 1)


def test_sample_mismatch_and_near_match(build_case, intake):
    m = intake(build_case("K_sample_mismatch")).manifest
    assert "SAMPLE_UNMATCHED_ACROSS_ASSETS" in codes(m, "ACTION_REQUIRED")
    assert "SAMPLE_ID_NEAR_MATCH" in codes(m, "WARNING")
    assert len(m.samples) == 3  # near-matches are never merged


def test_extension_mismatch_uses_content(build_case, intake):
    m = intake(build_case("L_extension_mismatch")).manifest
    fake_bam = next(a for a in m.assets if a.extension == ".bam")
    assert fake_bam.detected_format.value == "VCF"
    assert "FORMAT_EXTENSION_MISMATCH" in fake_bam.validation.issue_codes
    hidden = next(a for a in m.assets if a.extension == ".dat")
    assert hidden.detected_format.value == "BAM" and hidden.logical_role == LogicalRole.ALIGNED_READS
    assert "PRIMARY_VARIANT_ASSET_AMBIGUOUS" in codes(m, "ACTION_REQUIRED")


def test_primary_variant_can_be_configured(build_case, intake):
    m = intake(build_case("L_extension_mismatch"), primary_variant_asset="case.vcf.gz").manifest
    assert m.primary_inputs.primary_variant_selection == "configured"
    assert "PRIMARY_VARIANT_ASSET_AMBIGUOUS" not in codes(m)


def test_md5_sidecars_verified(build_case, intake):
    m = intake(build_case("M_md5_sidecar")).manifest
    sidecars = {a.metadata.target_asset_id: a.metadata.verified for a in m.assets if a.logical_role == LogicalRole.CHECKSUM_SIDECAR}
    assert sorted(sidecars.values()) == [False, True]
    assert "CHECKSUM_SIDECAR_MISMATCH" in codes(m)


def test_no_genomic_input_blocks(build_case, intake):
    m = intake(build_case("N_no_genomic_input")).manifest
    assert m.status == Status.INTAKE_BLOCKED
    assert "PRIMARY_GENOMIC_INPUT_MISSING" in codes(m, "BLOCKER")


def test_fastq_exfat_partial_download(build_case, intake):
    m = intake(build_case("O_fastq_exfat_partial")).manifest
    assert m.status == Status.INTAKE_BLOCKED
    # the tiny synthetic partial file also truncates within the sampled records → FASTQ_PARSE_FAILED is correct too
    assert "INCOMPLETE_DOWNLOAD" in codes(m, "BLOCKER") and codes(m, "BLOCKER") <= {"INCOMPLETE_DOWNLOAD", "FASTQ_PARSE_FAILED"}
    assert "FORMAT_EXTENSION_MISMATCH" not in codes(m)  # ._ AppleDouble files no longer raise mismatches
    assert [i.asset_ids for i in m.issues if i.code.value == "INCOMPLETE_DOWNLOAD"] == [[a.asset_id for a in m.assets if a.filename.endswith("R2_001.fastq.gz.download-part") and not a.filename.startswith("._")]]
    fq = [a for a in m.assets if a.logical_role == LogicalRole.RAW_READS]
    assert len(fq) == 4 and all(a.detected_format.value == "FASTQ" for a in fq)
    assert all(a.metadata.mate_asset_id for a in fq)
    assert sum(1 for r in m.relationships if r.type.value == "MATE_OF") == 2
    full = [a for a in fq if a.metadata.records_sampled == 50]
    assert len(full) == 3 and all(a.metadata.structure_valid and a.metadata.header_style == "illumina_casava_1.8" for a in full)
    sysf = [a for a in m.assets if a.logical_role == LogicalRole.SYSTEM_FILE]
    assert len(sysf) == 5 and all(a.retention_class.value == "controlled_case_material_review_required" for a in sysf)
    docx = next(a for a in m.assets if a.detected_format.value == "DOCX")
    assert docx.logical_role == LogicalRole.CASE_METADATA and docx.retention_class.value == "controlled_case_material_review_required"
    assert "PHENOTYPE_UNAVAILABLE" in codes(m) and "FASTQ_SAMPLE_UNDECLARED" in codes(m)
    assert m.primary_inputs.raw_read_asset_ids and m.reference.genome_build.value == GenomeBuild.GRCH38


def test_fastq_complete_with_docx_hpo(build_case, intake):
    m = intake(build_case("P_fastq_complete_docx_hpo")).manifest
    assert m.status == Status.INTAKE_COMPLETE_WITH_WARNINGS and not codes(m, "BLOCKER")
    assert m.phenotype.available and m.phenotype.hpo_valid_identifier_count == 2 and m.phenotype.hpo_malformed_identifier_count == 1
    fq = [a for a in m.assets if a.logical_role == LogicalRole.RAW_READS]
    assert all(a.metadata.end_of_file_verified is True for a in fq)  # no EOF marker, but final block intact
    docx = next(a for a in m.assets if a.detected_format.value == "DOCX")
    assert docx.logical_role == LogicalRole.PHENOTYPE_TERMS and docx.metadata.parser == "docx_text_scan"


@pytest.mark.parametrize("word", ["pathogenic", "benign", "causal", "candidate gene", "diagnosis", "treatment", "drug"])
def test_no_biological_interpretation_vocabulary(build_case, intake, word):
    result = intake(build_case("J_trio_with_pedigree"))
    text = (result.run_dir / "intake_report.md").read_text().lower() + (result.run_dir / "case_manifest.sanitized.json").read_text().lower()
    assert word not in text
