"""What might physically implement a biological control — consulted only after a route exists.

The compiler decides what biological transformation is needed before this layer is asked anything.
Mapping runs only for controls on a strategy that reaches the target under at least one
evidence-consistent variant, so it cannot produce an intervention list before the control
objective is defined. It lists classes and their evidence; it does not recommend.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.provenance import Immutable


class ActuatorClass(StrEnum):
    SMALL_MOLECULE = "small_molecule"
    APPROVED_PHARMACEUTICAL = "approved_pharmaceutical"
    EXPERIMENTAL_COMPOUND = "experimental_compound"
    ASO = "aso"
    SIRNA = "sirna"
    MRNA = "mrna"
    GENE_REGULATION = "gene_regulation"
    GENE_EDITING = "gene_editing"
    PROTEIN_DEGRADER = "protein_degrader"
    PROTEIN_STABILIZER = "protein_stabilizer"
    METABOLIC_INTERVENTION = "metabolic_intervention"
    COMBINATION = "combination"


class ActuatorCandidate(Immutable):
    actuator_id: str = Field(min_length=1)
    implements_control: str
    actuator_class: ActuatorClass
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1, description="What supports it, with its cap. Never empty.")
    evidence_refs: tuple[str, ...] = ()
    feasibility: Feasibility
    attribution_observables: tuple[str, ...] = Field(
        (), description="What must be measured to attribute an effect to this actuator's mechanism.")


class ActuatorMapping(Immutable):
    control_id: str
    candidates: tuple[ActuatorCandidate, ...]
    note: str


class RouteRequired(ValueError):
    """Asked for actuators before any route exists."""


def map_actuators(controls_on_working_routes: tuple[str, ...],
                  registry: tuple[ActuatorCandidate, ...]) -> tuple[ActuatorMapping, ...]:
    if not controls_on_working_routes:
        raise RouteRequired("no control lies on a route that reaches the target under any variant; "
                            "mapping actuators now would produce an intervention list before the "
                            "control objective is met")
    out = []
    for cid in sorted(controls_on_working_routes):
        matches = tuple(sorted((a for a in registry if a.implements_control == cid),
                               key=lambda a: a.actuator_id))
        out.append(ActuatorMapping(
            control_id=cid, candidates=matches,
            note=("Classes that could implement this transformation, each with its own evidence. "
                  "None is recommended; none has been assessed for feasibility in the relevant "
                  "cell type.") if matches else "no actuator class is registered for this control",
        ))
    return tuple(out)
