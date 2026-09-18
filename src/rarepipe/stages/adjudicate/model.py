"""AdjudicatedHypothesis — output contract of the evidence_adjudication stage.

The durable object here is not the report: it is `EvidenceAssertion`. Every claim about
the hypothesis decomposes into assertions that each carry a source, a strength, what they
support, and their limitations. Retrieval implementations will change; this shape should not.

Three questions are kept separate on purpose and never collapsed into one score:
  1. is the gene–disease mechanism appropriate?
  2. does each variant materially impair the gene's function?
  3. is there evidence the variants form the causal biallelic configuration?

This stage produces an evidence dossier. It is not a variant ranker, not ACMG classification
automation, and not a diagnosis.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "AdjudicatedHypothesis"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "evidence_adjudication"
STAGE_VERSION = "0.1.0"


class Status(StrEnum):
    ADJUDICATION_COMPLETE = "ADJUDICATION_COMPLETE"
    ADJUDICATION_COMPLETE_WITH_GAPS = "ADJUDICATION_COMPLETE_WITH_GAPS"
    ADJUDICATION_BLOCKED = "ADJUDICATION_BLOCKED"


class EvidenceClass(StrEnum):
    """Ordered by the hierarchy in PRD 004 §6 — a predictor must not outrank an assay."""

    HUMAN_OBSERVATION = "human_observation"
    FUNCTIONAL = "functional"
    POPULATION = "population"
    MOLECULAR_MECHANISTIC = "molecular_mechanistic"
    COMPUTATIONAL = "computational"
    TECHNICAL_CALL = "technical_call"
    PHASE = "phase"

    @property
    def rank(self) -> int:
        return _CLASS_RANK[self]


_CLASS_RANK = {
    EvidenceClass.HUMAN_OBSERVATION: 0,
    EvidenceClass.FUNCTIONAL: 1,
    EvidenceClass.POPULATION: 2,
    EvidenceClass.MOLECULAR_MECHANISTIC: 3,
    EvidenceClass.COMPUTATIONAL: 4,
    EvidenceClass.TECHNICAL_CALL: 5,
    EvidenceClass.PHASE: 6,
}


class Strength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    SUPPORTING = "supporting"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"


class Direction(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    UNCERTAIN = "uncertain"


class Retrieval(StrEnum):
    LOCAL_PINNED = "local_pinned_resource"
    BULK_PUBLIC = "bulk_public_resource"
    GENE_LEVEL_LOOKUP = "gene_level_public_lookup"
    NOT_RETRIEVED = "not_retrieved"


class EvidenceProvenance(BaseModel):
    source: str = Field(description="Resource name, e.g. 'ClinVar variant_summary' or 'Exomiser 2602 hg38 data'.")
    source_version: str | None = None
    identifier: str | None = Field(None, description="Stable id within the source (ClinVar VariationID, PMID, UniProt accession).")
    retrieval: Retrieval
    retrieved_at: str | None = None
    query: str | None = Field(None, description="Exactly what was asked of the source. Never contains case-specific variant identity.")
    url: str | None = None


class EvidenceAssertion(BaseModel):
    """One piece of evidence bearing on one claim."""

    assertion_id: str
    claim_id: str
    evidence_class: EvidenceClass
    statement: str = Field(description="What this evidence says, in plain words.")
    result: str | None = Field(None, description="The measured/reported value behind the statement.")
    direction: Direction
    strength: Strength
    strength_basis: str = Field(description="Why this strength — a documented threshold or guideline, never an invented score.")
    provenance: EvidenceProvenance
    limitations: list[str] = Field(default_factory=list)
    case_specific_detail: str | None = restricted(None, description="Any case-identifying detail behind this assertion (private only).")


class Claim(BaseModel):
    claim_id: str
    statement: str
    subject: Literal["gene_disease_mechanism", "variant_a", "variant_b", "configuration", "prior_classification_transfer"]
    assessment: Literal["supported", "contradicted", "unresolved", "not_assessed"]
    assessment_basis: str
    assertion_ids: list[str] = Field(default_factory=list)


class VariantIdentity(BaseModel):
    """Precise identity is required before any evidence lookup; the details stay private."""

    variant_ref: str
    role: Literal["variant_a", "variant_b"]
    molecular_consequence: str | None = None
    gene_symbol: str | None = None
    assembly: str | None = None
    transcript: str | None = restricted(None)
    hgvs: str | None = restricted(None)
    hgvs_protein: str | None = restricted(None)
    contig: str | None = restricted(None)
    position: int | None = restricted(None)
    ref: str | None = restricted(None)
    alt: str | None = restricted(None)
    rs_id: str | None = restricted(None)
    clinvar_variation_id: str | None = restricted(None)
    normalization_basis: str = Field(description="How identity was established (which pinned resource/transcript set).")


class PhaseEvidence(BaseModel):
    status: Literal["unresolved", "trans", "cis"] = "unresolved"
    existing_vcf_readbacked_phase: Literal["available_for_pair", "unavailable_for_pair"] = "unavailable_for_pair"
    genomic_distance_bp: int | None = None
    parental_data: Literal["unavailable", "available"] = "unavailable"
    long_range_phase: Literal["not_evaluated", "evaluated"] = "not_evaluated"
    note: str = ("Absence of read-backed phase is absence of evidence, not evidence of cis. "
                 "Neither configuration is inferred.")


class EvidenceRequest(BaseModel):
    """Uncertainty translated into the smallest possible external question."""

    request_id: str
    question: str
    why_it_matters: str
    evidence_needed: str
    minimum_information: str
    raw_data_required: bool = False
    preferred_route: str
    draft_message: str
    blocks_this_stage: bool = False


class MindChanger(BaseModel):
    direction: Literal["would_strengthen", "would_weaken"]
    evidence: str
    why: str


class NextAction(BaseModel):
    action: str
    expected_information_gain: Literal["high", "medium", "low", "uncertain"]
    cost: Literal["very_low", "low", "medium", "high", "very_high"]
    rationale: str
    blocked_by: list[str] = Field(default_factory=list)


class EvidenceSummary(BaseModel):
    """Per evidence class, for the hypothesis as a whole. Deliberately not a number."""

    human_observation: str = "absent"
    functional: str = "absent"
    population: str = "absent"
    molecular_mechanistic: str = "absent"
    computational: str = "absent"
    technical_call: str = "absent"
    phase: str = "unresolved"
    overall: Literal["supported", "unresolved", "contradicted"] = "unresolved"
    overall_basis: str = ""


class ProvisionalClassification(BaseModel):
    """Optional, explicitly research-only. Never presented as a clinical classification."""

    label: str = "research-only provisional interpretation"
    variant_role: Literal["variant_a", "variant_b"]
    criteria_applied: list[str] = Field(default_factory=list)
    criteria_source: str | None = None
    provisional_result: str | None = None
    caveat: str = ("Not a clinical classification. Produced outside a diagnostic laboratory, without "
                   "expert panel review, and must not be used for clinical decisions.")


class SourceHypothesis(BaseModel):
    raw_candidate_set_run_id: str
    raw_candidate_set_digest: str | None
    normalized_case_run_id: str
    case_id: str
    gene_symbol: str
    inheritance_model: str
    solver_rank: int
    profiles_supporting: list[str]


class Provenance(BaseModel):
    software: SoftwareProvenance
    source_hypothesis: SourceHypothesis
    evidence_sources: list[EvidenceProvenance]
    disclosure_policy: str = ("No case-specific variant identity, variant pair, or HPO combination is transmitted "
                              "externally. Retrieval is local, bulk, or gene-level only; exact-variant external "
                              "querying requires an explicit approval gate.")
    environment_controls: list[str] = Field(default_factory=list)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    raw_candidate_set_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class AdjudicatedHypothesis(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    hypothesis_id: str
    status: Status
    interpretation_note: str = ("An evidence dossier for one hypothesis. Not a diagnosis, not a clinical variant "
                                "classification, and not a ranking. Claims are kept separate on purpose.")
    gene_symbol: str
    inheritance_model: str
    variants: list[VariantIdentity]
    claims: list[Claim]
    assertions: list[EvidenceAssertion]
    contradicting_assertion_ids: list[str] = Field(default_factory=list, description="Present even when empty — contradiction hunting is mandatory.")
    evidence_summary: EvidenceSummary
    phase: PhaseEvidence
    provisional_classifications: list[ProvisionalClassification] = Field(default_factory=list)
    unresolved_questions: list[str]
    what_would_change_our_mind: list[MindChanger]
    evidence_requests: list[EvidenceRequest]
    next_actions: list[NextAction]
    evidence_gaps: list[str] = Field(default_factory=list, description="Evidence classes that were not retrieved, and why.")
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
