"""Standing authorization, recipient verification, opt-outs, and hard campaign exclusions (PRD §10, Task T05).

Standing authorization enables routine outreach actions without operator re-approval for each covered action.
At dispatch, the following checks are enforced:
  1. Current authorization validity window, scope, and non-revocation
  2. Recipient verification status
  3. Disclosure scope boundaries
  4. Opt-outs and explicit declines
  5. Hard campaign exclusions (MVA Society, the child, and the family)
  6. Intermediary outreach modeling (blocking contact intended to reach excluded parties via third parties)

This authorization layer sits ON TOP of native policy (rarepipe.stages.prospective.policy).
Because Permission.EXTERNAL_SEND is disabled in the challenge deployment, dispatch yields a
prepared, unsent artifact and does not bypass native policy.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Final, Literal

from pydantic import Field

from rarepipe.stages.network.eventlog import opaque, utc
from rarepipe.stages.network.model import (
    Authorization, ImmutableModel, Node, Request, new_id,
)
from rarepipe.stages.prospective.model import Actor, ActorType, Role
from rarepipe.stages.prospective.policy import DEFAULT_POLICY, Permission, Policy
from rarepipe.stages.prospective.store import content_digest


class AuthorizationError(ValueError):
    """Base class for authorization and dispatch blocks."""
    pass


class UnsetAuthorizationError(AuthorizationError):
    """Raised when no matching standing authorization covers the request."""
    pass


class RevokedAuthorizationError(AuthorizationError):
    """Raised when the authorization has been revoked."""
    pass


class ExpiredAuthorizationError(AuthorizationError):
    """Raised when current time is outside the authorization validity window."""
    pass


class OptOutBlocked(AuthorizationError):
    """Raised when the recipient or node has opted out of contact."""
    pass


class CampaignExclusionBlocked(AuthorizationError):
    """Raised when outreach targets an excluded entity directly."""
    pass


class IntermediaryExclusionBlocked(CampaignExclusionBlocked):
    """Raised when outreach targets an excluded entity via an intermediary or intent in content."""
    pass


class RecipientUnverifiedError(AuthorizationError):
    """Raised when the contact route is unverified and verification is required."""
    pass


class DisclosureScopeViolation(AuthorizationError):
    """Raised when request disclosure scope exceeds authorized bounds."""
    pass


class IntermediaryRecord(ImmutableModel):
    """Models known intermediaries and relays associated with excluded parties."""

    recipient: str
    target_exclusion: str
    description: str


class OptOutRecord(ImmutableModel):
    """Records an explicit decline or opt-out from further contact."""

    recipient_or_node: str
    opted_out_at: datetime
    reason: str


class PreparedDispatchArtifact(ImmutableModel):
    """Prepared unsent artifact yielded when external send is disabled by native policy."""

    artifact_id: str = Field(default_factory=new_id)
    request_id: str
    campaign_id: str
    sender: str
    recipient: str
    content: str
    content_digest: str
    authorization_ref: str
    created_at: datetime
    status: Literal["PREPARED_UNSENT"] = "PREPARED_UNSENT"
    policy_reason: str = "Permission.EXTERNAL_SEND is disabled in deployment policy; dispatch produces a prepared, unsent artifact"
    digest_coverage: str = "canonical content_digest over request, sha256"


# Phrases in request text indicating an intent to contact an excluded party via intermediary
INTERMEDIARY_INTENT_PATTERNS: Final[tuple[str, ...]] = (
    "forward to the family",
    "forward to the parents",
    "forward to the child",
    "forward to the patient",
    "relay to the family",
    "relay to the parents",
    "relay to the child",
    "contact the family",
    "contact the parents",
    "contact the child",
    "reach the family",
    "reach the parents",
    "reach the child",
    "connect us with the family",
    "connect us with the child",
    "forward to the mva society",
    "relay to the mva society",
    "reach the mva society",
    "contact the mva society",
    "ask the family",
    "ask the parents",
    "ask the child",
    "share with the family",
    "share with the parents",
    "share with the child",
)

MVA_DIRECT_EXCLUSION_TERMS: Final[tuple[str, ...]] = (
    "mvasociety",
    "mva_society",
    "mva-society",
    "mva society",
    "patient",
    "child",
    "family",
)


class AuthorizationManager:
    """Manages standing authorizations, opt-outs, intermediaries, and dispatch authorization checks."""

    def __init__(self, authorizations: tuple[Authorization, ...] = ()):
        self._authorizations: dict[str, Authorization] = {a.id: a for a in authorizations}
        self._opt_outs: dict[str, OptOutRecord] = {}
        self._intermediaries: list[IntermediaryRecord] = []

    def add_authorization(self, authorization: Authorization) -> None:
        """Register a valid standing authorization record."""
        self._authorizations[authorization.id] = authorization

    def get_authorization(self, auth_id: str) -> Authorization | None:
        return self._authorizations.get(auth_id)

    def revoke_authorization(self, auth_id: str, *, revoked_at: datetime, reason: str = "") -> Authorization:
        """Revoke a standing authorization. Revocation immediately invalidates all pending sends."""
        auth = self._authorizations.get(auth_id)
        if not auth:
            raise KeyError(f"unknown authorization: {auth_id}")
        data = auth.model_dump()
        data["revoked_at"] = utc(revoked_at)
        revoked = Authorization.model_validate(data)
        self._authorizations[auth_id] = revoked
        return revoked

    def record_opt_out(self, recipient_or_node: str, *, opted_out_at: datetime, reason: str = "") -> OptOutRecord:
        """Record an explicit decline/opt-out for a recipient address, domain, or node identity."""
        rec = OptOutRecord(
            recipient_or_node=recipient_or_node.strip().lower(),
            opted_out_at=utc(opted_out_at),
            reason=reason or "declined further contact",
        )
        self._opt_outs[rec.recipient_or_node] = rec
        return rec

    def is_opted_out(self, recipient: str, node_id: str | None = None) -> bool:
        """Check whether recipient, domain, or node has an active opt-out."""
        clean_recipient = recipient.strip().lower()
        if clean_recipient in self._opt_outs:
            return True
        if "@" in clean_recipient:
            domain = "@" + clean_recipient.split("@", 1)[1]
            if domain in self._opt_outs:
                return True
        if node_id and node_id.strip().lower() in self._opt_outs:
            return True
        return False

    def register_intermediary(self, intermediary: IntermediaryRecord) -> None:
        """Register a known intermediary linked to an excluded entity."""
        self._intermediaries.append(intermediary)

    def check_exclusions(self, request: Request, node: Node | None = None) -> None:
        """Check direct campaign exclusions and intermediary routes."""
        recipient_lower = request.recipient.strip().lower()
        node_id_lower = request.node_id.strip().lower()
        content_lower = request.content.lower()

        # 1. Direct check against hard exclusions
        for term in MVA_DIRECT_EXCLUSION_TERMS:
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, recipient_lower) or (node and re.search(pattern, node.institution.lower())):
                raise CampaignExclusionBlocked(
                    f"outreach to '{request.recipient}' targets hard-excluded party: '{term}'"
                )

        # 2. Intermediary registry check
        for inter in self._intermediaries:
            target = inter.recipient.strip().lower()
            if target == recipient_lower or (target.startswith("@") and recipient_lower.endswith(target)):
                raise IntermediaryExclusionBlocked(
                    f"recipient '{request.recipient}' is a modeled intermediary to excluded entity '{inter.target_exclusion}' "
                    f"({inter.description})"
                )

        # 3. Content-based intermediary intent check
        for intent in INTERMEDIARY_INTENT_PATTERNS:
            if intent in content_lower:
                raise IntermediaryExclusionBlocked(
                    f"message content contains intermediary outreach intent targeting excluded entity: '{intent}'"
                )

    def check_authorization(
        self,
        request: Request,
        *,
        node: Node | None = None,
        now: datetime,
        require_verified_recipient: bool = False,
    ) -> Authorization:
        """Perform comprehensive dispatch authorization check. Raises typed AuthorizationError on failure."""
        now_utc = utc(now)

        # Check opt-out
        if self.is_opted_out(request.recipient, request.node_id):
            raise OptOutBlocked(f"recipient '{request.recipient}' or node '{request.node_id}' has opted out of outreach")

        # Check hard exclusions and intermediaries
        self.check_exclusions(request, node=node)

        # Check recipient verification if required
        if require_verified_recipient:
            if node and node.contact_route and node.contact_route.verification is None:
                raise RecipientUnverifiedError(f"recipient '{request.recipient}' lacks verified contact route confirmation")

        # Resolve standing authorization
        auth: Authorization | None = None
        if request.authorization_ref:
            auth = self._authorizations.get(request.authorization_ref)
            if not auth:
                raise UnsetAuthorizationError(f"referenced authorization '{request.authorization_ref}' does not exist")
        else:
            # Find an active matching standing authorization
            candidates = [
                a for a in self._authorizations.values()
                if a.sender == request.sender.identity
                and (
                    request.recipient in a.recipients
                    or any(r.startswith("@") and request.recipient.endswith(r) for r in a.recipients)
                    or "*" in a.recipients
                )
            ]
            if not candidates:
                raise UnsetAuthorizationError(
                    f"no standing authorization found covering sender '{request.sender.identity}' and recipient '{request.recipient}'"
                )
            auth = candidates[0]

        # Check validity interval
        if now_utc < auth.valid_from or now_utc > auth.valid_until:
            raise ExpiredAuthorizationError(
                f"authorization '{auth.id}' is outside validity window [{auth.valid_from.isoformat()}, {auth.valid_until.isoformat()}]"
            )

        # Check revocation
        if auth.revoked_at is not None and auth.revoked_at <= now_utc:
            raise RevokedAuthorizationError(
                f"authorization '{auth.id}' was revoked at {auth.revoked_at.isoformat()}"
            )

        # Check issuer accountability
        if auth.issuer.actor_type is not ActorType.HUMAN:
            raise AuthorizationError("standing authorization must be issued and confirmed by a human actor")

        # Check disclosure scope
        if request.disclosure_scope and auth.content_refs and request.disclosure_scope not in auth.content_refs:
            raise DisclosureScopeViolation(
                f"request disclosure scope '{request.disclosure_scope}' is not authorized by {auth.content_refs}"
            )

        return auth

    def is_authorized(
        self,
        request: Request,
        *,
        node: Node | None = None,
        now: datetime,
        require_verified_recipient: bool = False,
    ) -> bool:
        """Predicate checking whether dispatch is authorized. Returns True only on success."""
        try:
            self.check_authorization(
                request,
                node=node,
                now=now,
                require_verified_recipient=require_verified_recipient,
            )
            return True
        except AuthorizationError:
            return False

    def create_prepared_artifact(
        self,
        request: Request,
        authorization: Authorization,
        *,
        now: datetime,
    ) -> PreparedDispatchArtifact:
        """Produce a prepared, unsent artifact when external send is disabled by native policy."""
        digest = content_digest(request)
        return PreparedDispatchArtifact(
            request_id=request.id,
            campaign_id=request.campaign_id,
            sender=request.sender.identity,
            recipient=request.recipient,
            content=request.content,
            content_digest=digest,
            authorization_ref=authorization.id,
            created_at=utc(now),
        )
