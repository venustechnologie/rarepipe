"""The engine gate: the specification's fourteen required behaviours, on graphs small enough to check.

These run before any comparison against a language model, because a competitive claim built on a
solver whose own arithmetic is unverified would be worthless. Four properties have to hold first:
the optimised solver agrees with the reference solver, no hard safety constraint is ever violated,
identical input gives identical output, and every tied optimal action is returned rather than one
of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import policy_toys as toys  # noqa: E402

from rarepipe.stages.control.policy import (  # noqa: E402
    ActuatorStatus, AVAILABLE, BLOCKED, CLOSED_INEFFECTIVE, CLOSED_NO_ENGAGEMENT, CLOSED_UNSAFE,
    Constraints, FALSE, IMPOSSIBLE, KnowledgeState, NOT_ESTABLISHED, Observation, TRUE,
    build_action_space, conditionally_reachable, seed_actuators, solve_policy, unsafe_routes,
    update,
)
from rarepipe.stages.control.policy.actions import admissible_outcomes  # noqa: E402
from rarepipe.stages.control.policy.graph import GraphError  # noqa: E402
from rarepipe.stages.control.policy.solvers.exact import (  # noqa: E402
    all_robust_first_actions, minimal_robust_horizon, robust_reference,
)

HORIZON = 4


def _space(graph, campaigns=()):
    return build_action_space(graph, campaigns)


def _agree(graph, campaigns=(), horizon=HORIZON, state=None):
    """Solve both ways and assert the verdicts match. Returns the optimised result."""
    state = state or KnowledgeState.initial()
    result = solve_policy(graph, state, horizon=horizon, campaigns=campaigns)
    reference = robust_reference(graph, _space(graph, campaigns), state, graph.goal, horizon)
    assert result.robust_reachable.value == reference, (
        f"optimised says {result.robust_reachable.value}, reference says {reference}")
    return result


# ── 1. a deterministic single route reaches the target ───────────────────────────────────────

def test_deterministic_route_is_robust():
    result = _agree(toys.deterministic_route())
    assert result.robust_reachable.value == TRUE
    assert result.minimal_robust_horizon == 1
    assert result.recommended_actions == ("RESOLVE::B",)


def test_an_already_grounded_goal_is_robust_at_horizon_zero():
    result = solve_policy(toys.grounded_route(), horizon=0)
    assert result.robust_reachable.value == TRUE
    assert result.minimal_robust_horizon == 0


# ── 2. a branch with one safe and one unsafe outcome ─────────────────────────────────────────

def test_an_unsafe_outcome_defeats_robustness():
    result = _agree(toys.safe_and_unsafe_outcome())
    assert result.robust_reachable.value == FALSE
    assert ("SAFE", "harm", "T_UNSAFE") in result.unsafe_routes


# ── 3. two alternative families ──────────────────────────────────────────────────────────────

def test_two_alternative_families_are_both_enumerated_and_neither_is_robust():
    """An alternative family hedges the first one failing; it does not make the goal guaranteed.

    Both families are sufficient on their own, so both are tied minimal routes and both are offered
    as first actions. Neither is robust, because either can fail outright — and reporting that as
    "robust" by pointing at the other family is the specific overstatement this engine replaces.
    """
    graph = toys.two_families()
    result = _agree(graph)
    assert result.conditional_reachable is True
    assert result.robust_reachable.value == FALSE
    assert [sorted(s) for s in result.tied_minimal_branch_sets] == [["F1"], ["F2"]]
    assert result.recommended_actions == ("RESOLVE::F1", "RESOLVE::F2")


def test_losing_one_family_leaves_the_other_live():
    graph = toys.two_families()
    after = solve_policy(
        graph,
        update(graph, KnowledgeState.initial(), _space(graph).by_id("RESOLVE::F1"),
               Observation(action_id="RESOLVE::F1", results=(("F1", "fails"),))),
        horizon=HORIZON)
    assert after.conditional_reachable is True, "F2 still reaches the goal"
    assert after.remaining_frontiers == ("F2",)
    assert after.recommended_actions == ("RESOLVE::F2",)


# ── 4. an AND node requires every member ─────────────────────────────────────────────────────

def test_a_conjunction_requires_both_members():
    graph = toys.conjunction()
    result = _agree(graph)
    assert result.robust_reachable.value == TRUE
    assert result.minimal_robust_horizon == 2, "both conjuncts must be settled"
    # Neither branch alone establishes the goal.
    assert all(len(s) == 2 for s in result.tied_minimal_branch_sets)


# ── 5. one campaign resolves two branches ────────────────────────────────────────────────────

def test_a_campaign_settling_two_branches_halves_the_depth():
    graph, campaigns = toys.campaign_resolves_two()
    with_campaign = _agree(graph, campaigns)
    without = _agree(graph)
    assert with_campaign.minimal_robust_horizon == 1
    assert without.minimal_robust_horizon == 2
    assert with_campaign.recommended_actions == ("JOINT01",)


def test_a_campaign_returns_one_result_per_branch_it_resolves():
    graph, campaigns = toys.campaign_resolves_two()
    space = _space(graph, campaigns)
    outcomes = admissible_outcomes(graph, space.by_id("JOINT01"), KnowledgeState.initial())
    assert len(outcomes) == 4, "the joint space is the product over the branches it settles"
    assert all(len(o.results) == 2 for o in outcomes)


# ── 6. a negative result closes one family and opens another ─────────────────────────────────

def test_a_negative_result_closes_one_family_and_opens_another():
    """Before the result, only REPAIR is actionable. The negative is what makes REPLACE reachable.

    This is the behaviour that a frontier computation ignoring decided outcomes gets wrong: unless
    a branch restricted to one result also closes its other outcomes, a negative never opens the
    family it was supposed to route to, and never closes the one it ruled out.
    """
    graph = toys.negative_opens_alternative()
    before = _agree(graph)
    assert before.conditional_reachable is True
    assert before.remaining_frontiers == ("REPAIR",), "REPLACE is not yet reachable"

    state = update(graph, KnowledgeState.initial(),
                   _space(graph).by_id("RESOLVE::REPAIR"),
                   Observation(action_id="RESOLVE::REPAIR",
                               results=(("REPAIR", "no_stabilisation"),)))
    after = solve_policy(graph, state, horizon=HORIZON)
    assert after.conditional_reachable is True, "the replace family is now the route"
    assert after.remaining_frontiers == ("REPLACE",)
    assert after.robust_reachable.value == FALSE, "REPLACE can still fail outright"

    # The positive result closes nothing and arrives directly.
    reached = update(graph, KnowledgeState.initial(),
                     _space(graph).by_id("RESOLVE::REPAIR"),
                     Observation(action_id="RESOLVE::REPAIR",
                                 results=(("REPAIR", "stabilised"),)))
    assert solve_policy(graph, reached, horizon=HORIZON).robust_reachable.value == TRUE


# ── 7. two tied optimal policies are both returned ───────────────────────────────────────────

def test_tied_optima_are_both_returned():
    graph = toys.tied_optima()
    result = _agree(graph)
    assert result.robust_reachable.value == TRUE
    assert result.recommended_actions == ("RESOLVE::LEFT", "RESOLVE::RIGHT")
    assert len(result.tied_minimal_branch_sets) == 2
    reference = all_robust_first_actions(graph, _space(graph), KnowledgeState.initial(),
                                         graph.goal, HORIZON)
    assert set(result.recommended_actions) == set(reference)


# ── 8/9. conditional true with robust false, and robust true ─────────────────────────────────

def test_conditional_true_and_robust_false_are_different_answers():
    graph = toys.conditional_not_robust()
    assert conditionally_reachable(graph) is True
    result = _agree(graph)
    assert result.conditional_reachable is True
    assert result.robust_reachable.value == FALSE


def test_robust_under_every_outcome():
    result = _agree(toys.robust_under_every_outcome())
    assert result.robust_reachable.value == TRUE
    assert result.minimal_robust_horizon == 2


# ── 10. a safety closure is never overridden by benefit ──────────────────────────────────────

def test_no_benefit_buys_a_route_through_an_unsafe_terminal():
    graph = toys.benefit_behind_unsafe()
    result = solve_policy(graph, horizon=HORIZON)
    assert result.conditional_reachable is False, "the goal is not reachable at all, safely or not"
    assert result.robust_reachable.value == FALSE
    assert result.policy is None
    assert ("B", "great_benefit", "T_UNSAFE") in result.unsafe_routes


def test_a_returned_policy_never_routes_through_an_unsafe_terminal():
    graph, campaigns = toys.three_armed_campaign()
    result = solve_policy(graph, horizon=HORIZON, campaigns=campaigns)
    unsafe = {(b, o) for b, o, _ in unsafe_routes(graph)}

    def walk(node):
        if node is None or node.action is None:
            return
        for outcome, child in node.outcome_children.items():
            for assignment in outcome.split("#")[0].split("+"):
                branch, _, name = assignment.partition("=")
                assert (branch, name) not in unsafe, f"{outcome} routes through an unsafe terminal"
            walk(child)

    walk(result.policy)
    assert all(c.safety_violations == 0 for c in result.candidates)


# ── 11. a governance block is not a biological impossibility ─────────────────────────────────

def test_governance_block_is_not_reported_as_biological_impossibility():
    graph = toys.governance_versus_impossible()
    result = solve_policy(graph, horizon=HORIZON)
    assert graph.terminals_with_role(BLOCKED) == ("T_GOV",)
    assert graph.terminals_with_role(IMPOSSIBLE) == ("T_IMPOSSIBLE",)
    # The governance-gated branch is not an action, and the reason says so rather than calling it
    # a dead end in the biology.
    unavailable = {u.branch: u for u in
                   build_action_space(graph, (), restrict_to=set(graph.branch_ids())).unavailable}
    assert "GOV" in unavailable
    assert unavailable["GOV"].requires == toys.ORGANISM
    assert "not declared available" in unavailable["GOV"].reason
    assert "GOV" not in [a.id.removeprefix("RESOLVE::") for a in _space(graph).actions]


# ── 12. re-entry terminates by canonicalising the state ──────────────────────────────────────

def test_a_reentry_loop_terminates_with_a_definite_verdict():
    """The property under test is termination. A solver that spins here has no answer at all.

    ``retry`` returns to an earlier state, so without canonicalising the knowledge state the search
    would revisit it once per path that reaches it. The verdict itself is ``FALSE``: the loop offers
    nothing new, because the branch has already returned its one result.
    """
    graph = toys.reentry_loop()
    result = _agree(graph)
    assert result.robust_reachable.established, "a loop must not leave the verdict indeterminate"
    assert result.robust_reachable.value == FALSE
    assert result.budget_exhausted is False
    assert result.states_considered < 50, "canonicalisation should collapse the loop"


# ── 13. identical input gives identical output ───────────────────────────────────────────────

def test_the_same_input_produces_the_same_mathematics():
    graph, campaigns = toys.three_armed_campaign()
    first = solve_policy(graph, horizon=HORIZON, campaigns=campaigns, model_id="TOY")
    second = solve_policy(graph, horizon=HORIZON, campaigns=campaigns, model_id="TOY")
    assert first.describe() == second.describe()


def test_determinism_survives_a_reordered_input():
    """Reordering the nodes and campaigns must not change a single field of the answer."""
    graph, campaigns = toys.three_armed_campaign()
    reordered = type(graph).build(
        nodes=list(reversed(list(graph.nodes.values()))),
        edges=tuple(reversed(graph.edges)), root=graph.root, goal=graph.goal,
        available_requirements=graph.available_requirements)
    assert (solve_policy(graph, horizon=HORIZON, campaigns=campaigns).describe()
            == solve_policy(reordered, horizon=HORIZON, campaigns=campaigns).describe())


# ── 14. the optimised solver agrees with the reference solver ────────────────────────────────

def test_optimised_and_reference_solvers_agree_on_every_toy():
    cases = {
        "deterministic_route": (toys.deterministic_route(), ()),
        "safe_and_unsafe": (toys.safe_and_unsafe_outcome(), ()),
        "two_families": (toys.two_families(), ()),
        "conjunction": (toys.conjunction(), ()),
        "negative_opens": (toys.negative_opens_alternative(), ()),
        "tied_optima": (toys.tied_optima(), ()),
        "conditional_not_robust": (toys.conditional_not_robust(), ()),
        "robust_every_outcome": (toys.robust_under_every_outcome(), ()),
        "reentry": (toys.reentry_loop(), ()),
        "invalid_run": (toys.invalid_run_outcome(), ()),
        "component_discovery": (toys.component_discovery_route(), ()),
        "campaign_two": toys.campaign_resolves_two(),
        "three_arms": toys.three_armed_campaign(),
    }
    disagreements = []
    for name, (graph, campaigns) in cases.items():
        state = KnowledgeState.initial()
        optimised = solve_policy(graph, state, horizon=HORIZON, campaigns=campaigns)
        reference = robust_reference(graph, _space(graph, campaigns), state, graph.goal, HORIZON)
        if optimised.robust_reachable.value != reference:
            disagreements.append(f"{name}: optimised={optimised.robust_reachable.value} "
                                 f"reference={reference}")
        if optimised.robust_reachable.value == TRUE:
            expected = minimal_robust_horizon(graph, _space(graph, campaigns), state,
                                              graph.goal, HORIZON)
            if optimised.minimal_robust_horizon != expected:
                disagreements.append(f"{name}: horizon {optimised.minimal_robust_horizon} "
                                     f"!= reference {expected}")
    assert not disagreements, "; ".join(disagreements)


def test_tied_first_actions_match_the_reference_enumeration():
    for graph, campaigns in (toys.tied_optima(), ()), (toys.component_discovery_route(), ()):
        state = KnowledgeState.initial()
        optimised = solve_policy(graph, state, horizon=HORIZON, campaigns=campaigns)
        if optimised.robust_reachable.value != TRUE:
            continue
        reference = all_robust_first_actions(graph, _space(graph, campaigns), state,
                                             graph.goal, HORIZON)
        assert set(optimised.recommended_actions) == set(reference)


# ── the three-valued verdict ─────────────────────────────────────────────────────────────────

def test_running_out_of_horizon_is_not_the_same_as_false():
    """Two steps are needed; one is allowed. The answer is "not established", not "no"."""
    graph = toys.conjunction()
    assert solve_policy(graph, horizon=1).robust_reachable.value == NOT_ESTABLISHED
    assert solve_policy(graph, horizon=1).robust_reachable.reason == "HORIZON"
    assert solve_policy(graph, horizon=2).robust_reachable.value == TRUE


def test_running_out_of_budget_is_not_the_same_as_false():
    graph = toys.conjunction()
    starved = solve_policy(graph, horizon=4, constraints=Constraints(max_states=1))
    assert starved.robust_reachable.value == NOT_ESTABLISHED
    assert starved.robust_reachable.reason == "BUDGET"
    assert starved.budget_exhausted is True


def test_a_closed_route_is_false_not_merely_unestablished():
    result = solve_policy(toys.benefit_behind_unsafe(), horizon=6)
    assert result.robust_reachable.value == FALSE


# ── invalid runs, and component discovery ────────────────────────────────────────────────────

def test_an_invalid_run_is_excluded_from_the_quantifier_but_reported():
    graph = toys.invalid_run_outcome()
    result = solve_policy(graph, horizon=HORIZON)
    assert result.robust_reachable.value == TRUE, "an assay voiding its gates is not a result"
    assert ("B", "insufficient") in result.excluded_non_informative


def test_including_invalid_runs_gives_the_other_answer():
    graph = toys.invalid_run_outcome()
    strict = solve_policy(graph, horizon=HORIZON,
                          constraints=Constraints(include_non_informative=True))
    assert strict.robust_reachable.value == FALSE, (
        "with invalid runs quantified over, nothing is robust — which is why the default excludes "
        "them and says so")


def test_component_discovery_is_not_priced_as_a_measurement():
    graph = toys.component_discovery_route()
    result = solve_policy(graph, horizon=HORIZON)
    by_id = {c.action_id: c for c in result.candidates}
    assert by_id["RESOLVE::DISCOVER"].needs_component_discovery is True
    assert by_id["RESOLVE::MEASURE"].needs_component_discovery is False


def test_a_branch_whose_every_outcome_is_non_informative_is_rejected():
    import pytest
    with pytest.raises(GraphError, match="never resolve"):
        toys.build(
            [toys.Node(id="ROOT", kind=toys.STATE),
             toys.branch("B", {"a": "S", "b": "S"}, non_informative=("a", "b")),
             toys.Node(id="S", kind=toys.STATE),
             toys.Node(id="GOAL", kind=toys.ALL_OF, members=("S",))],
            [toys.Edge("ROOT", "B")],
        )


# ── arms: an unsafe actuator is not an unsafe control variable ────────────────────────────────

def test_one_unsafe_actuator_does_not_close_the_control_variable():
    graph, campaigns = toys.three_armed_campaign()
    registry = seed_actuators({"CV_FLUX": ["paclitaxel_low_dose", "HAUS8_depletion",
                                           "NuMA_depletion"]})
    state = KnowledgeState.initial(registry)
    observation = Observation(
        action_id="FLUX01",
        results=(("EFFECT", "lowers"), ("POP", "harm")),
        arm_updates=(("paclitaxel_low_dose", CLOSED_UNSAFE),),
        closure_scopes=(("paclitaxel_low_dose", "ACTUATOR"),),
    )
    after = update(graph, state, campaigns[0], observation)
    assert after.actuator("paclitaxel_low_dose").status == CLOSED_UNSAFE
    assert after.actuator("HAUS8_depletion").status == AVAILABLE
    assert after.actuator("NuMA_depletion").status == AVAILABLE
    assert after.control_variable_closed("CV_FLUX") is False
    assert after.open_actuators("CV_FLUX") == ("HAUS8_depletion", "NuMA_depletion")


def test_a_control_variable_closes_only_when_every_arm_fails_conclusively():
    graph, campaigns = toys.three_armed_campaign()
    registry = seed_actuators({"CV_FLUX": ["paclitaxel_low_dose", "HAUS8_depletion",
                                           "NuMA_depletion"]})
    state = KnowledgeState.initial(registry)
    state = update(graph, state, campaigns[0], Observation(
        action_id="FLUX01", results=(("EFFECT", "no_reduction"), ("POP", "preserved")),
        arm_updates=(("paclitaxel_low_dose", CLOSED_INEFFECTIVE),
                     ("HAUS8_depletion", CLOSED_INEFFECTIVE),
                     ("NuMA_depletion", CLOSED_INEFFECTIVE))))
    assert state.control_variable_closed("CV_FLUX") is True
    assert state.closed_control_variables() == ("CV_FLUX",)


def test_an_unengaged_arm_never_counts_toward_closing_a_control_variable():
    """A null without validated engagement is not a null: that arm was never really run."""
    graph, campaigns = toys.three_armed_campaign()
    registry = seed_actuators({"CV_FLUX": ["paclitaxel_low_dose", "HAUS8_depletion",
                                           "NuMA_depletion"]})
    state = update(graph, KnowledgeState.initial(registry), campaigns[0], Observation(
        action_id="FLUX01", results=(("EFFECT", "no_reduction"), ("POP", "preserved")),
        arm_updates=(("paclitaxel_low_dose", CLOSED_INEFFECTIVE),
                     ("HAUS8_depletion", CLOSED_INEFFECTIVE),
                     ("NuMA_depletion", CLOSED_NO_ENGAGEMENT))))
    assert state.control_variable_closed("CV_FLUX") is False


def test_arm_state_is_canonical_not_merely_logged():
    """Two states differing only in actuator standing must not share a memo entry."""
    open_state = KnowledgeState.initial(seed_actuators({"CV": ["a", "b"]}))
    closed_state = KnowledgeState(
        actuators=(ActuatorStatus("CV", "a", CLOSED_UNSAFE), ActuatorStatus("CV", "b", AVAILABLE)))
    assert open_state.canonical() != closed_state.canonical()


def test_planning_time_outcomes_close_no_actuator():
    """The planner cannot know which arm failed, so it must not guess one."""
    graph, campaigns = toys.three_armed_campaign()
    registry = seed_actuators({"CV_FLUX": ["paclitaxel_low_dose", "HAUS8_depletion",
                                           "NuMA_depletion"]})
    state = KnowledgeState.initial(registry)
    for observation in admissible_outcomes(graph, campaigns[0], state):
        after = update(graph, state, campaigns[0], observation)
        assert after.control_variable_closed("CV_FLUX") is False
        assert all(a.status == AVAILABLE for a in after.actuators)


# ── a branch returns one result ───────────────────────────────────────────────────────────────

def test_a_branch_cannot_be_given_two_different_results():
    import pytest
    graph = toys.conditional_not_robust()
    action = _space(graph).by_id("RESOLVE::B")
    state = update(graph, KnowledgeState.initial(), action,
                   Observation(action_id="RESOLVE::B", results=(("B", "ok"),)))
    with pytest.raises(Exception, match="refusing to overwrite"):
        update(graph, state, action, Observation(action_id="RESOLVE::B", results=(("B", "bad"),)))
