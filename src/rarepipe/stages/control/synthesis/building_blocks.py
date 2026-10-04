"""The registry stores what a piece can *do*, not what it is called.

A registry of drug names would answer "what could we give?", which is the question this project is
built to stop asking first. A building block is stored as a typed transformation of state —
"holds this variable at this value, in this cell type, under these conditions" — so the compiler
can compose pieces without ever consulting a therapeutic indication.

Two rules keep the layer honest:

* **Off-target and safety effects are transformations too.** A block that depletes a population
  declares that as a state transformation, not as a footnote, so the hard safety filter sees it.
  A declared risk that lives only in prose cannot reject anything.
* **Reversibility must say what reverts.** A block declared reversible must say what value its
  variable returns to and what returns it. Without that, releasing it — in a feedback loop or when
  asking whether the state survives withdrawal — would invent a reversion mechanism the model does
  not contain.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.controls import (
    BiologicalControlKind, ControlVariable, Feasibility, RouteClass,
)
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.state_space import StateSpace
from rarepipe.stages.control.synthesis.kinds import (
    BlockClass, Direction, Reversibility, TransformationScale,
)
from rarepipe.stages.control.target_constraints import Membership

_BLOCK_TYPES = {EpistemicType.BUILDING_BLOCK_CAPABILITY, EpistemicType.LITERATURE_EVIDENCE,
                EpistemicType.INFERRED_HYPOTHESIS}


class BlockTransformation(Immutable):
    """L: X -> X'. One variable held at one value, with its direction and scale declared."""

    variable: str
    to: str
    direction: Direction
    scale: TransformationScale
    control_kind: BiologicalControlKind
    intended: bool = Field(
        True, description="False for a declared off-target or population effect. Unintended "
                          "transformations are composed and safety-checked exactly like intended "
                          "ones.")
    released_to: str | None = None
    release_rationale: str = ""
    magnitude_if_known: str = Field("", description="Left empty unless measured. Never estimated.")
    time_dependence_if_known: str = ""

    @model_validator(mode="after")
    def _release_is_accounted_for(self):
        if self.released_to is not None and not self.release_rationale:
            raise ValueError(
                f"{self.variable}: a release value asserts the variable returns there when the "
                "block stops acting — name what returns it")
        return self


class BuildingBlock(Immutable):
    building_block_id: str = Field(min_length=1)
    block_class: BlockClass
    mechanism: str = Field(min_length=20, description="What it does biologically, not its name.")
    route_class: RouteClass
    input_state_requirements: tuple[Membership, ...] = Field(
        (), description="States in which the block can act. Composition checks these, so a block "
                        "that needs a precondition cannot be applied before it holds.")
    state_transformations: tuple[BlockTransformation, ...] = Field(min_length=1)
    scale: TransformationScale
    reversibility: Reversibility
    cell_type: str = Field(min_length=1)
    tissue_context: str = Field(min_length=1)
    delivery_requirements: str = Field(min_length=1)
    known_off_targets: tuple[str, ...] = ()
    population_effects: tuple[str, ...] = ()
    safety_effects: tuple[str, ...] = ()
    evidence: str = Field(min_length=1, description="What supports it, with its limit. Never empty.")
    evidence_refs: tuple[str, ...] = ()
    validity_domain: str = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    feasibility_status: Feasibility
    feasibility_note: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _typed_and_consistent(self):
        if self.provenance.epistemic_type not in _BLOCK_TYPES:
            raise ValueError(
                f"{self.building_block_id}: a building block carries BUILDING_BLOCK_CAPABILITY, "
                "LITERATURE_EVIDENCE or INFERRED_HYPOTHESIS provenance")
        if self.reversibility is Reversibility.REVERSIBLE:
            missing = [t.variable for t in self.state_transformations if t.released_to is None]
            if missing:
                raise ValueError(
                    f"{self.building_block_id}: declared reversible but {missing} have no release "
                    "value; reversibility that cannot be evaluated is not reversibility")
        if self.reversibility is Reversibility.IRREVERSIBLE:
            declared = [t.variable for t in self.state_transformations if t.released_to is not None]
            if declared:
                raise ValueError(
                    f"{self.building_block_id}: declared irreversible but {declared} declare a "
                    "release value")
        quantified = [t.variable for t in self.state_transformations
                      if t.magnitude_if_known or t.time_dependence_if_known]
        if quantified and not self.evidence_refs:
            raise ValueError(
                f"{self.building_block_id}: {quantified} carry a magnitude or a time dependence "
                "with nothing cited; a quantitative constant without provenance is a guess wearing "
                "a number")
        held = {}
        for t in self.state_transformations:
            if t.variable in held and held[t.variable] != t.to:
                raise ValueError(
                    f"{self.building_block_id}: holds {t.variable} at both {held[t.variable]!r} "
                    f"and {t.to!r}")
            held[t.variable] = t.to
        return self

    def check(self, space: StateSpace) -> None:
        for t in self.state_transformations:
            domain = space.variable(t.variable).domain
            if t.to not in domain:
                raise ValueError(
                    f"{self.building_block_id}: {t.to!r} is not in {t.variable}'s domain {domain}")
            if t.released_to is not None and t.released_to not in domain:
                raise ValueError(
                    f"{self.building_block_id}: release value {t.released_to!r} is not in "
                    f"{t.variable}'s domain {domain}")
        for req in self.input_state_requirements:
            space.index(req.variable)

    def controls(self) -> tuple[ControlVariable, ...]:
        """Expand into engine controls — one per transformation, all held together.

        The provenance type travels: a block that is somebody's hypothesis produces controls that
        are still hypotheses, and feasibility is the block's, never upgraded by composition.
        """
        kind = (EpistemicType.INFERRED_HYPOTHESIS
                if self.provenance.epistemic_type is EpistemicType.INFERRED_HYPOTHESIS
                else EpistemicType.COMPOSED_CONTROL)
        out = []
        for t in self.state_transformations:
            intent = "intended effect" if t.intended else "declared off-target effect"
            out.append(ControlVariable(
                control_id=f"{self.building_block_id}::{t.variable}",
                sets=t.variable, to=t.to, kind=t.control_kind, route_class=self.route_class,
                interpretation=(f"{self.mechanism} — {intent}: {t.direction.value} {t.variable} "
                                f"to {t.to} at {t.scale.value} scale"),
                feasibility=self.feasibility_status, feasibility_note=self.feasibility_note,
                released_to=t.released_to, release_rationale=t.release_rationale,
                provenance=Provenance(
                    epistemic_type=kind,
                    source=f"building block {self.building_block_id} ({self.block_class.value})",
                    proposed_by=self.provenance.proposed_by, references=self.evidence_refs,
                    rationale=f"composed from {self.building_block_id}; {self.uncertainty}"),
            ))
        return tuple(out)

    @property
    def scales(self) -> tuple[TransformationScale, ...]:
        return tuple(sorted({t.scale for t in self.state_transformations}))

    @property
    def variables(self) -> tuple[str, ...]:
        return tuple(sorted({t.variable for t in self.state_transformations}))

    def can_act_in(self, space: StateSpace, state) -> bool:
        return all(r.holds(space, state) for r in self.input_state_requirements)


class BuildingBlockRegistry(Immutable):
    blocks: tuple[BuildingBlock, ...] = ()

    @model_validator(mode="after")
    def _unique(self):
        ids = [b.building_block_id for b in self.blocks]
        if len(set(ids)) != len(ids):
            raise ValueError("building block ids must be unique")
        return self

    def check(self, space: StateSpace) -> None:
        for block in self.blocks:
            block.check(space)

    def get(self, block_id: str) -> BuildingBlock:
        for block in self.blocks:
            if block.building_block_id == block_id:
                return block
        raise KeyError(f"no building block {block_id!r}")

    def acting_on(self, variable: str) -> tuple[BuildingBlock, ...]:
        return tuple(sorted((b for b in self.blocks if variable in b.variables),
                            key=lambda b: b.building_block_id))

    def usable(self) -> tuple[BuildingBlock, ...]:
        """Blocks that are not ruled out. An unassessed block stays in: its feasibility is the
        open question, not a reason to refuse to reason about it."""
        return tuple(sorted((b for b in self.blocks
                             if b.feasibility_status is not Feasibility.INFEASIBLE),
                            key=lambda b: b.building_block_id))

    def controls(self) -> dict[str, ControlVariable]:
        return {c.control_id: c for b in self.usable() for c in b.controls()}
