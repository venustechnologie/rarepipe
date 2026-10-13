"""The cheap relaxation must agree with the set-based frontier, always.

``robust_policy`` asks ``can_establish`` about every state it visits, hundreds of times per state,
because enumerating minimal branch sets to answer a yes/no question costs orders of magnitude more.
That substitution is only legitimate if the two never disagree, so this file is the licence for it:
the same question, asked both ways, over many states of several graphs.

Also pinned here: a cap on minimal sets cannot change the *smallest* set's size. The ranking relies
on that — it reads distance off a capped frontier while taking outstanding-branch counts from the
graph — and if ``_prune`` ever stopped keeping sets smallest-first, the two would silently diverge.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import policy_toys as toys  # noqa: E402

from rarepipe.stages.control.policy import KnowledgeState  # noqa: E402
from rarepipe.stages.control.policy.reachability import (can_establish,  # noqa: E402
                                                          dominators, frontier,
                                                          minimum_branches)

GRAPHS = {
    "deterministic_route": toys.deterministic_route(),
    "grounded_route": toys.grounded_route(),
    "safe_and_unsafe": toys.safe_and_unsafe_outcome(),
    "two_families": toys.two_families(),
    "conjunction": toys.conjunction(),
    "negative_opens": toys.negative_opens_alternative(),
    "tied_optima": toys.tied_optima(),
    "conditional_not_robust": toys.conditional_not_robust(),
    "robust_every_outcome": toys.robust_under_every_outcome(),
    "benefit_behind_unsafe": toys.benefit_behind_unsafe(),
    "governance_vs_impossible": toys.governance_versus_impossible(),
    "reentry": toys.reentry_loop(),
    "invalid_run": toys.invalid_run_outcome(),
    "component_discovery": toys.component_discovery_route(),
    "three_arms": toys.three_armed_campaign()[0],
}


def _both_ways(graph, decided):
    sets = frontier(graph, decided=decided, destination=graph.goal)
    cheap = can_establish(graph, decided=decided, destination=graph.goal)
    exact = (sets.establishable(graph.goal), frozenset() in sets.for_node(graph.goal))
    return cheap, exact


def test_the_two_reachability_computations_agree_on_the_empty_state():
    for name, graph in GRAPHS.items():
        cheap, exact = _both_ways(graph, {})
        assert cheap == exact, f"{name}: cheap={cheap} sets={exact}"


def test_the_two_agree_on_every_single_decided_outcome():
    for name, graph in GRAPHS.items():
        for node in graph.branches():
            for outcome in node.outcome_names:
                decided = {node.id: outcome}
                cheap, exact = _both_ways(graph, decided)
                assert cheap == exact, f"{name} {decided}: cheap={cheap} sets={exact}"


def test_the_two_agree_on_random_combinations_of_results():
    """Random because the interesting disagreements are in combinations nobody thought to write."""
    rng = random.Random(20261013)          # fixed: a flaky agreement test proves nothing
    for name, graph in GRAPHS.items():
        branches = list(graph.branches())
        if not branches:
            continue
        for _ in range(120):
            chosen = rng.sample(branches, rng.randint(1, len(branches)))
            decided = {node.id: rng.choice(list(node.outcome_names)) for node in chosen}
            cheap, exact = _both_ways(graph, decided)
            assert cheap == exact, f"{name} {decided}: cheap={cheap} sets={exact}"


def test_established_implies_establishable():
    for name, graph in GRAPHS.items():
        for node in graph.branches():
            for outcome in node.outcome_names:
                establishable, established = can_establish(
                    graph, decided={node.id: outcome}, destination=graph.goal)
                assert not established or establishable, (
                    f"{name}: {node.id}={outcome} reports established but not establishable")


def test_a_cap_cannot_change_the_smallest_sets_size():
    """The ranking reads distance off a capped frontier; this is why that is sound."""
    for name, graph in GRAPHS.items():
        uncapped = frontier(graph, destination=graph.goal)
        for cap in (1, 2, 4, 8):
            capped = frontier(graph, destination=graph.goal, max_sets=cap)
            assert capped.minimal_size(graph.goal) == uncapped.minimal_size(graph.goal), (
                f"{name}: cap {cap} changed the minimal distance")


def test_a_cap_is_reported_when_it_bites():
    """A truncation nobody is told about is how a tied optimum silently disappears."""
    graph = toys.tied_optima()
    capped = frontier(graph, destination=graph.goal, max_sets=1)
    assert capped.truncated, "truncation must be reported, not silent"
    assert len(frontier(graph, destination=graph.goal).tied_minimal(graph.goal)) == 2


def test_known_states_seed_the_relaxation_in_both_computations():
    graph = toys.negative_opens_alternative()
    for known in (frozenset(), frozenset({"S_REPAIRED"}), frozenset({"S_DONE"})):
        sets = frontier(graph, known=known, destination=graph.goal)
        cheap = can_establish(graph, known=known, destination=graph.goal)
        assert cheap == (sets.establishable(graph.goal),
                         frozenset() in sets.for_node(graph.goal)), known


def test_a_dominator_is_a_branch_whose_removal_closes_the_goal():
    graph = toys.conjunction()
    assert set(dominators(graph)) == {"B1", "B2"}, "both conjuncts are unavoidable"
    assert dominators(toys.tied_optima()) == (), "neither symmetric route is unavoidable"


def test_scoping_to_a_destination_does_not_change_its_answer():
    """The ancestor restriction is an optimisation; it must be exact, not approximate."""
    for name, graph in GRAPHS.items():
        scoped = frontier(graph, destination=graph.goal)
        whole = frontier(graph)
        assert scoped.for_node(graph.goal) == whole.for_node(graph.goal), name
        assert scoped.tied_minimal(graph.goal) == whole.tied_minimal(graph.goal), name


def test_the_branch_floor_never_exceeds_the_true_distance():
    """The search prunes on this bound, so an overestimate would discard a real policy.

    Understating is allowed and expected — ``max`` at a conjunction is weaker than the exact union
    — but overstating by even one would make the pruning unsound.
    """
    rng = random.Random(19930421)
    for name, graph in GRAPHS.items():
        branches = list(graph.branches())
        states = [{}]
        for _ in range(60):
            if not branches:
                break
            chosen = rng.sample(branches, rng.randint(1, len(branches)))
            states.append({n.id: rng.choice(list(n.outcome_names)) for n in chosen})
        for decided in states:
            exact = frontier(graph, decided=decided,
                             destination=graph.goal).minimal_size(graph.goal)
            floor = minimum_branches(graph, decided=decided, destination=graph.goal)
            if exact is None:
                assert floor is None, f"{name} {decided}: closed, but floor says {floor}"
            else:
                assert floor is not None, f"{name} {decided}: reachable, but floor says closed"
                assert floor <= exact, (
                    f"{name} {decided}: floor {floor} exceeds true distance {exact}; "
                    f"pruning on it would discard a reachable policy")


def test_the_floor_agrees_with_closure():
    for name, graph in GRAPHS.items():
        for node in graph.branches():
            for outcome in node.outcome_names:
                decided = {node.id: outcome}
                establishable, _ = can_establish(graph, decided=decided, destination=graph.goal)
                floor = minimum_branches(graph, decided=decided, destination=graph.goal)
                assert establishable == (floor is not None), f"{name} {decided}"


def test_a_state_with_no_results_is_the_initial_state():
    for graph in GRAPHS.values():
        assert KnowledgeState.initial().resolved == {}
        assert can_establish(graph, decided={}, destination=graph.goal) == \
            can_establish(graph, destination=graph.goal)
