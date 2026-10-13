"""Conditional reachability: the minimal sets of branches that would establish each node.

This is the *structural* question — does a route exist at all, if the branches fall a particular
way — and it is deliberately separate from two others the engine answers elsewhere:

* **Availability** is not consulted here. Whether we can run an experiment today is a fact about
  our capabilities, not about whether the graph contains a route. Mixing them would make a route
  vanish from the map the moment a model organism became unavailable, which is the wrong report.
  Availability constrains the *action space* (`actions.py`), not the structure.
* **Robustness** is not inferred from this. A node reachable along some favourable assignment of
  outcomes may be unreachable under others; that search lives in `robust_policy.py`.

Sets, never counts. Two routes that share an experiment do not cost two experiments, and summing
them invents work that does not exist. Incomparable minimal sets are all kept, because keeping only
the smallest per node discards the set that makes a downstream conjunction cheap and then reports a
distance that is too large.

**On truncation.** An earlier implementation of this computation elsewhere in the repository capped
candidate sets per node at eight to bound the cross-product at conjunctions. That cap was invisible
in the output, which matters because "enumerate every tied optimum" is a correctness property here:
a silently truncated frontier reports one minimal route where four exist. This version defaults to
no cap, and when a caller sets one the affected nodes are named in ``truncated`` so the limit is a
reported fact rather than a hidden one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rarepipe.stages.control.policy.graph import ALL_OF, BRANCH, PolicyGraph

# A frontier entry is a set of branch ids that, once resolved favourably, establishes the node.
BranchSet = frozenset[str]


@dataclass(frozen=True)
class Frontier:
    """Minimal branch-sets per node, plus any node where a cap hid alternatives."""
    sets: dict[str, tuple[BranchSet, ...]]
    truncated: frozenset[str] = frozenset()

    def for_node(self, nid: str) -> tuple[BranchSet, ...]:
        return self.sets.get(nid, ())

    def establishable(self, nid: str) -> bool:
        return bool(self.sets.get(nid))

    def minimal_size(self, nid: str) -> int | None:
        sets = self.sets.get(nid)
        return min(len(s) for s in sets) if sets else None

    def tied_minimal(self, nid: str) -> tuple[BranchSet, ...]:
        """Every minimal set of the smallest size — the tied optima, all of them.

        Returning one of these as "the" shortest route is the specific overstatement this method
        exists to prevent.
        """
        sets = self.sets.get(nid)
        if not sets:
            return ()
        smallest = min(len(s) for s in sets)
        return tuple(sorted((s for s in sets if len(s) == smallest), key=lambda s: sorted(s)))

    def relevant_branches(self, nid: str) -> frozenset[str]:
        """Every branch appearing in any minimal set for this node."""
        return frozenset().union(*self.sets.get(nid, ())) if self.sets.get(nid) else frozenset()


def _prune(candidates: list[BranchSet], cap: int | None) -> tuple[tuple[BranchSet, ...], bool]:
    """Keep only minimal sets. A set containing another is never a better route."""
    kept: list[BranchSet] = []
    for candidate in sorted(set(candidates), key=lambda s: (len(s), sorted(s))):
        size = len(candidate)
        # `kept` is in non-decreasing size order, so a kept set larger than this candidate cannot
        # be a subset of it and neither can anything after it. Stopping there turns the dominant
        # cost of this function from quadratic in the whole list into quadratic in its short prefix.
        dominated = False
        for existing in kept:
            if len(existing) > size:
                break
            if existing <= candidate:
                dominated = True
                break
        if not dominated:
            kept.append(candidate)
    if cap is not None and len(kept) > cap:
        return tuple(kept[:cap]), True
    return tuple(kept), False


def _dependency_order(nodes: dict, incoming: dict[str, list[tuple[str, bool]]]) -> list[str]:
    """Node ids with sources before the nodes that depend on them, so one sweep does most of the work.

    The graph is a DAG once re-entry edges are set aside, so a topological sweep reaches a fixed
    point in about two passes instead of the dozen a fixed order needs. Nodes left over by a cycle
    are appended in sorted order, which keeps the result deterministic without needing the cycle to
    be absent.
    """
    remaining = {nid: {src for src, _ in incoming[nid] if src in nodes} for nid in nodes}
    dependents: dict[str, list[str]] = {nid: [] for nid in nodes}
    for nid, sources in remaining.items():
        for source in sources:
            dependents[source].append(nid)
    ready = sorted(nid for nid, sources in remaining.items() if not sources)
    order: list[str] = []
    seen: set[str] = set()
    while ready:
        nid = ready.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        order.append(nid)
        for dependent in sorted(dependents[nid]):
            remaining[dependent].discard(nid)
            if not remaining[dependent] and dependent not in seen:
                ready.append(dependent)
    order.extend(sorted(nid for nid in nodes if nid not in seen))
    return order


@dataclass(frozen=True)
class _Relaxation:
    """The boolean relaxation's fixed structure, compiled once per (graph, destination).

    Only the ``decided`` mask varies between calls, so rebuilding the edge lists on each one — as a
    direct transcription of ``frontier`` does — spends almost all of its time re-deriving something
    constant. Indices rather than identifiers for the same reason: the search runs this hundreds of
    times per state it visits, and the constant factor is the whole budget.
    """
    index: dict[str, int]
    order: tuple[int, ...]
    is_conjunction: tuple[bool, ...]
    members: tuple[tuple[int, ...], ...]
    # Per node: incoming arrivals as (source, charged, branch, outcome). ``branch`` is -1 for an
    # ordinary edge; otherwise the arrival exists only while that branch may still return that
    # outcome.
    arrivals: tuple[tuple[tuple[int, bool, int, int], ...], ...]
    # Who must be re-examined when a node moves; the worklist's successor relation.
    dependents: tuple[tuple[int, ...], ...]
    root: int
    destination: int
    branch_outcome_index: dict[tuple[str, str], int]


def _compile_relaxation(graph: PolicyGraph, destination: str) -> _Relaxation | None:
    scope = graph.ancestors_of(destination)
    ids = [nid for nid in graph.nodes if nid in scope]
    if destination not in scope or graph.root not in scope:
        return None
    index = {nid: i for i, nid in enumerate(ids)}
    arrivals: list[list[tuple[int, bool, int, int]]] = [[] for _ in ids]
    outcome_index: dict[tuple[str, str], int] = {}
    for nid in ids:
        node = graph.nodes[nid]
        if node.kind != BRANCH:
            continue
        for position, (name, target) in enumerate(node.outcomes):
            outcome_index[(nid, name)] = position
            if target in index:
                arrivals[index[target]].append((index[nid], True, index[nid], position))
    for edge in graph.edges:
        if edge.source not in index or edge.target not in index:
            continue
        if graph.nodes[edge.source].kind == BRANCH:
            continue                      # a branch is left only by its outcomes
        arrivals[index[edge.target]].append((index[edge.source], False, -1, -1))

    incoming = {nid: [(ids[a[0]], a[1]) for a in arrivals[index[nid]]] for nid in ids}
    order = tuple(index[nid] for nid in _dependency_order({nid: None for nid in ids}, incoming))
    dependents: list[set[int]] = [set() for _ in ids]
    for position, nid in enumerate(ids):
        for arrival in arrivals[position]:
            dependents[arrival[0]].add(position)
        if graph.nodes[nid].kind == ALL_OF:
            for member in graph.nodes[nid].members:
                if member in index:
                    dependents[index[member]].add(position)
    return _Relaxation(
        index=index, order=order,
        is_conjunction=tuple(graph.nodes[nid].kind == ALL_OF for nid in ids),
        members=tuple(tuple(index[m] for m in graph.nodes[nid].members if m in index)
                      if graph.nodes[nid].kind == ALL_OF else () for nid in ids),
        arrivals=tuple(tuple(a) for a in arrivals),
        dependents=tuple(tuple(sorted(d)) for d in dependents),
        root=index[graph.root], destination=index[destination],
        branch_outcome_index=outcome_index,
    )


def _relaxation_for(graph: PolicyGraph, destination: str) -> _Relaxation | None:
    if "_relaxation_cache" not in graph.__dict__:
        object.__setattr__(graph, "_relaxation_cache", {})
    cache = graph.__dict__["_relaxation_cache"]
    if destination not in cache:
        cache[destination] = _compile_relaxation(graph, destination)
    return cache[destination]


def can_establish(graph: PolicyGraph, *, known: frozenset[str] = frozenset(),
                  decided: Mapping[str, str] | None = None,
                  destination: str | None = None) -> tuple[bool, bool]:
    """``(establishable, established)`` for the destination, without tracking any branch sets.

    The same relaxation as ``frontier``, carrying two bits per node instead of a list of sets. The
    search asks only these two questions of the thousands of states it visits, and tracking minimal
    sets to answer them costs orders of magnitude more — the set-based frontier is for reports,
    where there is one call and the sets are the point.

    ``tests/test_policy_reachability.py`` asserts the two never disagree, which is what licenses
    using the cheap one in the recursion.
    """
    destination = destination or graph.goal
    compiled = _relaxation_for(graph, destination)
    if compiled is None:
        return False, False
    decided = dict(decided or {})

    # Which (branch, outcome) arrivals survive: a decided branch returned one result, so its other
    # outcomes are not merely uncosted but unavailable, and it stops being charged as outstanding.
    chosen: dict[int, int] = {}
    for branch, outcome in decided.items():
        position = compiled.branch_outcome_index.get((branch, outcome))
        if position is not None and branch in compiled.index:
            chosen[compiled.index[branch]] = position

    size = len(compiled.order)
    possible = bytearray(size)
    done = bytearray(size)
    seeds = {compiled.root} | {compiled.index[n] for n in known if n in compiled.index}
    for seed in seeds:
        possible[seed] = done[seed] = 1

    def evaluate(nid: int) -> bool:
        """Recompute one node. Returns whether anything moved."""
        if compiled.is_conjunction[nid]:
            members = compiled.members[nid]
            new_possible = bool(members) and all(possible[m] for m in members)
            new_done = bool(members) and all(done[m] for m in members)
        else:
            new_possible = new_done = False
            for source, charged, branch, outcome in compiled.arrivals[nid]:
                if branch >= 0:
                    decided_outcome = chosen.get(branch)
                    if decided_outcome is not None:
                        if decided_outcome != outcome:
                            continue           # that result did not come back
                        charged = False        # already run; stop charging for it
                if possible[source]:
                    new_possible = True
                    if done[source] and not charged:
                        new_done = True
                        break
        # Both bits are monotone: a source never stops being reachable, so neither bit can go
        # back to false. Making that explicit is what bounds the worklist — each node can move
        # at most twice, so the propagation terminates without needing a sweep counter.
        changed = False
        if new_possible and not possible[nid]:
            possible[nid] = 1
            changed = True
        if new_done and not done[nid]:
            done[nid] = 1
            changed = True
        return changed

    # One pass in dependency order settles almost everything, because the graph is a DAG but for
    # its re-entry edges. What a pass leaves unsettled propagates along a worklist rather than by
    # re-sweeping all of the nodes to find the handful that moved.
    moved: list[int] = []
    for nid in compiled.order:
        if nid not in seeds and evaluate(nid):
            moved.append(nid)
    pending = {d for nid in moved for d in compiled.dependents[nid] if d not in seeds}
    while pending:
        nid = pending.pop()
        if evaluate(nid):
            pending.update(d for d in compiled.dependents[nid] if d not in seeds)
    return bool(possible[compiled.destination]), bool(done[compiled.destination])


def frontier(graph: PolicyGraph, *, known: frozenset[str] = frozenset(),
             decided: Mapping[str, str] | None = None, drop: str | None = None,
             max_sets: int | None = None, destination: str | None = None) -> Frontier:
    """For every node, the minimal sets of branches that would establish it from the root.

    Forward relaxation rather than backward search, because a conjunction's members are
    preconditions to be established, not waypoints with their own onward path: the backward form
    calls the goal unreachable whenever a conjunct sits on the chain feeding it.

    ``decided`` is a branch that has already returned a result. Two things follow, and both matter.
    The branch is restricted to that one outcome, because a branch returns one result and its other
    outcomes are not merely uncosted but unavailable — without this a negative result never closes
    the family it rules out. And it stops being charged as outstanding work, or "what remains after
    this result" keeps billing for the experiment that produced the result.

    ``destination`` restricts the relaxation to the nodes from which that node can still be reached.
    The restriction is exact, not a heuristic: a node that leads nowhere near the destination cannot
    change its frontier. Omitting it computes every node's frontier, which is what reproducing a
    whole-map report needs and what makes a single call expensive.
    """
    decided = dict(decided or {})
    scope = graph.ancestors_of(destination) if destination is not None else None
    nodes = {
        nid: node for nid, node in graph.nodes.items()
        if nid != drop and (scope is None or nid in scope)
    }

    # Who can establish whom, and whether arriving that way costs the branch.
    incoming: dict[str, list[tuple[str, bool]]] = {nid: [] for nid in nodes}
    for node in nodes.values():
        if node.kind != BRANCH:
            continue
        outcomes = node.outcomes
        if node.id in decided:
            outcomes = tuple((n, t) for n, t in outcomes if n == decided[node.id])
        charge = node.id not in decided
        for _, target in outcomes:
            if target in nodes:
                incoming[target].append((node.id, charge))
    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            continue
        if nodes[edge.source].kind == BRANCH:
            continue                      # a branch is left only by its outcomes
        # Re-entry edges *are* followed here. This is a forward relaxation to a fixed point, so a
        # cycle costs nothing and converges; and a re-entry edge is a real statement that the earlier
        # state can be returned to. They are excluded from the acyclicity check instead, which is
        # where they would otherwise be mistaken for a modelling error.
        incoming[edge.target].append((edge.source, False))

    best: dict[str, tuple[BranchSet, ...]] = {nid: () for nid in nodes}
    truncated: set[str] = set()
    for seed in (graph.root, *sorted(known)):
        if seed in best:
            best[seed] = (frozenset(),)

    # Relaxation to a fixed point, sweeping in dependency order so that most nodes are final after
    # the first pass. The bound is a guard against a malformed graph, not the expected number of
    # rounds; convergence is detected and breaks out first.
    order = _dependency_order(nodes, incoming)
    for _ in range(len(nodes) + 2):
        changed = False
        for nid in order:
            node = nodes[nid]
            if nid == graph.root or nid in known:
                continue
            if node.kind == ALL_OF:
                combos: list[BranchSet] = [frozenset()]
                for member in node.members:
                    member_sets = best.get(member) or ()
                    if not member_sets:
                        combos = []
                        break
                    merged, hit = _prune([c | m for c in combos for m in member_sets], max_sets)
                    combos = list(merged)
                    if hit:
                        truncated.add(nid)
                candidates, hit = _prune(combos, max_sets)
            else:
                candidates, hit = _prune(
                    [s | ({src} if charged else set())
                     for src, charged in incoming[nid]
                     for s in best.get(src) or ()],
                    max_sets,
                )
            if hit:
                truncated.add(nid)
            if candidates != best[nid]:
                best[nid] = candidates
                changed = True
        if not changed:
            break
    return Frontier(sets=best, truncated=frozenset(truncated))


def minimum_branches(graph: PolicyGraph, *, known: frozenset[str] = frozenset(),
                     decided: Mapping[str, str] | None = None,
                     destination: str | None = None) -> int | None:
    """A floor on how many more branches must be resolved. ``None`` if the destination is closed.

    Admissible, which is the whole point: it may understate the real distance but must never
    overstate it, because the search uses it to prune subtrees that cannot finish inside the
    remaining horizon and an overstatement would discard a real policy.

    ``min`` at a disjunction, because any one incoming route suffices. ``max`` at a conjunction,
    because a union is at least as large as its largest part — ``sum`` would be the exact answer
    only if the members shared no branches, and assuming that is how a bound stops being a bound.
    The exact answer needs the minimal *sets*, which is what ``frontier`` is for and what this
    function exists to avoid computing.
    """
    destination = destination or graph.goal
    compiled = _relaxation_for(graph, destination)
    if compiled is None:
        return None
    decided = dict(decided or {})
    chosen: dict[int, int] = {}
    for branch, outcome in decided.items():
        position = compiled.branch_outcome_index.get((branch, outcome))
        if position is not None and branch in compiled.index:
            chosen[compiled.index[branch]] = position

    size = len(compiled.order)
    infinity = size + 1
    cost = [infinity] * size
    seeds = {compiled.root} | {compiled.index[n] for n in known if n in compiled.index}
    for seed in seeds:
        cost[seed] = 0

    def evaluate(nid: int) -> bool:
        if compiled.is_conjunction[nid]:
            members = compiled.members[nid]
            value = max((cost[m] for m in members), default=infinity) if members else infinity
        else:
            value = infinity
            for source, charged, branch, outcome in compiled.arrivals[nid]:
                if branch >= 0:
                    decided_outcome = chosen.get(branch)
                    if decided_outcome is not None:
                        if decided_outcome != outcome:
                            continue
                        charged = False
                if cost[source] < infinity:
                    value = min(value, cost[source] + (1 if charged else 0))
        if value < cost[nid]:
            cost[nid] = value
            return True
        return False

    moved = [nid for nid in compiled.order if nid not in seeds and evaluate(nid)]
    pending = {d for nid in moved for d in compiled.dependents[nid] if d not in seeds}
    while pending:
        nid = pending.pop()
        if evaluate(nid):
            pending.update(d for d in compiled.dependents[nid] if d not in seeds)
    result = cost[compiled.destination]
    return None if result >= infinity else result


def conditionally_reachable(graph: PolicyGraph, *, known: frozenset[str] = frozenset(),
                            decided: Mapping[str, str] | None = None,
                            destination: str | None = None) -> bool:
    destination = destination or graph.goal
    return frontier(graph, known=known, decided=decided,
                    destination=destination).establishable(destination)


def blocking_outcomes(graph: PolicyGraph, destination: str | None = None) -> tuple[tuple[str, str], ...]:
    """Single outcomes that make `destination` unreachable: SINGLE_OUTCOME_RESILIENCE.

    One branch is perturbed at a time. An empty result means no *single* admissible result closes
    the destination, which is a strictly weaker claim than robust reachability and must never be
    reported as it — that conflation is exactly what `robust_policy.py` exists to replace.
    """
    destination = destination or graph.goal
    out: list[tuple[str, str]] = []
    for node in graph.branches():
        for name in node.outcome_names:
            # A boolean question, so it gets the boolean relaxation. Asking it with minimal sets
            # costs two hundred times more and throws the sets away.
            establishable, _ = can_establish(graph, decided={node.id: name},
                                             destination=destination)
            if not establishable:
                out.append((node.id, name))
    return tuple(sorted(out))


def dominators(graph: PolicyGraph, destination: str | None = None) -> tuple[str, ...]:
    """Branches every route must pass through, tested by deletion.

    Deletion is the honest test and it needs no probability: remove the branch and ask whether the
    destination can still be established.
    """
    destination = destination or graph.goal
    if not frontier(graph, destination=destination).establishable(destination):
        return ()
    return tuple(sorted(
        node.id for node in graph.branches()
        if not frontier(graph, drop=node.id, destination=destination).establishable(destination)
    ))
