"""Biological dynamics as inspectable relationships. No anonymous constants.

A relationship is either fully specified — an explicit finite table, with provenance for the whole
table — or explicitly UNKNOWN_FUNCTION. There is no third state in which a relationship is simply
absent and the variable quietly keeps its value: a non-exogenous variable without a defining
relationship is a missing relationship, and the compiler reports it as a blocker.

Competing mechanistic hypotheses are represented two ways, and the difference matters to the
result. Named alternative MODELS that are each fully specified and evidence-compatible produce
MODEL_DISAGREEMENT when they disagree. A single relationship whose function is UNKNOWN produces
CONTROL_INDETERMINATE naming that relationship.
"""
from __future__ import annotations

from enum import StrEnum
from itertools import product
from typing import Literal

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import Immutable, Provenance
from rarepipe.stages.control.state_space import StateSpace

Table = tuple[tuple[tuple[str, ...], str], ...]


class RelationshipKind(StrEnum):
    TABLE = "table"
    UNKNOWN_FUNCTION = "unknown_function"


class CandidateConstraint(StrEnum):
    """What is known about an unknown function, which bounds the candidates enumerated for it."""

    ANY = "any"
    MONOTONE_NONDECREASING = "monotone_nondecreasing"


class NamedHypothesis(Immutable):
    label: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    table: Table


class Relationship(Immutable):
    relationship_id: str = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    output: str = Field(min_length=1)
    kind: RelationshipKind
    table: Table = ()
    candidate_constraint: CandidateConstraint = CandidateConstraint.ANY
    candidate_constraint_rationale: str = ""
    named_hypotheses: tuple[NamedHypothesis, ...] = ()
    epistemic_status: Literal["established", "assumed", "unresolved"]
    provenance: Provenance
    support: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    validity_domain: str = Field(min_length=1)
    required_for: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _kind_is_honest(self):
        if self.output in self.inputs:
            raise ValueError(f"{self.relationship_id}: output cannot be its own input")
        if self.kind is RelationshipKind.TABLE:
            if not self.table:
                raise ValueError(f"{self.relationship_id}: a TABLE relationship needs its table")
            if self.epistemic_status == "unresolved":
                raise ValueError(f"{self.relationship_id}: an unresolved relationship is UNKNOWN_FUNCTION")
        else:
            if self.table:
                raise ValueError(f"{self.relationship_id}: an unknown function has no table")
            if self.epistemic_status != "unresolved":
                raise ValueError(f"{self.relationship_id}: UNKNOWN_FUNCTION must be marked unresolved")
            if (self.candidate_constraint is not CandidateConstraint.ANY
                    and not self.candidate_constraint_rationale):
                raise ValueError(
                    f"{self.relationship_id}: constraining an unknown function narrows what the "
                    "compiler considers possible; state why, or the narrowing is an assumption "
                    "nobody made")
        return self


def _check_table(rel_id: str, space: StateSpace, inputs: tuple[str, ...], output: str,
                 table: Table, label: str) -> dict[tuple[str, ...], str]:
    domains = [space.variable(i).domain for i in inputs]
    expected = set(product(*domains))
    mapping = dict(table)
    if len(mapping) != len(table):
        raise ValueError(f"{rel_id} {label}: an input combination appears twice")
    if set(mapping) != expected:
        missing = sorted(expected - set(mapping))
        raise ValueError(f"{rel_id} {label}: table is not total; missing {missing[:3]}")
    out_domain = space.variable(output).domain
    bad = sorted({v for v in mapping.values() if v not in out_domain})
    if bad:
        raise ValueError(f"{rel_id} {label}: values {bad} are not in {output}'s domain")
    return mapping


class Plausibility(StrEnum):
    ACCEPTED = "accepted"
    PLAUSIBLE_ALTERNATIVE = "plausible_alternative"


class Model(Immutable):
    model_id: str = Field(min_length=1)
    plausibility: Plausibility
    statement: str = Field(min_length=1)
    relationships: tuple[Relationship, ...]
    provenance: Provenance

    def check(self, space: StateSpace) -> None:
        outputs: dict[str, str] = {}
        for rel in self.relationships:
            for name in (*rel.inputs, rel.output):
                space.index(name)
            if rel.output in outputs:
                raise ValueError(
                    f"{self.model_id}: {rel.output} is defined by both {outputs[rel.output]} and "
                    f"{rel.relationship_id}; combine them into one relationship")
            outputs[rel.output] = rel.relationship_id
            if space.variable(rel.output).exogenous:
                raise ValueError(
                    f"{self.model_id}: {rel.output} is declared exogenous but "
                    f"{rel.relationship_id} defines it")
            if rel.kind is RelationshipKind.TABLE:
                _check_table(rel.relationship_id, space, rel.inputs, rel.output, rel.table, "table")
            for hyp in rel.named_hypotheses:
                _check_table(rel.relationship_id, space, rel.inputs, rel.output, hyp.table,
                             f"hypothesis {hyp.label}")

    def defining(self, variable: str) -> Relationship | None:
        return next((r for r in self.relationships if r.output == variable), None)
