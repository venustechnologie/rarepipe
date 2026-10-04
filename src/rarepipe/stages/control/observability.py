"""Can we know whether we caused it?

A controller must answer two questions: can we cause the desired state, and can we tell that we did.

Two kinds of check, because they fail for different reasons:

* **Direct observation of what success and safety are defined on.** Every variable a target or
  safety constraint refers to must be measured by the experiment meant to verify the strategy.
  Safety in particular cannot be certified by a model's prediction that a variable will not move —
  the model's omissions are precisely why that variable is measured, and using the prediction in
  place of the measurement would be treating simulation as observation.
* **Distinguishability.** Two states that produce identical measurements cannot be told apart.
  When they differ in something that matters — target membership, safety, which model is true —
  the observation set is insufficient for that question.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.provenance import Immutable, Provenance
from rarepipe.stages.control.safety_constraints import UnsafeRegion
from rarepipe.stages.control.state_space import State, StateSpace
from rarepipe.stages.control.target_constraints import TargetRegion


class ObservationModel(Immutable):
    """Which state variables an experiment measures: y = h(x) is the projection onto these."""

    name: str = Field(min_length=1)
    observed: tuple[str, ...]
    provenance: Provenance
    generated_under: str = Field(min_length=1)

    def project(self, space: StateSpace, state: State) -> tuple[str, ...]:
        """Measured variables that exist in this state space. An experiment can measure things the
        control model does not represent — upstream mechanism readouts, for instance."""
        present = set(space.names)
        return tuple(space.value(state, v) for v in self.observed if v in present)


class ObservabilityGaps(Immutable):
    observation_model: str
    unobserved_target_variables: tuple[str, ...]
    unobserved_safety_variables: tuple[str, ...]

    @property
    def sufficient(self) -> bool:
        return not (self.unobserved_target_variables or self.unobserved_safety_variables)


def direct_gaps(target: TargetRegion, unsafe: UnsafeRegion, obs: ObservationModel) -> ObservabilityGaps:
    seen = set(obs.observed)
    return ObservabilityGaps(
        observation_model=obs.name,
        unobserved_target_variables=tuple(v for v in target.variables() if v not in seen),
        unobserved_safety_variables=tuple(v for v in unsafe.variables() if v not in seen),
    )


def indistinguishable(space: StateSpace, states: tuple[State, ...], obs: ObservationModel,
                      label) -> tuple[tuple[State, State], ...]:
    """Pairs that look the same under `obs` but differ in `label` (e.g. target membership)."""
    by_view: dict[tuple[str, ...], list[State]] = {}
    for state in sorted(set(states)):
        by_view.setdefault(obs.project(space, state), []).append(state)
    pairs = []
    for view in sorted(by_view):
        group = by_view[view]
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if label(a) != label(b):
                    pairs.append((a, b))
    return tuple(pairs)
