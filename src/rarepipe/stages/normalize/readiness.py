"""Readiness by capability. A case is never globally 'ready' — it is ready for particular operations."""

from __future__ import annotations

from rarepipe.stages.normalize.model import (
    Capability,
    GenomeSection,
    PedigreeSection,
    PhenotypeSection,
    RawReadsSection,
)


def assess(genome: GenomeSection, phenotype: PhenotypeSection, pedigree: PedigreeSection, raw: RawReadsSection,
           upstream_blocked: bool, integrity_blocked: bool) -> list[Capability]:
    caps: list[Capability] = []
    base_block = (["upstream_intake_blocked"] if upstream_blocked else []) + (["source_integrity_failed"] if integrity_blocked else [])

    # ── phenotype-based prioritization
    usable = phenotype.canonical_term_count
    reasons, conds = list(base_block), []
    if phenotype.status == "unavailable":
        reasons.append("no_phenotype_terms_supplied")
    elif phenotype.status == "not_validated_resource_unavailable":
        reasons.append("hpo_ontology_resource_unavailable")
    elif usable == 0:
        reasons.append("no_supplied_term_resolves_to_a_current_hpo_concept")
    unresolved = phenotype.source_term_count - usable
    if unresolved > 0 and usable:
        conds.append(f"{unresolved}_supplied_term(s)_unresolved")
    if phenotype.polarity_counts.get("unspecified"):
        conds.append("phenotype_polarity_unspecified")
    ready = "no" if reasons else ("partial" if unresolved > 0 else "yes")
    caps.append(Capability(capability="phenotype_based_prioritization", ready=ready, blocking_reasons=reasons, conditions=conds))

    # ── VCF-based prioritization (singleton, as supplied)
    v = genome.variant_source
    reasons, conds = list(base_block), []
    if v is None:
        reasons.append("no_resolved_primary_variant_file")
    else:
        if not v.streamed_completely:
            reasons.append("vcf_not_fully_streamed")
        if v.records_malformed:
            reasons.append("vcf_contains_malformed_records")
        if v.htslib_error or v.parsers_agree is False:
            reasons.append("htslib_cannot_read_complete_vcf")
        if v.sorted is False:
            reasons.append("vcf_not_coordinate_sorted")
        if v.sample_id is None:
            reasons.append("vcf_sample_unresolved")
        if v.genotype_malformed:
            conds.append("some_genotypes_malformed")
        if v.multiallelic_records:
            conds.append("multiallelic_records_present_tools_may_require_decomposition")
        if v.filters.non_pass_records:
            conds.append("non_pass_records_present_filter_policy_is_an_analysis_decision")
    if genome.reference is None or genome.reference.assembly in ("unknown", "custom"):
        reasons.append("assembly_not_established")
    if genome.samples and all(s.role == "unknown" for s in genome.samples):
        conds.append("sample_role_unasserted")
    caps.append(Capability(capability="vcf_based_prioritization", ready="no" if reasons else "yes", blocking_reasons=reasons, conditions=conds))

    # ── trio / family analysis
    reasons = []
    if pedigree.status == "unavailable":
        reasons.append("pedigree_unavailable")
    if len(genome.samples) < 3:
        reasons.append("parental_genotypes_unavailable")
    caps.append(Capability(capability="trio_analysis", ready="no" if reasons else "yes", blocking_reasons=reasons))

    # ── use of existing phase information
    if v is None or v.phase.status == "none":
        caps.append(Capability(capability="phase_aware_analysis", ready="no",
                               blocking_reasons=["no_phase_information_in_vcf"] if v else ["no_resolved_primary_variant_file"]))
    else:
        caps.append(Capability(capability="phase_aware_analysis", ready="partial", blocking_reasons=[],
                               conditions=[f"phase_information_kinds:{'+'.join(v.phase.kinds)}",
                                           f"het_records_gt_phased:{v.phase.het_records_gt_phased}_of_{v.phase.het_records}"]))

    # ── variant decomposition / left-alignment (needs an exact reference)
    caps.append(Capability(capability="variant_decomposition_left_alignment", ready="no",
                           blocking_reasons=["analysis_reference_fasta_not_bound"]))

    # ── read-level analysis
    reasons = []
    if not raw.available:
        reasons.append("raw_reads_unavailable")
    else:
        if raw.sample_linkage and raw.sample_linkage.status == "unverified":
            reasons.append("fastq_sample_linkage_unverified")
        reasons.append("analysis_reference_fasta_not_bound")
        reasons.append("alignments_unavailable")
    caps.append(Capability(capability="read_level_analysis", ready="no", blocking_reasons=reasons))
    return caps
