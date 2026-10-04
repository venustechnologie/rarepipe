"""A capability gap is a specification, not a question.

The previous phase could say "to build this we would need a piece that does X". A gap turns that
sentence into a formal object with an interface a candidate either satisfies or does not: the
transformation required, the direction, the context, the scale, and — for a bypass — the
dependencies that are forbidden.

The search specification derived from a gap is what gets handed to a source provider. It is
deliberately not prose. "Investigate the checkpoint" invites a model to retrieve whatever it
associates with the word; a contract stating the required output, the forbidden dependency and the
context is something a provider can be wrong about in a way that a validator can catch.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.realization.kinds import Effect, EpistemicBurden
from rarepipe.stages.control.discovery.kinds import GapStatus


class RequiredContext(Immutable):
    """The context a capability has to hold in. Each dimension is checked separately."""

    agent: str = Field("", description="What may be administered. Empty means unconstrained.")
    compartment: str = Field("", description="Where the change must occur.")
    system: str = Field(min_length=1, description="Species, cell type or model required.")

    def dimension(self, name: str) -> str:
        return {"agent": self.agent, "compartment": self.compartment, "system": self.system}[name]


class CapabilityGap(Immutable):
    gap_id: str = Field(min_length=1)
    required_transformation: str = Field(min_length=1)
    required_input: str = Field(
        "", description="The node a capability must act on. Empty means any input is acceptable, "
                        "which is the normal case for a discovery gap.")
    required_output: str = Field(min_length=1)
    required_value: str = Field("", description="For a categorical output, the value required.")
    required_direction: Effect
    forbidden_dependencies: tuple[str, ...] = Field(
        (), description="Nodes that must not appear anywhere upstream of the output under the "
                        "candidate's own mechanism. This is what makes a bypass gap a bypass.")
    required_context: RequiredContext
    biological_scale: str = Field(min_length=1)
    required_outputs: tuple[str, ...] = Field(
        (), description="Further outputs the same capability must produce, if any.")
    allowed_side_effects: tuple[str, ...] = ()
    forbidden_states: tuple[str, ...] = Field(
        (), description="States a candidate may not drive the system into, as 'variable=value'.")
    epistemic_burden: EpistemicBurden
    observables_needed: tuple[str, ...] = ()
    current_known_paths: tuple[str, ...] = Field(
        (), description="What the inventory already holds for this output, so the gap says what is "
                        "being added to rather than implying a blank page.")
    current_missing_reason: str = Field(min_length=10)
    status: GapStatus = GapStatus.OPEN
    rationale: str = Field(min_length=10)

    @model_validator(mode="after")
    def _coherent(self):
        if self.required_input and self.required_input == self.required_output:
            raise ValueError(f"{self.gap_id}: a transformation cannot have the same input and output")
        if self.required_output in self.forbidden_dependencies:
            raise ValueError(
                f"{self.gap_id}: {self.required_output} is both the required output and a forbidden "
                "dependency, which no candidate could ever satisfy")
        for state in self.forbidden_states:
            if "=" not in state:
                raise ValueError(f"{self.gap_id}: forbidden state {state!r} must be 'variable=value'")
        return self


class SearchSpecification(Immutable):
    """The contract handed to a source provider. Not a prompt, and not a topic."""

    gap_id: str
    required_output: str
    required_value: str = ""
    required_direction: Effect
    required_input: str = ""
    must_not_require: tuple[str, ...] = ()
    context: RequiredContext
    scale: str
    minimum_evidence_condition: str = Field(
        "a mechanistic or experimental relation capable of grounding the required transformation",
        description="Stated so a provider returning something weaker is returning a miss, not a hit.")
    returns: tuple[str, ...] = ("mechanisms", "candidates", "blockers")


def specification(gap: CapabilityGap) -> SearchSpecification:
    return SearchSpecification(
        gap_id=gap.gap_id, required_output=gap.required_output, required_value=gap.required_value,
        required_direction=gap.required_direction, required_input=gap.required_input,
        must_not_require=gap.forbidden_dependencies, context=gap.required_context,
        scale=gap.biological_scale)
