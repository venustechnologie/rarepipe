"""The oracle: the exact answer for an episode, or a refusal.

The specification is explicit that mathematical correctness is not to be judged by a language
model. The oracle is therefore the exhaustive solver over the same formal graph, and its one
non-negotiable property is that **an answer is recorded only when it was computed exactly**.

Three ways a solve can come back inexact, and all three disqualify an episode rather than being
rounded off:

* ``NOT_ESTABLISHED/BUDGET`` — the search stopped before it could tell.
* ``NOT_ESTABLISHED/HORIZON`` where the horizon was *not* searched exhaustively — nothing is
  established about the question asked.
* a frontier that reported truncation, which would mean a tied optimum may be missing.

The third matters most for scoring. ``route_completeness`` asks whether a system returned *all*
tied optima; an oracle that itself dropped one would mark a correct answer wrong.

A ``NOT_ESTABLISHED/HORIZON`` verdict *is* admissible when the space up to that horizon was
searched exhaustively, because then the claim "no robust policy uses this many actions or fewer" is
itself an exact result. That is the honest shape of the domain the harness is restricted to.
"""
from __future__ import annotations

from dataclasses import dataclass

from rarepipe.stages.control.policy import (BUDGET, Constraints, FALSE, KnowledgeState,
                                            NOT_ESTABLISHED, PolicyGraph, TRUE, solve_policy)
from rarepipe.stages.control.policy.actions import Action

EXACT = "EXACT"
INEXACT_BUDGET = "INEXACT_BUDGET"
INEXACT_HORIZON = "INEXACT_HORIZON"
INEXACT_TRUNCATED = "INEXACT_TRUNCATED"


class OracleError(ValueError):
    """An oracle answer was requested that cannot be given exactly. Never worked around."""


@dataclass(frozen=True)
class OracleAnswer:
    """An exact answer, with the evidence that it is exact."""
    verdict: str
    verdict_reason: str | None
    exactness: str
    horizon: int
    searched_exhaustively_to: int | None
    conditional_reachable: bool
    minimal_robust_horizon: int | None
    recommended_actions: tuple[str, ...]
    tied_minimal_branch_sets: tuple[tuple[str, ...], ...]
    remaining_frontiers: tuple[str, ...]
    cut_sets: tuple[tuple[tuple[str, str], ...], ...]
    success_sets: tuple[tuple[tuple[str, str], ...], ...]
    unsafe_routes: tuple[tuple[str, str, str], ...]
    worst_case_depth: int | None
    # Per-action worst-case further campaigns, so optimality regret is a real difference rather
    # than a binary "chose a tied-optimal action or not".
    action_costs: tuple[tuple[str, int], ...]
    states_considered: int

    @property
    def exact(self) -> bool:
        return self.exactness == EXACT

    def optimal_cost(self) -> int | None:
        """The worst-case further campaigns of the best available action."""
        return min((cost for _, cost in self.action_costs), default=None)

    def cost_of(self, action: str | None) -> int | None:
        """``None`` when the action is not one this episode offers — a different error."""
        return dict(self.action_costs).get(action) if action is not None else None

    def describe(self) -> dict:
        return {
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "exactness": self.exactness,
            "horizon": self.horizon,
            "searched_exhaustively_to": self.searched_exhaustively_to,
            "conditional_reachable": self.conditional_reachable,
            "minimal_robust_horizon": self.minimal_robust_horizon,
            "recommended_actions": list(self.recommended_actions),
            "tied_minimal_branch_sets": [list(s) for s in self.tied_minimal_branch_sets],
            "remaining_frontiers": list(self.remaining_frontiers),
            "minimal_target_cut_sets": [
                [{"branch": b, "outcome": o} for b, o in combo] for combo in self.cut_sets
            ],
            "minimal_target_success_sets": [
                [{"branch": b, "outcome": o} for b, o in combo] for combo in self.success_sets
            ],
            "unsafe_routes": [
                {"branch": b, "outcome": o, "terminal": t} for b, o, t in self.unsafe_routes
            ],
            "worst_case_depth": self.worst_case_depth,
            "action_costs": {action: cost for action, cost in self.action_costs},
            "states_considered": self.states_considered,
        }


def _exactness(answer: dict) -> str:
    verdict = answer["robust_reachable"]
    value = verdict if isinstance(verdict, str) else verdict["value"]
    reason = None if isinstance(verdict, str) else verdict.get("reason")
    trace = answer["trace"]

    if trace["budget_exhausted"] or reason == BUDGET:
        return INEXACT_BUDGET
    if trace["frontier_truncated_at"]:
        # A truncated frontier may be missing a tied optimum, and route completeness is scored
        # against this list. An oracle that dropped one would mark a correct answer wrong.
        return INEXACT_TRUNCATED
    if value in (TRUE, FALSE):
        return EXACT
    # NOT_ESTABLISHED is exact only as the statement "no policy within N actions", and only when
    # the space up to N was actually exhausted.
    if answer.get("no_robust_policy_within") is not None \
            and answer["no_robust_policy_within"] >= answer["horizon"]:
        return EXACT
    return INEXACT_HORIZON


def oracle_answer(graph: PolicyGraph, state: KnowledgeState, *, target: str | None = None,
                  horizon: int = 3, campaigns: tuple[Action, ...] = (),
                  constraints: Constraints | None = None,
                  require_exact: bool = True) -> OracleAnswer:
    """Solve exhaustively and return the answer only if it was exact.

    ``require_exact=False`` is for diagnosing *why* an episode is inadmissible; the harness never
    stores a non-exact answer as ground truth.
    """
    constraints = constraints or Constraints()
    result = solve_policy(graph, state, target=target, constraints=constraints,
                          horizon=horizon, campaigns=tuple(campaigns))
    answer = result.describe()
    exactness = _exactness(answer)
    if require_exact and exactness != EXACT:
        raise OracleError(
            f"the oracle could not answer exactly ({exactness}); this episode is not admissible as "
            f"ground truth. Lower the horizon, raise the budget, or drop the episode — do not "
            f"record an inexact answer as truth.")

    verdict = answer["robust_reachable"]
    cuts = (answer["failure_certificates"].get("cut_set_analysis") or {}) \
        if answer.get("failure_certificates") else {}

    def combos(key: str) -> tuple[tuple[tuple[str, str], ...], ...]:
        return tuple(
            tuple((entry["branch"], entry["outcome"]) for entry in combo)
            for combo in (cuts.get(key) or [])
        )

    return OracleAnswer(
        verdict=verdict if isinstance(verdict, str) else verdict["value"],
        verdict_reason=None if isinstance(verdict, str) else verdict.get("reason"),
        exactness=exactness,
        horizon=answer["horizon"],
        searched_exhaustively_to=answer.get("no_robust_policy_within"),
        conditional_reachable=answer["conditional_reachable"],
        minimal_robust_horizon=answer["minimal_robust_horizon"],
        recommended_actions=tuple(answer["recommended_actions"]),
        tied_minimal_branch_sets=tuple(
            tuple(s) for s in answer["tied_minimal_branch_sets"]["optimal_sets"]),
        remaining_frontiers=tuple(answer["remaining_frontiers"]),
        cut_sets=combos("minimal_target_cut_sets"),
        success_sets=combos("minimal_target_success_sets"),
        unsafe_routes=tuple(
            (r["branch"], r["outcome"], r["terminal"]) for r in answer["unsafe_routes"]),
        worst_case_depth=answer["worst_case_depth"],
        action_costs=tuple(sorted(
            (c["action"], int(c["worst_case_campaigns"])) for c in answer["candidates"])),
        states_considered=answer["trace"]["states_considered"],
    )


def exactness_of(graph: PolicyGraph, state: KnowledgeState, *, target: str | None = None,
                 horizon: int = 3, campaigns: tuple[Action, ...] = (),
                 constraints: Constraints | None = None) -> str:
    """Why an episode would or would not be admissible, without raising."""
    return oracle_answer(graph, state, target=target, horizon=horizon, campaigns=campaigns,
                         constraints=constraints, require_exact=False).exactness
