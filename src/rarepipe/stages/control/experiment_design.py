"""Choose the measurement that resolves a control question, not an interesting assay.

When controllability depends on something unknown, the useful experiment is the one whose outcome
differs between the possibilities. Deterministic criterion: a measurement discriminates two groups
of model variants if the sets of values it can take under them are disjoint, so a single reading
identifies the group.

**A reading is only a discriminator if nothing outside the model could produce it.** If the
measured variable descends from an exogenous variable that the experiment does not hold, that
variable could move for reasons the model omits and fake the reading. The measurement is then valid
only alongside a measurement of that ancestor. This is rules B17/B18 generalised: a falling
aneuploid fraction separates rescue from failure only if cell death is measured beside it, because
selective loss of aneuploid cells produces the same fall.

Expected information gain is not used. It needs a probability over the variants, and none is
grounded here; fabricating one in order to compute EIG would put a made-up number at the centre of
the experiment choice.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.controls import ControlVariable
from rarepipe.stages.control.observability import ObservationModel
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.reachability import Compiled, run_strategy
from rarepipe.stages.control.state_space import State


class DiscriminatingMeasurement(Immutable):
    resolves: str
    controls_held: tuple[str, ...]
    variable: str
    values_if_route_works: tuple[str, ...]
    values_if_route_fails: tuple[str, ...]
    observed_by: tuple[str, ...] = Field(
        description="Existing experiments whose measurements include this variable.")
    confounded_by: tuple[str, ...] = Field(
        (), description="Uncontrolled exogenous ancestors that could produce the same reading for "
                        "reasons the model omits. The measurement discriminates only alongside a "
                        "measurement of each of these.")


def _finals(compiled: Compiled, x0: tuple[State, ...], held: tuple[str, ...],
            controls: dict[str, ControlVariable], unsafe) -> tuple[State, ...] | None:
    outcome = run_strategy(compiled, x0, (held,), controls, lambda s: True, unsafe)
    return None if outcome.status == "UNSAFE" else outcome.final_belief


def ancestors(compiled: Compiled, variable: str) -> set[str]:
    """Every variable the given one depends on, through the variant's relationships."""
    space = compiled.space
    parents = {space.names[r.output]: [space.names[i] for i in r.inputs] for r in compiled.rules}
    seen: set[str] = set()
    frontier = [variable]
    while frontier:
        for parent in parents.get(frontier.pop(), []):
            if parent not in seen:
                seen.add(parent)
                frontier.append(parent)
    return seen


def discriminate(resolves: str, works: list[str], fails: list[str],
                 compiled: dict[str, Compiled], x0: dict[str, tuple[State, ...]],
                 controls: dict[str, ControlVariable], control_sets: list[tuple[str, ...]],
                 unsafe, observation_models: tuple[ObservationModel, ...]) -> list[DiscriminatingMeasurement]:
    """Measurements whose value under `controls_held` separates `works` from `fails` variants."""
    found: list[DiscriminatingMeasurement] = []
    if not works or not fails:
        return found
    space = compiled[works[0]].space
    for held in control_sets:
        groups: dict[str, list[tuple[State, ...]]] = {"works": [], "fails": []}
        broken = False
        for label, ids in (("works", works), ("fails", fails)):
            for vid in ids:
                finals = _finals(compiled[vid], x0[vid], held, controls, unsafe)
                if finals is None:
                    broken = True
                    break
                groups[label].append(finals)
            if broken:
                break
        if broken:
            continue
        for name in space.names:
            yes = {space.value(s, name) for finals in groups["works"] for s in finals}
            no = {space.value(s, name) for finals in groups["fails"] for s in finals}
            if yes and no and not (yes & no):
                held_vars = {controls[c].sets for c in held}
                lineage = set()
                for vid in (*works, *fails):
                    lineage |= ancestors(compiled[vid], name)
                confounders = tuple(sorted(
                    a for a in lineage
                    if space.variable(a).exogenous and a not in held_vars))
                found.append(DiscriminatingMeasurement(
                    resolves=resolves, controls_held=held, variable=name,
                    values_if_route_works=tuple(sorted(yes)),
                    values_if_route_fails=tuple(sorted(no)),
                    observed_by=tuple(sorted(o.name for o in observation_models
                                             if name in o.observed)),
                    confounded_by=confounders,
                ))
    return found
