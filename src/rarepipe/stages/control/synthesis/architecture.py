"""An architecture is a composition of transformations, and an assessment of one is two verdicts.

The two verdicts never collapse into one. `logical` says whether the composition reaches the
target in the mathematics; `physical` says whether anything is known to implement its declared
transformations. An elegant composition with no demonstrated actuator is a legitimate, useful
output — and it is not a proposal to do anything.

An architecture also records what scale it acts at, because a target reached at the population
scale is not a cell that was corrected, and the two must never be reported as the same event.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.synthesis.feedback import FeedbackPolicy
from rarepipe.stages.control.synthesis.kinds import (
    ArchitectureOrigin, CompositionMode, LogicalStatus, PhysicalStatus, RobustnessClass,
    StabilityClass, TransformationScale,
)
from rarepipe.stages.control.synthesis.population import ConfounderGap
from rarepipe.stages.control.target_constraints import Membership

_ARCHITECTURE_TYPES = {EpistemicType.PROPOSED_ARCHITECTURE, EpistemicType.COMPOSED_CONTROL}


class ControlArchitecture(Immutable):
    architecture_id: str = Field(min_length=1)
    family: str = Field(min_length=1, description="The structural family it belongs to.")
    composition: tuple[tuple[str, ...], ...] = Field(
        min_length=1, description="Ordered steps of building-block ids. One step means they act "
                                  "together; several mean the order is part of the architecture.")
    composition_mode: CompositionMode
    target_constraints: tuple[str, ...] = ()
    required_conditions: tuple[Membership, ...] = ()
    feedback: FeedbackPolicy | None = None
    origin: ArchitectureOrigin
    rationale: str = Field(min_length=1)
    assumptions: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="after")
    def _well_formed(self):
        flat = [b for step in self.composition for b in step]
        if len(set(flat)) != len(flat):
            raise ValueError(f"{self.architecture_id}: a building block appears twice; holding one "
                             "block in two steps is not represented")
        if not flat:
            raise ValueError(f"{self.architecture_id}: an architecture needs at least one component")
        if self.composition_mode is CompositionMode.SIMULTANEOUS and len(self.composition) != 1:
            raise ValueError(f"{self.architecture_id}: SIMULTANEOUS means one step")
        if self.composition_mode is CompositionMode.SEQUENTIAL and len(self.composition) < 2:
            raise ValueError(f"{self.architecture_id}: SEQUENTIAL needs more than one step")
        if self.composition_mode is CompositionMode.CONDITIONAL and self.feedback is None:
            raise ValueError(f"{self.architecture_id}: CONDITIONAL composition is defined by its "
                             "policy; attach one or declare a different mode")
        if self.provenance.epistemic_type not in _ARCHITECTURE_TYPES:
            raise ValueError(f"{self.architecture_id}: an architecture carries PROPOSED_ARCHITECTURE "
                             "or COMPOSED_CONTROL provenance, never an empirical type")
        return self

    @property
    def components(self) -> tuple[str, ...]:
        return tuple(sorted({b for step in self.composition for b in step}))

    @property
    def steps(self) -> int:
        return len(self.composition)


class ArchitectureAssessment(Immutable):
    architecture_id: str
    family: str
    origin: ArchitectureOrigin
    composition_mode: CompositionMode
    composition: tuple[tuple[str, ...], ...]
    components: tuple[str, ...]
    scales: tuple[TransformationScale, ...]
    rescue_scope: str = Field(description="What a reached target here is, and is not, evidence of.")

    logical: LogicalStatus
    physical: PhysicalStatus
    robustness: RobustnessClass
    stability: StabilityClass
    stability_note: str

    works_in: tuple[str, ...] = ()
    fails_in: tuple[str, ...] = ()
    unsafe_in: tuple[str, ...] = ()
    per_model: tuple[tuple[str, str], ...] = ()
    blocking_relationships: tuple[str, ...] = ()
    irrelevant_unknowns: tuple[str, ...] = ()
    relies_on: tuple[str, ...] = ()
    unresolved_relied_on: tuple[str, ...] = ()

    feasibility_blockers: tuple[str, ...] = Field(
        (), description="Components whose implementation is not established. Named, not scored.")
    overrides_relationships: tuple[str, ...] = Field(
        (), description="Relationships this architecture overrides by holding their output "
                        "directly. A bypass works precisely by asserting that some mechanism can "
                        "supply a value the model says comes from somewhere else, so each one is "
                        "an unmet requirement of its own and is named rather than absorbed.")
    missing_release_declarations: tuple[str, ...] = ()
    confounder_gaps: tuple[ConfounderGap, ...] = ()
    undeclared_population_mechanisms: tuple[str, ...] = ()
    unobservable_policy_inputs: tuple[str, ...] = ()

    order_is_load_bearing: bool = False
    order_note: str = ""
    feedback_policy: str | None = None
    feedback_status: str = ""
    unsafe_path: tuple[dict, ...] = ()
    assumptions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _the_two_feasibilities_stay_apart(self):
        if (self.physical is PhysicalStatus.PHYSICALLY_FEASIBLE
                and (self.feasibility_blockers or self.missing_release_declarations)):
            raise ValueError(
                f"{self.architecture_id}: cannot be PHYSICALLY_FEASIBLE while components "
                f"{list(self.feasibility_blockers)} have no established implementation; logical "
                "synthesizability does not transfer")
        if self.logical is LogicalStatus.TARGET_REACHABLE and not self.works_in:
            raise ValueError(f"{self.architecture_id}: TARGET_REACHABLE must name the variants it "
                             "holds under")
        if self.robustness is RobustnessClass.ROBUST_CONTROL_CANDIDATE and self.fails_in:
            raise ValueError(f"{self.architecture_id}: robust means every consistent variant, and "
                             f"{list(self.fails_in)} are not")
        return self

    @property
    def logically_synthesizable(self) -> bool:
        return self.logical in {LogicalStatus.TARGET_REACHABLE,
                                LogicalStatus.REACHABLE_UNDER_SOME_MODELS}

    @property
    def physically_feasible(self) -> bool:
        return self.physical is PhysicalStatus.PHYSICALLY_FEASIBLE

    @property
    def clear(self) -> bool:
        """Reaches the target under every consistent variant, safely, with every piece buildable."""
        return (self.logical is LogicalStatus.TARGET_REACHABLE
                and self.robustness is RobustnessClass.ROBUST_CONTROL_CANDIDATE
                and self.physically_feasible and not self.unsafe_in
                and not self.confounder_gaps and not self.unobservable_policy_inputs)
