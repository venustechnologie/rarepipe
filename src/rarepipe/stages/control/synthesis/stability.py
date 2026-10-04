"""Reaching a state and holding it are different claims.

x(T) in X_target says nothing about x(t) for t > T. This module separates the two, and refuses to
infer the second from the first.

* **SELF_STABILIZING_TARGET** — withdraw every control (each to its declared release value) and
  every attractor the system settles into is still inside the target.
* **MAINTAINED_TARGET** — the target holds while the controls are held, but not after withdrawal.
* **TRANSIENT_TARGET** — the target is visited but is not where the system settles.
* **UNKNOWN_STABILITY** — the default. Any control that does not declare what its variable returns
  to makes withdrawal unevaluable, and silence is not evidence that the state persists.

UNKNOWN_STABILITY being the default is the point. A model with no time in it cannot support a
claim about durability, and the absence of a decay mechanism is not a maintenance mechanism.
"""
from __future__ import annotations

from rarepipe.stages.control.controls import ControlVariable
from rarepipe.stages.control.reachability import Compiled, explore
from rarepipe.stages.control.state_space import State
from rarepipe.stages.control.synthesis.composition import released_state
from rarepipe.stages.control.synthesis.kinds import StabilityClass


def classify(c: Compiled, belief: tuple[State, ...], held: tuple[ControlVariable, ...],
             target, unsafe) -> tuple[StabilityClass, str]:
    if not belief:
        return StabilityClass.UNKNOWN_STABILITY, "no state was reached, so nothing is held"
    if not all(target(s) for s in belief):
        outside = sum(1 for s in belief if not target(s))
        return (StabilityClass.TRANSIENT_TARGET,
                f"{outside} of {len(belief)} attractor states lie outside the target while the "
                "controls are held")
    unreleasable = tuple(sorted(ctl.control_id for ctl in held if not ctl.releasable))
    if unreleasable:
        return (StabilityClass.UNKNOWN_STABILITY,
                f"the target holds while the controls are held; {list(unreleasable)} do not declare "
                "what their variable returns to, so what happens after withdrawal is not "
                "evaluable and is not assumed")
    settles: set[State] = set()
    for state in belief:
        ex = explore(c, released_state(c, state, held), frozenset(), unsafe)
        if ex.unsafe_path:
            return (StabilityClass.MAINTAINED_TARGET,
                    "withdrawal leads into the unsafe region, so the target holds only while the "
                    "controls are held")
        settles.update(ex.attractors)
    outside = tuple(sorted(s for s in settles if not target(s)))
    if not outside:
        return (StabilityClass.SELF_STABILIZING_TARGET,
                "after every control is withdrawn to its declared release value, every attractor "
                "is still inside the target")
    return (StabilityClass.MAINTAINED_TARGET,
            f"the target holds while the controls are held; after withdrawal the system settles "
            f"into {len(outside)} state(s) outside it, so maintenance is required")
