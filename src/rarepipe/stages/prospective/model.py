"""Stage 10 — prospective experiment and decision plan: the normative contracts (PRD §13).

A plan turns an unresolved hypothesis into conditional forecasts, proposed experiments, interpretable
outcome branches and accountable next actions. Three rules run through every object here:

  * Evidence and forecasts stay distinct (FR-001). A statement's type is data, not a display label.
  * Uncertainty is explicit (FR-003). "Unknown", "not measured", "not reported", "unavailable",
    "inconclusive", "evidence against" and "not applicable" are different states, and a missing
    number is null with a reason, never zero.
  * Nothing here prescribes, administers or recommends a treatment (FR-007). No state or action in
    this module reaches a patient.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_NAME = "ProspectivePlan"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "prospective_plan"
STAGE_VERSION = "0.1.0"
CANONICALIZATION = "rarepipe-canonical-json-v1: UTF-8 JSON, keys sorted, no insignificant whitespace, floats as repr"


# ── statement types and uncertainty ──────────────────────────────────────────


class StatementType(StrEnum):
    OBSERVATION = "observation"
    LITERATURE_CLAIM = "literature_claim"
    HYPOTHESIS = "hypothesis"
    ASSUMPTION = "assumption"
    CONDITIONAL_FORECAST = "conditional_forecast"
    SIMULATION_OUTPUT = "simulation_output"
    PROPOSED_ACTION = "proposed_action"


class Knowledge(StrEnum):
    """FR-003. Each means something different; none of them means zero."""

    UNKNOWN = "UNKNOWN"
    NOT_MEASURED = "NOT_MEASURED"
    NOT_REPORTED = "NOT_REPORTED"
    UNAVAILABLE = "UNAVAILABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    EVIDENCE_AGAINST = "EVIDENCE_AGAINST"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Quantity(BaseModel):
    """A number that may be missing — but only with a reason."""

    value: float | None = None
    unit: str | None = None
    null_reason: Knowledge | None = None
    note: str = ""

    @model_validator(mode="after")
    def _null_needs_reason(self):
        if self.value is None and self.null_reason is None:
            raise ValueError("a missing number needs a null_reason (FR-003); it is never zero")
        if self.value is not None and self.null_reason is not None:
            raise ValueError("a number with a value cannot also carry a null_reason")
        return self


# ── lifecycle ────────────────────────────────────────────────────────────────


class PlanState(StrEnum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY_TO_FREEZE = "READY_TO_FREEZE"
    FROZEN = "FROZEN"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


class ExecutionState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    RESULTS_PENDING = "RESULTS_PENDING"
    RESULT_RECEIVED = "RESULT_RECEIVED"
    RESULT_REVIEW_REQUIRED = "RESULT_REVIEW_REQUIRED"
    CLOSED = "CLOSED"


class ForecastMode(StrEnum):
    QUALITATIVE_CONDITIONAL = "QUALITATIVE_CONDITIONAL"
    QUANTITATIVE_EXPLORATORY = "QUANTITATIVE_EXPLORATORY"
    QUANTITATIVE_VALIDATED_FOR_CONTEXT = "QUANTITATIVE_VALIDATED_FOR_CONTEXT"


class TemporalStatus(StrEnum):
    PRE_RESULT_EVIDENCED = "PRE_RESULT_EVIDENCED"
    TEMPORAL_STATUS_UNVERIFIED = "TEMPORAL_STATUS_UNVERIFIED"
    POST_RESULT_AMENDMENT = "POST_RESULT_AMENDMENT"


class EvaluationMode(StrEnum):
    PROSPECTIVE_NEW_RESULT = "PROSPECTIVE_NEW_RESULT"
    BLINDED_EXISTING_RESULT = "BLINDED_EXISTING_RESULT"
    RETROSPECTIVE_REPLAY = "RETROSPECTIVE_REPLAY"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"


class Applicability(StrEnum):
    """Model hierarchy (§8.2). Each label travels with every forecast and export."""

    EXACT_ALLELE_ENGINEERED = "EXACT_ALLELE_ENGINEERED"
    COMPLETE_GENOTYPE = "COMPLETE_GENOTYPE"
    PATIENT_DERIVED = "PATIENT_DERIVED"
    GENERIC_BUB1B_DEFICIENT = "GENERIC_BUB1B_DEFICIENT"
    NOT_SPECIFIED = "NOT_SPECIFIED"


class ExperimentKind(StrEnum):
    ALLELE_FUNCTION = "ALLELE_FUNCTION"
    DRUG_MECHANISM_FUNCTION = "DRUG_MECHANISM_FUNCTION"
    REPLICATION_RELEVANCE = "REPLICATION_RELEVANCE"


# ── actors, roles and reviews ────────────────────────────────────────────────


class ActorType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class Role(StrEnum):
    TREATING_CLINICIAN = "treating_clinician"
    SCIENTIFIC_LEAD = "scientific_lead"
    RESEARCH_OPERATIONS = "research_operations"
    ASSAY_SCIENTIST = "assay_scientist"
    STATISTICIAN = "statistician"
    ENGINEER = "engineer"
    PATIENT_OR_CAREGIVER = "patient_or_caregiver"
    CLINICAL_PHARMACOLOGIST = "clinical_pharmacologist"
    DATA_HOLDER = "data_holder"


class Actor(BaseModel):
    actor_type: ActorType
    identity: str
    roles: list[Role] = Field(default_factory=list)
    model_or_provider: str | None = Field(None, description="For agents: model/provider/version (§15).")


class ReviewDecision(StrEnum):
    ACCEPT_INTERPRETATION = "ACCEPT_INTERPRETATION"
    AMEND_WITH_REASON = "AMEND_WITH_REASON"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    DEFER_DECISION = "DEFER_DECISION"
    APPROVE_FOR_FREEZE = "APPROVE_FOR_FREEZE"
    REJECT = "REJECT"


class ReviewRecord(BaseModel):
    review_id: str
    actor: Actor
    role: Role = Field(description="The capacity in which this decision was made (§3).")
    object_ref: str
    object_version: str
    decision: ReviewDecision
    rationale: str
    timestamp: str
    authority: str = ""


# ── plan contents ────────────────────────────────────────────────────────────


class Unresolved(BaseModel):
    """A missing field, made actionable: which field, why it matters, who owns it (§16.2)."""

    object_ref: str
    field: str
    reason: str
    owner: Role
    blocks: Literal["scientific_freeze", "interpretation", "applicability", "quantitative_claims",
                    "clinical_translation", "external_node_use", "real_experiment_readiness"]


class Scope(BaseModel):
    """FR-002: scope follows the experimental system."""

    species: str | None = None
    tissue_or_cell: str | None = None
    genotype_relationship: Literal["gene_level", "variant_class", "exact_allele", "complete_genotype",
                                   "not_specified"] = "not_specified"
    intervention: str | None = None
    exposure: str | None = None
    timeframe: str | None = None
    endpoint: str | None = None
    comparator: str | None = None


class EvidenceRef(BaseModel):
    ref: str = Field(description="Artifact id in the pinned baseline, e.g. VX_0007, MC_0012, PMID:24825348.")
    statement_type: StatementType
    scope_note: str = ""
    independence_group: str | None = None
    overlaps_with: list[str] = Field(default_factory=list, description="FR-006: not independent of these.")


class Assumption(BaseModel):
    id: str
    statement: str
    depends_on: list[str] = Field(default_factory=list, description="Baseline refs this assumption rests on.")
    status: Knowledge | Literal["ASSUMED"] = "ASSUMED"


class Hypothesis(BaseModel):
    id: str
    statement: str
    level: Literal["allele_function", "drug_upstream", "drug_mechanism", "cellular_function", "alternative_mechanism",
                   "confounding", "translation"]
    statement_type: StatementType = StatementType.HYPOTHESIS
    dependencies: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    scope: Scope = Field(default_factory=Scope)
    assessment: Literal["UNRESOLVED", "STRENGTHENED", "WEAKENED", "UNDER_INVESTIGATION", "NOT_ASSESSED"] = "UNRESOLVED"
    assessment_note: str = "outcome unknown for this child's exact genotype"
    distinguished_by: str = ""
    falsification: str = ""


class EndpointSpec(BaseModel):
    id: str
    key: str = Field(description="The observation-vector key the rules read, e.g. checkpoint_silencing.")
    biological_meaning: str
    method: str | None = None
    unit: str | None = None
    denominator: str | None = Field(None, description="e.g. 'per viable assessable division'.")
    comparator: str | None = None
    desired: str = Field(description="Direction or justified reference range; a prolonged arrest is not "
                                     "automatically better (FR-004).")
    window: str | None = None
    required: bool = True
    validity_criteria: str | None = None
    effect_criterion: Quantity = Field(default_factory=lambda: Quantity(null_reason=Knowledge.UNKNOWN,
                                                                        note="set by the assay scientist"))
    threshold_version: str | None = None
    owner: Role = Role.ASSAY_SCIENTIST


class AnalysisSpec(BaseModel):
    """§8.4. Every field None until a named owner supplies it."""

    experimental_unit: str | None = None
    replication: str | None = None
    allocation_and_blinding: str | None = None
    primary_endpoints: list[str] = Field(default_factory=list)
    secondary_endpoints: list[str] = Field(default_factory=list)
    effect_scale: str | None = None
    analysis_population: str | None = None
    denominators: str | None = None
    time_windows: str | None = None
    missing_data_and_exclusions: str | None = None
    multiplicity: str | None = None
    meaningful_effect: str | None = None
    uncertainty_method: str | None = None
    repeat_or_termination: str | None = None


ANALYSIS_REQUIRED = ("experimental_unit", "replication", "allocation_and_blinding", "effect_scale",
                     "analysis_population", "denominators", "time_windows", "missing_data_and_exclusions",
                     "multiplicity", "meaningful_effect", "uncertainty_method", "repeat_or_termination")


class ModelRequirement(BaseModel):
    applicability: Applicability
    requirement: str
    availability: Knowledge | Literal["AVAILABLE", "PERMITTED"] = Knowledge.UNKNOWN
    private_ref: str | None = Field(None, description="Opaque reference that resolves only inside the "
                                                      "authorized environment (§13.1). Never a variant.")


class ExperimentSpec(BaseModel):
    id: str
    kind: ExperimentKind
    decision_question: str
    model_requirements: list[ModelRequirement] = Field(default_factory=list)
    intervention: str | None = None
    comparators: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list, description="EndpointSpec ids.")
    controls: list[str] = Field(default_factory=list)
    analysis: AnalysisSpec = Field(default_factory=AnalysisSpec)
    interpretation: str = ""
    feasibility: Knowledge | Literal["FEASIBLE", "NOT_FEASIBLE"] = Knowledge.UNKNOWN
    owners: list[Role] = Field(default_factory=list)
    trigger: str | None = None


class Uncertainty(BaseModel):
    """FR-013: kept apart; unquantified is said out loud."""

    model: str = "UNQUANTIFIED"
    parameter: str = "UNQUANTIFIED"
    measurement: str = "UNQUANTIFIED"
    biological: str = "UNQUANTIFIED"


class OutcomeAvailability(BaseModel):
    """FR-014. A hash proves byte identity, not that the author had never seen a result."""

    planned_start: str | None = None
    actual_start: str | None = None
    earliest_result_generation: str | None = None
    first_result_access: str | None = None
    timestamp_evidence: list[str] = Field(default_factory=list)
    status: TemporalStatus = TemporalStatus.TEMPORAL_STATUS_UNVERIFIED


class Forecast(BaseModel):
    id: str
    hypothesis: str
    experiment: str
    endpoint: str
    intervention_or_comparator: str
    statement_type: StatementType = StatementType.CONDITIONAL_FORECAST
    prediction: str
    expected_direction: str
    window: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    evidence_snapshot: str = Field(description="Baseline semantic digest the forecast was made against.")
    disconfirming_pattern: str
    branch_actions: dict[str, str] = Field(default_factory=dict)
    model_applicability: Applicability
    cannot_conclude: list[str] = Field(default_factory=list)
    mode: ForecastMode = ForecastMode.QUALITATIVE_CONDITIONAL
    probability: float | None = None
    probability_null_reason: str | None = "no calibrated probability model exists for this event (FR-012)"
    calibration_ref: str | None = None
    uncertainty: Uncertainty = Field(default_factory=Uncertainty)
    temporal: OutcomeAvailability = Field(default_factory=OutcomeAvailability)

    @model_validator(mode="after")
    def _probability_needs_basis(self):
        if self.probability is None and not self.probability_null_reason:
            raise ValueError("a null probability needs a reason (FR-012)")
        if self.probability is not None:
            if self.mode is ForecastMode.QUALITATIVE_CONDITIONAL:
                raise ValueError("a qualitative forecast carries no numeric probability")
            if not self.calibration_ref:
                raise ValueError("a numeric probability needs calibration evidence (FR-012)")
            self.probability_null_reason = None
        return self


class RuleDescriptor(BaseModel):
    """The serialized face of a rule implemented in rules.py; pinned in every plan version."""

    id: str
    version: str
    branch: str
    applies_to: list[ExperimentKind]
    required_inputs: list[str]
    actions: list[str]
    rationale: str


class ResearchTask(BaseModel):
    id: str
    origin: str = Field(description="Branch, decision or plan element that created it.")
    type: str
    description: str
    owner: Role
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["PROPOSED", "OPEN", "BLOCKED", "DONE", "CANCELLED"] = "PROPOSED"
    estimated_cost: Quantity = Field(default_factory=lambda: Quantity(null_reason=Knowledge.UNKNOWN))
    estimated_time: Quantity = Field(default_factory=lambda: Quantity(null_reason=Knowledge.UNKNOWN))
    external_action_authorized: bool = False
    completion_evidence: str | None = None


class CapabilityRequestType(StrEnum):
    FIND_EXISTING_RESULT = "FIND_EXISTING_RESULT"
    ASSESS_MODEL_AVAILABILITY = "ASSESS_MODEL_AVAILABILITY"
    ASSESS_ASSAY_CAPABILITY = "ASSESS_ASSAY_CAPABILITY"
    REQUEST_FEASIBILITY_ESTIMATE = "REQUEST_FEASIBILITY_ESTIMATE"


class CapabilityRequest(BaseModel):
    """FR-030: extends NodeQuerySpecification. Drafts only; nothing is sent in this deployment."""

    id: str
    type: CapabilityRequestType
    extends_node_query_spec: str | None = None
    decision_it_could_change: str
    required_capability: str
    permitted_scope: str
    useful_positive_output: str
    useful_negative_output: str
    minimum_metadata: list[str] = Field(default_factory=list)
    local_compute_restrictions: str = "answer locally; return only an approved summary"
    authorization_requirements: str = "institutional authorization, permitted purpose and output disclosure check"
    owner: Role = Role.RESEARCH_OPERATIONS
    recheck_by: str | None = None
    status: Literal["DRAFT_UNSENT"] = "DRAFT_UNSENT"


class BaselineRef(BaseModel):
    package_path: str
    package_sha256: str
    manifest_entries: int
    manifest_verified: bool
    stage_runs: dict[str, str]
    semantic_digests: dict[str, str]
    digest_algorithm: str = "sha256 over sorted-key JSON of the sanitized artifact minus execution (rarepipe.core.digest)"
    code_commit: str | None = None
    git_describe: str | None = None
    corpus_snapshot: str | None = None
    status: Literal["CANDIDATE", "FROZEN"] = "CANDIDATE"
    known_limitations: list[str] = Field(default_factory=list)
    residual_function: dict | None = None
    hypothesis_versions: dict[str, str] = Field(default_factory=dict)


class ProspectivePlan(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    plan_id: str
    version_id: str | None = None
    parent_version: str | None = None
    change_reason: str = "initial draft"
    change_kind: Literal["initial", "scientific", "editorial", "operational", "post_result_amendment"] = "initial"
    case_ref: str
    decision_question: str
    patient_relevant_goal: str | None = None
    lifecycle: PlanState = PlanState.DRAFT
    synthetic_fixture: bool = Field(False, description="A software fixture; freezing it preregisters nothing.")
    evaluation_mode: EvaluationMode = EvaluationMode.PROSPECTIVE_NEW_RESULT
    baseline: BaselineRef
    owner: Role = Role.SCIENTIFIC_LEAD
    policy: str = "challenge-deployment-v1"
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    endpoints: list[EndpointSpec] = Field(default_factory=list)
    experiments: list[ExperimentSpec] = Field(default_factory=list)
    forecasts: list[Forecast] = Field(default_factory=list)
    rules: list[RuleDescriptor] = Field(default_factory=list)
    rules_version: str | None = None
    reviews: list[ReviewRecord] = Field(default_factory=list)
    tasks: list[ResearchTask] = Field(default_factory=list)
    capability_requests: list[CapabilityRequest] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    outcome_availability: OutcomeAvailability | None = None
    temporal_status: TemporalStatus = TemporalStatus.TEMPORAL_STATUS_UNVERIFIED
    not_established: list[str] = Field(default_factory=lambda: [
        "a treatment", "that any laboratory experiment has been run", "a prescription or dose",
        "a validated simulation of this child"])
    content_digest: str | None = None

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


# ── observations and decisions ───────────────────────────────────────────────

CATEGORIES = ("improved", "unchanged", "worsened", "increased", "decreased", "present", "absent", "matched",
              "not_matched", "normal", "impaired", "partial", "yes", "no")


class ObservationValue(BaseModel):
    endpoint_key: str
    quantity: Quantity | None = None
    uncertainty: str | None = None
    denominator: str | None = None
    denominator_n: int | None = None
    category: Literal[CATEGORIES] | Knowledge | None = None  # type: ignore[valid-type]
    analysis_ref: str | None = None
    threshold_version: str | None = None
    derivation: str | None = None
    adjudicated_by: str | None = Field(None, description="Human author of a manually adjudicated category (§13.2).")


class QualityChecks(BaseModel):
    identity_verified: bool | None = None
    provenance_verified: bool | None = None
    controls_valid: bool | None = None
    precision_adequate: bool | None = None
    protocol_deviations: list[str] = Field(default_factory=list)
    critical_adverse_flag: bool | None = None


class ModelIdentity(BaseModel):
    applicability: Applicability
    genotype_verified_locally: bool | None = None
    private_ref: str | None = None
    independent_execution: str | None = Field(None, description="What makes this execution independent (§8.3).")


class Observation(BaseModel):
    observation_id: str | None = None
    experiment_id: str
    execution_ref: str
    origin: Literal["REAL", "SYNTHETIC"]
    evaluation_mode: EvaluationMode
    raw_result_sha256: str
    values: list[ObservationValue]
    qc: QualityChecks = Field(default_factory=QualityChecks)
    model_identity: ModelIdentity
    independence_group: str | None = None
    timing: dict[str, str] = Field(default_factory=dict)
    disclosure_policy: Literal["private", "sanitized_ok"] = "private"
    replication_of: str | None = None
    context: dict[str, str] = Field(default_factory=dict, description="e.g. exposure_feasible, relevance_review.")


class DecisionRecord(BaseModel):
    decision_id: str
    plan_id: str
    plan_version: str
    observation_id: str | None
    scenario: bool = Field(False, description="True for previews: never a real decision.")
    rules_version: str
    pinned_inputs_digest: str
    predicates: dict[str, str]
    matches: list[str]
    inadmissible_matches: list[str] = Field(default_factory=list)
    unknown_inputs: list[str] = Field(default_factory=list)
    information_requests: list[str] = Field(default_factory=list)
    proposed_actions: list[str]
    conflicting_actions: list[list[str]] = Field(default_factory=list)
    status: Literal["PROPOSED", "DECISION_REVIEW_REQUIRED", "REVIEWED"] = "PROPOSED"
    interpretation: list[str] = Field(default_factory=list)
    cannot_conclude: list[str] = Field(default_factory=list)
    hypothesis_updates: dict[str, str] = Field(default_factory=dict)
    proposed_tasks: list[ResearchTask] = Field(default_factory=list)
    selected_actions: list[str] = Field(default_factory=list)
    review: ReviewRecord | None = None
    review_version: int = 0
    case_state_delta: dict[str, str] = Field(default_factory=dict)


class SimulationRun(BaseModel):
    """P1 contract (§11.2); defined now so outputs can never be mistaken for observations."""

    run_id: str
    statement_type: Literal[StatementType.SIMULATION_OUTPUT] = StatementType.SIMULATION_OUTPUT
    model_hash: str
    input_hash: str
    environment_hash: str
    parameters: dict[str, Quantity] = Field(default_factory=dict)
    parameter_provenance: dict[str, str] = Field(default_factory=dict)
    seed: int | None = None
    outcome: Literal["SUCCEEDED", "FAILED"]
    outputs: dict[str, Quantity] = Field(default_factory=dict)
    limits: list[str] = Field(default_factory=list)
    validation_scope: str = "EXPLORATORY: no validation for this context"
    synthetic: bool = True
