"""Hybrid state space. Qualitative values stay qualitative.

Every value is a named category. Nothing here maps "impaired" to 0 and "normal" to 1 to make a
computation convenient — an ordinal-to-numeric mapping would need explicit semantics and provenance,
and the finite-state engine does not need one. INTERVAL variables are recognised by the contract and
refused by this engine.
"""
from __future__ import annotations

from enum import StrEnum
from itertools import product
from typing import Iterator

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import Immutable

State = tuple[str, ...]


class VariableKind(StrEnum):
    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"
    INTERVAL = "interval"


class Variable(Immutable):
    name: str = Field(min_length=1)
    kind: VariableKind
    domain: tuple[str, ...]
    meaning: str = Field(min_length=1, description="What this variable is, biologically.")
    ordinal_semantics: str = Field(
        "", description="For ORDINAL: what the order means. Required, or the order is arbitrary.")
    latent: bool = Field(False, description="True when no endpoint measures it directly.")
    exogenous: bool = Field(
        False, description="True when it has no defining relationship by design.")
    exogenous_reason: str = ""

    @model_validator(mode="after")
    def _well_formed(self):
        if self.kind is VariableKind.INTERVAL:
            raise ValueError(
                f"{self.name}: interval variables are recognised by the contract but this phase "
                "implements the finite-state formalism only; add an adapter to an established "
                "solver rather than discretising silently"
            )
        if len(self.domain) < 2 or len(set(self.domain)) != len(self.domain):
            raise ValueError(f"{self.name}: a domain needs at least two distinct values")
        if self.kind is VariableKind.ORDINAL and not self.ordinal_semantics:
            raise ValueError(f"{self.name}: an ordinal variable must say what its order means")
        if self.exogenous and not self.exogenous_reason:
            raise ValueError(
                f"{self.name}: declaring a variable exogenous asserts that nothing in the model "
                "drives it — say why, or a missing relationship is being hidden"
            )
        return self

    def rank(self, value: str) -> int:
        if self.kind is not VariableKind.ORDINAL:
            raise ValueError(f"{self.name} is not ordinal; its values have no order")
        return self.domain.index(value)


class StateSpace(Immutable):
    variables: tuple[Variable, ...]

    @model_validator(mode="after")
    def _unique(self):
        names = [v.name for v in self.variables]
        if len(set(names)) != len(names):
            raise ValueError("variable names must be unique")
        return self

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.variables)

    def index(self, name: str) -> int:
        try:
            return self.names.index(name)
        except ValueError:
            raise KeyError(f"no variable named {name!r}") from None

    def variable(self, name: str) -> Variable:
        return self.variables[self.index(name)]

    def size(self) -> int:
        total = 1
        for v in self.variables:
            total *= len(v.domain)
        return total

    def states(self, allowed: dict[str, tuple[str, ...]] | None = None) -> Iterator[State]:
        """Every state, optionally restricted per variable. Deterministic order."""
        allowed = allowed or {}
        axes = [allowed.get(v.name, v.domain) for v in self.variables]
        yield from product(*axes)

    def value(self, state: State, name: str) -> str:
        return state[self.index(name)]

    def as_dict(self, state: State) -> dict[str, str]:
        return dict(zip(self.names, state))
