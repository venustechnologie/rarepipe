"""Epistemic typing and provenance. Every object says what kind of knowledge it is."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rarepipe.stages.prospective.model import Actor, ActorType, Role


class Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EpistemicType(StrEnum):
    """What kind of knowledge an object is. A SIMULATED_PREDICTION never becomes OBSERVED_EMPIRICAL."""

    OBSERVED_EMPIRICAL = "observed_empirical"
    LITERATURE_EVIDENCE = "literature_evidence"
    MODEL_ASSUMPTION = "model_assumption"
    EXTRACTED_PARAMETER = "extracted_parameter"
    SIMULATED_PREDICTION = "simulated_prediction"
    INFERRED_HYPOTHESIS = "inferred_hypothesis"
    DECISION_RULE = "decision_rule"
    TARGET_CONSTRAINT = "target_constraint"
    SAFETY_CONSTRAINT = "safety_constraint"
    CONTROL_VARIABLE = "control_variable"
    CONTROL_CAPABILITY = "control_capability"


# Types that assert something was measured or published. Each must name what it rests on.
_NEEDS_REFERENCES = {EpistemicType.OBSERVED_EMPIRICAL, EpistemicType.LITERATURE_EVIDENCE,
                     EpistemicType.EXTRACTED_PARAMETER}


class Provenance(Immutable):
    epistemic_type: EpistemicType
    source: str = Field(min_length=1, description="Where this came from, in words a reviewer can follow.")
    proposed_by: str = Field(min_length=1, description="Who or what put it here: a person, a skill, a plan seed.")
    references: tuple[str, ...] = ()
    rationale: str = ""

    @model_validator(mode="after")
    def _claims_name_what_they_rest_on(self):
        if self.epistemic_type in _NEEDS_REFERENCES and not self.references:
            raise ValueError(
                f"{self.epistemic_type.value} provenance must cite what it rests on; an uncited "
                "observation or literature claim is an assertion"
            )
        if self.epistemic_type is EpistemicType.MODEL_ASSUMPTION and not self.rationale:
            raise ValueError("a model assumption must state its rationale, or it is an anonymous constant")
        return self


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    PROPOSED = "proposed"
    UNSPECIFIED = "unspecified"


_APPROVING_ROLES = {Role.SCIENTIFIC_LEAD, Role.TREATING_CLINICIAN}


class Approval(Immutable):
    """Who is accountable for a target or safety definition.

    The software must not invent thresholds, and no agent may approve one. APPROVED requires a human
    holding a scientific-lead or treating-clinician role. UNSPECIFIED means the definition is
    missing and must say why; the compiler then cannot say what success is.
    """

    status: ApprovalStatus
    approver: Actor | None = None
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def _only_an_accountable_human_approves(self):
        if self.status is ApprovalStatus.APPROVED:
            if self.approver is None:
                raise ValueError("an approved definition must name its approver")
            if self.approver.actor_type is not ActorType.HUMAN:
                raise ValueError("only a human can approve a target or safety definition; an agent cannot")
            if not _APPROVING_ROLES.intersection(self.approver.roles):
                raise ValueError("approval requires a scientific lead or treating clinician")
        elif self.approver is not None:
            raise ValueError(f"a {self.status.value} definition has no approver")
        return self
