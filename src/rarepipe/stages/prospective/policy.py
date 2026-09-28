"""Who may do what, enforced in the domain layer (PRD §3, §15, FR-050..FR-054).

Permissions are separate: reading, drafting, scientific review, freezing, private export and
external sending. In this challenge deployment external sending and remote execution are disabled
for everyone. An agent may draft; it can never sign as a human reviewer or freeze a real plan.
Text inside documents, node responses or observations is data: nothing in this module reads it.
"""

from __future__ import annotations

from enum import StrEnum

from rarepipe.stages.prospective.model import Actor, ActorType, Role


class Permission(StrEnum):
    READ = "read"
    DRAFT = "draft"
    SCIENTIFIC_REVIEW = "scientific_review"
    FREEZE = "freeze"
    PRIVATE_EXPORT = "private_export"
    EXTERNAL_SEND = "external_send"


class PolicyError(PermissionError):
    pass


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.TREATING_CLINICIAN: {Permission.READ, Permission.SCIENTIFIC_REVIEW},
    Role.SCIENTIFIC_LEAD: {Permission.READ, Permission.DRAFT, Permission.SCIENTIFIC_REVIEW, Permission.FREEZE,
                           Permission.PRIVATE_EXPORT},
    Role.RESEARCH_OPERATIONS: {Permission.READ, Permission.DRAFT, Permission.PRIVATE_EXPORT},
    Role.ASSAY_SCIENTIST: {Permission.READ, Permission.DRAFT, Permission.SCIENTIFIC_REVIEW},
    Role.STATISTICIAN: {Permission.READ, Permission.DRAFT, Permission.SCIENTIFIC_REVIEW},
    Role.ENGINEER: {Permission.READ, Permission.DRAFT, Permission.PRIVATE_EXPORT},
    Role.PATIENT_OR_CAREGIVER: {Permission.READ},
    Role.CLINICAL_PHARMACOLOGIST: {Permission.READ, Permission.SCIENTIFIC_REVIEW},
    Role.DATA_HOLDER: {Permission.READ},
}
AGENT_PERMISSIONS = {Permission.READ, Permission.DRAFT}


class Policy:
    """The deployment's rules. Constructed from configuration, never from document content."""

    name = "challenge-deployment-v1"

    def __init__(self, external_send_enabled: bool = False, remote_execution_enabled: bool = False):
        # The MVA challenge deployment: no external send, no remote execution, no contact with the
        # MVA Society, the child or the family (PRD §4.4). Requests are generated as unsent drafts.
        self.external_send_enabled = external_send_enabled
        self.remote_execution_enabled = remote_execution_enabled

    def permissions(self, actor: Actor) -> set[Permission]:
        if actor.actor_type is ActorType.AGENT:
            granted = set(AGENT_PERMISSIONS)
        elif actor.actor_type is ActorType.SYSTEM:
            granted = {Permission.READ}
        else:
            granted = set().union(*(ROLE_PERMISSIONS.get(r, set()) for r in actor.roles)) if actor.roles else set()
        if not self.external_send_enabled:
            granted.discard(Permission.EXTERNAL_SEND)
        return granted

    def require(self, actor: Actor, permission: Permission, role: Role | None = None) -> None:
        if permission is Permission.EXTERNAL_SEND and not self.external_send_enabled:
            raise PolicyError("external sending is disabled in this deployment; requests stay unsent drafts")
        if permission in (Permission.SCIENTIFIC_REVIEW, Permission.FREEZE) and actor.actor_type is not ActorType.HUMAN:
            raise PolicyError(f"a {actor.actor_type.value.lower()} cannot sign as a human reviewer or freeze a plan")
        if role is not None and role not in actor.roles:
            raise PolicyError(f"{actor.identity} does not hold the {role.value} role it is acting in")
        if permission not in self.permissions(actor):
            raise PolicyError(f"{actor.identity} lacks the {permission.value} permission")


DEFAULT_POLICY = Policy()
