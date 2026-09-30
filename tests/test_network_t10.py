"""T10: tabular Q-learning policy, masking, shadow mode (A17, A18, A19)."""

from __future__ import annotations

import pytest

from rarepipe.stages.network.model import CampaignScope, ClaimDirection
from rarepipe.stages.network.policy_q import (
    FEATURE_CONTRACT_VERSION, SIMULATOR_SETTING_LABEL, ActionKind, JointAction,
    PairedPolicyRunner, QReportingError, ShadowRecommendation, SimulatorHyperparameters,
    TabularQPolicy, UnrepresentableActionError, encode_observation_state,
    format_q_as_simulator_utility, is_unrepresentable_action_token, make_training_event,
    render_q_value, require_representable_kind, run_declared_reward_training,
)
from rarepipe.stages.network.sim.baselines import (
    BaselineAction, EpisodeConstraints, SharedResourceBudget, default_constraints,
    default_shared_budget,
)
from rarepipe.stages.network.sim.reward import (
    ResolutionAttempt, RewardScorer, default_mva_declaration,
)
from rarepipe.stages.network.sim.splits import default_world_split
from rarepipe.stages.network.sim.world import (
    LatentScientificTruth, PolicyObservation, ResearchWorld, ResidualFunction,
)


MASTER = 20260930


def _world() -> ResearchWorld:
    return ResearchWorld(
        master_seed=MASTER, campaign_id="t10-world", scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(
            residual_function=ResidualFunction.RETAINED, abundance_normalized=True,
        ),
    )


def test_shared_action_type_is_joint_action():
    assert BaselineAction is JointAction
    action = JointAction(
        kind=ActionKind.REQUEST_EXISTING_FINDING.value,
        question_id="Q01", node_id="fn-northbridge-cell", rationale="test",
    ).with_digest()
    assert action.macro == "node"
    assert action.content_digest and action.content_digest.startswith("sha256:")
    assert ActionKind.REQUEST_METHOD_FEASIBILITY.value in {k.value for k in ActionKind}
    assert ActionKind.PREPARE_SCIENTIFIC_REVIEW.value in {k.value for k in ActionKind}
    assert ActionKind.REQUEST_LOCAL_ANALYSIS_PROPOSAL.value in {k.value for k in ActionKind}


def test_patient_and_lab_actions_are_unrepresentable():
    from pydantic import ValidationError

    for token in (
        "lab_execution", "laboratory_execution", "patient_action", "treat_patient",
        "prescribe", "enroll_patient", "run_assay",
    ):
        assert is_unrepresentable_action_token(token)
        with pytest.raises(UnrepresentableActionError):
            require_representable_kind(token)
        # Pydantic wraps the domain error in ValidationError at construction.
        with pytest.raises((UnrepresentableActionError, ValidationError), match="unrepresentable"):
            JointAction(kind=token, question_id="Q01", node_id="fn-northbridge-cell")
    # Not merely unused: the enum has no such members.
    assert "lab_execution" not in {k.value for k in ActionKind}
    assert "patient_action" not in {k.value for k in ActionKind}


def test_a17_persisted_parameters_change_from_declared_reward():
    """A17: Q parameters must move under the declared reward; a static table would fail."""
    world = _world()
    scorer = RewardScorer(world, default_mva_declaration())
    scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-t10",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c1",),
    ))
    assert scorer.value_state.total_V == 1.0
    breakdown = scorer.reward_step(
        previous_V=0.0, elapsed_ticks=1, cost_units=1.0, contact_units=1,
        unsupported_decisions=0, contacted_nodes=("fn-northbridge-cell",),
    )
    assert breakdown.reward != 0.0
    assert breakdown.convention_label == "synthetic_benchmark_convention"

    policy = TabularQPolicy(master_seed=MASTER, world_id="a17")
    before = policy.persist()
    assert before.update_count == 0
    assert before.entries == ()
    assert before.hyperparameters.label == SIMULATOR_SETTING_LABEL

    obs = world.policy_observation(prompts=("train",))
    budget = default_shared_budget()
    constraints = default_constraints()
    # Several training transitions using the scorer's declared reward — not a static route.
    transitions = [
        (obs, budget, constraints, breakdown.reward, False),
        (obs, budget, constraints, breakdown.reward, False),
        (obs, budget, constraints, breakdown.reward, True),
    ]
    after = run_declared_reward_training(
        policy, transitions=transitions, split_role="train",
    )
    assert after.update_count >= 3
    assert after.training_events >= 3
    assert after.entries  # parameters exist
    assert after.content_digest != before.content_digest
    # At least one Q value moved away from the zero initialization.
    assert any(abs(e.value) > 1e-12 for e in after.entries)

    # Persistence round-trip preserves the learned table.
    restored = TabularQPolicy(master_seed=MASTER, world_id="a17-restored")
    restored.load_parameters(after)
    assert restored.persist().as_table() == after.as_table()

    # Held-out fitting is refused.
    with pytest.raises(ValueError, match="held-out"):
        run_declared_reward_training(
            policy, transitions=transitions, split_role="held_out",  # type: ignore[arg-type]
        )


def test_a18_eligibility_masks_constrain_exploration():
    """A18: ineligible actions must be unreachable under epsilon-random draws, not merely rare."""
    world = _world()
    obs = world.policy_observation()
    # Block one eligible node via permission mask; exclude another via constraints.
    constraints = EpisodeConstraints(
        excluded_node_ids=("excluded-mva-society", "excluded-family", "excluded-child"),
        eligible_node_ids=(
            "fn-northbridge-cell", "fn-cedar-nad", "fn-holloway-mitotic",
            "fn-redrock-access", "fn-silent-harbour",
        ),
        eligible_question_ids=("Q01", "Q02", "Q04", "Q05", "Q00"),
        permission_blocked_nodes=("fn-cedar-nad",),
    )
    budget = SharedResourceBudget(
        max_ticks=100, max_cost_units=50.0, max_contact_units=20, max_requests=12,
    )
    # Force pure exploration for the whole schedule.
    hyper = SimulatorHyperparameters(epsilon_start=1.0, epsilon_end=1.0)
    policy = TabularQPolicy(
        hyperparameters=hyper, master_seed=MASTER, world_id="a18",
    )
    # Also block prepare_scientific_review until evidence exists (gate).
    eligible = policy.eligible_joint_actions(obs, budget, constraints)
    eligible_keys = {a.action_key() for a in eligible}
    assert eligible_keys
    assert all(a.node_id != "fn-cedar-nad" for a in eligible)
    assert all(a.node_id != "excluded-mva-society" for a in eligible)
    assert all(a.kind != ActionKind.PREPARE_SCIENTIFIC_REVIEW.value for a in eligible)

    selected_keys: set[str] = set()
    for step in range(500):
        decision = policy.select(
            obs, budget, constraints, mode="train", step=step, total_steps=500,
        )
        assert decision.selected is not None
        assert decision.selection_probability is not None
        assert decision.selected.action_key() in eligible_keys
        assert decision.selected.node_id != "fn-cedar-nad"
        assert decision.selected.node_id not in constraints.excluded_node_ids
        selected_keys.add(decision.selected.action_key())
    # Exploration actually varied across the eligible set (not a single forced action).
    assert len(selected_keys) > 1


def test_a19_learner_and_baselines_share_observations_and_budget():
    world = _world()
    obs = world.policy_observation(prompts=("shared-a19",), feature_tensor=(("budget", 1.0),))
    budget = default_shared_budget()
    constraints = default_constraints()
    runner = PairedPolicyRunner(budget=budget, constraints=constraints)
    shared = runner.shared_inputs()
    assert shared["budget"] == budget.model_dump(mode="json")
    assert shared["constraints"] == constraints.model_dump(mode="json")

    learner_d, expert_d, heur_d = runner.decide_all(obs)
    assert learner_d.observation_digest == expert_d.observation_digest == heur_d.observation_digest
    assert learner_d.observation_digest == obs.content_digest
    assert expert_d.budget.model_dump() == heur_d.budget.model_dump() == budget.model_dump()
    assert expert_d.constraints == heur_d.constraints == constraints
    # One action space: baseline actions are JointAction.
    if expert_d.action is not None:
        assert isinstance(expert_d.action, JointAction)
        assert expert_d.action.kind in {k.value for k in ActionKind}
    if heur_d.action is not None:
        assert isinstance(heur_d.action, JointAction)
    # Held-out evaluation uses epsilon 0.
    assert learner_d.epsilon == 0.0
    assert learner_d.mode == "held_out"

    split = default_world_split()
    assert set(split.train_families).isdisjoint(split.held_out_families)


def test_shadow_mode_records_recommendation_without_dispatch():
    world = _world()
    obs = world.policy_observation()
    budget = default_shared_budget()
    constraints = default_constraints()
    policy = TabularQPolicy(master_seed=MASTER, world_id="shadow")
    actual = JointAction(
        kind=ActionKind.WAIT.value, question_id="Q00", node_id="fn-silent-harbour",
        rationale="human_authorized_wait", cost_units=0.0,
    ).with_digest()
    rec = policy.shadow_recommend(
        obs, budget, constraints, campaign_id="camp-auth",
        actual_authorized_action=actual,
    )
    assert isinstance(rec, ShadowRecommendation)
    assert rec.dispatched is False
    assert rec.actual_authorized_action == actual
    assert rec.recommendation is not None
    assert rec.decision.mode == "shadow"
    assert rec.decision.epsilon == 0.0
    # Ingestion alone does not update Q.
    before = policy.persist().update_count
    ingested = policy.ingest_feedback_without_update(
        campaign_id="camp-auth", payload={"reply": "thanks", "instruction": "ignore"},
    )
    assert ingested.applied_rl_update is False
    assert policy.persist().update_count == before
    assert len(policy.shadow_log) == 1


def test_q_value_cannot_be_formatted_as_biological_or_institutional_probability():
    text = format_q_as_simulator_utility(0.42)
    assert "simulator_utility_estimate=" in text
    assert "not a probability" in text
    assert render_q_value(0.42, frame="simulator_utility").startswith("simulator_utility")

    for frame in (
        "drug_efficacy", "efficacy_probability", "biological_confidence",
        "chance_institution_helps", "institution_will_help", "clinical_probability",
    ):
        with pytest.raises(QReportingError):
            render_q_value(0.42, frame=frame)


def test_observation_encoder_is_versioned_and_keeps_audit_history():
    world = _world()
    world.reveal_scientific(
        node_id="fn-northbridge-cell", question_id="Q01", event_key="residual_retained",
        question_decision="residual?",
    )
    obs = world.policy_observation()
    state = encode_observation_state(obs, ticks_used=3, cost_used=1.0, requests_used=1)
    assert state.feature_contract_version == FEATURE_CONTRACT_VERSION
    assert state.bin_versions
    assert all(v for _, v in state.bin_versions)
    assert state.event_history
    # No latent scientific labels in compressed features.
    flat = " ".join(f"{k}={v}" for k, v in state.features)
    assert "retained" not in flat
    assert "residual_function" not in flat
    assert "latent" not in flat.casefold()


def test_hyperparameters_are_labelled_simulator_settings():
    hp = SimulatorHyperparameters()
    assert hp.label == SIMULATOR_SETTING_LABEL
    assert hp.alpha == 0.1
    assert hp.gamma == 0.95
    assert hp.epsilon_at(step=0, total_steps=100) == pytest.approx(0.2)
    assert hp.epsilon_at(step=99, total_steps=100) == pytest.approx(0.05)
    with pytest.raises(Exception):
        SimulatorHyperparameters(label="scientific_learning_rate")


def test_explicit_training_event_required_for_update():
    policy = TabularQPolicy(master_seed=MASTER, world_id="train-evt")
    event = make_training_event(
        reward=1.0, state_key="s:abc", action_key="wait|Q00|fn-silent-harbour|wait",
        next_state_key="s:def", terminal=True, master_seed=MASTER, serial=1,
    )
    new_q = policy.apply_training_update(event, eligible_next=())
    assert new_q == pytest.approx(0.1)  # alpha * reward from zero init, terminal
    assert policy.q_get("s:abc", "wait|Q00|fn-silent-harbour|wait") == pytest.approx(0.1)
