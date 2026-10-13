"""The knowledge state K = (R, U, C, S), immutable, and canonical enough to memoise on.

The state is epistemic as much as physical: it encodes what has been established, what is still
unresolved, which actions are permitted, and which actuators have been closed and on what grounds.
Two different histories that have learned the same things are the *same* state here, and must be,
or the search re-explores the same subtree once per path that reaches it.

``R`` is ``established`` — nodes taken as reached.
``U`` is every branch not in ``decided``, together with the outcomes it may still return.
``C`` is carried by the graph: conjunctions, required capabilities, re-entry.
``S`` is the ``UNSAFE`` terminal role, which no amount of benefit elsewhere may trade against.

**Actuator state is part of K, not of the log.** This is the one place where a compact campaign
abstraction would quietly lose a decision: observing that low-dose paclitaxel harms the population
does *not* establish that poleward flux is unsafe, and it does not close the HAUS8 and NuMA arms.
A solver that kept arm identity only in its trace would be unable to answer "what should we try
next" correctly, because the next actuator choice is exactly what that observation constrains. So
closures are recorded per actuator, with a scope, and a control variable closes only when every one
of its actuators has failed *on a test that actually engaged the target*.

A null without validated engagement is not a null. An arm closed for want of engagement therefore
contributes nothing toward closing its control variable — the arm was never really run.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping

from rarepipe.stages.control.policy.graph import PolicyGraph, TERMINAL, UNSAFE

AVAILABLE = "AVAILABLE"
CLOSED_UNSAFE = "CLOSED_UNSAFE"
CLOSED_INEFFECTIVE = "CLOSED_INEFFECTIVE"
CLOSED_NO_ENGAGEMENT = "CLOSED_NO_ENGAGEMENT"
ACTUATOR_STATUSES = (AVAILABLE, CLOSED_UNSAFE, CLOSED_INEFFECTIVE, CLOSED_NO_ENGAGEMENT)

# Closures that count toward closing the whole control variable. An unengaged arm does not: the
# experiment failed, which is not the same as the biology refusing.
CONCLUSIVE_CLOSURES = (CLOSED_UNSAFE, CLOSED_INEFFECTIVE)

# Scopes an observation may close, widest last. Opaque to the mathematics; meaningful to the caller.
SCOPE_ACTUATOR = "ACTUATOR"
SCOPE_CONFIGURATION = "CONFIGURATION"
SCOPE_CONTEXT = "CONTEXT"
SCOPE_CONTROL_VARIABLE = "CONTROL_VARIABLE"
SCOPE_NO_NEXT_STEP = "NO_NEXT_STEP"


class StateError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class ActuatorStatus:
    """One actuator's standing, and why. Ordered so that canonical forms sort reproducibly."""
    control_variable: str
    actuator: str
    status: str = AVAILABLE

    def __post_init__(self) -> None:
        if self.status not in ACTUATOR_STATUSES:
            raise StateError(f"{self.actuator}: unknown status {self.status!r}")

    @property
    def closed(self) -> bool:
        return self.status != AVAILABLE

    @property
    def conclusively_closed(self) -> bool:
        return self.status in CONCLUSIVE_CLOSURES


@dataclass(frozen=True)
class Observation:
    """One admissible result of one action.

    ``results`` maps each branch the action resolves to the outcome it returned, because a campaign
    may settle several branches at once and the joint result is what actually arrives from a bench.

    ``arm_updates`` and ``closure_scopes`` carry the structured per-actuator consequence. They are
    part of the observation, not an annotation on it: the state update reads them.
    """
    action_id: str
    results: tuple[tuple[str, str], ...]
    arm_updates: tuple[tuple[str, str], ...] = ()        # actuator -> status
    closure_scopes: tuple[tuple[str, str], ...] = ()     # actuator -> scope
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(sorted(self.results)))
        object.__setattr__(self, "arm_updates", tuple(sorted(self.arm_updates)))
        object.__setattr__(self, "closure_scopes", tuple(sorted(self.closure_scopes)))
        for actuator, status in self.arm_updates:
            if status not in ACTUATOR_STATUSES:
                raise StateError(f"{self.action_id}/{actuator}: unknown status {status!r}")

    @property
    def id(self) -> str:
        """A stable name for this outcome, used in policy trees and traces."""
        joint = "+".join(f"{branch}={outcome}" for branch, outcome in self.results)
        arms = "|".join(f"{a}:{s}" for a, s in self.arm_updates)
        return f"{joint}#{arms}" if arms else joint

    def resolved(self) -> dict[str, str]:
        return dict(self.results)


@dataclass(frozen=True)
class KnowledgeState:
    """What is known, what is not, and what has been closed. Immutable; `update.py` derives new ones."""
    decided: tuple[tuple[str, str], ...] = ()            # branch -> observed outcome
    established: frozenset[str] = frozenset()            # extra nodes taken as reached
    actuators: tuple[ActuatorStatus, ...] = ()
    history: tuple[str, ...] = ()                        # action ids, in the order they were taken

    def __post_init__(self) -> None:
        object.__setattr__(self, "decided", tuple(sorted(self.decided)))
        object.__setattr__(self, "actuators", tuple(sorted(self.actuators)))

    # ---------------------------------------------------------------- construction

    @classmethod
    def initial(cls, actuators: Iterable[ActuatorStatus] = ()) -> KnowledgeState:
        return cls(actuators=tuple(sorted(actuators)))

    # ---------------------------------------------------------------- views

    @property
    def resolved(self) -> dict[str, str]:
        return dict(self.decided)

    @property
    def resolved_branches(self) -> frozenset[str]:
        return frozenset(branch for branch, _ in self.decided)

    def unresolved(self, graph: PolicyGraph) -> tuple[str, ...]:
        """U: every branch that has not yet returned a result."""
        return tuple(b for b in graph.branch_ids() if b not in self.resolved_branches)

    def actuator(self, actuator: str) -> ActuatorStatus | None:
        for entry in self.actuators:
            if entry.actuator == actuator:
                return entry
        return None

    def actuators_for(self, control_variable: str) -> tuple[ActuatorStatus, ...]:
        return tuple(a for a in self.actuators if a.control_variable == control_variable)

    def open_actuators(self, control_variable: str) -> tuple[str, ...]:
        return tuple(a.actuator for a in self.actuators_for(control_variable) if not a.closed)

    def control_variable_closed(self, control_variable: str) -> bool:
        """Closed only when every one of its actuators failed a test that engaged the target.

        One unsafe actuator is not an unsafe control variable. An arm closed for want of validated
        engagement leaves the variable open, because that arm never tested it.
        """
        arms = self.actuators_for(control_variable)
        return bool(arms) and all(a.conclusively_closed for a in arms)

    def closed_control_variables(self) -> tuple[str, ...]:
        names = {a.control_variable for a in self.actuators}
        return tuple(sorted(cv for cv in names if self.control_variable_closed(cv)))

    # ---------------------------------------------------------------- safety

    def unsafe_observations(self, graph: PolicyGraph) -> tuple[tuple[str, str], ...]:
        """Observed results whose outcome node is an ``UNSAFE`` terminal.

        These are findings, not misconduct: learning that a manipulation harms the population is
        what the safety readouts are for. What the hard constraint forbids is *routing through*
        one, or reporting it as acceptable, and both are enforced by never treating such a node as
        a step toward the goal.
        """
        out: list[tuple[str, str]] = []
        for branch, outcome in self.decided:
            node = graph.nodes.get(branch)
            if node is None:
                continue
            target = graph.nodes.get(node.outcome_target(outcome))
            if target is not None and target.kind == TERMINAL and target.role == UNSAFE:
                out.append((branch, outcome))
        return tuple(out)

    # ---------------------------------------------------------------- canonical form

    def canonical(self) -> tuple:
        """What makes two states the same state for memoisation.

        History is excluded on purpose: how we came to know something does not change what follows
        from it, and including the path would defeat the transposition cache entirely. Actuator
        standing *is* included, because it changes which actions remain.
        """
        return (
            self.decided,
            tuple(sorted(self.established)),
            tuple((a.control_variable, a.actuator, a.status) for a in self.actuators),
        )

    def with_history(self, action_id: str) -> KnowledgeState:
        return replace(self, history=self.history + (action_id,))

    def describe(self) -> dict:
        """A machine-readable rendering, for traces and API responses."""
        return {
            "decided": {branch: outcome for branch, outcome in self.decided},
            "established": sorted(self.established),
            "actuators": [
                {"control_variable": a.control_variable, "actuator": a.actuator, "status": a.status}
                for a in self.actuators
            ],
            "closed_control_variables": list(self.closed_control_variables()),
            "history": list(self.history),
        }


def seed_actuators(registry: Mapping[str, Iterable[str]]) -> tuple[ActuatorStatus, ...]:
    """Build an all-available registry from {control_variable: [actuator, ...]}."""
    return tuple(sorted(
        ActuatorStatus(control_variable=cv, actuator=actuator)
        for cv, actuators in registry.items()
        for actuator in actuators
    ))
