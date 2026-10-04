"""Reachability under hard safety constraints, on a finite state-transition system.

Semantics, chosen deliberately:

* **Asynchronous causal updates, all interleavings.** With controls held, any relationship whose
  output disagrees with its function may fire. Biology chooses the order, not us, so every
  reachable state under every interleaving is explored. A step is safe only if *none* of them is
  unsafe. Finding one path that happens to avoid the unsafe region would not be a control
  guarantee.
* **Attractors, not single paths.** After a step, the system is wherever its terminal strongly
  connected components are. The belief is the union of those states over every possible starting
  state.
* **Controls accumulate.** A strategy adds controls and holds them. Release is not modelled:
  exogenous variables have no restoring dynamics here, and allowing release would let a transient
  control lock in an effect that no mechanism maintains.
* **Determinism.** Every collection that reaches an output is sorted. Iterating a set of string
  tuples gives a different order in every process under hash randomisation; that is how a "fixed"
  result stops being reproducible.

Graph traversal and Tarjan's algorithm are implemented here directly. They are standard
algorithms, not a numerical solver.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable

from rarepipe.stages.control.controls import ControlVariable
from rarepipe.stages.control.state_space import State, StateSpace
from rarepipe.stages.control.uncertainty import Variant

Predicate = Callable[[State], bool]


@dataclass(frozen=True)
class Rule:
    relationship_id: str
    output: int
    inputs: tuple[int, ...]
    lookup: dict


@dataclass(frozen=True)
class Compiled:
    space: StateSpace
    rules: tuple[Rule, ...]


def compile_variant(space: StateSpace, variant: Variant) -> Compiled:
    rules = tuple(
        Rule(fn.relationship_id, space.index(fn.output),
             tuple(space.index(i) for i in fn.inputs), fn.lookup())
        for fn in sorted(variant.functions, key=lambda f: f.relationship_id)
    )
    return Compiled(space, rules)


def _successors(c: Compiled, state: State, pinned: frozenset[int]) -> list[tuple[str, State]]:
    out = []
    for rule in c.rules:
        if rule.output in pinned:
            continue
        value = rule.lookup[tuple(state[i] for i in rule.inputs)]
        if state[rule.output] != value:
            nxt = list(state)
            nxt[rule.output] = value
            out.append((rule.relationship_id, tuple(nxt)))
    return out


def apply_controls(space: StateSpace, state: State, controls: tuple[ControlVariable, ...]) -> State:
    nxt = list(state)
    for control in controls:
        nxt[space.index(control.sets)] = control.to
    return tuple(nxt)


@dataclass(frozen=True)
class Exploration:
    reachable: tuple[State, ...]
    attractors: tuple[State, ...]
    fired: tuple[str, ...]
    unsafe_path: tuple[State, ...] = ()


def _terminal_sccs(nodes: list[State], edges: dict[State, list[State]]) -> list[State]:
    """States in terminal strongly connected components (iterative Tarjan)."""
    index: dict[State, int] = {}
    low: dict[State, int] = {}
    on_stack: set[State] = set()
    stack: list[State] = []
    comp_of: dict[State, int] = {}
    comps: list[list[State]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, i = work[-1]
            succ = edges.get(node, [])
            if i < len(succ):
                work[-1] = (node, i + 1)
                nxt = succ[i]
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    comp = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        comp_of[member] = len(comps)
                        comp.append(member)
                        if member == node:
                            break
                    comps.append(comp)
    terminal: list[State] = []
    for k, comp in enumerate(comps):
        if all(comp_of[n] == k for member in comp for n in edges.get(member, [])):
            terminal.extend(comp)
    return sorted(terminal)


def explore(c: Compiled, start: State, pinned: frozenset[int], unsafe: Predicate) -> Exploration:
    """Every state reachable under every interleaving, stopping at the first unsafe one found."""
    if unsafe(start):
        return Exploration((start,), (), (), (start,))
    parent: dict[State, State | None] = {start: None}
    edges: dict[State, list[State]] = {}
    fired: set[str] = set()
    queue = deque([start])
    while queue:
        state = queue.popleft()
        succ = _successors(c, state, pinned)
        edges[state] = [s for _, s in succ]
        for rid, nxt in succ:
            fired.add(rid)
            if nxt in parent:
                continue
            parent[nxt] = state
            if unsafe(nxt):
                path = [nxt]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])
                return Exploration((), (), tuple(sorted(fired)), tuple(reversed(path)))
            queue.append(nxt)
    nodes = sorted(parent)
    return Exploration(tuple(nodes), tuple(_terminal_sccs(nodes, edges)), tuple(sorted(fired)))


Step = tuple[str, ...]
Strategy = tuple[Step, ...]


@dataclass(frozen=True)
class Outcome:
    status: str  # SUCCESS | UNSAFE | NO_TARGET
    final_belief: tuple[State, ...] = ()
    fired: tuple[str, ...] = ()
    unsafe_step: int | None = None
    unsafe_path: tuple[State, ...] = ()
    unsafe_from: State | None = None
    visited: tuple[State, ...] = ()


def run_strategy(c: Compiled, x0: tuple[State, ...], strategy: Strategy,
                 controls: dict[str, ControlVariable], target: Predicate,
                 unsafe: Predicate) -> Outcome:
    if not x0:
        raise ValueError("an empty initial-state set makes every strategy vacuously succeed; "
                         "exclude the variant instead")
    belief = tuple(sorted(x0))
    held: list[str] = []
    fired: set[str] = set()
    visited: set[State] = set()
    for k, added in enumerate(strategy):
        held.extend(added)
        active = tuple(controls[cid] for cid in sorted(held))
        pinned = frozenset(c.space.index(ctl.sets) for ctl in active)
        landed: set[State] = set()
        for state in belief:
            ex = explore(c, apply_controls(c.space, state, active), pinned, unsafe)
            if ex.unsafe_path:
                return Outcome("UNSAFE", fired=tuple(sorted(fired | set(ex.fired))),
                               unsafe_step=k, unsafe_path=ex.unsafe_path, unsafe_from=state,
                               visited=tuple(sorted(visited)))
            landed.update(ex.attractors)
            visited.update(ex.reachable)
            fired.update(ex.fired)
        belief = tuple(sorted(landed))
    status = "SUCCESS" if all(target(s) for s in belief) else "NO_TARGET"
    return Outcome(status, belief, tuple(sorted(fired)), visited=tuple(sorted(visited)))


@dataclass
class SearchResult:
    successes: list[Strategy] = field(default_factory=list)
    rejected: list[tuple[Strategy, Outcome]] = field(default_factory=list)


def _subsets(items: list[str]) -> list[Step]:
    return [tuple(combo) for size in range(1, len(items) + 1)
            for combo in combinations(items, size)]


def search(c: Compiled, x0: tuple[State, ...], controls: dict[str, ControlVariable],
           target: Predicate, unsafe: Predicate, max_depth: int) -> SearchResult:
    """Breadth-first over strategies; success and unsafe nodes are not extended."""
    result = SearchResult()
    frontier: list[Strategy] = [()]
    seen: set[tuple[frozenset[str], tuple[State, ...]]] = {(frozenset(), tuple(sorted(x0)))}
    all_ids = sorted(controls)
    for _ in range(max_depth):
        nxt: list[Strategy] = []
        for strategy in frontier:
            held = {cid for step in strategy for cid in step}
            for added in _subsets([cid for cid in all_ids if cid not in held]):
                candidate = strategy + (added,)
                outcome = run_strategy(c, x0, candidate, controls, target, unsafe)
                if outcome.status == "UNSAFE":
                    result.rejected.append((candidate, outcome))
                elif outcome.status == "SUCCESS":
                    result.successes.append(candidate)
                else:
                    key = (frozenset(held | set(added)), outcome.final_belief)
                    if key not in seen:
                        seen.add(key)
                        nxt.append(candidate)
        frontier = nxt
    return result
