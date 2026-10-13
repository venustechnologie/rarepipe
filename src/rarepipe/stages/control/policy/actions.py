"""The action space: what may be *run*, as distinct from what is merely unresolved.

Branches are units of ignorance; actions are units of work. The two are not the same and counting
branches alone overstates how much work a route needs, because one set of observations can settle
several branches at once.

Three kinds of thing live here, and the difference between the first two is the reason this module
exists rather than treating every branch as its own experiment:

* ``DECLARED_CAMPAIGN`` — a specified experiment: a question, a required system, validity gates,
  readouts, and a declared set of branches it settles. Work somebody could start tomorrow.
* ``UNDECLARED_RESOLVER`` — a branch with no campaign specified for it. It is an action in the
  search because the branch is resolvable *in principle*, and it is tagged so that no output ever
  implies otherwise. This is not a claim that a runnable experiment exists; it is a placeholder for
  work that has not been designed. A recommendation resting on one of these is a recommendation to
  go and design an experiment, and it must read that way.
* unavailable — a branch whose required capability the caller has not declared available, or that
  is barred on governance grounds. Not an action at all. It stays in the record with its reason,
  because "we cannot do this" and "this would not help" are different findings and collapsing them
  would let an authorisation boundary pass for a biological one.

Arms are deliberately *not* enumerated into the policy tree in this version. A campaign with three
mechanistically independent arms stays one action with flat joint outcomes, because at planning
time we cannot know which arm will be the one that fails — guessing would invent a closure. When a
real result arrives it may carry per-arm detail, and `update.py` writes that into the canonical
state. The consequence is the right default: nothing the planner enumerates can close a control
variable, so one unsafe actuator never stands in for an unsafe control variable.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Mapping, Sequence

from rarepipe.stages.control.policy.graph import (COMPONENT_DISCOVERY, MEASUREMENT, PolicyGraph)
from rarepipe.stages.control.policy.state import KnowledgeState, Observation

DECLARED_CAMPAIGN = "DECLARED_CAMPAIGN"
UNDECLARED_RESOLVER = "UNDECLARED_RESOLVER"
ACTION_KINDS = (DECLARED_CAMPAIGN, UNDECLARED_RESOLVER)

UNDECLARED_CAMPAIGN = "UNDECLARED_CAMPAIGN"


@dataclass(frozen=True)
class Arm:
    """One mechanistically independent way of moving the same control variable."""
    id: str
    control_variable: str
    actuator: str
    engagement_readout: str = ""


@dataclass(frozen=True)
class Action:
    id: str
    kind: str
    resolves: tuple[str, ...]
    requires: tuple[str, ...] = ()
    arms: tuple[Arm, ...] = ()
    resolves_by: str = MEASUREMENT
    provenance: str = ""
    question: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolves", tuple(sorted(self.resolves)))
        object.__setattr__(self, "requires", tuple(sorted(set(self.requires))))
        if self.kind not in ACTION_KINDS:
            raise ValueError(f"{self.id}: unknown action kind {self.kind!r}")
        if not self.resolves:
            raise ValueError(f"{self.id}: an action that resolves nothing is not an action")

    @property
    def declared(self) -> bool:
        return self.kind == DECLARED_CAMPAIGN

    @property
    def needs_component_discovery(self) -> bool:
        """Settling this means finding a component nobody has described, not running an assay.

        Kept separate from ``MEASUREMENT`` throughout, because pricing the two alike is the single
        most misleading thing this search could do.
        """
        return self.resolves_by == COMPONENT_DISCOVERY

    def describe(self) -> dict:
        out = {
            "id": self.id,
            "kind": self.kind,
            "resolves": list(self.resolves),
            "resolves_by": self.resolves_by,
            "requires": list(self.requires),
        }
        if self.arms:
            out["arms"] = [
                {"id": a.id, "control_variable": a.control_variable, "actuator": a.actuator}
                for a in self.arms
            ]
        if self.provenance:
            out["provenance"] = self.provenance
        if self.question:
            out["question"] = self.question
        return out


@dataclass(frozen=True)
class Unavailable:
    """A branch that cannot be acted on, and precisely why."""
    branch: str
    requires: str | None
    reason: str

    def describe(self) -> dict:
        return {"branch": self.branch, "requires": self.requires, "reason": self.reason}


@dataclass(frozen=True)
class ActionSpace:
    actions: tuple[Action, ...]
    unavailable: tuple[Unavailable, ...] = ()

    def by_id(self, action_id: str) -> Action:
        for action in self.actions:
            if action.id == action_id:
                return action
        raise KeyError(action_id)

    def for_branch(self, branch: str) -> tuple[Action, ...]:
        return tuple(a for a in self.actions if branch in a.resolves)

    def describe(self) -> dict:
        declared = [a for a in self.actions if a.declared]
        return {
            "total": len(self.actions),
            "declared_campaigns": len(declared),
            "undeclared_resolvers": len(self.actions) - len(declared),
            "unavailable": [u.describe() for u in self.unavailable],
        }


def build_action_space(graph: PolicyGraph, campaigns: Sequence[Action] = (), *,
                       singleton_fallback: bool = True,
                       restrict_to: Iterable[str] | None = None) -> ActionSpace:
    """Declared campaigns, plus one undeclared resolver per branch no campaign covers.

    ``restrict_to`` narrows the branch universe — normally to the target-relevant branches, since
    resolving anything else can only remove routes to the goal and never add one.

    A campaign is available only if *every* capability it needs is declared available. A campaign
    spanning a cell experiment and an organism experiment is not half-runnable.
    """
    universe = set(restrict_to) if restrict_to is not None else set(graph.branch_ids())
    actions: list[Action] = []
    unavailable: list[Unavailable] = []

    def requirement_problem(branches: Iterable[str]) -> str | None:
        missing = sorted({
            graph.nodes[b].requires for b in branches
            if graph.nodes[b].requires is not None
            and graph.nodes[b].requires not in graph.available_requirements
        })
        return ", ".join(missing) if missing else None

    covered: set[str] = set()
    for campaign in sorted(campaigns, key=lambda c: c.id):
        relevant = [b for b in campaign.resolves if b in universe]
        if not relevant:
            continue
        covered.update(campaign.resolves)
        if (missing := requirement_problem(campaign.resolves)) is not None:
            unavailable.append(Unavailable(
                branch=campaign.id, requires=missing,
                reason=f"campaign requires {missing}, which is not declared available"))
            continue
        actions.append(campaign)

    if singleton_fallback:
        for branch in sorted(universe - covered):
            node = graph.nodes[branch]
            if (missing := requirement_problem([branch])) is not None:
                unavailable.append(Unavailable(
                    branch=branch, requires=node.requires,
                    reason=f"requires {missing}, which is not declared available"))
                continue
            actions.append(Action(
                id=f"RESOLVE::{branch}",
                kind=UNDECLARED_RESOLVER,
                resolves=(branch,),
                requires=(node.requires,) if node.requires else (),
                resolves_by=node.resolves_by,
                provenance=UNDECLARED_CAMPAIGN,
                question=node.label,
            ))

    return ActionSpace(actions=tuple(sorted(actions, key=lambda a: a.id)),
                       unavailable=tuple(sorted(unavailable, key=lambda u: u.branch)))


def admissible(space: ActionSpace, state: KnowledgeState) -> tuple[Action, ...]:
    """Actions that would still settle something. An action resolving only decided branches is spent."""
    done = state.resolved_branches
    return tuple(a for a in space.actions if any(b not in done for b in a.resolves))


def admissible_outcomes(graph: PolicyGraph, action: Action, state: KnowledgeState, *,
                        include_non_informative: bool = False) -> tuple[Observation, ...]:
    """Every admissible joint result of one action.

    The joint space is the product over the branches the action still settles, because a campaign
    returns one result per branch it resolves and those results are separately admissible — a
    component can lower missegregation *and* harm the population, which is why safety is its own
    branch rather than a caveat on the efficacy one.

    Non-informative outcomes are excluded by default. They are not results about biology but
    failures to produce one, and quantifying over them would make every policy fail robustness
    because every assay can void its validity gates. The exclusion is reported by the caller, never
    silent, and ``include_non_informative=True`` gives the other answer for comparison.
    """
    done = state.resolved_branches
    pending = [b for b in action.resolves if b not in done]
    if not pending:
        return ()
    per_branch: list[list[tuple[str, str]]] = []
    for branch in pending:
        node = graph.nodes[branch]
        names = [
            name for name in node.outcome_names
            if include_non_informative or name not in node.non_informative
        ]
        if not names:
            return ()
        per_branch.append([(branch, name) for name in names])
    return tuple(
        Observation(action_id=action.id, results=tuple(combination))
        for combination in product(*per_branch)
    )


def excluded_non_informative(graph: PolicyGraph, space: ActionSpace) -> tuple[tuple[str, str], ...]:
    """Every (branch, outcome) the search leaves out, so the omission is auditable."""
    out: list[tuple[str, str]] = []
    for action in space.actions:
        for branch in action.resolves:
            node = graph.nodes.get(branch)
            if node is None:
                continue
            out.extend((branch, name) for name in node.non_informative)
    return tuple(sorted(set(out)))


def campaign_cover(space: ActionSpace, branches: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The fewest actions covering a set of branches, plus any branch nothing covers.

    Brute-forced over the declared campaigns: there are a handful, and an exact answer beats a
    heuristic nobody can check. No time, cost or probability is involved.
    """
    wanted = frozenset(branches)
    useful = {a.id: frozenset(a.resolves) & wanted for a in space.actions if a.declared}
    useful = {k: v for k, v in useful.items() if v}
    reachable = frozenset().union(*useful.values()) if useful else frozenset()
    uncovered = tuple(sorted(wanted - reachable))
    ids = sorted(useful)
    from itertools import combinations
    for size in range(len(ids) + 1):
        for combo in combinations(ids, size):
            got = frozenset().union(*(useful[c] for c in combo)) if combo else frozenset()
            if got >= reachable:
                return tuple(combo), uncovered
    return (), uncovered


def seed_registry_from_arms(actions: Iterable[Action],
                            extra: Mapping[str, Iterable[str]] | None = None) -> dict[str, list[str]]:
    """Collect {control_variable: [actuator, ...]} from declared arms, plus any extras."""
    registry: dict[str, set[str]] = {}
    for action in actions:
        for arm in action.arms:
            registry.setdefault(arm.control_variable, set()).add(arm.actuator)
    for cv, actuators in (extra or {}).items():
        registry.setdefault(cv, set()).update(actuators)
    return {cv: sorted(actuators) for cv, actuators in sorted(registry.items())}
