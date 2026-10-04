"""Compose building blocks into something the existing engine can evaluate.

A composition is a sequence of steps, each a set of blocks that act together. Expansion turns it
into the control strategy the reachability engine already understands, which means every guarantee
that engine provides — asynchronous all-interleaving exploration, hard safety filtering, unknown
functions fixed per trajectory — applies to a synthesized architecture unchanged. The synthesis
layer adds no new reachability semantics; it only decides what to compose.

Three checks live here because they are properties of the composition itself:

* **Conflicts.** One variable cannot be held at two values. A composition that tries is refused
  rather than silently resolved by ordering, which would make the result depend on a sort.
* **Preconditions.** A block that declares the states it can act in is checked against the belief
  at the step where it acts, so "works, provided it is applied to a cell already in state X" cannot
  pass as "works".
* **Whether the order matters.** Declaring a composition SEQUENTIAL is a claim. It is tested by
  re-running the permutations and the simultaneous collapse, and reported as load-bearing only when
  a different order actually gives a different verdict.
"""
from __future__ import annotations

from itertools import permutations

from pydantic import Field

from rarepipe.stages.control.controls import ControlVariable, Feasibility
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.reachability import Compiled, Strategy, apply_controls, run_strategy
from rarepipe.stages.control.state_space import State
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlockRegistry
from rarepipe.stages.control.synthesis.kinds import (
    ArchitectureOrigin, CompositionMode, TransformationScale,
)

Composition = tuple[tuple[str, ...], ...]

# How a single component's route relates to normal physiology. Replacement supplies a function
# the natural pathway has lost, by a route that is not the natural one, which is compensation --
# not a synthetic composition, a term reserved for a function that emerges from combining pieces.
_ROUTE_ORIGIN = {
    "repair": ArchitectureOrigin.NATURAL_PATHWAY,
    "stabilization": ArchitectureOrigin.NATURAL_PATHWAY,
    "bypass": ArchitectureOrigin.NATURAL_BYPASS,
    "compensation": ArchitectureOrigin.COMPENSATORY,
    "suppression": ArchitectureOrigin.COMPENSATORY,
    "replacement": ArchitectureOrigin.COMPENSATORY,
    "rewiring": ArchitectureOrigin.SYNTHETIC_COMPOSITION,
}


class ConflictingComposition(ValueError):
    """Two components hold the same variable at different values."""


class PreconditionGap(Immutable):
    block_id: str
    step: int
    requirement: str
    holds_in: int
    of_states: int
    severity: str = Field(description="never | sometimes — whether the block can ever act here.")


def expand(registry: BuildingBlockRegistry, composition: Composition
           ) -> tuple[dict[str, ControlVariable], Strategy]:
    """Blocks to engine controls. A block's transformations enter the same step, always together."""
    controls: dict[str, ControlVariable] = {}
    steps: list[tuple[str, ...]] = []
    for step in composition:
        ids: list[str] = []
        for block_id in sorted(step):
            for control in registry.get(block_id).controls():
                controls[control.control_id] = control
                ids.append(control.control_id)
        if not ids:
            raise ValueError("a composition step with no transformations cannot be evaluated")
        steps.append(tuple(sorted(ids)))
    return controls, tuple(steps)


def conflicts(registry: BuildingBlockRegistry, composition: Composition) -> tuple[str, ...]:
    held: dict[str, tuple[str, str]] = {}
    found: list[str] = []
    for step in composition:
        for block_id in sorted(step):
            for t in registry.get(block_id).state_transformations:
                prior = held.get(t.variable)
                if prior and prior[1] != t.to:
                    found.append(f"{t.variable} held at {prior[1]!r} by {prior[0]} and {t.to!r} "
                                 f"by {block_id}")
                else:
                    held[t.variable] = (block_id, t.to)
    return tuple(sorted(set(found)))


def scales(registry: BuildingBlockRegistry, composition: Composition) -> tuple[TransformationScale, ...]:
    found: set[TransformationScale] = set()
    for step in composition:
        for block_id in step:
            found.update(registry.get(block_id).scales)
    return tuple(sorted(found))


def derive_origin(registry: BuildingBlockRegistry, composition: Composition,
                  has_feedback: bool) -> ArchitectureOrigin:
    """Classify the composition structurally. Origin carries no epistemic discount either way."""
    if has_feedback:
        return ArchitectureOrigin.FEEDBACK_CONTROL
    found = scales(registry, composition)
    if TransformationScale.INTRACELLULAR not in found and found:
        return ArchitectureOrigin.POPULATION_CONTROL
    blocks = [registry.get(b) for step in composition for b in step]
    if len(blocks) > 1:
        return ArchitectureOrigin.SYNTHETIC_COMPOSITION
    return _ROUTE_ORIGIN.get(blocks[0].route_class.value, ArchitectureOrigin.SYNTHETIC_COMPOSITION)


def derive_mode(composition: Composition, has_feedback: bool, reversible: bool) -> CompositionMode:
    if has_feedback:
        return CompositionMode.CONDITIONAL
    if len(composition) > 1:
        return CompositionMode.SEQUENTIAL
    return CompositionMode.PULSED if reversible else CompositionMode.SIMULTANEOUS


def feasibility_blockers(registry: BuildingBlockRegistry, composition: Composition) -> tuple[str, ...]:
    return tuple(sorted({b for step in composition for b in step
                         if registry.get(b).feasibility_status is not Feasibility.ESTABLISHED}))


def moved_variables(registry: BuildingBlockRegistry, composition: Composition) -> tuple[str, ...]:
    return tuple(sorted({t.variable for step in composition for b in step
                         for t in registry.get(b).state_transformations}))


def precondition_gaps(c: Compiled, x0: tuple[State, ...], registry: BuildingBlockRegistry,
                      composition: Composition, controls: dict[str, ControlVariable],
                      target, unsafe) -> tuple[PreconditionGap, ...]:
    """Check each block's declared input states against the belief at the step where it acts."""
    gaps: list[PreconditionGap] = []
    for k, step in enumerate(composition):
        prefix = composition[:k]
        if prefix:
            _, strategy = expand(registry, prefix)
            outcome = run_strategy(c, x0, strategy, controls, target, unsafe)
            belief = outcome.final_belief
        else:
            belief = tuple(sorted(x0))
        if not belief:
            continue
        for block_id in sorted(step):
            block = registry.get(block_id)
            for req in block.input_state_requirements:
                holds = sum(1 for s in belief if req.holds(c.space, s))
                if holds < len(belief):
                    gaps.append(PreconditionGap(
                        block_id=block_id, step=k,
                        requirement=f"{req.variable} in {list(req.allowed)}",
                        holds_in=holds, of_states=len(belief),
                        severity="never" if holds == 0 else "sometimes"))
    return tuple(gaps)


def order_matters(c: Compiled, x0: tuple[State, ...], registry: BuildingBlockRegistry,
                  composition: Composition, target, unsafe) -> tuple[bool, str]:
    """Does this ordering do something the other orderings do not?

    Tested, not assumed: every permutation of the steps and the simultaneous collapse are run, and
    the order is called load-bearing only when some alternative gives a different verdict.
    """
    if len(composition) < 2:
        return False, "a single step has no order to be load-bearing"
    controls, strategy = expand(registry, composition)
    mine = run_strategy(c, x0, strategy, controls, target, unsafe).status
    alternatives: list[tuple[str, str]] = []
    if len(composition) <= 4:
        for perm in permutations(range(len(composition))):
            if list(perm) == list(range(len(composition))):
                continue
            other = tuple(composition[i] for i in perm)
            _, alt = expand(registry, other)
            alternatives.append((f"order {[list(composition[i]) for i in perm]}",
                                 run_strategy(c, x0, alt, controls, target, unsafe).status))
    collapsed = (tuple(sorted({b for step in composition for b in step})),)
    _, flat = expand(registry, collapsed)
    alternatives.append(("all components at once",
                         run_strategy(c, x0, flat, controls, target, unsafe).status))
    differing = [f"{label}: {status}" for label, status in alternatives if status != mine]
    if not differing:
        return False, f"every alternative ordering also gives {mine}; the order is not load-bearing"
    return True, (f"this order gives {mine}; " + "; ".join(sorted(differing)))


def released_state(c: Compiled, state: State, controls: tuple[ControlVariable, ...]) -> State:
    """The state after every control is withdrawn to its declared release value."""
    nxt = list(state)
    for control in controls:
        if control.releasable:
            nxt[c.space.index(control.sets)] = control.released_to
    return tuple(nxt)


def held_state(c: Compiled, state: State, controls: tuple[ControlVariable, ...]) -> State:
    return apply_controls(c.space, state, controls)
