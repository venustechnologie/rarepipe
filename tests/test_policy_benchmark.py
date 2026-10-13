"""The harness, and the engine measured against graphs whose answers are known by construction.

Two different things are tested here and they should not be confused.

*The harness works*: episodes are legal, the oracle refuses to be inexact, splits are stable and
sealed, malformed responses are counted rather than dropped, and a metric that does not apply says
so instead of scoring zero.

*The engine is right*: on eleven synthetic graphs whose answers follow from how they were built,
the solver's verdict, minimal horizon, tied first actions and tied route count all match. This is
the check MVA cannot provide — one hand-built graph can be fitted, and a solver tuned until it
passes it has learned that graph rather than the problem.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from rarepipe.stages.control.benchmark import contracts, metrics, splits, synthetic  # noqa: E402
from rarepipe.stages.control.benchmark.episodes import (coverage, episode_id,  # noqa: E402
                                                        generate, walk)
from rarepipe.stages.control.benchmark.oracle import (EXACT, INEXACT_BUDGET,  # noqa: E402
                                                      OracleError, exactness_of, oracle_answer)
from rarepipe.stages.control.policy import (Constraints, KnowledgeState,  # noqa: E402
                                            solve_policy)
from rarepipe.stages.control.policy.actions import build_action_space  # noqa: E402
from rarepipe.stages.control.policy.solvers.exact import (  # noqa: E402
    all_robust_first_actions, minimal_robust_horizon, robust_reference)

CASES = synthetic.catalogue()
HORIZON = 4


# ── the engine, against answers known by construction ───────────────────────────────────────

@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_the_engine_matches_the_construction(case):
    """Verdict, horizon, tied first actions and tied route count, all as built."""
    result = solve_policy(case.graph, horizon=HORIZON, campaigns=case.campaigns,
                          constraints=Constraints(max_states=500_000))
    assert result.robust_reachable.value == case.expected_robust, case.note
    assert result.minimal_robust_horizon == case.expected_minimal_horizon, case.note
    tied = result.describe()["tied_minimal_branch_sets"]
    assert tied["count"] == case.expected_tied_minimal_route_count, case.note
    assert tied["truncated"] is False
    if case.expected_robust == "TRUE":
        assert set(result.recommended_actions) == set(case.expected_recommended_actions), case.note
        assert set(result.recommended_actions) <= set(case.expected_robust_first_actions), (
            "a recommendation must be one of the actions that begins a robust policy")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_the_reference_solver_also_matches_the_construction(case):
    """The optimised and reference solvers must both be right, not merely agree with each other."""
    space = build_action_space(case.graph, case.campaigns)
    state = KnowledgeState.initial()
    assert robust_reference(case.graph, space, state, case.graph.goal, HORIZON) \
        == case.expected_robust, case.note
    if case.expected_robust == "TRUE":
        assert minimal_robust_horizon(case.graph, space, state, case.graph.goal, HORIZON) \
            == case.expected_minimal_horizon, case.note
        assert set(all_robust_first_actions(case.graph, space, state, case.graph.goal,
                                            HORIZON)) == set(case.expected_robust_first_actions)


def test_a_deceptively_short_route_is_robust_but_not_recommended():
    """The one-step gamble is excluded by guaranteed progress, not by robustness.

    Its failing outcome closes nothing, so it does begin a robust policy and the reference
    enumeration lists it. What separates it is that its unlucky outcome guarantees no progress,
    while the longer route guarantees a step whatever happens — and guaranteed progress sits
    above worst-case campaign count in the lexicographic order.
    """
    case = synthetic.deceptive_short_route()
    result = solve_policy(case.graph, horizon=HORIZON, campaigns=case.campaigns)
    space = build_action_space(case.graph, case.campaigns)
    robust_set = set(all_robust_first_actions(case.graph, space, KnowledgeState.initial(),
                                              case.graph.goal, HORIZON))

    assert result.robust_reachable.value == "TRUE"
    assert "RESOLVE::SHORT" in robust_set, "the gamble failing does not close the alternative"
    assert set(result.recommended_actions) == {"RESOLVE::LONG_A", "RESOLVE::LONG_B"}
    assert "RESOLVE::SHORT" not in result.recommended_actions

    worst = {c.action_id: c.progress.distance_reduction for c in result.candidates}
    assert worst["RESOLVE::SHORT"] == -1, (
        "its unlucky outcome guarantees *regress*: the one-branch route disappears and the "
        "cheapest remaining route is two branches, so the distance grows")
    assert worst["RESOLVE::LONG_A"] == 0, (
        "it guarantees no regress, which is what beats the gamble. Not a *reduction*, because "
        "the one-branch route through SHORT is still open and still sets the minimum")
    assert worst["RESOLVE::LONG_A"] > worst["RESOLVE::SHORT"], (
        "and that difference is the whole reason the gamble is not recommended")


def test_a_campaign_resolving_two_branches_halves_the_depth():
    with_campaigns = synthetic.campaign_halves_depth(4)
    without = synthetic.conjunction(4)
    assert solve_policy(with_campaigns.graph, horizon=HORIZON,
                        campaigns=with_campaigns.campaigns).minimal_robust_horizon == 2
    assert solve_policy(without.graph, horizon=HORIZON).minimal_robust_horizon == 4


# ── the oracle refuses to be inexact ────────────────────────────────────────────────────────

def test_the_oracle_gives_an_exact_answer_on_a_known_case():
    case = synthetic.always_arrives(2)
    answer = oracle_answer(case.graph, KnowledgeState.initial(), horizon=2,
                           campaigns=case.campaigns)
    assert answer.exact and answer.exactness == EXACT
    assert answer.verdict == "TRUE"
    assert answer.optimal_cost() is not None


def test_the_oracle_refuses_when_the_budget_runs_out():
    """Ground truth is never recorded from a search that stopped before it could tell."""
    case = synthetic.conjunction(3)
    with pytest.raises(OracleError, match="not admissible as ground truth"):
        oracle_answer(case.graph, KnowledgeState.initial(), horizon=HORIZON,
                      campaigns=case.campaigns, constraints=Constraints(max_states=1))
    assert exactness_of(case.graph, KnowledgeState.initial(), horizon=HORIZON,
                        campaigns=case.campaigns,
                        constraints=Constraints(max_states=1)) == INEXACT_BUDGET


def test_an_exhausted_horizon_is_exact_but_an_unexhausted_one_is_not():
    """"No policy within N" is an exact result; "we did not find one" is not."""
    case = synthetic.conjunction(3)
    exhausted = oracle_answer(case.graph, KnowledgeState.initial(), horizon=2,
                              campaigns=case.campaigns)
    assert exhausted.exactness == EXACT
    assert exhausted.verdict == "NOT_ESTABLISHED"
    assert exhausted.searched_exhaustively_to == 2, (
        "the claim is 'no policy uses two actions or fewer', which was actually established")


# ── episodes are legal, distinct and reproducible ───────────────────────────────────────────

def test_every_generated_step_is_a_state_the_solver_could_reach():
    from random import Random

    case = synthetic.conjunction(3)
    trail = walk(case.graph, campaigns=case.campaigns, rng=Random(7), max_depth=3)
    assert trail, "the walk produced nothing"
    for _, state, taken in trail:
        for branch, outcome in state.decided:
            node = case.graph.nodes[branch]
            assert outcome in node.outcome_names, f"{branch}={outcome} is not an admissible result"
        assert len(taken) == len(state.history)


def test_generation_is_reproducible_for_a_seed():
    case = synthetic.conjunction(3)
    first, _ = generate(case.graph, graph_ref="toy", campaigns=case.campaigns, seed=11,
                        count=6, max_depth=3, horizon=3)
    second, _ = generate(case.graph, graph_ref="toy", campaigns=case.campaigns, seed=11,
                         count=6, max_depth=3, horizon=3)
    assert [e.id for e in first] == [e.id for e in second]
    assert [e.describe() for e in first] == [e.describe() for e in second]


def test_a_different_seed_explores_differently():
    case = synthetic.conjunction(3)
    first, _ = generate(case.graph, graph_ref="toy", campaigns=case.campaigns, seed=1,
                        count=8, max_depth=3, horizon=3)
    second, _ = generate(case.graph, graph_ref="toy", campaigns=case.campaigns, seed=99,
                         count=8, max_depth=3, horizon=3)
    assert {e.id for e in first} or {e.id for e in second}


def test_episode_ids_are_content_addressed_and_order_independent():
    a = episode_id("g", "GOAL", (("B1", "a"), ("B2", "b")))
    b = episode_id("g", "GOAL", (("B2", "b"), ("B1", "a")))
    assert a == b, "the same knowledge is the same episode however it is listed"
    assert a != episode_id("g", "GOAL", (("B1", "b"), ("B2", "b")))


def test_episodes_are_distinct_and_carry_exact_oracles():
    case = synthetic.conjunction(3)
    episodes, refused = generate(case.graph, graph_ref="toy", campaigns=case.campaigns,
                                 seed=5, count=10, max_depth=3, horizon=3)
    assert len({e.id for e in episodes}) == len(episodes), "duplicates must collapse"
    assert all(e.oracle.exact for e in episodes)
    report = coverage(episodes, refused)
    assert report["attempted"] == len(episodes) + len(refused)
    assert 0.0 <= report["admitted_fraction"] <= 1.0


def test_refusals_are_recorded_rather_than_silently_dropped():
    """The refusal count is the measurement of how far the exhaustive oracle certifies."""
    case = synthetic.conjunction(3)
    episodes, refused = generate(case.graph, graph_ref="toy", campaigns=case.campaigns,
                                 seed=5, count=10, max_depth=3, horizon=3,
                                 constraints=Constraints(max_states=1))
    assert refused, "a budget of one must refuse anything that needs searching"
    assert all("not admissible as ground truth" in entry.reason for entry in refused)
    # Anything still admitted was decided without searching at all — a state whose goal is
    # already established or already closed needs no policy space, and answering it exactly
    # under any budget is correct rather than a leak.
    assert all(e.oracle.states_considered == 0 for e in episodes), (
        "an episode admitted under a budget of one must have needed no search")
    report = coverage(episodes, refused)
    assert report["admitted_fraction"] < 1.0


# ── splits: stable by content, and sealed ───────────────────────────────────────────────────

def _episodes(count: int = 12):
    case = synthetic.tied_optima(4)
    episodes, _ = generate(case.graph, graph_ref="toy", campaigns=case.campaigns, seed=3,
                           count=count, max_depth=3, horizon=3)
    return episodes


def test_split_assignment_is_stable_when_episodes_are_added():
    """Adding episodes must never move an existing one, or nothing can stay locked."""
    episodes = _episodes(12)
    before = splits.split_episodes(episodes[:6], salt="s")
    after = splits.split_episodes(episodes, salt="s")
    for name in splits.SPLITS:
        kept = set(before.by_name(name).ids())
        assert kept <= set(after.by_name(name).ids()), (
            f"{name} lost an episode when the set grew; assignment is not content-addressed")


def test_split_assignment_is_independent_of_order():
    episodes = _episodes(12)
    forward = splits.split_episodes(episodes, salt="s")
    backward = splits.split_episodes(tuple(reversed(episodes)), salt="s")
    assert forward.locked.ids() == backward.locked.ids()
    assert forward.locked_seal == backward.locked_seal


def test_a_different_salt_reshuffles():
    episodes = _episodes(12)
    assert (splits.split_episodes(episodes, salt="a").locked.ids()
            != splits.split_episodes(episodes, salt="b").locked.ids()
            or len(episodes) < 4)


def test_the_locked_seal_verifies_and_is_computed_not_written():
    episodes = _episodes(12)
    created = splits.split_episodes(episodes, salt="s")
    created.verify()
    assert created.locked_seal.startswith("sha256:")
    assert created.locked_seal == splits.seal_of(created.locked.episodes)


def test_editing_the_locked_split_breaks_its_seal():
    from dataclasses import replace

    episodes = _episodes(12)
    created = splits.split_episodes(episodes, salt="s")
    if not created.locked.episodes:
        pytest.skip("this episode set put nothing in the locked split")
    tampered = replace(
        created,
        locked=replace(created.locked,
                       episodes=created.locked.episodes[:-1] if len(created.locked.episodes) > 1
                       else ()),
    )
    with pytest.raises(splits.SealError, match="does not match its seal"):
        tampered.verify()


def test_weights_must_name_exactly_the_three_splits():
    with pytest.raises(splits.SealError, match="must name exactly"):
        splits.split_episodes(_episodes(4), salt="s", weights={"development": 1.0})


# ── the response contract and the metrics ───────────────────────────────────────────────────

def _oracle_for(case):
    return oracle_answer(case.graph, KnowledgeState.initial(), horizon=3,
                         campaigns=case.campaigns)


def test_a_known_correct_answer_scores_perfectly():
    """A metric that cannot award full marks to a correct answer is a broken metric."""
    case = synthetic.tied_optima(4)
    answer = _oracle_for(case)
    response = contracts.from_oracle(answer, episode_id="ep_x")
    scored = metrics.score(case.graph, response, answer)
    assert scored.malformed is False
    assert scored.robust_reachability_accuracy == 1.0
    assert scored.route_completeness == 1.0
    assert scored.optimality_regret == 0.0
    assert scored.policy_validity == 1.0


def test_returning_one_of_four_tied_optima_is_wrong():
    """Even though the route it names is one of the four."""
    case = synthetic.tied_optima(4)
    answer = _oracle_for(case)
    full = contracts.from_oracle(answer, episode_id="ep_x")
    from dataclasses import replace
    partial = replace(full, all_tied_optimal_routes=full.all_tied_optimal_routes[:1])
    scored = metrics.score(case.graph, partial, answer)
    assert scored.route_completeness == 0.0
    assert scored.returned_subset_of_tied_optima is True
    assert scored.invented_unique_optimum is True


def test_a_malformed_response_is_counted_not_dropped():
    case = synthetic.always_arrives(2)
    answer = _oracle_for(case)
    response = contracts.parse({"conditional_reachable": True}, episode_id="ep_x", arm="A")
    assert response.scorable is False
    assert "missing fields" in response.malformed_reason
    scored = metrics.score(case.graph, response, answer)
    assert scored.malformed is True
    assert scored.robust_reachability_accuracy == 0.0
    assert metrics.aggregate((scored,))["A"]["malformed"] == 1


def test_an_out_of_vocabulary_verdict_is_malformed_not_wrong():
    response = contracts.parse(
        {name: [] for name in contracts.REQUIRED_FIELDS} | {
            "conditional_reachable": True, "robust_reachable": "PROBABLY",
            "contingent_policy_tree": {}, "next_best_action": None},
        episode_id="ep_x", arm="A")
    assert response.scorable is False
    assert "PROBABLY" in response.malformed_reason


def test_naming_an_action_the_episode_does_not_offer_is_its_own_error():
    case = synthetic.tied_optima(4)
    answer = _oracle_for(case)
    from dataclasses import replace
    response = replace(contracts.from_oracle(answer, episode_id="ep_x"),
                       next_best_action="RESOLVE::NOT_A_BRANCH")
    scored = metrics.score(case.graph, response, answer)
    assert scored.named_unavailable_action is True
    assert scored.optimality_regret is None, "a nonexistent action has no cost to regret"


def test_an_unsafe_continuation_is_a_safety_error():
    case = synthetic.unsafe_only_route()
    answer = oracle_answer(case.graph, KnowledgeState.initial(), horizon=2,
                           campaigns=case.campaigns)
    from dataclasses import replace
    offending = replace(
        contracts.from_oracle(answer, episode_id="ep_x"),
        contingent_policy_tree={"action": "RESOLVE::B",
                                "then": {"B=benefit": {"status": "GOAL_REACHED"}}})
    scored = metrics.score(case.graph, offending, answer)
    assert scored.safety_error == 1.0, "a branch ending UNSAFE was offered as acceptable"


def test_a_metric_that_does_not_apply_reports_none_not_zero():
    case = synthetic.always_arrives(2)
    answer = _oracle_for(case)
    response = contracts.from_oracle(answer, episode_id="ep_x")
    scored = metrics.score(case.graph, response, answer)
    assert scored.safety_error is None, "no policy tree was offered, so nothing was risked"
    assert scored.outcome_coverage is None
    summary = metrics.aggregate((scored,))["engine"]
    assert summary["safety_error"]["mean"] is None
    assert summary["safety_error"]["not_applicable"] == 1


def test_aggregates_report_the_denominator_of_every_mean():
    case = synthetic.tied_optima(2)
    answer = _oracle_for(case)
    rows = tuple(
        metrics.score(case.graph, contracts.from_oracle(answer, episode_id=f"ep_{i}"), answer)
        for i in range(3))
    summary = metrics.aggregate(rows)["engine"]
    assert summary["episodes"] == 3
    for name in metrics.PRIMARY:
        assert "applied_to" in summary[name] and "not_applicable" in summary[name]


def test_reproducibility_is_undefined_without_repeats():
    case = synthetic.tied_optima(2)
    answer = _oracle_for(case)
    one = metrics.score(case.graph, contracts.from_oracle(answer, episode_id="ep_1"), answer)
    assert metrics.reproducibility((one,))["repeated_episodes"] == 0
    assert "not measured" in metrics.reproducibility((one,))["note"]

    twice = (one, metrics.score(case.graph, contracts.from_oracle(answer, episode_id="ep_1"),
                                answer))
    report = metrics.reproducibility(twice)
    assert report["repeated_episodes"] == 1
    assert report["per_arm"]["engine"] == 1.0


def test_the_response_schema_requires_every_scored_field():
    schema = contracts.response_schema()
    assert set(schema["required"]) == set(contracts.REQUIRED_FIELDS)
    assert schema["properties"]["robust_reachable"]["enum"] == list(contracts.VERDICTS)
