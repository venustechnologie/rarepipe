"""The target is a region of functional success, not a prescribed mechanism.

Normal BubR1 abundance is not part of the target merely because restoring it is one possible route.
The target describes what the cell must achieve; the route is solved for.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import (
    Approval, ApprovalStatus, EpistemicType, Immutable, Provenance,
)
from rarepipe.stages.control.state_space import State, StateSpace


class Membership(Immutable):
    """variable ∈ allowed."""

    variable: str
    allowed: tuple[str, ...] = Field(min_length=1)

    def holds(self, space: StateSpace, state: State) -> bool:
        return space.value(state, self.variable) in self.allowed


class TargetConstraint(Immutable):
    constraint_id: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    predicate: Membership | None = Field(
        None, description="None only while UNSPECIFIED: a threshold nobody has set yet.")
    provenance: Provenance
    approval: Approval

    @model_validator(mode="after")
    def _accountable(self):
        if self.provenance.epistemic_type is not EpistemicType.TARGET_CONSTRAINT:
            raise ValueError("a target constraint must carry TARGET_CONSTRAINT provenance")
        if self.approval.status is ApprovalStatus.UNSPECIFIED and self.predicate is not None:
            raise ValueError("an unspecified constraint cannot carry a predicate")
        if self.approval.status is not ApprovalStatus.UNSPECIFIED and self.predicate is None:
            raise ValueError("only an unspecified constraint may omit its predicate")
        return self


class TargetRegion(Immutable):
    """Conjunction of constraints."""

    constraints: tuple[TargetConstraint, ...] = Field(min_length=1)

    def unspecified(self) -> tuple[TargetConstraint, ...]:
        return tuple(c for c in self.constraints if c.approval.status is ApprovalStatus.UNSPECIFIED)

    def accountability(self) -> str:
        statuses = {c.approval.status for c in self.constraints}
        if ApprovalStatus.UNSPECIFIED in statuses:
            return "INCOMPLETE"
        return "APPROVED" if statuses == {ApprovalStatus.APPROVED} else "PROPOSED_UNAPPROVED"

    def variables(self) -> tuple[str, ...]:
        return tuple(sorted({c.predicate.variable for c in self.constraints if c.predicate}))

    def contains(self, space: StateSpace, state: State) -> bool:
        return all(c.predicate.holds(space, state) for c in self.constraints if c.predicate)
