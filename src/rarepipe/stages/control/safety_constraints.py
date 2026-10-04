"""Forbidden states. First-class, and never a penalty term.

A trajectory that enters an unsafe state is invalid even if every other endpoint improves. That is
the general form of what rules B08, B16 and B18 express for one case: an apparent improvement that
arrives with a deteriorating population is not success. Safety is checked as a hard filter on
every state a trajectory can visit; it never enters an objective function where a large enough
benefit could outweigh it.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import Approval, EpistemicType, Immutable, Provenance
from rarepipe.stages.control.state_space import State, StateSpace
from rarepipe.stages.control.target_constraints import Membership


class SafetyConstraint(Immutable):
    constraint_id: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    unsafe_when: Membership
    provenance: Provenance
    approval: Approval

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type is not EpistemicType.SAFETY_CONSTRAINT:
            raise ValueError("a safety constraint must carry SAFETY_CONSTRAINT provenance")
        return self


class UnsafeRegion(Immutable):
    """Disjunction: a state is unsafe if any constraint says so."""

    constraints: tuple[SafetyConstraint, ...]

    def variables(self) -> tuple[str, ...]:
        return tuple(sorted({c.unsafe_when.variable for c in self.constraints}))

    def violated_by(self, space: StateSpace, state: State) -> tuple[str, ...]:
        return tuple(c.constraint_id for c in self.constraints if c.unsafe_when.holds(space, state))

    def contains(self, space: StateSpace, state: State) -> bool:
        return bool(self.violated_by(space, state))
