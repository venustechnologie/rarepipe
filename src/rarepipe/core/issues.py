"""Structured issue taxonomy shared by every pipeline stage.

An issue is a fact about the case, not an exception. Stages collect issues and
the stage status is derived from their severities — nothing raises past the
stage boundary for a problem with the *data*.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    BLOCKER = "BLOCKER"  # the case cannot safely proceed
    ACTION_REQUIRED = "ACTION_REQUIRED"  # can proceed only after a human decision/fix
    WARNING = "WARNING"  # proceed, but downstream must be aware
    INFO = "INFO"  # a fact worth recording

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Severity.BLOCKER: 0, Severity.ACTION_REQUIRED: 1, Severity.WARNING: 2, Severity.INFO: 3}


class IssueCode(StrEnum):
    # discovery / format
    UNKNOWN_FILE = "UNKNOWN_FILE"
    FILE_UNREADABLE = "FILE_UNREADABLE"
    FORMAT_EXTENSION_MISMATCH = "FORMAT_EXTENSION_MISMATCH"
    EMPTY_FILE = "EMPTY_FILE"
    SYMLINK_OUTSIDE_CASE_ROOT = "SYMLINK_OUTSIDE_CASE_ROOT"
    SYMLINKED_DIRECTORY_NOT_TRAVERSED = "SYMLINKED_DIRECTORY_NOT_TRAVERSED"
    ADDITIONAL_METADATA_DETECTED = "ADDITIONAL_METADATA_DETECTED"
    CHECKSUM_SIDECAR_MISMATCH = "CHECKSUM_SIDECAR_MISMATCH"
    CHECKSUM_SIDECAR_UNPARSEABLE = "CHECKSUM_SIDECAR_UNPARSEABLE"
    # primary inputs
    PRIMARY_GENOMIC_INPUT_MISSING = "PRIMARY_GENOMIC_INPUT_MISSING"
    VARIANT_CALLS_ABSENT = "VARIANT_CALLS_ABSENT"
    PRIMARY_VARIANT_ASSET_AMBIGUOUS = "PRIMARY_VARIANT_ASSET_AMBIGUOUS"
    CONFIGURED_ASSET_NOT_FOUND = "CONFIGURED_ASSET_NOT_FOUND"
    OPTIONAL_ALIGNMENTS_SUPPLIED = "OPTIONAL_ALIGNMENTS_SUPPLIED"
    # VCF
    VCF_PARSE_FAILED = "VCF_PARSE_FAILED"
    VCF_NO_RECORDS = "VCF_NO_RECORDS"
    VCF_NO_SAMPLES = "VCF_NO_SAMPLES"
    VCF_NOT_BGZF = "VCF_NOT_BGZF"
    VCF_NO_CONTIG_HEADER = "VCF_NO_CONTIG_HEADER"
    GVCF_DETECTED = "GVCF_DETECTED"
    # BGZF / alignments
    BGZF_EOF_MISSING = "BGZF_EOF_MISSING"
    ALIGNMENT_PARSE_FAILED = "ALIGNMENT_PARSE_FAILED"
    ALIGNMENT_QUICKCHECK_FAILED = "ALIGNMENT_QUICKCHECK_FAILED"
    ALIGNMENT_NOT_COORDINATE_SORTED = "ALIGNMENT_NOT_COORDINATE_SORTED"
    READ_GROUPS_ABSENT = "READ_GROUPS_ABSENT"
    READ_GROUP_SAMPLE_MISSING = "READ_GROUP_SAMPLE_MISSING"
    READ_GROUP_SAMPLE_CONFLICT = "READ_GROUP_SAMPLE_CONFLICT"
    CRAM_REFERENCE_UNAVAILABLE = "CRAM_REFERENCE_UNAVAILABLE"
    CRAM_REFERENCE_UNVERIFIED = "CRAM_REFERENCE_UNVERIFIED"
    CRAM_REFERENCE_MD5_ABSENT = "CRAM_REFERENCE_MD5_ABSENT"
    # indexes
    INDEX_MISSING = "INDEX_MISSING"
    INDEX_UNUSABLE = "INDEX_UNUSABLE"
    ORPHAN_INDEX = "ORPHAN_INDEX"
    # reference
    GENOME_BUILD_UNKNOWN = "GENOME_BUILD_UNKNOWN"
    GENOME_BUILD_UNCONFIRMED = "GENOME_BUILD_UNCONFIRMED"
    GENOME_BUILD_CLAIM_CONFLICT = "GENOME_BUILD_CLAIM_CONFLICT"
    REFERENCE_BUILD_CONFLICT = "REFERENCE_BUILD_CONFLICT"
    REFERENCE_CONTIG_LENGTH_MISMATCH = "REFERENCE_CONTIG_LENGTH_MISMATCH"
    CONTIG_NAMING_INCONSISTENT = "CONTIG_NAMING_INCONSISTENT"
    NONSTANDARD_CONTIG_NAMING = "NONSTANDARD_CONTIG_NAMING"
    FASTA_PARSE_FAILED = "FASTA_PARSE_FAILED"
    # samples
    SAMPLE_UNMATCHED_ACROSS_ASSETS = "SAMPLE_UNMATCHED_ACROSS_ASSETS"
    SAMPLE_ID_NEAR_MATCH = "SAMPLE_ID_NEAR_MATCH"
    SAMPLE_IDENTITY_UNDETERMINED = "SAMPLE_IDENTITY_UNDETERMINED"
    MULTIPLE_SAMPLES_PRESENT = "MULTIPLE_SAMPLES_PRESENT"
    # phenotype
    PHENOTYPE_UNAVAILABLE = "PHENOTYPE_UNAVAILABLE"
    HPO_TERM_MALFORMED = "HPO_TERM_MALFORMED"
    HPO_NO_VALID_TERMS = "HPO_NO_VALID_TERMS"
    HPO_PARSE_FAILED = "HPO_PARSE_FAILED"
    # pedigree
    PEDIGREE_UNAVAILABLE = "PEDIGREE_UNAVAILABLE"
    PEDIGREE_PARSE_FAILED = "PEDIGREE_PARSE_FAILED"
    PEDIGREE_INCONSISTENT = "PEDIGREE_INCONSISTENT"
    PEDIGREE_SAMPLE_WITHOUT_DATA = "PEDIGREE_SAMPLE_WITHOUT_DATA"


class Issue(BaseModel):
    code: IssueCode
    severity: Severity
    message: str = Field(description="Operator-facing description. Must never contain genomic payload or raw sample labels.")
    asset_ids: list[str] = Field(default_factory=list)
    sample_ids: list[str] = Field(default_factory=list, description="Internal sample aliases (SAMPLE_nnn) only.")
    evidence: list[str] = Field(default_factory=list)
    suggested_action: str | None = None

    def sort_key(self) -> tuple:
        return (self.severity.rank, self.code.value, tuple(self.asset_ids), tuple(self.sample_ids), self.message)


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Deterministic order and de-duplication — required for idempotent manifests."""
    seen: dict[str, Issue] = {}
    for issue in issues:
        seen.setdefault(issue.model_dump_json(), issue)
    return sorted(seen.values(), key=Issue.sort_key)


def count_by_severity(issues: list[Issue]) -> dict[str, int]:
    return {s.value: sum(1 for i in issues if i.severity == s) for s in Severity}
