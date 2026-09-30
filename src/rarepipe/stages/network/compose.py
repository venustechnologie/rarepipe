"""Request composer for research-network outreach (PRD §10, Task T05).

Composes structured first requests and follow-ups. Each first request states:
  - The actual sender and accountability role
  - The bounded question and decision consequence
  - Why this institution is relevant (citing public sources)
  - The smallest useful contribution
  - Five concrete alternatives (existing finding, brief explanation, referral,
    feasibility reply, or quote)
  - Disclosure limits (no private patient identifiers or exact variant clues)
  - Clear instructions to decline further contact

Confirmed clinical leadership may only be asserted when an authentic human treating
clinician is appointed. If unappointed, the message must not imply clinical leadership exists.

The partnership campaign is structurally separated from the MVA campaign: its composer is
incapable of accepting or emitting private case information or technical architecture. No
partnership institution is seeded in this project's registry; the separation is kept because a
partnership reply must remain unable to satisfy an MVA scientific question (A26).
"""

from __future__ import annotations

import re
from typing import Final

from rarepipe.stages.network.model import (
    Campaign, CampaignScope, Node, Origin, Question, Request, RequestState, new_id,
)
from rarepipe.stages.prospective.model import Actor, ActorType, Role


CASE_PRIVATE_TERMS: Final[tuple[str, ...]] = (
    "pp_mva",
    "case_ref",
    "patient",
    "bub1b",
    "bubr1",
    "mosaic variegated aneuploidy",
    "mva",
    "nicotinic",
    "niacin",
    "sirt2",
    "variant",
    "mutation",
    "allele",
    "genotype",
)

TECHNICAL_ARCHITECTURE_TERMS: Final[tuple[str, ...]] = (
    "neural network",
    "transformer",
    "hyperparameter",
    "loss function",
    "q-learning",
    "reinforcement learning",
    "policy gradient",
    "backpropagation",
    "architecture diagram",
    "policy_q",
    "sim_world",
    "action space",
    "reward function",
    "reward scorer",
    "feature vector",
    "actor-critic",
)


def _validate_clinical_lead(clinical_lead: Actor | None) -> str:
    """Validate clinical leadership appointment. Only genuine human treating clinicians qualify."""
    if clinical_lead is None:
        return (
            "Clinical Leadership: Unassigned (no clinical lead is currently appointed). "
            "This is an exploratory preclinical research inquiry; no clinical leadership "
            "or patient-care decision is asserted or implied."
        )

    if clinical_lead.actor_type is not ActorType.HUMAN:
        raise ValueError("agents cannot be asserted as clinical lead; only a human clinician qualifies")

    if Role.TREATING_CLINICIAN not in clinical_lead.roles:
        raise ValueError(f"clinical lead must hold the {Role.TREATING_CLINICIAN.value} role")

    return (
        f"Clinical Leadership: Confirmed - Dr. {clinical_lead.identity} ({Role.TREATING_CLINICIAN.value}). "
        "Preclinical question bounds and patient relevance are governed by appointed clinical leadership."
    )


class ScientificRequestComposer:
    """Composes bounded scientific requests for candidate research institutions."""

    def compose(
        self,
        campaign: Campaign,
        question: Question,
        node: Node,
        *,
        sender: Actor,
        clinical_lead: Actor | None = None,
        recipient: str | None = None,
        disclosure_limits: str | None = None,
    ) -> Request:
        if campaign.scope is not CampaignScope.MVA_SCIENTIFIC:
            raise ValueError(f"ScientificRequestComposer only handles MVA_SCIENTIFIC campaigns, got {campaign.scope}")

        clinical_lead_text = _validate_clinical_lead(clinical_lead)

        resolved_recipient = recipient or (node.contact_route.recipient if node.contact_route else f"inquiry@{node.id}.org")

        capabilities_text = "; ".join(c.description for c in node.capabilities) if node.capabilities else "Identified via public research literature"

        endpoint_text = f"\nTarget Endpoint: {question.evidence_criteria.endpoint}" if question.evidence_criteria.endpoint else ""

        question_text = f"Question: {question.text}\n" if question.text else ""

        disclosure_text = disclosure_limits or (
            "Preclinical research scope only. Under institutional policy, no identifying patient combinations, "
            "exact variant coordinates, private repository paths, or clinical case records are disclosed."
        )

        content = f"""From: {sender.identity} (Role: {', '.join(r.value for r in sender.roles) if sender.roles else 'Researcher'})
To: {resolved_recipient}
Subject: Research Inquiry: Bounded Question on {question.id}

Dear Research Team at {node.institution},

{clinical_lead_text}

1. Bounded Research Question:
We are investigating a specific preclinical question ({question.id}):
{question_text}What an answer could change: {question.decision}{endpoint_text}

2. Relevance and Public Source:
Your institution was identified based on public scientific publications and institutional profiles:
Institution: {node.institution}{f' ({node.group})' if node.group else ''}
Public Reference: {node.source.reference}
Relevant Public Capabilities: {capabilities_text}

3. Smallest Useful Contribution:
We seek the smallest useful contribution that can inform this question. A complete study, private data transfer, or biological specimen shipment is NOT required. We welcome any of the following alternatives:
  (a) An existing result or historical finding relevant to the mechanism.
  (b) A brief methods explanation, interpretation, or advice on assay limitations.
  (c) A referral to another group, sample custodian, or research infrastructure.
  (d) A feasibility reply on whether your laboratory could evaluate this endpoint.
  (e) A formal quote or service agreement proposal.

4. Disclosure Limits:
{disclosure_text}

5. Declining Further Contact:
If your group does not wish to participate, does not have relevant resources, or prefers not to receive further contact, please reply with 'DECLINE' or 'OPT OUT'. We will immediately respect your preference and close this outreach route without further follow-up.

Sincerely,
{sender.identity}
"""

        return Request(
            id=new_id(),
            origin=Origin.PUBLIC_EVIDENCE,
            campaign_id=campaign.id,
            question_id=question.id,
            node_id=node.id,
            content=content.strip(),
            sender=sender,
            recipient=resolved_recipient,
            disclosure_scope="preclinical_non_identifying",
            state=RequestState.DRAFT,
        )


class PartnershipRequestComposer:
    """Composes partnership exploration inquiries for oncology / data-holder candidates.

    Structurally incapable of accepting or emitting case-private information or technical architecture.
    """

    def compose(
        self,
        node: Node,
        *,
        sender: Actor,
        recipient: str | None = None,
        question: Question | None = None,
        disclosure_limits: str | None = None,
        **forbidden_kwargs,
    ) -> Request:
        if forbidden_kwargs:
            raise ValueError(f"partnership composer rejects case or architecture parameters: {list(forbidden_kwargs.keys())}")

        resolved_recipient = recipient or (node.contact_route.recipient if node.contact_route else f"info@{node.id}.org")

        disclosure_text = disclosure_limits or (
            "Non-confidential partnership inquiry. Contains no confidential clinical records, private case material, or internal technical architecture."
        )

        content = f"""From: {sender.identity}
To: {resolved_recipient}
Subject: Research Partnership Inquiry - Multidisciplinary Tumour Board Note Extraction

Dear Team at {node.institution},

We are reaching out regarding the public challenge listing referencing {node.institution} ({node.source.reference}):
The listing reports multidisciplinary virtual tumour board meeting notes (2017-2026) and interest in an AI research partner.

We are inquiring whether {node.institution} is still considering an AI research partner to extract research questions, clinical reasoning, and evidence needs from permitted material.

We offer several flexible response options:
1. Confirm availability: Inform us if exploration of research partnerships remains open.
2. Administrative referral: Direct us to the designated institutional lead or governance contact.
3. Feasibility reply: Clarify current status regarding consent and data access model considerations.
4. Decline: If this partnership route is closed or you do not wish to be contacted, let us know and we will immediately close this contact.

Disclosure limits:
{disclosure_text}

Declining contact:
If you do not wish to receive further correspondence regarding this partnership inquiry, reply with 'DECLINE' or 'OPT OUT' and all outreach will cease immediately.

Sincerely,
{sender.identity}
"""
        cleaned_content = content.strip()
        self._assert_structural_purity(cleaned_content)

        return Request(
            id=new_id(),
            origin=Origin.PUBLIC_EVIDENCE,
            campaign_id="cmp-partnership-oncology",
            question_id=question.id if question else "Q_ONC_01",
            node_id=node.id,
            content=cleaned_content,
            sender=sender,
            recipient=resolved_recipient,
            disclosure_scope="partnership_non_confidential",
            state=RequestState.DRAFT,
        )

    @staticmethod
    def _assert_structural_purity(content: str) -> None:
        """Scan content to structurally guarantee no case-private details or technical architecture keywords leak."""
        lower = content.lower()
        for term in CASE_PRIVATE_TERMS:
            # Word boundary search to avoid accidental substring false positives
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, lower):
                raise ValueError(f"partnership message structurally cannot contain case-private detail: '{term}'")

        for term in TECHNICAL_ARCHITECTURE_TERMS:
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, lower):
                raise ValueError(f"partnership message structurally cannot contain technical architecture: '{term}'")


def compose_request(
    campaign: Campaign,
    question: Question,
    node: Node,
    *,
    sender: Actor,
    clinical_lead: Actor | None = None,
    recipient: str | None = None,
    disclosure_limits: str | None = None,
) -> Request:
    """Compose a draft outreach request according to campaign scope and rules."""
    if campaign.scope is CampaignScope.PARTNERSHIP_ONCOLOGY:
        if clinical_lead is not None:
            raise ValueError("partnership campaign cannot assert clinical leadership")
        return PartnershipRequestComposer().compose(
            node=node,
            sender=sender,
            recipient=recipient,
            question=question,
            disclosure_limits=disclosure_limits,
        )
    elif campaign.scope is CampaignScope.MVA_SCIENTIFIC:
        return ScientificRequestComposer().compose(
            campaign=campaign,
            question=question,
            node=node,
            sender=sender,
            clinical_lead=clinical_lead,
            recipient=recipient,
            disclosure_limits=disclosure_limits,
        )
    else:
        raise ValueError(f"unsupported campaign scope: {campaign.scope}")
