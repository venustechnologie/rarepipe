"""Robust contingent planning: is there a policy that wins whatever the admissible results are?

The computation the surrounding repository reports as ``NOT_ESTABLISHED``. Two claims are carefully
kept apart:

``conditional_reachable``
    There exists *some* assignment of outcomes under which the goal is established. A statement
    about the graph containing a route.

``robust_reachable``
    There exists a policy π such that for **every** admissible combination of outcomes, following
    π still reaches the goal. A statement about a plan surviving the world's answers.

    ∃a ∀o ∈ Outcomes(a, K) : ROBUST(UPDATE(K, a, o), h−1)

The second is three-valued, and that is not hedging. "No robust policy within horizon 6" and "no
robust policy exists" are different facts, and so is "the search ran out of budget before it could
tell". Collapsing any of those into ``false`` would repeat precisely the overstatement that got
single-outcome resilience renamed in this repository. So the verdict is ``TRUE``, ``FALSE`` or
``NOT_ESTABLISHED`` carrying a reason of ``HORIZON`` or ``BUDGET``, and ``FALSE`` is returned only
when every action is defeated by an outcome that *definitively* defeats it.

Tractability. The full graph has 56 branches, most with three to seven outcomes, so enumeration is
hopeless and the search leans on four things: the action space is restricted to branches the goal
can actually depend on; the ∀ loop exits at the first outcome that fails; the ∃ loop short-circuits
on the first robust action, except at the root where every action is scored so that tied optima can
all be returned; and states are memoised on a canonical form that excludes history, so two paths
that learned the same things share a subtree. A declared state budget bounds the rest, and running
into it produces ``NOT_ESTABLISHED/BUDGET`` rather than a false negative.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from rarepipe.stages.control.policy.actions import (Action, ActionSpace, admissible,
                                                    admissible_outcomes, build_action_space,
                                                    campaign_cover, excluded_non_informative)
from rarepipe.stages.control.policy.certificates import (AdversaryWitness, ClosingCombinations,
                                                         minimal_closing_combinations,
                                                         robust_subset, unreached_frontiers)
from rarepipe.stages.control.policy.graph import PolicyGraph
from rarepipe.stages.control.policy.ranking import (Candidate, ProgressVector, maximin,
                                                    progress_between, rank)
from rarepipe.stages.control.policy.reachability import (Frontier, blocking_outcomes,
                                                          can_establish, frontier,
                                                          minimum_branches)
from rarepipe.stages.control.policy.state import KnowledgeState, Observation
from rarepipe.stages.control.policy.update import state_frontier, unsafe_routes, update

TRUE, FALSE, NOT_ESTABLISHED = "TRUE", "FALSE", "NOT_ESTABLISHED"
HORIZON, BUDGET = "HORIZON", "BUDGET"

TARGET_MODE, DISCOVERY_MODE = "TARGET", "DISCOVERY"


@dataclass(frozen=True)
class Constraints:
    """What the search is allowed to do. Nothing here is inferred; a caller states it."""
    include_non_informative: bool = False
    restrict_to_target_relevant: bool = True
    singleton_fallback: bool = True
    # The budget counts *state evaluations*, not recursion entries: one recursion step examines
    # a few hundred candidate successors, and it is those that cost the time and fill the memo
    # tables. Counting entries instead bounded neither, and let a search reach a gigabyte of
    # cached statuses while reporting twenty thousand states.
    max_states: int = 3_000_000
    max_closing_combination_size: int = 2
    # Cap on minimal sets kept per node *while ranking candidates*, where the sets feed a comparison
    # rather than an answer. Truncation is reported. The frontier that is published is uncapped.
    scoring_max_sets: int | None = 8
    # Diagnostics — the per-conjunct "which parts of the target are robustly reachable" probe —
    # get their own, smaller budget. They are a breakdown of the headline answer, not the
    # answer, and solving each conjunct as hard as the whole target tripled the cost of a
    # report for a figure nobody treats as load-bearing.
    diagnostic_max_states: int = 300_000
    # Domain annotations for the progress vector. Absent means the component is reported unavailable
    # rather than assumed zero.
    hypothesis_discriminators: Mapping[str, frozenset[str]] = field(default_factory=dict)
    node_families: Mapping[str, str] = field(default_factory=dict)

    def describe(self) -> dict:
        return {
            "include_non_informative": self.include_non_informative,
            "restrict_to_target_relevant": self.restrict_to_target_relevant,
            "singleton_fallback": self.singleton_fallback,
            "max_states": self.max_states,
            "max_closing_combination_size": self.max_closing_combination_size,
            "diagnostic_max_states": self.diagnostic_max_states,
            "hypothesis_discriminators": len(self.hypothesis_discriminators),
            "node_families": len(self.node_families),
        }


@dataclass(frozen=True)
class Verdict:
    value: str
    reason: str | None = None

    @property
    def established(self) -> bool:
        return self.value in (TRUE, FALSE)

    def describe(self) -> dict | str:
        return self.value if self.reason is None else {"value": self.value, "reason": self.reason}


@dataclass
class PolicyNode:
    """A node of the contingent plan: one action, then one continuation per admissible outcome."""
    action: str | None = None
    outcome_children: dict[str, "PolicyNode"] = field(default_factory=dict)
    status: str = "ACTION"          # ACTION | GOAL_REACHED | CLOSED | FRONTIER

    def depth(self) -> int:
        if not self.outcome_children:
            return 0
        return 1 + max(child.depth() for child in self.outcome_children.values())

    def describe(self, depth: int = 6) -> dict:
        if self.action is None or depth <= 0:
            return {"status": self.status}
        return {
            "status": self.status,
            "action": self.action,
            "then": {
                outcome: child.describe(depth - 1)
                for outcome, child in sorted(self.outcome_children.items())
            },
        }


@dataclass
class _Budget:
    limit: int
    used: int = 0

    def spend(self) -> bool:
        self.used += 1
        return self.used <= self.limit

    @property
    def exhausted(self) -> bool:
        return self.used > self.limit


class _Solver:
    """One search. Holds the memo table and the budget, so a solve is reproducible in isolation."""

    def __init__(self, graph: PolicyGraph, space: ActionSpace, target: str,
                 constraints: Constraints):
        self.graph = graph
        self.space = space
        self.target = target
        self.constraints = constraints
        self.budget = _Budget(constraints.max_states)
        # Monotone verdict caches, keyed on the canonical state alone. `_true_from` holds the
        # shallowest horizon at which a robust policy was found, with that policy; anything in
        # `_definitely_false` is defeated at every horizon.
        self._true_from: dict[tuple, tuple[int, PolicyNode]] = {}
        self._definitely_false: set[tuple] = set()
        self._frontiers: dict[tuple, Frontier] = {}
        self._status_cache: dict[tuple, tuple[bool, bool]] = {}
        self._distance_cache: dict[tuple, int | None] = {}
        self._floor_cache: dict[tuple, int | None] = {}
        # The most branches any one action settles, which converts a branch floor into an
        # action floor. Read off the action space rather than assumed to be one, because a
        # campaign resolving two branches halves the depth a route needs.
        self._widest = max((len(a.resolves) for a in space.actions), default=0)
        self.visited = 0          # recursion entries: the trace's "states considered"
        self.witness: AdversaryWitness | None = None

    # ------------------------------------------------------------------ helpers

    def frontier_for(self, state: KnowledgeState) -> Frontier:
        """The set-based frontier: minimal branch sets, for scoring and reporting.

        Scoped to this solve's target and cached per state. Still expensive — the recursion uses
        ``_status`` instead, and this is called once per state that actually needs the sets.
        """
        key = state.canonical()
        if key not in self._frontiers:
            self._frontiers[key] = state_frontier(self.graph, state, destination=self.target)
        return self._frontiers[key]

    def _status(self, state: KnowledgeState) -> tuple[bool, bool]:
        """``(establishable, established)``, by the cheap relaxation. The recursion's hot path.

        This is where the budget is spent, because this is the unit of work: one recursion step
        evaluates a few hundred candidate successor states, so counting recursion entries bounds
        neither the time nor — worse — the size of this cache. A budget that did not gate the cache
        let a twenty-thousand-state search reach well over a gigabyte of memo entries.

        A miss over budget is still computed: the caller needs a correct answer, and ``robust``
        stops at its next entry. The overshoot is bounded by one recursion step.
        """
        key = state.canonical()
        if key not in self._status_cache:
            self.budget.spend()
            self._status_cache[key] = can_establish(
                self.graph, known=state.established, decided=state.resolved,
                destination=self.target)
        return self._status_cache[key]

    def distance(self, state: KnowledgeState) -> int | None:
        """Fewest branches still to resolve before the target is established, or ``None`` if closed.

        Read off a *capped* frontier, which is sound for this question specifically: ``_prune`` keeps
        minimal sets in non-decreasing size order, so a cap discards the largest and can never
        change the smallest one's size. It would undercount the set of outstanding branches, which
        is why that number is taken from the graph instead.
        """
        key = state.canonical()
        if key not in self._distance_cache:
            establishable, established = self._status(state)
            if established:
                self._distance_cache[key] = 0
            elif not establishable:
                self._distance_cache[key] = None
            else:
                f = state_frontier(self.graph, state, destination=self.target,
                                   max_sets=self.constraints.scoring_max_sets)
                self._distance_cache[key] = f.minimal_size(self.target)
        return self._distance_cache[key]

    def floor(self, state: KnowledgeState) -> int | None:
        """An admissible floor on the branches still to resolve. Cheap; never an overestimate."""
        key = state.canonical()
        if key not in self._floor_cache:
            self._floor_cache[key] = minimum_branches(
                self.graph, known=state.established, decided=state.resolved,
                destination=self.target)
        return self._floor_cache[key]

    def too_deep(self, state: KnowledgeState, horizon: int) -> bool:
        """Whether the horizon cannot possibly hold enough actions, however well they are chosen.

        One action settles at most ``_widest`` branches, so resolving a floor of *n* takes at least
        ``ceil(n / widest)`` of them. When that exceeds the horizon no policy fits, and the whole
        subtree can be skipped without expanding it. Admissible because the floor is: the bound can
        only ever be too generous, never too strict, so nothing reachable is pruned.
        """
        if self._widest <= 0:
            return False
        floor = self.floor(state)
        if floor is None:
            return False                     # closed, which the caller reports as FALSE, not depth
        return -(-floor // self._widest) > horizon

    def outcomes_of(self, action: Action, state: KnowledgeState) -> tuple[Observation, ...]:
        return admissible_outcomes(
            self.graph, action, state,
            include_non_informative=self.constraints.include_non_informative)

    # ------------------------------------------------------------------ the recursion

    def robust(self, state: KnowledgeState, horizon: int) -> tuple[Verdict, PolicyNode | None]:
        establishable, established = self._status(state)
        if established:
            return Verdict(TRUE), PolicyNode(status="GOAL_REACHED")
        if not establishable:
            return Verdict(FALSE, "ROUTE_CLOSED"), PolicyNode(status="CLOSED")
        if horizon <= 0:
            return Verdict(NOT_ESTABLISHED, HORIZON), PolicyNode(status="FRONTIER")
        if self.too_deep(state, horizon):
            return Verdict(NOT_ESTABLISHED, HORIZON), PolicyNode(status="FRONTIER")

        canonical = state.canonical()
        # Both verdicts are monotone in the horizon, and exploiting that is what makes iterative
        # deepening affordable. TRUE at some horizon stays TRUE at any larger one — the extra steps
        # simply go unused. And FALSE here means *definitively* defeated: the route is closed, or
        # every action meets an outcome that is itself definitively defeated. That property does not
        # mention the horizon, so a FALSE never has to be recomputed at a deeper one.
        cached_true = self._true_from.get(canonical)
        if cached_true is not None and horizon >= cached_true[0]:
            return Verdict(TRUE), cached_true[1]
        if canonical in self._definitely_false:
            return Verdict(FALSE, "ALL_ACTIONS_DEFEATED"), None
        if self.budget.exhausted:
            return Verdict(NOT_ESTABLISHED, BUDGET), None
        self.visited += 1

        saw_indeterminate = False
        for action in admissible(self.space, state):
            outcomes = self.outcomes_of(action, state)
            if not outcomes:
                continue
            children: dict[str, PolicyNode] = {}
            defeated = False
            for observation in self._fail_first(state, action, outcomes):
                verdict, child = self.robust(update(self.graph, state, action, observation),
                                             horizon - 1)
                if verdict.value == TRUE and child is not None:
                    children[observation.id] = child
                    continue
                defeated = True
                if verdict.value == NOT_ESTABLISHED:
                    saw_indeterminate = True
                break                         # one failing outcome is enough to defeat the action
            if not defeated:
                node = PolicyNode(action=action.id, outcome_children=children)
                self._true_from[canonical] = (horizon, node)
                return Verdict(TRUE), node

        if self.budget.exhausted:
            return Verdict(NOT_ESTABLISHED, BUDGET), None
        # FALSE only when every action met an outcome that *definitively* defeated it. If any defeat
        # was merely "we ran out of horizon", the honest answer is that we do not know.
        if saw_indeterminate:
            return Verdict(NOT_ESTABLISHED, HORIZON), None
        self._definitely_false.add(canonical)
        return Verdict(FALSE, "ALL_ACTIONS_DEFEATED"), None

    def _fail_first(self, state: KnowledgeState, action, outcomes):
        """Outcomes ordered worst-first, by the cheap relaxation only.

        Pure search order: the ∀ quantifier is defeated by any single failing outcome, so testing
        the one that closes the route *first* kills a hopeless action after one child instead of
        after all fifteen. It cannot change the verdict — every outcome is still examined unless one
        of them defeats the action, and that defeat is order-independent.
        """
        if len(outcomes) < 2:
            return outcomes

        def rank(observation):
            establishable, established = self._status(
                update(self.graph, state, action, observation))
            # closed first, then merely unfinished, then already reached
            return (0 if not establishable else 1 if not established else 2, observation.id)

        return sorted(outcomes, key=rank)

    # ------------------------------------------------------------------ witness extraction

    def adversary(self, state: KnowledgeState, horizon: int, depth: int = 2) -> AdversaryWitness:
        """For every action, an outcome that defeats it. The counter-policy, replayable by hand."""
        defeats: list[tuple[str, str, AdversaryWitness | None]] = []
        for action in admissible(self.space, state):
            for observation in self.outcomes_of(action, state):
                child_state = update(self.graph, state, action, observation)
                verdict, _ = self.robust(child_state, horizon - 1)
                if verdict.value != TRUE:
                    child = (self.adversary(child_state, horizon - 1, depth - 1)
                             if depth > 1 and horizon > 1 else None)
                    defeats.append((action.id, observation.id, child))
                    break
        return AdversaryWitness(state=state.describe(), defeats=tuple(defeats),
                                reason="no action survives every admissible outcome")


# ---------------------------------------------------------------------- scoring the first step


def _score_root_actions(solver: _Solver, state: KnowledgeState, horizon: int, *,
                        need_robust: bool) -> list[Candidate]:
    """Every first action, scored. No short-circuit here: tied optima must all be found.

    ``need_robust`` asks for the per-action robustness flag, which costs a full sub-search per
    action and is only ever *read* when a robust policy exists — it is what distinguishes tied
    optimal routes in target mode. In discovery mode the ranking is maximin over guaranteed
    progress and safety, none of which consults it, so computing it there would buy nothing and
    is by far the most expensive thing this function could do.
    """
    graph, space, constraints = solver.graph, solver.space, solver.constraints
    # Outstanding work comes from the graph's own relevance relation, which is exact and costs one
    # reverse walk. Distance comes from a capped frontier, which cannot misreport the smallest set's
    # size. Mixing the two deliberately: each component uses the cheapest computation that is exact
    # for it, rather than one expensive computation that is exact for all of them.
    relevant = frozenset(graph.target_relevant_branches(solver.target))
    outcome_counts = {
        branch: sum(1 for name in graph.nodes[branch].outcome_names
                    if name not in graph.nodes[branch].non_informative)
        for branch in relevant
    }
    before_unresolved = relevant - state.resolved_branches
    before_distance = solver.distance(state)
    candidates: list[Candidate] = []

    for action in admissible(space, state):
        outcomes = solver.outcomes_of(action, state)
        if not outcomes:
            continue
        robust_here = True
        worst_unknowns = 0
        worst_campaigns = 0
        progress_vectors: list[ProgressVector] = []
        for observation in outcomes:
            child_state = update(graph, state, action, observation)
            if need_robust:
                verdict, _ = solver.robust(child_state, horizon - 1)
                if verdict.value != TRUE:
                    robust_here = False
            else:
                robust_here = False
            _, established = solver._status(child_state)
            after_unresolved = (frozenset() if established
                               else relevant - child_state.resolved_branches)
            worst_unknowns = max(worst_unknowns, len(after_unresolved))
            cover, uncovered = campaign_cover(space, after_unresolved)
            worst_campaigns = max(worst_campaigns, len(cover) + len(uncovered))
            progress_vectors.append(progress_between(
                before_unresolved=before_unresolved,
                after_unresolved=after_unresolved,
                outcome_counts=outcome_counts,
                before_distance=before_distance,
                after_distance=solver.distance(child_state),
                before_resolved=state.resolved_branches,
                after_resolved=child_state.resolved_branches,
                hypothesis_discriminators=constraints.hypothesis_discriminators,
                node_families=constraints.node_families,
            ))
        candidates.append(Candidate(
            action_id=action.id,
            # Zero by construction: nothing in a returned policy is ever offered as acceptable
            # while routing through an unsafe terminal. The field exists because the same metric
            # must be computable against answers this engine did not produce.
            safety_violations=0,
            robust=robust_here,
            worst_case_unknowns=worst_unknowns,
            worst_case_campaigns=worst_campaigns,
            progress=ProgressVector.worst(progress_vectors) or ProgressVector(),
            explicit_cost=None,
            undeclared=not action.declared,
            needs_component_discovery=action.needs_component_discovery,
        ))
    return candidates


# ---------------------------------------------------------------------- result


@dataclass
class PolicyResult:
    model_id: str
    target: str
    mode: str
    horizon: int
    conditional_reachable: bool
    robust_reachable: Verdict
    minimal_robust_horizon: int | None
    # The deepest horizon whose policy space was searched exhaustively without finding one.
    # `None` means not even horizon 0 was settled. Independent of the verdict: it survives the
    # search later running out of budget, and it is the claim a reader can actually rely on.
    no_robust_policy_within: int | None
    recommended_actions: tuple[str, ...]
    policy: PolicyNode | None
    worst_case_depth: int | None
    single_outcome_resilient: bool
    blocking_single_outcomes: tuple[tuple[str, str], ...]
    tied_minimal_branch_sets: tuple[frozenset[str], ...]
    remaining_frontiers: tuple[str, ...]
    unsafe_routes: tuple[tuple[str, str, str], ...]
    closing_combinations: ClosingCombinations | None
    robust_conjuncts: dict
    witness: AdversaryWitness | None
    candidates: tuple[Candidate, ...]
    ranking_report: dict
    action_space: dict
    excluded_non_informative: tuple[tuple[str, str], ...]
    frontier_truncated: tuple[str, ...]
    states_considered: int
    state_evaluations: int
    budget_exhausted: bool
    constraints: dict

    def describe(self, *, policy_depth: int = 6) -> dict:
        """The machine-readable answer. Field names are the API contract."""
        return {
            "model_id": self.model_id,
            "target": self.target,
            "mode": self.mode,
            "horizon": self.horizon,
            "conditional_reachable": self.conditional_reachable,
            "robust_reachable": self.robust_reachable.describe(),
            "minimal_robust_horizon": self.minimal_robust_horizon,
            "no_robust_policy_within": self.no_robust_policy_within,
            "recommended_actions": list(self.recommended_actions),
            "tied_action_count": len(self.recommended_actions),
            "policy": self.policy.describe(policy_depth) if self.policy else None,
            "worst_case_depth": self.worst_case_depth,
            "single_outcome_resilient": self.single_outcome_resilient,
            "blocking_single_outcomes": [
                {"branch": b, "outcome": o} for b, o in self.blocking_single_outcomes
            ],
            "tied_minimal_branch_sets": [sorted(s) for s in self.tied_minimal_branch_sets],
            "remaining_frontiers": list(self.remaining_frontiers),
            "unsafe_routes": [
                {"branch": b, "outcome": o, "terminal": t} for b, o, t in self.unsafe_routes
            ],
            "failure_certificates": {
                **(self.closing_combinations.describe() if self.closing_combinations else {}),
                "robust_subset": self.robust_conjuncts,
                "adversary_witness": self.witness.describe() if self.witness else None,
            },
            "candidates": [c.describe() for c in self.candidates],
            "ranking": self.ranking_report,
            "action_space": self.action_space,
            "excluded_non_informative_outcomes": [
                {"branch": b, "outcome": o} for b, o in self.excluded_non_informative
            ],
            "trace": {
                "states_considered": self.states_considered,
                "state_evaluations": self.state_evaluations,
                "budget_exhausted": self.budget_exhausted,
                "frontier_truncated_at": list(self.frontier_truncated),
                "constraints": self.constraints,
            },
        }


# ---------------------------------------------------------------------- entry point


def solve_policy(graph: PolicyGraph, knowledge_state: KnowledgeState | None = None,
                 target: str | None = None, constraints: Constraints | None = None,
                 horizon: int = 6, *, campaigns: Iterable[Action] = (),
                 model_id: str = "") -> PolicyResult:
    """Solve for a robust contingent policy, or explain why there is none.

    Domain-neutral by construction: everything case-specific — which terminals are unsafe, which
    capabilities exist, which campaigns are declared — arrives through the graph and the campaign
    list. Nothing in this package knows what a kinetochore is.
    """
    state = knowledge_state or KnowledgeState.initial()
    constraints = constraints or Constraints()
    target = target or graph.goal

    relevant = None
    if constraints.restrict_to_target_relevant:
        relevant = frozenset(graph.target_relevant_branches(target))
    space = build_action_space(graph, tuple(campaigns),
                               singleton_fallback=constraints.singleton_fallback,
                               restrict_to=relevant)
    solver = _Solver(graph, space, target, constraints)

    base = solver.frontier_for(state)
    conditional = base.establishable(target)

    # Iterative deepening, which gives the minimal satisfying horizon for free and finds a shallow
    # policy without first paying for a deep one.
    verdict = Verdict(FALSE, "ROUTE_CLOSED") if not conditional else Verdict(NOT_ESTABLISHED, HORIZON)
    policy: PolicyNode | None = None
    minimal_horizon: int | None = None
    searched_exactly = None
    if conditional:
        for depth in range(0, horizon + 1):
            verdict, policy = solver.robust(state, depth)
            if verdict.value == TRUE:
                minimal_horizon = depth
                break
            if verdict.value == FALSE:
                break
            if verdict.reason == BUDGET:
                # The budget ran out at this depth, so nothing is established about it or beyond.
                break
            # The space was exhausted at this depth without finding a policy, which is a result:
            # no policy of this many actions or fewer exists. Recorded separately from the verdict
            # because "we looked everywhere up to three campaigns" is a much stronger statement
            # than "we did not find one", and only the first survives hitting the budget later.
            searched_exactly = depth

    candidates = _score_root_actions(solver, state, max(horizon, 1),
                                     need_robust=verdict.value == TRUE)
    if verdict.value == TRUE:
        ordered, tied, report = rank(candidates)
        recommended = tuple(c.action_id for c in tied)
    else:
        tied, report = maximin(candidates)
        ordered = tied
        recommended = tuple(c.action_id for c in tied)
        report["mode_note"] = (
            "No robust policy was established, so the recommendation is the experiment whose worst "
            "admissible outcome still guarantees the most progress. It is not a route to the goal.")

    witness = None
    closing = None
    conjuncts: dict = {}
    if verdict.value != TRUE:
        witness = solver.adversary(state, max(horizon, 1))
        closing = minimal_closing_combinations(
            graph, destination=target,
            max_size=constraints.max_closing_combination_size,
            restrict_to=relevant)

        diagnostic = replace(constraints, max_states=constraints.diagnostic_max_states)

        def check(member: str) -> str:
            sub = _Solver(graph, space, member, diagnostic)
            for depth in range(0, horizon + 1):
                sub_verdict, _ = sub.robust(state, depth)
                if sub_verdict.value in (TRUE, FALSE):
                    return sub_verdict.value
            return NOT_ESTABLISHED

        conjuncts = robust_subset(graph, check)

    blocking = blocking_outcomes(graph, target)
    return PolicyResult(
        model_id=model_id,
        target=target,
        mode=TARGET_MODE if verdict.value == TRUE else DISCOVERY_MODE,
        horizon=horizon,
        conditional_reachable=conditional,
        robust_reachable=verdict,
        minimal_robust_horizon=minimal_horizon,
        no_robust_policy_within=searched_exactly,
        recommended_actions=recommended,
        policy=policy if verdict.value == TRUE else None,
        worst_case_depth=policy.depth() if (policy and verdict.value == TRUE) else None,
        single_outcome_resilient=not blocking,
        blocking_single_outcomes=blocking,
        tied_minimal_branch_sets=base.tied_minimal(target),
        remaining_frontiers=unreached_frontiers(graph, state.resolved, target),
        unsafe_routes=unsafe_routes(graph),
        closing_combinations=closing,
        robust_conjuncts=conjuncts,
        witness=witness,
        candidates=tuple(ordered),
        ranking_report=report,
        action_space=space.describe(),
        excluded_non_informative=excluded_non_informative(graph, space),
        frontier_truncated=tuple(sorted(base.truncated)),
        states_considered=solver.visited,
        state_evaluations=solver.budget.used,
        budget_exhausted=solver.budget.exhausted,
        constraints=constraints.describe(),
    )
