"""Experiment compiler v2: which single reading eliminates the most candidate architectures.

The first experiment compiler asked what measurement resolves an unknown relationship. With
several architectures in play there is a second question — which of them is physically real — and
one reading can bear on both.

Two kinds of discriminator are compiled, and they fail for different reasons:

* **Relationship discriminators.** When architectures disagree because they depend on an unknown
  relationship resolving different ways, a measurement whose value sets are disjoint across the
  candidates for that relationship separates them. Each reading is pre-committed to the
  architectures it eliminates, before anybody measures anything.
* **Premise tests.** An architecture whose component has no demonstrated implementation rests on a
  premise: that the component achieves the transformation it declares. The measurement that tests
  it is the component's own target variable. Without that reading, a failed component and a
  refuted architecture produce the same result and cannot be told apart.

Expected information gain is not computed. I(a;A) needs a probability distribution over the
architectures, and there is none: assigning one would put an invented prior at the centre of which
experiment gets run. The criterion is deterministic elimination, and the report says so by name.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from rarepipe.stages.control.compiler import Problem
from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.experiment_design import discriminate
from rarepipe.stages.control.observability import ObservationModel
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.synthesis.architecture import ArchitectureAssessment
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlockRegistry
from rarepipe.stages.control.synthesis.search import VariantContext

CRITERION = "deterministic_elimination"


class ArchitectureDiscriminator(Immutable):
    discriminator_id: str
    kind: Literal["relationship", "premise"]
    resolves: str
    criterion: Literal["deterministic_elimination"] = CRITERION
    measurement: str
    controls_held: tuple[str, ...]
    reading: tuple[str, ...] = Field(description="The values that indicate the route is working.")
    contrary_reading: tuple[str, ...] = ()
    eliminates_if_contrary: tuple[str, ...] = Field(
        (), description="Architectures ruled out when the contrary reading comes back. "
                        "Pre-committed, so the interpretation cannot be chosen afterwards.")
    eliminates_if_reading: tuple[str, ...] = ()
    confounded_by: tuple[str, ...] = ()
    valid_only_with: tuple[str, ...] = Field(
        (), description="Measurements that must be taken beside this one for it to mean anything.")
    observed_by: tuple[str, ...] = ()
    measurable: bool = Field(
        True, description="False when no existing experiment measures this variable. A reading "
                          "that would settle the question but that nobody can take is a gap in "
                          "the experiment, not an experiment.")
    note: str

    @property
    def at_most_eliminated(self) -> int:
        return max(len(self.eliminates_if_contrary), len(self.eliminates_if_reading))


def _depends_on(assessments: tuple[ArchitectureAssessment, ...], rid: str) -> tuple[str, ...]:
    return tuple(sorted(a.architecture_id for a in assessments
                        if rid in a.blocking_relationships))


def relationship_discriminators(problem: Problem, ctx: VariantContext,
                                assessments: tuple[ArchitectureAssessment, ...],
                                controls: dict, observation_models: tuple[ObservationModel, ...]
                                ) -> list[ArchitectureDiscriminator]:
    space = problem.space
    unsafe_ok = lambda s: problem.unsafe.contains(space, s)      # noqa: E731
    blocking = sorted({rid for a in assessments for rid in a.blocking_relationships})
    control_sets = sorted({tuple(sorted({cid for step in a.composition for b in step
                                         for cid in controls
                                         if cid.startswith(f"{b}::")}))
                           for a in assessments if a.works_in})
    control_sets = [cs for cs in control_sets if cs]
    found: list[ArchitectureDiscriminator] = []
    for rid in blocking:
        labels: dict[str, list[str]] = {}
        for variant in ctx.variants:
            label = dict(variant.choices).get(rid)
            if label is not None:
                labels.setdefault(label, []).append(variant.variant_id)
        names = sorted(labels)
        for i, good in enumerate(names):
            for bad in names[i + 1:]:
                measurements = discriminate(
                    rid, labels[good], labels[bad], ctx.compiled, ctx.x0, controls,
                    control_sets, unsafe_ok, observation_models)
                for m in measurements:
                    survives_good = tuple(sorted(
                        a.architecture_id for a in assessments
                        if set(a.works_in) & set(labels[good])))
                    survives_bad = tuple(sorted(
                        a.architecture_id for a in assessments
                        if set(a.works_in) & set(labels[bad])))
                    depends = set(_depends_on(assessments, rid))
                    found.append(ArchitectureDiscriminator(
                        discriminator_id=f"D::{rid}::{good}_vs_{bad}::{m.variable}",
                        kind="relationship", resolves=rid, measurement=m.variable,
                        controls_held=m.controls_held,
                        reading=m.values_if_route_works, contrary_reading=m.values_if_route_fails,
                        eliminates_if_reading=tuple(sorted(depends - set(survives_good))),
                        eliminates_if_contrary=tuple(sorted(depends - set(survives_bad))),
                        confounded_by=m.confounded_by,
                        valid_only_with=m.confounded_by,
                        observed_by=m.observed_by, measurable=bool(m.observed_by),
                        note=(("" if m.observed_by else
                               "no existing experiment measures this variable, so this is a gap in "
                               "the measurement set rather than an available experiment. ") +
                              f"separates {good} from {bad} for {rid}: the value sets are disjoint, "
                              "so one reading identifies the candidate" +
                              (f". Valid only alongside {list(m.confounded_by)}, which could "
                               "produce the same reading for a reason the model omits"
                               if m.confounded_by else "")),
                    ))
    return found


def premise_tests(space, registry: BuildingBlockRegistry,
                  assessments: tuple[ArchitectureAssessment, ...],
                  observation_models: tuple[ObservationModel, ...]
                  ) -> list[ArchitectureDiscriminator]:
    """For each component with no established implementation, the reading that tests its premise.

    Every available experiment is consulted, not just the default observation model: a premise the
    case's own second experiment can check is checkable, and saying otherwise would invent a gap.
    """
    out: list[ArchitectureDiscriminator] = []
    for block in registry.usable():
        if block.feasibility_status is Feasibility.ESTABLISHED:
            continue
        users = tuple(sorted(a.architecture_id for a in assessments
                             if block.building_block_id in a.components))
        if not users:
            continue
        for t in block.state_transformations:
            if not t.intended:
                continue
            measured_by = tuple(sorted(o.name for o in observation_models
                                       if t.variable in o.observed))
            observed = bool(measured_by)
            others = tuple(v for v in registry.get(block.building_block_id).variables
                           if v != t.variable)
            out.append(ArchitectureDiscriminator(
                discriminator_id=f"P::{block.building_block_id}::{t.variable}",
                kind="premise", resolves=f"component_feasibility:{block.building_block_id}",
                measurement=t.variable, controls_held=(f"{block.building_block_id}::{t.variable}",),
                reading=(t.to,),
                contrary_reading=tuple(v for v in space.variable(t.variable).domain if v != t.to),
                eliminates_if_contrary=() if not observed else users,
                observed_by=measured_by, measurable=observed,
                valid_only_with=() if observed else (t.variable,),
                note=(f"{block.building_block_id} is {block.feasibility_status.value}; every "
                      f"architecture using it assumes it drives {t.variable} to {t.to}. "
                      + (f"{list(measured_by)} measure that variable, so the premise can be "
                         "checked and a component that did nothing can be told apart from a "
                         "refuted architecture."
                         if observed else
                         f"No available experiment measures {t.variable}, so a null result "
                         "cannot distinguish a component that did nothing from an architecture "
                         "that is wrong.")
                      + (f" Other variables this component moves: {list(others)}." if others else "")),
            ))
    return out


def compile_experiments(problem: Problem, ctx: VariantContext, registry: BuildingBlockRegistry,
                        assessments: tuple[ArchitectureAssessment, ...], controls: dict
                        ) -> tuple[ArchitectureDiscriminator, ...]:
    models = tuple(e.observation for e in problem.experiments) or (problem.observation,)
    found = relationship_discriminators(problem, ctx, assessments, controls, models)
    found.extend(premise_tests(problem.space, registry, assessments, models))
    unique = {d.discriminator_id: d for d in found}
    # Measurable discriminators first: a reading nobody can take settles nothing today.
    return tuple(sorted(unique.values(),
                        key=lambda d: (not d.measurable, -d.at_most_eliminated, d.kind,
                                       d.discriminator_id)))
