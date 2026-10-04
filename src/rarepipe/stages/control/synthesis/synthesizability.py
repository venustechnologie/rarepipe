"""Two questions that must never be answered by one word.

`LOGICALLY_SYNTHESIZABLE`
    A composition of declared transformations reaches the target region without entering the unsafe
    region, under the stated models.

`PHYSICALLY_FEASIBLE`
    There is evidence that those transformations can actually be produced, in the relevant cell
    type, by something that exists.

    logical solution  =/=>  feasible intervention

Collapsing the two is how an elegant diagram becomes a treatment proposal. So the physical verdict
is computed only from the components' own feasibility fields and never from the logical result:
`SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN` is a successful output of the compiler, with its blockers
named.
"""
from __future__ import annotations

from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlockRegistry
from rarepipe.stages.control.synthesis.composition import Composition
from rarepipe.stages.control.synthesis.kinds import LogicalStatus, PhysicalStatus


def logical_status(works_in: tuple[str, ...], fails_in: tuple[str, ...],
                   unsafe_in: tuple[str, ...]) -> LogicalStatus:
    if unsafe_in:
        return LogicalStatus.UNSAFE
    if works_in and not fails_in:
        return LogicalStatus.TARGET_REACHABLE
    if works_in:
        return LogicalStatus.REACHABLE_UNDER_SOME_MODELS
    return LogicalStatus.TARGET_UNREACHABLE


def physical_status(registry: BuildingBlockRegistry, composition: Composition
                    ) -> tuple[PhysicalStatus, tuple[str, ...]]:
    """The components' own feasibility, and nothing else. Returns the status and its blockers."""
    blocks = [registry.get(b) for step in composition for b in sorted(step)]
    infeasible = tuple(sorted(b.building_block_id for b in blocks
                              if b.feasibility_status is Feasibility.INFEASIBLE))
    if infeasible:
        return PhysicalStatus.PHYSICALLY_INFEASIBLE, infeasible
    unassessed = tuple(sorted(b.building_block_id for b in blocks
                              if b.feasibility_status is not Feasibility.ESTABLISHED))
    if unassessed:
        return PhysicalStatus.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN, unassessed
    return PhysicalStatus.PHYSICALLY_FEASIBLE, ()


def blockers(registry: BuildingBlockRegistry, composition: Composition) -> tuple[str, ...]:
    """Why each component is not established, in words, so the gap is actionable."""
    out = []
    for step in composition:
        for block_id in sorted(step):
            block = registry.get(block_id)
            if block.feasibility_status is not Feasibility.ESTABLISHED:
                out.append(f"{block_id}: {block.feasibility_status.value} — {block.feasibility_note}")
    return tuple(out)
