"""Intake, deduplication, review routing and emission separation (PRD §9, Task T06).

Implements the 7-step intake pipeline of PRD §9:
1. Preserve original permitted response and transport metadata in its authorized scope.
2. Deduplicate provider message IDs and content lineage without losing distinct replies.
3. Detect response type and propose structured fields, each traceable to source spans.
4. Mark missing, conflicting or ambiguous fields; never invent estimates or permissions.
5. Route substantive scientific interpretations to the configured review queue.
6. Emit approved case changes and operational changes SEPARATELY.
7. Prepare the next action with rationale and dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from rarepipe.stages.network.eventlog import opaque, utc
from rarepipe.stages.network.extract import (
    CapabilityExtraction, ExtractedField, ResponseTypeClassification,
    ScientificExtraction, classify_response_type, extract_capability_fields,
    extract_scientific_fields,
)
from rarepipe.stages.network.model import (
    AdditionalResponseState, Assessment, CampaignScope, ClaimDirection,
    ClaimRelation, Compartment, Contribution, EvidenceCriteria,
    HumanConfirmation, ImmutableModel, Intervention, NetworkEnvelope,
    OperationalResponse, Origin, Question, RequestState, Restrictions,
    ScientificFinding, unknown_quantity, new_id,
)
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.prospective.model import Actor, ActorType, Knowledge, Quantity, Role
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.store import content_digest


class InboundAttachment(ImmutableModel):
    """Inbound attachment preserved as inert data. Executable content is NEVER run."""

    filename: str
    content_type: str
    data: bytes = Field(repr=False)
    digest: str = ""
    digest_coverage: str = "sha256 of raw bytes"

    @model_validator(mode="after")
    def _compute_digest(self):
        if not self.digest:
            h = hashlib.sha256(self.data).hexdigest()
            object.__setattr__(self, "digest", f"sha256:{h}")
        return self


class InboundPayload(ImmutableModel):
    """Untrusted raw inbound response and transport envelope."""

    raw_content: str
    campaign_id: str
    scope: CampaignScope
    question_id: str
    node_id: str
    request_id: str
    responder: str
    received_at: datetime
    provider_message_id: str | None = None
    transport_headers: dict[str, str] = Field(default_factory=dict)
    attachments: tuple[InboundAttachment, ...] = ()
    restrictions: Restrictions = Field(default_factory=Restrictions)
    origin: Origin = Origin.AUTHENTIC_INSTITUTIONAL


class EvidenceFamilyIndex:
    """Tracks study provenance citations to ensure multiple reports of one original observation
    share the same evidence_family_id, preventing duplicate replication or reward (A06)."""

    def __init__(self):
        self._study_to_family: dict[str, str] = {}
        self._family_to_contributions: dict[str, list[str]] = {}

    def get_or_create_family_id(self, provenance_key: str | None, default_id: str | None = None) -> str:
        if provenance_key and provenance_key in self._study_to_family:
            return self._study_to_family[provenance_key]
        family_id = default_id or f"ef-{uuid4()}"
        if provenance_key:
            self._study_to_family[provenance_key] = family_id
        return family_id

    def register_contribution(self, family_id: str, contribution_id: str):
        self._family_to_contributions.setdefault(family_id, []).append(contribution_id)


class ContextComparisonPoint(ImmutableModel):
    """Individual dimension compared between conflicting scientific findings."""

    parameter: str
    finding_a_id: str
    finding_a_value: str
    finding_b_id: str
    finding_b_value: str
    notes: str = ""


class ContextComparison(ImmutableModel):
    """Structured context comparison for conflicting scientific findings (PRD §9, Acceptance A09).
    
    Averaging and majority voting are prohibited; conflicting findings require scientific review
    of context differences (assay, model, exposure, compartment).
    """

    id: str = Field(default_factory=new_id)
    question_id: str
    finding_ids: tuple[str, ...]
    comparison_points: tuple[ContextComparisonPoint, ...]
    synthesis_method: str = "CONTEXT_COMPARISON_AND_HUMAN_REVIEW"
    rationale: str = "Conflicting scientific findings produce context comparison and review, not majority vote or averaging"
    digest: str = ""
    digest_coverage: str = "canonical digest over question_id, finding_ids, comparison_points"

    @model_validator(mode="after")
    def _compute_digest(self):
        if not self.digest:
            payload = {
                "question_id": self.question_id,
                "finding_ids": list(self.finding_ids),
                "comparison_points": [p.model_dump() for p in self.comparison_points],
                "rationale": self.rationale,
            }
            object.__setattr__(self, "digest", content_digest(payload))
        return self


class ReviewTask(ImmutableModel):
    """Human review task created for substantive scientific interpretations or conflicts."""

    id: str = Field(default_factory=new_id)
    question_id: str
    contribution_id: str
    assessment_id: str
    required_role: Role
    status: Literal["PENDING", "ACCEPTED", "REJECTED", "DEFERRED"] = "PENDING"
    reason: str
    conflict_comparison_id: str | None = None
    created_at: datetime


class NextAction(ImmutableModel):
    """Next action prepared with explicit rationale and dependencies (PRD §9 step 7)."""

    id: str = Field(default_factory=new_id)
    action_type: str
    rationale: str
    dependencies: tuple[str, ...] = ()
    owner_role: Role | None = None
    target_id: str | None = None


class IntakeEmission(ImmutableModel):
    """Separately emitted operational changes, case changes, review tasks, and next actions.
    
    Rule: Operational changes and case changes are emitted SEPARATELY (PRD §9 step 6).
    """

    operational_changes: tuple[OperationalResponse, ...] = ()
    case_changes: tuple[Assessment, ...] = ()  # Only approved case changes
    proposed_case_changes: tuple[Assessment, ...] = ()  # Unreviewed proposals
    review_tasks: tuple[ReviewTask, ...] = ()
    context_comparisons: tuple[ContextComparison, ...] = ()
    next_actions: tuple[NextAction, ...] = ()


class IntakeResult(ImmutableModel):
    """Result of processing an inbound payload through the intake pipeline."""

    is_delivery_receipt: bool = False
    is_duplicate: bool = False
    contribution: Contribution | None = None
    assessment: Assessment | None = None
    emission: IntakeEmission
    import_digest: str = ""
    digest_coverage: str = "canonical content_digest over payload, contribution, and timestamp"
    security_flags: tuple[str, ...] = ()


def _parse_quantity(extracted: ExtractedField | None) -> Quantity:
    if not extracted or not extracted.value:
        return unknown_quantity()
    val_str = str(extracted.value)
    # Check for numeric extraction
    import re
    m = re.search(r"([+-]?\d+(?:\.\d+)?)", val_str)
    if m:
        try:
            return Quantity(value=float(m.group(1)), unit=val_str)
        except ValueError:
            pass
    return unknown_quantity()


def build_context_comparison(
    question: Question,
    finding_a: ScientificFinding,
    finding_b: ScientificFinding,
    contrib_a: Contribution,
    contrib_b: Contribution,
) -> ContextComparison:
    """Build structured comparison points between two conflicting scientific findings."""
    points: list[ContextComparisonPoint] = []

    # 1. State / Finding outcome
    points.append(ContextComparisonPoint(
        parameter="state",
        finding_a_id=finding_a.id,
        finding_a_value=str(finding_a.state),
        finding_b_id=finding_b.id,
        finding_b_value=str(finding_b.state),
        notes="Conflicting outcome directions between findings",
    ))

    # 2. Estimate
    points.append(ContextComparisonPoint(
        parameter="estimate",
        finding_a_id=finding_a.id,
        finding_a_value=str(finding_a.value.value if finding_a.value else "unknown"),
        finding_b_id=finding_b.id,
        finding_b_value=str(finding_b.value.value if finding_b.value else "unknown"),
        notes="Differing effect estimates",
    ))

    # 3. Model
    points.append(ContextComparisonPoint(
        parameter="model",
        finding_a_id=finding_a.id,
        finding_a_value=str(finding_a.context.model or "unspecified"),
        finding_b_id=finding_b.id,
        finding_b_value=str(finding_b.context.model or "unspecified"),
        notes="Biological model differences",
    ))

    # 4. Compartment
    points.append(ContextComparisonPoint(
        parameter="compartment",
        finding_a_id=finding_a.id,
        finding_a_value=str(finding_a.context.compartment),
        finding_b_id=finding_b.id,
        finding_b_value=str(finding_b.context.compartment),
        notes="Compartment specificity",
    ))

    return ContextComparison(
        question_id=question.id,
        finding_ids=(finding_a.id, finding_b.id),
        comparison_points=tuple(points),
        rationale="Two conflicting scientific findings produce context comparison and review, not majority vote or averaging",
    )


def intake_response(
    payload: InboundPayload,
    *,
    question: Question | None = None,
    outbox: Outbox | None = None,
    extractor: Actor,
    existing_contributions: tuple[Contribution, ...] = (),
    family_index: EvidenceFamilyIndex | None = None,
    now: datetime | None = None,
) -> IntakeResult:
    """Process an inbound response through the 7-step PRD §9 intake pipeline."""
    now_utc = utc(now or datetime.now(timezone.utc))
    extractor = Actor.model_validate(extractor)

    # ── Step 0: Scope and Permission Invariant Checks ─────────────────────────
    if question is not None:
        if payload.scope != question.scope:
            if payload.scope is CampaignScope.PARTNERSHIP_ONCOLOGY and question.scope is CampaignScope.MVA_SCIENTIFIC:
                raise ValueError("partnership reply cannot satisfy an MVA scientific question")
            raise ValueError(f"payload scope ({payload.scope}) does not match question scope ({question.scope})")
        if payload.campaign_id != question.campaign_id:
            raise ValueError(f"payload campaign ({payload.campaign_id}) does not match question campaign ({question.campaign_id})")

    # ── Step 1: Detect Delivery Receipt vs Substantive Reply ──────────────────
    classification = classify_response_type(payload.raw_content, payload.transport_headers)

    if classification.is_delivery_receipt:
        # A delivery receipt is NOT a contribution (PRD §9, §10)
        if outbox is not None:
            receipt_ref = payload.provider_message_id or payload.request_id
            outbox.delivery_receipt(payload.request_id, receipt_ref=receipt_ref, actor=extractor, now=now_utc)

        next_action = NextAction(
            action_type="AWAIT_REPLY",
            rationale="Delivery receipt recorded in transport log; awaiting substantive institutional reply",
            dependencies=(),
        )
        emission = IntakeEmission(next_actions=(next_action,))
        digest = content_digest({
            "payload_content": payload.raw_content,
            "provider_message_id": payload.provider_message_id,
            "type": "delivery_receipt",
            "received_at": now_utc.isoformat(),
        })
        return IntakeResult(
            is_delivery_receipt=True,
            is_duplicate=False,
            contribution=None,
            assessment=None,
            emission=emission,
            import_digest=digest,
            security_flags=classification.security_flags,
        )

    # ── Step 2: Deduplicate Provider Message IDs and Content Lineage ──────────
    payload_content_digest = content_digest({"raw": payload.raw_content})
    for existing in existing_contributions:
        # Message ID deduplication
        if payload.provider_message_id and existing.source == payload.provider_message_id:
            return IntakeResult(
                is_duplicate=True,
                contribution=existing,
                emission=IntakeEmission(),
                import_digest=payload_content_digest,
                security_flags=classification.security_flags,
            )
        # Exact duplicate content for same request
        if existing.request_id == payload.request_id and content_digest({"raw": existing.permitted_content}) == payload_content_digest:
            return IntakeResult(
                is_duplicate=True,
                contribution=existing,
                emission=IntakeEmission(),
                import_digest=payload_content_digest,
                security_flags=classification.security_flags,
            )

    # ── Step 3 & 4: Detection & Structured Field Extraction with Spans ────────
    if classification.kind == "operational":
        op_extraction = extract_capability_fields(payload.raw_content)

        # Build Operational Envelope and Event
        q_id = question.id if question else payload.question_id
        envelope = NetworkEnvelope(
            question_id=q_id,
            node_identity=payload.node_id,
            response_state=classification.state,
        )

        res_avail: bool | Knowledge = Knowledge.UNKNOWN
        analysis_perm: bool | Knowledge = Knowledge.UNKNOWN

        # Respect model invariants for confirmed resource/permission
        if classification.state is AdditionalResponseState.CAPABILITY_REPORTED:
            if op_extraction.availability_evidence:
                res_avail = True
            if op_extraction.followup_permission:
                analysis_perm = True

        op_event = OperationalResponse(
            id=new_id(),
            origin=payload.origin,
            state=classification.state,
            envelope=envelope,
            resource_available=res_avail,
            analysis_permission=analysis_perm,
            restrictions=payload.restrictions,
        )

        family_id = f"ef-op-{uuid4()}"
        contrib_id = new_id()
        contribution = Contribution(
            id=contrib_id,
            origin=payload.origin,
            derived_from=(op_event.lineage(),),
            campaign_id=payload.campaign_id,
            scope=payload.scope,
            request_id=payload.request_id,
            responder=payload.responder,
            source=payload.provider_message_id or payload.responder,
            received_at=now_utc,
            event=op_event,
            permitted_content=payload.raw_content,
            extractor=extractor,
            human_confirmation=None,
            evidence_family_id=family_id,
            restrictions=payload.restrictions,
        )

        # Operational Next Actions
        if classification.state is AdditionalResponseState.DECLINED:
            next_action = NextAction(
                action_type="SELECT_ALTERNATIVE_NODE",
                rationale=f"Node {payload.node_id} declined request: {classification.rationale}",
                dependencies=(),
            )
        elif classification.state is AdditionalResponseState.NO_RELEVANT_RESOURCE:
            next_action = NextAction(
                action_type="UPDATE_NODE_RESOURCE_AND_SEEK_ALTERNATIVE",
                rationale=f"Node {payload.node_id} reported no relevant resource; update registry and select alternative",
                dependencies=(),
            )
        elif classification.state is AdditionalResponseState.CAPABILITY_REPORTED:
            next_action = NextAction(
                action_type="SCHEDULE_FEASIBILITY_FOLLOWUP",
                rationale="Capability reported; follow up to confirm protocol, turnaround, and sample requirements",
                dependencies=(),
            )
        elif classification.state is AdditionalResponseState.UNCLASSIFIED:
            next_action = NextAction(
                action_type="HUMAN_READ_UNCLASSIFIED_REPLY",
                rationale="Reply matched no known pattern. Nothing is inferred from it: the node's "
                          "resource and permission stay unknown until a human reads it.",
                dependencies=(),
            )
        elif classification.state is ResponseState.NO_RESPONSE:
            next_action = NextAction(
                action_type="CHECK_FOLLOWUP_CADENCE",
                rationale="No response received; verify retry cadence and expiration",
                dependencies=(),
            )
        else:
            next_action = NextAction(
                action_type="RECORD_OPERATIONAL_STATE",
                rationale=f"Operational state recorded: {classification.state}",
                dependencies=(),
            )

        if outbox is not None:
            outbox.receive(payload.request_id, contribution, actor=extractor, now=now_utc)

        emission = IntakeEmission(
            operational_changes=(op_event,),
            case_changes=(),
            proposed_case_changes=(),
            review_tasks=(),
            context_comparisons=(),
            next_actions=(next_action,),
        )

        import_digest = content_digest({
            "payload_digest": payload_content_digest,
            "contribution_id": contribution.id,
            "timestamp": now_utc.isoformat(),
        })

        return IntakeResult(
            is_delivery_receipt=False,
            is_duplicate=False,
            contribution=contribution,
            assessment=None,
            emission=emission,
            import_digest=import_digest,
            security_flags=classification.security_flags,
        )

    # ── Scientific Finding Intake ─────────────────────────────────────────────
    sci_extraction = extract_scientific_fields(payload.raw_content)

    # Verify all extracted spans against source text
    for field_name in (
        "intervention", "compartment", "species", "model", "tissue_or_cell",
        "comparator", "endpoint", "experimental_unit", "denominator",
        "estimate", "uncertainty", "quality", "provenance", "permitted_uses"
    ):
        f = getattr(sci_extraction, field_name)
        if f is not None and f.span is not None:
            if not f.span.verify(payload.raw_content):
                raise ValueError(f"extracted span for {field_name} does not match source text")

    # Step 2 (Lineage / Evidence Family): Multiple reports of one study share family ID (A06)
    provenance_key = None
    if sci_extraction.provenance and sci_extraction.provenance.value:
        provenance_key = str(sci_extraction.provenance.value).strip()

    # Search existing contributions for matching provenance
    matched_family_id = None
    if provenance_key:
        for ex in existing_contributions:
            if isinstance(ex.event, ScientificFinding):
                if ex.permitted_content and provenance_key in ex.permitted_content:
                    matched_family_id = ex.evidence_family_id
                    break

    if matched_family_id:
        family_id = matched_family_id
    elif family_index:
        family_id = family_index.get_or_create_family_id(provenance_key)
    else:
        family_id = f"ef-sci-{uuid4()}"

    if family_index:
        family_index.register_contribution(family_id, payload.request_id)

    # Context construction: Unknown fields STAY unknown (A05)
    context = sci_extraction.to_evidence_criteria()

    value = _parse_quantity(sci_extraction.estimate)
    uncertainty = _parse_quantity(sci_extraction.uncertainty)

    # Quality setting
    quality: Knowledge | Literal["VALID"] = Knowledge.UNKNOWN
    if sci_extraction.quality and sci_extraction.quality.value == "VALID":
        quality = "VALID"
    elif classification.state in (ResponseState.MEASURED_EFFECT, ResponseState.MEASURED_NO_EFFECT, AdditionalResponseState.INFORMATIVE_NEGATIVE):
        quality = "VALID"

    q_id = question.id if question else payload.question_id
    envelope = NetworkEnvelope(
        question_id=q_id,
        node_identity=payload.node_id,
        response_state=classification.state,
    )

    finding = ScientificFinding(
        id=new_id(),
        origin=payload.origin,
        state=classification.state,
        envelope=envelope,
        context=context,
        value=value,
        uncertainty=uncertainty,
        quality=quality,
        limitations=tuple(str(f.value) for f in sci_extraction.limitations),
        not_measured=tuple(str(f.value) for f in sci_extraction.not_measured),
        restrictions=payload.restrictions,
    )

    # Claim Relation determination
    relations: list[ClaimRelation] = []
    matches = False
    mismatch_reasons: list[str] = []

    if question is not None:
        matches = finding.matches(question.evidence_criteria)

        if not matches:
            # Diagnose specific mismatch (A03, A04)
            if (
                not isinstance(question.evidence_criteria.intervention, Knowledge)
                and context.intervention != question.evidence_criteria.intervention
            ):
                mismatch_reasons.append(
                    f"intervention mismatch: reported {context.intervention}, question requires {question.evidence_criteria.intervention}"
                )
            if (
                not isinstance(question.evidence_criteria.compartment, Knowledge)
                and context.compartment != question.evidence_criteria.compartment
            ):
                mismatch_reasons.append(
                    f"compartment mismatch: reported {context.compartment}, question requires {question.evidence_criteria.compartment}"
                )
            if (
                question.evidence_criteria.endpoint is not None
                and context.endpoint != question.evidence_criteria.endpoint
            ):
                mismatch_reasons.append(
                    f"endpoint mismatch: reported {context.endpoint}, question requires {question.evidence_criteria.endpoint}"
                )
            if classification.state in (AdditionalResponseState.INVALID_MEASUREMENT, ResponseState.INCONCLUSIVE_RESULT):
                mismatch_reasons.append(f"state is {classification.state}")

            rationale = "Scientific relation unresolved due to criteria mismatch: " + "; ".join(mismatch_reasons)
            # Must be UNRESOLVED or NOT_APPLICABLE because Contribution validator forbids SUPPORTS/AGAINST on mismatch
            direction = ClaimDirection.UNRESOLVED
        else:
            if classification.state is ResponseState.MEASURED_EFFECT:
                direction = ClaimDirection.SUPPORTS
                rationale = "Scientific finding matches intervention, compartment, and endpoint criteria with observed effect"
            elif classification.state in (AdditionalResponseState.INFORMATIVE_NEGATIVE, ResponseState.MEASURED_NO_EFFECT):
                direction = ClaimDirection.AGAINST
                rationale = "Validated negative finding matches criteria"
            else:
                direction = ClaimDirection.UNRESOLVED
                rationale = f"Finding matches criteria but state is {classification.state}"

        relations.append(ClaimRelation(
            claim_id=new_id(),
            question=question,
            direction=direction,
            rationale=rationale,
            source_refs=(f"node:{payload.node_id}",),
        ))

    contrib_id = new_id()
    contribution = Contribution(
        id=contrib_id,
        origin=payload.origin,
        derived_from=(finding.lineage(),),
        campaign_id=payload.campaign_id,
        scope=payload.scope,
        request_id=payload.request_id,
        responder=payload.responder,
        source=payload.provider_message_id or payload.responder,
        received_at=now_utc,
        event=finding,
        permitted_content=payload.raw_content,
        extractor=extractor,
        human_confirmation=None,
        evidence_family_id=family_id,
        relations=tuple(relations),
        restrictions=payload.restrictions,
    )

    # Propose Assessment
    assessment = None
    review_tasks: list[ReviewTask] = []
    comparisons: list[ContextComparison] = []

    if question is not None:
        assessment_id = new_id()
        assessment = Assessment(
            id=assessment_id,
            origin=payload.origin,
            derived_from=(contribution.lineage(),),
            contribution=contribution,
            question=question,
            relations=contribution.relations,
            applicability="APPLICABLE" if matches else "NOT_APPLICABLE",
            missing_fields=sci_extraction.missing_fields,
            reviewer=extractor,
            decision="PROPOSED",
            confirmation=None,
            source_refs=(f"contrib:{contribution.id}",),
            restrictions=payload.restrictions,
        )

        # Check for Conflicting Scientific Findings (A09)
        conflicting_existing: list[tuple[ScientificFinding, Contribution]] = []
        for ex in existing_contributions:
            if (
                ex.campaign_id == question.campaign_id
                and ex.scope == question.scope
                and isinstance(ex.event, ScientificFinding)
            ):
                ex_finding = ex.event
                # Check for conflict in direction or state
                if (
                    finding.state is ResponseState.MEASURED_EFFECT
                    and ex_finding.state in (ResponseState.MEASURED_NO_EFFECT, AdditionalResponseState.INFORMATIVE_NEGATIVE)
                ) or (
                    finding.state in (ResponseState.MEASURED_NO_EFFECT, AdditionalResponseState.INFORMATIVE_NEGATIVE)
                    and ex_finding.state is ResponseState.MEASURED_EFFECT
                ):
                    conflicting_existing.append((ex_finding, ex))

        conflict_id = None
        if conflicting_existing:
            # Produce ContextComparison instead of averaging or majority voting (A09)
            ex_finding, ex_contrib = conflicting_existing[0]
            comparison = build_context_comparison(question, finding, ex_finding, contribution, ex_contrib)
            comparisons.append(comparison)
            conflict_id = comparison.id

            review_task = ReviewTask(
                question_id=question.id,
                contribution_id=contribution.id,
                assessment_id=assessment.id,
                required_role=question.required_reviewer or Role.SCIENTIFIC_LEAD,
                status="PENDING",
                reason="CONFLICT_REVIEW_REQUIRED: Conflicting scientific findings detected; majority voting and averaging prohibited",
                conflict_comparison_id=conflict_id,
                created_at=now_utc,
            )
            review_tasks.append(review_task)

            next_action = NextAction(
                action_type="HUMAN_CONFLICT_ADJUDICATION",
                rationale="Conflicting scientific findings produce context comparison and human review task, NOT majority vote or averaging",
                dependencies=(review_task.id,),
                owner_role=question.required_reviewer or Role.SCIENTIFIC_LEAD,
                target_id=assessment.id,
            )
        else:
            review_task = ReviewTask(
                question_id=question.id,
                contribution_id=contribution.id,
                assessment_id=assessment.id,
                required_role=question.required_reviewer or Role.SCIENTIFIC_LEAD,
                status="PENDING",
                reason="SCIENTIFIC_INTERPRETATION_REVIEW: Substantive scientific finding proposed for human confirmation",
                conflict_comparison_id=None,
                created_at=now_utc,
            )
            review_tasks.append(review_task)

            if not matches:
                next_action = NextAction(
                    action_type="AWAIT_CRITERIA_MISMATCH_REVIEW",
                    rationale=f"Scientific finding has criteria mismatch ({'; '.join(mismatch_reasons)}); routed to review queue",
                    dependencies=(review_task.id,),
                    owner_role=question.required_reviewer or Role.SCIENTIFIC_LEAD,
                    target_id=assessment.id,
                )
            else:
                next_action = NextAction(
                    action_type="AWAIT_SCIENTIFIC_REVIEW",
                    rationale="Scientific finding proposed; awaiting human scientific confirmation",
                    dependencies=(review_task.id,),
                    owner_role=question.required_reviewer or Role.SCIENTIFIC_LEAD,
                    target_id=assessment.id,
                )
    else:
        next_action = NextAction(
            action_type="AWAIT_QUESTION_ATTACHMENT",
            rationale="Scientific finding extracted without attached question",
            dependencies=(),
        )

    if outbox is not None:
        outbox.receive(payload.request_id, contribution, actor=extractor, now=now_utc)

    # Step 6: Emit approved case changes and operational changes SEPARATELY
    emission = IntakeEmission(
        operational_changes=(),
        case_changes=(),  # None approved yet: awaiting human review
        proposed_case_changes=(assessment,) if assessment else (),
        review_tasks=tuple(review_tasks),
        context_comparisons=tuple(comparisons),
        next_actions=(next_action,),
    )

    import_digest = content_digest({
        "payload_digest": payload_content_digest,
        "contribution_id": contribution.id,
        "timestamp": now_utc.isoformat(),
    })

    return IntakeResult(
        is_delivery_receipt=False,
        is_duplicate=False,
        contribution=contribution,
        assessment=assessment,
        emission=emission,
        import_digest=import_digest,
        security_flags=classification.security_flags,
    )


# ── Step 6 Approval Workflow ──────────────────────────────────────────────────

def complete_human_review(
    assessment: Assessment,
    *,
    reviewer: Actor,
    role: Role,
    decision: Literal["ACCEPTED", "REJECTED", "DEFERRED"],
    rationale: str,
    now: datetime,
) -> tuple[Assessment, IntakeEmission]:
    """Complete a human scientific review of a proposed assessment.
    
    Rule: An agent CANNOT sign a human review or close a scientific gap (PRD §8, T01 §2).
    Only an authenticated human with the configured review role may accept, reject, or defer.
    """
    if reviewer.actor_type is not ActorType.HUMAN:
        raise ValueError("only an authenticated human reviewer may sign a review decision")
    if role not in reviewer.roles:
        raise ValueError(f"reviewer lacks role {role}")
    if assessment.question.required_reviewer is not None and role != assessment.question.required_reviewer:
        raise ValueError(f"role {role} does not match question's required reviewer {assessment.question.required_reviewer}")

    now_utc = utc(now)
    confirmation = HumanConfirmation(
        actor=reviewer,
        role=role,
        timestamp=now_utc,
        statement_ref=assessment.id,
        rationale=rationale,
    )

    assessed = Assessment(
        id=assessment.id,
        origin=assessment.origin,
        derived_from=assessment.derived_from,
        contribution=assessment.contribution,
        question=assessment.question,
        relations=assessment.relations,
        applicability=assessment.applicability,
        missing_fields=assessment.missing_fields,
        reviewer=reviewer,
        decision=decision,
        confirmation=confirmation,
        source_refs=assessment.source_refs,
        restrictions=assessment.restrictions,
    )

    if decision == "ACCEPTED":
        case_changes = (assessed,)
        next_action = NextAction(
            action_type="ADAPT_PROSPECTIVE_PLAN",
            rationale="Scientific assessment accepted by human reviewer; prepare prospective plan proposal",
            dependencies=(assessed.id,),
            owner_role=role,
            target_id=assessed.id,
        )
    else:
        case_changes = ()
        next_action = NextAction(
            action_type="ARCHIVE_OR_DEFER_ASSESSMENT",
            rationale=f"Assessment was {decision.lower()} by human reviewer: {rationale}",
            dependencies=(assessed.id,),
            owner_role=role,
            target_id=assessed.id,
        )

    emission = IntakeEmission(
        operational_changes=(),
        case_changes=case_changes,
        proposed_case_changes=(),
        review_tasks=(),
        context_comparisons=(),
        next_actions=(next_action,),
    )

    return assessed, emission
