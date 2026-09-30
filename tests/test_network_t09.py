"""T09: reward scorer, baselines, world splits (A06, A16, A19, A21)."""

from __future__ import annotations

import pytest

from rarepipe.stages.network.model import CampaignScope, ClaimDirection
from rarepipe.stages.network.sim.baselines import (
    EXPERT_SEQUENCE, HEURISTIC_ACTION_PRIORITY, EligibleNodeHeuristicBaseline,
    FixedExpertSequenceBaseline, PairedBaselineRunner, SharedResourceBudget,
    default_constraints, default_shared_budget,
)
from rarepipe.stages.network.sim.reward import (
    WEIGHT_LABEL, ConstraintViolation, ReportedRate, ResolutionAttempt, ResolutionVerdict,
    RewardScorer, ToyBenchmarkWeights, compute_toy_reward,
    default_mva_declaration, policy_cannot_buy_exclusion, sensitivity_runs, wilson_interval,
)
from rarepipe.stages.network.sim.scenarios import build_s08
from rarepipe.stages.network.sim.splits import (
    KeyedExogenousRNG, ParameterRegion, SeedOnlySplitError,
    catalogue_world_families, check_split_leakage, default_world_split, refuse_seed_only_split,
    required_traits_present,
)
from rarepipe.stages.network.sim.institution import AssumptionLabel, LabeledParam
from rarepipe.stages.network.sim.world import (
    EffectDirection, LatentScientificTruth, PolicyObservation, ResearchWorld, ResidualFunction,
    walk_for_latent_keys,
)


MASTER = 20260930


def _world_with_latent(**updates) -> ResearchWorld:
    data = dict(residual_function=ResidualFunction.RETAINED, abundance_normalized=True)
    data.update(updates)
    return ResearchWorld(
        master_seed=MASTER, campaign_id="t09-world", scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(**data),
    )


def test_a06_two_reports_one_study_scored_once():
    fixture = build_s08(MASTER)
    assert len(fixture.contributions) == 2
    a, b = fixture.contributions
    assert a.evidence_family_id == b.evidence_family_id
    assert not a.independent_of(b)

    world = ResearchWorld(
        master_seed=MASTER, campaign_id=fixture.campaign_id, scope=fixture.scope,
        latent=LatentScientificTruth(
            residual_function=ResidualFunction.UNKNOWN, abundance_normalized=False,
            nad_intracellular=EffectDirection.INCREASED,
            evidence_family_overlap=a.evidence_family_id,
        ),
    )
    scorer = RewardScorer(world, default_mva_declaration())
    first = scorer.score_evidence_family_reports(
        question_id="Q02", evidence_family_id=a.evidence_family_id,
        contribution_ids=(a.id, b.id), claimed_direction=ClaimDirection.SUPPORTS,
    )
    assert first.verdict is ResolutionVerdict.CORRECT_SUPPORT
    assert first.value_units == 1.0
    assert scorer.value_state.total_V == 1.0

    # Second report of the same family adds nothing.
    second = scorer.score_evidence_family_reports(
        question_id="Q02", evidence_family_id=b.evidence_family_id,
        contribution_ids=(b.id,), claimed_direction=ClaimDirection.SUPPORTS,
    )
    assert second.verdict is ResolutionVerdict.DUPLICATE
    assert second.value_units == 0.0
    assert scorer.value_state.total_V == 1.0

    # Attempting to split the duplicate into a new family also adds nothing.
    split = scorer.score_attempt(ResolutionAttempt(
        question_id="Q02", evidence_family_id="fake-split-family",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=(b.id,),
        split_from_family_id=a.evidence_family_id,
    ))
    assert split.verdict is ResolutionVerdict.DUPLICATE
    assert split.value_units == 0.0
    assert scorer.value_state.total_V == 1.0


def test_a16_scorer_sees_hidden_truth_without_policy_leak():
    world = _world_with_latent()
    world.reveal_scientific(
        node_id="fn-northbridge-cell", question_id="Q01", event_key="residual_retained",
        question_decision="residual?",
    )
    scorer = RewardScorer(world, default_mva_declaration())
    assert scorer.latent.residual_function is ResidualFunction.RETAINED
    bundle = scorer.scorer_only_bundle()
    assert "latent_truth" in bundle
    assert bundle["scorer_only"] is True

    obs = world.policy_observation(
        prompts=("select eligible action",),
        feature_tensor=(("budget_remaining", 5.0),),
        ui_payload={"summary": "open questions"},
        reward_explanation_for_selection="eligible actions only",
    )
    assert isinstance(obs, PolicyObservation)
    scorer.assert_no_policy_leak(obs)
    assert walk_for_latent_keys(obs) == []
    assert walk_for_latent_keys(obs.model_dump(mode="json")) == []
    # Scorer bundle itself is intentionally latent — must not be merged into policy objects.
    with pytest.raises((AssertionError, Exception)):
        # Constructing a policy observation that embeds scorer keys must fail.
        PolicyObservation(campaign_id="x", ui_payload={"latent_truth": bundle["latent_truth"]})


def test_a19_baselines_share_observations_budgets_and_splits_leakage():
    world = _world_with_latent()
    obs = world.policy_observation(prompts=("shared",), feature_tensor=(("x", 1.0),))
    budget = default_shared_budget()
    constraints = default_constraints()
    runner = PairedBaselineRunner(budget=budget, constraints=constraints)
    shared = runner.shared_inputs()
    assert shared["budget"] == budget.model_dump(mode="json")
    assert shared["constraints"] == constraints.model_dump(mode="json")

    expert_d, heur_d = runner.decide_both(obs)
    assert expert_d.observation_digest == heur_d.observation_digest == obs.content_digest
    assert expert_d.constraints == heur_d.constraints == constraints
    assert expert_d.budget.model_dump() == heur_d.budget.model_dump() == budget.model_dump()
    assert expert_d.baseline_id == "fixed_expert_sequence_v1"
    assert heur_d.baseline_id == "eligible_node_heuristic_v1"
    # Weakening guards: named constants exist and are non-empty by design.
    assert len(EXPERT_SEQUENCE) >= 5
    assert HEURISTIC_ACTION_PRIORITY[0] == "request_existing_finding"

    split = default_world_split()
    report = check_split_leakage(split)
    assert report.passed
    assert report.shared_family_ids == ()
    assert report.shared_region_fingerprints == ()
    rate = report.leakage_rate()
    assert rate["numerator"] == 0
    assert rate["denominator"] == len(split.held_out_families)
    assert "numerator" in rate and "denominator" in rate

    # Seed-only split is rejected.
    shared_region = ParameterRegion(
        region_id="same-region", family_id="placeholder",
        params=(LabeledParam(name="x", value=1, label=AssumptionLabel.ASSUME),),
    )
    with pytest.raises(SeedOnlySplitError):
        refuse_seed_only_split(
            train_seeds=(1, 2), held_out_seeds=(3, 4), shared_region=shared_region,
        )


def test_a21_every_reported_rate_has_numerator_and_denominator():
    world = _world_with_latent()
    scorer = RewardScorer(world, default_mva_declaration())
    scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-q01",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c1",),
    ))
    rate = scorer.resolution_rate()
    assert isinstance(rate, ReportedRate)
    assert rate.numerator == 1
    assert rate.denominator == len(default_mva_declaration().question_values)
    assert rate.point == pytest.approx(rate.numerator / rate.denominator)
    assert rate.interval_applies
    assert rate.interval_method == "wilson_95"
    assert rate.interval_lo is not None and rate.interval_hi is not None

    traits = required_traits_present()
    assert traits["numerator"] == traits["denominator"] == 5
    assert traits["missing"] == []
    assert "numerator" in traits and "denominator" in traits
    assert traits["interval_applies"] is False
    assert traits["no_interval_reason"]

    leak = check_split_leakage(default_world_split()).leakage_rate()
    assert isinstance(leak["numerator"], int)
    assert isinstance(leak["denominator"], int)

    lo, hi = wilson_interval(1, 3)
    assert 0.0 <= lo <= hi <= 1.0


def test_policy_cannot_game_reward_or_buy_exclusions():
    world = _world_with_latent()
    scorer = RewardScorer(world, default_mva_declaration())
    prior_V = scorer.value_state.total_V

    # Relabelling resolution: learner_claimed_resolved is ignored; latent drives the verdict.
    relabel = scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-relabel",
        claimed_direction=ClaimDirection.AGAINST,  # wrong vs retained latent
        contribution_ids=("c-relabel",),
        learner_claimed_resolved=True,
        learner_claimed_value=99.0,
    ))
    assert relabel.verdict is ResolutionVerdict.INCORRECT
    assert relabel.value_units == 0.0
    assert scorer.value_state.total_V == prior_V

    # Correct support still works under scorer authority.
    ok = scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-ok",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c-ok",),
    ))
    assert ok.verdict is ResolutionVerdict.CORRECT_SUPPORT
    assert scorer.value_state.total_V == 1.0

    # Accurate rejection is equally eligible (defective latent).
    defective = _world_with_latent(residual_function=ResidualFunction.DEFECTIVE)
    scorer_r = RewardScorer(defective, default_mva_declaration())
    rejection = scorer_r.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-rej",
        claimed_direction=ClaimDirection.AGAINST, contribution_ids=("c-rej",),
    ))
    assert rejection.verdict is ResolutionVerdict.CORRECT_REJECTION
    assert rejection.value_units == 1.0

    # Re-accepting own evidence yields nothing.
    own = scorer.score_attempt(ResolutionAttempt(
        question_id="Q02", evidence_family_id="fam-own",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c-own",),
        accepts_own_evidence=True,
    ))
    assert own.verdict is ResolutionVerdict.INCORRECT
    assert own.value_units == 0.0

    # Invalidation removes prior value.
    scorer.invalidate_family("fam-ok")
    assert scorer.value_state.total_V == 0.0

    # Hard exclusion cannot be purchased with cost.
    with pytest.raises(ConstraintViolation, match="constraint"):
        policy_cannot_buy_exclusion(
            scorer, excluded_node_id="excluded-mva-society", offered_cost_units=1_000.0,
        )
    with pytest.raises(ConstraintViolation):
        scorer.reward_step(
            previous_V=0.0, elapsed_ticks=1, cost_units=0.0, contact_units=1,
            unsupported_decisions=0, contacted_nodes=("excluded-family",),
        )

    # Operational mere delivery / generic reply worth nothing.
    assert scorer.score_operational(
        question_id="Q05", changed_feasible_routing=False, is_mere_delivery=True,
    ) == 0.0
    assert scorer.score_operational(
        question_id="Q05", changed_feasible_routing=False, is_generic_reply=True,
    ) == 0.0
    assert scorer.score_operational(
        question_id="Q05", changed_feasible_routing=True,
    ) == 0.5


def test_toy_reward_formula_and_sensitivity_are_labelled_synthetic():
    weights = ToyBenchmarkWeights()
    assert weights.convention_label == WEIGHT_LABEL
    breakdown = compute_toy_reward(
        delta_V=2.0, elapsed_ticks=10, cost_units=4.0, contact_units=2,
        unsupported_decisions=1, weights=weights,
    )
    expected = 2.0 - 0.01 * 10 - 0.05 * 4.0 - 0.05 * 2 - 1.0 * 1
    assert breakdown.reward == pytest.approx(expected)
    assert breakdown.convention_label == WEIGHT_LABEL
    assert breakdown.content_digest and breakdown.content_digest.startswith("sha256:")

    runs = sensitivity_runs(
        delta_V=2.0, elapsed_ticks=10, cost_units=4.0, contact_units=2,
        unsupported_decisions=1,
    )
    assert len(runs) >= 3
    assert all(r.convention_label == WEIGHT_LABEL for r in runs)
    # Different weights produce different rewards (sensitivity is real, not decorative).
    assert len({r.reward for r in runs}) > 1

    with pytest.raises(Exception):
        ToyBenchmarkWeights(convention_label="patient_preference")


def test_keyed_exogenous_randomness_order_invariant():
    rng_a = KeyedExogenousRNG(MASTER, world_id="world-A")
    rng_b = KeyedExogenousRNG(MASTER, world_id="world-A")
    # Different call orders — same keys must yield the same draws.
    order_a = [
        ("fn-cedar-nad", "Q02", "reply"),
        ("fn-northbridge-cell", "Q01", "reply"),
        ("fn-holloway-mitotic", "Q05", "referral"),
    ]
    order_b = list(reversed(order_a))
    draws_a = {
        (n, q, e): rng_a.draw_u01(node_id=n, question_id=q, event=e) for n, q, e in order_a
    }
    draws_b = {
        (n, q, e): rng_b.draw_u01(node_id=n, question_id=q, event=e) for n, q, e in order_b
    }
    assert draws_a == draws_b
    assert rng_a.stream(node_id="fn-cedar-nad", question_id="Q02", event="reply") == (
        rng_b.stream(node_id="fn-cedar-nad", question_id="Q02", event="reply")
    )


def test_split_catalogue_covers_required_traits_and_families_are_disjoint():
    families = catalogue_world_families()
    assert len(families) >= 5
    traits = required_traits_present(families)
    assert traits["numerator"] == 5
    assert traits["missing"] == []
    split = default_world_split()
    assert set(split.train_families).isdisjoint(split.held_out_families)
    assert set(split.train_families).isdisjoint(split.development_families)
    assert split.content_digest and split.content_digest.startswith("sha256:")
    for fam in families:
        assert fam.region.params
        assert all(p.label in AssumptionLabel for p in fam.region.params)


def test_baselines_respect_exclusions_identically():
    world = _world_with_latent()
    obs = world.policy_observation()
    constraints = default_constraints()
    assert "excluded-mva-society" in constraints.excluded_node_ids
    expert = FixedExpertSequenceBaseline()
    heur = EligibleNodeHeuristicBaseline()
    budget = SharedResourceBudget(
        max_ticks=100, max_cost_units=50.0, max_contact_units=20, max_requests=12,
    )
    d1 = expert.select(obs, budget, constraints)
    d2 = heur.select(obs, budget, constraints)
    if d1.action is not None:
        assert d1.action.node_id not in constraints.excluded_node_ids
    if d2.action is not None:
        assert d2.action.node_id not in constraints.excluded_node_ids


def test_a06_relabelling_one_study_under_a_new_family_earns_nothing():
    """A06: the duplicate check must not depend on the learner admitting the split.

    Two reports of one original study share an evidence family, so the same-family check catches
    them. A learner that simply files the second report under a fresh family id was not caught:
    the declared question was credited twice and V doubled. A declared question pays once.
    """
    world = _world_with_latent()
    scorer = RewardScorer(world, default_mva_declaration())

    first = scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-original",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c1",)))
    assert first.verdict is ResolutionVerdict.CORRECT_SUPPORT
    credited = scorer.value_state.total_V
    assert credited > 0.0

    relabelled = scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-relabelled",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c2",)))
    assert relabelled.verdict is ResolutionVerdict.DUPLICATE
    assert relabelled.value_units == 0.0
    assert scorer.value_state.total_V == credited
    # The duplicate carries both sides' contributions, so the corroboration is still traceable.
    assert "c1" in relabelled.contribution_ids and "c2" in relabelled.contribution_ids


def test_a06_invalidating_the_credited_family_clears_the_question_value():
    """A correction must remove the value, not leave a relabelled copy holding it."""
    world = _world_with_latent()
    scorer = RewardScorer(world, default_mva_declaration())
    scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-original",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c1",)))
    scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-relabelled",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c2",)))

    scorer.invalidate_family("fam-original")
    assert scorer.value_state.total_V == 0.0
    assert scorer.resolution_rate().numerator == 0

    # And the question is free to be resolved again by genuinely new evidence.
    again = scorer.score_attempt(ResolutionAttempt(
        question_id="Q01", evidence_family_id="fam-independent",
        claimed_direction=ClaimDirection.SUPPORTS, contribution_ids=("c3",)))
    assert again.verdict is ResolutionVerdict.CORRECT_SUPPORT
    assert scorer.value_state.total_V > 0.0
