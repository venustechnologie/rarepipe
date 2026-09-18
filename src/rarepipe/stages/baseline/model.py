"""RawCandidateSet and AnalysisProfile — output contracts of the baseline_analysis stage.

`RawCandidateSet` records **what the solver said**, not what this system believes.
Nothing here is a diagnosis, and no candidate is reranked by rarepipe.

Fields declared ``restricted()`` exist only in the private artifact: variant
coordinates, HGVS, genotypes and source sample labels are case-derived findings.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.issues import Severity
from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "RawCandidateSet"
SCHEMA_VERSION = "1.1.0"  # 1.1: location-only fields moved into `execution` (a path is not content)
STAGE_NAME = "baseline_analysis"
STAGE_VERSION = "0.1.0"
SUPPORTED_NORMALIZED_MAJOR = "1"


class Status(StrEnum):
    BASELINE_ANALYSIS_COMPLETE = "BASELINE_ANALYSIS_COMPLETE"
    BASELINE_ANALYSIS_COMPLETE_WITH_WARNINGS = "BASELINE_ANALYSIS_COMPLETE_WITH_WARNINGS"
    BASELINE_ANALYSIS_BLOCKED = "BASELINE_ANALYSIS_BLOCKED"


class BaselineIssueCode(StrEnum):
    UPSTREAM_SCHEMA_UNSUPPORTED = "UPSTREAM_SCHEMA_UNSUPPORTED"
    UPSTREAM_NOT_READY = "UPSTREAM_NOT_READY"
    SOURCE_ASSET_CHANGED = "SOURCE_ASSET_CHANGED"
    SOLVER_UNAVAILABLE = "SOLVER_UNAVAILABLE"
    SOLVER_DATA_UNAVAILABLE = "SOLVER_DATA_UNAVAILABLE"
    SOLVER_VERSION_MISMATCH = "SOLVER_VERSION_MISMATCH"
    SOLVER_RUN_FAILED = "SOLVER_RUN_FAILED"
    SOLVER_OUT_OF_MEMORY = "SOLVER_OUT_OF_MEMORY"
    SOLVER_REJECTED_INPUT = "SOLVER_REJECTED_INPUT"
    SOLVER_IGNORED_CONTIGS = "SOLVER_IGNORED_CONTIGS"
    SOLVER_VARIANT_LOSS = "SOLVER_VARIANT_LOSS"
    MULTIALLELIC_HANDLING_UNVERIFIED = "MULTIALLELIC_HANDLING_UNVERIFIED"
    PROFILE_PRODUCED_NO_CANDIDATES = "PROFILE_PRODUCED_NO_CANDIDATES"
    PHENOTYPE_ASSUMPTION_APPLIED = "PHENOTYPE_ASSUMPTION_APPLIED"
    ANALYSIS_ROLE_ASSUMED = "ANALYSIS_ROLE_ASSUMED"
    CANDIDATE_PHASE_UNRESOLVED = "CANDIDATE_PHASE_UNRESOLVED"
    PROFILE_DISAGREEMENT = "PROFILE_DISAGREEMENT"
    NON_PASS_ONLY_CANDIDATE = "NON_PASS_ONLY_CANDIDATE"


class Issue(BaseModel):
    code: str
    severity: Severity
    message: str
    profile_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggested_action: str | None = None


# ── analysis profile ────────────────────────────────────────────────────────


class AnalysisAssumption(BaseModel):
    """An interpretation this analysis makes that the case record does NOT establish."""

    id: str
    statement: str
    basis: str
    scope: Literal["this_analysis"] = "this_analysis"
    contradicts_case_record: bool = Field(False, description="True if the case record states otherwise (never silently overridden).")


class PhenotypeSelection(BaseModel):
    rule: Literal["phenotypic_abnormality_only", "all_supplied_terms"]
    term_count: int
    branches_included: list[str]
    term_ids: list[str] = restricted(list)


class FilterPolicy(BaseModel):
    """PASS_ONLY (an Exomiser analysis *mode*) and failedVariantFilter (a *step* that drops
    non-PASS VCF records) are different things; conflating them is a classic silent bug."""

    analysis_mode: Literal["PASS_ONLY", "FULL"]
    failed_variant_filter: bool
    non_pass_records_permitted: bool
    source_filter_labels_modified: Literal[False] = False


class AnalysisProfile(BaseModel):
    profile_id: str
    label: str
    phenotype: PhenotypeSelection
    filter_policy: FilterPolicy
    inheritance_modes: dict[str, float]
    frequency_max_percent: float
    assumptions: list[AnalysisAssumption]
    analysis_yaml_sha256: str
    sample_yaml_sha256: str
    properties_sha256: str


# ── solver identity ─────────────────────────────────────────────────────────


class SolverIdentity(BaseModel):
    name: Literal["Exomiser"] = "Exomiser"
    version: str
    distribution_sha256: str | None = None
    jar_sha256: str | None = None
    hg38_data_version: str | None = None
    phenotype_data_version: str | None = None
    data_sha256: dict[str, str] = Field(default_factory=dict)
    java_version: str | None = None
    java_max_heap: str | None = None
    container_digest: str | None = None


# ── candidates ──────────────────────────────────────────────────────────────


class ContributingVariant(BaseModel):
    variant_ref: str = Field(description="Stable within this run: sha256(contig:pos:ref:alt)[:12]. Coordinates themselves are private.")
    source_filter_status: str = Field(description=("FILTER as it stands in the source VCF, read back from that locus — never rewritten. "
                                                   "NOT the solver's own FILTER column, which reports its internal status."))
    solver_variant_score: float | None = None
    functional_class: str | None = None
    clinvar_interpretation: str | None = None
    clinvar_star_rating: int | None = None
    max_frequency_percent: float | None = None
    max_pathogenicity_score: float | None = None
    acmg_classification: str | None = None
    contig: str | None = restricted(None)
    position: int | None = restricted(None)
    ref: str | None = restricted(None)
    alt: str | None = restricted(None)
    hgvs: str | None = restricted(None)
    genotype: str | None = restricted(None)
    rs_id: str | None = restricted(None)


class CandidatePhase(BaseModel):
    status: Literal["unresolved", "not_applicable"] = "unresolved"
    note: str = ("Two heterozygous variants in one gene are a candidate compound-heterozygous configuration. "
                 "Without parental data or phasing evidence this is NOT proof they are in trans.")


class Candidate(BaseModel):
    rank: int
    gene_symbol: str
    gene_id: str | None = None
    inheritance_model: str
    p_value: float | None = None
    score_combined: float | None = None
    score_phenotype: float | None = None
    score_variant: float | None = None
    contributing_variants: list[ContributingVariant]
    contributing_variant_count: int
    is_variant_pair: bool = Field(description="Exactly two contributing variants under a compound-heterozygous model.")
    phase: CandidatePhase | None = None
    any_contributing_variant_non_pass: bool
    solver_evidence: dict[str, str] = Field(default_factory=dict, description="Solver-reported evidence strings (phenotype matches, scores) verbatim.")


class ProfileRuntime(BaseModel):
    """Execution measurements — excluded from the semantic digest."""

    profile_id: str
    wall_clock_seconds: float | None = None
    peak_rss_bytes: int | None = None


class ProfileResult(BaseModel):
    profile_id: str
    status: Literal["completed", "failed", "not_run"]
    failure_reason: str | None = None
    exit_code: int | None = None
    candidate_count: int
    candidates: list[Candidate]
    variants_in_source: int | None = None
    variants_reported_by_solver: int | None = None
    contigs_absent_from_solver_output: list[str] = Field(default_factory=list)
    native_output_files: list[str] = Field(default_factory=list, description="Paths relative to the run's native output root.")
    native_output_sha256: dict[str, str] = Field(default_factory=dict)


# ── cross-profile comparison ────────────────────────────────────────────────


class PairOverlap(BaseModel):
    profile_a: str
    profile_b: str
    top1_same_gene: bool | None = None
    top5_gene_overlap: int
    top10_gene_overlap: int
    top20_gene_overlap: int
    compound_het_gene_overlap: int


class GeneRankRow(BaseModel):
    gene_symbol: str
    ranks: dict[str, int | None]
    best_rank: int
    appears_in_profiles: int


class Stability(BaseModel):
    profiles_compared: list[str]
    pairwise: list[PairOverlap]
    top_gene_table: list[GeneRankRow]
    genes_only_when_non_pass_permitted: list[str]
    genes_only_with_eighth_term: list[str]
    genes_in_all_profiles: list[str]
    max_rank_movement: dict[str, int] = Field(default_factory=dict)
    verdict: Literal["stable", "partially_stable", "unstable", "insufficient"]
    verdict_basis: str


# ── artifact ────────────────────────────────────────────────────────────────


class Retention(BaseModel):
    native_solver_outputs: Literal["delete_required"] = "delete_required"
    raw_candidate_set: Literal["delete_required_review"] = "delete_required_review"
    top_n_findings: Literal["retainable_after_review"] = "retainable_after_review"
    note: str = ("Genome-scale solver intermediates (annotated VCF, full variant tables) must be deleted with the case. "
                 "Only a small ranked candidate list may survive, and only after explicit review.")


class SourceCase(BaseModel):
    case_id: str
    normalized_case_run_id: str
    normalized_case_semantic_digest: str | None
    normalized_case_sha256: str
    source_vcf_asset_id: str
    source_vcf_sha256: str
    assembly: str


class Provenance(BaseModel):
    software: SoftwareProvenance
    solver: SolverIdentity
    source_case: SourceCase
    environment_controls: list[str]
    execution_host: dict[str, str] = Field(default_factory=dict)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    profile_runtimes: list[ProfileRuntime] = Field(default_factory=list)
    native_output_root: str | None = restricted(None)
    normalized_case_path: str | None = restricted(None)
    source_vcf_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class RawCandidateSet(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    status: Status
    interpretation_note: str = ("This artifact records what an external solver reported under declared assumptions. "
                                "It is not a diagnosis, not a ranking by rarepipe, and no candidate was manually promoted.")
    profiles: list[AnalysisProfile]
    results: list[ProfileResult]
    stability: Stability | None
    issues: list[Issue]
    issue_counts: dict[str, int]
    retention: Retention = Field(default_factory=Retention)
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
