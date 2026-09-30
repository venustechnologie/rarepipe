"""Acceptance tests for TASK T07: native plan adapter, supersession, dependency invalidation.

Asserts:
- A08: The native B16 route is preserved on the reduced-division/unknown-benefit fixture, and
  the native death-hold (B09) and other review routes regress unchanged.
- A09: Conflicting scientific findings route to context comparison and review, never a majority vote.
- A10: A frozen native plan cannot be mutated; a stale edit fails with a conflict.
- A11: No persona or agent actor can sign a required human review or release a scientific freeze.
- A22: A later correction or permission change invalidates affected derivatives AND suspends pending
  dependent dispatch, while history survives.
- A27: A coherent positive scientific branch terminates at confirmation/review tasks — no patient
  action is reachable, and this must be structurally true, not merely absent from the happy path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from rarepipe.stages.network.adapter import (
    NativePlanAdapter,
    PatientActionForbiddenError,
    PlanProposal,
    ProposalReadiness,
    ProposalStatus,
    assert_no_patient_action,
    native_action_vocabulary,
)
from rarepipe.stages.network.eventlog import Reason
from rarepipe.stages.network.intake import ContextComparison, ReviewTask, build_context_comparison
from rarepipe.stages.network.model import (
    Assessment,
    BudgetCadence,
    Campaign,
    CampaignMode,
    CampaignScope,
    ClaimDirection,
    ClaimRelation,
    Compartment,
    Contribution,
    EvidenceCriteria,
    HumanConfirmation,
    Intervention,
    NetworkEnvelope,
    Origin,
    Question,
    Request,
    RequestState,
    Restrictions,
    ScientificFinding,
    new_id,
)
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.prospective import fixtures as FX
from rarepipe.stages.prospective import workflow
from rarepipe.stages.prospective.model import (
    Actor,
    ActorType,
    DecisionRecord,
    Knowledge,
    OutcomeAvailability,
    PlanState,
    Quantity,
    ReviewDecision,
    Role,
)
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.policy import Policy, PolicyError
from rarepipe.stages.prospective.seed import seed_plan
from rarepipe.stages.prospective.store import (
    ImmutableError,
    PlanStore,
    VersionConflict,
    content_digest,
)

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
LEAD = Actor(actor_type=ActorType.HUMAN, identity="lead-scientist", roles=[Role.SCIENTIFIC_LEAD])
ASSAY = Actor(actor_type=ActorType.HUMAN, identity="assay-scientist", roles=[Role.ASSAY_SCIENTIST])
STATS = Actor(actor_type=ActorType.HUMAN, identity="statistician", roles=[Role.STATISTICIAN])
OPS = Actor(actor_type=ActorType.HUMAN, identity="research-ops", roles=[Role.RESEARCH_OPERATIONS])
AGENT = Actor(actor_type=ActorType.AGENT, identity="claude-agent", roles=[Role.SCIENTIFIC_LEAD], model_or_provider="anthropic")


# ── Fixture Helpers ─────────────────────────────────────────────────────────


def _store(tmp_path: Path, plan=None) -> PlanStore:
    """Build a temporary plan store in tmp_path (controlled drive never touched)."""
    plan = plan or FX.complete_plan()
    store = PlanStore(tmp_path / "ws", plan.plan_id)
    store.commit(plan, expected_parent=None, reason="fixture", kind="initial", actor="test-init")
    return store


def _reviewed_frozen(tmp_path: Path, availability: OutcomeAvailability | None = None) -> PlanStore:
    """Build a frozen plan in temporary store approved by all three required roles."""
    store = _store(tmp_path)
    for actor, role in ((LEAD, Role.SCIENTIFIC_LEAD), (ASSAY, Role.ASSAY_SCIENTIST), (STATS, Role.STATISTICIAN)):
        workflow.record_plan_review(store, actor, role, ReviewDecision.APPROVE_FOR_FREEZE, "approved for fixture freeze")
    workflow.freeze(store, LEAD, availability)
    return store


def _make_campaign(tmp_path: Path) -> tuple[Campaign, Outbox]:
    limits = BudgetCadence(
        max_requests=10,
        minimum_interval=Quantity(value=0.0, unit="seconds"),
        spend_limit=Quantity(value=500.0, unit="EUR"),
    )
    cmp = Campaign(
        id="cmp-mva-t07",
        purpose="MVA scientific investigation",
        case_ref="PP_MVA_001_RH_001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        mode=CampaignMode.LIVE,
        status="ACTIVE",
        owner=LEAD,
        limits=limits,
    )
    box = Outbox(tmp_path / "outbox_ws", cmp)
    return cmp, box


def _make_question(cmp_id: str = "cmp-mva-t07") -> Question:
    criteria = EvidenceCriteria(
        intervention=Intervention.NICOTINIC_ACID,
        compartment=Compartment.INTRACELLULAR,
        endpoint="nad_intracellular",
        species="human",
        model="fibroblasts",
        comparator="vehicle",
    )
    return Question(
        id="Q-t07-nad",
        campaign_id=cmp_id,
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Does nicotinic acid increase intracellular NAD?",
        evidence_criteria=criteria,
        required_reviewer=Role.SCIENTIFIC_LEAD,
    )


# ── A08: Native B16 and Review Routes Regress Unchanged ──────────────────────


def test_a08_native_b16_carries_reduced_division_when_benefit_is_unknown(tmp_path):
    """A08: Reduced-division / unknown-benefit fixture triggers B16 without B08; B16 actions are preserved."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation(
        "EXP02",
        FX.exp02(
            missegregation=Knowledge.UNKNOWN,
            checkpoint_activation="unchanged",
            checkpoint_silencing="unchanged",
            chromosome_alignment="unchanged",
            division_rate="decreased",
        ),
    )

    proposal = adapter.propose_evidence(obs, actor=OPS)

    assert "B16" in proposal.native_matches, "B16 must fire on established fall in division rate"
    assert "B08" not in proposal.native_matches, "B08 requires an improvement claim"
    assert {"RECORD_POPULATION_CHANGE", "CREATE_EVALUABILITY_REVIEW"} <= set(proposal.native_actions)
    assert any(t.type == "evaluability_review" for t in proposal.native_tasks)
    assert "H06" in proposal.decision.hypothesis_updates
    assert proposal.status is ProposalStatus.PENDING, "New evidence creates a pending proposal"


def test_a08_native_death_hold_b09_preserves_hold_with_b16(tmp_path):
    """A08: Established death triggers B09 adverse hold alongside B16 unchanged."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.exp02(missegregation=Knowledge.UNKNOWN, cell_death="increased"))
    proposal = adapter.propose_evidence(obs, actor=OPS)

    assert "B09" in proposal.native_matches and "B16" in proposal.native_matches
    assert "HOLD_PROGRESSION" in proposal.native_actions


def test_a08_b08_keeps_its_meaning_when_benefit_is_present(tmp_path):
    """A08: Improvement accompanied by selection triggers B08 and HOLD_RESCUE_CONCLUSION."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.SCENARIOS["exp02_selection"]["values"])
    proposal = adapter.propose_evidence(obs, actor=OPS)

    assert "B08" in proposal.native_matches and "B16" in proposal.native_matches
    assert "HOLD_RESCUE_CONCLUSION" in proposal.native_actions


def test_a08_b16_is_not_a_toxicity_or_selection_finding(tmp_path):
    """A08: B16 must request review, not assert toxicity or selective loss."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.exp02(missegregation=Knowledge.UNKNOWN, division_rate="decreased"))
    proposal = adapter.propose_evidence(obs, actor=OPS)

    all_text = " ".join(
        list(proposal.decision.interpretation)
        + list(proposal.native_actions)
        + [t.description for t in proposal.native_tasks]
    ).lower()

    assert "does not by itself declare toxicity" in all_text
    assert "not a finding of toxicity or selective loss" in all_text

    stripped = all_text
    for disclaimer in (
        "does not by itself declare toxicity or selective loss",
        "not a finding of toxicity or selective loss",
    ):
        stripped = stripped.replace(disclaimer, "")
    for forbidden_claim in ("toxic", "selective loss", "selection confirmed", "cytotoxic"):
        assert forbidden_claim not in stripped, f"B16 must not assert {forbidden_claim!r}"


def test_a08_b16_and_candidate_signal_require_review(tmp_path):
    """A08: When candidate signal B10 and B16 co-occur, review is required."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.exp02(division_rate="decreased"))
    proposal = adapter.propose_evidence(obs, actor=OPS)

    if "B10" in proposal.native_matches and "B16" in proposal.native_matches:
        assert proposal.status is ProposalStatus.DECISION_REVIEW_REQUIRED


def test_a08_adverse_flag_holds_even_when_unverified(tmp_path):
    """A08: Critical adverse flag creates hold even when result is unverified."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.exp02(), qc={"identity_verified": None, "critical_adverse_flag": True})
    proposal = adapter.propose_evidence(obs, actor=OPS)

    assert "B00" in proposal.native_matches
    assert "B09" in proposal.native_matches
    assert "B10" in proposal.decision.inadmissible_matches
    assert "RECORD_CANDIDATE_FUNCTIONAL_SIGNAL" not in proposal.native_actions


def test_a08_native_hold_is_preserved_over_policy_routing(tmp_path):
    """A08: Native rule outputs take precedence over external learned policy routing."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.exp02(missegregation=Knowledge.UNKNOWN, cell_death="increased"))
    proposal = adapter.propose_evidence(obs, actor=OPS)

    # Policy wants to skip to next phase, but adverse hold is active
    routed = adapter.route_next_action(proposal, preferred_policy_action="SCHEDULE_NEXT_EXPERIMENT")
    assert "SCHEDULE_NEXT_EXPERIMENT" not in routed
    assert "HOLD_PROGRESSION" in routed


# ── A09: Conflicting Findings Route to Comparison, Never Majority Vote ──────


def test_a09_conflicting_findings_route_to_context_comparison(tmp_path):
    """A09: Conflicting scientific findings produce context comparison and human review, never majority vote or averaging."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)
    q = _make_question()

    finding_pos = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(question_id=q.id, node_identity="lab-a", response_state=ResponseState.MEASURED_EFFECT),
        context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID, compartment=Compartment.INTRACELLULAR, endpoint="nad_intracellular", model="fibroblasts"),
        value=Quantity(value=50.0, unit="percent_increase"),
        quality="VALID",
    )
    contrib_pos = Contribution(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(finding_pos.lineage(),),
        campaign_id=q.campaign_id,
        scope=q.scope,
        request_id="req-pos",
        responder="lab-a@example.org",
        source="lab-a",
        received_at=NOW,
        event=finding_pos,
        permitted_content="50% increase in NAD+",
        extractor=OPS,
        evidence_family_id="fam-01",
    )

    finding_neg = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_NO_EFFECT,
        envelope=NetworkEnvelope(question_id=q.id, node_identity="lab-b", response_state=ResponseState.MEASURED_NO_EFFECT),
        context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID, compartment=Compartment.INTRACELLULAR, endpoint="nad_intracellular", model="patient_cells"),
        value=Quantity(value=0.0, unit="percent_increase"),
        quality="VALID",
    )
    contrib_neg = Contribution(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(finding_neg.lineage(),),
        campaign_id=q.campaign_id,
        scope=q.scope,
        request_id="req-neg",
        responder="lab-b@example.org",
        source="lab-b",
        received_at=NOW,
        event=finding_neg,
        permitted_content="no effect in patient cells",
        extractor=OPS,
        evidence_family_id="fam-02",
    )

    comparison, review_task = adapter.compare_conflicting_findings(
        finding_pos, finding_neg, q, contrib_pos, contrib_neg, now=NOW
    )

    assert isinstance(comparison, ContextComparison)
    assert comparison.question_id == q.id
    assert finding_pos.id in comparison.finding_ids
    assert finding_neg.id in comparison.finding_ids

    # Assert no averaging occurred: 50.0 and 0.0 remain distinct
    param_values = {p.parameter: (p.finding_a_value, p.finding_b_value) for p in comparison.comparison_points}
    assert param_values["estimate"] == ("50.0", "0.0")
    assert param_values["model"] == ("fibroblasts", "patient_cells")

    # Assert review task requires human adjudication, not majority voting
    assert isinstance(review_task, ReviewTask)
    assert "CONFLICT_REVIEW_REQUIRED" in review_task.reason
    assert "majority voting and averaging prohibited" in review_task.reason
    assert review_task.required_role is Role.SCIENTIFIC_LEAD


def test_a09_contradictory_native_actions_require_human_review(tmp_path):
    """A09: Conflicting actions within rule evaluation flag DECISION_REVIEW_REQUIRED without picking a winner."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    obs = FX.observation("EXP02", FX.exp02(), qc={"critical_adverse_flag": True})
    proposal = adapter.propose_evidence(obs, actor=OPS)

    assert {"B10", "B09"} <= set(proposal.native_matches)
    assert proposal.status is ProposalStatus.DECISION_REVIEW_REQUIRED
    assert ("PROPOSE_INDEPENDENT_REPLICATION", "HOLD_PROGRESSION") in proposal.native_conflicts


# ── A10: Frozen Plan Immutable; Stale Edit Fails with VersionConflict ────────


def test_a10_frozen_plan_cannot_be_mutated(tmp_path):
    """A10: Frozen versions are read-only; attempts to overwrite them fail with ImmutableError."""
    store = _reviewed_frozen(tmp_path)
    adapter = NativePlanAdapter(store)

    frozen = adapter.load_pinned()
    assert frozen.lifecycle is PlanState.FROZEN
    assert adapter.is_pin_current()

    # The physical file is 0444 read-only
    version_file = store.root / "versions" / f"{frozen.version_id}.json"
    assert oct(version_file.stat().st_mode)[-3:] == "444"

    from rarepipe.stages.prospective.store import _write_once
    with pytest.raises(ImmutableError):
        _write_once(version_file, b"{}")


def test_a10_stale_edit_fails_with_version_conflict(tmp_path):
    """A10: Applying a review or amendment naming a stale pin raises VersionConflict."""
    store = _reviewed_frozen(tmp_path)
    adapter = NativePlanAdapter(store)

    pinned_version_1 = adapter.pinned_version
    frozen_1 = adapter.load_pinned()

    # Ingest observation to produce a decision
    obs = FX.observation("EXP02", FX.exp02())
    proposal = adapter.propose_evidence(obs, actor=OPS)
    decision_id = proposal.decision.decision_id

    # Simulate concurrent commit advancing store HEAD behind the adapter's back
    plan_copy = frozen_1.model_copy(deep=True)
    next(e for e in plan_copy.endpoints if e.id == "E02_MIS").effect_criterion = Quantity(value=2.5, unit="ratio")
    store.commit(plan_copy, expected_parent=pinned_version_1, reason="concurrent amendment", kind="scientific", actor="concurrent-user")

    # The store HEAD has moved to version 2; adapter is still pinned to version 1
    assert not adapter.is_pin_current()

    # Checking pin currency raises VersionConflict
    with pytest.raises(VersionConflict) as exc_info:
        adapter.check_pin_current()
    assert "stale edit" in str(exc_info.value)

    # Applying a reviewed change on a stale pin raises VersionConflict
    with pytest.raises(VersionConflict):
        adapter.review_decision(
            decision_id,
            actor=LEAD,
            role=Role.SCIENTIFIC_LEAD,
            decision=ReviewDecision.ACCEPT_INTERPRETATION,
            rationale="accept on stale pin",
            expected_review_version=0,
        )

    # Proposing an amendment on a stale pin raises VersionConflict
    with pytest.raises(VersionConflict):
        adapter.amend_plan(plan_copy, reason="stale edit attempt", actor=LEAD)


def test_a10_amend_frozen_plan_creates_draft_successor_leaving_frozen_parent_intact(tmp_path):
    """A10: Editing a frozen plan creates a successor in DRAFT, preserving the immutable parent."""
    store = _reviewed_frozen(tmp_path)
    adapter = NativePlanAdapter(store)

    parent_version = adapter.pinned_version
    frozen_parent = adapter.load_pinned()

    # Ingest result to trigger post-result amendment logic
    adapter.propose_evidence(FX.observation("EXP02", FX.exp02()), actor=OPS)

    edited = frozen_parent.model_copy(deep=True)
    next(e for e in edited.endpoints if e.id == "E02_MIS").effect_criterion = Quantity(value=2.0, unit="ratio")

    successor = adapter.amend_plan(edited, reason="tighten threshold", actor=LEAD)

    assert successor.version_id != parent_version
    assert successor.parent_version == parent_version
    assert successor.lifecycle is PlanState.DRAFT
    assert successor.change_kind == "post_result_amendment"

    # Parent remains unchanged and frozen
    assert store.load(parent_version).lifecycle is PlanState.FROZEN
    assert store.load(parent_version).version_id == parent_version


# ── A11: Agent Cannot Sign Human Review or Release Scientific Freeze ────────


def test_a11_agent_actor_cannot_sign_human_review(tmp_path):
    """A11: An agent actor cannot sign a required human review; PolicyError is surfaced."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    proposal = adapter.propose_evidence(FX.observation("EXP02", FX.exp02()), actor=OPS)

    with pytest.raises(PolicyError, match="cannot sign as a human reviewer or freeze a plan"):
        adapter.review_decision(
            proposal.decision.decision_id,
            actor=AGENT,
            role=Role.SCIENTIFIC_LEAD,
            decision=ReviewDecision.ACCEPT_INTERPRETATION,
            rationale="AI signed review",
        )


def test_a11_agent_actor_cannot_freeze_plan(tmp_path):
    """A11: An agent actor cannot release a scientific freeze."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    with pytest.raises(PolicyError, match="cannot sign as a human reviewer or freeze a plan"):
        adapter.freeze_plan(actor=AGENT)


def test_a11_human_without_required_role_cannot_review(tmp_path):
    """A11: A human lacking the designated role cannot sign review for that role."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    proposal = adapter.propose_evidence(FX.observation("EXP02", FX.exp02()), actor=OPS)

    with pytest.raises(PolicyError, match="does not hold the scientific_lead role"):
        adapter.review_decision(
            proposal.decision.decision_id,
            actor=STATS,  # STATS has role STATISTICIAN, not SCIENTIFIC_LEAD
            role=Role.SCIENTIFIC_LEAD,
            decision=ReviewDecision.ACCEPT_INTERPRETATION,
            rationale="statistician attempting lead review",
        )


def test_a11_candidate_baseline_gaps_block_human_freeze(tmp_path):
    """A11: Even human lead cannot freeze a plan with scientific readiness gaps (e.g. 112 gaps)."""
    # Seed plan starts with candidate baseline and 112 gaps
    store = _store(tmp_path, seed_plan(FX.synthetic_baseline(status="CANDIDATE")))
    adapter = NativePlanAdapter(store)

    report = adapter.validate()
    assert not report.freezable
    assert len(report.scientific_readiness) > 50

    with pytest.raises(workflow.WorkflowError, match="scientific freeze refused") as exc_info:
        adapter.freeze_plan(actor=LEAD)
    assert any("model_requirements" in p or "feasibility" in p for p in exc_info.value.problems)


# ── A22: Invalidation of Derivatives, Suspension of Dispatch, History Intact ─


def test_a22_source_correction_invalidates_derivatives_suspends_dispatch(tmp_path):
    """A22: Source correction or permission revocation invalidates derivatives, suspends dispatch, preserves history."""
    store = _store(tmp_path)
    cmp, outbox = _make_campaign(tmp_path)
    adapter = NativePlanAdapter(store, campaign=cmp, outbox=outbox)

    # 1. Prepare and ready a downstream request in the outbox
    req = Request(
        campaign_id=cmp.id,
        question_id="Q-t07-nad",
        node_id="node-target-lab",
        content="Requesting analysis based on premise SRC_01",
        disclosure_scope="private",
        sender=LEAD,
        recipient="lab@example.org",
        origin=Origin.PUBLIC_EVIDENCE,
    )
    outbox_task = outbox.prepare(req, idempotency_key="key-req-01", actor=LEAD, now=NOW)
    outbox.transition(outbox_task.id, RequestState.READY, reason=Reason.READY, actor=LEAD, now=NOW)
    adapter.track_request("SRC_01", outbox_task.id)

    # 2. Ingest evidence citing SRC_01 into the adapter
    obs = FX.observation("EXP02", FX.exp02())
    proposal = adapter.propose_evidence(obs, actor=OPS, source_id="SRC_01")
    assert proposal.status is ProposalStatus.PENDING

    # 3. Create and register an assessment referencing SRC_01
    q = _make_question(cmp.id)
    finding = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(question_id=q.id, node_identity="node-target-lab", response_state=ResponseState.MEASURED_EFFECT),
        context=q.evidence_criteria,
        quality="VALID",
    )
    contrib = Contribution(
        id="SRC_01",
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(finding.lineage(),),
        campaign_id=cmp.id,
        scope=cmp.scope,
        request_id=outbox_task.id,
        responder="lab@example.org",
        source="SRC_01",
        received_at=NOW,
        event=finding,
        permitted_content="evidence text",
        extractor=OPS,
        evidence_family_id="ef-src-01",
    )
    assessment = Assessment(
        id="asm-01",
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(contrib.lineage(),),
        contribution=contrib,
        question=q,
        relations=(),
        reviewer=OPS,
        decision="PROPOSED",
    )
    adapter.register_assessment(assessment)

    # Observations and decisions exist in store prior to invalidation
    assert len(store.observations()) == 1
    assert len(store.decisions()) == 1

    # 4. Trigger source invalidation due to permission restriction / data correction
    report = adapter.invalidate_source(
        "SRC_01",
        reason="Errata: sample cross-contamination confirmed by provider",
        actor=LEAD,
        permission_restricted=True,
        now=NOW,
    )

    # Assert 1: Proposal is marked STALE
    updated_proposal = adapter._proposals[proposal.id]
    assert updated_proposal.status is ProposalStatus.STALE
    assert "cross-contamination" in updated_proposal.invalidation_reason
    assert proposal.id in report.affected_proposals

    # Assert 2: Assessment is included in affected list
    assert assessment.id in report.affected_assessments

    # Assert 3: Human review task created
    assert len(report.review_tasks) == 1
    review_task = report.review_tasks[0]
    assert review_task.required_role is Role.SCIENTIFIC_LEAD
    assert "cross-contamination" in review_task.reason
    assert "Permission restricted: True" in review_task.reason

    # Assert 4: Downstream dispatch in outbox is SUSPENDED (state PAUSED)
    assert outbox_task.id in report.suspended_dispatch_tasks
    suspended_task = outbox.load(outbox_task.id)
    assert suspended_task.state is RequestState.PAUSED
    assert suspended_task.paused_from is RequestState.READY

    # Assert 5: History survives! Prior observations and decisions are NOT deleted
    assert len(store.observations()) == 1
    assert len(store.decisions()) == 1
    # Outbox event log retains complete audit trail
    assert len(outbox.log.events()) >= 3


# ── A27: Positive Branch Ends at Confirmation/Review; No Patient Action ─────


def test_a27_coherent_positive_branch_terminates_at_review_no_patient_action(tmp_path):
    """A27: Coherent positive branch terminates at confirmation/review; patient actions are structurally unreachable."""
    store = _reviewed_frozen(tmp_path)
    adapter = NativePlanAdapter(store)

    # Phase 1: EXP02 coherent functional benefit
    obs_exp02 = FX.observation("EXP02", FX.exp02())
    proposal_2 = adapter.propose_evidence(obs_exp02, actor=OPS)

    assert "B10" in proposal_2.native_matches
    assert {"RECORD_CANDIDATE_FUNCTIONAL_SIGNAL", "PROPOSE_INDEPENDENT_REPLICATION"} <= set(proposal_2.native_actions)

    # Human review accepts candidate signal and replication proposal
    record_2, plan_v2 = adapter.review_decision(
        proposal_2.decision.decision_id,
        actor=LEAD,
        role=Role.SCIENTIFIC_LEAD,
        decision=ReviewDecision.ACCEPT_INTERPRETATION,
        rationale="candidate functional signal accepted; propose replication",
        expected_review_version=0,
    )
    assert plan_v2 is not None
    assert adapter.pinned_version == plan_v2.version_id

    # Phase 2: EXP03 replicated benefit
    obs_exp03 = FX.observation(
        "EXP03",
        FX.exp02(sirt2_activity=None, k668_acetylation=None),
        context={"replicated": "yes", "exposure_feasible": "yes", "relevance_review": "yes"},
    )
    proposal_3 = adapter.propose_evidence(obs_exp03, actor=OPS)

    assert "B13" in proposal_3.native_matches
    assert "CREATE_TRANSLATIONAL_REVIEW_TASK" in proposal_3.native_actions

    # Review B13 creates translational review task
    record_3, plan_v3 = adapter.review_decision(
        proposal_3.decision.decision_id,
        actor=LEAD,
        role=Role.SCIENTIFIC_LEAD,
        decision=ReviewDecision.ACCEPT_INTERPRETATION,
        rationale="replication verified; create translational review task",
        expected_review_version=0,
    )

    # Task description explicitly emphasizes "No patient intervention"
    trans_tasks = [t for t in record_3.proposed_tasks if t.type == "translational_review"]
    assert len(trans_tasks) == 1
    assert "No patient intervention" in trans_tasks[0].description

    # Structural verification: No patient action is reachable
    assert adapter.is_patient_action_reachable() is False

    # Attempting to introduce patient dosing or treatment raises PatientActionForbiddenError
    with pytest.raises(PatientActionForbiddenError):
        assert_no_patient_action(["ADMINISTER_TO_PATIENT"])

    with pytest.raises(PatientActionForbiddenError):
        assert_no_patient_action(["PRESCRIBE_HIGH_DOSE_NIACIN"])

    with pytest.raises(PatientActionForbiddenError):
        adapter.review_decision(
            proposal_3.decision.decision_id,
            actor=LEAD,
            role=Role.SCIENTIFIC_LEAD,
            decision=ReviewDecision.ACCEPT_INTERPRETATION,
            rationale="trying forbidden patient action",
            expected_review_version=record_3.review_version,
            selected_actions=["TREAT_PATIENT_CLINICALLY"],
        )


# ── Proposal Readiness & Alternatives ───────────────────────────────────────


def test_conditional_vs_apply_ready_proposals(tmp_path):
    """Proposals with missing endpoints/methods remain CONDITIONAL; complete evidence is APPLY_READY."""
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)

    # Missing missegregation readout
    obs_missing = FX.observation("EXP02", FX.exp02(missegregation=None))
    proposal_missing = adapter.propose_evidence(obs_missing, actor=OPS)

    assert proposal_missing.readiness is ProposalReadiness.CONDITIONAL
    assert any("missegregation" in dep for dep in proposal_missing.missing_dependencies)
    assert proposal_missing.status is ProposalStatus.PENDING

    # Complete observation with resolved context on complete plan is APPLY_READY
    obs_complete = FX.observation(
        "EXP02",
        FX.exp02(),
        context={"replicated": "yes", "exposure_feasible": "yes", "relevance_review": "yes"},
    )
    proposal_complete = adapter.propose_evidence(obs_complete, actor=OPS)

    assert proposal_complete.readiness is ProposalReadiness.APPLY_READY
    assert proposal_complete.status is ProposalStatus.PENDING


# ── A27: the guard must work in both directions ──────────────────────────────


def test_a27_ordinary_preclinical_work_is_not_blocked():
    """A guard that blocks the plan's own experiments is not a safety feature.

    The first implementation matched bare substrings, so "DOSE" refused "a 10 mM dose in patient-
    derived fibroblasts" and "compare dose levels in vitro" — the exact preclinical work Stage 10
    exists to plan. A patient-derived fibroblast is a cell line, not a patient.
    """
    for text in (
        "Measure intracellular NAD+ in patient-derived fibroblasts at a 10 mM dose of nicotinic acid",
        "Compare division rate across dose levels in vitro",
        "Treat cultured cells with NMN and record viability",
        "A cellular result does not establish patient benefit; no patient intervention follows",
    ):
        assert_no_patient_action([text])


@pytest.mark.parametrize("directive", [
    "Start the child on niacin at breakfast",
    "Begin niacin therapy in the index case",
    "Recommend the family give nicotinic acid daily",
    "Initiate supplementation in the proband",
    "Administer nicotinic acid to the patient",
    "Dose the patient at 500 mg daily",
])
def test_a27_a_patient_directive_is_refused_however_it_is_phrased(directive: str):
    """None of these contained a token the original blacklist looked for, so all of them passed."""
    with pytest.raises(PatientActionForbiddenError):
        assert_no_patient_action([directive])


def test_a27_actions_are_checked_against_the_engines_closed_vocabulary():
    """The real guarantee: the native engine has no patient action to emit.

    Checking membership of `rules.descriptors()`'s action set is structural, where a word list
    over prose can only ever be defence in depth.
    """
    vocabulary = native_action_vocabulary()
    assert vocabulary, "an empty vocabulary would make this check vacuous"
    assert not any("PATIENT" in a or "ADMINISTER" in a or "PRESCRIBE" in a for a in vocabulary)

    assert_no_patient_action(sorted(vocabulary))  # every real action passes

    for injected in ("ADMINISTER_TO_PATIENT", "PRESCRIBE_NICOTINIC_ACID", "START_TREATMENT"):
        with pytest.raises(PatientActionForbiddenError, match="not in the native rule engine"):
            assert_no_patient_action([injected])


def test_a10_a_stale_pin_whose_version_is_gone_still_raises_a_conflict(tmp_path):
    """A pin pointing at an unreadable version is a stale edit, not a file error.

    check_pin_current loads the pinned version to build a diff; when that version does not exist
    the caller got FileNotFoundError, which it has no reason to catch, instead of VersionConflict.
    """
    store = _store(tmp_path)
    adapter = NativePlanAdapter(store)
    head = store.head()
    adapter.pinned_version = f"{store.plan_id}@0001-notarealversion"

    with pytest.raises(VersionConflict, match="nothing was written"):
        adapter.check_pin_current()
    assert store.head() == head
