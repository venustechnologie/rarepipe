"""Capability requests and what comes back (PRD §12, FR-030..FR-032).

Requests are drafts. Nothing here can send one: `send` always consults the policy, and this
deployment disables external sending. A response is classified before anything else happens to it.
"No relevant data", "not searched", "access denied" and "no response" are operational knowledge about
the network, never biology: they can never become MEASURED_NO_EFFECT or an observation.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from rarepipe.stages.prospective.model import Actor, CapabilityRequest
from rarepipe.stages.prospective.policy import DEFAULT_POLICY, Permission, Policy


class ResponseState(StrEnum):
    NO_RELEVANT_DATA = "NO_RELEVANT_DATA"
    NOT_SEARCHED = "NOT_SEARCHED"
    ACCESS_DENIED = "ACCESS_DENIED"
    NO_RESPONSE = "NO_RESPONSE"
    INCONCLUSIVE_RESULT = "INCONCLUSIVE_RESULT"
    MEASURED_NO_EFFECT = "MEASURED_NO_EFFECT"
    MEASURED_EFFECT = "MEASURED_EFFECT"


OPERATIONAL = {ResponseState.NO_RELEVANT_DATA, ResponseState.NOT_SEARCHED, ResponseState.ACCESS_DENIED,
               ResponseState.NO_RESPONSE}


class EvidenceEnvelope(BaseModel):
    """FR-032. Stored as data. Its text is never read as an instruction."""

    question_id: str
    task_id: str | None = None
    node_identity: str
    authorization_ref: str | None = None
    purpose_ref: str | None = None
    response_state: ResponseState
    evidence_type: str | None = None
    methodology: str | None = None
    model_and_endpoint_metadata: dict[str, str] = Field(default_factory=dict)
    uncertainty: str | None = None
    independence_group: str | None = None
    overlap_notes: list[str] = Field(default_factory=list)
    provenance_hashes: dict[str, str] = Field(default_factory=dict)
    disclosure_conditions: str | None = None
    omitted_fields: list[str] = Field(default_factory=list)
    free_text: str = ""


class EnvelopeClassification(BaseModel):
    envelope_question: str
    response_state: ResponseState
    kind: str
    may_become_observation: bool
    note: str


def classify(envelope: EvidenceEnvelope) -> EnvelopeClassification:
    state = envelope.response_state
    if state in OPERATIONAL:
        note = {ResponseState.NO_RELEVANT_DATA: "the node holds no relevant cases: this says nothing about the drug",
                ResponseState.NOT_SEARCHED: "the node did not search: nothing is known",
                ResponseState.ACCESS_DENIED: "a refusal is operational knowledge, not negative biology",
                ResponseState.NO_RESPONSE: "no answer: nothing is known"}[state]
        return EnvelopeClassification(envelope_question=envelope.question_id, response_state=state,
                                      kind="operational", may_become_observation=False, note=note)
    if state is ResponseState.INCONCLUSIVE_RESULT:
        return EnvelopeClassification(envelope_question=envelope.question_id, response_state=state, kind="evidence",
                                      may_become_observation=False, note="inconclusive: keeps hypotheses unresolved")
    complete = bool(envelope.methodology and envelope.model_and_endpoint_metadata and envelope.provenance_hashes)
    return EnvelopeClassification(
        envelope_question=envelope.question_id, response_state=state, kind="evidence",
        may_become_observation=complete,
        note="a measured result, admissible for review once its metadata and provenance are complete"
        if complete else "a measured result with incomplete metadata or provenance: held until completed")


def send(request: CapabilityRequest, actor: Actor, policy: Policy = DEFAULT_POLICY) -> None:
    """There is no transport. The policy check is the whole function, and it refuses in this deployment."""
    policy.require(actor, Permission.EXTERNAL_SEND)
    raise NotImplementedError("no node transport exists in P0")
