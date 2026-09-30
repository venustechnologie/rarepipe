"""Durable preparation and dispatch claims, without transport or authorization policy.

T05 must call begin_attempt with its current authorization checker, and send only when
created is true. A claimed attempt is never handed out twice. Crashes after a claim
require reconciliation, including when it is unknown whether transport was invoked.
No exactly-once delivery guarantee is made.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

from pydantic import Field

from rarepipe.stages.network.eventlog import EventLog, Reason, opaque, utc
from rarepipe.stages.network.model import (
    Campaign, CampaignMode, Contribution, ImmutableModel, Origin, Request, RequestState,
)
from rarepipe.stages.network.scheduler import WaitingTask, parse_quiet_hours
from rarepipe.stages.prospective.model import Actor, Quantity
from rarepipe.stages.prospective.store import content_digest


class DispatchBlocked(ValueError):
    pass


class ReconciliationRequired(DispatchBlocked):
    pass


class OutboxEntry(WaitingTask):
    idempotency_digest: str
    preparation_digest: str
    digest_coverage: str = "idempotency: exact key; preparation: complete initial Request, canonical-json-v1"
    attempt_id: str | None = None
    attempt_count: int = Field(0, ge=0)
    reserved_cost: Decimal | None = None
    cost_unit: str | None = None
    reconciliation_ref: str | None = None
    receipt_refs: tuple[str, ...] = ()
    response_refs: tuple[str, ...] = ()
    paused_from: RequestState | None = None


class DispatchClaim(ImmutableModel):
    attempt_id: str
    created: bool
    task: OutboxEntry


class Handoff(ImmutableModel):
    """Operational references only, for the campaign's private operator view."""

    campaign_ref: str
    status: Literal["PAUSED", "CANCELLED"]
    task_refs: tuple[str, ...]
    event_ids: tuple[str, ...]
    reconciliation_required: tuple[str, ...]
    next_action: Literal["OPERATOR_REVIEW", "RECONCILE_WITHOUT_RETRY"]


_ALLOWED = {
    RequestState.DRAFT: {RequestState.READY, RequestState.AUTHORIZATION_REQUIRED, RequestState.CONTACT_UNVERIFIED},
    RequestState.AUTHORIZATION_REQUIRED: {RequestState.READY},
    RequestState.CONTACT_UNVERIFIED: {RequestState.READY},
    RequestState.SENT: {RequestState.WAITING},
    RequestState.WAITING: {RequestState.WAITING},
    RequestState.RECEIVED: {RequestState.ASSESSED},
    RequestState.ASSESSED: {RequestState.CLOSED},
}
_TERMINAL = {RequestState.CLOSED, RequestState.DECLINED, RequestState.EXPIRED, RequestState.FAILED}
_TRANSITION_REASONS = {
    RequestState.READY: Reason.READY,
    RequestState.AUTHORIZATION_REQUIRED: Reason.AUTHORIZATION_REQUIRED,
    RequestState.CONTACT_UNVERIFIED: Reason.CONTACT_UNVERIFIED,
    RequestState.WAITING: Reason.WAIT_SCHEDULED,
    RequestState.ASSESSED: Reason.ASSESSMENT_RECORDED,
    RequestState.CLOSED: Reason.WORK_COMPLETE,
    RequestState.DECLINED: Reason.DECLINED,
    RequestState.EXPIRED: Reason.EXPIRED,
    RequestState.FAILED: Reason.FAILED,
}


class Outbox:
    def __init__(self, workspace: Path, campaign: Campaign):
        self.campaign_id = campaign.id
        self.log = EventLog(Path(workspace) / opaque(campaign.id))
        with self.log.writer():
            history = self.log.replay(self.campaign_key)
            if not history:
                actor = campaign.owner or Actor(actor_type="SYSTEM", identity="network-store")
                self.log._append(task_id=self.campaign_key, previous_state=None,
                                new_state=campaign.status, reason=Reason.PREPARED, actor=actor,
                                kind="campaign", snapshot=campaign.model_dump(mode="json"),
                                origin=None, now=datetime.now(timezone.utc))
            elif self.campaign().mode != campaign.mode:
                raise ValueError("campaign mode is immutable")

    @property
    def campaign_key(self):
        return "campaign:" + self.campaign_id

    def campaign(self) -> Campaign:
        return Campaign.model_validate(self.log.snapshot(self.log.replay(self.campaign_key)[-1]))

    def require_active(self):
        if self.campaign().status != "ACTIVE":
            raise DispatchBlocked("campaign is not active")

    def load(self, task_id: str) -> OutboxEntry:
        history = self.log.replay(task_id)
        if not history or history[-1].kind == "campaign":
            raise KeyError("unknown task")
        return OutboxEntry.model_validate(self.log.snapshot(history[-1]))

    def tasks(self) -> tuple[OutboxEntry, ...]:
        latest = {}
        for event in self.log.events():
            if event.kind != "campaign":
                latest[event.task_id] = event
        return tuple(OutboxEntry.model_validate(self.log.snapshot(event)) for event in latest.values())

    @staticmethod
    def successor(task: OutboxEntry, **changes) -> OutboxEntry:
        return OutboxEntry.model_validate(task.model_dump() | changes)

    def record(self, task: OutboxEntry, reason: Reason, actor: Actor, now: datetime, *, kind="task"):
        history = self.log.replay(task.id)
        self.log._append(task_id=task.id, previous_state=history[-1].new_state if history else None,
                        new_state=task.state.value, reason=reason, actor=actor, kind=kind,
                        snapshot=task.model_dump(mode="json"), origin=task.origin, now=now)

    def prepare(self, request: Request, *, idempotency_key: str, actor: Actor,
                now: datetime) -> OutboxEntry:
        if not idempotency_key.strip():
            raise ValueError("nonempty idempotency key required")
        request = Request.model_validate(request)
        if request.parent_request_id is not None:
            raise ValueError("prepare follow-ups through the bounded followup operation")
        if request.state is not RequestState.DRAFT:
            raise ValueError("prepare requires a draft")
        with self.log.writer():
            campaign = self.campaign()
            if request.campaign_id != campaign.id or request.id == self.campaign_key:
                raise ValueError("request belongs to another campaign or uses reserved id")
            if campaign.mode is CampaignMode.LIVE and request.origin is Origin.SYNTHETIC:
                raise ValueError("synthetic request cannot enter live outbox")
            key = opaque(idempotency_key)
            digest = content_digest(request)
            for prior in self.tasks():
                if prior.idempotency_digest == key:
                    if prior.preparation_digest != digest:
                        raise ValueError("idempotency key already binds different preparation")
                    return prior
                if prior.id == request.id:
                    raise ValueError("task already prepared under another key")
            task = OutboxEntry(**request.model_dump(), idempotency_digest=key, preparation_digest=digest)
            self.record(task, Reason.PREPARED, actor, utc(now))
            return task

    def transition(self, task_id: str, state: RequestState, *, reason: Reason, actor: Actor,
                   now: datetime, owner: Actor | None = None, next_trigger: datetime | None = None,
                   unscheduled_reason: Reason | None = None) -> OutboxEntry:
        state = RequestState(state)
        reason = Reason(reason)
        with self.log.writer():
            task = self.load(task_id)
            if self.campaign().status in {"PAUSED", "CANCELLED", "CLOSED"}:
                raise DispatchBlocked("campaign is stopped")
            allowed = set(_ALLOWED.get(task.state, set()))
            if task.state not in _TERMINAL | {RequestState.DISPATCHING, RequestState.DELIVERY_UNKNOWN, RequestState.PAUSED}:
                allowed |= {RequestState.DECLINED, RequestState.EXPIRED, RequestState.FAILED}
            if state not in allowed or reason != _TRANSITION_REASONS.get(state):
                raise ValueError("invalid transition or reason; use receipt/response/reconciliation operations")
            changes = dict(state=state)
            if state is RequestState.WAITING:
                quiet = parse_quiet_hours(self.campaign().limits.quiet_hours)
                trigger = quiet.next_allowed(next_trigger) if quiet and next_trigger else next_trigger
                changes.update(owner=owner, next_trigger=trigger, unscheduled_reason=unscheduled_reason,
                               schedule_state="SCHEDULED" if trigger is not None else "UNSCHEDULED")
            task = self.successor(task, **changes)
            self.record(task, reason, actor, now)
            return task

    def _check_limits(self, now: datetime, cost: Quantity):
        limits = self.campaign().limits
        interval = limits.minimum_interval
        spend = limits.spend_limit
        if limits.max_requests is None or interval.value is None or spend.value is None:
            raise DispatchBlocked("cadence and spend limits must be explicitly configured")
        if interval.unit != "seconds" or not interval.value >= 0:
            raise DispatchBlocked("minimum interval requires nonnegative seconds")
        if cost.value is None or not cost.value >= 0 or not spend.value >= 0 or not spend.unit or cost.unit != spend.unit:
            raise DispatchBlocked("known nonnegative cost and matching spend units required")
        amount, maximum = Decimal(str(cost.value)), Decimal(str(spend.value))
        if not amount.is_finite() or not maximum.is_finite() or not Decimal(str(interval.value)).is_finite():
            raise DispatchBlocked("finite limits and cost required")
        quiet = parse_quiet_hours(limits.quiet_hours)
        if quiet and quiet.contains(now):
            raise DispatchBlocked("recipient quiet hours")
        attempts = [event for event in self.log.events() if event.kind == "dispatch"]
        # Reserve every attempt, even an ambiguous one. Never infer a refund from silence.
        if len(attempts) >= limits.max_requests:
            raise DispatchBlocked("request limit reached")
        if attempts and (now - max(event.timestamp for event in attempts)).total_seconds() < interval.value:
            raise DispatchBlocked("minimum cadence interval has not elapsed")
        total = Decimal(0)
        for event in attempts:
            prior = OutboxEntry.model_validate(self.log.snapshot(event))
            if prior.cost_unit != spend.unit or prior.reserved_cost is None:
                raise DispatchBlocked("incompatible historical spend unit")
            total += prior.reserved_cost
        if total + amount > maximum:
            raise DispatchBlocked("spend limit reached")
        return amount

    def begin_attempt(self, task_id: str, *, actor: Actor, now: datetime, cost: Quantity,
                      authorize: Callable[[Request], bool]) -> DispatchClaim:
        """authorize is T05's fresh domain check; only literal True grants a claim."""
        now = utc(now)
        with self.log.writer():
            self.require_active()
            task = self.load(task_id)
            if task.state in {RequestState.DELIVERY_UNKNOWN, RequestState.DISPATCHING}:
                raise ReconciliationRequired("ambiguous or outstanding attempt must be reconciled")
            if task.attempt_id and task.state in {RequestState.SENT, RequestState.WAITING, RequestState.RECEIVED,
                                                 RequestState.ASSESSED, RequestState.CLOSED}:
                return DispatchClaim(attempt_id=task.attempt_id, created=False, task=task)
            if task.state is not RequestState.READY:
                raise DispatchBlocked("task is not ready")
            if authorize(task) is not True:
                raise DispatchBlocked("dispatch authorization required")
            amount = self._check_limits(now, cost)
            task = self.successor(task, state=RequestState.DISPATCHING, attempt_id=str(uuid4()),
                                  attempt_count=task.attempt_count + 1, reserved_cost=amount, cost_unit=cost.unit)
            self.record(task, Reason.DISPATCH_CLAIMED, actor, now, kind="dispatch")
            return DispatchClaim(attempt_id=task.attempt_id, created=True, task=task)

    def finish_attempt(self, task_id: str, attempt_id: str, *, outcome: Literal["accepted", "unknown"],
                       actor: Actor, now: datetime) -> OutboxEntry:
        if outcome not in {"accepted", "unknown"}:
            raise ValueError("unsupported outcome")
        with self.log.writer():
            task = self.load(task_id)
            if task.attempt_id != attempt_id or task.state is not RequestState.DISPATCHING:
                raise ValueError("attempt is not outstanding")
            task = self.successor(task, state=RequestState.SENT if outcome == "accepted" else RequestState.DELIVERY_UNKNOWN)
            self.record(task, Reason.PROVIDER_ACCEPTED if outcome == "accepted" else Reason.DELIVERY_AMBIGUOUS, actor, now)
            return task

    def reconcile(self, task_id: str, *, result: Literal["sent", "not_sent", "unknown"],
                  evidence_ref: str, actor: Actor, now: datetime) -> OutboxEntry:
        if result not in {"sent", "not_sent", "unknown"} or not evidence_ref.strip():
            raise ValueError("reconciliation requires an explicit result and evidence reference")
        with self.log.writer():
            task = self.load(task_id)
            if task.state not in {RequestState.DISPATCHING, RequestState.DELIVERY_UNKNOWN}:
                raise ValueError("no attempt to reconcile")
            state, reason = {
                "sent": (RequestState.SENT, Reason.RECONCILED_SENT),
                "not_sent": (RequestState.READY, Reason.RECONCILED_NOT_SENT),
                "unknown": (RequestState.DELIVERY_UNKNOWN, Reason.RECONCILED_UNKNOWN),
            }[result]
            task = self.successor(task, state=state, reconciliation_ref=opaque(evidence_ref))
            self.record(task, reason, actor, now, kind="reconciliation")
            return task

    def delivery_receipt(self, task_id: str, *, receipt_ref: str, actor: Actor, now: datetime) -> OutboxEntry:
        if not receipt_ref.strip():
            raise ValueError("receipt reference required")
        with self.log.writer():
            task = self.load(task_id)
            if task.attempt_id is None:
                raise ValueError("receipt requires a dispatch attempt")
            reference = opaque(receipt_ref)
            if reference in task.receipt_refs:
                return task
            task = self.successor(task, receipt_refs=(*task.receipt_refs, reference))
            self.record(task, Reason.DELIVERY_RECEIPT, actor, now, kind="receipt")
            return task

    def receive(self, task_id: str, contribution: Contribution, *, actor: Actor, now: datetime) -> OutboxEntry:
        # T06 retains the actual contribution; a receipt cannot satisfy this typed boundary.
        contribution = Contribution.model_validate(contribution)
        with self.log.writer():
            task = self.load(task_id)
            if contribution.request_id != task.id or contribution.campaign_id != self.campaign_id:
                raise ValueError("response does not belong to this request")
            if contribution.scope != self.campaign().scope:
                raise ValueError("response scope mismatch")
            if self.campaign().mode is CampaignMode.LIVE and contribution.origin is Origin.SYNTHETIC:
                raise ValueError("synthetic response cannot enter live outbox")
            reference = opaque(contribution.id)
            if reference in task.response_refs:
                return task
            if task.state not in {RequestState.SENT, RequestState.WAITING, RequestState.RECEIVED}:
                raise ValueError("request cannot receive a response in this state")
            task = self.successor(task, state=RequestState.RECEIVED,
                                  response_refs=(*task.response_refs, reference), next_trigger=None,
                                  schedule_state="UNSCHEDULED")
            self.record(task, Reason.RESPONSE_IMPORTED, actor, now, kind="response")
            return task

    def followup(self, task_id: str, request: Request, *, maximum: int, reason: Reason,
                 idempotency_key: str, actor: Actor, now: datetime) -> OutboxEntry:
        """Prepare a distinct bounded follow-up. Dispatch still passes every fresh gate."""
        if maximum < 0 or Reason(reason) is not Reason.FOLLOWUP_REQUIRED:
            raise ValueError("follow-up requires a bound and reason")
        with self.log.writer():
            self.require_active()
            parent = self.load(task_id)
            request = Request.model_validate(request)
            if parent.state is not RequestState.WAITING or request.parent_request_id != parent.id:
                raise ValueError("follow-up requires a waiting parent")
            if parent.parent_request_id is not None:
                raise ValueError("follow-ups must refer to the original request")
            children = [task for task in self.tasks() if task.parent_request_id == parent.id]
            for child in children:
                if child.idempotency_digest == opaque(idempotency_key):
                    if child.preparation_digest != content_digest(request):
                        raise ValueError("idempotency conflict")
                    return child
            bound = parent.max_followups if parent.max_followups is not None else (
                children[0].max_followups if children else maximum)
            if maximum != bound or len(children) >= bound:
                raise DispatchBlocked("follow-up bound reached or changed")
            if (request.campaign_id != parent.campaign_id or request.node_id != parent.node_id
                    or request.question_id != parent.question_id or request.origin != parent.origin
                    or parent.lineage() not in request.derived_from or request.state is not RequestState.DRAFT):
                raise ValueError("follow-up must preserve request scope and lineage")
            if request.id == self.campaign_key or not idempotency_key.strip() or any(t.id == request.id or t.idempotency_digest == opaque(idempotency_key)
                                                   for t in self.tasks()):
                raise ValueError("follow-up id or key already exists")
            child = OutboxEntry(**request.model_dump(), idempotency_digest=opaque(idempotency_key),
                                preparation_digest=content_digest(request))
            # The child is authoritative for counting; an interruption before the parent
            # update cannot permit an extra follow-up or forget the original bound.
            child = self.successor(child, max_followups=bound, followup_reason=reason)
            if children and any(t.max_followups != bound for t in children):
                raise DispatchBlocked("follow-up bound changed")
            self.record(child, Reason.FOLLOWUP_REQUIRED, actor, now)
            parent = self.successor(parent, max_followups=bound, followup_count=len(children) + 1,
                                    followup_reason=reason)
            self.record(parent, Reason.FOLLOWUP_REQUIRED, actor, now)
            return child

    def stop(self, *, cancel: bool, actor: Actor, now: datetime) -> Handoff:
        with self.log.writer():
            campaign = self.campaign()
            status = "CANCELLED" if cancel else "PAUSED"
            if campaign.status == "CANCELLED" and not cancel:
                raise ValueError("cancelled campaign cannot be resumed or paused")
            if campaign.status != status:
                updated = Campaign.model_validate(campaign.model_dump() | {"status": status})
                self.log._append(task_id=self.campaign_key, previous_state=campaign.status, new_state=status,
                                reason=Reason.OPERATOR_CANCEL if cancel else Reason.OPERATOR_PAUSE,
                                actor=actor, kind="campaign", snapshot=updated.model_dump(mode="json"),
                                origin=None, now=now)
            # The campaign gate is written first: a crash mid-pause still blocks all sends.
            for task in self.tasks():
                if task.state in _TERMINAL | {RequestState.PAUSED}:
                    continue
                if task.state is RequestState.DISPATCHING:
                    task = self.successor(task, state=RequestState.DELIVERY_UNKNOWN)
                    self.record(task, Reason.DELIVERY_AMBIGUOUS, actor, now)
                elif task.state is not RequestState.DELIVERY_UNKNOWN:
                    task = self.successor(task, paused_from=task.state, state=RequestState.PAUSED)
                    self.record(task, Reason.OPERATOR_CANCEL if cancel else Reason.OPERATOR_PAUSE, actor, now)
            return self.handoff()

    def handoff(self) -> Handoff:
        campaign = self.campaign()
        if campaign.status not in {"PAUSED", "CANCELLED"}:
            raise ValueError("handoff requires paused or cancelled campaign")
        tasks = self.tasks()
        unknown = tuple(opaque(task.id) for task in tasks
                        if task.state in {RequestState.DISPATCHING, RequestState.DELIVERY_UNKNOWN})
        return Handoff(campaign_ref=opaque(campaign.id), status=campaign.status,
                       task_refs=tuple(opaque(task.id) for task in tasks),
                       event_ids=tuple(event.id for event in self.log.events()),
                       reconciliation_required=unknown,
                       next_action="RECONCILE_WITHOUT_RETRY" if unknown else "OPERATOR_REVIEW")

    def resume(self, *, actor: Actor, now: datetime) -> Campaign:
        with self.log.writer():
            campaign = self.campaign()
            if campaign.status != "PAUSED":
                raise ValueError("only a paused campaign can resume")
            for task in self.tasks():
                if task.state is RequestState.PAUSED:
                    if task.paused_from is None:
                        raise ValueError("paused task has no prior state")
                    restored = self.successor(task, state=task.paused_from, paused_from=None)
                    self.record(restored, Reason.OPERATOR_RESUME, actor, now)
            updated = Campaign.model_validate(campaign.model_dump() | {"status": "ACTIVE"})
            self.log._append(task_id=self.campaign_key, previous_state="PAUSED", new_state="ACTIVE",
                             reason=Reason.OPERATOR_RESUME, actor=actor, kind="campaign",
                             snapshot=updated.model_dump(mode="json"), origin=None, now=now)
            return updated
