"""Closed-loop control: measure, decide, act, measure again.

A static intervention and a feedback policy are different objects, and this module keeps them
apart. The control compiler's semantics are deliberately open-loop — controls accumulate and are
never released, because releasing one would otherwise let a transient push lock in a state that no
mechanism maintains. Feedback needs release, so it is admitted here under one condition: **a
control can only be released if it says what its variable returns to, and what returns it.**
Without that, a loop would be evaluated against a reversion the model does not contain.

The loop is evaluated as a finite transition system over composite nodes (plant state, controls
currently held). From any node either the plant takes an asynchronous causal step, or the
controller fires one applicable rule. Every interleaving is explored, so the verdict does not
depend on an assumed sampling rate — which is the honest level of claim available, since nothing
here has a time constant.

What the loop can be said to achieve:

* the target is **maintained** when every terminal strongly connected component of the composite
  system lies inside the target region and no reachable state is unsafe;
* anything less is reported as not maintained, with the states it settles into.

Invariant: every rule reads a variable the observation model actually measures. A controller
keyed on an unmeasured variable is not a controller.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from pydantic import Field, model_validator

from rarepipe.stages.control.controls import ControlVariable
from rarepipe.stages.control.observability import ObservationModel
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.reachability import Compiled, _successors, _terminal_sccs
from rarepipe.stages.control.state_space import State
from rarepipe.stages.control.target_constraints import Membership

Predicate = Callable[[State], bool]


class FeedbackAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"


class ReleaseUndeclared(ValueError):
    """A policy releases a control that never said what its variable returns to."""


class FeedbackRule(Immutable):
    rule_id: str = Field(min_length=1)
    when: Membership = Field(description="Read on a measured variable, never on a latent one.")
    action: FeedbackAction
    control_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class FeedbackPolicy(Immutable):
    """u(t) = pi(y(t)). No numeric times: the policy says what to do on a reading, not when."""

    policy_id: str = Field(min_length=1)
    rules: tuple[FeedbackRule, ...] = Field(min_length=1)
    sampling: str = Field(
        min_length=1,
        description="What counts as a reading, in words. No sampling interval is invented: none is "
                    "grounded, and the evaluation explores every interleaving instead.")
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type is not EpistemicType.FEEDBACK_POLICY:
            raise ValueError(f"{self.policy_id}: a feedback policy carries FEEDBACK_POLICY provenance")
        return self

    @property
    def observed_inputs(self) -> tuple[str, ...]:
        return tuple(sorted({r.when.variable for r in self.rules}))

    @property
    def control_ids(self) -> tuple[str, ...]:
        return tuple(sorted({r.control_id for r in self.rules}))


def unobservable_inputs(policy: FeedbackPolicy, obs: ObservationModel) -> tuple[str, ...]:
    """Rule inputs the experiment does not measure. A non-empty result invalidates the policy."""
    seen = set(obs.observed)
    return tuple(sorted({r.when.variable for r in policy.rules if r.when.variable not in seen}))


def undeclared_releases(policy: FeedbackPolicy, controls: dict[str, ControlVariable]) -> tuple[str, ...]:
    return tuple(sorted({r.control_id for r in policy.rules
                         if r.action is FeedbackAction.DEACTIVATE
                         and not controls[r.control_id].releasable}))


# `held` is a sorted tuple, not a frozenset. Sorting nodes has to be a total order for the
# result to be reproducible, and `<` on frozensets is a subset test: two incomparable sets would
# sort in whatever order the list happened to be in.
Node = tuple[State, tuple[str, ...]]


@dataclass(frozen=True)
class LoopOutcome:
    status: str                             # MAINTAINED | NOT_MAINTAINED | UNSAFE
    fired: tuple[str, ...] = ()
    attractor_states: tuple[State, ...] = ()
    reachable_states: tuple[State, ...] = ()
    outside_target: tuple[State, ...] = ()
    unsafe_path: tuple[State, ...] = ()
    held_at_attractors: tuple[tuple[str, ...], ...] = ()

    @property
    def maintained(self) -> bool:
        return self.status == "MAINTAINED"


def _settle(state: State, held: tuple[str, ...], controls: dict[str, ControlVariable],
            space) -> State:
    """Force every held control's variable to its value. Controls are held, not suggested."""
    nxt = list(state)
    for cid in held:
        control = controls[cid]
        nxt[space.index(control.sets)] = control.to
    return tuple(nxt)


def _controller_steps(c: Compiled, node: Node, policy: FeedbackPolicy,
                      controls: dict[str, ControlVariable]) -> list[Node]:
    """One applicable rule at a time: the controller is asynchronous like everything else."""
    state, held = node
    out: list[Node] = []
    for rule in sorted(policy.rules, key=lambda r: r.rule_id):
        if not rule.when.holds(c.space, state):
            continue
        control = controls[rule.control_id]
        if rule.action is FeedbackAction.ACTIVATE:
            if rule.control_id in held:
                continue
            new_held = tuple(sorted({*held, rule.control_id}))
            out.append((_settle(state, new_held, controls, c.space), new_held))
        else:
            if rule.control_id not in held:
                continue
            if not control.releasable:
                raise ReleaseUndeclared(
                    f"{policy.policy_id}/{rule.rule_id} releases {rule.control_id}, which does not "
                    f"declare what {control.sets} returns to; evaluating the loop would invent a "
                    "reversion mechanism")
            new_held = tuple(cid for cid in held if cid != rule.control_id)
            reverted = list(state)
            reverted[c.space.index(control.sets)] = control.released_to
            out.append((_settle(tuple(reverted), new_held, controls, c.space), new_held))
    return out


def run_closed_loop(c: Compiled, x0: tuple[State, ...], policy: FeedbackPolicy,
                    controls: dict[str, ControlVariable], target: Predicate,
                    unsafe: Predicate) -> LoopOutcome:
    """Explore every interleaving of plant steps and controller decisions."""
    if not x0:
        raise ValueError("an empty initial-state set makes every policy vacuously succeed")
    starts: list[Node] = [(state, ()) for state in sorted(x0)]
    for state, _ in starts:
        if unsafe(state):
            return LoopOutcome("UNSAFE", unsafe_path=(state,))
    parent: dict[Node, Node | None] = {n: None for n in starts}
    edges: dict[Node, list[Node]] = {}
    fired: set[str] = set()
    queue = deque(starts)
    while queue:
        node = queue.popleft()
        state, held = node
        pinned = frozenset(c.space.index(controls[cid].sets) for cid in held)  # order-free
        plant = _successors(c, state, pinned)
        fired.update(rid for rid, _ in plant)
        succ = [(s, held) for _, s in plant]
        succ.extend(_controller_steps(c, node, policy, controls))
        edges[node] = succ
        for nxt in succ:
            if nxt in parent:
                continue
            parent[nxt] = node
            if unsafe(nxt[0]):
                path = [nxt]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])
                return LoopOutcome("UNSAFE", fired=tuple(sorted(fired)),
                                   unsafe_path=tuple(n[0] for n in reversed(path)))
            queue.append(nxt)
    nodes = sorted(parent)
    terminal = _terminal_sccs(nodes, edges)
    attractors = tuple(sorted({n[0] for n in terminal}))
    outside = tuple(s for s in attractors if not target(s))
    return LoopOutcome(
        "MAINTAINED" if attractors and not outside else "NOT_MAINTAINED",
        fired=tuple(sorted(fired)), attractor_states=attractors,
        reachable_states=tuple(sorted({n[0] for n in nodes})),
        outside_target=outside,
        held_at_attractors=tuple(sorted({n[1] for n in terminal})),
    )
