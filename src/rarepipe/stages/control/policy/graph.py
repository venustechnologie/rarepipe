"""A contingent AND/OR graph, with no knowledge of any particular case.

This module is the engine's input language. It deliberately knows nothing about biology, about
MVA, or about the vocabulary any one map happens to use. A caller hands it node kinds, outcome
names and *roles*; the domain's own strings — ``UNSAFE``, ``GOVERNANCE_BLOCKED``, ``CELL_MODEL`` —
stay in the caller's adapter and arrive here already mapped onto the small set of roles the
mathematics actually distinguishes.

That boundary is the point. A solver that imported a case's terminal vocabulary would have to be
rewritten for the second case, and the whole claim of the engine is that the same core solves both.

Four node kinds, which is all the structure the search needs:

* ``STATE`` — something that can be established, and that leads onward along edges.
* ``BRANCH`` — a unit of ignorance. It is left *only* by its outcomes, never by an edge, because a
  branch that could be walked past would let a route skip the experiment that resolves it.
* ``ALL_OF`` — a conjunction. Established when every member is, which makes it a precondition set
  rather than a waypoint with its own onward path.
* ``TERMINAL`` — an end state carrying a role: reached, unsafe, blocked, impossible or frontier.

Roles, and why each is separate:

* ``GOAL`` — the thing we are solving for. Normally an ``ALL_OF``, not a terminal.
* ``UNSAFE`` — a hard constraint. No benefit anywhere else in the graph may trade against it.
* ``BLOCKED`` — cannot be done, for reasons outside the biology (authorisation, materials). It is
  held apart from ``IMPOSSIBLE`` on purpose: a governance boundary is not a biological finding,
  and collapsing the two would let an administrative limit masquerade as a fact about the world.
* ``IMPOSSIBLE`` — ruled out by evidence already held.
* ``FRONTIER`` — not established, with no next step specified. The honest third answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

STATE, BRANCH, ALL_OF, TERMINAL = "STATE", "BRANCH", "ALL_OF", "TERMINAL"
NODE_KINDS = (STATE, BRANCH, ALL_OF, TERMINAL)

GOAL, UNSAFE, BLOCKED, IMPOSSIBLE, FRONTIER = "GOAL", "UNSAFE", "BLOCKED", "IMPOSSIBLE", "FRONTIER"
TERMINAL_ROLES = (GOAL, UNSAFE, BLOCKED, IMPOSSIBLE, FRONTIER)

MEASUREMENT, COMPONENT_DISCOVERY = "MEASUREMENT", "COMPONENT_DISCOVERY"


class GraphError(ValueError):
    """The graph contradicts its own declared shape. Raised rather than worked around."""


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    label: str = ""
    # BRANCH only: outcome name -> node it establishes. Ordered by name on construction so that
    # every enumeration over outcomes is reproducible across processes.
    outcomes: tuple[tuple[str, str], ...] = ()
    # BRANCH only: outcomes that are not results about the world but failures to observe one — an
    # invalid run, an unengaged target, a voided validity gate. They are *declared*, never guessed,
    # and the distinction is load-bearing: a run that did not happen validly tells us nothing, so
    # quantifying over it would make every policy fail robustness on the grounds that any assay can
    # break. An outcome recording that the experiment ran and left the question open is a genuine
    # state of the world and does not belong here.
    non_informative: tuple[str, ...] = ()
    # BRANCH only: an opaque capability token the caller decides is available or not, and how the
    # branch is settled at all. A measurement and "find a component nobody has described" are not
    # the same kind of work, and pricing them alike is the one way this search could mislead.
    requires: str | None = None
    resolves_by: str = MEASUREMENT
    # ALL_OF only.
    members: tuple[str, ...] = ()
    # TERMINAL only.
    role: str | None = None
    # TERMINAL only: a closure this terminal declares, as (scope, subject). Scope is opaque to the
    # engine; `state.py` applies it. Carried here because it is a property of the end state.
    closes: tuple[str, str] | None = None

    @property
    def outcome_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.outcomes)

    def outcome_target(self, name: str) -> str:
        for candidate, target in self.outcomes:
            if candidate == name:
                return target
        raise GraphError(f"{self.id} has no outcome {name!r}")


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""
    # A deliberate loop back to an earlier state. Excluded from the acyclicity check and from the
    # forward relaxation, because re-entry is a modelling device for "this can be revisited", not a
    # route that shortens anything.
    reentry: bool = False


@dataclass(frozen=True)
class PolicyGraph:
    nodes: dict[str, Node]
    edges: tuple[Edge, ...]
    root: str
    goal: str
    # Capability tokens treated as available. A branch requiring anything outside this set is not a
    # runnable action; see `actions.py`. Empty means nothing is gated.
    available_requirements: frozenset[str] = frozenset()
    _out: dict[str, tuple[Edge, ...]] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        out: dict[str, list[Edge]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            out[edge.source].append(edge)
        object.__setattr__(self, "_out", {k: tuple(v) for k, v in out.items()})

    # ---------------------------------------------------------------- construction

    @classmethod
    def build(cls, *, nodes: Iterable[Node], edges: Iterable[Edge], root: str, goal: str,
              available_requirements: Iterable[str] = ()) -> PolicyGraph:
        """Validate and freeze. Integrity only — whether the graph is *true* is not our business."""
        ordered: dict[str, Node] = {}
        for node in nodes:
            if node.id in ordered:
                raise GraphError(f"duplicate node id {node.id!r}")
            if node.kind not in NODE_KINDS:
                raise GraphError(f"{node.id}: unknown kind {node.kind!r}")
            ordered[node.id] = Node(
                id=node.id, kind=node.kind, label=node.label,
                outcomes=tuple(sorted(node.outcomes)), requires=node.requires,
                resolves_by=node.resolves_by, members=tuple(node.members),
                role=node.role, closes=node.closes,
                non_informative=tuple(sorted(node.non_informative)),
            )
        problems: list[str] = []
        for node in ordered.values():
            if node.kind == BRANCH:
                if not node.outcomes:
                    problems.append(f"{node.id}: a branch with no outcomes is not a branch")
                for name, target in node.outcomes:
                    if target not in ordered:
                        problems.append(f"{node.id}.{name} -> unknown node {target!r}")
            elif node.kind == ALL_OF:
                if not node.members:
                    problems.append(f"{node.id}: an all_of with no members is vacuously true")
                for member in node.members:
                    if member not in ordered:
                        problems.append(f"{node.id} requires unknown node {member!r}")
            elif node.kind == TERMINAL:
                if node.role not in TERMINAL_ROLES:
                    problems.append(f"{node.id}: terminal role {node.role!r} is not one of "
                                    f"{', '.join(TERMINAL_ROLES)}")
            if node.outcomes and node.kind != BRANCH:
                problems.append(f"{node.id}: only a branch may carry outcomes")
            for name in node.non_informative:
                if name not in node.outcome_names:
                    problems.append(f"{node.id}: non-informative outcome {name!r} is not an outcome")
            if node.kind == BRANCH and node.outcomes and len(node.non_informative) == len(node.outcomes):
                problems.append(f"{node.id}: every outcome is non-informative, so it can never resolve")
        frozen_edges = tuple(edges)
        for edge in frozen_edges:
            if edge.source not in ordered:
                problems.append(f"edge from unknown node {edge.source!r}")
            elif edge.target not in ordered:
                problems.append(f"edge to unknown node {edge.target!r}")
        for name, nid in (("root", root), ("goal", goal)):
            if nid not in ordered:
                problems.append(f"{name} {nid!r} is not a node in the graph")
        if problems:
            raise GraphError("; ".join(sorted(problems)))
        graph = cls(nodes=ordered, edges=frozen_edges, root=root, goal=goal,
                    available_requirements=frozenset(available_requirements))
        if cycles := graph.cycles():
            raise GraphError(f"cycle through non-reentry edges: {cycles[0]}")
        return graph

    # ---------------------------------------------------------------- views

    def out_edges(self, nid: str, *, follow_reentry: bool = False) -> tuple[Edge, ...]:
        return tuple(e for e in self._out.get(nid, ()) if follow_reentry or not e.reentry)

    def successors(self, nid: str, *, follow_reentry: bool = False) -> tuple[str, ...]:
        """Where this node can lead. A branch leaves only by its outcomes."""
        node = self.nodes[nid]
        if node.kind == BRANCH:
            return tuple(target for _, target in node.outcomes)
        return tuple(e.target for e in self.out_edges(nid, follow_reentry=follow_reentry))

    def branches(self) -> tuple[Node, ...]:
        return tuple(n for n in self.nodes.values() if n.kind == BRANCH)

    def branch_ids(self) -> tuple[str, ...]:
        return tuple(sorted(n.id for n in self.nodes.values() if n.kind == BRANCH))

    def terminals_with_role(self, role: str) -> tuple[str, ...]:
        return tuple(sorted(n.id for n in self.nodes.values()
                            if n.kind == TERMINAL and n.role == role))

    def role_of(self, nid: str) -> str | None:
        node = self.nodes.get(nid)
        return node.role if node is not None and node.kind == TERMINAL else None

    def is_available(self, nid: str) -> bool:
        """Whether this branch's required capability is one the caller declared available."""
        requires = self.nodes[nid].requires
        return requires is None or requires in self.available_requirements

    def with_requirements(self, available: Iterable[str]) -> PolicyGraph:
        return PolicyGraph(nodes=self.nodes, edges=self.edges, root=self.root, goal=self.goal,
                           available_requirements=frozenset(available))

    def cycles(self) -> list[str]:
        """Acyclic once deliberate re-entry edges are dropped; anything else is a modelling error.

        Iterative, because the recursive form overflows Python's stack on a graph of this size and
        a validator that dies of recursion has reported nothing.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        colour = dict.fromkeys(self.nodes, WHITE)
        found: list[str] = []
        for root in sorted(self.nodes):
            if colour[root] != WHITE:
                continue
            stack: list[tuple[str, tuple[str, ...]]] = [(root, ())]
            while stack:
                nid, path = stack.pop()
                if nid == "":                                    # post-order marker
                    colour[path[0]] = BLACK
                    continue
                if colour[nid] == GREY:
                    continue
                colour[nid] = GREY
                stack.append(("", (nid,)))
                for nxt in self.successors(nid):
                    if colour[nxt] == GREY:
                        found.append(" -> ".join(path + (nid, nxt)))
                    elif colour[nxt] == WHITE:
                        stack.append((nxt, path + (nid,)))
        return sorted(set(found))

    def _forward(self) -> dict[str, tuple[str, ...]]:
        """Who leads into whom, counting conjunction membership.

        A member of an ``ALL_OF`` leads to that conjunction, because establishing the member is a
        step toward establishing it. Without that, every conjunct looks like a dead end and the
        target becomes unreachable from everything that feeds it.
        """
        if "_forward_cache" not in self.__dict__:
            forward: dict[str, list[str]] = {nid: [] for nid in self.nodes}
            for nid in self.nodes:
                forward[nid].extend(self.successors(nid, follow_reentry=True))
            for node in self.nodes.values():
                if node.kind == ALL_OF:
                    for member in node.members:
                        forward[member].append(node.id)
            object.__setattr__(self, "_forward_cache",
                               {k: tuple(sorted(set(v))) for k, v in forward.items()})
        return self.__dict__["_forward_cache"]

    def ancestors_of(self, destination: str) -> frozenset[str]:
        """Every node from which `destination` can still be reached, plus itself.

        This is what makes the search affordable. The frontier of a node cannot be affected by a
        node that leads nowhere near it, so restricting the relaxation to this set is exact rather
        than approximate — and on the real map it is the difference between twenty-one seconds and
        a few milliseconds, because the organism-scale conjunction downstream of the cellular
        target contributes a thousand incomparable sets that the cellular answer never consults.
        """
        if "_ancestor_cache" not in self.__dict__:
            object.__setattr__(self, "_ancestor_cache", {})
        cache = self.__dict__["_ancestor_cache"]
        if destination not in cache:
            forward = self._forward()
            reverse: dict[str, list[str]] = {nid: [] for nid in self.nodes}
            for source, targets in forward.items():
                for target in targets:
                    reverse[target].append(source)
            seen = {destination}
            stack = [destination]
            while stack:
                nid = stack.pop()
                for previous in reverse.get(nid, ()):
                    if previous not in seen:
                        seen.add(previous)
                        stack.append(previous)
            cache[destination] = frozenset(seen)
        return cache[destination]

    def reaches(self, source: str, destination: str) -> bool:
        return source in self.ancestors_of(destination)

    def target_relevant_branches(self, destination: str | None = None) -> tuple[str, ...]:
        """Branches at least one of whose outcomes can still lead to the destination.

        Resolving anything else cannot help: an outcome only ever *removes* routes, so settling a
        branch the goal does not depend on can lower the chance of reaching it and can never raise
        it. Restricting the action space to these is therefore sound as well as necessary — the
        full branch set makes the horizon-6 search intractable.
        """
        ancestors = self.ancestors_of(destination or self.goal)
        return tuple(sorted(n.id for n in self.branches() if n.id in ancestors))
