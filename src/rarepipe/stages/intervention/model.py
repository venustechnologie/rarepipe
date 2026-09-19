"""InterventionMap — what a treatment would have to accomplish, before anyone names a treatment.

Stage 07 does not rank drugs, search drug databases or recommend anything. It converts a supported
mechanism into the middle layer a drug search is otherwise missing: which biological state, moved in
which direction, measured by which endpoint, and which directions would be expected to make things
worse.

Three distinctions the schema enforces, each learned from a mistake the pipeline nearly made:

1. A high computational signal is not a mechanism. `MechanisticAxis` records what supports an axis
   at each level separately, so a prediction can support a working hypothesis without becoming one.
2. A weak model signal is not a refutation. `NegativePredictionEvidence` deprioritizes an axis and
   states in the object itself that it does not establish absence.
3. Two scores are not two witnesses. `independence_group` marks evidence that shares a source model,
   so nothing can claim independent support from a model that embeds another.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "InterventionMap"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "intervention_logic"
STAGE_VERSION = "0.1.0"


class Status(StrEnum):
    READY = "INTERVENTION_LOGIC_READY_FOR_APPROVED_DRUG_SEARCH"
    BLOCKED = "INTERVENTION_LOGIC_BLOCKED"


class AxisState(StrEnum):
    """Never a permanent exclusion on one model's weak prediction."""

    ACTIVE = "ACTIVE"
    DEPRIORITIZED = "DEPRIORITIZED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class Role(StrEnum):
    """What kind of thing an intervention point is. Decisive once drug targets start arriving."""

    ROOT_CAUSE = "root_cause"
    PROXIMAL_MECHANISM = "proximal_mechanism"
    INTERMEDIATE_MECHANISM = "intermediate_mechanism"
    DOWNSTREAM_PHENOTYPE = "downstream_phenotype"
    BIOMARKER = "biomarker"


class Direction(StrEnum):
    RESTORE = "restore_toward_normal"
    INCREASE = "increase"
    DECREASE = "decrease"
    STABILISE = "stabilise"
    NORMALISE = "normalise"
    UNKNOWN = "unknown"


class PointStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNRESOLVED = "UNRESOLVED"
    DEPRIORITIZED = "DEPRIORITIZED"
    NOT_JUSTIFIED = "NOT_JUSTIFIED"


class Priority(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    SPECULATIVE = "speculative"


class Scope(StrEnum):
    EXACT_VARIANT = "exact_variant"
    VARIANT_CLASS = "variant_class"
    GENE_LEVEL = "gene_level"
    PATHWAY_LEVEL = "pathway_level"
    CELLULAR_PROCESS = "cellular_process"
    DISEASE_LEVEL = "disease_level"


class AxisSupport(BaseModel):
    """Support recorded per level, never collapsed — the precedence order is the point."""

    human_experimental: bool = False
    curated_human_evidence: bool = False
    primary_literature: bool = False
    human_class_level: bool = False
    exact_variant_experimental: bool = False
    computational_exact_variant: bool = False
    supporting_claims: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)


class CandidateAxis(BaseModel):
    """An axis considered and set aside, with the conditions that would reopen it."""

    axis: str
    state: AxisState
    reason: str
    evidence_type: Literal["human_experimental", "primary_literature", "computational", "none"] = "none"
    reopen_if: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class MechanisticAxis(BaseModel):
    """A level at which the disease process could be engaged, and what actually supports it."""

    id: str
    biological_level: Literal["transcript", "protein", "complex", "cellular_process", "cellular_state", "clinical"]
    state: str
    support: AxisSupport
    competing_axes: list[CandidateAxis] = Field(default_factory=list)
    confidence: Literal["low", "moderate", "high"]
    limitations: list[str] = Field(default_factory=list)


class NegativePredictionEvidence(BaseModel):
    """A model that did not light up. Recorded as a reason to deprioritize, never as a refutation."""

    hypothesis: str
    result: Literal["no_material_positive_signal", "weak_positive_signal"] = "no_material_positive_signal"
    source: str
    scope: Scope
    strength: Literal["computational_only"] = "computational_only"
    consequence: Literal["deprioritize"] = "deprioritize"
    does_not_establish: str = "absence of the effect: no experiment was performed"
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)


class DesiredEffect(BaseModel):
    """A target with no direction is how a search finds a compound that pushes the wrong way."""

    target_state: str
    current_state: str
    desired_state: str
    direction: Direction
    evidence: list[str] = Field(default_factory=list)
    confidence: Literal["low", "moderate", "high"]


class ForbiddenEffect(BaseModel):
    """Mechanistic contradiction detection, not clinical safety advice.

    Derived only from the mechanism graph and functional evidence. A computational prediction says
    what an allele may do; it never establishes which therapeutic direction is dangerous.
    """

    biological_state: str
    prohibited_direction: Direction
    reason: str
    evidence: list[str] = Field(default_factory=list)
    derived_from: Literal["mechanism_graph", "functional_evidence"] = "mechanism_graph"


class ReversibilityClaim(BaseModel):
    biological_state: str
    timing: Literal["developmental", "ongoing", "both", "unknown"] = "unknown"
    reversible: Literal["supported", "partially_supported", "unsupported", "unknown"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    note: str = ""


class ValidationEndpoints(BaseModel):
    """Only endpoints the dossier's own assay inventory supports."""

    proximal: list[str] = Field(default_factory=list)
    cellular: list[str] = Field(default_factory=list)
    disease_related: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class MindChanger(BaseModel):
    would_strengthen: str = ""
    would_weaken: str = ""
    would_falsify: str = ""


class InterventionPoint(BaseModel):
    id: str
    biological_state: str
    role: Role
    desired_effect: DesiredEffect
    rationale: str
    mechanism_claims: list[str] = Field(default_factory=list)
    evidence_scope: Scope
    axis: str | None = None
    expected_downstream_effect: str = ""
    rescue_evidence: list[str] = Field(default_factory=list, description="Evidence where changing this state "
                                                                        "restored a phenotype, not merely correlated.")
    validation_endpoints: ValidationEndpoints = Field(default_factory=ValidationEndpoints)
    reversibility: ReversibilityClaim | None = None
    directness: Literal["upstream", "intermediate", "downstream"] = "intermediate"
    requires_exact_allele_mechanism: bool = False
    status: PointStatus = PointStatus.UNRESOLVED
    priority: Priority = Priority.SPECULATIVE
    confidence: Literal["low", "moderate", "high", "unresolved"] = "unresolved"
    limitations: list[str] = Field(default_factory=list)
    contraindicated_direction: str | None = None
    what_would_change_our_mind: MindChanger = Field(default_factory=MindChanger)
    track2_relevance: Literal["high", "moderate", "low"] = "moderate"


class InterventionSearchSpec(BaseModel):
    """What Stage 08 is allowed to search for. Not a gene name — a biological effect with a direction."""

    spec_id: str
    intervention_point: str
    biological_target: str
    desired_effect: Direction
    acceptable_mechanisms: list[str] = Field(default_factory=list)
    disallowed_mechanisms: list[str] = Field(default_factory=list)
    expected_rescue_readout: list[str] = Field(default_factory=list)
    minimum_evidence: Literal["mechanistic", "cellular", "clinical"] = "mechanistic"
    patient_specificity: Scope = Scope.DISEASE_LEVEL
    exact_allele_dependency: bool = False
    constraints: dict = Field(default_factory=lambda: {"pediatric_case": True})
    uncertainties: list[str] = Field(default_factory=list)


class ActionOutcome(BaseModel):
    """What the research action actually bought us. The trace that will eventually teach us which to take."""

    action: str
    expected_gain: Literal["high", "moderate", "low"]
    actual_result: str
    information_gain: Literal["high", "moderate", "low", "none"]
    case_state_change: str = "none"
    lesson: str = ""


class Provenance(BaseModel):
    software: SoftwareProvenance
    mechanism_run_id: str
    mechanism_digest: str | None = None
    mechanism_status: str | None = None
    validation_run_id: str | None = None
    alphagenome_used: bool = False
    research_sessions: list[str] = Field(default_factory=list)
    evidence_precedence: list[str] = Field(default_factory=lambda: [
        "human experimental", "curated human evidence", "primary literature", "computational prediction"])
    disclosure_policy: str = ("No case-specific identity is transmitted. Intervention research queries are "
                              "gene-, protein- and disease-level, and are additionally refused if they look "
                              "like a search for a treatment.")
    environment_controls: list[str] = Field(default_factory=list)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    mechanism_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class InterventionMap(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    gene_symbol: str
    status: Status
    status_basis: str
    interpretation_note: str = ("Intervention logic: what a treatment would have to accomplish. Not a treatment "
                                "plan, not medical advice, and not a drug candidate list. No medication is named, "
                                "ranked or recommended at this stage.")
    axes: list[MechanisticAxis] = Field(default_factory=list)
    intervention_points: list[InterventionPoint] = Field(default_factory=list)
    forbidden_effects: list[ForbiddenEffect] = Field(default_factory=list)
    negative_predictions: list[NegativePredictionEvidence] = Field(default_factory=list)
    deprioritized_axes: list[CandidateAxis] = Field(default_factory=list)
    not_currently_justified: list[str] = Field(default_factory=list)
    unresolved_points: list[str] = Field(default_factory=list)
    search_specs: list[InterventionSearchSpec] = Field(default_factory=list)
    action_outcomes: list[ActionOutcome] = Field(default_factory=list)
    knowledge_tasks: list[dict] = Field(default_factory=list)
    readiness: dict = Field(default_factory=dict)
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
