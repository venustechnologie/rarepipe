"""Uncertainty stays explicit: unknown functions and unknown initial states are both sets.

**Unknown functions are universally quantified, and fixed for a whole trajectory.** An
UNKNOWN_FUNCTION relationship is expanded into every function consistent with what is known about
it. Each candidate becomes a separate model variant, and the function is held fixed across that
variant's entire trajectory — biology does not change its laws mid-experiment. Treating an unknown
as free to take whatever value helps at each step would let the search exploit ignorance and
report reachability that no single biology supports.

**The initial state is a set.** X0 is every state compatible with the recorded evidence and at
steady state under the variant's uncontrolled dynamics. A variant that admits no such state is
falsified by the evidence and is excluded — and reported as excluded — rather than counted, because
"the strategy works for every initial state" is vacuously true of an empty set.
"""
from __future__ import annotations

from itertools import product

from pydantic import Field

from rarepipe.stages.control.dynamics import (
    CandidateConstraint, Model, Plausibility, Relationship, RelationshipKind,
)
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.state_space import State, StateSpace, VariableKind

CANDIDATE_LIMIT = 64
STATE_LIMIT = 1 << 18


class TooBroadToEnumerate(ValueError):
    """An unknown relationship with too many consistent functions to quantify over."""


class StateEvidence(Immutable):
    """What the case evidence says about one variable's current value."""

    evidence_id: str = Field(min_length=1)
    variable: str
    allowed: tuple[str, ...] = Field(min_length=1)
    provenance: Provenance
    generated_under: str = Field(
        min_length=1,
        description="The plan, schema or rule version this evidence was produced under. An "
                    "observation stays attached to the version that generated it.")


class Function(Immutable):
    relationship_id: str
    inputs: tuple[str, ...]
    output: str
    mapping: tuple[tuple[tuple[str, ...], str], ...]
    epistemic_status: str
    candidate_label: str | None = None

    def lookup(self) -> dict[tuple[str, ...], str]:
        return dict(self.mapping)


class Variant(Immutable):
    """One fully resolved biology: a model, with one candidate chosen for each unknown."""

    variant_id: str
    model_id: str
    plausibility: Plausibility
    choices: tuple[tuple[str, str], ...]
    functions: tuple[Function, ...]


def _is_monotone(space: StateSpace, rel: Relationship, mapping: dict[tuple[str, ...], str]) -> bool:
    out = space.variable(rel.output)
    ins = [space.variable(i) for i in rel.inputs]
    for a, b in product(mapping, repeat=2):
        if all(v.rank(x) <= v.rank(y) for v, x, y in zip(ins, a, b)):
            if out.rank(mapping[a]) > out.rank(mapping[b]):
                return False
    return True


def candidates(space: StateSpace, rel: Relationship) -> list[tuple[str, dict[tuple[str, ...], str]]]:
    """Every function consistent with what is known, labelled with any hypothesis it matches."""
    domains = [space.variable(i).domain for i in rel.inputs]
    keys = list(product(*domains))
    out_domain = space.variable(rel.output).domain
    if len(out_domain) ** len(keys) > CANDIDATE_LIMIT * 16:
        raise TooBroadToEnumerate(
            f"{rel.relationship_id}: {len(out_domain) ** len(keys)} candidate functions — narrow it "
            "with a stated constraint or a named hypothesis before asking what it implies")
    if rel.candidate_constraint is CandidateConstraint.MONOTONE_NONDECREASING:
        if any(space.variable(n).kind is not VariableKind.ORDINAL for n in (*rel.inputs, rel.output)):
            raise ValueError(f"{rel.relationship_id}: monotonicity needs ordinal variables")
    named = {tuple(sorted(h.table)): h.label for h in rel.named_hypotheses}
    found: list[tuple[str, dict[tuple[str, ...], str]]] = []
    unnamed = 0
    for values in product(out_domain, repeat=len(keys)):
        mapping = dict(zip(keys, values))
        if (rel.candidate_constraint is CandidateConstraint.MONOTONE_NONDECREASING
                and not _is_monotone(space, rel, mapping)):
            continue
        label = named.get(tuple(sorted(mapping.items())))
        if label is None:
            unnamed += 1
            label = f"unnamed_{unnamed}"
        found.append((label, mapping))
    if len(found) > CANDIDATE_LIMIT:
        raise TooBroadToEnumerate(f"{rel.relationship_id}: {len(found)} consistent functions")
    return found


def expand(space: StateSpace, model: Model) -> list[Variant]:
    """The model's variants: one per combination of candidates for its unknown relationships."""
    model.check(space)
    fixed: list[Function] = []
    unknown: list[tuple[Relationship, list[tuple[str, dict]]]] = []
    for rel in sorted(model.relationships, key=lambda r: r.relationship_id):
        if rel.kind is RelationshipKind.TABLE:
            fixed.append(Function(relationship_id=rel.relationship_id, inputs=rel.inputs,
                                  output=rel.output, mapping=tuple(sorted(rel.table)),
                                  epistemic_status=rel.epistemic_status))
        else:
            unknown.append((rel, candidates(space, rel)))
    variants: list[Variant] = []
    for combo in product(*(options for _, options in unknown)):
        chosen = list(fixed)
        choices = []
        for (rel, _), (label, mapping) in zip(unknown, combo):
            chosen.append(Function(relationship_id=rel.relationship_id, inputs=rel.inputs,
                                   output=rel.output, mapping=tuple(sorted(mapping.items())),
                                   epistemic_status="unresolved", candidate_label=label))
            choices.append((rel.relationship_id, label))
        suffix = "|".join(f"{r}={lab}" for r, lab in choices) or "resolved"
        variants.append(Variant(
            variant_id=f"{model.model_id}::{suffix}", model_id=model.model_id,
            plausibility=model.plausibility, choices=tuple(choices),
            functions=tuple(sorted(chosen, key=lambda f: f.relationship_id))))
    return variants


def evidence_domains(space: StateSpace, evidence: tuple[StateEvidence, ...]) -> dict[str, tuple[str, ...]]:
    allowed: dict[str, tuple[str, ...]] = {}
    for item in evidence:
        if item.provenance.epistemic_type is EpistemicType.SIMULATED_PREDICTION:
            raise ValueError(
                f"{item.evidence_id}: a simulated prediction cannot constrain the case's initial "
                "state; simulation is not observation")
        domain = space.variable(item.variable).domain
        bad = [v for v in item.allowed if v not in domain]
        if bad:
            raise ValueError(f"{item.evidence_id}: {bad} not in {item.variable}'s domain")
        current = allowed.get(item.variable, domain)
        allowed[item.variable] = tuple(v for v in current if v in item.allowed)
    return allowed


def is_fixpoint(space: StateSpace, variant: Variant, state: State) -> bool:
    for fn in variant.functions:
        key = tuple(space.value(state, i) for i in fn.inputs)
        if fn.lookup()[key] != space.value(state, fn.output):
            return False
    return True


def initial_states(space: StateSpace, variant: Variant,
                   evidence: tuple[StateEvidence, ...]) -> tuple[State, ...]:
    """Evidence-compatible steady states of the uncontrolled variant. May be empty."""
    if space.size() > STATE_LIMIT:
        raise ValueError(f"state space of {space.size()} states exceeds the finite engine's limit")
    allowed = evidence_domains(space, evidence)
    return tuple(s for s in space.states(allowed) if is_fixpoint(space, variant, s))
