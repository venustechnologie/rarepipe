"""Synthetic AND/OR graphs with known answers.

MVA alone is not enough: one hand-built graph is one shape, and an algorithm tuned until it
succeeds on it has learned that graph rather than the problem. These generators build graphs whose
right answer follows from the construction, so a disagreement is a bug in the solver rather than a
question about biology.

Each generator covers one of the structures the specification lists, and each returns the answer it
was built to have. The point is not realism — these are not biology and do not pretend to be. It is
that the answer is known *independently of the solver*, which is the only thing that makes the
agreement meaningful.

Determinism is by explicit seed. Nothing is random where a structure is the point of the fixture.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random

from rarepipe.stages.control.policy import (ALL_OF, BRANCH, FRONTIER, MEASUREMENT, PolicyGraph,
                                            STATE, TERMINAL, UNSAFE, Action, Edge, Node)
from rarepipe.stages.control.policy.actions import DECLARED_CAMPAIGN

CAPABILITY = "MODEL"


@dataclass(frozen=True)
class SyntheticCase:
    """A graph, its campaigns, and what the construction guarantees about the answer."""
    name: str
    graph: PolicyGraph
    campaigns: tuple[Action, ...]
    expected_robust: str
    expected_minimal_horizon: int | None
    # Two different sets, and conflating them is a real mistake: every action that *begins* a
    # robust policy, against the subset the lexicographic ranking actually *recommends*. The
    # ranking may legitimately narrow the first to the second — an action can be robust and
    # still guarantee less progress than another — so a test asserting they are equal is wrong
    # in general. The relationship is containment.
    expected_robust_first_actions: tuple[str, ...]
    expected_recommended_actions: tuple[str, ...]
    expected_tied_minimal_route_count: int
    structures: tuple[str, ...]
    note: str


def _branch(bid: str, outcomes: dict[str, str], *, non_informative: tuple[str, ...] = ()) -> Node:
    return Node(id=bid, kind=BRANCH, outcomes=tuple(outcomes.items()), requires=CAPABILITY,
                resolves_by=MEASUREMENT, non_informative=non_informative)


def _build(nodes, edges) -> PolicyGraph:
    return PolicyGraph.build(nodes=nodes, edges=edges, root="ROOT", goal="GOAL",
                             available_requirements=[CAPABILITY])


def always_arrives(width: int = 3) -> SyntheticCase:
    """One branch, every outcome leading on. Robust at horizon 1 by construction."""
    outcomes = {f"o{i}": "S_DONE" for i in range(width)}
    graph = _build(
        [Node(id="ROOT", kind=STATE), _branch("B", outcomes), Node(id="S_DONE", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "B"), Edge("S_DONE", "GOAL")])
    return SyntheticCase(
        name=f"always_arrives_{width}", graph=graph, campaigns=(),
        expected_robust="TRUE", expected_minimal_horizon=1,
        expected_robust_first_actions=("RESOLVE::B",),
        expected_recommended_actions=("RESOLVE::B",),
        expected_tied_minimal_route_count=1,
        structures=("single route",),
        note="Every outcome arrives, so the ∀ quantifier is satisfied in one step.")


def one_dead_outcome() -> SyntheticCase:
    """A single dead end makes the whole thing non-robust while staying conditionally reachable."""
    graph = _build(
        [Node(id="ROOT", kind=STATE),
         _branch("B", {"ok": "S_DONE", "dead": "T_DEAD"}),
         Node(id="S_DONE", kind=STATE), Node(id="T_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "B"), Edge("S_DONE", "GOAL")])
    return SyntheticCase(
        name="one_dead_outcome", graph=graph, campaigns=(),
        expected_robust="FALSE", expected_minimal_horizon=None,
        expected_robust_first_actions=(), expected_recommended_actions=(),
        expected_tied_minimal_route_count=1,
        structures=("dead end", "conditional but not robust"),
        note="Conditional reachability holds; robustness cannot, because one outcome ends it.")


def tied_optima(count: int = 4) -> SyntheticCase:
    """``count`` interchangeable sufficient branches: exactly ``count`` tied minimal routes.

    The fixture for the failure that motivated removing a silent cap — a solver returning one of
    several tied optima as though it were unique.
    """
    nodes = [Node(id="ROOT", kind=STATE), Node(id="S_DONE", kind=STATE),
             Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))]
    edges = [Edge("S_DONE", "GOAL")]
    for i in range(count):
        nodes.append(_branch(f"B{i}", {"a": "S_DONE", "b": "S_DONE"}))
        edges.append(Edge("ROOT", f"B{i}"))
    return SyntheticCase(
        name=f"tied_optima_{count}", graph=_build(nodes, edges), campaigns=(),
        expected_robust="TRUE", expected_minimal_horizon=1,
        expected_robust_first_actions=tuple(f"RESOLVE::B{i}" for i in range(count)),
        expected_recommended_actions=tuple(f"RESOLVE::B{i}" for i in range(count)),
        expected_tied_minimal_route_count=count,
        structures=("multiple tied optima",),
        note=f"{count} interchangeable routes; all {count} must be returned, not one of them.")


def conjunction(members: int = 3) -> SyntheticCase:
    """An AND node needing every member: the horizon is the number of members."""
    nodes = [Node(id="ROOT", kind=STATE)]
    edges = []
    names = []
    for i in range(members):
        nodes.append(_branch(f"B{i}", {"a": f"S{i}", "b": f"S{i}"}))
        nodes.append(Node(id=f"S{i}", kind=STATE))
        edges.append(Edge("ROOT", f"B{i}"))
        names.append(f"S{i}")
    nodes.append(Node(id="GOAL", kind=ALL_OF, members=tuple(names)))
    return SyntheticCase(
        name=f"conjunction_{members}", graph=_build(nodes, edges), campaigns=(),
        expected_robust="TRUE", expected_minimal_horizon=members,
        expected_robust_first_actions=tuple(f"RESOLVE::B{i}" for i in range(members)),
        expected_recommended_actions=tuple(f"RESOLVE::B{i}" for i in range(members)),
        expected_tied_minimal_route_count=1,
        structures=("AND node",),
        note=f"All {members} conjuncts are required, so no policy is shorter than {members}.")


def campaign_halves_depth(members: int = 4) -> SyntheticCase:
    """A campaign settling two branches at once: the depth is halved, and counting branches misleads."""
    case = conjunction(members)
    campaigns = tuple(
        Action(id=f"JOINT{i}", kind=DECLARED_CAMPAIGN,
               resolves=(f"B{2 * i}", f"B{2 * i + 1}"), requires=(CAPABILITY,),
               question="toy joint campaign")
        for i in range(members // 2)
    )
    return SyntheticCase(
        name=f"campaign_halves_depth_{members}", graph=case.graph, campaigns=campaigns,
        expected_robust="TRUE", expected_minimal_horizon=members // 2,
        expected_robust_first_actions=tuple(c.id for c in campaigns),
        expected_recommended_actions=tuple(c.id for c in campaigns),
        expected_tied_minimal_route_count=1,
        structures=("AND node", "campaign resolving several branches"),
        note="Branches are units of ignorance, campaigns units of work; the depth follows the work.")


def unsafe_only_route() -> SyntheticCase:
    """The only route runs through an unsafe terminal: not reachable at all, safely or otherwise."""
    graph = _build(
        [Node(id="ROOT", kind=STATE),
         _branch("B", {"benefit": "T_UNSAFE", "nothing": "T_DEAD"}),
         Node(id="T_UNSAFE", kind=TERMINAL, role=UNSAFE),
         Node(id="T_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="S_NEVER", kind=STATE),
         Node(id="GOAL", kind=ALL_OF, members=("S_NEVER",))],
        [Edge("ROOT", "B"), Edge("S_NEVER", "GOAL")])
    return SyntheticCase(
        name="unsafe_only_route", graph=graph, campaigns=(),
        expected_robust="FALSE", expected_minimal_horizon=None,
        expected_robust_first_actions=(), expected_recommended_actions=(),
        expected_tied_minimal_route_count=0,
        structures=("safety closure", "no safe route"),
        note="No benefit may buy a route through an unsafe terminal, so there is no route.")


def deceptive_short_route() -> SyntheticCase:
    """A one-branch route that can fail beside a two-branch route that cannot.

    The trap: ranking by length alone prefers the short route, which is not robust. The robust
    answer is the longer one, and a solver that optimises length before robustness gets this wrong.
    """
    graph = _build(
        [Node(id="ROOT", kind=STATE),
         _branch("SHORT", {"lucky": "S_DONE", "unlucky": "T_DEAD"}),
         _branch("LONG_A", {"a": "S_MID", "b": "S_MID"}),
         _branch("LONG_B", {"a": "S_DONE", "b": "S_DONE"}),
         Node(id="S_MID", kind=STATE), Node(id="S_DONE", kind=STATE),
         Node(id="T_DEAD", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "SHORT"), Edge("ROOT", "LONG_A"), Edge("S_MID", "LONG_B"),
         Edge("S_DONE", "GOAL")])
    return SyntheticCase(
        name="deceptive_short_route", graph=graph, campaigns=(),
        expected_robust="TRUE", expected_minimal_horizon=2,
        expected_robust_first_actions=("RESOLVE::LONG_A", "RESOLVE::LONG_B",
                                       "RESOLVE::SHORT"),
        expected_recommended_actions=("RESOLVE::LONG_A", "RESOLVE::LONG_B"),
        expected_tied_minimal_route_count=1,
        structures=("deceptively short route", "robustness beats length"),
        note="All three begin a robust policy, because the short gamble failing closes nothing. "
             "The ranking still excludes it: its unlucky outcome guarantees no progress at all, "
             "while the long route guarantees a step whatever happens. Robustness does not "
             "separate these; guaranteed progress does.")


def invalid_run_outcome() -> SyntheticCase:
    """A declared invalid-run outcome, which must not be quantified over."""
    graph = _build(
        [Node(id="ROOT", kind=STATE),
         _branch("B", {"ok": "S_DONE", "assay_void": "T_REPEAT"},
                 non_informative=("assay_void",)),
         Node(id="S_DONE", kind=STATE), Node(id="T_REPEAT", kind=TERMINAL, role=FRONTIER),
         Node(id="GOAL", kind=ALL_OF, members=("S_DONE",))],
        [Edge("ROOT", "B"), Edge("S_DONE", "GOAL")])
    return SyntheticCase(
        name="invalid_run_outcome", graph=graph, campaigns=(),
        expected_robust="TRUE", expected_minimal_horizon=1,
        expected_robust_first_actions=("RESOLVE::B",),
        expected_recommended_actions=("RESOLVE::B",),
        expected_tied_minimal_route_count=1,
        structures=("invalid run excluded from the quantifier",),
        note="A voided validity gate is a failure to observe, not a result about the world.")


def catalogue(seed: int = 0) -> tuple[SyntheticCase, ...]:
    """Every synthetic case. ``seed`` is accepted for future randomised shapes and unused today.

    Deliberately fixed rather than random: each of these exists to pin one structure, and a fixture
    that varies between runs cannot pin anything.
    """
    Random(seed)  # reserved; the catalogue is structural, not sampled
    return (
        always_arrives(2),
        always_arrives(4),
        one_dead_outcome(),
        tied_optima(2),
        tied_optima(4),
        conjunction(2),
        conjunction(3),
        campaign_halves_depth(4),
        unsafe_only_route(),
        deceptive_short_route(),
        invalid_run_outcome(),
    )
