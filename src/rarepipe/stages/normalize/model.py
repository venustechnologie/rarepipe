"""NormalizedCase — output contract of the case_normalization stage.

A CaseManifest says what exists. A NormalizedCase says how downstream analysis
must interpret it: canonical identities, measured VCF characteristics,
capability-level readiness, and every uncertainty carried forward.
Fields declared ``restricted()`` exist only in the private artifact.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.issues import IssueCode as IntakeIssueCode
from rarepipe.core.issues import Severity
from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "NormalizedCase"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "case_normalization"
STAGE_VERSION = "0.1.0"
SUPPORTED_MANIFEST_MAJOR = "1"


class Status(StrEnum):
    NORMALIZATION_COMPLETE = "NORMALIZATION_COMPLETE"
    NORMALIZATION_COMPLETE_WITH_WARNINGS = "NORMALIZATION_COMPLETE_WITH_WARNINGS"
    NORMALIZATION_BLOCKED = "NORMALIZATION_BLOCKED"


class NormIssueCode(StrEnum):
    # upstream contract
    UPSTREAM_SCHEMA_UNSUPPORTED = "UPSTREAM_SCHEMA_UNSUPPORTED"
    UPSTREAM_INTAKE_BLOCKED = "UPSTREAM_INTAKE_BLOCKED"
    UPSTREAM_SEAL_MISMATCH = "UPSTREAM_SEAL_MISMATCH"
    UPSTREAM_SEAL_UNAVAILABLE = "UPSTREAM_SEAL_UNAVAILABLE"
    SOURCE_ASSET_MISSING = "SOURCE_ASSET_MISSING"
    SOURCE_ASSET_CHANGED = "SOURCE_ASSET_CHANGED"
    PRIMARY_VARIANT_ASSET_UNRESOLVED = "PRIMARY_VARIANT_ASSET_UNRESOLVED"
    MULTI_SAMPLE_VCF_NOT_SUPPORTED = "MULTI_SAMPLE_VCF_NOT_SUPPORTED"
    # resources
    RESOURCE_LOCK_MISSING = "RESOURCE_LOCK_MISSING"
    RESOURCE_MISSING = "RESOURCE_MISSING"
    RESOURCE_CHECKSUM_MISMATCH = "RESOURCE_CHECKSUM_MISMATCH"
    HPO_RESOURCE_UNAVAILABLE = "HPO_RESOURCE_UNAVAILABLE"
    ASSEMBLY_RESOURCE_UNAVAILABLE = "ASSEMBLY_RESOURCE_UNAVAILABLE"
    ASSEMBLY_RESOURCE_MISMATCH = "ASSEMBLY_RESOURCE_MISMATCH"
    # VCF full stream
    VCF_RECORDS_MALFORMED = "VCF_RECORDS_MALFORMED"
    VCF_HTSLIB_READ_FAILED = "VCF_HTSLIB_READ_FAILED"
    VCF_PARSER_DISAGREEMENT = "VCF_PARSER_DISAGREEMENT"
    VCF_NOT_SORTED = "VCF_NOT_SORTED"
    VCF_CONTIG_ORDER_DIFFERS_FROM_HEADER = "VCF_CONTIG_ORDER_DIFFERS_FROM_HEADER"
    VCF_RECORDS_ON_UNDECLARED_CONTIGS = "VCF_RECORDS_ON_UNDECLARED_CONTIGS"
    VCF_INVALID_ALLELE_SYNTAX = "VCF_INVALID_ALLELE_SYNTAX"
    VCF_DUPLICATE_RECORDS = "VCF_DUPLICATE_RECORDS"
    VCF_UNDECLARED_FILTERS = "VCF_UNDECLARED_FILTERS"
    VCF_GENOTYPE_MALFORMED = "VCF_GENOTYPE_MALFORMED"
    VCF_NON_PASS_RECORDS_PRESERVED = "VCF_NON_PASS_RECORDS_PRESERVED"
    VCF_MULTIALLELIC_RECORDS_PRESENT = "VCF_MULTIALLELIC_RECORDS_PRESENT"
    PHASE_INFORMATION_ABSENT = "PHASE_INFORMATION_ABSENT"
    # contigs / reference
    CONTIG_LENGTH_CONFLICT = "CONTIG_LENGTH_CONFLICT"
    CONTIGS_BOUND_BY_HEURISTIC = "CONTIGS_BOUND_BY_HEURISTIC"
    CONTIGS_UNBOUND = "CONTIGS_UNBOUND"
    ANALYSIS_REFERENCE_NOT_BOUND = "ANALYSIS_REFERENCE_NOT_BOUND"
    # phenotype
    HPO_TERM_UNKNOWN = "HPO_TERM_UNKNOWN"
    HPO_TERM_OBSOLETE_REPLACED = "HPO_TERM_OBSOLETE_REPLACED"
    HPO_TERM_OBSOLETE_NO_REPLACEMENT = "HPO_TERM_OBSOLETE_NO_REPLACEMENT"
    HPO_TERM_SECONDARY_ID = "HPO_TERM_SECONDARY_ID"
    HPO_TERM_OUTSIDE_PHENOTYPIC_ABNORMALITY = "HPO_TERM_OUTSIDE_PHENOTYPIC_ABNORMALITY"
    HPO_POLARITY_UNSPECIFIED = "HPO_POLARITY_UNSPECIFIED"
    PHENOTYPE_UNAVAILABLE = "PHENOTYPE_UNAVAILABLE"
    # assertions
    ASSERTION_REJECTED = "ASSERTION_REJECTED"
    ASSERTION_APPLIED = "ASSERTION_APPLIED"
    ASSERTIONS_CASE_MISMATCH = "ASSERTIONS_CASE_MISMATCH"


ALL_CODES = {c.value for c in IntakeIssueCode} | {c.value for c in NormIssueCode}


class CarriedIssue(BaseModel):
    code: str
    severity: Severity
    origin_stage: Literal["case_intake", "case_normalization"]
    resolution: Literal["unresolved", "addressed_by_assertion", "informational"]
    message: str
    asset_ids: list[str] = Field(default_factory=list)
    sample_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    assertion_ids: list[str] = Field(default_factory=list)

    def sort_key(self):
        return (0 if self.origin_stage == "case_intake" else 1, self.severity.rank, self.code, tuple(self.asset_ids), self.message)


# ── provenance of inputs ────────────────────────────────────────────────────


class SourceManifest(BaseModel):
    schema_version: str
    stage_version: str
    run_id: str
    intake_status: str
    manifest_sha256: str
    semantic_digest: str | None
    input_fingerprint: str
    seal_verified: bool | None
    path: str | None = restricted(None)


class ResourceRef(BaseModel):
    kind: str
    name: str
    version: str
    sha256: str
    size_bytes: int
    source_url: str | None = None
    retrieved_at: str | None = None
    status: Literal["verified", "missing", "checksum_mismatch"]
    path: str | None = restricted(None)


class VerifiedAsset(BaseModel):
    asset_id: str
    role: str
    expected_sha256: str
    status: Literal["verified", "missing", "changed"]


class Operation(BaseModel):
    operation: str
    inputs: list[str]
    parameters: dict[str, str] = Field(default_factory=dict)
    resources: list[str] = Field(default_factory=list)
    output: str
    transforms_source_data: bool = False


# ── genome ──────────────────────────────────────────────────────────────────


class ContigClass(StrEnum):
    PRIMARY_CHROMOSOME = "primary_chromosome"
    MITOCHONDRIAL = "mitochondrial"
    ALTERNATE_LOCUS = "alternate_locus"
    UNLOCALIZED = "unlocalized"
    UNPLACED = "unplaced"
    PATCH = "patch"
    DECOY_OR_OTHER = "decoy_or_other"
    UNKNOWN = "unknown"


class ContigBinding(BaseModel):
    source_name: str
    source_length: int | None
    contig_class: ContigClass
    canonical_id: str | None = None
    label: str | None = None
    aliases: dict[str, str] = Field(default_factory=dict)
    basis: Literal["assembly_report_name_and_length", "assembly_report_alias_normalized", "assembly_report_name_only", "name_heuristic", "unbound"]
    matched_alias: str | None = Field(None, description="The assembly-report alias this source name bound to (differs when chr-prefix normalization was needed).")
    length_conflict: bool = False
    records: int | None = restricted(None, description="Per-contig record count (e.g. chrY counts reveal biology) — private only.")


class ContigSummary(BaseModel):
    source_scheme: str
    declared: int
    with_records: int
    by_class: dict[str, int]
    records_by_class: dict[str, int]
    by_basis: dict[str, int]
    length_conflicts: int


class AnalysisReference(BaseModel):
    status: Literal["not_yet_bound", "unresolved"]
    reason: str


class ReferenceBinding(BaseModel):
    assembly: str
    assembly_confidence: str
    assembly_evidence: list[str]
    source_contig_scheme: str
    assembly_resource: ResourceRef | None
    contig_summary: ContigSummary
    contigs: list[ContigBinding]
    analysis_reference: AnalysisReference


class FilterDefinition(BaseModel):
    id: str
    description: str | None


class FilterCharacterization(BaseModel):
    definitions: list[FilterDefinition]
    pass_records: int
    missing_filter_records: int = Field(description="FILTER '.' — filters not applied/recorded")
    non_pass_records: int
    records_by_filter: dict[str, int]
    records_with_multiple_filters: int
    undeclared_filters_used: list[str]
    note: str = "Non-PASS records are preserved and remain part of the case; FILTER is evidence, not an exclusion rule."


class FormatFieldStat(BaseModel):
    field: str
    present_in_header: bool
    header_number: str | None = None
    header_type: str | None = None
    records_declaring: int
    records_populated: int
    populated_fraction: float


class GenotypeStates(BaseModel):
    hom_ref: int = 0
    het: int = 0
    hom_alt: int = 0
    het_non_ref: int = 0
    haploid_called: int = 0
    missing: int = 0
    partially_missing: int = 0
    ploidy_counts: dict[str, int] = Field(default_factory=dict)


class PhaseInformation(BaseModel):
    status: Literal["none", "present"]
    kinds: list[str] = Field(default_factory=list, description="gt_phased_separator | phase_set_PS | read_backed_PGT_PID")
    het_records: int
    het_records_gt_phased: int
    ps_populated_records: int
    pgt_populated_records: int
    pid_populated_records: int
    note: str = "Structural availability only; no phasing was inferred."
    interpretation_note: str | None = Field(None, description="Mechanical explanation of the observed combination of phase fields.")


class UpstreamStep(BaseModel):
    tool: str
    version: str | None = None
    date: str | None = None
    parameters: Literal["available", "unavailable"]
    source: str
    command_line: str | None = restricted(None)


class VcfCharacterization(BaseModel):
    asset_id: str
    sample_id: str | None
    streamed_completely: bool
    data_lines: int
    records_parsed: int
    records_malformed: int
    malformed_line_numbers: list[int] = Field(default_factory=list, description="First 20 only. Line numbers, never content.")
    htslib_records: int | None
    htslib_error: bool
    parsers_agree: bool | None
    sorted: bool | None
    out_of_order_records: int
    noncontiguous_contig_blocks: int
    contig_order_follows_header: bool
    records_on_undeclared_contigs: int
    exact_duplicate_records: int
    records_sharing_position: int
    invalid_ref_alleles: int
    invalid_alt_alleles: int
    filters: FilterCharacterization
    record_classes: dict[str, int]
    allele_classes: dict[str, int]
    multiallelic_records: int
    max_alt_alleles: int
    records_with_spanning_deletion_allele: int
    qual_missing_records: int
    info_fields_declared: list[str]
    format_fields: list[FormatFieldStat]
    genotype_states: GenotypeStates
    genotype_malformed: int
    phase: PhaseInformation
    upstream_processing: list[UpstreamStep]
    elapsed_seconds: float


class SampleIdentity(BaseModel):
    sample_id: str
    source_labels: list[str] = restricted(list)
    role: str = "unknown"
    role_source: Literal["unknown", "externally_asserted"] = "unknown"
    role_assertion_id: str | None = None


class GenomeSection(BaseModel):
    reference: ReferenceBinding | None
    variant_source: VcfCharacterization | None
    samples: list[SampleIdentity]


# ── phenotype ───────────────────────────────────────────────────────────────


class HpoTermNormalized(BaseModel):
    source_id: str | None = restricted(None)
    canonical_id: str | None = restricted(None)
    label: str | None = restricted(None)
    consider_ids: list[str] = restricted(list)
    status: Literal["active", "secondary_id", "obsolete_replaced", "obsolete_no_replacement", "unknown", "not_validated"]
    replacement_basis: Literal["ontology_replaced_by", "ontology_alt_id"] | None = None
    branches: list[str] = Field(default_factory=list)
    polarity: Literal["unspecified", "observed", "excluded"]
    polarity_basis: str
    source_asset_id: str


class PhenotypeSection(BaseModel):
    status: Literal["normalized", "not_validated_resource_unavailable", "unavailable"]
    ontology: ResourceRef | None
    ontology_release: str | None
    source_term_count: int
    canonical_term_count: int
    status_counts: dict[str, int]
    polarity_counts: dict[str, int]
    branch_counts: dict[str, int]
    terms: list[HpoTermNormalized]
    note: str = "Supplied terms only; no ancestors, descendants, similarity or associations were added."


# ── case context ────────────────────────────────────────────────────────────


class PedigreeSection(BaseModel):
    status: Literal["available", "unavailable"]
    note: str
    relationships: list[dict] = Field(default_factory=list)


class LanePair(BaseModel):
    lane: int | None
    r1_asset_id: str | None
    r2_asset_id: str | None


class SampleLinkage(BaseModel):
    status: Literal["unverified", "externally_asserted"]
    sample_id: str | None = None
    assertion_id: str | None = None
    reason: str


class RawReadsSection(BaseModel):
    available: bool
    asset_ids: list[str]
    lane_pairs: list[LanePair]
    total_size_bytes: int
    sample_linkage: SampleLinkage | None
    opened_by_this_stage: bool = False


class AppliedAssertion(BaseModel):
    assertion_id: str
    subject_type: str
    subject_id: str
    predicate: str
    value: str
    evidence_type: str
    evidence_reference: str | None = restricted(None)
    asserted_by: str | None = restricted(None)
    asserted_at: str
    applied: bool
    rejection_reason: str | None = None


class Capability(BaseModel):
    capability: str
    ready: Literal["yes", "partial", "no"]
    blocking_reasons: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class Retention(BaseModel):
    classification: Literal["inherits_case_policy"] = "inherits_case_policy"
    inherited_from_assets: list[str]
    source_retention_classes: list[str]
    review_required: bool = True
    note: str = ("Derived from controlled case material. Delete with the case under its data-use terms unless a later "
                 "review explicitly reclassifies a specific output.")


class Provenance(BaseModel):
    software: SoftwareProvenance
    source_manifest: SourceManifest
    verified_assets: list[VerifiedAsset]
    resources: list[ResourceRef]
    assertions_sha256: str | None
    operations: list[Operation]
    environment_controls: list[str]
    case_root_override: str | None = restricted(None)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    argv: list[str] = restricted(list)


class NormalizedCase(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    status: Status
    readiness: list[Capability]
    genome: GenomeSection
    phenotype: PhenotypeSection
    pedigree: PedigreeSection
    raw_reads: RawReadsSection
    assertions: list[AppliedAssertion]
    issues: list[CarriedIssue]
    issue_counts: dict[str, int]
    retention: Retention
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
