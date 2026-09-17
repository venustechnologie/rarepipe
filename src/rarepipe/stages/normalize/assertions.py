"""CaseAssertions: externally supplied facts, as versioned data.

Facts a computation cannot establish (a sample's role, that a listed HPO set
means 'observed', which sample a FASTQ set belongs to) enter the pipeline only
through this artifact — with evidence, author and time — never through code.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0.0"

ROLE_VALUES = {"proband", "mother", "father", "sibling", "other_relative"}
POLARITY_VALUES = {"observed", "excluded"}


class Subject(BaseModel):
    type: Literal["sample", "phenotype_set", "hpo_term", "raw_read_set"]
    id: str = Field(description="SAMPLE_nnn | ASSET_* | HP:nnnnnnn | 'ALL' (phenotype_set / raw_read_set)")


class Evidence(BaseModel):
    type: Literal["organizer_documentation", "challenge_documentation", "clinical_record", "operator_verification", "other"]
    reference: str
    note: str | None = None


class Assertion(BaseModel):
    assertion_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    subject: Subject
    predicate: Literal["role", "phenotype_polarity", "sample_linkage"]
    value: str
    evidence: Evidence
    asserted_by: str
    asserted_at: str

    @model_validator(mode="after")
    def _shape(self):
        allowed = {
            "role": ({"sample"}, lambda v: v in ROLE_VALUES),
            "phenotype_polarity": ({"phenotype_set", "hpo_term"}, lambda v: v in POLARITY_VALUES),
            "sample_linkage": ({"raw_read_set"}, lambda v: bool(re.match(r"^SAMPLE_\d{3,}$", v))),
        }
        subject_types, value_ok = allowed[self.predicate]
        if self.subject.type not in subject_types:
            raise ValueError(f"predicate '{self.predicate}' cannot apply to subject type '{self.subject.type}'")
        if not value_ok(self.value):
            raise ValueError(f"invalid value for predicate '{self.predicate}'")
        return self


class CaseAssertions(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": "CaseAssertions", "version": SCHEMA_VERSION}, alias="schema")
    case_id: str
    assertions: list[Assertion]

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [a.assertion_id for a in self.assertions]
        if len(ids) != len(set(ids)):
            raise ValueError("assertion_id values must be unique")
        return self
