"""The population scale, and the rule that keeps it from lying.

An architecture may aim at the composition of a population rather than at correcting any cell. The
honest representation of dp/dt = T + R - D + S here is not a solver: it is a population variable in
the same finite state space, moved by **named mechanisms**, each of which must say what produces
the differential. A declared population effect with no stated source of differential growth, death
or transition is a wish, and this module refuses it.

The load-bearing rule is the general form of something the control compiler already found for one
measurement: a falling aneuploid fraction separates rescue from failure only if cell death is
measured beside it, because selective loss of the aneuploid cells produces the same fall.
Generalised:

    No population-level improvement counts as functional success while an omitted process could
    produce the same observation.

So every population outcome declares the processes that could fake its reading and the observables
that would exclude each. A process the model does not represent has no node to be an ancestor of,
which is exactly why it has to be declared here rather than derived from the graph.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import Approval, ApprovalStatus, EpistemicType, Immutable, Provenance
from rarepipe.stages.control.state_space import StateSpace
from rarepipe.stages.control.synthesis.kinds import TransformationScale
from rarepipe.stages.control.target_constraints import Membership

Differential = Literal["differential_growth", "differential_death", "state_transition",
                       "replacement", "competition"]


class PopulationMechanism(Immutable):
    """What moves a population variable, and what makes the movement selective."""

    mechanism_id: str = Field(min_length=1)
    produces: Differential
    drives: str = Field(min_length=1, description="The population variable it moves.")
    requires: tuple[Membership, ...] = ()
    source_of_differential: str = Field(
        min_length=20,
        description="What makes this act unequally on the subpopulations — a fitness difference, a "
                    "surface marker, a dependency. 'Selection' is not an answer.")
    affects_scale: TransformationScale = TransformationScale.POPULATION
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type not in {EpistemicType.POPULATION_CONTROL,
                                                  EpistemicType.LITERATURE_EVIDENCE,
                                                  EpistemicType.INFERRED_HYPOTHESIS,
                                                  EpistemicType.MODEL_ASSUMPTION}:
            raise ValueError(f"{self.mechanism_id}: a population mechanism carries "
                             "POPULATION_CONTROL, LITERATURE_EVIDENCE, INFERRED_HYPOTHESIS or "
                             "MODEL_ASSUMPTION provenance")
        return self


class ConfoundingProcess(Immutable):
    """A process that could produce a population reading for a reason the model omits."""

    process_id: str = Field(min_length=1)
    could_produce: str = Field(min_length=1, description="The population variable whose reading it fakes.")
    reading: tuple[str, ...] = Field(
        min_length=1, description="The values it could produce without any functional improvement.")
    mechanism: str = Field(min_length=20)
    excluded_by: tuple[str, ...] = Field(
        min_length=1, description="Observables that would distinguish it. Never empty: a confounder "
                                  "nobody can exclude is a reason the measurement cannot be used.")
    represented_in_model: bool = Field(
        description="False when the model has no node for it, which is why it must be declared.")
    provenance: Provenance


class PopulationRequirement(Immutable):
    """rho_acceptable / rho_total >= q_min, with q_min owned by a human.

    The fraction is represented as a qualitative population variable entering an acceptable set.
    No numeric threshold is stored, because none has been approved: inventing q_min would put a
    made-up number at the centre of what counts as success.
    """

    requirement_id: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    acceptable: tuple[str, ...] = Field(min_length=1)
    threshold_note: str = Field(min_length=1)
    approval: Approval

    @model_validator(mode="after")
    def _threshold_is_owned(self):
        if self.approval.status is ApprovalStatus.APPROVED and self.approval.approver is None:
            raise ValueError(f"{self.requirement_id}: an approved threshold must name its approver")
        return self


class ConfounderGap(Immutable):
    variable: str
    process_id: str
    missing_observables: tuple[str, ...]
    consequence: str


class PopulationLayer(Immutable):
    population_variables: tuple[str, ...] = ()
    tissue_variables: tuple[str, ...] = ()
    mechanisms: tuple[PopulationMechanism, ...] = ()
    confounders: tuple[ConfoundingProcess, ...] = ()
    requirements: tuple[PopulationRequirement, ...] = ()

    def check(self, space: StateSpace) -> None:
        for name in (*self.population_variables, *self.tissue_variables):
            space.index(name)
        for mech in self.mechanisms:
            space.index(mech.drives)
            if mech.drives not in self.population_variables:
                raise ValueError(
                    f"{mech.mechanism_id} drives {mech.drives}, which is not declared a population "
                    "variable; a mechanism cannot change the scale of what it moves")
        for conf in self.confounders:
            domain = space.variable(conf.could_produce).domain
            bad = [v for v in conf.reading if v not in domain]
            if bad:
                raise ValueError(f"{conf.process_id}: {bad} not in {conf.could_produce}'s domain")

    def undeclared_movers(self, space: StateSpace, moved: tuple[str, ...]) -> tuple[str, ...]:
        """Population variables an architecture moves with no mechanism saying what makes it selective."""
        declared = {m.drives for m in self.mechanisms}
        return tuple(sorted(v for v in moved
                            if v in self.population_variables and v not in declared))

    def gaps(self, outcome_variables: tuple[str, ...], observed: tuple[str, ...]) -> tuple[ConfounderGap, ...]:
        """Where a population reading cannot be trusted because what could fake it is unmeasured."""
        seen = set(observed)
        out: list[ConfounderGap] = []
        for conf in sorted(self.confounders, key=lambda c: (c.could_produce, c.process_id)):
            if conf.could_produce not in outcome_variables:
                continue
            missing = tuple(o for o in conf.excluded_by if o not in seen)
            if missing:
                out.append(ConfounderGap(
                    variable=conf.could_produce, process_id=conf.process_id,
                    missing_observables=missing,
                    consequence=(f"{conf.could_produce} reaching {list(conf.reading)} would look the "
                                 f"same whether the architecture worked or {conf.process_id} "
                                 "occurred; the reading supports no conclusion until "
                                 f"{list(missing)} is measured beside it")))
        return tuple(out)


def rescue_scope(scales: tuple[TransformationScale, ...]) -> str:
    """What a reached target is, and is not, evidence of.

    A population-scale success is a statement about the composition of the population. It is not a
    statement that any cell was corrected, and the report says so in the same breath as the result.
    """
    if TransformationScale.INTRACELLULAR in scales:
        return ("the target is reached at the scale of the individual cell under this model; "
                "population composition is a separate claim")
    if TransformationScale.POPULATION in scales or TransformationScale.TISSUE_FUNCTION in scales:
        return ("the target is reached at the population or tissue scale only. No cell is corrected "
                "by this architecture, and the result is not evidence of cellular rescue")
    return "no scale is declared for this architecture, so what was reached is undefined"
