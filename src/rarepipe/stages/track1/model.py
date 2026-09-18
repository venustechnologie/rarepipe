"""Track1SubmissionPackage and ExternalValidationResult.

Stage 05 is the pipeline's first prospective black-box validation: one query against a
hidden clinical answer key, made after everything upstream is frozen. Two rules shape
these objects.

1. The package must record exactly what the pipeline knew *before* the answer was seen.
   That is what `ValidationSnapshot.created_before_ground_truth_query` asserts, and why
   the snapshot is hashed and sealed with the run.
2. The result is evidence, not training data. `ExternalValidationResult` records the
   verdict and the branch it puts the case into; nothing upstream is modified by it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "Track1SubmissionPackage"
SCHEMA_VERSION = "1.0.0"
RESULT_SCHEMA_NAME = "ExternalValidationResult"
RESULT_SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "track1_export"
STAGE_VERSION = "0.1.0"

PROBAND_ID = "PROBAND01"
CSV_COLUMNS = ["proband_id", "chrom_1", "pos_1", "ref_1", "alt_1",
               "chrom_2", "pos_2", "ref_2", "alt_2", "epcr", "finding_type", "notes"]
MAX_ROWS = 10


class ValidationSnapshot(BaseModel):
    """What the pipeline knew before the oracle was queried. Immutable once submitted."""

    intake_run: str | None = None
    normalization_run: str | None = None
    baseline_run: str
    adjudication_run: str
    baseline_digest: str | None = None
    adjudication_digest: str | None = None
    git_commit: str | None = None
    git_describe: str | None = None
    git_dirty: bool | None = None
    created_before_ground_truth_query: bool = True
    created_at: str


class SubmissionVariant(BaseModel):
    """Exact identity, restricted: it goes to the evaluator, never into a shared artifact."""

    chrom: str | None = restricted(None, description="Chromosome as submitted (UCSC-style, chr-prefixed).")
    pos: int | None = restricted(None)
    ref: str | None = restricted(None)
    alt: str | None = restricted(None)
    source_contig: str | None = restricted(None, description="Contig name as it appears in the case VCF.")
    hgvs: str | None = restricted(None)
    solver_variant_score: float | None = None
    functional_class: str | None = None


class SubmissionRow(BaseModel):
    rank: int
    epcr: float = Field(gt=0, le=1)
    configuration: Literal["single_variant", "candidate_compound_heterozygous"]
    gene_symbol: str
    inheritance_model: str
    finding_type: Literal["primary", "secondary"] = "primary"
    notes: str = ""
    variants: list[SubmissionVariant]
    selected_by: Literal["adjudicated_hypothesis", "baseline_stability_rule"]
    profiles_supporting: list[str] = Field(default_factory=list)
    best_profile_rank: int | None = None
    phase: Literal["unresolved", "trans", "cis"] = "unresolved"
    variants_dropped: int = Field(0, description="Contributing variants beyond the two the CSV can carry.")


class SelectionRule(BaseModel):
    """Frozen before generation. Recorded so the ordering can be reproduced and criticised."""

    description: str
    steps: list[str]
    profiles_considered: list[str]
    deduplication: str
    max_variants_per_row: int = 2
    tie_breaks: list[str]
    rows_considered: int = 0
    rows_emitted: int = 0


class EpcrSchedule(BaseModel):
    description: str
    values: list[float]
    disclaimer: str = ("EPCR values are rank-preserving confidence surrogates, not empirically "
                       "calibrated probabilities. No calibration model exists for this pipeline.")


class ValidationCheck(BaseModel):
    check: str
    passed: bool
    detail: str = ""


class OfficialScorerCheck(BaseModel):
    """The official public parser, run locally against our file, without the answer key."""

    available: bool = False
    path: str | None = None
    sha256: str | None = None
    source_url: str | None = None
    parsed_ok: bool | None = None
    rows_parsed: int | None = None
    ranks_as_submitted: bool | None = Field(None, description="True if the parser's EPCR ordering matches our row order.")
    error: str | None = None


class SubmissionFile(BaseModel):
    name: str
    sha256: str
    bytes: int
    contains_case_specific_identity: bool = False


class SubmissionState(BaseModel):
    state: Literal["ready", "submitted"] = "ready"
    submission_number: int = 1
    submission_budget: int = 6
    recommended_upload_filename: str
    channel: str = "Hugging Face Space — Track 1 submission tab (manual, human-controlled upload)"
    note: str = "rarepipe does not upload. The submission is made by a person, deliberately."


class Provenance(BaseModel):
    software: SoftwareProvenance
    validation_snapshot: ValidationSnapshot
    snapshot_digest: str
    prediction_digest: str | None = None
    upstream_unmodified: str = ("Stages 01–04 were frozen before this package was generated and are not "
                                "modified by any benchmark feedback.")
    disclosure: str = ("The predictions file carries exact variant identity and goes only to the evaluator, "
                       "which already holds authorized access to this case. The methods report and this "
                       "manifest carry none.")


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    raw_candidate_set_path: str | None = restricted(None)
    adjudication_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class Track1SubmissionPackage(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    proband_id: str = PROBAND_ID
    assembly: str
    interpretation_note: str = ("A ranked list of causal hypotheses for one proband. Submitting a pair asserts a "
                                "proposed causal configuration, not experimentally established trans phase.")
    rows: list[SubmissionRow]
    selection_rule: SelectionRule
    epcr_schedule: EpcrSchedule
    checks: list[ValidationCheck]
    official_scorer: OfficialScorerCheck
    valid: bool
    files: list[SubmissionFile]
    submission: SubmissionState
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class ScoredResult(BaseModel):
    match: Literal["FULL", "PARTIAL", "NONE"]
    full_match_rank: int | None = None
    partial_match_rank: int | None = None
    rank_points: float | None = None
    f_max: float | None = None
    f_max_threshold: float | None = None
    n_predictions_at_f_max: int | None = None


class ExternalValidationResult(BaseModel):
    """The oracle's answer, made part of the case state rather than a screenshot."""

    schema_: dict = Field(default_factory=lambda: {"name": RESULT_SCHEMA_NAME, "version": RESULT_SCHEMA_VERSION}, alias="schema")
    visibility: Literal["private", "sanitized"] = "sanitized"
    case_id: str
    evaluator: str = "MVA_Hackathon_Track1"
    submission_number: int
    submission_package_run_id: str
    prediction_digest: str
    snapshot_digest: str
    result: ScoredResult
    raw_response: str = Field(description="The evaluator's response as captured, verbatim.")
    received_at: str
    branch: Literal["A_full_match", "B_partial_match", "C_no_match"]
    branch_action: str
    upstream_modification: str = ("None. Leaderboard feedback is evidence about the case, not a training signal "
                                  "for the pipeline; a further submission requires an independently justified "
                                  "pipeline change.")
    semantic_digest: str | None = None

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


BRANCHES = {
    "FULL": ("A_full_match",
             "Causal pair confirmed for hackathon purposes. Stop spending engineering effort on causal-variant "
             "discovery; the open questions become mechanism resolution (missense severity, phase), not ranking."),
    "PARTIAL": ("B_partial_match",
                "One causal allele recovered, the partner is wrong or missing. The next question is specifically "
                "'where is the other allele?' — filtered variants, structural variants, splicing, alternative "
                "alleles in the same gene — not a blind re-analysis."),
    "NONE": ("C_no_match",
             "Perform error attribution before anything else: was the gene wrong, did the true pair fall below "
             "rank 10, did the solver miss a variant, was the representation wrong, was the variant type "
             "unsupported, did filtering matter, is the upstream VCF incomplete? No parameter tweaking."),
}
