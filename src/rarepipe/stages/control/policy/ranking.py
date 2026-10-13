"""Deterministic ordering, lexicographic and never a weighted sum.

A weighted sum would require weights, and no weight here is grounded in anything. Worse, a sum lets
a large gain on a soft criterion outvote a safety constraint, which is the one thing that must
never happen. So both orderings in this module are lexicographic: each criterion is consulted only
to break ties left by the one above it, and the last tie-break is a canonical identifier so that
the same input yields the same output in every process.

Two orderings live here.

**Policy ranking** follows the specification's seven rules, in order: never prefer a policy that
violates a hard safety constraint; prefer robust success to non-robust; minimise the worst-case
number of relevant unknowns left; maximise the guaranteed elimination of viable routes; minimise
the worst-case number of further campaigns; minimise explicit cost *where real cost metadata
exists*; break remaining ties on canonical ids.

**Progress** is for the case where no robust policy exists — the question becomes "which experiment
guarantees we learn the most useful thing next", answered maximin: the action whose *worst* outcome
still makes the most progress. Progress is a five-component vector, compared lexicographically for
the same reason. Collapsing it to a scalar would hide which kind of progress was bought.

Two of the five components have **no data behind them in a graph that does not annotate them**, and
this module reports that rather than inventing it:

* *hypotheses eliminated* needs each hypothesis to name the branches that discriminate it. A
  hypothesis whose discriminating experiment is described in prose cannot be counted mechanically.
* *families resolved* needs node-to-family membership. Inferring it from identifier spelling is
  exactly the shortcut that has already produced one wrong answer in this repository, so it is not
  done here.

An unavailable component is ``None``, is skipped in the comparison, and is named in the output. It
is never silently treated as zero, because zero is a measurement and absence is not.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterable, Mapping, Sequence


# The five progress components, in the order they are consulted. Declared once, so that the output
# schema, the comparison and the "which of these is unavailable" report cannot drift apart.
PROGRESS_COMPONENTS = (
    "hypotheses_eliminated",
    "families_resolved",
    "worlds_eliminated",
    "branches_eliminated",
    "distance_reduction",
)


@dataclass(frozen=True)
class ProgressVector:
    """Guaranteed progress, one component per declared measure. ``None`` means no data supports it.

    Every component is oriented so that **more is better**.
    """
    hypotheses_eliminated: int | None = None
    families_resolved: int | None = None
    worlds_eliminated: int | None = None
    branches_eliminated: int | None = None
    distance_reduction: int | None = None

    def available(self) -> tuple[str, ...]:
        return tuple(name for name in PROGRESS_COMPONENTS if getattr(self, name) is not None)

    def unavailable(self) -> tuple[str, ...]:
        return tuple(name for name in PROGRESS_COMPONENTS if getattr(self, name) is None)

    def sort_key(self, components: Sequence[str]) -> tuple[int, ...]:
        """Negated, so that ascending sort puts the most progress first."""
        return tuple(-(getattr(self, name) or 0) for name in components)

    def describe(self) -> dict:
        return {name: getattr(self, name) for name in PROGRESS_COMPONENTS}

    @staticmethod
    def worst(vectors: Iterable[ProgressVector]) -> ProgressVector | None:
        """Component-wise minimum: the guarantee that holds whatever the outcome.

        Component-wise rather than "the worst whole vector", because a guarantee is a floor on each
        measure independently. Claiming the floor of one outcome's vector would promise progress on
        a component that a different outcome does not deliver.
        """
        collected = list(vectors)
        if not collected:
            return None
        values: dict[str, int | None] = {}
        for name in PROGRESS_COMPONENTS:
            seen = [getattr(v, name) for v in collected]
            values[name] = None if any(s is None for s in seen) else min(seen)
        return ProgressVector(**values)


def progress_between(*, before_unresolved: frozenset[str], after_unresolved: frozenset[str],
                     outcome_counts: Mapping[str, int],
                     before_distance: int | None, after_distance: int | None,
                     before_resolved: frozenset[str], after_resolved: frozenset[str],
                     hypothesis_discriminators: Mapping[str, frozenset[str]] | None = None,
                     node_families: Mapping[str, frozenset[str]] | None = None) -> ProgressVector:
    """What is guaranteed to have been learned, moving from one state to another.

    Takes plain numbers rather than frontier objects, because each component has a different
    cheapest exact computation and the caller knows which it can afford. In particular the count of
    outstanding branches must come from the graph's own relevance relation — a capped frontier
    undercounts it — while the distance may come from a capped frontier, since pruning drops the
    *largest* sets and so cannot change the smallest one's size.

    ``hypothesis_discriminators`` maps a hypothesis id to the branches whose resolution settles it.
    ``node_families`` maps a branch id to the route families it belongs to — a *set*, because a
    branch shared between two strategies is the normal case rather than the exception, and a
    single-valued field would force a choice that erases one of them.

    Both are optional analysis annotations. They may move scoring; they may never move
    traversability, and nothing in this module can reach the graph to try. When absent, their
    components come back ``None`` rather than zero, because zero is a measurement and absence is
    not.
    """
    # Possible worlds: admissible joint assignments of the branches the goal still depends on. Each
    # resolved branch divides the space by its own outcome count, so the reduction is exact and
    # needs no probability.
    def worlds(unresolved: frozenset[str]) -> int:
        total = 1
        for branch in sorted(unresolved):
            total *= max(outcome_counts.get(branch, 1), 1)
        return total

    # A closed route has distance None. Treat closure as reaching the floor rather than as an
    # improvement of unbounded size: learning that a route is dead is progress, but it is not
    # infinite progress, and an unbounded number would dominate every other component for ever.
    if after_distance is None:
        distance_reduction = before_distance if before_distance is not None else 0
    elif before_distance is None:
        distance_reduction = 0
    else:
        distance_reduction = before_distance - after_distance

    hypotheses = None
    if hypothesis_discriminators:
        settled_before = {h for h, branches in hypothesis_discriminators.items()
                          if branches and branches <= before_resolved}
        settled_after = {h for h, branches in hypothesis_discriminators.items()
                         if branches and branches <= after_resolved}
        hypotheses = len(settled_after - settled_before)

    families = None
    if node_families:
        def live(branches: frozenset[str]) -> set[str]:
            found: set[str] = set()
            for branch in branches:
                found |= set(node_families.get(branch) or ())
            return found

        # Families no longer reachable through any outstanding branch: closed or confirmed, and
        # either way no longer a live alternative.
        families = len(live(before_unresolved) - live(after_unresolved))

    return ProgressVector(
        hypotheses_eliminated=hypotheses,
        families_resolved=families,
        worlds_eliminated=worlds(before_unresolved) - worlds(after_unresolved),
        branches_eliminated=len(before_unresolved) - len(after_unresolved),
        distance_reduction=distance_reduction,
    )


@dataclass(frozen=True)
class Candidate:
    """One first action, scored. Field order is not the ranking order; `sort_key` is."""
    action_id: str
    safety_violations: int
    robust: bool
    worst_case_unknowns: int
    worst_case_campaigns: int
    progress: ProgressVector
    explicit_cost: float | None = None
    # Carried for the report, never for the ordering.
    undeclared: bool = False
    needs_component_discovery: bool = False

    def describe(self) -> dict:
        return {
            "action": self.action_id,
            "robust": self.robust,
            "safety_violations": self.safety_violations,
            "worst_case_unknowns": self.worst_case_unknowns,
            "worst_case_campaigns": self.worst_case_campaigns,
            "explicit_cost": self.explicit_cost,
            "undeclared_campaign": self.undeclared,
            "needs_component_discovery": self.needs_component_discovery,
            "guaranteed_progress": self.progress.describe(),
        }


def rank(candidates: Sequence[Candidate]) -> tuple[tuple[Candidate, ...], tuple[Candidate, ...], dict]:
    """Order candidates and return (ordered, tied-best, report).

    The tied set is every candidate indistinguishable from the best on *every* criterion except the
    canonical-id tie-break. Returning one of several tied optima as though it were unique is a
    specific failure this function exists to prevent, so the tie-break is applied last and only to
    fix an order, never to pick a winner.
    """
    if not candidates:
        return (), (), {"compared_on": [], "skipped": list(PROGRESS_COMPONENTS),
                        "cost_metadata": "ABSENT"}

    # Rule 6 participates only when every candidate carries real cost metadata. A partial cost
    # column would rank the measured ones against an assumed zero for the rest.
    costed = all(c.explicit_cost is not None for c in candidates)
    progress_components = tuple(
        name for name in PROGRESS_COMPONENTS
        if all(getattr(c.progress, name) is not None for c in candidates)
    )
    skipped = tuple(n for n in PROGRESS_COMPONENTS if n not in progress_components)

    def key(c: Candidate) -> tuple:
        return (
            c.safety_violations,                      # 1. minimise; must be zero to be offered
            0 if c.robust else 1,                     # 2. robust success first
            c.worst_case_unknowns,                    # 3. minimise
            c.progress.sort_key(progress_components),  # 4. maximise guaranteed elimination
            c.worst_case_campaigns,                   # 5. minimise
            (c.explicit_cost if costed else 0.0),     # 6. minimise, only when real
        )

    ordered = tuple(sorted(candidates, key=lambda c: (key(c), c.action_id)))
    best = key(ordered[0])
    tied = tuple(c for c in ordered if key(c) == best)
    report = {
        "compared_on": ["safety", "robust_success", "worst_case_unknowns",
                        *(f"progress.{n}" for n in progress_components),
                        "worst_case_campaigns", *(["explicit_cost"] if costed else [])],
        "skipped": list(skipped),
        "skipped_reason": {
            n: "no data in the graph supports this component" for n in skipped
        },
        "cost_metadata": "PRESENT" if costed else "ABSENT",
        "tied_count": len(tied),
    }
    return ordered, tied, report


def maximin(candidates: Sequence[Candidate]) -> tuple[tuple[Candidate, ...], dict]:
    """Discovery mode: the action whose worst admissible outcome still makes the most progress.

    Safety stays first — an action is never preferred for being informative if it is offered as
    acceptable while routing through an unsafe terminal. Beyond that the progress vector decides,
    lexicographically, and ties are returned in full.
    """
    if not candidates:
        return (), {"compared_on": [], "skipped": list(PROGRESS_COMPONENTS)}
    components = tuple(
        name for name in PROGRESS_COMPONENTS
        if all(getattr(c.progress, name) is not None for c in candidates)
    )

    def key(c: Candidate) -> tuple:
        return (c.safety_violations, c.progress.sort_key(components), c.worst_case_campaigns)

    ordered = sorted(candidates, key=lambda c: (key(c), c.action_id))
    best = key(ordered[0])
    tied = tuple(c for c in ordered if key(c) == best)
    return tied, {
        "compared_on": ["safety", *(f"progress.{n}" for n in components), "worst_case_campaigns"],
        "skipped": [n for n in PROGRESS_COMPONENTS if n not in components],
        "skipped_reason": {
            n: "no data in the graph supports this component"
            for n in PROGRESS_COMPONENTS if n not in components
        },
        "tied_count": len(tied),
    }


def component_names() -> tuple[str, ...]:
    """Guard against the dataclass and the declared order drifting apart."""
    declared = tuple(f.name for f in fields(ProgressVector))
    if declared != PROGRESS_COMPONENTS:
        raise RuntimeError(
            f"ProgressVector fields {declared} do not match PROGRESS_COMPONENTS "
            f"{PROGRESS_COMPONENTS}; the ranking order and the output schema have drifted")
    return PROGRESS_COMPONENTS
