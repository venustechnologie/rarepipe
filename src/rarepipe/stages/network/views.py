"""Operator views: pure projections over stored records (PRD §15, Task T11).

A view returns a typed payload. It does not compute science, decide, dispatch or write.
Available actions are declared with preconditions; performing one goes through the owning
module. Synthetic material keeps a structural label that projections cannot drop (A15).
Hidden world truth is never read here (A16).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import field_validator, model_validator

from rarepipe.stages.network.eventlog import opaque
from rarepipe.stages.network.model import (
    Assessment, Campaign, CampaignMode, Contribution, ImmutableModel, Knowledge,
    LearningFeedback, Match, Origin, PolicyArtifact, Question, RequestState,
)
from rarepipe.stages.network.outbox import Handoff, Outbox, OutboxEntry
from rarepipe.stages.network.policy_q import (
    PersistedQParameters, QReportingError, TabularQPolicy, render_q_value,
)
from rarepipe.stages.network.registry import CapabilityRegistry, MatchExplanation
from rarepipe.stages.network.sim.baselines import BaselineDecision
from rarepipe.stages.network.sim.institution import LabeledParam
from rarepipe.stages.network.sim.reward import ReportedRate, RewardBreakdown
from rarepipe.stages.network.sim.scenarios import (
    WITHHELD, ScenarioFixture, redact_world_truth, truth_revealing_assumption_names,
)
from rarepipe.stages.prospective.model import Actor, Quantity
from rarepipe.stages.prospective.store import content_digest

STATED_UNKNOWN = "not recorded"
SYNTHETIC_LABEL: Literal["synthetic"] = "synthetic"
Q_UNIT = "simulator_utility_estimate"
Q_LIMITATION = (
    "Q estimates simulator utility under the configured synthetic reward; "
    "it is not a probability, not a percentage chance of biological effect, "
    "and not a chance that an institution will help"
)
VIEW_DIGEST_COVERAGE = (
    "view kind, campaign/opaque refs, recorded fields, available-action ids and "
    "preconditions, synthetic labels, rate counts; excludes content_digest itself, "
    "latent/scorer fields, exact variants and private recipient addresses"
)


class AvailableAction(ImmutableModel):
    """An operator action currently available; performing it goes through owning_module."""

    action_id: str
    label: str
    owning_module: str
    preconditions: tuple[str, ...]
    enabled: bool
    blocked_reason: str | None = None


class PremiseField(ImmutableModel):
    name: str
    status: Literal["known", "unknown"]
    recorded_value: str
    source: str = STATED_UNKNOWN


class StopPauseControls(ImmutableModel):
    """Controls that Outbox.stop / resume / handoff implement — views only expose them."""

    can_pause: bool
    can_cancel: bool
    can_resume: bool
    can_handoff: bool
    campaign_status: str
    owning_module: str = "rarepipe.stages.network.outbox"
    pause_precondition: str = "campaign status is ACTIVE"
    cancel_precondition: str = "campaign is not already CANCELLED"
    resume_precondition: str = "campaign status is PAUSED"
    handoff_precondition: str = "campaign status is PAUSED or CANCELLED"


class WaitingTaskSurface(ImmutableModel):
    """Live waiting task projection; unowned/untriggered tasks are surfaced, never omitted (A12)."""

    task_id: str
    state: str
    schedule_state: str
    owner_identity: str
    next_trigger: str
    unscheduled_reason: str
    ownership_gap: bool
    origin: Origin


class RequestTaskRow(ImmutableModel):
    task_id: str
    state: RequestState
    question_id: str
    node_id: str
    content: str
    authorization_ref: str
    authorization_status: str
    owner_identity: str
    next_trigger: str
    unscheduled_reason: str
    schedule_state: str
    next_followup: str
    origin: Origin
    available_actions: tuple[AvailableAction, ...]


class QValueDisplay(ImmutableModel):
    """Q as simulator utility only — never a percentage or biological probability."""

    value: float
    unit: Literal["simulator_utility_estimate"] = Q_UNIT
    display: str
    limitation: str = Q_LIMITATION
    state_key: str | None = None
    action_key: str | None = None

    @model_validator(mode="after")
    def _not_a_probability(self):
        text = f"{self.display} {self.unit} {self.limitation}".casefold()
        if "%" in self.display or "percent" in text or "probability" in self.display.casefold():
            if "not a probability" not in text and "not a percentage" not in text:
                raise ValueError("Q display must not frame the estimate as a probability or percentage")
        if self.unit != Q_UNIT:
            raise ValueError("Q unit must be simulator_utility_estimate")
        return self

    @staticmethod
    def from_q(value: float, *, state_key: str | None = None, action_key: str | None = None) -> QValueDisplay:
        return QValueDisplay(
            value=value,
            display=render_q_value(value, frame="simulator_utility"),
            state_key=state_key,
            action_key=action_key,
        )

    def as_percentage(self) -> str:
        raise QReportingError(
            "refusing to render Q value as a percentage: Q estimates simulator utility only"
        )

    def as_probability_of_biological_effect(self) -> str:
        raise QReportingError(
            "refusing to render Q value as a probability of biological effect"
        )

    def as_chance_institution_helps(self) -> str:
        raise QReportingError(
            "refusing to render Q value as a chance that an institution will help"
        )


class RateView(ImmutableModel):
    """Projection of ReportedRate — counts travel with every rate (A21); never recomputed here."""

    name: str
    numerator: int
    denominator: int
    point: float | None
    interval_lo: float | None
    interval_hi: float | None
    interval_method: str | None
    interval_applies: bool
    no_interval_reason: str | None

    @classmethod
    def from_reported(cls, rate: ReportedRate) -> RateView:
        return cls(
            name=rate.name,
            numerator=rate.numerator,
            denominator=rate.denominator,
            point=rate.point,
            interval_lo=rate.interval_lo,
            interval_hi=rate.interval_hi,
            interval_method=rate.interval_method,
            interval_applies=rate.interval_applies,
            no_interval_reason=rate.no_interval_reason,
        )


class CaseView(ImmutableModel):
    view: Literal["case"] = "case"
    campaign_id: str
    campaign_status: str
    current_question_id: str
    current_question_decision: str
    known_premises: tuple[PremiseField, ...]
    unknown_premises: tuple[PremiseField, ...]
    latest_change: str
    next_task_id: str
    owner_identity: str
    next_trigger: str
    clinical_lead: str = STATED_UNKNOWN
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None


class NetworkCandidateRow(ImmutableModel):
    node_id: str
    institution: str
    question_id: str
    candidate_rationale: str
    supporting_evidence: tuple[str, ...]
    public_evidence_only: bool
    resource_available: str
    analysis_permission: str
    confirmation_remains: tuple[str, ...]
    ranking_basis: str


class NetworkView(ImmutableModel):
    view: Literal["network"] = "network"
    campaign_id: str
    candidates: tuple[NetworkCandidateRow, ...]
    note: str = (
        "Public evidence is held apart from confirmed availability and permission; "
        "unknown confirmation fields stay unknown"
    )
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None


class RequestsView(ImmutableModel):
    view: Literal["requests"] = "requests"
    campaign_id: str
    campaign_status: str
    tasks: tuple[RequestTaskRow, ...]
    waiting_surfaces: tuple[WaitingTaskSurface, ...]
    stop_pause_controls: StopPauseControls
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None


class ContributionReviewView(ImmutableModel):
    view: Literal["contribution_review"] = "contribution_review"
    campaign_id: str
    contribution_id: str
    origin: Origin
    synthetic_label: str | None = None
    permitted_content: str
    structured_proposal: str
    missing_fields: tuple[str, ...]
    applicability: str
    evidence_family_id: str
    reviewer_action: str
    reviewer_identity: str
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None

    @model_validator(mode="after")
    def _synthetic_stays_labelled(self):
        if self.origin is Origin.SYNTHETIC:
            if self.synthetic_label != SYNTHETIC_LABEL:
                raise ValueError("synthetic contribution must carry synthetic_label")
        elif self.synthetic_label is not None:
            raise ValueError("synthetic_label only permitted for synthetic origin")
        return self


class ScenarioTraceStep(ImmutableModel):
    step: str
    detail: str


class ScenariosView(ImmutableModel):
    view: Literal["scenarios"] = "scenarios"
    scenario_id: str
    origin: Literal[Origin.SYNTHETIC] = Origin.SYNTHETIC
    synthetic_label: Literal["synthetic"] = SYNTHETIC_LABEL
    campaign_id: str
    scope: str
    selected_assumptions: tuple[LabeledParam, ...]
    withheld_assumption_names: tuple[str, ...] = ()
    reveals_world_truth: bool = False
    action_trace: tuple[ScenarioTraceStep, ...]
    resulting_decisions: tuple[str, ...]
    expected_invariant: str
    invariant_holds: bool
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None

    @model_validator(mode="after")
    def _always_synthetic(self):
        if self.origin is not Origin.SYNTHETIC or self.synthetic_label != SYNTHETIC_LABEL:
            raise ValueError("scenario views are always synthetic-labelled")
        if not self.reveals_world_truth:
            revealing = truth_revealing_assumption_names()
            leaked = [p.name for p in self.selected_assumptions
                      if p.name in revealing and p.value != WITHHELD]
            if leaked:
                raise ValueError(
                    f"scenario view would publish hidden world truth for {leaked}; "
                    "pass reveal_world_truth for a post-hoc review payload"
                )
        return self


class LearningView(ImmutableModel):
    view: Literal["learning"] = "learning"
    campaign_id: str
    policy_version: str
    policy_algorithm: str
    promotion_state: str
    q_values: tuple[QValueDisplay, ...]
    reward_components: tuple[tuple[str, str], ...]
    baseline_comparisons: tuple[tuple[str, str], ...]
    rates: tuple[RateView, ...]
    updates: tuple[str, ...]
    limitations: tuple[str, ...]
    feedback_items: tuple[tuple[str, str, str], ...]
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None


class AuditExportView(ImmutableModel):
    view: Literal["audit_export"] = "audit_export"
    campaign_id_opaque: str
    campaign_status: str
    provenance: tuple[tuple[str, str], ...]
    supersessions: tuple[tuple[str, str], ...]
    scoped_sharing: tuple[str, ...]
    plain_language_account: tuple[str, ...]
    event_ids: tuple[str, ...]
    event_count: int
    handoff: Handoff | None = None
    history_survived_stop: bool
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None


class FamilySummaryView(ImmutableModel):
    view: Literal["family_summary"] = "family_summary"
    campaign_id: str
    what_changed: str
    what_it_means: str
    remains_unresolved: tuple[str, ...]
    next_step_owner: str
    clinical_lead: str = STATED_UNKNOWN
    partnership_status: str = STATED_UNKNOWN
    efficacy_confidence: str = STATED_UNKNOWN
    family_preference: str = STATED_UNKNOWN
    continuous_activity: str = STATED_UNKNOWN
    available_actions: tuple[AvailableAction, ...]
    content_digest: str | None = None

    @field_validator(
        "clinical_lead", "partnership_status", "efficacy_confidence",
        "family_preference", "continuous_activity",
    )
    @classmethod
    def _no_fabrication(cls, value: str) -> str:
        if not value or not value.strip():
            return STATED_UNKNOWN
        return value


def _with_digest(model: ImmutableModel) -> Any:
    payload = model.model_dump(mode="json")
    digest = content_digest(payload, exclude={"content_digest"})
    data = {k: v for k, v in payload.items() if k != "content_digest"}
    data["content_digest"] = digest
    return type(model).model_validate(data)


def _actor_identity(actor: Actor | None) -> str:
    if actor is None or not actor.identity.strip():
        return STATED_UNKNOWN
    return actor.identity


def _quantity_status(q: Quantity) -> PremiseField:
    if q.value is None:
        reason = q.null_reason.value if q.null_reason is not None else STATED_UNKNOWN
        return PremiseField(name="quantity", status="unknown", recorded_value=reason)
    return PremiseField(name="quantity", status="known", recorded_value=f"{q.value} {q.unit or ''}".strip())


def _premise_from_criteria(question: Question) -> tuple[tuple[PremiseField, ...], tuple[PremiseField, ...]]:
    known: list[PremiseField] = []
    unknown: list[PremiseField] = []
    criteria = question.evidence_criteria
    for field in (
        "intervention", "compartment", "species", "model", "tissue_or_cell", "endpoint",
        "comparator", "method", "experimental_unit", "denominator", "timeframe",
    ):
        value = getattr(criteria, field)
        if value is None or isinstance(value, Knowledge):
            unknown.append(PremiseField(
                name=field, status="unknown",
                recorded_value=value.value if isinstance(value, Knowledge) else STATED_UNKNOWN,
                source="question.evidence_criteria",
            ))
        else:
            known.append(PremiseField(
                name=field, status="known", recorded_value=str(value),
                source="question.evidence_criteria",
            ))
    for name, quantity in (("exposure", criteria.exposure), ("effect_criterion", criteria.effect_criterion)):
        row = _quantity_status(quantity)
        row = PremiseField(name=name, status=row.status, recorded_value=row.recorded_value,
                           source="question.evidence_criteria")
        (known if row.status == "known" else unknown).append(row)
    if question.state is Knowledge.UNKNOWN or question.state in (
        Knowledge.NOT_MEASURED, Knowledge.NOT_REPORTED, Knowledge.UNAVAILABLE, Knowledge.INCONCLUSIVE,
    ):
        unknown.append(PremiseField(
            name="question_state", status="unknown", recorded_value=question.state.value,
            source="question.state",
        ))
    else:
        known.append(PremiseField(
            name="question_state", status="known", recorded_value=question.state.value,
            source="question.state",
        ))
    return tuple(known), tuple(unknown)


def _latest_change(outbox: Outbox) -> str:
    events = outbox.log.events()
    if not events:
        return STATED_UNKNOWN
    last = events[-1]
    return f"event {last.id}: {last.kind} {last.previous_state}->{last.new_state} ({last.reason.value})"


def _authorization_status(task: OutboxEntry) -> str:
    if task.authorization_ref:
        return f"authorization_ref recorded ({opaque(task.authorization_ref)[:12]}…)"
    if task.state is RequestState.AUTHORIZATION_REQUIRED:
        return "authorization required; no authorization_ref recorded"
    return "no authorization_ref recorded"


def _next_followup(task: OutboxEntry) -> str:
    if task.max_followups is None:
        return "follow-up bound not recorded"
    remaining = task.max_followups - task.followup_count
    if remaining <= 0:
        return "follow-up bound reached"
    if task.followup_reason is not None:
        return f"follow-up permitted ({remaining} remaining); last reason {task.followup_reason.value}"
    return f"follow-up permitted ({remaining} remaining); no follow-up reason recorded yet"


def _waiting_surface(task: OutboxEntry) -> WaitingTaskSurface:
    owner = _actor_identity(task.owner)
    trigger = task.next_trigger.isoformat() if task.next_trigger is not None else STATED_UNKNOWN
    reason = task.unscheduled_reason.value if task.unscheduled_reason is not None else STATED_UNKNOWN
    gap = (
        task.state is RequestState.WAITING
        and (owner == STATED_UNKNOWN or task.next_trigger is None)
    )
    return WaitingTaskSurface(
        task_id=task.id,
        state=task.state.value,
        schedule_state=task.schedule_state,
        owner_identity=owner,
        next_trigger=trigger,
        unscheduled_reason=reason,
        ownership_gap=gap,
        origin=task.origin,
    )


def _stop_pause_controls(campaign: Campaign) -> StopPauseControls:
    status = campaign.status
    return StopPauseControls(
        can_pause=status == "ACTIVE",
        can_cancel=status != "CANCELLED",
        can_resume=status == "PAUSED",
        can_handoff=status in {"PAUSED", "CANCELLED"},
        campaign_status=status,
    )


def _task_actions(task: OutboxEntry, campaign: Campaign) -> tuple[AvailableAction, ...]:
    active = campaign.status == "ACTIVE"
    actions = [
        AvailableAction(
            action_id="outbox.transition_ready",
            label="Mark ready",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=("task state is DRAFT or AUTHORIZATION_REQUIRED or CONTACT_UNVERIFIED",
                           "campaign is ACTIVE"),
            enabled=active and task.state in {
                RequestState.DRAFT, RequestState.AUTHORIZATION_REQUIRED, RequestState.CONTACT_UNVERIFIED,
            },
            blocked_reason=None if active else "campaign is not active",
        ),
        AvailableAction(
            action_id="outbox.begin_attempt",
            label="Begin dispatch attempt",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=("task state is READY", "fresh authorization check returns True",
                           "campaign is ACTIVE"),
            enabled=active and task.state is RequestState.READY,
            blocked_reason=None if (active and task.state is RequestState.READY) else "not ready or campaign stopped",
        ),
        AvailableAction(
            action_id="scheduler.claim",
            label="Claim due timer",
            owning_module="rarepipe.stages.network.scheduler",
            preconditions=("task is WAITING and SCHEDULED", "next_trigger <= now", "campaign is ACTIVE"),
            enabled=active and task.state is RequestState.WAITING and task.schedule_state == "SCHEDULED",
            blocked_reason=None if task.schedule_state == "SCHEDULED" else (
                task.unscheduled_reason.value if task.unscheduled_reason else "timer not scheduled"
            ),
        ),
    ]
    return tuple(actions)


def summary_projection(payload: ImmutableModel) -> dict[str, Any]:
    """Filter/summary helper that cannot drop a synthetic label (A15).

    Callers may omit fields, but any payload that carried synthetic material keeps
    origin=synthetic and synthetic_label=synthetic in the projection.
    """
    data = payload.model_dump(mode="json")
    origin = data.get("origin")
    carries = origin == SYNTHETIC_LABEL or data.get("synthetic_label") == SYNTHETIC_LABEL
    if isinstance(payload, ScenariosView):
        carries = True
    feedback = data.get("feedback_items") or ()
    if any(len(item) >= 3 and item[2] == SYNTHETIC_LABEL for item in feedback):
        carries = True
    # Drop decorative fields a summary might omit — never the synthetic markers.
    slim = {
        k: v for k, v in data.items()
        if k not in {"content_digest", "available_actions", "note", "plain_language_account"}
    }
    if carries:
        slim["origin"] = SYNTHETIC_LABEL
        slim["synthetic_label"] = SYNTHETIC_LABEL
    return slim


def case_view(
    outbox: Outbox,
    *,
    question: Question | None = None,
    clinical_lead: Actor | None = None,
) -> CaseView:
    campaign = outbox.campaign()
    questions = campaign.questions
    current = question
    if current is None and questions:
        current = questions[0]
    if current is None:
        known: tuple[PremiseField, ...] = ()
        unknown = (PremiseField(
            name="current_question", status="unknown", recorded_value=STATED_UNKNOWN,
            source="campaign.questions",
        ),)
        qid, decision = STATED_UNKNOWN, STATED_UNKNOWN
    else:
        known, unknown = _premise_from_criteria(current)
        qid, decision = current.id, current.decision

    tasks = outbox.tasks()
    waiting = [t for t in tasks if t.state is RequestState.WAITING]
    next_task = waiting[0] if waiting else (tasks[0] if tasks else None)
    lead = _actor_identity(clinical_lead) if clinical_lead is not None else STATED_UNKNOWN

    actions = (
        AvailableAction(
            action_id="intake.import_reply",
            label="Import permitted reply",
            owning_module="rarepipe.stages.network.intake",
            preconditions=("authenticated manual import or test transport receipt",),
            enabled=campaign.status == "ACTIVE",
            blocked_reason=None if campaign.status == "ACTIVE" else "campaign is not active",
        ),
        AvailableAction(
            action_id="policy_q.select",
            label="Select next eligible action",
            owning_module="rarepipe.stages.network.policy_q",
            preconditions=("eligible action set non-empty", "observation has no latent keys"),
            enabled=True,
        ),
    )
    view = CaseView(
        campaign_id=campaign.id,
        campaign_status=campaign.status,
        current_question_id=qid,
        current_question_decision=decision,
        known_premises=known,
        unknown_premises=unknown,
        latest_change=_latest_change(outbox),
        next_task_id=next_task.id if next_task else STATED_UNKNOWN,
        owner_identity=_actor_identity(next_task.owner if next_task else campaign.owner),
        next_trigger=(
            next_task.next_trigger.isoformat()
            if next_task and next_task.next_trigger is not None
            else STATED_UNKNOWN
        ),
        clinical_lead=lead,
        available_actions=actions,
    )
    return _with_digest(view)


def network_view(
    campaign: Campaign,
    *,
    registry: CapabilityRegistry,
    question_id: str | None = None,
) -> NetworkView:
    questions = list(campaign.questions)
    if question_id is not None:
        qids = [question_id]
    elif questions:
        qids = [q.id for q in questions]
    else:
        qids = []

    rows: list[NetworkCandidateRow] = []
    for qid in qids:
        try:
            matches = registry.get_matches_for_question(qid)
        except KeyError:
            continue
        for match in matches:
            try:
                explanation = registry.explain_match(match.node_id, qid)
            except KeyError:
                continue
            rows.append(_candidate_row(explanation, match))

    actions = (
        AvailableAction(
            action_id="registry.explain_match",
            label="Explain candidate match",
            owning_module="rarepipe.stages.network.registry",
            preconditions=("node and question are registered",),
            enabled=bool(rows),
            blocked_reason=None if rows else "no explained candidates recorded",
        ),
        AvailableAction(
            action_id="compose.first_request",
            label="Compose first request draft",
            owning_module="rarepipe.stages.network.compose",
            preconditions=("candidate selected", "disclosure scope set"),
            enabled=bool(rows),
            blocked_reason=None if rows else "no candidate to compose against",
        ),
    )
    view = NetworkView(
        campaign_id=campaign.id,
        candidates=tuple(rows),
        available_actions=actions,
    )
    return _with_digest(view)


def _candidate_row(explanation: MatchExplanation, match: Match) -> NetworkCandidateRow:
    resource = explanation.resource_available
    permission = explanation.analysis_permission
    return NetworkCandidateRow(
        node_id=explanation.node_id,
        institution=explanation.institution,
        question_id=explanation.question_id,
        candidate_rationale=explanation.candidate_rationale,
        supporting_evidence=explanation.supporting_evidence,
        public_evidence_only=True,
        resource_available=(
            resource.value if isinstance(resource, Knowledge) else str(resource)
        ),
        analysis_permission=(
            permission.value if isinstance(permission, Knowledge) else str(permission)
        ),
        confirmation_remains=explanation.confirmation_remains,
        ranking_basis=match.ranking_basis,
    )


def requests_view(outbox: Outbox) -> RequestsView:
    campaign = outbox.campaign()
    tasks = outbox.tasks()
    rows: list[RequestTaskRow] = []
    waiting_surfaces: list[WaitingTaskSurface] = []
    for task in tasks:
        if task.state is RequestState.WAITING:
            # A12: surface every live waiting task, including unowned / untriggered ones.
            waiting_surfaces.append(_waiting_surface(task))
        rows.append(RequestTaskRow(
            task_id=task.id,
            state=task.state,
            question_id=task.question_id,
            node_id=task.node_id,
            content=task.content,
            authorization_ref=task.authorization_ref or STATED_UNKNOWN,
            authorization_status=_authorization_status(task),
            owner_identity=_actor_identity(task.owner),
            next_trigger=task.next_trigger.isoformat() if task.next_trigger else STATED_UNKNOWN,
            unscheduled_reason=(
                task.unscheduled_reason.value if task.unscheduled_reason is not None else STATED_UNKNOWN
            ),
            schedule_state=task.schedule_state,
            next_followup=_next_followup(task),
            origin=task.origin,
            available_actions=_task_actions(task, campaign),
        ))

    controls = _stop_pause_controls(campaign)
    actions = (
        AvailableAction(
            action_id="outbox.stop_pause",
            label="Pause campaign",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=(controls.pause_precondition,),
            enabled=controls.can_pause,
            blocked_reason=None if controls.can_pause else f"status is {campaign.status}",
        ),
        AvailableAction(
            action_id="outbox.stop_cancel",
            label="Cancel campaign",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=(controls.cancel_precondition,),
            enabled=controls.can_cancel,
            blocked_reason=None if controls.can_cancel else "already cancelled",
        ),
        AvailableAction(
            action_id="outbox.resume",
            label="Resume paused campaign",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=(controls.resume_precondition,),
            enabled=controls.can_resume,
            blocked_reason=None if controls.can_resume else f"status is {campaign.status}",
        ),
        AvailableAction(
            action_id="outbox.handoff",
            label="Obtain handoff package",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=(controls.handoff_precondition,),
            enabled=controls.can_handoff,
            blocked_reason=None if controls.can_handoff else "campaign not paused or cancelled",
        ),
    )
    view = RequestsView(
        campaign_id=campaign.id,
        campaign_status=campaign.status,
        tasks=tuple(rows),
        waiting_surfaces=tuple(waiting_surfaces),
        stop_pause_controls=controls,
        available_actions=actions,
    )
    return _with_digest(view)


def contribution_review_view(
    campaign: Campaign,
    *,
    contribution: Contribution,
    assessment: Assessment | None = None,
) -> ContributionReviewView:
    if contribution.campaign_id != campaign.id:
        raise ValueError("contribution belongs to another campaign")
    if campaign.mode is CampaignMode.LIVE and contribution.origin is Origin.SYNTHETIC:
        raise ValueError("synthetic contribution cannot be presented as live campaign evidence")

    if assessment is None:
        missing = ("assessment",)
        applicability = STATED_UNKNOWN
        proposal = STATED_UNKNOWN
        reviewer_action = "PROPOSED review not recorded"
        reviewer = STATED_UNKNOWN
        actions = (
            AvailableAction(
                action_id="intake.complete_human_review",
                label="Complete human scientific review",
                owning_module="rarepipe.stages.network.intake",
                preconditions=("assessment exists", "reviewer is HUMAN with required role"),
                enabled=False,
                blocked_reason="no assessment recorded",
            ),
        )
    else:
        missing = assessment.missing_fields or ("no missing fields recorded",)
        applicability = (
            assessment.applicability.value
            if isinstance(assessment.applicability, Knowledge)
            else str(assessment.applicability)
        )
        proposal = (
            f"decision={assessment.decision}; relations={len(assessment.relations)}; "
            f"question={assessment.question.id}"
        )
        reviewer_action = assessment.decision
        reviewer = _actor_identity(assessment.reviewer)
        actions = (
            AvailableAction(
                action_id="intake.complete_human_review",
                label="Complete human scientific review",
                owning_module="rarepipe.stages.network.intake",
                preconditions=("reviewer is HUMAN", "required role held", "assessment is PROPOSED"),
                enabled=assessment.decision == "PROPOSED",
                blocked_reason=None if assessment.decision == "PROPOSED" else f"already {assessment.decision}",
            ),
        )

    view = ContributionReviewView(
        campaign_id=campaign.id,
        contribution_id=contribution.id,
        origin=contribution.origin,
        synthetic_label=SYNTHETIC_LABEL if contribution.origin is Origin.SYNTHETIC else None,
        permitted_content=contribution.permitted_content,
        structured_proposal=proposal,
        missing_fields=tuple(missing),
        applicability=applicability,
        evidence_family_id=contribution.evidence_family_id,
        reviewer_action=reviewer_action,
        reviewer_identity=reviewer,
        available_actions=actions,
    )
    return _with_digest(view)


def scenarios_view(
    scenario: ScenarioFixture,
    *,
    action_trace: tuple[ScenarioTraceStep, ...] | None = None,
    resulting_decisions: tuple[str, ...] | None = None,
    reveal_world_truth: bool = False,
) -> ScenariosView:
    """Project a synthetic scenario. Always labelled synthetic; never campaign evidence.

    `reveal_world_truth` is a post-hoc review payload and must never be rendered into anything a
    policy reads or an operator uses while choosing an action (A16).
    """
    trace = action_trace or tuple(
        ScenarioTraceStep(step="contribution", detail=f"{c.id}:{c.event.kind}")
        for c in scenario.contributions
    )
    decisions = resulting_decisions or (
        (f"expected:{scenario.expected}", f"invariant_holds:{scenario.invariant_holds}")
    )
    shown, withheld = redact_world_truth(scenario.assumptions, reveal=reveal_world_truth)
    view = ScenariosView(
        scenario_id=scenario.id,
        campaign_id=scenario.campaign_id,
        scope=scenario.scope.value,
        selected_assumptions=shown,
        withheld_assumption_names=withheld,
        reveals_world_truth=reveal_world_truth,
        action_trace=trace,
        resulting_decisions=decisions,
        expected_invariant=scenario.expected,
        invariant_holds=scenario.invariant_holds,
        available_actions=(
            AvailableAction(
                action_id="sim.scenarios.rebuild",
                label="Rebuild scenario fixture",
                owning_module="rarepipe.stages.network.sim.scenarios",
                preconditions=("master seed recorded",),
                enabled=True,
            ),
        ),
    )
    return _with_digest(view)


def _q_values_from_snapshot(snapshot: PersistedQParameters) -> tuple[QValueDisplay, ...]:
    return tuple(
        QValueDisplay.from_q(entry.value, state_key=entry.state_key, action_key=entry.action_key)
        for entry in snapshot.entries
    )


def learning_view(
    campaign: Campaign,
    *,
    policy: TabularQPolicy | PolicyArtifact | PersistedQParameters | None = None,
    reward: RewardBreakdown | None = None,
    rates: tuple[ReportedRate, ...] = (),
    baseline_decisions: tuple[BaselineDecision, ...] = (),
    feedback: tuple[LearningFeedback, ...] = (),
) -> LearningView:
    if policy is None:
        version = STATED_UNKNOWN
        algorithm = STATED_UNKNOWN
        promotion = STATED_UNKNOWN
        q_values: tuple[QValueDisplay, ...] = ()
        updates: tuple[str, ...] = (STATED_UNKNOWN,)
    elif isinstance(policy, PersistedQParameters):
        version = policy.content_digest or STATED_UNKNOWN
        algorithm = policy.algorithm
        promotion = STATED_UNKNOWN
        q_values = _q_values_from_snapshot(policy)
        updates = (
            f"update_count={policy.update_count}",
            f"training_events={policy.training_events}",
        )
    elif isinstance(policy, PolicyArtifact):
        version = policy.id
        algorithm = policy.algorithm
        promotion = policy.promotion_state
        # PolicyArtifact.parameters are named floats — still render under the Q unit boundary.
        q_values = tuple(
            QValueDisplay.from_q(p.value, state_key=p.key, action_key=None)
            for p in policy.parameters
        )
        updates = (f"parent_version={policy.parent_version or STATED_UNKNOWN}",)
    else:
        snapshot = policy.parameter_snapshot()
        version = policy.policy_id
        algorithm = snapshot.algorithm
        promotion = "SHADOW"
        q_values = _q_values_from_snapshot(snapshot)
        updates = (
            f"training_events={snapshot.training_events}",
            f"update_count={snapshot.update_count}",
        )

    if reward is None:
        components: tuple[tuple[str, str], ...] = (("reward", STATED_UNKNOWN),)
    else:
        components = (
            ("delta_V", str(reward.delta_V)),
            ("elapsed_ticks", str(reward.elapsed_ticks)),
            ("cost_units", str(reward.cost_units)),
            ("contact_units", str(reward.contact_units)),
            ("unsupported_decisions", str(reward.unsupported_decisions)),
            ("reward", str(reward.reward)),
            ("convention_label", reward.convention_label),
        )

    baselines = tuple(
        (d.baseline_id, d.action.kind if d.action is not None else STATED_UNKNOWN)
        for d in baseline_decisions
    ) or (("baseline_comparison", STATED_UNKNOWN),)

    source_feedback = feedback if feedback else campaign.feedback
    feedback_items = tuple(
        (item.id, item.status, item.origin.value) for item in source_feedback
    )

    rate_views = tuple(RateView.from_reported(r) for r in rates)
    limitations = (
        Q_LIMITATION,
        "Learning results are engineering comparisons under synthetic reward; "
        "they do not establish clinical efficacy or institutional response rates",
        "No interval is invented when a rate declares interval_applies=False",
    )
    view = LearningView(
        campaign_id=campaign.id,
        policy_version=version,
        policy_algorithm=algorithm,
        promotion_state=promotion,
        q_values=q_values,
        reward_components=components,
        baseline_comparisons=baselines,
        rates=rate_views,
        updates=updates,
        limitations=limitations,
        feedback_items=feedback_items,
        available_actions=(
            AvailableAction(
                action_id="policy_q.update",
                label="Apply recorded learning update",
                owning_module="rarepipe.stages.network.policy_q",
                preconditions=("synthetic or permitted observed feedback", "eligible action set"),
                enabled=True,
            ),
        ),
    )
    return _with_digest(view)


def audit_export_view(
    outbox: Outbox,
    *,
    contributions: tuple[Contribution, ...] = (),
    handoff: Handoff | None = None,
) -> AuditExportView:
    campaign = outbox.campaign()
    events = outbox.log.events()
    event_ids = tuple(e.id for e in events)

    provenance = (
        ("campaign_id_opaque", opaque(campaign.id)),
        ("campaign_mode", campaign.mode.value),
        ("campaign_scope", campaign.scope.value),
        ("campaign_status", campaign.status),
        ("event_count", str(len(events))),
    )
    supersessions = tuple(
        (c.id, c.supersedes)
        for c in contributions
        if c.supersedes
    ) or ((STATED_UNKNOWN, "no supersession recorded"),)

    sharing: list[str] = []
    for c in contributions:
        sharing.append(
            f"contribution {c.id}: case_use={c.restrictions.case_use} "
            f"public_export={c.restrictions.public_export} "
            f"other_case={c.restrictions.other_case} "
            f"policy_training={c.restrictions.policy_training} "
            f"revoked={c.restrictions.revoked}"
        )
    if not sharing:
        sharing.append("no scoped sharing grants recorded")

    account = [
        f"Campaign purpose recorded as: {campaign.purpose}",
        f"Status is {campaign.status} with {len(events)} journal events retained",
    ]
    if campaign.status in {"PAUSED", "CANCELLED"}:
        account.append(
            "Pause/cancel recorded through outbox.stop; journal events remain readable"
        )
    if handoff is not None:
        account.append(
            f"Handoff next_action={handoff.next_action}; "
            f"task_refs={len(handoff.task_refs)}; "
            f"reconciliation_required={len(handoff.reconciliation_required)}"
        )
    elif campaign.status in {"PAUSED", "CANCELLED"}:
        # An obtainable handoff that was simply not passed in is not "no handoff". Saying so
        # would read as though the pause had cost the operator their handoff.
        account.append(
            "No handoff package was passed to this view; the campaign is "
            f"{campaign.status} so one is obtainable through outbox.handoff"
        )
    else:
        account.append(
            "No handoff package recorded; the campaign is "
            f"{campaign.status}, so a handoff is not available until it is paused or cancelled"
        )

    # History survival: events still readable after stop/handoff.
    history_ok = True
    if campaign.status in {"PAUSED", "CANCELLED"}:
        history_ok = len(events) > 0
        if handoff is not None:
            history_ok = history_ok and set(handoff.event_ids) == set(event_ids)

    actions = (
        AvailableAction(
            action_id="outbox.handoff",
            label="Refresh handoff package",
            owning_module="rarepipe.stages.network.outbox",
            preconditions=("campaign is PAUSED or CANCELLED",),
            enabled=campaign.status in {"PAUSED", "CANCELLED"},
            blocked_reason=None if campaign.status in {"PAUSED", "CANCELLED"} else "campaign not stopped",
        ),
    )
    view = AuditExportView(
        campaign_id_opaque=opaque(campaign.id),
        campaign_status=campaign.status,
        provenance=provenance,
        supersessions=supersessions,
        scoped_sharing=tuple(sharing),
        plain_language_account=tuple(account),
        event_ids=event_ids,
        event_count=len(events),
        handoff=handoff,
        history_survived_stop=history_ok,
        available_actions=actions,
    )
    return _with_digest(view)


def family_summary_view(
    outbox: Outbox,
    *,
    clinical_lead: Actor | None = None,
    partnership_status: str | None = None,
    efficacy_confidence: str | None = None,
    family_preference: str | None = None,
) -> FamilySummaryView:
    """Family-facing continuity from the event store. Unrecorded fields stay stated unknown."""
    campaign = outbox.campaign()
    events = outbox.log.events()
    tasks = outbox.tasks()
    waiting = [t for t in tasks if t.state is RequestState.WAITING]

    if not events:
        changed = STATED_UNKNOWN
    else:
        last = events[-1]
        changed = f"Latest recorded change: {last.reason.value} on {last.kind}"

    if campaign.contributions:
        means = (
            f"{len(campaign.contributions)} contribution(s) on record; "
            "interpretation requires human review where assessment is pending"
        )
    else:
        means = "No contribution has been recorded yet; no partnership or efficacy claim follows"

    unresolved = []
    for q in campaign.questions:
        if q.state is Knowledge.UNKNOWN or q.state in (
            Knowledge.NOT_MEASURED, Knowledge.NOT_REPORTED, Knowledge.UNAVAILABLE, Knowledge.INCONCLUSIVE,
        ):
            unresolved.append(f"question {q.id}: {q.state.value}")
    if not unresolved:
        unresolved.append("no question-resolution state recorded as known")

    if waiting:
        owner = _actor_identity(waiting[0].owner)
        if owner == STATED_UNKNOWN:
            owner = (
                f"waiting task {waiting[0].id} has no owner "
                f"({waiting[0].unscheduled_reason.value if waiting[0].unscheduled_reason else STATED_UNKNOWN})"
            )
    else:
        owner = _actor_identity(campaign.owner)
        if owner == STATED_UNKNOWN:
            owner = "no next-step owner recorded"

    view = FamilySummaryView(
        campaign_id=campaign.id,
        what_changed=changed,
        what_it_means=means,
        remains_unresolved=tuple(unresolved),
        next_step_owner=owner,
        clinical_lead=_actor_identity(clinical_lead) if clinical_lead is not None else STATED_UNKNOWN,
        partnership_status=partnership_status if partnership_status else STATED_UNKNOWN,
        efficacy_confidence=efficacy_confidence if efficacy_confidence else STATED_UNKNOWN,
        family_preference=family_preference if family_preference else STATED_UNKNOWN,
        continuous_activity=STATED_UNKNOWN,
        available_actions=(
            AvailableAction(
                action_id="outbox.handoff",
                label="Operator handoff",
                owning_module="rarepipe.stages.network.outbox",
                preconditions=("campaign paused or cancelled for handoff",),
                enabled=campaign.status in {"PAUSED", "CANCELLED"},
                blocked_reason=None if campaign.status in {"PAUSED", "CANCELLED"} else "campaign not stopped",
            ),
        ),
    )
    return _with_digest(view)


def render_view_text(payload: ImmutableModel) -> str:
    """Thin CLI rendering over a typed payload — tests assert on the payload, not this text."""
    data = payload.model_dump(mode="json")
    kind = data.get("view", type(payload).__name__)
    lines = [f"view: {kind}"]
    for key, value in data.items():
        if key in {"view", "content_digest", "available_actions"}:
            continue
        lines.append(f"  {key}: {value}")
    if "content_digest" in data and data["content_digest"]:
        lines.append(f"  content_digest: {data['content_digest']}")
    actions = data.get("available_actions") or []
    if actions:
        lines.append("  available_actions:")
        for action in actions:
            flag = "enabled" if action.get("enabled") else "blocked"
            lines.append(f"    - {action.get('action_id')} [{flag}] via {action.get('owning_module')}")
    return "\n".join(lines)


def all_view_payloads(
    outbox: Outbox,
    *,
    registry: CapabilityRegistry | None = None,
    scenario: ScenarioFixture | None = None,
    contribution: Contribution | None = None,
    assessment: Assessment | None = None,
    policy: TabularQPolicy | PolicyArtifact | PersistedQParameters | None = None,
    reward: RewardBreakdown | None = None,
    rates: tuple[ReportedRate, ...] = (),
    handoff: Handoff | None = None,
) -> tuple[ImmutableModel, ...]:
    """Render every operator view for latent-leak and export scans."""
    campaign = outbox.campaign()
    payloads: list[ImmutableModel] = [
        case_view(outbox),
        requests_view(outbox),
        family_summary_view(outbox),
        audit_export_view(outbox, contributions=campaign.contributions, handoff=handoff),
        learning_view(campaign, policy=policy, reward=reward, rates=rates,
                      feedback=campaign.feedback),
    ]
    if registry is not None:
        payloads.append(network_view(campaign, registry=registry))
    if scenario is not None:
        payloads.append(scenarios_view(scenario))
    if contribution is not None:
        payloads.append(contribution_review_view(
            campaign, contribution=contribution, assessment=assessment))
    return tuple(payloads)
