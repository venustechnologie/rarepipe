"""Control variables are biological transformations, not drugs.

The compiler first determines what biological change is needed. Only afterwards does a separate
layer (actuator_registry) ask what physical intervention might implement it. A control here says
"BubR1 abundance is held at restored", never "give nicotinic acid".
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance


class BiologicalControlKind(StrEnum):
    PROTEIN_ABUNDANCE = "protein_abundance"
    PROTEIN_STABILITY = "protein_stability"
    PROTEIN_DEGRADATION = "protein_degradation"
    ENZYMATIC_ACTIVITY = "enzymatic_activity"
    LOCALIZATION = "localization"
    POST_TRANSLATIONAL_MODIFICATION = "post_translational_modification"
    PROTEIN_PROTEIN_INTERACTION = "protein_protein_interaction"
    TRANSCRIPTION = "transcription"
    TRANSLATION = "translation"
    METABOLITE_CONCENTRATION = "metabolite_concentration"
    PATHWAY_ACTIVATION = "pathway_activation"
    PATHWAY_INHIBITION = "pathway_inhibition"
    FUNCTIONAL_REPLACEMENT = "functional_replacement"


class RouteClass(StrEnum):
    """Repairing the original mechanism is one route among several. The target is the invariant."""

    REPAIR = "repair"
    STABILIZATION = "stabilization"
    COMPENSATION = "compensation"
    BYPASS = "bypass"
    SUPPRESSION = "suppression"
    REPLACEMENT = "replacement"
    REWIRING = "rewiring"


class Feasibility(StrEnum):
    ESTABLISHED = "established"
    UNASSESSED = "unassessed"
    INFEASIBLE = "infeasible"


class ControlVariable(Immutable):
    control_id: str = Field(min_length=1)
    sets: str = Field(min_length=1, description="The state variable this control holds.")
    to: str = Field(min_length=1)
    kind: BiologicalControlKind
    route_class: RouteClass
    interpretation: str = Field(
        min_length=20, description="What the transformation is, biologically. Never a drug name.")
    feasibility: Feasibility
    feasibility_note: str = Field(min_length=1)
    released_to: str | None = Field(
        None, description="The value the variable takes when this control stops being held. "
                          "Required before withdrawal or feedback release can be evaluated: "
                          "without it, releasing a control would silently invent a reversion "
                          "mechanism that nothing in the model provides.")
    release_rationale: str = ""
    provenance: Provenance

    @property
    def releasable(self) -> bool:
        return self.released_to is not None

    @model_validator(mode="after")
    def _typed(self):
        if self.released_to is not None and not self.release_rationale:
            raise ValueError(
                f"{self.control_id}: declaring a release value asserts that the variable returns "
                "there on withdrawal — say what returns it, or stability would rest on an "
                "unstated mechanism")
        if self.provenance.epistemic_type not in {EpistemicType.CONTROL_VARIABLE,
                                                  EpistemicType.INFERRED_HYPOTHESIS,
                                                  EpistemicType.COMPOSED_CONTROL}:
            raise ValueError("a control variable carries CONTROL_VARIABLE, COMPOSED_CONTROL or "
                             "INFERRED_HYPOTHESIS provenance")
        return self
