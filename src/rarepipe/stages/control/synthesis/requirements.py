"""Invert the specification: from the desired state, what must become true.

The control compiler asks whether given controls reach the target. This module asks the prior
question — what would have to change for the target to hold at all — and answers it without naming
a single intervention.

For each target constraint the decomposition records: the values the state actually takes across
the evidence-consistent initial states, whether the constraint already holds there, the causal
ancestors through which it could be moved, the **entry points** (ancestors that nothing in the
model drives, so a building block has to act on one of them), and the unresolved relationships
lying between an entry point and the requirement.

The entry points are the specification handed to the synthesis layer. They say *where* a mechanism
must act, never *what* mechanism — that separation is the whole reason this layer exists.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.compiler import Problem
from rarepipe.stages.control.dynamics import Model, RelationshipKind
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.state_space import State, StateSpace
from rarepipe.stages.control.synthesis.kinds import TransformationScale


class RequiredFunction(Immutable):
    """One thing that must become true. Not a mechanism, and not an intervention."""

    requirement_id: str
    constraint_id: str
    variable: str
    must_enter: tuple[str, ...]
    currently: tuple[str, ...] = Field(
        description="Values the variable takes across the evidence-consistent initial states.")
    already_satisfied: bool
    scale: TransformationScale
    causal_ancestors: tuple[str, ...]
    entry_points: tuple[str, ...] = Field(
        description="Ancestors with no defining relationship, plus the variable itself when it has "
                    "none. A transformation has to act on one of these to move the requirement.")
    unresolved_dependencies: tuple[str, ...] = Field(
        description="Unknown relationships between an entry point and this requirement. Acting on "
                    "an entry point moves the requirement only if these resolve favourably.")
    latent: bool = Field(description="True when no endpoint measures this variable directly.")


class Decomposition(Immutable):
    required: tuple[RequiredFunction, ...]
    unmet: tuple[str, ...] = Field(description="Requirement ids not already satisfied.")
    entry_points: tuple[str, ...] = Field(description="Union of entry points across unmet requirements.")
    note: str


def _lineage(model: Model, variable: str) -> tuple[set[str], set[str], set[str]]:
    """(ancestors, entry points, unresolved relationship ids) for one variable in one model."""
    ancestors: set[str] = set()
    entries: set[str] = set()
    unresolved: set[str] = set()
    frontier = [variable]
    seen = {variable}
    while frontier:
        name = frontier.pop()
        rel = model.defining(name)
        if rel is None:
            entries.add(name)
            continue
        if rel.kind is RelationshipKind.UNKNOWN_FUNCTION or rel.epistemic_status != "established":
            unresolved.add(rel.relationship_id)
        for parent in rel.inputs:
            ancestors.add(parent)
            if parent not in seen:
                seen.add(parent)
                frontier.append(parent)
    return ancestors, entries, unresolved


def scale_of(space: StateSpace, variable: str, population: frozenset[str],
             tissue: frozenset[str]) -> TransformationScale:
    if variable in tissue:
        return TransformationScale.TISSUE_FUNCTION
    if variable in population:
        return TransformationScale.POPULATION
    return TransformationScale.INTRACELLULAR


def decompose(problem: Problem, initial: dict[str, tuple[State, ...]],
              population_variables: tuple[str, ...] = (),
              tissue_variables: tuple[str, ...] = ()) -> Decomposition:
    """Turn the target region into the set of functions that must hold, and where they can be moved."""
    space = problem.space
    population, tissue = frozenset(population_variables), frozenset(tissue_variables)
    every_state = sorted({s for states in initial.values() for s in states})
    required: list[RequiredFunction] = []
    for constraint in problem.target.constraints:
        if constraint.predicate is None:
            continue
        name = constraint.predicate.variable
        allowed = constraint.predicate.allowed
        current = tuple(sorted({space.value(s, name) for s in every_state}))
        ancestors: set[str] = set()
        entries: set[str] = set()
        unresolved: set[str] = set()
        for model in problem.models:
            a, e, u = _lineage(model, name)
            ancestors |= a
            entries |= e
            unresolved |= u
        required.append(RequiredFunction(
            requirement_id=f"RF::{constraint.constraint_id}",
            constraint_id=constraint.constraint_id, variable=name, must_enter=allowed,
            currently=current,
            already_satisfied=bool(current) and all(v in allowed for v in current),
            scale=scale_of(space, name, population, tissue),
            causal_ancestors=tuple(sorted(ancestors)),
            entry_points=tuple(sorted(e for e in entries if space.variable(e).exogenous or
                                      all(m.defining(e) is None for m in problem.models))),
            unresolved_dependencies=tuple(sorted(unresolved)),
            latent=space.variable(name).latent,
        ))
    required.sort(key=lambda r: r.requirement_id)
    unmet = tuple(r.requirement_id for r in required if not r.already_satisfied)
    entry_union = tuple(sorted({e for r in required if not r.already_satisfied
                                for e in r.entry_points}))
    return Decomposition(
        required=tuple(required), unmet=unmet, entry_points=entry_union,
        note=("What must become true for the target to hold, and the variables a transformation "
              "would have to act on. Nothing here names an intervention: the entry points are "
              "positions in the causal model, and whether anything can act on one is a separate "
              "question answered by the building-block registry."),
    )
