"""What a qualitative state means, so a change cannot be mistaken for a restored function.

A state model that represents `checkpoint_activation` as a number above a threshold cannot tell the
difference between a checkpoint that arrests division when it should and a cell that has simply been
stopped from dividing at all. Both would read as "activation high". Biologically they are opposites:
one is the function, the other is the loss of it.

So a state the gap asks for carries a specification of the behaviour required, and an effect reported
in the literature does not satisfy it without a mapping that says why:

    increase(X)  does not imply  X = normal

`FunctionalEffectMapping` is the only way the two connect, it needs evidence of its own, and there is
no global rule. A source reporting that something strengthens a signal has not reported that the
signal became appropriate.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.kinds import Effect


class FunctionalSemantics(Immutable):
    """What `normal` requires of a variable, beyond a level."""

    variable: str = Field(min_length=1)
    state: str = Field(min_length=1)
    requires: tuple[str, ...] = Field(
        min_length=2,
        description="Behaviours the state requires. At least two, because a single condition is a "
                    "threshold wearing a name.")
    excludes: tuple[str, ...] = Field(
        min_length=1,
        description="States that would satisfy a naive reading and are not this one — permanent "
                    "hyperactivation, activation out of context, absence of activation.")
    rationale: str = Field(min_length=20)


class FunctionalEffectMapping(Immutable):
    """`increase(X)` becomes `X = normal` only here, and only with evidence."""

    mapping_id: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    source_effect: Effect
    target_state: str = Field(min_length=1)
    conditions: tuple[str, ...] = Field(
        min_length=1, description="What must hold for the effect to constitute the state.")
    evidence_claims: tuple[str, ...] = Field(
        min_length=1, description="Claims establishing that the effect restores appropriate "
                                  "function, not merely a higher level.")
    validity_domain: str = Field(min_length=10)
    provenance: Provenance

    @model_validator(mode="after")
    def _typed(self):
        if self.provenance.epistemic_type not in {EpistemicType.LITERATURE_EVIDENCE,
                                                  EpistemicType.MODEL_ASSUMPTION}:
            raise ValueError(f"{self.mapping_id}: a mapping rests on literature or on a stated "
                             "model assumption, never on nothing")
        return self


class SemanticsRegistry(Immutable):
    semantics: tuple[FunctionalSemantics, ...] = ()
    mappings: tuple[FunctionalEffectMapping, ...] = ()

    def for_state(self, variable: str, state: str) -> FunctionalSemantics | None:
        return next((s for s in self.semantics
                     if s.variable == variable and s.state == state), None)

    def mapping(self, variable: str, effect: Effect, state: str) -> FunctionalEffectMapping | None:
        return next((m for m in self.mappings if m.variable == variable
                     and m.source_effect is effect and m.target_state == state), None)

    def satisfies(self, variable: str, effect: Effect, state: str) -> tuple[bool, str]:
        """Does an effect of this direction constitute this state? Only a mapping can say yes."""
        if not state:
            return True, "the gap asks for a direction, not a qualitative state"
        if effect is Effect.SET:
            return True, "the claim reports the state itself, not a change in it"
        found = self.mapping(variable, effect, state)
        if found is None:
            specification = self.for_state(variable, state)
            excluded = list(specification.excludes) if specification else []
            return False, (
                f"{effect.value}({variable}) does not constitute {variable}={state}: no "
                f"FunctionalEffectMapping establishes it"
                + (f", and {state} is specified to exclude {excluded}" if excluded else ""))
        return True, (f"mapping {found.mapping_id} establishes that {effect.value}({variable}) "
                      f"constitutes {variable}={state}, conditional on {list(found.conditions)}")
