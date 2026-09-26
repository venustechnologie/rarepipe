"""Approved intervention and experience discovery.

Stage 08 asks whether anything already approved has credible evidence of producing the biological
change Stage 07 specified — and what happened when people tried. It does not rank medicines, propose
doses, or recommend treatment.

The principle that shapes every object here:

    "we found no evidence it works"  ≠  "someone tried it and it did not work"

Absence of evidence and observed failure are different facts, they are stored in different fields,
and a search that found nothing can never be rendered as a negative result. `InterventionExperience`
exists to carry what actually happened, including the failures, because another patient's failure is
only reusable if what failed, measured how, in which system, survives the write-down.

`InterventionExperience` is deliberately source-agnostic: a paper, a trial, a case report, a hospital
node or a patient record should all fit it unchanged. That shape is the point.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "InterventionDiscovery"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "intervention_discovery"
STAGE_VERSION = "0.1.0"


class Status(StrEnum):
    CANDIDATES_FOUND = "APPROVED_DRUG_CANDIDATES_FOUND"
    LOW_CONFIDENCE_ONLY = "ONLY_LOW_CONFIDENCE_CANDIDATES"
    NONE_FOUND = "NO_DEFENSIBLE_APPROVED_DRUG_CANDIDATE_FOUND"


class Outcome(StrEnum):
    """What happened when someone tried it. UNKNOWN means untested — never 'we didn't find it'."""

    IMPROVED = "improved"
    NO_EFFECT = "no_effect"
    WORSENED = "worsened"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SubjectScope(StrEnum):
    PATIENT = "patient"
    PATIENT_COHORT = "patient_cohort"
    PATIENT_CELLS = "patient_cells"
    ENGINEERED_HUMAN_CELLS = "engineered_human_cells"
    ANIMAL = "animal"
    BIOCHEMICAL = "biochemical"


class Lane(StrEnum):
    A_DIRECT_RESTORATION = "A_direct_bubr1_restoration"
    B_DEFICIENT_RESCUE = "B_rescue_in_deficient_biology"
    C_MECHANISTIC_LEAD = "C_mechanistic_lead"
    D_FAILURE = "D_failure_or_negative_experience"


class MatchStatus(StrEnum):
    MATCH = "MATCH"
    POSSIBLE = "POSSIBLE"
    NO_MATCH = "NO_MATCH"


class Directness(StrEnum):
    DIRECT_BUBR1 = "direct_BUBR1"
    DEFICIENT_MODEL = "BUB1B_model"
    RELATED_MODEL = "related_model"
    PATHWAY_ONLY = "pathway_only"


class CandidateState(StrEnum):
    DISCOVERED = "DISCOVERED"
    MECHANISM_MATCH = "MECHANISM_MATCH"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_APPROVED = "NOT_APPROVED"


class RejectionReason(StrEnum):
    NOT_APPROVED = "NOT_APPROVED"
    WRONG_DIRECTION = "WRONG_DIRECTION"
    DATABASE_ONLY = "DATABASE_ONLY"
    NO_CAUSAL_BRIDGE = "NO_CAUSAL_BRIDGE"
    FAILED_IN_RELEVANT_MODEL = "FAILED_IN_RELEVANT_MODEL"
    HARMFUL_SIGNAL = "HARMFUL_SIGNAL"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"


class MeasuredEndpoint(BaseModel):
    """"No effect" is meaningless without an endpoint. This is how a failure stays reusable."""

    endpoint: str
    direction: Literal["improved", "unchanged", "worsened", "not_reported"]
    magnitude_if_reported: str | None = None
    timeframe: str | None = None
    system: str | None = Field(None, description="What it was measured in, in the source's own words.")


class EvidenceSource(BaseModel):
    source_id: str
    quote: str
    url: str | None = None
    pub_year: int | None = None
    verified_from_source: bool = False


class InterventionExperience(BaseModel):
    """Something that was actually tried, and what happened.

    Source-agnostic on purpose: a paper, a trial, a case report or a hospital node should all
    populate this unchanged.
    """

    id: str
    intervention_ingredient: str
    intervention_identifiers: dict[str, str] = Field(default_factory=dict)
    disease: str | None = None
    gene: str | None = None
    mechanism: str | None = None
    model: str | None = None
    subject_scope: SubjectScope
    intervention_intent: str = ""
    outcome: Outcome
    measured_endpoints: list[MeasuredEndpoint] = Field(default_factory=list)
    relevant_to: list[str] = Field(default_factory=list, description="Intervention point and spec ids.")
    lane: Lane
    evidence_source: EvidenceSource
    independence_group: str | None = None
    limitations: list[str] = Field(default_factory=list)
    extracted_by: str = ""


class ApprovalRecord(BaseModel):
    """Verified against a regulator's own data, never because a paper called something 'a drug'."""

    verified: bool = False
    ingredient: str
    jurisdictions: list[str] = Field(default_factory=list)
    authority_source: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    indications_sampled: list[str] = Field(default_factory=list)
    retrieved_at: str | None = None
    query: str | None = None
    note: str = ""


class MechanismMatch(BaseModel):
    """Does what it does point the way the mechanism needs? Direction decides, not pathway membership."""

    intervention: str
    specification: str
    required_effect: str
    observed_or_reported_effect: str
    direction: Literal["concordant", "discordant", "unknown"]
    evidence_directness: Directness
    establishing_evidence: list[str] = Field(default_factory=list)
    related_evidence: list[str] = Field(default_factory=list)
    status: MatchStatus
    basis: str = ""


class PediatricMetadata(BaseModel):
    """Collected, never evaluated here. Stage 09 assesses; this only records what exists."""

    pediatric_labelling_found: bool | None = None
    note: str = "not evaluated at this stage"
    sources: list[str] = Field(default_factory=list)


class MedicationCandidate(BaseModel):
    id: str
    ingredient: str
    canonical_ids: dict[str, str] = Field(default_factory=dict)
    approval: ApprovalRecord
    intervention_point: str
    specification: str
    proposed_effect: str = ""
    required_direction: str = ""
    mechanism_match: MechanismMatch | None = None
    direct_gene_evidence: list[str] = Field(default_factory=list)
    experiences_positive: list[str] = Field(default_factory=list)
    experiences_negative: list[str] = Field(default_factory=list)
    experiences_harmful: list[str] = Field(default_factory=list)
    experiences_mixed: list[str] = Field(default_factory=list)
    experiences_unknown: list[str] = Field(
        default_factory=list,
        description="Tried-or-considered with no measured outcome — e.g. a clinician's decision to withhold. "
                    "Informative, and not the same as observed harm.")
    adversarial_search_performed: bool = False
    adversarial_search_note: str = ""
    forbidden_direction_conflict: str | None = None
    pediatric_metadata: PediatricMetadata = Field(default_factory=PediatricMetadata)
    independence_groups: list[str] = Field(default_factory=list)
    state: CandidateState = CandidateState.DISCOVERED
    limitations: list[str] = Field(default_factory=list)


class MechanisticReferenceCompound(BaseModel):
    """Not approved, so not a Track 2 candidate — but proof the biology is pharmacologically movable."""

    id: str
    ingredient: str
    what_it_showed: str
    track2_eligible: bool = False
    proves_pharmacologic_modifiability: bool = False
    experiences: list[str] = Field(default_factory=list)
    follow_up_question: str = ("is there an approved medication producing the same relevant molecular effect? "
                               "Sharing a nominal target is not the same effect.")


class RejectedCandidate(BaseModel):
    intervention: str
    discovered_because: str
    rejected_because: RejectionReason
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)
    lane: Lane | None = None


class NodeQuerySpec(BaseModel):
    """A question for a future network node. Generated here, not sent."""

    id: str
    question: str
    desired_evidence: list[str] = Field(default_factory=list)
    useful_negative_result: bool = True
    patient_identity_required: bool = False
    acceptable_output: list[str] = Field(default_factory=lambda: ["aggregate", "deidentified_summary",
                                                                  "local_computation_result"])
    disclosure_level: str = "disease_gene_level"
    arises_from: str = Field("", description="The unresolved evidence need that produced this question.")
    sent: bool = False


class SearchRecord(BaseModel):
    lane: Lane
    knowledge_task: str | None = None
    queries: list[str] = Field(default_factory=list)
    documents: int = 0
    interventions_named: int = 0
    note: str = ""


class Provenance(BaseModel):
    software: SoftwareProvenance
    intervention_map_run_id: str
    intervention_map_digest: str | None = None
    specifications_consumed: list[str] = Field(default_factory=list)
    research_sessions: list[str] = Field(default_factory=list)
    approval_sources: list[str] = Field(default_factory=list)
    disclosure_policy: str = ("Retrieval is gene-, mechanism-, disease- and drug-level. No exact patient variant, "
                              "allele, HGVS or phenotype combination enters any external query.")
    environment_controls: list[str] = Field(default_factory=list)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    intervention_map_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class InterventionDiscovery(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    gene_symbol: str
    status: Status
    status_basis: str
    interpretation_note: str = ("Discovered interventions with the evidence for and against them. Not a ranking, "
                                "not a dose, not a recommendation, and not medical advice. An approved medicine "
                                "appearing here means evidence exists worth examining — nothing more.")
    candidates: list[MedicationCandidate] = Field(default_factory=list)
    experiences: list[InterventionExperience] = Field(default_factory=list)
    reference_compounds: list[MechanisticReferenceCompound] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    node_query_specs: list[NodeQuerySpec] = Field(default_factory=list)
    searches: list[SearchRecord] = Field(default_factory=list)
    untested_note: str = ("Interventions for which no experience was found are recorded as UNKNOWN, never as "
                          "failures. A search that found nothing is not a negative result.")
    unresolved_evidence_needs: list[str] = Field(default_factory=list)
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
