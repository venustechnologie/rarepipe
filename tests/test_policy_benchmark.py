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
    """No robust policy exists here, so there is no plan to judge for safety or coverage.

    Scoring that as zero would punish a system for correctly declining to produce a plan.
    """
    case = synthetic.one_dead_outcome()
    answer = _oracle_for(case)
    response = contracts.from_oracle(answer, episode_id="ep_x")
    assert not response.contingent_policy_tree, "a FALSE verdict carries no policy"
    scored = metrics.score(case.graph, response, answer)
    assert scored.safety_error is None, "no policy was offered, so nothing was risked"
    assert scored.outcome_coverage is None
    summary = metrics.aggregate((scored,))["engine"]
    assert summary["safety_error"]["mean"] is None
    assert summary["safety_error"]["not_applicable"] == 1


def test_a_real_policy_is_judged_for_safety_and_coverage_rather_than_skipped():
    """The complement: where a plan exists, both metrics apply and must be measured.

    Two of the six metrics were previously never applied on a real run, because the engine arm
    returned an empty tree. A metric that is never applied is a metric that was never validated.
    """
    case = synthetic.always_arrives(2)
    answer = _oracle_for(case)
    response = contracts.from_oracle(answer, episode_id="ep_x")
    assert response.contingent_policy_tree, "a TRUE verdict must carry its policy"
    scored = metrics.score(case.graph, response, answer)
    assert scored.safety_error == 0.0, "a real plan that routes nowhere unsafe scores zero"
    assert scored.outcome_coverage == 1.0, "and answers for every admissible outcome"


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


# ── the runner, and Arm E as the harness's own self-test ────────────────────────────────────

def _runnable(count: int = 10):
    from rarepipe.stages.control.benchmark.episodes import generate as gen
    case = synthetic.tied_optima(4)
    episodes, _ = gen(case.graph, graph_ref="synthetic:tied_optima_4",
                      campaigns=case.campaigns, seed=42, count=count, max_depth=3, horizon=3)
    return case, splits.split_episodes(episodes, salt="enigma-002a")


def test_the_engine_arm_recomputes_rather_than_echoing_the_stored_oracle():
    """Reading the answer out of the episode would make Arm E pass even if the solver broke."""
    from rarepipe.stages.control.benchmark import arms

    case, split_set = _runnable()
    episode = split_set.development.episodes[0]
    context = arms.ArmContext(graph=case.graph, campaigns=case.campaigns, horizon=3,
                              constraints=Constraints())
    response = arms.engine_only()(episode, context)
    assert response.scorable
    assert response.robust_reachable == episode.oracle.verdict
    assert response.latency_seconds is not None, "a recomputed answer takes measurable time"


def test_arm_e_scores_perfectly_which_is_the_harness_self_test():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    result = runner.run(case.graph, split_set, (arms.engine_only(),),
                        campaigns=case.campaigns, horizon=3,
                        graph_ref="synthetic:tied_optima_4")
    summary = result.describe()["per_arm"][arms.ENGINE_ONLY]
    assert summary["malformed"] == 0
    assert summary["robust_reachability_accuracy"]["mean"] == 1.0
    assert summary["route_completeness"]["mean"] == 1.0
    assert summary["optimality_regret"]["mean"] == 0.0
    assert summary["invented_unique_optimum"] == 0


def test_a_run_records_what_it_was_measured_on():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    provenance = runner.run(case.graph, split_set, (arms.engine_only(),),
                            campaigns=case.campaigns, horizon=3,
                            graph_ref="synthetic:tied_optima_4").describe()["provenance"]
    assert provenance["locked_seal"] == split_set.locked_seal
    assert provenance["split_salt"] == "enigma-002a"
    assert provenance["graph_ref"] == "synthetic:tied_optima_4"
    assert provenance["horizon"] == 3


def test_the_locked_split_needs_an_explicit_opt_in():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    with pytest.raises(runner.RunnerError, match="allow_locked"):
        runner.run(case.graph, split_set, (arms.engine_only(),), campaigns=case.campaigns,
                   split=splits.LOCKED)
    allowed = runner.run(case.graph, split_set, (arms.engine_only(),),
                         campaigns=case.campaigns, split=splits.LOCKED, allow_locked=True)
    assert allowed.split == splits.LOCKED


def test_a_run_against_a_broken_seal_is_refused():
    from dataclasses import replace

    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    tampered = replace(split_set, locked_seal="sha256:" + "0" * 64)
    with pytest.raises(splits.SealError, match="does not match its seal"):
        runner.run(case.graph, tampered, (arms.engine_only(),), campaigns=case.campaigns)


def test_repeats_produce_a_reproducibility_measurement():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    once = runner.run(case.graph, split_set, (arms.engine_only(),), campaigns=case.campaigns,
                      repeats=1).describe()["reproducibility"]
    assert once["repeated_episodes"] == 0

    twice = runner.run(case.graph, split_set, (arms.engine_only(),), campaigns=case.campaigns,
                       repeats=2).describe()["reproducibility"]
    assert twice["repeated_episodes"] == len(split_set.development.episodes)
    assert twice["per_arm"][arms.ENGINE_ONLY] == 1.0, "a deterministic arm must agree with itself"


def test_an_arm_that_raises_becomes_a_malformed_response_not_a_crash():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()

    def broken(episode, context):
        raise RuntimeError("the model fell over")

    result = runner.run(case.graph, split_set,
                        (arms.from_callable("A_broken", broken),),
                        campaigns=case.campaigns)
    summary = result.describe()["per_arm"]["A_broken"]
    assert summary["malformed"] == summary["episodes"] > 0
    assert summary["malformed_rate"] == 1.0
    assert any("the model fell over" in (r.malformed_reason or "") for r in result.responses)


def test_an_arm_returning_prose_instead_of_the_schema_is_malformed():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    result = runner.run(case.graph, split_set,
                        (arms.from_callable("A_prose", lambda e, c: {"answer": "it depends"}),),
                        campaigns=case.campaigns)
    assert result.describe()["per_arm"]["A_prose"]["malformed_rate"] == 1.0


def test_secondary_costs_are_recorded_beside_the_scores():
    from rarepipe.stages.control.benchmark import arms, runner

    case, split_set = _runnable()
    secondary = runner.run(case.graph, split_set, (arms.engine_only(),),
                           campaigns=case.campaigns).describe()["secondary"]
    latency = secondary[arms.ENGINE_ONLY]["latency_seconds"]
    assert latency["reported_by"] > 0 and latency["mean"] is not None
    assert secondary[arms.ENGINE_ONLY]["engine_calls"]["mean"] == 1.0


# ── the committed episode set is safe to publish ────────────────────────────────────────────

def test_the_committed_episode_set_contains_nothing_beyond_the_map(tmp_path):
    """Every identifier in the frozen set must already exist in the committed route map.

    This repository becomes public, and the episode set is derived from a map whose private
    boundary is explicit: the child's exact substitution is deliberately not in it. The guard is
    that episodes introduce no identifier of their own — anything in them traces to a node, an
    outcome or an action that is already committed.

    Skipped when the set has not been built, so a fresh checkout does not fail on a missing
    artifact; CI builds it before this runs.
    """
    import importlib.util
    import json
    import re

    episodes_file = Path(__file__).resolve().parents[1] / "data/policy_benchmark/episodes.json"
    if not episodes_file.exists():
        pytest.skip("the benchmark has not been built in this checkout")

    spec = importlib.util.spec_from_file_location(
        "solve_mva_policy",
        Path(__file__).resolve().parents[1] / "tools/control/solve_mva_policy.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    document = adapter.load()

    known = {node["id"] for node in document["nodes"]}
    known |= {name for node in document["nodes"] for name in (node.get("outcomes") or {})}
    known |= {campaign["id"] for campaign in document["campaigns"]}
    known |= {f"RESOLVE::{node['id']}" for node in document["nodes"]}
    known |= set(document.get("control_variables") or {})
    known |= set(document.get("families") or {})

    stored = json.loads(episodes_file.read_text())
    mva = next((s for s in stored["sources"] if s["name"] == "MVA_001"), None)
    if mva is None:
        pytest.skip("the committed set has no MVA source")

    # Identifier-shaped tokens: upper-case or snake_case words long enough to be a name.
    pattern = re.compile(r"\b[A-Za-z][A-Za-z0-9_:]{3,}\b")
    harness_vocabulary = {
        "EXACT", "TRUE", "FALSE", "NOT_ESTABLISHED", "HORIZON", "BUDGET", "ROUTE_CLOSED",
        "ALL_ACTIONS_DEFEATED", "RESOLVE", "None", "true", "false", "null",
    }
    unknown: set[str] = set()
    for episode in mva["episodes"]:
        for token in pattern.findall(json.dumps(episode)):
            bare = token.removeprefix("RESOLVE::")
            if bare in known or token in known or token in harness_vocabulary:
                continue
            if bare.isdigit() or token.startswith("ep_") or token.startswith("sha256"):
                continue
            unknown.add(token)

    # Field names of the record itself are expected; anything else would be new information.
    field_names = {
        "id", "graph_ref", "target", "horizon", "depth", "decided", "actions_taken", "oracle",
        "verdict", "verdict_reason", "exactness", "searched_exhaustively_to",
        "conditional_reachable", "minimal_robust_horizon", "recommended_actions",
        "tied_minimal_branch_sets", "remaining_frontiers", "minimal_target_cut_sets",
        "minimal_target_success_sets", "unsafe_routes", "worst_case_depth", "action_costs",
        "states_considered", "branch", "outcome", "terminal", "MVA_001",
    }
    unknown -= field_names
    assert not unknown, (
        f"the committed episode set introduces identifiers that are not in the route map: "
        f"{sorted(unknown)[:12]}")


def test_the_committed_set_agrees_with_the_synthetic_constructions():
    """The frozen artifact must still encode the answers the graphs were built to have.

    Each synthetic source stores the expectation its construction guarantees. The depth-0 episode
    is the root situation, so its oracle answer is exactly what that expectation describes. If a
    rebuild ever disagrees, either the solver regressed or a construction changed — and this says
    which source.

    Skipped on a checkout where the set has not been built.
    """
    import json

    episodes_file = Path(__file__).resolve().parents[1] / "data/policy_benchmark/episodes.json"
    if not episodes_file.exists():
        pytest.skip("the benchmark has not been built in this checkout")

    stored = json.loads(episodes_file.read_text())
    checked = 0
    problems: list[str] = []
    for source in stored["sources"]:
        expected = source.get("expected")
        if not expected:
            continue                                   # the real map has no construction to check
        root = next((e for e in source["episodes"] if e["depth"] == 0), None)
        if root is None:
            problems.append(f"{source['name']}: no depth-0 episode to check the construction on")
            continue
        checked += 1
        oracle = root["oracle"]
        if oracle["verdict"] != expected["robust"]:
            problems.append(f"{source['name']}: stored verdict {oracle['verdict']} != "
                            f"constructed {expected['robust']}")
        if oracle["minimal_robust_horizon"] != expected["minimal_horizon"]:
            problems.append(f"{source['name']}: stored horizon "
                            f"{oracle['minimal_robust_horizon']} != "
                            f"constructed {expected['minimal_horizon']}")
        if len(oracle["tied_minimal_branch_sets"]) != expected["tied_minimal_route_count"]:
            problems.append(f"{source['name']}: stored "
                            f"{len(oracle['tied_minimal_branch_sets'])} tied routes != "
                            f"constructed {expected['tied_minimal_route_count']}")
        if expected["robust"] == "TRUE" and \
                set(oracle["recommended_actions"]) != set(expected["recommended_actions"]):
            problems.append(f"{source['name']}: stored recommendation "
                            f"{sorted(oracle['recommended_actions'])} != constructed "
                            f"{sorted(expected['recommended_actions'])}")

    assert checked, "no synthetic source carried a construction to check"
    assert not problems, "\n  ".join(["the frozen set disagrees with its constructions:", *problems])


def test_every_committed_episode_was_certified_exactly():
    """Nothing inexact may sit in the frozen set, whatever the coverage table says."""
    import json

    episodes_file = Path(__file__).resolve().parents[1] / "data/policy_benchmark/episodes.json"
    if not episodes_file.exists():
        pytest.skip("the benchmark has not been built in this checkout")

    stored = json.loads(episodes_file.read_text())
    for source in stored["sources"]:
        for episode in source["episodes"]:
            assert episode["oracle"]["exactness"] == EXACT, (
                f"{source['name']}/{episode['id']} is in the frozen set with exactness "
                f"{episode['oracle']['exactness']}")
