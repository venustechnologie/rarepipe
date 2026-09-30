"""Transport abstractions, test transport, and authenticated manual import (PRD §9, §10, Task T05).

Defines:
  1. Transport ABC: abstract outreach interface (no guarantee of exactly-once delivery).
  2. TestTransport: test double that records attempted sends and delivers nothing externally.
     Can simulate accepted sends, timeouts / unknown delivery, and provider failures.
  3. Authenticated manual import: enables an authorized human operator to paste an authentic
     institutional reply with full cryptographic provenance and lineage.
  4. Dispatch orchestrator: Coordinates Outbox, Standing Authorization, and Native Policy.
     With external send disabled in native policy, dispatch yields a prepared, unsent artifact
     and invokes no transport.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Final, Literal
from uuid import uuid4

from pydantic import Field

from rarepipe.stages.network.authorization import (
    AuthorizationManager, PreparedDispatchArtifact,
)
from rarepipe.stages.network.eventlog import opaque, utc
from rarepipe.stages.network.model import (
    AdditionalResponseState, CampaignScope, ClaimRelation, Contribution,
    HumanConfirmation, ImmutableModel, NetworkEnvelope, OperationalResponse,
    Origin, Request, RequestState, ResponseState, new_id,
)
from rarepipe.stages.network.outbox import DispatchBlocked, Outbox, OutboxEntry
from rarepipe.stages.prospective.model import Actor, ActorType, Knowledge, Quantity, Role
from rarepipe.stages.prospective.policy import DEFAULT_POLICY, Permission, Policy
from rarepipe.stages.prospective.store import content_digest


class TransportResult(ImmutableModel):
    """Result of a transport send invocation."""

    status: Literal["accepted", "unknown", "failed"]
    attempt_id: str
    provider_message_id: str | None = None
    timestamp: datetime
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class RecordedDispatch(ImmutableModel):
    """In-memory record of an outreach transmission recorded by TestTransport."""

    attempt_id: str
    request_id: str
    sender: str
    recipient: str
    content_digest: str
    timestamp: datetime
    status: str


class Transport(ABC):
    """Abstract transport interface for delivering outreach requests."""

    @abstractmethod
    def send(self, request: Request, attempt_id: str) -> TransportResult:
        """Attempt to deliver request. Does NOT promise exactly-once delivery."""
        ...


class TestTransport(Transport):
    """Test transport double that records what would be sent and delivers nothing."""

    __test__ = False

    def __init__(self, mode: Literal["succeed", "unknown", "fail"] = "succeed"):
        self.mode = mode
        self.dispatches: list[RecordedDispatch] = []

    def set_mode(self, mode: Literal["succeed", "unknown", "fail"]) -> None:
        self.mode = mode

    def send(self, request: Request, attempt_id: str) -> TransportResult:
        now = datetime.now(timezone.utc)
        digest = content_digest(request)

        if self.mode == "succeed":
            message_id = f"test-msg-{uuid4()}"
            record = RecordedDispatch(
                attempt_id=attempt_id,
                request_id=request.id,
                sender=request.sender.identity,
                recipient=request.recipient,
                content_digest=digest,
                timestamp=now,
                status="accepted",
            )
            self.dispatches.append(record)
            return TransportResult(
                status="accepted",
                attempt_id=attempt_id,
                provider_message_id=message_id,
                timestamp=now,
            )

        elif self.mode == "unknown":
            # Simulate network timeout or provider ambiguity
            return TransportResult(
                status="unknown",
                attempt_id=attempt_id,
                timestamp=now,
                error="transport timeout or ambiguous provider response",
            )

        else:
            # Simulate outright delivery rejection
            return TransportResult(
                status="failed",
                attempt_id=attempt_id,
                timestamp=now,
                error="provider delivery rejected",
            )


class ManualImportResult(ImmutableModel):
    """Structured container returned from an authenticated manual import."""

    contribution: Contribution
    operational_response: OperationalResponse
    import_digest: str
    imported_at: datetime
    operator: Actor
    digest_coverage: str = "canonical content_digest of (raw_content + provenance), sha256"


def manual_import_reply(
    raw_content: str,
    *,
    operator: Actor,
    request_id: str,
    campaign_id: str,
    scope: CampaignScope,
    question_id: str,
    node_id: str,
    responder: str,
    received_at: datetime,
    evidence_family_id: str,
    rationale: str = "Manual paste of authentic institutional reply by authorized operator",
    response_state: AdditionalResponseState | ResponseState = AdditionalResponseState.CAPABILITY_REPORTED,
    outbox: Outbox | None = None,
    transport_headers: dict[str, str] | None = None,
) -> ManualImportResult:
    """Authenticated manual import path for authentic institutional correspondence (PRD §9, Acceptance A23).

    External content is untrusted data: embedded commands or instructions are NEVER executed,
    cannot alter system permissions, cannot modify authorizations, and cannot trigger exports.
    """
    if operator.actor_type is not ActorType.HUMAN:
        raise ValueError("only an authenticated human operator can perform manual institutional import")

    authorized_roles = {Role.RESEARCH_OPERATIONS, Role.SCIENTIFIC_LEAD, Role.TREATING_CLINICIAN}
    if not any(r in authorized_roles for r in operator.roles):
        raise ValueError(f"operator {operator.identity} lacks required role for manual import ({[r.value for r in authorized_roles]})")

    received_utc = utc(received_at)
    import_time = datetime.now(timezone.utc)

    # Cryptographic provenance digest over the untrusted input and provenance metadata
    payload_for_digest = {
        "raw_content": raw_content,
        "responder": responder,
        "request_id": request_id,
        "node_id": node_id,
        "received_at": received_utc.isoformat(),
        "transport_headers": transport_headers or {},
    }
    import_digest = content_digest(payload_for_digest)

    # Build operational event
    envelope = NetworkEnvelope(
        question_id=question_id,
        node_identity=node_id,
        response_state=response_state,
    )

    op_response = OperationalResponse(
        id=new_id(),
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=response_state,
        envelope=envelope,
        resource_available=Knowledge.UNKNOWN,
        analysis_permission=Knowledge.UNKNOWN,
    )

    contrib_id = new_id()
    operator_role = operator.roles[0] if operator.roles else Role.RESEARCH_OPERATIONS

    confirmation = HumanConfirmation(
        actor=operator,
        role=operator_role,
        timestamp=import_time,
        statement_ref=contrib_id,
        rationale=rationale,
    )

    contribution = Contribution(
        id=contrib_id,
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(op_response.lineage(),),
        campaign_id=campaign_id,
        scope=scope,
        request_id=request_id,
        responder=responder,
        source="authenticated_manual_institutional_import",
        received_at=received_utc,
        event=op_response,
        permitted_content=raw_content,  # Stored purely as inert text data
        extractor=operator,
        human_confirmation=confirmation,
        evidence_family_id=evidence_family_id,
    )

    if outbox is not None:
        outbox.receive(request_id, contribution, actor=operator, now=import_time)

    return ManualImportResult(
        contribution=contribution,
        operational_response=op_response,
        import_digest=import_digest,
        imported_at=import_time,
        operator=operator,
    )


def dispatch_request(
    outbox: Outbox,
    task_id: str,
    *,
    authorization_manager: AuthorizationManager,
    transport: Transport,
    actor: Actor,
    now: datetime,
    cost: Quantity,
    policy: Policy = DEFAULT_POLICY,
) -> PreparedDispatchArtifact | TransportResult:
    """Coordinate task dispatch checking standing authorization and native policy.

    Layering rule:
      The authorization layer sits ON TOP of native policy (Permission.EXTERNAL_SEND).
      With external send disabled in native policy, standing authorization is checked;
      if authorized, a PreparedDispatchArtifact is returned and no transport send occurs.
    """
    now_utc = utc(now)
    task = outbox.load(task_id)

    # 1. Enforce standing authorization check first
    auth = authorization_manager.check_authorization(task, now=now_utc)

    # 2. Check native policy
    if not policy.external_send_enabled:
        # Native external send is disabled: yield prepared unsent artifact
        return authorization_manager.create_prepared_artifact(task, auth, now=now_utc)

    # 3. If policy permits external send, claim from outbox and dispatch
    claim = outbox.begin_attempt(
        task_id,
        actor=actor,
        now=now_utc,
        cost=cost,
        authorize=lambda req: authorization_manager.is_authorized(req, now=now_utc),
    )

    if not claim.created:
        # Already dispatched in prior attempt
        return TransportResult(
            status="accepted",
            attempt_id=claim.attempt_id,
            timestamp=now_utc,
            metadata={"note": "reused existing claim"},
        )

    # 4. Invoke transport
    send_result = transport.send(claim.task, claim.attempt_id)

    if send_result.status == "accepted":
        outbox.finish_attempt(task_id, claim.attempt_id, outcome="accepted", actor=actor, now=now_utc)
    elif send_result.status == "unknown":
        outbox.finish_attempt(task_id, claim.attempt_id, outcome="unknown", actor=actor, now=now_utc)
    else:
        # Failed send transitions attempt to delivery unknown for explicit reconciliation
        outbox.finish_attempt(task_id, claim.attempt_id, outcome="unknown", actor=actor, now=now_utc)

    return send_result
