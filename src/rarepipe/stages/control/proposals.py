"""Agents propose. Deterministic validators gate.

A skill emits a typed proposal; this module decides what, if anything, it becomes. The rule that
matters most: **the gate assigns the epistemic type, never the proposer.** A proposal that claims
to be OBSERVED_EMPIRICAL or "established" is not believed on its say-so — an agent-proposed
relationship enters as an INFERRED_HYPOTHESIS at most, an agent cannot assert that a control is
feasible, and no proposal can carry a result class. A guard keyed on a flag the proposer sets is
not a guard.

Nothing here alters a frozen object. Accepted proposals become new immutable objects that a human
or the compiler may then use.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, ValidationError

from rarepipe.stages.control.controls import ControlVariable, Feasibility
from rarepipe.stages.control.dynamics import Relationship, RelationshipKind
from rarepipe.stages.control.provenance import (
    GATE_NEVER_ASSIGNS, GATE_REFUSES_CLAIM, Approval, ApprovalStatus, EpistemicType, Immutable,
    Provenance,
)
from rarepipe.stages.control.result_types import ResultClass
from rarepipe.stages.control.synthesis.architecture import ControlArchitecture
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlock
from rarepipe.stages.control.synthesis.kinds import (
    LogicalStatus, PhysicalStatus, RobustnessClass, SynthesisResultClass,
)
from rarepipe.stages.control.target_constraints import TargetConstraint
from rarepipe.stages.prospective.model import Actor, ActorType


class ProposalKind(StrEnum):
    RELATIONSHIP = "relationship"
    CONTROL = "control"
    TARGET_CONSTRAINT = "target_constraint"
    ARCHITECTURE = "architecture"
    BUILDING_BLOCK = "building_block"


class Proposal(Immutable):
    proposal_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    skill_version: str = Field(min_length=1)
    proposer: Actor
    kind: ProposalKind
    payload: dict[str, Any]
    claimed_epistemic_type: EpistemicType | None = Field(
        None, description="Recorded for audit and ignored by the gate.")
    rationale: str = Field(min_length=1)
    references: tuple[str, ...] = ()


class GateDecision(Immutable):
    proposal_id: str
    accepted: bool
    reason: str
    assigned_epistemic_type: EpistemicType | None = None
    accepted_object: dict | None = None


# An agent may not state a verdict in any of the vocabularies the compiler owns. Claiming
# robustness, logical synthesizability or physical feasibility is claiming a result.
_RESULT_WORDS = (
    {r.value for r in ResultClass}
    | {r.value for r in SynthesisResultClass}
    | {r.value for r in RobustnessClass}
    | {r.value for r in LogicalStatus}
    | {r.value for r in PhysicalStatus}
    | {"CONTROL_SOLUTION_FOUND", "VALID_CONTROL", "LOGICALLY_SYNTHESIZABLE"}
)


def _contains_result_claim(value: Any) -> bool:
    if isinstance(value, str):
        return any(word in value.upper() for word in _RESULT_WORDS)
    if isinstance(value, dict):
        return any(_contains_result_claim(k) or _contains_result_claim(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_result_claim(v) for v in value)
    return False


def _reject(p: Proposal, reason: str) -> GateDecision:
    return GateDecision(proposal_id=p.proposal_id, accepted=False, reason=reason)


def _provenance(p: Proposal, kind: EpistemicType, **extra) -> dict:
    if kind in GATE_NEVER_ASSIGNS:  # pragma: no cover — guarded by construction
        raise AssertionError(f"the gate may never assign {kind.value}")
    return Provenance(epistemic_type=kind, source=f"{p.skill_id} v{p.skill_version} proposal {p.proposal_id}",
                      proposed_by=f"{p.proposer.actor_type.value}:{p.proposer.identity}",
                      references=p.references, rationale=p.rationale, **extra).model_dump()


def gate(p: Proposal) -> GateDecision:
    if p.claimed_epistemic_type in GATE_REFUSES_CLAIM:
        return _reject(p, f"no proposal may be a {p.claimed_epistemic_type.value}: it is produced "
                          "by the deterministic validators, so it cannot also be submitted to them")
    if _contains_result_claim(p.payload):
        return _reject(p, "a proposal cannot carry a result class; only the compiler produces one, "
                          "and never from prose")
    agent = p.proposer.actor_type is not ActorType.HUMAN
    try:
        if p.kind is ProposalKind.RELATIONSHIP:
            payload = dict(p.payload)
            unknown = payload.get("kind") == RelationshipKind.UNKNOWN_FUNCTION.value
            if agent:
                # An agent may propose a relationship. It may not declare one established.
                payload["epistemic_status"] = "unresolved" if unknown else "assumed"
            assigned = EpistemicType.INFERRED_HYPOTHESIS
            payload["provenance"] = _provenance(p, assigned)
            obj = Relationship(**payload)
        elif p.kind is ProposalKind.CONTROL:
            payload = dict(p.payload)
            if agent and payload.get("feasibility") != Feasibility.UNASSESSED.value:
                payload["feasibility"] = Feasibility.UNASSESSED.value
                payload["feasibility_note"] = ("feasibility asserted by an agent is not accepted; "
                                               "recorded as unassessed")
            assigned = EpistemicType.INFERRED_HYPOTHESIS
            payload["provenance"] = _provenance(p, assigned)
            obj = ControlVariable(**payload)
        elif p.kind is ProposalKind.ARCHITECTURE:
            payload = dict(p.payload)
            # An architecture an agent imagined is a PROPOSED_ARCHITECTURE and nothing more. The
            # compiler decides whether it reaches anything; the proposer does not get to say.
            assigned = (EpistemicType.PROPOSED_ARCHITECTURE if agent
                        else EpistemicType.COMPOSED_CONTROL)
            payload["provenance"] = _provenance(p, assigned)
            obj = ControlArchitecture(**payload)
        elif p.kind is ProposalKind.BUILDING_BLOCK:
            payload = dict(p.payload)
            if agent:
                if payload.get("feasibility_status") != Feasibility.UNASSESSED.value:
                    payload["feasibility_status"] = Feasibility.UNASSESSED.value
                    payload["feasibility_note"] = (
                        "feasibility asserted by an agent is not accepted; recorded as unassessed")
                for transformation in payload.get("state_transformations", ()):
                    if isinstance(transformation, dict) and transformation.get("magnitude_if_known"):
                        transformation["magnitude_if_known"] = ""
            assigned = (EpistemicType.INFERRED_HYPOTHESIS if agent
                        else EpistemicType.BUILDING_BLOCK_CAPABILITY)
            payload["provenance"] = _provenance(p, assigned)
            obj = BuildingBlock(**payload)
        elif p.kind is ProposalKind.TARGET_CONSTRAINT:
            payload = dict(p.payload)
            if agent:
                payload["approval"] = Approval(
                    status=ApprovalStatus.PROPOSED,
                    note=f"proposed by {p.proposer.identity}; an agent cannot approve a target").model_dump()
            assigned = EpistemicType.TARGET_CONSTRAINT
            payload["provenance"] = _provenance(p, assigned)
            obj = TargetConstraint(**payload)
        else:  # pragma: no cover — the enum is closed
            return _reject(p, f"unsupported proposal kind {p.kind}")
    except (ValidationError, ValueError, TypeError) as exc:
        return _reject(p, f"does not validate: {exc}")
    return GateDecision(proposal_id=p.proposal_id, accepted=True,
                        reason="validated; epistemic type assigned by the gate, not the proposer",
                        assigned_epistemic_type=assigned, accepted_object=obj.model_dump(mode="json"))
