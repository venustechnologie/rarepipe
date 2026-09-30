"""T11: operator views — pure projections, A12/A15/A16/A30 and Q reporting boundary."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from rarepipe.stages.network.eventlog import Reason
from rarepipe.stages.network.model import (
    BudgetCadence, Campaign, CampaignMode, CampaignScope, Origin, Question, Request,
    RequestState,
)
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.network.policy_q import QReportingError, TabularQPolicy
from rarepipe.stages.network.sim.institution import AssumptionLabel, LabeledParam
from rarepipe.stages.network.sim.reward import ReportedRate
from rarepipe.stages.network.sim.scenarios import build_s01
from rarepipe.stages.network.sim.world import (
    LATENT_KEY_MARKERS, LatentScientificTruth, ResearchWorld, ResidualFunction,
    walk_for_latent_keys,
)
from rarepipe.stages.network.views import (
    STATED_UNKNOWN, SYNTHETIC_LABEL, QValueDisplay, all_view_payloads, audit_export_view,
    case_view, contribution_review_view, family_summary_view, learning_view, network_view,
    ScenariosView, requests_view, scenarios_view, summary_projection,
)
from rarepipe.stages.prospective.model import Actor, Knowledge, Quantity


NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
ACTOR = Actor(actor_type="HUMAN", identity="private-operator@example.org")
MASTER = 20260930
LATENT_CANARY = "LATENT_CANARY_VALUE_7f3a9b_MUST_NOT_LEAK"


def limits(**changes):
    return BudgetCadence(**(dict(
        max_requests=5,
        minimum_interval=Quantity(value=60, unit="seconds"),
        spend_limit=Quantity(value=20, unit="EUR"),
    ) | changes))


def campaign(**changes):
    from rarepipe.stages.network.model import new_id

    data = dict(
        purpose="research",
        scope=CampaignScope.MVA_SCIENTIFIC,
        mode=CampaignMode.LIVE,
        status="ACTIVE",
        owner=ACTOR,
        limits=limits(),
    )
    data.update(changes)
    data.setdefault("id", new_id())
    question = Question(
        id="Q01",
        campaign_id=data["id"],
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="What function remains when abundance is normalized?",
        state=Knowledge.UNKNOWN,
    )
    data["questions"] = (question,)
    return Campaign(**data)


def request(c: Campaign, **changes):
    return Request(**(dict(
        campaign_id=c.id,
        question_id="Q01",
        node_id="node-hubrecht",
        origin=Origin.PUBLIC_EVIDENCE,
        sender=ACTOR,
        recipient="private@example.org",
        content="bounded public request; no private variant",
        disclosure_scope="private",
    ) | changes))


def prepared(tmp_path: Path, c: Campaign | None = None):
    c = c or campaign()
    box = Outbox(tmp_path, c)
    req = request(c)
    box.prepare(req, idempotency_key="view-key", actor=ACTOR, now=NOW)
    return box, req, c


def test_a16_latent_truth_absent_from_every_view_payload(tmp_path):
    """Attack: distinctive latent values must not appear in any operator view."""
    from rarepipe.stages.network.sim.scenarios import ScenarioFixture

    world = ResearchWorld(
        master_seed=MASTER,
        campaign_id="latent-attack",
        scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(
            residual_function=ResidualFunction.RETAINED,
            abundance_normalized=True,
            selection_effect=True,
            params=(LabeledParam(
                name="attack_marker",
                value=LATENT_CANARY,
                label=AssumptionLabel.ASSUME,
                note="scorer-only canary; views must never read this",
            ),),
        ),
    )
    assert world.latent_for_scorer.residual_function is ResidualFunction.RETAINED
    assert any(p.value == LATENT_CANARY for p in world.latent_for_scorer.params)

    box, _req, c = prepared(tmp_path, campaign(id="latent-attack"))
    # Scenario payload is operator-visible labelled assumptions only — never latent_for_scorer.
    safe_scenario = ScenarioFixture(
        id="SAFE",
        event="operator_view_boundary",
        expected="no_latent_in_views",
        campaign_id="sim-safe",
        scope=CampaignScope.MVA_SCIENTIFIC,
        assumptions=(LabeledParam(
            name="world_family", value="synthetic-view-fixture",
            label=AssumptionLabel.ASSUME, note="labelled assumption; not scorer truth",
        ),),
        invariant_holds=True,
    )
    from rarepipe.stages.network.registry import load_seed
    payloads = all_view_payloads(box, registry=load_seed(), scenario=safe_scenario)
    kinds = {getattr(p, "view", type(p).__name__) for p in payloads}
    assert {
        "case", "requests", "family_summary", "audit_export", "learning",
        "scenarios", "network",
    } <= kinds

    views_source = Path(__file__).resolve().parents[1] / "src/rarepipe/stages/network/views.py"
    source_text = views_source.read_text()
    for banned in ("LatentScientificTruth", "latent_for_scorer", "scorer_only_bundle"):
        assert banned not in source_text

    for payload in payloads:
        leaked_keys = walk_for_latent_keys(payload)
        assert leaked_keys == [], (type(payload).__name__, leaked_keys)
        dumped = payload.model_dump(mode="json")
        assert walk_for_latent_keys(dumped) == []
        blob = json.dumps(dumped)
        assert LATENT_CANARY not in blob
        assert LATENT_CANARY not in " ".join(_flatten_strings(dumped))
        for key in _flatten_keys(dumped):
            norm = "".join(ch if ch.isalnum() else "_" for ch in key.casefold())
            assert norm not in LATENT_KEY_MARKERS, key
            assert not any(marker in norm for marker in LATENT_KEY_MARKERS), key


def _flatten_strings(obj) -> list[str]:
    found: list[str] = []

    def visit(node):
        if isinstance(node, dict):
            for value in node.values():
                visit(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                visit(item)
        elif node is None or isinstance(node, bool):
            return
        else:
            found.append(str(node))

    visit(obj)
    return found


def _flatten_keys(obj) -> list[str]:
    found: list[str] = []

    def visit(node):
        if isinstance(node, dict):
            for key, value in node.items():
                found.append(str(key))
                visit(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                visit(item)

    visit(obj)
    return found


def test_a15_synthetic_scenario_label_survives_summary_projection():
    scenario = build_s01(MASTER)
    view = scenarios_view(scenario)
    assert view.origin is Origin.SYNTHETIC
    assert view.synthetic_label == SYNTHETIC_LABEL
    summary = summary_projection(view)
    assert summary["origin"] == SYNTHETIC_LABEL
    assert summary["synthetic_label"] == SYNTHETIC_LABEL
    naive = {k: v for k, v in view.model_dump(mode="json").items()
             if k not in {"synthetic_label", "origin", "content_digest", "available_actions"}}
    assert "synthetic_label" not in naive
    repaired = summary_projection(view)
    assert repaired["synthetic_label"] == SYNTHETIC_LABEL
    with pytest.raises(Exception):
        Campaign(
            id=scenario.campaign_id, purpose="live", scope=scenario.scope,
            mode=CampaignMode.LIVE, contributions=scenario.contributions,
        )


def test_a12_unowned_waiting_task_is_surfaced_not_dropped(tmp_path):
    box, req, _c = prepared(tmp_path)
    box.transition(req.id, RequestState.READY, reason=Reason.READY, actor=ACTOR, now=NOW)
    claim = box.begin_attempt(
        req.id, actor=ACTOR, now=NOW, cost=Quantity(value=1, unit="EUR"),
        authorize=lambda task: True,
    )
    box.finish_attempt(req.id, claim.attempt_id, outcome="accepted", actor=ACTOR, now=NOW)
    box.transition(
        req.id, RequestState.WAITING, reason=Reason.WAIT_SCHEDULED, actor=ACTOR, now=NOW,
        owner=None, next_trigger=None, unscheduled_reason=Reason.OWNER_UNASSIGNED,
    )
    view = requests_view(box)
    assert len(view.waiting_surfaces) == 1
    surface = view.waiting_surfaces[0]
    assert surface.task_id == req.id
    assert surface.owner_identity == STATED_UNKNOWN
    assert surface.next_trigger == STATED_UNKNOWN
    assert surface.unscheduled_reason == Reason.OWNER_UNASSIGNED.value
    assert surface.ownership_gap is True
    assert any(row.task_id == req.id for row in view.tasks)
    assert view.stop_pause_controls.can_pause is True


def test_family_summary_does_not_fabricate_clinical_lead_or_partnership(tmp_path):
    box, _req, _c = prepared(tmp_path)
    view = family_summary_view(box)
    assert view.clinical_lead == STATED_UNKNOWN
    assert view.partnership_status == STATED_UNKNOWN
    assert view.efficacy_confidence == STATED_UNKNOWN
    assert view.family_preference == STATED_UNKNOWN
    assert view.continuous_activity == STATED_UNKNOWN
    dumped = json.dumps(view.model_dump(mode="json")).casefold()
    for fabricated in (
        "dr.", "partnership established", "efficacy confirmed", "family prefers",
        "ongoing continuous activity",
    ):
        assert fabricated not in dumped


def test_q_value_refuses_percentage_and_probability_framing():
    display = QValueDisplay.from_q(0.42, state_key="s0", action_key="a0")
    assert display.unit == "simulator_utility_estimate"
    assert "%" not in display.display
    assert "not a probability" in display.display.casefold()
    assert "simulator_utility" in display.display
    # Must not frame the numeric estimate itself as a percentage chance.
    assert not display.display.strip().endswith("%")
    assert "42%" not in display.display
    assert "0.42%" not in display.display
    with pytest.raises(QReportingError, match="percentage"):
        display.as_percentage()
    with pytest.raises(QReportingError, match="biological"):
        display.as_probability_of_biological_effect()
    with pytest.raises(QReportingError, match="institution"):
        display.as_chance_institution_helps()

    policy = TabularQPolicy(master_seed=MASTER, world_id="q-view")
    policy._q[("state-a", "action-b")] = 1.25
    c = campaign(id="learn-q")
    view = learning_view(c, policy=policy)
    assert view.q_values
    assert all(q.unit == "simulator_utility_estimate" for q in view.q_values)
    assert all("%" not in q.display for q in view.q_values)
    rate = ReportedRate(name="toy_rate", numerator=1, denominator=4)
    view2 = learning_view(c, rates=(rate,))
    assert view2.rates[0].numerator == 1
    assert view2.rates[0].denominator == 4
    assert view2.rates[0].interval_method == "wilson_95"


def test_a30_pause_cancel_preserves_recorded_history(tmp_path):
    box, req, _c = prepared(tmp_path)
    before = [event.id for event in box.log.events()]
    assert before

    paused = box.stop(cancel=False, actor=ACTOR, now=NOW + timedelta(minutes=1))
    assert paused.status == "PAUSED"
    after_pause = [event.id for event in box.log.events()]
    assert set(before).issubset(set(after_pause))
    assert len(after_pause) > len(before)

    handoff = box.handoff()
    assert handoff.status == "PAUSED"
    assert set(handoff.event_ids) == set(after_pause)

    audit = audit_export_view(box, handoff=handoff)
    assert audit.history_survived_stop is True
    assert audit.event_count == len(after_pause)
    assert set(audit.event_ids) == set(after_pause)
    assert audit.handoff is not None
    assert audit.campaign_status == "PAUSED"

    box.resume(actor=ACTOR, now=NOW + timedelta(minutes=2))
    cancelled = box.stop(cancel=True, actor=ACTOR, now=NOW + timedelta(minutes=3))
    assert cancelled.status == "CANCELLED"
    final_ids = [event.id for event in box.log.events()]
    assert set(before).issubset(set(final_ids))
    assert set(after_pause).issubset(set(final_ids))

    final_handoff = box.handoff()
    final_audit = audit_export_view(box, handoff=final_handoff)
    assert final_audit.history_survived_stop is True
    assert final_audit.campaign_status == "CANCELLED"
    requests = requests_view(box)
    assert requests.stop_pause_controls.can_resume is False
    assert requests.stop_pause_controls.can_handoff is True
    assert req.id in {row.task_id for row in requests.tasks}


def test_case_and_network_views_state_unknowns_explicitly(tmp_path):
    from rarepipe.stages.network.registry import load_seed

    box, _req, c = prepared(tmp_path)
    case = case_view(box)
    assert case.clinical_lead == STATED_UNKNOWN
    assert case.unknown_premises
    assert any(p.status == "unknown" for p in case.unknown_premises)
    assert case.available_actions

    net = network_view(c, registry=load_seed(), question_id="Q01")
    assert net.candidates
    for row in net.candidates:
        assert row.public_evidence_only is True
        assert row.resource_available == Knowledge.UNKNOWN.value


def test_contribution_review_rejects_synthetic_as_live_evidence(tmp_path):
    scenario = build_s01(MASTER)
    contrib = scenario.contributions[0]
    assert contrib.origin is Origin.SYNTHETIC
    live = campaign(id=contrib.campaign_id)
    with pytest.raises(ValueError, match="synthetic"):
        contribution_review_view(live, contribution=contrib)

    synth_campaign = Campaign(
        id=contrib.campaign_id,
        purpose="sim",
        scope=contrib.scope,
        mode=CampaignMode.SYNTHETIC,
        status="ACTIVE",
        contributions=scenario.contributions,
    )
    view = contribution_review_view(synth_campaign, contribution=contrib)
    assert view.synthetic_label == SYNTHETIC_LABEL
    assert view.origin is Origin.SYNTHETIC
    summary = summary_projection(view)
    assert summary["synthetic_label"] == SYNTHETIC_LABEL


def test_a16_the_real_catalogue_cannot_publish_its_own_hidden_truth():
    """A16 against the shipped catalogue, not a fixture chosen to avoid the collision.

    The scenario builders label each assumption with the latent field it sets, so S01's
    `residual_function = 'retained'` is literally S01's hidden truth. `scenarios_view` passed
    `scenario.assumptions` straight through, which published the answer the policy is meant to
    discover. Every catalogue entry is checked here, so a new builder cannot reintroduce it.
    """
    from rarepipe.stages.network.sim.scenarios import (
        WITHHELD, build_catalogue, truth_revealing_assumption_names,
    )

    revealing = truth_revealing_assumption_names()
    catalogue = build_catalogue()
    assert catalogue, "an empty catalogue would make this test vacuous"

    collisions = [
        (f.id, p.name) for f in catalogue for p in f.assumptions if p.name in revealing
    ]
    assert collisions, (
        "no catalogue assumption names a latent field, so this test no longer guards anything — "
        "check whether the catalogue or the latent type changed"
    )

    for fixture in catalogue:
        view = scenarios_view(fixture)
        assert view.reveals_world_truth is False
        blob = json.dumps(view.model_dump(mode="json"))
        for param in fixture.assumptions:
            if param.name in revealing:
                assert param.name in view.withheld_assumption_names
                assert str(param.value) not in blob, (fixture.id, param.name)
        # The dimension is still visible to an operator; only the answer is withheld.
        shown = {p.name: p.value for p in view.selected_assumptions}
        for name in view.withheld_assumption_names:
            assert shown[name] == WITHHELD


def test_a16_a_scenario_view_cannot_be_hand_built_around_the_redaction():
    """Constructing the payload directly must fail too, or the guard is only in one code path."""
    from rarepipe.stages.network.sim.scenarios import build_catalogue

    leaky = next(f for f in build_catalogue() if f.id == "S01")
    with pytest.raises(ValidationError, match="publish hidden world truth"):
        ScenariosView(
            scenario_id=leaky.id, campaign_id=leaky.campaign_id, scope=leaky.scope.value,
            selected_assumptions=leaky.assumptions, action_trace=(),
            resulting_decisions=(), expected_invariant=leaky.expected, invariant_holds=True,
            available_actions=(),
        )


def test_a16_post_hoc_review_can_reveal_but_says_so():
    """A reveal is available for post-hoc review and is marked, never silent."""
    from rarepipe.stages.network.sim.scenarios import build_catalogue

    fixture = next(f for f in build_catalogue() if f.id == "S01")
    revealed = scenarios_view(fixture, reveal_world_truth=True)
    assert revealed.reveals_world_truth is True
    assert revealed.withheld_assumption_names == ()
    assert "retained" in json.dumps(revealed.model_dump(mode="json"))
    # And the default is still the safe one.
    assert scenarios_view(fixture).reveals_world_truth is False


def test_a30_the_audit_account_distinguishes_no_handoff_from_one_not_fetched(tmp_path: Path):
    """A30: a paused campaign's handoff is obtainable; the account must not read as though the
    pause destroyed it. The view is a pure projection, so a caller may legitimately not pass one."""
    box, _req, _c = prepared(tmp_path)
    box.stop(cancel=False, actor=ACTOR, now=NOW)

    view = audit_export_view(box)
    account = " ".join(view.plain_language_account)
    assert "obtainable through outbox.handoff" in account
    assert view.history_survived_stop is True

    handoff = box.handoff()
    with_handoff = audit_export_view(box, handoff=handoff)
    assert with_handoff.handoff is not None
    assert with_handoff.history_survived_stop is True
    assert set(handoff.event_ids) == set(with_handoff.event_ids)
