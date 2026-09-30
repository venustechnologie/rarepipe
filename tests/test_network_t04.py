from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import errno
import json

import pytest
from pydantic import ValidationError

from rarepipe.stages.network.eventlog import Reason, StoreBusy, opaque
from rarepipe.stages.network.model import (
    BudgetCadence, Campaign, CampaignMode, CampaignScope, Origin, Request, RequestState,
)
from rarepipe.stages.network.outbox import DispatchBlocked, Outbox, ReconciliationRequired
from rarepipe.stages.network.scheduler import QuietHours, Scheduler, WaitingTask
from rarepipe.stages.prospective.model import Actor, Quantity


NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
ACTOR = Actor(actor_type="HUMAN", identity="private-operator@example.org")


def limits(**changes):
    return BudgetCadence(**(dict(max_requests=3, minimum_interval=Quantity(value=60, unit="seconds"),
                                spend_limit=Quantity(value=6, unit="EUR")) | changes))


def campaign(**changes):
    return Campaign(**(dict(purpose="research", scope=CampaignScope.MVA_SCIENTIFIC,
                            mode=CampaignMode.LIVE, status="ACTIVE", owner=ACTOR,
                            limits=limits()) | changes))


def request(c, **changes):
    return Request(**(dict(campaign_id=c.id, question_id="private-question", node_id="node",
                           origin=Origin.PUBLIC_EVIDENCE, sender=ACTOR, recipient="private@example.org",
                           content="private variant chr1:123 A>T /private/case", disclosure_scope="private") | changes))


def prepared(tmp_path, c=None):
    c = c or campaign()
    box = Outbox(tmp_path, c)
    req = request(c)
    box.prepare(req, idempotency_key="private-key", actor=ACTOR, now=NOW)
    return box, req


def ready(box, req):
    return box.transition(req.id, RequestState.READY, reason=Reason.READY, actor=ACTOR, now=NOW)


def begin(box, req, **changes):
    return box.begin_attempt(req.id, **(dict(actor=ACTOR, now=NOW, cost=Quantity(value=2, unit="EUR"),
                                            authorize=lambda task: True) | changes))


def sent(box, req):
    ready(box, req)
    claim = begin(box, req)
    return box.finish_attempt(req.id, claim.attempt_id, outcome="accepted", actor=ACTOR, now=NOW)


def wait(box, req, **changes):
    return box.transition(req.id, RequestState.WAITING, **(dict(reason=Reason.WAIT_SCHEDULED,
                          actor=ACTOR, now=NOW, owner=ACTOR, next_trigger=NOW + timedelta(hours=1)) | changes))


def test_a12_waiting_is_a_validated_union_and_timers_are_utc(tmp_path):
    c = campaign()
    data = request(c).model_dump() | {"state": RequestState.WAITING}
    with pytest.raises(ValidationError):
        WaitingTask(**data)
    with pytest.raises(ValidationError):
        WaitingTask(**(data | {"schedule_state": "SCHEDULED", "next_trigger": NOW}))
    with pytest.raises(ValidationError):
        WaitingTask(**(data | {"schedule_state": "SCHEDULED", "owner": ACTOR}))
    unscheduled = WaitingTask(**(data | {"unscheduled_reason": Reason.OWNER_UNASSIGNED}))
    assert unscheduled.schedule_state == "UNSCHEDULED"
    box, req = prepared(tmp_path)
    sent(box, req)
    with pytest.raises(ValidationError):
        wait(box, req, owner=None)
    with pytest.raises(ValueError):
        wait(box, req, next_trigger=NOW.replace(tzinfo=None))
    local = NOW.astimezone(timezone(timedelta(hours=2)))
    task = wait(box, req, next_trigger=local)
    assert task.next_trigger.utcoffset() == timedelta(0)
    scheduler = Scheduler(Outbox(tmp_path, box.campaign()))
    assert [t.id for t in scheduler.due(NOW)] == [req.id]
    claimed = scheduler.claim(req.id, actor=ACTOR, now=NOW)
    assert claimed.schedule_state == "UNSCHEDULED"
    assert claimed.unscheduled_reason == Reason.TIMER_CLAIMED
    assert scheduler.due(NOW) == ()
    with pytest.raises(ValueError):
        scheduler.claim(req.id, actor=ACTOR, now=NOW)


def test_a13_deduplication_and_unknown_requires_reconciliation(tmp_path):
    box, req = prepared(tmp_path)
    before = box.log.events()
    assert box.prepare(req, idempotency_key="private-key", actor=ACTOR, now=NOW).id == req.id
    assert box.log.events() == before
    with pytest.raises(ValueError):
        box.prepare(request(box.campaign()), idempotency_key="private-key", actor=ACTOR, now=NOW)
    ready(box, req)
    first = begin(box, req)
    with pytest.raises(ReconciliationRequired):
        begin(box, req)
    task = box.finish_attempt(req.id, first.attempt_id, outcome="unknown", actor=ACTOR, now=NOW)
    assert task.state == RequestState.DELIVERY_UNKNOWN
    box = Outbox(tmp_path, box.campaign())
    with pytest.raises(ReconciliationRequired):
        begin(box, req)
    with pytest.raises(ValueError):
        ready(box, req)
    box.reconcile(req.id, result="unknown", evidence_ref="lookup-1", actor=ACTOR, now=NOW)
    with pytest.raises(ReconciliationRequired):
        begin(box, req)
    box.reconcile(req.id, result="not_sent", evidence_ref="lookup-2", actor=ACTOR, now=NOW)
    with pytest.raises(DispatchBlocked):
        begin(box, req, now=NOW + timedelta(minutes=2), authorize=lambda task: False)
    second = begin(box, req, now=NOW + timedelta(minutes=2))
    assert second.created and second.attempt_id != first.attempt_id
    box.finish_attempt(req.id, second.attempt_id, outcome="accepted", actor=ACTOR, now=NOW + timedelta(minutes=2))
    duplicate = begin(box, req)
    assert not duplicate.created and duplicate.attempt_id == second.attempt_id
    assert len([e for e in box.log.events() if e.kind == "dispatch"]) == 2


@pytest.mark.parametrize("config", [BudgetCadence(), limits(max_requests=None),
    limits(minimum_interval=Quantity(null_reason="UNKNOWN")),
    limits(spend_limit=Quantity(null_reason="UNKNOWN"))])
def test_a14_unset_limits_allow_preparation_but_block_dispatch(tmp_path, config):
    box, req = prepared(tmp_path, campaign(limits=config))
    assert ready(box, req).state == RequestState.READY
    with pytest.raises(DispatchBlocked):
        begin(box, req)
    assert all(e.kind != "dispatch" for e in box.log.events())


def test_limits_reserve_unknown_attempts_and_enforce_cadence_and_units(tmp_path):
    box, first = prepared(tmp_path, campaign(limits=limits(spend_limit=Quantity(value=3, unit="EUR"))))
    ready(box, first)
    begin(box, first)
    second = request(box.campaign())
    box.prepare(second, idempotency_key="second", actor=ACTOR, now=NOW)
    ready(box, second)
    with pytest.raises(DispatchBlocked, match="cadence"):
        begin(box, second)
    with pytest.raises(DispatchBlocked, match="spend"):
        begin(box, second, now=NOW + timedelta(minutes=2))
    with pytest.raises(DispatchBlocked, match="matching"):
        begin(box, second, now=NOW + timedelta(minutes=2), cost=Quantity(value=1, unit="USD"))


@pytest.mark.parametrize("cancel", [False, True])
def test_a30_stop_preserves_history_and_produces_private_reference_handoff(tmp_path, cancel):
    box, req = prepared(tmp_path)
    ready(box, req)
    begin(box, req)
    before = tuple(box.log.events())
    handoff = box.stop(cancel=cancel, actor=ACTOR, now=NOW)
    assert tuple(box.log.events())[:len(before)] == before
    assert handoff.status == ("CANCELLED" if cancel else "PAUSED")
    assert handoff.reconciliation_required == (opaque(req.id),)
    assert handoff.next_action == "RECONCILE_WITHOUT_RETRY"
    assert len(handoff.event_ids) == len(box.log.events())
    text = handoff.model_dump_json()
    assert "private" not in text and req.id not in text and req.recipient not in text
    restarted = Outbox(tmp_path, box.campaign())
    assert restarted.handoff() == handoff
    with pytest.raises(DispatchBlocked):
        begin(restarted, req)
    restarted.reconcile(req.id, result="not_sent", evidence_ref="provider-query", actor=ACTOR, now=NOW)
    with pytest.raises(DispatchBlocked):
        begin(restarted, req)
    assert Scheduler(restarted).due(NOW + timedelta(days=1)) == ()


def test_pause_of_waiting_task_records_paused_state(tmp_path):
    box, req = prepared(tmp_path)
    sent(box, req)
    wait(box, req)
    before = box.log.replay(req.id)
    box.stop(cancel=False, actor=ACTOR, now=NOW)
    assert box.load(req.id).state == RequestState.PAUSED
    assert box.load(req.id).paused_from == RequestState.WAITING
    assert box.log.replay(req.id)[:-1] == before


def test_receipt_is_not_a_response_and_deduplicates(tmp_path):
    box, req = prepared(tmp_path)
    sent(box, req)
    receipt = box.delivery_receipt(req.id, receipt_ref="provider-receipt", actor=ACTOR, now=NOW)
    assert receipt.state == RequestState.SENT
    assert not receipt.response_refs
    before = box.log.events()
    box.delivery_receipt(req.id, receipt_ref="provider-receipt", actor=ACTOR, now=NOW)
    assert box.log.events() == before
    with pytest.raises(ValueError):
        box.transition(req.id, RequestState.RECEIVED, reason=Reason.RESPONSE_IMPORTED, actor=ACTOR, now=NOW)
    with pytest.raises(ValidationError):
        box.receive(req.id, {"receipt_ref": "provider-receipt"}, actor=ACTOR, now=NOW)


def test_quiet_hours_and_dst_are_respected(tmp_path):
    quiet = QuietHours(timezone="Europe/Berlin", start="22:00", end="08:00")
    fall_back = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    trigger = quiet.next_allowed(fall_back)
    assert trigger == datetime(2026, 10, 25, 7, tzinfo=timezone.utc)
    box, req = prepared(tmp_path, campaign(limits=limits(quiet_hours="Europe/Berlin 13:00-15:00")))
    ready(box, req)
    with pytest.raises(DispatchBlocked, match="quiet"):
        begin(box, req)
    claim = begin(box, req, now=NOW + timedelta(hours=1))
    box.finish_attempt(req.id, claim.attempt_id, outcome="accepted", actor=ACTOR, now=NOW + timedelta(hours=1))
    task = wait(box, req, next_trigger=NOW)
    assert task.next_trigger == NOW + timedelta(hours=1)


def test_hardlink_fallback_replay_and_pointer_recovery(tmp_path, monkeypatch):
    def no_links(*args, **kwargs):
        raise OSError(errno.EOPNOTSUPP, "hard links unavailable")
    monkeypatch.setattr("rarepipe.stages.prospective.store.os.link", no_links)
    box, req = prepared(tmp_path)
    sent(box, req)
    expected = box.log.replay(req.id)
    (box.log.root / "HEAD").write_text("stale")
    reopened = Outbox(tmp_path, box.campaign())
    assert reopened.log.replay(req.id) == expected
    assert reopened.load(req.id).state == RequestState.SENT
    for event in reopened.log.events():
        assert event.digest.startswith("sha256:")
    serialized = json.dumps([e.model_dump(mode="json") for e in reopened.log.events()])
    for secret in (req.recipient, req.content, ACTOR.identity, "private-key", "private-question"):
        assert secret not in serialized


def test_concurrent_dispatch_and_stale_lock_fail_closed(tmp_path):
    box, req = prepared(tmp_path)
    ready(box, req)
    def attempt():
        try:
            return begin(box, req).created
        except (StoreBusy, ReconciliationRequired):
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: attempt(), range(2))) == 1
    (box.log.root / ".writer").mkdir()
    with pytest.raises(StoreBusy):
        box.reconcile(req.id, result="not_sent", evidence_ref="lookup", actor=ACTOR, now=NOW)


def test_synthetic_origin_cannot_enter_live_outbox(tmp_path):
    c = campaign()
    box = Outbox(tmp_path, c)
    with pytest.raises(ValueError, match="synthetic"):
        box.prepare(request(c, origin=Origin.SYNTHETIC), idempotency_key="fake", actor=ACTOR, now=NOW)
    with pytest.raises(ValueError, match="mode"):
        Outbox(tmp_path, Campaign.model_validate(c.model_dump() | {"mode": CampaignMode.SYNTHETIC}))


def test_bounded_followups_preserve_lineage(tmp_path):
    box, req = prepared(tmp_path)
    sent(box, req)
    parent = wait(box, req)
    child = request(box.campaign(), parent_request_id=req.id, derived_from=(parent.lineage(),))
    kwargs = dict(maximum=1, reason=Reason.FOLLOWUP_REQUIRED, actor=ACTOR, now=NOW)
    first = box.followup(req.id, child, idempotency_key="followup", **kwargs)
    assert first.parent_request_id == req.id
    assert box.load(req.id).followup_count == 1
    assert box.followup(req.id, child, idempotency_key="followup", **kwargs) == first
    with pytest.raises(DispatchBlocked):
        box.followup(req.id, request(box.campaign(), parent_request_id=req.id,
                                   derived_from=(parent.lineage(),)), idempotency_key="too-many", **kwargs)


def test_resume_preserves_waiting_owner_and_timer_but_cancel_is_final(tmp_path):
    box, req = prepared(tmp_path)
    sent(box, req)
    waiting = wait(box, req)
    box.stop(cancel=False, actor=ACTOR, now=NOW)
    box.resume(actor=ACTOR, now=NOW)
    assert box.load(req.id) == waiting
    assert len(Scheduler(box).due(NOW + timedelta(hours=2))) == 1
    box.stop(cancel=True, actor=ACTOR, now=NOW)
    with pytest.raises(ValueError):
        box.resume(actor=ACTOR, now=NOW)


def test_followup_cannot_bypass_bound_through_prepare(tmp_path):
    box, req = prepared(tmp_path)
    with pytest.raises(ValueError, match="bounded"):
        box.prepare(request(box.campaign(), parent_request_id=req.id), idempotency_key="bypass",
                    actor=ACTOR, now=NOW)


def test_crash_after_committed_claim_never_reissues_attempt(tmp_path, monkeypatch):
    box, req = prepared(tmp_path)
    ready(box, req)
    def crash(*args):
        raise OSError("simulated interruption before HEAD update")
    with monkeypatch.context() as patch:
        patch.setattr("rarepipe.stages.network.eventlog._atomic_write", crash)
        with pytest.raises(OSError):
            begin(box, req)
    restarted = Outbox(tmp_path, box.campaign())
    assert restarted.load(req.id).state == RequestState.DISPATCHING
    with pytest.raises(ReconciliationRequired):
        begin(restarted, req)
    restarted.reconcile(req.id, result="sent", evidence_ref="provider-lookup", actor=ACTOR, now=NOW)
    assert not begin(restarted, req).created
    assert len([e for e in restarted.log.events() if e.kind == "dispatch"]) == 1


def test_complete_lifecycle_requires_typed_response_and_deduplicates_it(tmp_path):
    from rarepipe.stages.network.model import Contribution, NetworkEnvelope, OperationalResponse
    from rarepipe.stages.prospective.nodes import ResponseState

    c = campaign(mode=CampaignMode.SYNTHETIC)
    box, req = prepared(tmp_path, c)
    sent(box, req)
    wait(box, req)
    event = OperationalResponse(origin=Origin.SYNTHETIC, state=ResponseState.NO_RELEVANT_DATA,
                envelope=NetworkEnvelope(question_id=req.question_id, node_identity=req.node_id,
                                         response_state=ResponseState.NO_RELEVANT_DATA))
    response = Contribution(origin=Origin.SYNTHETIC, derived_from=(event.lineage(),), campaign_id=c.id,
                            scope=c.scope, request_id=req.id, responder="synthetic-node", source="fixture",
                            received_at=NOW, event=event, extractor=ACTOR, evidence_family_id="fixture-family")
    task = box.receive(req.id, response, actor=ACTOR, now=NOW)
    assert task.state == RequestState.RECEIVED
    assert task.next_trigger is None
    before = box.log.events()
    assert box.receive(req.id, response, actor=ACTOR, now=NOW) == task
    assert box.log.events() == before
    with pytest.raises(ValueError, match="different content"):
        box.receive(req.id, Contribution.model_validate(response.model_dump() | {"source": "changed"}),
                    actor=ACTOR, now=NOW)
    box.transition(req.id, RequestState.ASSESSED, reason=Reason.ASSESSMENT_RECORDED, actor=ACTOR, now=NOW)
    box.transition(req.id, RequestState.CLOSED, reason=Reason.WORK_COMPLETE, actor=ACTOR, now=NOW)
    assert [e.new_state for e in box.log.replay(req.id)] == [
        "DRAFT", "READY", "DISPATCHING", "SENT", "WAITING", "RECEIVED", "ASSESSED", "CLOSED"]
    with pytest.raises(ValueError):
        ready(box, req)
