"""Research-network records (PRD §8).

Records are immutable snapshots: corrections create successors, never rewrite origin.
Operational knowledge cannot masquerade as a scientific finding. These contracts do not
send requests, accept scientific edits, or grant authority to execute physical work.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rarepipe.stages.prospective.model import Actor, ActorType, Knowledge, Quantity, Role
from rarepipe.stages.prospective.nodes import EvidenceEnvelope, ResponseState


def new_id() -> str:
    return str(uuid4())


def unknown_quantity() -> Quantity:
    return Quantity(null_reason=Knowledge.UNKNOWN)


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    def model_copy(self, *, update=None, deep=False):
        # Pydantic's default copy(update=...) bypasses validators, including origin checks.
        if update:
            raise ValueError("create and validate a successor record instead of updating a snapshot")
        return super().model_copy(deep=deep)


class Origin(StrEnum):
    PUBLIC_EVIDENCE = "public_evidence"
    AUTHENTIC_INSTITUTIONAL = "authentic_institutional"
    SYNTHETIC = "synthetic"


class UsePurpose(StrEnum):
    CASE_USE = "case_use"
    PUBLIC_EXPORT = "public_export"
    OTHER_CASE = "other_case"
    POLICY_TRAINING = "policy_training"


class Restrictions(ImmutableModel):
    """Each use needs its own grant; permission for one case is not a general license."""

    case_ref: str | None = None
    case_use: bool = False
    public_export: bool = False
    other_case: bool = False
    policy_training: bool = False
    conditions: tuple[str, ...] = ()
    revoked: bool = False

    @model_validator(mode="after")
    def _case_grant_is_scoped(self):
        if self.case_use and not self.case_ref:
            raise ValueError("case use requires a case reference")
        return self

    def may_use(self, purpose: UsePurpose, *, case_ref: str | None = None) -> bool:
        purpose = UsePurpose(purpose)
        if self.revoked:
            return False
        if purpose is UsePurpose.CASE_USE:
            return self.case_use and case_ref == self.case_ref
        return getattr(self, purpose.value)


class Lineage(ImmutableModel):
    """Full ancestry preserves synthetic origin and inherited restrictions through derivation."""

    record_id: str
    origin: Origin
    restrictions: Restrictions = Field(default_factory=Restrictions)
    parents: tuple[Lineage, ...] = ()

    @model_validator(mode="after")
    def _inherited_origin(self):
        if self.parents and self.origin != inherited_origin(self.parents):
            raise ValueError("derived origin must inherit its parents' lineage")
        return self

    def may_use(self, purpose: UsePurpose, *, case_ref: str | None = None) -> bool:
        return self.restrictions.may_use(purpose, case_ref=case_ref) and all(
            parent.may_use(purpose, case_ref=case_ref) for parent in self.parents)


def inherited_origin(parents: tuple[Lineage, ...]) -> Origin:
    origins = {parent.origin for parent in parents}
    if Origin.SYNTHETIC in origins:
        return Origin.SYNTHETIC
    if Origin.AUTHENTIC_INSTITUTIONAL in origins:
        return Origin.AUTHENTIC_INSTITUTIONAL
    return Origin.PUBLIC_EVIDENCE


class Record(ImmutableModel):
    id: str = Field(default_factory=new_id)
    origin: Origin
    derived_from: tuple[Lineage, ...] = ()
    restrictions: Restrictions = Field(default_factory=Restrictions)
    supersedes: str | None = None

    @model_validator(mode="after")
    def _lineage(self):
        if self.derived_from and self.origin != inherited_origin(self.derived_from):
            raise ValueError("derived origin must inherit its parents' lineage")
        return self

    def lineage(self) -> Lineage:
        return Lineage(record_id=self.id, origin=self.origin, restrictions=self.restrictions,
                       parents=self.derived_from)

    def may_use(self, purpose: UsePurpose, *, case_ref: str | None = None) -> bool:
        return self.lineage().may_use(purpose, case_ref=case_ref)


class CampaignMode(StrEnum):
    LIVE = "live"
    SYNTHETIC = "synthetic"


class CampaignScope(StrEnum):
    MVA_SCIENTIFIC = "MVA_SCIENTIFIC"
    PARTNERSHIP_ONCOLOGY = "PARTNERSHIP_ONCOLOGY"


class Intervention(StrEnum):
    NICOTINIC_ACID = "nicotinic_acid"
    NAM = "NAM"
    NR = "NR"
    NMN = "NMN"


class Compartment(StrEnum):
    BLOOD = "blood"
    INTRACELLULAR = "intracellular"
    EXTRACELLULAR = "extracellular"


class EvidenceCriteria(ImmutableModel):
    """Unspecified scientific scope stays unspecified, never a wildcard for resolution."""

    intervention: Intervention | Knowledge = Knowledge.UNKNOWN
    compartment: Compartment | Knowledge = Knowledge.UNKNOWN
    species: str | None = None
    model: str | None = None
    tissue_or_cell: str | None = None
    endpoint: str | None = None
    comparator: str | None = None
    exposure: Quantity = Field(default_factory=unknown_quantity)
    method: str | None = None
    experimental_unit: str | None = None
    denominator: str | None = None
    timeframe: str | None = None
    effect_criterion: Quantity = Field(default_factory=unknown_quantity)
    uncertainty_method: str | None = None


class Question(ImmutableModel):
    id: str = Field(default_factory=new_id)
    campaign_id: str
    scope: CampaignScope
    decision: str
    dependencies: tuple[str, ...] = ()
    evidence_criteria: EvidenceCriteria = Field(default_factory=EvidenceCriteria)
    required_reviewer: Role | None = None
    state: Knowledge = Knowledge.UNKNOWN
    native_artifact_refs: tuple[str, ...] = ()


class AdditionalResponseState(StrEnum):
    """Only distinctions missing from the native ResponseState vocabulary."""

    CAPABILITY_REPORTED = "capability_reported"
    NO_RELEVANT_RESOURCE = "no_relevant_resource"
    CANNOT_DISCLOSE = "cannot_disclose"
    DECLINED = "declined"
    INVALID_MEASUREMENT = "invalid_measurement"
    INFORMATIVE_NEGATIVE = "informative_negative"
    # A reply nobody could classify. It asserts nothing about the node and routes to a human.
    # The absence of this state is what made "capability reported" the fallback.
    UNCLASSIFIED = "unclassified"


OperationalState = Literal[
    ResponseState.NO_RELEVANT_DATA, ResponseState.NOT_SEARCHED,
    ResponseState.ACCESS_DENIED, ResponseState.NO_RESPONSE,
    AdditionalResponseState.NO_RELEVANT_RESOURCE,
    AdditionalResponseState.CANNOT_DISCLOSE, AdditionalResponseState.DECLINED,
    AdditionalResponseState.CAPABILITY_REPORTED,
    AdditionalResponseState.UNCLASSIFIED,
]
ScientificState = Literal[
    ResponseState.INCONCLUSIVE_RESULT, ResponseState.MEASURED_NO_EFFECT,
    ResponseState.MEASURED_EFFECT, AdditionalResponseState.INVALID_MEASUREMENT,
    AdditionalResponseState.INFORMATIVE_NEGATIVE,
]


class NetworkEnvelope(EvidenceEnvelope):
    """Native envelope with network distinctions; received text remains inert data."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")
    response_state: ResponseState | AdditionalResponseState


class OperationalResponse(Record):
    kind: Literal["operational"] = "operational"
    state: OperationalState
    envelope: NetworkEnvelope
    resource_available: bool | Knowledge = Knowledge.UNKNOWN
    analysis_permission: bool | Knowledge = Knowledge.UNKNOWN

    @model_validator(mode="after")
    def _state_matches(self):
        if self.envelope.response_state != self.state:
            raise ValueError("envelope and event states disagree")
        if (isinstance(self.resource_available, bool) or isinstance(self.analysis_permission, bool)) and self.state in (
            ResponseState.NO_RESPONSE, ResponseState.NOT_SEARCHED, AdditionalResponseState.DECLINED,
            AdditionalResponseState.CANNOT_DISCLOSE,
        ):
            raise ValueError("this response cannot confirm resource or permission")
        if self.resource_available is True and self.state in (
            AdditionalResponseState.NO_RELEVANT_RESOURCE, ResponseState.NO_RELEVANT_DATA,
        ):
            raise ValueError("no-resource response cannot confirm availability")
        if self.analysis_permission is True and self.state is ResponseState.ACCESS_DENIED:
            raise ValueError("access denial cannot grant analysis permission")
        return self


class ScientificFinding(Record):
    kind: Literal["scientific"] = "scientific"
    state: ScientificState
    envelope: NetworkEnvelope
    context: EvidenceCriteria = Field(default_factory=EvidenceCriteria)
    value: Quantity = Field(default_factory=unknown_quantity)
    uncertainty: Quantity = Field(default_factory=unknown_quantity)
    quality: Knowledge | Literal["VALID"] = Knowledge.UNKNOWN
    limitations: tuple[str, ...] = ()
    not_measured: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _state_matches(self):
        if self.envelope.response_state != self.state:
            raise ValueError("envelope and event states disagree")
        return self

    def matches(self, criteria: EvidenceCriteria) -> bool:
        """Scope compatibility only, never permission to close a scientific gap."""
        if self.quality != "VALID" or self.state in (
            AdditionalResponseState.INVALID_MEASUREMENT, ResponseState.INCONCLUSIVE_RESULT,
        ):
            return False
        if isinstance(criteria.intervention, Knowledge) or isinstance(criteria.compartment, Knowledge):
            return False
        if criteria.endpoint is None:
            return False
        for field in ("intervention", "compartment", "endpoint", "species", "model", "tissue_or_cell",
                      "comparator", "method", "experimental_unit", "denominator", "timeframe"):
            required = getattr(criteria, field)
            if required is not None and getattr(self.context, field) != required:
                return False
        if criteria.exposure.value is not None and self.context.exposure != criteria.exposure:
            return False
        return True


class HumanConfirmation(ImmutableModel):
    """An accountable human confirmation is separate from machine extraction."""

    actor: Actor
    role: Role
    timestamp: datetime
    statement_ref: str
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _human_only(self):
        if self.actor.actor_type is not ActorType.HUMAN:
            raise ValueError("only a human may confirm a statement")
        if self.role not in self.actor.roles:
            raise ValueError("confirmation role must be held by the human")
        return self


class ClaimDirection(StrEnum):
    SUPPORTS = "supports"
    AGAINST = "against"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class ClaimRelation(ImmutableModel):
    claim_id: str
    question: Question
    direction: ClaimDirection = ClaimDirection.UNRESOLVED
    rationale: str
    source_refs: tuple[str, ...] = ()


class IndependenceAssertion(ImmutableModel):
    """Different institutions are not evidence of independent experimental execution."""

    other_family_id: str
    reason: str = Field(min_length=1)
    confirmation: HumanConfirmation


class Contribution(Record):
    campaign_id: str
    scope: CampaignScope
    request_id: str
    responder: str
    source: str
    received_at: datetime
    event: Annotated[OperationalResponse | ScientificFinding, Field(discriminator="kind")]
    evidence_status: Knowledge = Knowledge.UNKNOWN
    permitted_content: str = ""
    extractor: Actor
    human_confirmation: HumanConfirmation | None = None
    relations: tuple[ClaimRelation, ...] = ()
    evidence_family_id: str = Field(min_length=1, description="Shared for reports of one original observation.")
    independence: tuple[IndependenceAssertion, ...] = ()

    @model_validator(mode="after")
    def _attachment(self):
        if self.event.lineage() not in self.derived_from:
            raise ValueError("contribution must inherit the source event's lineage")
        if self.human_confirmation is not None and self.human_confirmation.statement_ref != self.id:
            raise ValueError("human confirmation must identify this contribution")
        for relation in self.relations:
            question = relation.question
            if question.campaign_id != self.campaign_id or question.scope != self.scope:
                raise ValueError("contribution cannot attach to another campaign or scope")
            if relation.direction in (ClaimDirection.SUPPORTS, ClaimDirection.AGAINST):
                if not isinstance(self.event, ScientificFinding) or not self.event.matches(question.evidence_criteria):
                    raise ValueError("scientific relation requires matching intervention, compartment and endpoint")
        if any(a.other_family_id == self.evidence_family_id for a in self.independence):
            raise ValueError("reports in one evidence family cannot be independent")
        return self

    def independent_of(self, other: Contribution) -> bool:
        return self.evidence_family_id != other.evidence_family_id and any(
            assertion.other_family_id == other.evidence_family_id for assertion in self.independence)


class NodeType(StrEnum):
    EVIDENCE_PRODUCING_LAB = "evidence_producing_lab"
    ANALYSIS_SERVICE = "analysis_service"
    DISCOVERY_NETWORK = "discovery_network"
    HISTORICAL_CUSTODIAL_LEAD = "historical_custodial_lead"


class PublicSource(ImmutableModel):
    reference: str
    accessed_at: datetime | None = None
    published_at: datetime | None = None


class Capability(ImmutableModel):
    description: str
    source: PublicSource
    evidence_status: Knowledge | Literal["PUBLICLY_REPORTED"] = Knowledge.UNKNOWN


class ContactRoute(ImmutableModel):
    recipient: str = Field(repr=False, description="Private routing data; not a public export field.")
    source: PublicSource
    verification: HumanConfirmation | None = None


class Node(ImmutableModel):
    id: str = Field(default_factory=new_id)
    institution: str
    group: str | None = None
    node_type: NodeType
    source: PublicSource
    capabilities: tuple[Capability, ...] = ()
    contact_route: ContactRoute | None = None
    resource_available: bool | Knowledge = Knowledge.UNKNOWN
    analysis_permission: bool | Knowledge = Knowledge.UNKNOWN
    capacity: Quantity = Field(default_factory=unknown_quantity)
    cost: Quantity = Field(default_factory=unknown_quantity)
    turnaround: Quantity = Field(default_factory=unknown_quantity)
    confirmation_events: tuple[OperationalResponse, ...] = ()

    @model_validator(mode="after")
    def _confirmation_required(self):
        for field in ("resource_available", "analysis_permission"):
            if isinstance(getattr(self, field), bool) and not any(
                event.origin is Origin.AUTHENTIC_INSTITUTIONAL
                and event.envelope.node_identity == self.id
                and getattr(event, field) is getattr(self, field)
                for event in self.confirmation_events
            ):
                raise ValueError("confirmed resource/permission requires a new institutional evidence event")
        return self


class Match(ImmutableModel):
    id: str = Field(default_factory=new_id)
    question_id: str
    node_id: str
    reasons: tuple[str, ...]
    sources: tuple[PublicSource, ...]
    gaps: tuple[str, ...] = ()
    eligibility: Knowledge | Literal["ELIGIBLE", "INELIGIBLE"] = Knowledge.UNKNOWN
    ranking_basis: str
    ranking_version: str
    inferred: tuple[str, ...] = ()


class RequestState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    DISPATCHING = "DISPATCHING"
    SENT = "SENT"
    WAITING = "WAITING"
    RECEIVED = "RECEIVED"
    ASSESSED = "ASSESSED"
    CLOSED = "CLOSED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    CONTACT_UNVERIFIED = "CONTACT_UNVERIFIED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
    PAUSED = "PAUSED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class Request(Record):
    campaign_id: str
    question_id: str
    node_id: str
    content: str = Field(repr=False, description="Exact content; approval is a separate human act.")
    approval: HumanConfirmation | None = None
    sender: Actor
    recipient: str = Field(repr=False)
    disclosure_scope: str
    authorization_ref: str | None = None
    parent_request_id: str | None = None
    state: RequestState = RequestState.DRAFT
    owner: Actor | None = None
    next_trigger: datetime | None = None
    unscheduled_reason: str | None = None


class Assessment(Record):
    contribution: Contribution
    question: Question
    relations: tuple[ClaimRelation, ...]
    applicability: Knowledge | Literal["APPLICABLE", "NOT_APPLICABLE"] = Knowledge.UNKNOWN
    missing_fields: tuple[str, ...] = ()
    reviewer: Actor
    decision: Literal["PROPOSED", "ACCEPTED", "REJECTED", "DEFERRED"] = "PROPOSED"
    confirmation: HumanConfirmation | None = None
    source_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _review_boundary(self):
        if self.contribution.lineage() not in self.derived_from:
            raise ValueError("assessment must inherit contribution lineage")
        if (self.question.campaign_id != self.contribution.campaign_id
                or self.question.scope != self.contribution.scope):
            raise ValueError("assessment cannot cross campaign scope")
        if any(relation not in self.contribution.relations or relation.question != self.question
               for relation in self.relations):
            raise ValueError("assessment relations must belong to this contribution and question")
        if self.decision != "PROPOSED" and (
            self.confirmation is None or self.reviewer != self.confirmation.actor
            or self.confirmation.statement_ref != self.id
            or self.confirmation.role != self.question.required_reviewer
        ):
            raise ValueError("review decisions require the configured human review")
        return self


class ActionEvent(Record):
    campaign_id: str
    previous_state: str
    eligible_options: tuple[str, ...]
    selected_action: str
    randomized: bool = False
    selection_probability: float | None = Field(None, gt=0, le=1)
    policy_version: str
    config_version: str
    occurred_at: datetime
    elapsed: Quantity = Field(default_factory=unknown_quantity)
    cost: Quantity = Field(default_factory=unknown_quantity)
    outcome: str | None = None

    @model_validator(mode="after")
    def _selection(self):
        if self.selected_action not in self.eligible_options:
            raise ValueError("selected action must be eligible")
        if self.randomized and self.selection_probability is None:
            raise ValueError("randomized actions require the actual selection probability")
        return self


class FeedbackComponent(ImmutableModel):
    name: str
    value: Quantity


class LearningFeedback(Record):
    campaign_id: str
    action_id: str
    components: tuple[FeedbackComponent, ...] = ()
    assessor: Actor
    method: str
    status: Literal["synthetic", "observed", "pending"] = "pending"
    version: str

    @model_validator(mode="after")
    def _synthetic_is_not_observed(self):
        if self.status == "observed" and self.origin is Origin.SYNTHETIC:
            raise ValueError("synthetic feedback cannot become observed feedback")
        if self.status == "synthetic" and self.origin is not Origin.SYNTHETIC:
            raise ValueError("synthetic feedback requires synthetic origin")
        return self


class PolicyParameter(ImmutableModel):
    key: str
    value: float


class PolicyArtifact(Record):
    algorithm: str
    feature_contract: tuple[str, ...]
    training_config: tuple[tuple[str, str], ...]
    seed: int
    dataset_ids: tuple[str, ...] = ()
    world_split_ids: tuple[str, ...] = ()
    parameters: tuple[PolicyParameter, ...] = ()
    evaluation_refs: tuple[str, ...] = ()
    promotion_state: Literal["DRAFT", "EVALUATED", "SHADOW", "PROMOTED"] = "DRAFT"
    parent_version: str | None = None


class BudgetCadence(ImmutableModel):
    """Unset limits cannot be interpreted as unlimited authority."""

    max_requests: int | None = Field(None, ge=0)
    minimum_interval: Quantity = Field(default_factory=unknown_quantity)
    spend_limit: Quantity = Field(default_factory=unknown_quantity)
    quiet_hours: str | None = None


class Authorization(ImmutableModel):
    id: str = Field(default_factory=new_id)
    issuer: Actor
    authority: str
    confirmation: HumanConfirmation
    sender: str
    recipients: tuple[str, ...]
    purpose: str
    content_refs: tuple[str, ...]
    limits: BudgetCadence = Field(default_factory=BudgetCadence)
    valid_from: datetime
    valid_until: datetime
    revoked_at: datetime | None = None
    exclusions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _human_authority(self):
        if self.issuer != self.confirmation.actor or self.confirmation.statement_ref != self.id:
            raise ValueError("authorization requires the issuer's human confirmation")
        if self.valid_until <= self.valid_from:
            raise ValueError("authorization validity must have a positive interval")
        return self


class Campaign(ImmutableModel):
    id: str = Field(default_factory=new_id)
    purpose: str
    case_ref: str | None = None
    scope: CampaignScope
    mode: CampaignMode
    owner: Actor | None = None
    exclusions: tuple[str, ...] = ()
    status: Literal["DRAFT", "ACTIVE", "PAUSED", "CANCELLED", "CLOSED"] = "DRAFT"
    limits: BudgetCadence = Field(default_factory=BudgetCadence)
    questions: tuple[Question, ...] = ()
    contributions: tuple[Contribution, ...] = ()
    feedback: tuple[LearningFeedback, ...] = ()

    @model_validator(mode="after")
    def _campaign_boundary(self):
        for record in (*self.questions, *self.contributions, *self.feedback):
            if record.campaign_id != self.id:
                raise ValueError("record belongs to another campaign")
        for record in (*self.questions, *self.contributions):
            if record.scope != self.scope:
                raise ValueError("record belongs to another campaign scope")
        if self.mode is CampaignMode.LIVE and any(
            record.origin is Origin.SYNTHETIC for record in (*self.contributions, *self.feedback)
        ):
            raise ValueError("synthetic contributions and feedback cannot enter a live campaign")
        return self
