"""Stage 02 — case normalization. Synthetic fixtures only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rarepipe.core.console import Console
from rarepipe.stages.normalize.model import Status
from rarepipe.stages.normalize.stage import NormalizeRequest, NormalizeUsageError, run_normalize
from rarepipe.testing import normalize_fixtures as nf


@pytest.fixture
def case(tmp_path):
    """Builds a synthetic case, runs the real Stage 01, returns paths."""

    def _build(name="case", **kw):
        root = nf.build_case(tmp_path / name, **kw)
        manifest = nf.run_intake_for(root, tmp_path / f"{name}_intake")
        return root, manifest

    return _build


@pytest.fixture
def resources(tmp_path):
    def _build(**kw):
        return nf.build_resources(tmp_path / "resources", **kw)

    return _build


@pytest.fixture
def normalize(tmp_path):
    def _run(manifest: Path, res: Path | None = None, out: str = "norm", **kw):
        return run_normalize(NormalizeRequest(manifest=manifest, output=tmp_path / out, resources=res, **kw), Console(quiet=True))

    return _run


def codes(c, severity=None):
    return {i.code for i in c.issues if severity is None or i.severity.value == severity}


def cap(c, name):
    return next(x for x in c.readiness if x.capability == name)


# ── the clean path ──────────────────────────────────────────────────────────


def test_clean_case_characterizes_the_whole_vcf(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    assert c.status == Status.NORMALIZATION_COMPLETE_WITH_WARNINGS
    assert not codes(c, "BLOCKER")
    v = c.genome.variant_source
    assert v.streamed_completely and v.data_lines == 12 and v.records_malformed == 0
    assert v.htslib_records == 12 and v.parsers_agree is True  # independent readers agree
    assert v.sorted is True and v.sample_id == "SAMPLE_001"
    assert v.records_sharing_position == 0 and v.exact_duplicate_records == 0
    assert v.invalid_ref_alleles == 0 and v.invalid_alt_alleles == 0


def test_filter_distribution_is_measured_and_nothing_is_dropped(case, resources, normalize):
    _, manifest = case()
    v = normalize(manifest, resources()).case.genome.variant_source
    f = v.filters
    assert (f.pass_records, f.non_pass_records, f.missing_filter_records) == (8, 3, 1)
    assert f.records_by_filter == {"FS60": 1, "LowQual": 2, "QD2": 1}
    assert f.records_with_multiple_filters == 1
    assert f.pass_records + f.non_pass_records + f.missing_filter_records == v.records_parsed
    assert {d.id for d in f.definitions} >= {"LowQual", "QD2", "FS60", "SOR3"}  # declared-but-unused kept
    assert not f.undeclared_filters_used


def test_variant_and_allele_classes(case, resources, normalize):
    _, manifest = case()
    v = normalize(manifest, resources()).case.genome.variant_source
    assert v.record_classes == {"complex": 1, "deletion": 1, "insertion": 1, "mnv": 1, "multiallelic": 2, "snv": 5, "symbolic": 1}
    assert v.multiallelic_records == 2 and v.max_alt_alleles == 2
    assert v.records_with_spanning_deletion_allele == 1
    assert v.allele_classes["spanning_deletion"] == 1 and v.allele_classes["symbolic"] == 1


def test_genotype_fields_and_states(case, resources, normalize):
    _, manifest = case()
    v = normalize(manifest, resources()).case.genome.variant_source
    fields = {s.field: s for s in v.format_fields}
    assert fields["GT"].present_in_header and fields["GT"].records_declaring == 12
    assert fields["PGT"].present_in_header and fields["PGT"].records_declaring == 0  # declared, never used
    assert fields["AD"].records_declaring == 11 and fields["AD"].records_populated == 10  # one record has './.:.:.:.:.'
    gs = v.genotype_states
    assert (gs.hom_ref, gs.het, gs.hom_alt, gs.het_non_ref, gs.haploid_called, gs.missing) == (1, 7, 1, 1, 1, 1)
    assert gs.ploidy_counts == {"1": 1, "2": 11}
    assert v.genotype_malformed == 0


def test_phase_information_is_reported_not_inferred(case, resources, normalize):
    _, manifest = case()
    p = normalize(manifest, resources()).case.genome.variant_source.phase
    assert p.status == "present" and set(p.kinds) == {"gt_phased_separator", "phase_set_PS"}
    assert p.het_records == 8 and p.het_records_gt_phased == 1 and p.ps_populated_records == 1
    assert p.pgt_populated_records == 0


def test_upstream_processing_is_captured_structurally(case, resources, normalize):
    _, manifest = case()
    steps = normalize(manifest, resources()).case.genome.variant_source.upstream_processing
    tools = {s.tool: s for s in steps}
    assert "GATK VariantFiltration" in tools and tools["GATK VariantFiltration"].version == "4.5.0.0"
    assert tools["GATK VariantFiltration"].parameters == "available"
    assert any(t.startswith("bcftools") for t in tools)


def test_contigs_are_canonicalized_without_rewriting_the_vcf(case, resources, normalize, tmp_path):
    root, manifest = case()
    before = (root / "case.vcf.gz").read_bytes()
    c = normalize(manifest, resources()).case
    r = c.genome.reference
    assert r.assembly == "GRCh38" and r.source_contig_scheme == "numeric"
    assert r.contig_summary.by_class == {"alternate_locus": 1, "decoy_or_other": 2, "mitochondrial": 1,
                                         "primary_chromosome": 4, "unknown": 1, "unlocalized": 1, "unplaced": 1}
    chr1 = next(b for b in r.contigs if b.source_name == "1")
    assert chr1.canonical_id == "GRCh38:NC_000001.11" and chr1.aliases["ucsc"] == "chr1"
    assert chr1.basis == "assembly_report_name_and_length" and chr1.label == "chromosome 1"
    assert r.analysis_reference.status == "not_yet_bound"
    assert (root / "case.vcf.gz").read_bytes() == before  # source untouched


def test_chr_and_numeric_schemes_reach_the_same_canonical_identities(case, resources, normalize):
    res = resources()
    _, m_num = case("numeric", scheme="numeric")
    _, m_chr = case("ucsc", scheme="chr")
    num = normalize(m_num, res, out="n1").case.genome.reference
    ucsc = normalize(m_chr, res, out="n2").case.genome.reference
    assert ucsc.source_contig_scheme == "chr_prefixed"
    ids = lambda r: {b.canonical_id for b in r.contigs if b.canonical_id}  # noqa: E731
    assert ids(num) == ids(ucsc)


def test_records_per_contig_are_private_only(case, resources, normalize):
    _, manifest = case()
    result = normalize(manifest, resources())
    private = {b.source_name: b.records for b in result.case.genome.reference.contigs}
    assert private["1"] == 8
    assert all(b.records is None for b in result.sanitized.genome.reference.contigs)
    assert result.sanitized.genome.reference.contig_summary.records_by_class["primary_chromosome"] == 10


# ── phenotype ───────────────────────────────────────────────────────────────


def test_hpo_terms_validated_against_pinned_release(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    p = c.phenotype
    assert p.status == "normalized" and p.ontology_release == "2099-01-01"
    assert p.source_term_count == 3 and p.canonical_term_count == 3
    assert p.status_counts == {"active": 3}
    assert p.branch_counts == {"phenotypic_abnormality": 3}
    assert {t.label for t in p.terms} == {"Synthetic phenotype A", "Synthetic phenotype B", "Synthetic phenotype C"}


def test_obsolete_unknown_and_secondary_identifiers(case, resources, normalize):
    _, manifest = case(hpo_terms=nf.EDGE_HPO)
    c = normalize(manifest, resources()).case
    by_source = {t.source_id: t for t in c.phenotype.terms}
    assert by_source["HP:0002099"].status == "secondary_id" and by_source["HP:0002099"].canonical_id == "HP:0001250"
    replaced = by_source["HP:0000009"]
    assert replaced.status == "obsolete_replaced" and replaced.canonical_id == "HP:0001263" and replaced.replacement_basis == "ontology_replaced_by"
    ambiguous = by_source["HP:0000010"]
    assert ambiguous.status == "obsolete_no_replacement" and ambiguous.canonical_id is None
    assert set(ambiguous.consider_ids) == {"HP:0001250", "HP:0000252"}  # surfaced, never chosen
    assert by_source["HP:9999999"].status == "unknown"
    assert by_source["HP:0000007"].branches == ["mode_of_inheritance"]
    assert {"HPO_TERM_UNKNOWN", "HPO_TERM_OBSOLETE_NO_REPLACEMENT"} <= codes(c, "ACTION_REQUIRED")
    assert {"HPO_TERM_OBSOLETE_REPLACED", "HPO_TERM_OUTSIDE_PHENOTYPIC_ABNORMALITY"} <= codes(c, "WARNING")


def test_polarity_stays_unspecified_without_evidence(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    assert c.phenotype.polarity_counts == {"unspecified": 3}
    assert all(t.polarity_basis == "default_unspecified" for t in c.phenotype.terms)
    assert "HPO_POLARITY_UNSPECIFIED" in codes(c, "WARNING")
    assert cap(c, "phenotype_based_prioritization").ready == "yes"
    assert "phenotype_polarity_unspecified" in cap(c, "phenotype_based_prioritization").conditions


def test_hpo_resource_absent_leaves_terms_unvalidated(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources(hpo=False)).case
    assert c.phenotype.status == "not_validated_resource_unavailable"
    assert all(t.status == "not_validated" for t in c.phenotype.terms)
    assert "HPO_RESOURCE_UNAVAILABLE" in codes(c, "ACTION_REQUIRED")
    assert cap(c, "phenotype_based_prioritization").ready == "no"
    assert c.genome.reference.contig_summary.by_basis.get("name_heuristic")  # falls back, labelled as heuristic


# ── assertions ──────────────────────────────────────────────────────────────


def _assertions(tmp_path, *entries) -> Path:
    p = tmp_path / "assertions.json"
    p.write_text(json.dumps({"schema": {"name": "CaseAssertions", "version": "1.0.0"}, "case_id": "SYNTH_CASE", "assertions": list(entries)}, indent=2))
    return p


def _entry(aid, stype, sid, predicate, value):
    return {"assertion_id": aid, "subject": {"type": stype, "id": sid}, "predicate": predicate, "value": value,
            "evidence": {"type": "organizer_documentation", "reference": "synthetic challenge README §2"},
            "asserted_by": "operator", "asserted_at": "2099-01-01T00:00:00+00:00"}


def test_assertions_supply_facts_computation_cannot(case, resources, normalize, tmp_path):
    _, manifest = case(with_fastq=True)
    a = _assertions(tmp_path, _entry("ASSERT_001", "sample", "SAMPLE_001", "role", "proband"),
                    _entry("ASSERT_002", "phenotype_set", "ALL", "phenotype_polarity", "observed"),
                    _entry("ASSERT_003", "raw_read_set", "ALL", "sample_linkage", "SAMPLE_001"))
    c = normalize(manifest, resources(), assertions=a).case
    assert c.genome.samples[0].role == "proband" and c.genome.samples[0].role_source == "externally_asserted"
    assert c.phenotype.polarity_counts == {"observed": 3}
    assert all(t.polarity_basis == "assertion:ASSERT_002" for t in c.phenotype.terms)
    assert c.raw_reads.sample_linkage.status == "externally_asserted" and c.raw_reads.sample_linkage.sample_id == "SAMPLE_001"
    carried = next(i for i in c.issues if i.code == "FASTQ_SAMPLE_UNDECLARED")
    assert carried.resolution == "addressed_by_assertion" and carried.assertion_ids == ["ASSERT_003"]
    assert all(a.applied for a in c.assertions)


def test_invalid_assertions_are_rejected_not_applied(case, resources, normalize, tmp_path):
    _, manifest = case()
    a = _assertions(tmp_path, _entry("ASSERT_001", "sample", "SAMPLE_404", "role", "proband"),
                    _entry("ASSERT_002", "raw_read_set", "ALL", "sample_linkage", "SAMPLE_001"))
    c = normalize(manifest, resources(), assertions=a).case
    assert all(not x.applied for x in c.assertions)
    assert "ASSERTION_REJECTED" in codes(c, "ACTION_REQUIRED")
    assert c.genome.samples[0].role == "unknown"


def test_assertions_for_another_case_are_refused(case, resources, normalize, tmp_path):
    _, manifest = case()
    p = tmp_path / "other.json"
    p.write_text(json.dumps({"case_id": "OTHER_CASE", "assertions": [_entry("A1", "sample", "SAMPLE_001", "role", "proband")]}))
    c = normalize(manifest, resources(), assertions=p).case
    assert c.status == Status.NORMALIZATION_BLOCKED and "ASSERTIONS_CASE_MISMATCH" in codes(c, "BLOCKER")


def test_malformed_assertions_file_is_a_usage_error(case, resources, normalize, tmp_path):
    _, manifest = case()
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"case_id": "SYNTH_CASE", "assertions": [_entry("A1", "sample", "SAMPLE_001", "role", "not_a_role")]}))
    with pytest.raises(NormalizeUsageError):
        normalize(manifest, resources(), assertions=p)


# ── failure branches ────────────────────────────────────────────────────────


def test_malformed_record_late_in_file_is_found_by_full_stream(case, resources, normalize):
    root, manifest = case(malformed_late=True)
    intake = json.loads(manifest.read_text())
    assert intake["status"] != "INTAKE_BLOCKED"  # Stage 01 only reads the first record
    c = normalize(manifest, resources()).case
    assert c.status == Status.NORMALIZATION_BLOCKED and "VCF_RECORDS_MALFORMED" in codes(c, "BLOCKER")
    v = c.genome.variant_source
    assert v.records_malformed == 1 and v.records_parsed == 12
    assert v.malformed_line_numbers and cap(c, "vcf_based_prioritization").ready == "no"


def test_unsorted_vcf(case, resources, normalize):
    _, manifest = case(unsorted=True)
    c = normalize(manifest, resources()).case
    v = c.genome.variant_source
    assert v.sorted is False and v.out_of_order_records == 1
    assert "VCF_NOT_SORTED" in codes(c, "ACTION_REQUIRED")
    assert "vcf_not_coordinate_sorted" in cap(c, "vcf_based_prioritization").blocking_reasons


def test_source_asset_changed_since_intake_blocks(case, resources, normalize):
    root, manifest = case()
    (root / "hpo_terms.txt").write_text("HP:0001250\nHP:0000252\n")  # edited after intake
    c = normalize(manifest, resources()).case
    assert c.status == Status.NORMALIZATION_BLOCKED and "SOURCE_ASSET_CHANGED" in codes(c, "BLOCKER")
    assert [v.status for v in c.provenance.verified_assets if v.role == "phenotype"] == ["changed"]


def test_tampered_manifest_fails_the_stage01_seal(case, resources, normalize):
    _, manifest = case()
    manifest.chmod(0o644)
    data = json.loads(manifest.read_text())
    data["case"]["case_id"] = "TAMPERED"
    manifest.write_text(json.dumps(data))
    c = normalize(manifest, resources()).case
    assert c.status == Status.NORMALIZATION_BLOCKED and "UPSTREAM_SEAL_MISMATCH" in codes(c, "BLOCKER")


def test_blocked_intake_blocks_normalization(case, resources, normalize, tmp_path):
    root = nf.build_case(tmp_path / "empty_case", empty=True)
    manifest = nf.run_intake_for(root, tmp_path / "empty_intake")
    c = normalize(manifest, resources()).case
    assert c.status == Status.NORMALIZATION_BLOCKED and "UPSTREAM_INTAKE_BLOCKED" in codes(c, "BLOCKER")
    assert cap(c, "vcf_based_prioritization").ready == "no"


def test_resource_checksum_mismatch_blocks(case, resources, normalize):
    _, manifest = case()
    res = resources()
    (res / "hpo" / "v2099-01-01" / "hp.obo").write_text(nf.SYNTH_OBO + "\n[Term]\nid: HP:1111111\nname: Sneaked in\n")
    c = normalize(manifest, res).case
    assert c.status == Status.NORMALIZATION_BLOCKED and "RESOURCE_CHECKSUM_MISMATCH" in codes(c, "BLOCKER")
    assert [r.status for r in c.provenance.resources if r.kind == "hpo_ontology"] == ["checksum_mismatch"]


def test_sanitized_manifest_is_refused(case, resources, normalize):
    _, manifest = case()
    with pytest.raises(NormalizeUsageError):
        normalize(manifest.parent / "case_manifest.sanitized.json", resources())


def test_output_inside_stage01_run_is_refused(case, resources, normalize, tmp_path):
    _, manifest = case()
    with pytest.raises(NormalizeUsageError):
        run_normalize(NormalizeRequest(manifest=manifest, output=manifest.parent / "norm"), Console(quiet=True))


# ── case context that must stay explicit ────────────────────────────────────


def test_pedigree_absence_is_explicit_and_no_singleton_is_fabricated(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    assert c.pedigree.status == "unavailable" and not c.pedigree.relationships
    assert "no singleton pedigree is fabricated" in c.pedigree.note
    assert cap(c, "trio_analysis").ready == "no"
    assert set(cap(c, "trio_analysis").blocking_reasons) == {"pedigree_unavailable", "parental_genotypes_unavailable"}


def test_raw_reads_are_carried_unverified_and_never_opened(case, resources, normalize):
    root, manifest = case(with_fastq=True)
    for p in root.glob("*.fastq.gz"):
        p.chmod(0o000)  # unreadable: the stage must not touch them
    try:
        c = normalize(manifest, resources()).case
    finally:
        for p in root.glob("*.fastq.gz"):
            p.chmod(0o644)
    assert c.raw_reads.available and len(c.raw_reads.asset_ids) == 2 and not c.raw_reads.opened_by_this_stage
    assert c.raw_reads.sample_linkage.status == "unverified"
    assert [(p.lane, bool(p.r1_asset_id), bool(p.r2_asset_id)) for p in c.raw_reads.lane_pairs] == [(1, True, True)]
    assert cap(c, "read_level_analysis").ready == "no"
    assert set(cap(c, "read_level_analysis").blocking_reasons) == {"fastq_sample_linkage_unverified", "analysis_reference_fasta_not_bound", "alignments_unavailable"}


def test_readiness_is_per_capability(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    assert {x.capability: x.ready for x in c.readiness} == {
        "phenotype_based_prioritization": "yes", "vcf_based_prioritization": "yes", "trio_analysis": "no",
        "phase_aware_analysis": "partial", "variant_decomposition_left_alignment": "no", "read_level_analysis": "no"}


def test_stage01_issues_are_carried_with_origin(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    origins = {i.origin_stage for i in c.issues}
    assert origins == {"case_intake", "case_normalization"}
    assert any(i.origin_stage == "case_intake" and i.code == "PEDIGREE_UNAVAILABLE" for i in c.issues)


def test_retention_is_inherited(case, resources, normalize):
    _, manifest = case()
    c = normalize(manifest, resources()).case
    assert c.retention.classification == "inherits_case_policy" and c.retention.review_required
    assert "controlled_genomic_delete_required" in c.retention.source_retention_classes
