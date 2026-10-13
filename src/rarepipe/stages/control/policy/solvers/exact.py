"""The reference solver: the definition, written out, with nothing clever in it.

This is ground truth. It has no memo table, no transposition cache, no early exit, no restriction
of the action space and no budget. It is exponential and it is meant to be, because its only job is
to be obviously the thing the specification says:

    ROBUST(K, h) = ∃a ∀o ∈ Outcomes(a, K) : ROBUST(UPDATE(K, a, o), h−1)

with terminal cases for success, a closed route and an exhausted horizon. Every optimisation in
``robust_policy`` is a claim that it computes this faster, and that claim is tested by running both
on small graphs and refusing to let them disagree.

Do not "improve" this file. If it gets faster by getting cleverer, it stops being a check on the
clever one.
"""
from __future__ import annotations

from rarepipe.stages.control.policy.actions import ActionSpace, admissible, admissible_outcomes
from rarepipe.stages.control.policy.graph import PolicyGraph
from rarepipe.stages.control.policy.reachability import frontier
from rarepipe.stages.control.policy.state import KnowledgeState
from rarepipe.stages.control.policy.update import update

TRUE, FALSE, NOT_ESTABLISHED = "TRUE", "FALSE", "NOT_ESTABLISHED"


def robust_reference(graph: PolicyGraph, space: ActionSpace, state: KnowledgeState,
                     target: str, horizon: int, *,
                     include_non_informative: bool = False) -> str:
    """``TRUE``, ``FALSE`` or ``NOT_ESTABLISHED``, computed straight from the definition."""
    f = frontier(graph, known=state.established, decided=state.resolved)
    if frozenset() in f.for_node(target):
        return TRUE
    if not f.establishable(target):
        return FALSE
    if horizon <= 0:
        return NOT_ESTABLISHED

    saw_indeterminate = False
    for action in admissible(space, state):
        outcomes = admissible_outcomes(graph, action, state,
                                       include_non_informative=include_non_informative)
        if not outcomes:
            continue
        verdicts = [
            robust_reference(graph, space, update(graph, state, action, observation),
                             target, horizon - 1,
                             include_non_informative=include_non_informative)
            for observation in outcomes
        ]
        if all(v == TRUE for v in verdicts):
            return TRUE
        if any(v == NOT_ESTABLISHED for v in verdicts):
            saw_indeterminate = True
    return NOT_ESTABLISHED if saw_indeterminate else FALSE


def minimal_robust_horizon(graph: PolicyGraph, space: ActionSpace, state: KnowledgeState,
                           target: str, max_horizon: int, *,
                           include_non_informative: bool = False) -> int | None:
    """The smallest horizon at which a robust policy exists, or ``None`` within the bound."""
    for depth in range(max_horizon + 1):
        if robust_reference(graph, space, state, target, depth,
                            include_non_informative=include_non_informative) == TRUE:
            return depth
    return None


def all_robust_first_actions(graph: PolicyGraph, space: ActionSpace, state: KnowledgeState,
                            target: str, horizon: int, *,
                            include_non_informative: bool = False) -> tuple[str, ...]:
    """Every action that begins *some* robust policy — all tied optima, by brute force.

    The optimised search returns tied first actions too, by scoring every root action instead of
    stopping at the first that works. This is the check on that.
    """
    out: list[str] = []
    for action in admissible(space, state):
        outcomes = admissible_outcomes(graph, action, state,
                                       include_non_informative=include_non_informative)
        if not outcomes:
            continue
        if all(
            robust_reference(graph, space, update(graph, state, action, observation),
                             target, horizon - 1,
                             include_non_informative=include_non_informative) == TRUE
            for observation in outcomes
        ):
            out.append(action.id)
    return tuple(sorted(out))
