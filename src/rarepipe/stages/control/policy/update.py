"""UPDATE(K, action, observation) → K', and the predicates the search asks of a state.

Deterministic. No probability is needed to make this transition, and none is used.

**What may close an actuator.** Only an explicit per-arm result. When a campaign with three
independent arms returns a joint outcome saying the population was harmed, the engine does *not*
guess which arm did the harm, because it cannot: attributing it would invent a closure, and that
invented closure would then close a control variable that three separate mechanisms still reach.
So planning-time outcomes close nothing, and a real bench result closes exactly the arms it names.

Terminals that *declare* a closure scope are reported rather than applied, for the same reason.
A terminal saying "this closes an actuator for control variable X" does not say which actuator, and
the engine will not pick one. The declaration is surfaced as a finding for a human to attribute.
"""
from __future__ import annotations

from dataclasses import replace

from rarepipe.stages.control.policy.actions import Action
from rarepipe.stages.control.policy.graph import TERMINAL, UNSAFE, PolicyGraph
from rarepipe.stages.control.policy.reachability import Frontier, frontier
from rarepipe.stages.control.policy.state import KnowledgeState, Observation, StateError


def update(graph: PolicyGraph, state: KnowledgeState, action: Action,
           observation: Observation) -> KnowledgeState:
    """Fold one observation into the knowledge state.

    Re-deciding a branch is rejected rather than overwritten. A branch returns one result; a second,
    different result for the same branch means either the caller is replaying history wrongly or the
    experiment was repeated, and silently taking the newer answer would make the state depend on
    arrival order — which is exactly what the canonical form exists to prevent.
    """
    if observation.action_id != action.id:
        raise StateError(f"observation is for {observation.action_id!r}, not {action.id!r}")
    resolved = state.resolved
    for branch, outcome in observation.results:
        node = graph.nodes.get(branch)
        if node is None:
            raise StateError(f"{observation.action_id}: {branch!r} is not a node in the graph")
        if branch not in action.resolves:
            raise StateError(f"{action.id} does not resolve {branch!r}")
        if outcome not in node.outcome_names:
            raise StateError(f"{branch} has no outcome {outcome!r}")
        if branch in resolved and resolved[branch] != outcome:
            raise StateError(
                f"{branch} already returned {resolved[branch]!r}; refusing to overwrite with "
                f"{outcome!r}. A branch returns one result.")

    decided = dict(state.decided)
    decided.update(observation.results)

    actuators = {a.actuator: a for a in state.actuators}
    for actuator, status in observation.arm_updates:
        existing = actuators.get(actuator)
        if existing is None:
            raise StateError(f"{actuator!r} is not in the actuator registry; seed it before use")
        actuators[actuator] = replace(existing, status=status)

    return KnowledgeState(
        decided=tuple(sorted(decided.items())),
        established=state.established,
        actuators=tuple(sorted(actuators.values())),
        history=state.history + (action.id,),
    )


def establish(state: KnowledgeState, nodes: frozenset[str]) -> KnowledgeState:
    """Take extra nodes as reached, without attributing them to an action.

    Used to seed a partial state — an episode, or knowledge that arrived outside this graph.
    """
    return replace(state, established=state.established | nodes)


# ---------------------------------------------------------------- predicates on a state


def state_frontier(graph: PolicyGraph, state: KnowledgeState, *,
                   destination: str | None = None, **kwargs) -> Frontier:
    return frontier(graph, known=state.established, decided=state.resolved,
                    destination=destination, **kwargs)


def goal_reached(graph: PolicyGraph, state: KnowledgeState,
                 known_frontier: Frontier | None = None) -> bool:
    """The goal is established: reachable with nothing further left to resolve.

    An empty branch-set in the goal's frontier is what "established" means — every remaining link
    in the chain is already grounded.
    """
    f = known_frontier or state_frontier(graph, state, destination=graph.goal)
    return frozenset() in f.for_node(graph.goal)


def goal_closed(graph: PolicyGraph, state: KnowledgeState,
                known_frontier: Frontier | None = None) -> bool:
    """No assignment of the remaining outcomes can establish the goal. The route is dead."""
    f = known_frontier or state_frontier(graph, state, destination=graph.goal)
    return not f.establishable(graph.goal)


def unsafe_observed(graph: PolicyGraph, state: KnowledgeState) -> tuple[tuple[str, str], ...]:
    """Results already in hand whose outcome node is an ``UNSAFE`` terminal."""
    return state.unsafe_observations(graph)


def declared_closures(graph: PolicyGraph, state: KnowledgeState) -> tuple[dict, ...]:
    """Closures the reached terminals declare, reported for attribution rather than applied.

    A terminal naming a scope and a subject — "closes an actuator for this control variable" — does
    not name *which* actuator. The engine refuses to choose one; this is the list a human resolves.
    """
    out: list[dict] = []
    for branch, outcome in state.decided:
        node = graph.nodes.get(branch)
        if node is None:
            continue
        target = graph.nodes.get(node.outcome_target(outcome))
        if target is None or target.kind != TERMINAL or target.closes is None:
            continue
        scope, subject = target.closes
        out.append({
            "branch": branch,
            "outcome": outcome,
            "terminal": target.id,
            "scope": scope,
            "subject": subject,
            "attribution": "UNATTRIBUTED" if scope == "ACTUATOR" else "SCOPE_LEVEL",
        })
    return tuple(out)


def unsafe_routes(graph: PolicyGraph) -> tuple[tuple[str, str, str], ...]:
    """Every (branch, outcome, terminal) in the graph that ends on an unsafe terminal.

    Reported wholesale so a caller can check that nothing in a returned policy is on this list —
    which is how "a branch ending UNSAFE was presented as acceptable" becomes a measurable error
    rather than a judgement call.
    """
    out: list[tuple[str, str, str]] = []
    for node in graph.branches():
        for name, target_id in node.outcomes:
            target = graph.nodes[target_id]
            if target.kind == TERMINAL and target.role == UNSAFE:
                out.append((node.id, name, target_id))
    return tuple(sorted(out))
