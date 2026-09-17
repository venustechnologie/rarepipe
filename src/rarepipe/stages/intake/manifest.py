"""CaseManifest — the versioned output contract of the case_intake stage.

Fields tagged ``restricted`` (see ``_R``) may carry local paths, source sample
labels, or case-derived content. They are populated only in the *private*
manifest; ``redact.sanitize`` clears every one of them generically, so the
sanitized manifest and the human report are privacy-safe by construction.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from rarepipe.core.issues import Issue
from rarepipe.core.provenance import SoftwareProvenance

SCHEMA_NAME = "CaseManifest"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "case_intake"
STAGE_VERSION = "0.1.0"

_R = {"restricted": True}


def restricted(default=None, **kw):
    """A field that exists only in the private manifest."""
    if default is list:
        return Field(default_factory=list, json_schema_extra=_R, **kw)
    if default is dict:
        return Field(default_factory=dict, json_schema_extra=_R, **kw)
    return Field(default=default, json_schema_extra=_R, **kw)


# ── enums ──────────────────────────────────────────────────────────────────


class Status(StrEnum):
    INTAKE_COMPLETE = "INTAKE_COMPLETE"
    INTAKE_COMPLETE_WITH_WARNINGS = "INTAKE_COMPLETE_WITH_WARNINGS"
    INTAKE_BLOCKED = "INTAKE_BLOCKED"


class Format(StrEnum):
    VCF = "VCF"
    BCF = "BCF"
    BAM = "BAM"
    CRAM = "CRAM"
    SAM = "SAM"
    FASTQ = "FASTQ"
    TBI = "TBI"
    CSI = "CSI"
    BAI = "BAI"
    CRAI = "CRAI"
    GZI = "GZI"
    FASTA = "FASTA"
    FAI = "FAI"
    SEQUENCE_DICTIONARY = "SEQUENCE_DICTIONARY"
    PED = "PED"
    JSON = "JSON"
    CSV = "CSV"
    TSV = "TSV"
    TEXT = "TEXT"
    PDF = "PDF"
    DOCX = "DOCX"
    APPLEDOUBLE = "APPLEDOUBLE"
    CHECKSUM_MD5 = "CHECKSUM_MD5"
    CHECKSUM_SHA256 = "CHECKSUM_SHA256"
    GZIP_UNKNOWN = "GZIP_UNKNOWN"
    BINARY_UNKNOWN = "BINARY_UNKNOWN"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


class Compression(StrEnum):
    NONE = "none"
    BGZF = "bgzf"
    GZIP = "gzip"
    FORMAT_NATIVE = "format_native"  # BAM/CRAM/BCF carry their own block compression


class LogicalRole(StrEnum):
    GENOMIC_VARIANTS = "genomic_variants"
    ALIGNED_READS = "aligned_reads"
    RAW_READS = "raw_reads"
    VARIANT_INDEX = "variant_index"
    ALIGNMENT_INDEX = "alignment_index"
    REFERENCE_SEQUENCE = "reference_sequence"
    REFERENCE_INDEX = "reference_index"
    SEQUENCE_DICTIONARY = "sequence_dictionary"
    PHENOTYPE_TERMS = "phenotype_terms"
    PEDIGREE = "pedigree"
    CASE_METADATA = "case_metadata"
    DOCUMENTATION = "documentation"
    CHECKSUM_SIDECAR = "checksum_sidecar"
    SYSTEM_FILE = "system_file"
    UNKNOWN = "unknown"


class RetentionClass(StrEnum):
    # VCF/BAM/CRAM, slices, and their indexes: delete at the governance deadline.
    CONTROLLED_GENOMIC_DELETE_REQUIRED = "controlled_genomic_delete_required"
    # Phenotype/pedigree/metadata/unknown case material: may survive only after review.
    CONTROLLED_CASE_MATERIAL_REVIEW_REQUIRED = "controlled_case_material_review_required"
    # Supplied explicitly from outside the case root via --reference.
    EXTERNAL_REFERENCE = "external_reference"


class ValidationStatus(StrEnum):
    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    REQUIRES_ACTION = "requires_action"
    INVALID = "invalid"
    NOT_INSPECTED = "not_inspected"


class GenomeBuild(StrEnum):
    GRCH37 = "GRCh37"
    GRCH37_DECOY = "GRCh37+decoy"
    GRCH38 = "GRCh38"
    T2T_CHM13 = "T2T-CHM13"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class ContigNaming(StrEnum):
    UCSC_CHR_PREFIXED = "chr_prefixed"
    NUMERIC = "numeric"
    MIXED = "mixed"
    NONSTANDARD = "nonstandard"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    INDEX_OF = "INDEX_OF"
    BGZF_INDEX_OF = "BGZF_INDEX_OF"  # .gzi
    SEQUENCE_DICTIONARY_OF = "SEQUENCE_DICTIONARY_OF"
    CHECKSUM_OF = "CHECKSUM_OF"
    MATE_OF = "MATE_OF"  # R2 → R1 of the same read set
    CANDIDATE_REFERENCE_FOR = "CANDIDATE_REFERENCE_FOR"
    VERIFIED_REFERENCE_FOR = "VERIFIED_REFERENCE_FOR"


class CramReferenceStatus(StrEnum):
    AVAILABLE_VERIFIED_MD5 = "available_verified_md5"
    AVAILABLE_UNVERIFIED = "available_unverified_name_length_match_only"
    UNAVAILABLE = "unavailable"


# ── shared value objects ───────────────────────────────────────────────────


class Contig(BaseModel):
    name: str
    length: int | None = None
    md5: str | None = None


class GenomeBuildCall(BaseModel):
    value: GenomeBuild
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    naming_convention: ContigNaming = ContigNaming.UNKNOWN
    markers: list[str] = Field(default_factory=list, description="e.g. decoy_contigs, alt_contigs, hla_contigs, ebv_contig, hg19_style_chrM")
    claim_conflict: bool = Field(False, description="Header text claims a build other than the one contig lengths establish.")
    action_required: list[str] = Field(default_factory=list)


class IndexStatus(BaseModel):
    present: bool
    index_type: Format | None = None
    asset_id: str | None = None
    usable: bool | None = None


class HeaderDeclarations(BaseModel):
    info: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    filter: list[str] = Field(default_factory=list)


# ── per-format metadata (discriminated by `kind`) ──────────────────────────


class VcfMetadata(BaseModel):
    kind: Literal["variants"] = "variants"
    format: Format
    compression: Compression
    header_valid: bool
    vcf_version: str | None = None
    is_gvcf: bool = False
    has_records: bool | None = Field(None, description="Whether at least one record parsed. Record content is never stored.")
    sample_count: int = 0
    sample_ids: list[str] = Field(default_factory=list)
    source_sample_labels: list[str] = restricted(list)
    contigs: list[Contig] = Field(default_factory=list)
    contigs_with_records_per_index: list[str] | None = None
    reference_claim: str | None = restricted(None, description="Raw ##reference value (may be a local path).")
    genome_build: GenomeBuildCall
    index: IndexStatus
    declarations: HeaderDeclarations = Field(default_factory=HeaderDeclarations)
    source_tools: list[str] = Field(default_factory=list)
    processing_hints: list[str] = Field(default_factory=list)


class ReadGroup(BaseModel):
    sample_id: str | None = None
    platform: str | None = None
    source_id: str | None = restricted(None)
    source_sample_label: str | None = restricted(None)
    library: str | None = restricted(None)


class Program(BaseModel):
    name: str | None = None
    version: str | None = None


class CramReference(BaseModel):
    all_sequences_have_md5: bool
    status: CramReferenceStatus
    reference_asset_ids: list[str] = Field(default_factory=list)
    declared_uris: list[str] = restricted(list)
    evidence: list[str] = Field(default_factory=list)


class AlignmentMetadata(BaseModel):
    kind: Literal["alignments"] = "alignments"
    format: Format
    header_valid: bool
    quickcheck_passed: bool | None = None
    bgzf_eof_present: bool | None = None
    sort_order: str | None = None
    contigs: list[Contig] = Field(default_factory=list)
    read_group_count: int = 0
    read_groups: list[ReadGroup] = Field(default_factory=list)
    sample_ids: list[str] = Field(default_factory=list)
    programs: list[Program] = Field(default_factory=list)
    genome_build: GenomeBuildCall
    index: IndexStatus
    cram_reference: CramReference | None = None


class FastaMetadata(BaseModel):
    kind: Literal["reference_sequence"] = "reference_sequence"
    compression: Compression
    contig_source: Literal["fai", "sequence_dictionary", "streamed_scan", "none"]
    contigs: list[Contig] = Field(default_factory=list)
    md5_computed: bool = False
    genome_build: GenomeBuildCall
    index: IndexStatus


class SequenceDictionaryMetadata(BaseModel):
    kind: Literal["sequence_dictionary"] = "sequence_dictionary"
    contigs: list[Contig] = Field(default_factory=list)
    genome_build: GenomeBuildCall


class HpoTerm(BaseModel):
    id: str
    polarity: Literal["observed", "excluded", "unspecified"]


class PhenotypeMetadata(BaseModel):
    kind: Literal["phenotype"] = "phenotype"
    parser: Literal["line_list", "delimited_table", "phenopacket_json", "json_scan", "docx_text_scan"]
    valid_term_count: int
    unique_valid_term_count: int
    malformed_identifier_count: int
    observed_count: int
    excluded_count: int
    polarity_unspecified_count: int
    terms: list[HpoTerm] = restricted(list)
    malformed_line_numbers: list[int] = restricted(list)


class PedigreeIndividual(BaseModel):
    sample_id: str
    asserted_sex: Literal["male", "female", "unknown"]
    asserted_affected_status: Literal["affected", "unaffected", "unknown"]
    source_family_label: str | None = restricted(None)


class PedigreeMetadata(BaseModel):
    kind: Literal["pedigree"] = "pedigree"
    individual_count: int
    family_count: int
    individuals: list[PedigreeIndividual] = Field(default_factory=list)


class FastqMetadata(BaseModel):
    kind: Literal["raw_reads"] = "raw_reads"
    compression: Compression
    records_sampled: int = Field(description="Leading records parsed for structure only; sequences/qualities are never stored.")
    structure_valid: bool
    header_style: Literal["illumina_casava_1.8", "unrecognized"]
    read_number_from_header: int | None = None
    read_number_from_filename: int | None = None
    lane_from_header: int | None = None
    lane_from_filename: int | None = None
    read_length_min: int | None = None
    read_length_max: int | None = None
    quality_encoding: Literal["phred33", "ambiguous", "unknown"] = "unknown"
    end_of_file_verified: bool | None = Field(None, description="BGZF EOF marker check; None for plain gzip (not verifiable without full decompression).")
    mate_asset_id: str | None = None
    instrument: str | None = restricted(None)
    flowcell: str | None = restricted(None)


class ChecksumSidecarMetadata(BaseModel):
    kind: Literal["checksum_sidecar"] = "checksum_sidecar"
    algorithm: Literal["md5", "sha256"]
    target_asset_id: str | None = None
    verified: bool | None = None


AssetMetadata = Annotated[
    VcfMetadata
    | AlignmentMetadata
    | FastaMetadata
    | SequenceDictionaryMetadata
    | PhenotypeMetadata
    | PedigreeMetadata
    | FastqMetadata
    | ChecksumSidecarMetadata,
    Field(discriminator="kind"),
]


# ── assets ─────────────────────────────────────────────────────────────────


class Validation(BaseModel):
    status: ValidationStatus
    issue_codes: list[str] = Field(default_factory=list)


class AssetRecord(BaseModel):
    asset_id: str = Field(description="Stable, machine-safe. Derived from the relative path, never the absolute path.")
    relative_path: str | None = restricted(None, description="POSIX path relative to case root (or 'external:<n>' for --reference inputs).")
    filename: str | None = restricted(None)
    extension: str
    extension_format: Format | None = Field(None, description="What the filename claims.")
    detected_format: Format = Field(description="What the content is, independent of the name.")
    compression: Compression
    size_bytes: int
    checksum_sha256: str | None
    logical_role: LogicalRole
    restricted: bool
    retention_class: RetentionClass
    external: bool = False
    metadata: AssetMetadata | None = None
    validation: Validation


class AssetRelationship(BaseModel):
    type: RelationshipType
    source: str
    target: str
    evidence: list[str] = Field(default_factory=list)


# ── case-level sections ────────────────────────────────────────────────────


class SampleObservation(BaseModel):
    asset_id: str
    via: Literal["vcf_sample_column", "read_group_SM", "pedigree_individual", "vcf_pedigree_header"]


class AssertedValue(BaseModel):
    value: str
    source_asset_id: str


class Sample(BaseModel):
    sample_id: str
    observed_in: list[SampleObservation]
    source_labels: list[str] = restricted(list)
    asserted_role: Literal["unknown"] = Field(
        "unknown", description="Roles such as proband/mother/father are never inferred; see pedigree.relationships for explicit assertions."
    )
    asserted_sex: list[AssertedValue] = Field(default_factory=list)
    asserted_affected_status: list[AssertedValue] = Field(default_factory=list)


class Relationship(BaseModel):
    subject: str
    relation: Literal["child_of"]
    object: str
    source_asset_id: str


class PedigreeSection(BaseModel):
    status: Literal["available", "unavailable"]
    asset_ids: list[str] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


class PhenotypeSection(BaseModel):
    available: bool
    asset_ids: list[str] = Field(default_factory=list)
    hpo_valid_identifier_count: int = 0
    hpo_unique_valid_identifier_count: int = 0
    hpo_malformed_identifier_count: int = 0
    observed_count: int = 0
    excluded_count: int = 0


class AssetBuild(BaseModel):
    asset_id: str
    value: GenomeBuild
    confidence: Confidence


class ReferenceSection(BaseModel):
    genome_build: GenomeBuildCall
    per_asset: list[AssetBuild] = Field(default_factory=list)


class PrimaryInputs(BaseModel):
    """Where downstream stages should look — so nobody re-derives it from filenames."""

    variant_asset_ids: list[str] = Field(default_factory=list)
    primary_variant_asset_id: str | None = Field(None, description="Set only when unambiguous (exactly one) or explicitly configured.")
    primary_variant_selection: Literal["only_candidate", "configured", "ambiguous", "none"] = "none"
    alignment_asset_ids: list[str] = Field(default_factory=list)
    raw_read_asset_ids: list[str] = Field(default_factory=list)
    reference_sequence_asset_ids: list[str] = Field(default_factory=list)
    phenotype_asset_ids: list[str] = Field(default_factory=list)
    pedigree_asset_ids: list[str] = Field(default_factory=list)


class InventorySummary(BaseModel):
    asset_count: int
    total_size_bytes: int
    by_role: dict[str, int]
    by_format: dict[str, int]


class Readiness(BaseModel):
    normalization_ready: bool
    blockers: list[str] = Field(default_factory=list)
    actions_required: list[str] = Field(default_factory=list)
    rationale: str


class IntakeConfiguration(BaseModel):
    case_root: str | None = restricted(None)
    exclude_globs: list[str] = Field(default_factory=list)
    primary_variant_asset: str | None = restricted(None)
    external_references: list[str] = restricted(list)


class Fingerprints(BaseModel):
    input_fingerprint: str = Field(description="sha256 over sorted asset content digests — changes iff biological/technical content changes.")
    inventory_fingerprint: str = Field(description="sha256 over sorted (relative_path, digest) — also changes on renames/moves.")
    configuration_digest: str


class Provenance(BaseModel):
    software: SoftwareProvenance
    configuration: IntakeConfiguration
    fingerprints: Fingerprints
    environment_controls: list[str] = Field(default_factory=list)


class Execution(BaseModel):
    """Execution-specific metadata. Excluded from the semantic digest."""

    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    checksum_cache_enabled: bool
    checksum_cache_hits: int
    argv: list[str] = restricted(list)


class SchemaRef(BaseModel):
    name: Literal["CaseManifest"] = SCHEMA_NAME
    version: str = SCHEMA_VERSION


class PipelineRef(BaseModel):
    stage: Literal["case_intake"] = STAGE_NAME
    stage_version: str = STAGE_VERSION


class CaseRef(BaseModel):
    case_id: str


class Redaction(BaseModel):
    visibility: Literal["private", "sanitized"]
    note: str


class CaseManifest(BaseModel):
    schema_: SchemaRef = Field(default_factory=SchemaRef, alias="schema")
    pipeline: PipelineRef = Field(default_factory=PipelineRef)
    redaction: Redaction
    case: CaseRef
    status: Status
    readiness: Readiness
    inventory: InventorySummary
    primary_inputs: PrimaryInputs
    assets: list[AssetRecord]
    relationships: list[AssetRelationship]
    samples: list[Sample]
    phenotype: PhenotypeSection
    pedigree: PedigreeSection
    reference: ReferenceSection
    issues: list[Issue]
    issue_counts: dict[str, int]
    provenance: Provenance
    semantic_digest: str | None = Field(None, description="sha256 of this manifest excluding `execution` and this field.")
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
