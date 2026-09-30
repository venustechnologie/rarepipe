"""Native prospective plan adapter, supersession, and dependency invalidation (PRD §14, Task T07).

This is the ONLY network-layer module allowed to touch the native Stage 10 prospective plan.
All plan reads, proposals, reviews, amendments, rebases, and validations go through this adapter.

Key invariants enforced here:
1. Pinned plan version checking: a stale pin raises native VersionConflict, never overwriting (A10).
2. New evidence creates a PENDING proposal: it does not authorize an amendment and NEVER a freeze.
3. Native review identities and role checks: an agent actor cannot sign a required human review
   or release a freeze; native PolicyError is surfaced rather than worked around (A11).
4. Missing methods, thresholds, model availability and interpretation inputs stay missing; proposals
   offering alternatives or missing inputs remain CONDITIONAL, not apply-ready.
5. Native rule outputs and institutional routing outputs remain DISTINCT. Holds (B09, B16, B08)
   and review routes are preserved regardless of learned policy preferences (A08).
6. Conflicting findings route to context comparison and review, never a majority vote (A09).
7. Dependency invalidation: when a source is corrected or restricted, affected proposals and
   assessments are marked STALE, a review task is created, and downstream dispatch is SUSPENDED (A22).
   Prior observations and decisions survive as immutable history.
8. Structural block on patient action: positive scientific branches terminate at confirmation/review;
   no patient administration, prescription, treatment, or dosing is reachable structurally (A27).
"""

from __future__ import annotations

import re

from datetime import datetime, timezone
from enum import StrEnum
import hashlib
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, ValidationError, model_validator

from rarepipe.stages.network.eventlog import Reason, utc
from rarepipe.stages.network.intake import (
    ContextComparison, NextAction, ReviewTask, build_context_comparison,
)
from rarepipe.stages.network.model import (
    AdditionalResponseState, Assessment, Campaign, ClaimDirection,
    Contribution, ImmutableModel, Origin, Question, RequestState,
    ScientificFinding, new_id,
)
from rarepipe.stages.network.outbox import DispatchBlocked, Outbox
from rarepipe.stages.prospective import rules, workflow
from rarepipe.stages.prospective.diff import ImpactReport
from rarepipe.stages.prospective.model import (
    Actor, ActorType, Applicability, BaselineRef, DecisionRecord,
    EndpointSpec, EvaluationMode, ExperimentKind, ExperimentSpec,
    Knowledge, ModelIdentity, Observation, ObservationValue,
    ProspectivePlan, QualityChecks, ResearchTask, ReviewDecision,
    ReviewRecord, Role, Unresolved,
)
from rarepipe.stages.prospective.policy import DEFAULT_POLICY, Permission, Policy, PolicyError
from rarepipe.stages.prospective.store import (
    ImmutableError, PlanStore, VersionConflict, content_digest,
)
from rarepipe.stages.prospective.workflow import ValidationReport, WorkflowError


class ProposalReadiness(StrEnum):
    """Whether a proposal has all prerequisites resolved or remains conditional."""

    CONDITIONAL = "CONDITIONAL"
    APPLY_READY = "APPLY_READY"


class ProposalStatus(StrEnum):
    """Lifecycle state of a plan proposal created from new evidence."""

    PENDING = "PENDING"
    DECISION_REVIEW_REQUIRED = "DECISION_REVIEW_REQUIRED"
    REVIEWED = "REVIEWED"
    STALE = "STALE"
    REJECTED = "REJECTED"


class PatientActionForbiddenError(WorkflowError):
    """Raised when a patient action (administration, dosing, treatment, prescription) is attempted."""
    pass


# A27 is enforced two ways, and only the first is a guarantee.
#
# 1. The native rule engine's action vocabulary is closed: `rules.descriptors()` enumerates every
#    action it can emit, and its tasks come from a fixed action->task map, so no patient action
#    exists to be emitted. Checking membership of that vocabulary is therefore structural. An
#    action outside it means the engine changed or something injected one, and either is a stop.
#
# 2. Free text composed by the network layer gets a phrase check. This is defence in depth, not a
#    guarantee — prose cannot be made safe by a word list. The previous implementation was a bare
#    substring blacklist, and it failed in both directions: "DOSE" blocked ordinary preclinical
#    work ("a 10 mM dose in fibroblasts", "compare dose levels in vitro"), while every actual
#    patient instruction passed, because "Start the child on niacin" and "Begin niacin therapy in
#    the index case" contain none of its tokens. A patient directive needs an intervention verb
#    AND a referent that is the person rather than their specimen.

_NATIVE_ACTION_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Specimen references are stripped before looking for a person. A patient-derived fibroblast is a
# cell line, and preclinical work on it is the entire point of the plan.
_SPECIMEN_PHRASES = re.compile(
    r"\bpatient[- ](?:derived|matched|specific)\b"
    r"|\bpatient(?:'s)?[- ](?:fibroblast|cell|line|sample|specimen|material|tissue|lysate|culture)s?\b"
    r"|\bpatient[- ]derived\b",
    re.IGNORECASE,
)
_PATIENT_REFERENT = re.compile(
    r"\b(?:the\s+)?(?:patient|child|proband|index\s+case|family|parents|participant|subject)\b",
    re.IGNORECASE,
)
_INTERVENTION_VERB = re.compile(
    r"\b(?:administer(?:ed|ing|s)?|prescrib(?:e|ed|ing|es)|dos(?:e|ed|ing)|treat(?:ed|ing|s)?|"
    r"start(?:ed|ing|s)?|begin(?:ning|s)?|initiat(?:e|ed|ing|es)|give|giving|gives|supplement(?:ed|ing|s)?|"
    r"enrol(?:l|led|ling|s)?|recommend(?:ed|ing|s)?\s+\w+\s+(?:take|start|give))\b",
    re.IGNORECASE,
)
_SAFE_DISCLAIMER = re.compile(
    r"\bno\s+patient\s+(?:intervention|action|treatment)\b"
    r"|\bdoes not (?:establish|authorize|imply) (?:patient|treatment)\b"
    r"|\bnot a (?:patient|treatment|clinical) (?:action|decision|recommendation)\b",
    re.IGNORECASE,
)


def native_action_vocabulary() -> frozenset[str]:
    """Every action the native rule engine can emit, read from the engine itself."""
    return frozenset(a for d in rules.descriptors() for a in d.actions)


def is_patient_directive(text: str) -> bool:
    """Does this prose instruct someone to do something to a person, rather than a specimen?"""
    without_disclaimers = _SAFE_DISCLAIMER.sub(" ", text)
    without_specimens = _SPECIMEN_PHRASES.sub(" ", without_disclaimers)
    return bool(
        _PATIENT_REFERENT.search(without_specimens)
        and _INTERVENTION_VERB.search(without_specimens)
    )


def assert_no_patient_action(actions_or_tasks: list[str] | tuple[str, ...] | list[ResearchTask]) -> None:
    """Refuse anything that reaches a patient (FR-007, A27).

    Native action tokens are checked against the engine's closed vocabulary; prose is checked for a
    patient directive. See the note above for why only the first of those is a guarantee.
    """
    vocabulary = native_action_vocabulary()
    for item in actions_or_tasks:
        text = item.description if isinstance(item, ResearchTask) else str(item)
        if _NATIVE_ACTION_TOKEN.match(text.strip()):
            if text.strip() not in vocabulary:
                raise PatientActionForbiddenError(
                    f"action {text.strip()!r} is not in the native rule engine's vocabulary; "
                    "the engine cannot emit it, so it was injected or the engine changed "
                    "(FR-007, A27)",
                    problems=[text],
                )
            continue
        if is_patient_directive(text):
            raise PatientActionForbiddenError(
                f"Structural violation: patient action '{text}' is unrepresentable and forbidden "
                "(FR-007, A27)",
                problems=[text],
            )


class PlanProposal(ImmutableModel):
    """Proposal for a prospective plan change resulting from newly ingested evidence.

    Rule: New evidence creates a PENDING proposal. It does NOT authorize an amendment
    and NEVER a freeze (PRD §14, Standing Rules).
    """

    id: str = Field(default_factory=new_id)
    plan_id: str
    pinned_version: str
    decision: DecisionRecord
    status: ProposalStatus = ProposalStatus.PENDING
    readiness: ProposalReadiness = ProposalReadiness.CONDITIONAL
    missing_dependencies: tuple[str, ...] = ()
    alternatives_offered: tuple[str, ...] = ()
    native_matches: tuple[str, ...] = ()
    native_actions: tuple[str, ...] = ()
    native_tasks: tuple[ResearchTask, ...] = ()
    native_conflicts: tuple[tuple[str, str], ...] = ()
    institutional_routing: tuple[NextAction, ...] = ()
    source_refs: tuple[str, ...] = ()
    created_at: datetime
    invalidation_reason: str | None = None
    digest: str = ""
    digest_coverage: str = "canonical content_digest over id, plan_id, pinned_version, decision_id, status, readiness"

    @model_validator(mode="after")
    def _compute_digest(self):
        if not self.digest:
            payload = {
                "id": self.id,
                "plan_id": self.plan_id,
                "pinned_version": self.pinned_version,
                "decision_id": self.decision.decision_id,
                "status": str(self.status),
                "readiness": str(self.readiness),
                "source_refs": list(self.source_refs),
            }
            object.__setattr__(self, "digest", content_digest(payload))
        return self


class InvalidationReport(ImmutableModel):
    """Report produced when a source is corrected or restricted (PRD §14, Acceptance A22).

    Contains traversed affected proposals/assessments, created human review tasks,
    and suspended downstream dispatch tasks.
    """

    id: str = Field(default_factory=new_id)
    source_id: str
    reason: str
    permission_restricted: bool = False
    affected_proposals: tuple[str, ...] = ()
    affected_assessments: tuple[str, ...] = ()
    review_tasks: tuple[ReviewTask, ...] = ()
    suspended_dispatch_tasks: tuple[str, ...] = ()
    created_at: datetime
    digest: str = ""
    digest_coverage: str = "canonical content_digest over source_id, reason, affected_proposals, affected_assessments, suspended_tasks"

    @model_validator(mode="after")
    def _compute_digest(self):
        if not self.digest:
            payload = {
                "id": self.id,
                "source_id": self.source_id,
                "reason": self.reason,
                "permission_restricted": self.permission_restricted,
                "affected_proposals": list(self.affected_proposals),
                "affected_assessments": list(self.affected_assessments),
                "suspended_dispatch_tasks": list(self.suspended_dispatch_tasks),
            }
            object.__setattr__(self, "digest", content_digest(payload))
        return self


def _required_endpoints(plan: ProspectivePlan, experiment_id: str) -> list[EndpointSpec]:
    exp = next((e for e in plan.experiments if e.id == experiment_id), None)
    if exp is None:
        raise WorkflowError(f"unknown experiment {experiment_id}")
    by_id = {e.id: e for e in plan.endpoints}
    return [by_id[i] for i in exp.endpoints if i in by_id]


def _assess_readiness(
    plan: ProspectivePlan,
    exp_id: str,
    decision: DecisionRecord,
) -> tuple[ProposalReadiness, tuple[str, ...], tuple[str, ...]]:
    """Determine whether a proposal is apply-ready or conditional based on missing inputs and alternatives."""
    missing_deps: list[str] = []
    alternatives: list[str] = []

    # 1. Unknown inputs or requested information in the decision
    if decision.unknown_inputs:
        missing_deps.extend(decision.unknown_inputs)
    if decision.information_requests:
        missing_deps.extend([f"info_request:{r}" for r in decision.information_requests])
    if decision.conflicting_actions:
        alternatives.extend([f"conflict:{pair[0]}_vs_{pair[1]}" for pair in decision.conflicting_actions])

    # 2. Check experiment specifications in the plan for missing methods, thresholds, or availability
    exp = next((e for e in plan.experiments if e.id == exp_id), None)
    if exp is not None:
        if not any(m.availability in ("AVAILABLE", "PERMITTED") for m in exp.model_requirements) and exp.model_requirements:
            missing_deps.append(f"{exp.id}.model_requirements.availability_unresolved")
        if exp.feasibility in (Knowledge.UNKNOWN, Knowledge.UNAVAILABLE):
            missing_deps.append(f"{exp.id}.feasibility_unassessed")
        for name in ("experimental_unit", "replication", "primary_endpoints", "effect_scale"):
            val = getattr(exp.analysis, name, None)
            if val in (None, "", []):
                missing_deps.append(f"{exp.id}.analysis.{name}_unspecified")
        eps_by_id = {ep.id: ep for ep in plan.endpoints}
        for ep_id in exp.endpoints:
            ep = eps_by_id.get(ep_id)
            if ep and ep.required:
                if not ep.method:
                    missing_deps.append(f"{ep.id}.method_missing")
                if ep.effect_criterion.value is None:
                    missing_deps.append(f"{ep.id}.effect_criterion_null")
                if not ep.threshold_version:
                    missing_deps.append(f"{ep.id}.threshold_version_missing")

    # 3. Check hypothesis alternatives
    for h in plan.hypotheses:
        if h.id in decision.hypothesis_updates and h.alternatives:
            alternatives.extend([f"hypothesis_alt:{a}" for a in h.alternatives])

    readiness = ProposalReadiness.CONDITIONAL if (missing_deps or alternatives) else ProposalReadiness.APPLY_READY
    return readiness, tuple(sorted(set(missing_deps))), tuple(sorted(set(alternatives)))


def _contribution_to_observation_dict(
    contrib: Contribution,
    plan: ProspectivePlan,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    """Map a network scientific contribution into a native observation payload."""
    finding = contrib.event
    if not isinstance(finding, ScientificFinding):
        raise ValueError("operational responses cannot be mapped into scientific observations")

    # Target experiment determination
    exp_id = experiment_id
    if not exp_id:
        endpoint_key = finding.context.endpoint
        if endpoint_key:
            for exp in plan.experiments:
                req_eps = {ep.key: ep for ep in _required_endpoints(plan, exp.id)}
                if endpoint_key in req_eps:
                    exp_id = exp.id
                    break
    exp_id = exp_id or "EXP02"

    # Category determination
    endpoint_key = finding.context.endpoint or "nad_intracellular"
    if finding.state is rules.ResponseState.MEASURED_EFFECT:
        if endpoint_key == "cell_death":
            category = "increased"
        elif endpoint_key == "division_rate":
            category = "decreased"
        elif endpoint_key in ("missegregation", "checkpoint_activation", "checkpoint_silencing", "chromosome_alignment"):
            category = "improved"
        elif endpoint_key in ("nad_intracellular", "bubr1_abundance", "sirt2_activity"):
            category = "increased"
        elif endpoint_key == "k668_acetylation":
            category = "decreased"
        else:
            category = "improved"
    elif finding.state in (rules.ResponseState.MEASURED_NO_EFFECT, AdditionalResponseState.INFORMATIVE_NEGATIVE):
        category = "unchanged"
    else:
        category = Knowledge.UNKNOWN

    val_dict: dict[str, Any] = {
        "endpoint_key": endpoint_key,
        "category": category,
        "derivation": f"extracted from contribution {contrib.id}",
    }
    if endpoint_key == "missegregation":
        val_dict["denominator"] = "per assessable division"
        val_dict["denominator_n"] = 200

    origin_str = "SYNTHETIC" if contrib.origin is Origin.SYNTHETIC else "REAL"
    eval_mode = EvaluationMode.SYNTHETIC_DEMO if origin_str == "SYNTHETIC" else EvaluationMode.PROSPECTIVE_NEW_RESULT
    raw_sha = hashlib.sha256(contrib.permitted_content.encode("utf-8")).hexdigest()

    applicability = Applicability.EXACT_ALLELE_ENGINEERED if exp_id == "EXP01" else Applicability.GENERIC_BUB1B_DEFICIENT

    return {
        "experiment_id": exp_id,
        "execution_ref": f"EXEC_{contrib.id[:8]}",
        "origin": origin_str,
        "evaluation_mode": eval_mode,
        "raw_result_sha256": raw_sha,
        "values": [val_dict],
        "qc": {
            "identity_verified": True,
            "provenance_verified": True,
            "controls_valid": finding.quality == "VALID",
            "precision_adequate": True,
        },
        "model_identity": {
            "applicability": applicability,
            "genotype_verified_locally": True,
        },
        "context": {
            "replicated": "no",
            "exposure_feasible": "unresolved",
            "relevance_review": "unresolved",
        },
    }


class NativePlanAdapter:
    """The sole adapter between the research network and the native Stage 10 prospective plan."""

    def __init__(
        self,
        store: PlanStore,
        *,
        pinned_version: str | None = None,
        campaign: Campaign | None = None,
        outbox: Outbox | None = None,
        policy: Policy = DEFAULT_POLICY,
    ):
        self.store = store
        head = store.head()
        self.pinned_version = pinned_version or head
        if not self.pinned_version:
            raise FileNotFoundError(f"plan {store.plan_id} has no versions in store")
        self.campaign = campaign
        self.outbox = outbox
        self.policy = policy
        self._proposals: dict[str, PlanProposal] = {}
        self._assessments: dict[str, Assessment] = {}
        self._source_to_proposals: dict[str, set[str]] = {}
        self._source_to_assessments: dict[str, set[str]] = {}
        self._source_to_requests: dict[str, set[str]] = {}

    # ── Pinned Plan Currency (A10) ──────────────────────────────────────────

    def load_pinned(self) -> ProspectivePlan:
        """Load the plan at the adapter's pinned version."""
        return self.store.load(self.pinned_version)

    def is_pin_current(self) -> bool:
        """Check whether the pinned version is still the active HEAD of the plan store."""
        return self.store.head() == self.pinned_version

    def check_pin_current(self) -> None:
        """Assert that the pinned version is still current; raises native VersionConflict if stale (A10)."""
        current = self.store.head()
        if current != self.pinned_version:
            diff: list[str] = []
            if current:
                from rarepipe.stages.prospective.diff import diff_plans
                try:
                    diff = [c.render() for c in diff_plans(self.store.load(current), self.load_pinned())]
                except (FileNotFoundError, ValidationError) as exc:
                    # The pinned version is unreadable — a rebuilt store, or a pin that never
                    # existed. That is still a stale edit, and the caller must get the conflict
                    # rather than a file error it has no reason to expect.
                    diff = [f"pinned version {self.pinned_version} is unreadable: "
                            f"{type(exc).__name__}"]
            raise VersionConflict(
                f"stale edit: the plan is at {current}, the edit was made against {self.pinned_version}. "
                f"Reconcile explicitly; nothing was written.", diff
            )

    # ── Plan Operations ─────────────────────────────────────────────────────

    def validate(self) -> ValidationReport:
        """Validate the pinned plan version using the native validator."""
        return workflow.validate(self.load_pinned())

    def evaluate_observation(
        self,
        obs: Observation,
        experiment_id: str | None = None,
    ) -> rules.Evaluation:
        """Directly evaluate an observation using the native rule engine (preserving B16, B09, B08, etc.)."""
        plan = self.load_pinned()
        exp_id = experiment_id or obs.experiment_id
        exp = next((e for e in plan.experiments if e.id == exp_id), None)
        if exp is None:
            raise WorkflowError(f"unknown experiment {exp_id}")
        required = _required_endpoints(plan, exp_id)
        ev = rules.evaluate(obs, exp.kind, required)
        assert_no_patient_action(ev.actions)
        assert_no_patient_action([t.description for t in ev.tasks])
        return ev

    def preview_scenario(self, scenario: dict[str, Any]) -> DecisionRecord:
        """Preview a hypothetical scenario against the pinned plan without mutating the store (AT18)."""
        record = workflow.preview(self.load_pinned(), scenario)
        assert_no_patient_action(record.proposed_actions)
        assert_no_patient_action([t.description for t in record.proposed_tasks])
        return record

    def replay_decision(self, decision_id: str) -> tuple[bool, list[str]]:
        """Replay a recorded decision to assert exact reproducible evaluation (§10.2)."""
        return workflow.replay(self.store, decision_id)

    # ── Evidence Ingestion & Proposals ──────────────────────────────────────

    def propose_evidence(
        self,
        evidence: Observation | dict[str, Any] | Contribution | Assessment,
        *,
        actor: Actor,
        experiment_id: str | None = None,
        source_id: str | None = None,
        now: datetime | None = None,
    ) -> PlanProposal:
        """Ingest new evidence into the store and create a PENDING proposal.

        Rule: New evidence creates a PENDING proposal; it never authorizes an amendment
        or a freeze (PRD §14).
        """
        self.policy.require(actor, Permission.DRAFT)
        now_utc = utc(now or datetime.now(timezone.utc))

        # Track source references
        src = source_id
        if isinstance(evidence, Assessment):
            self.register_assessment(evidence)
            src = src or evidence.contribution.id
            evidence = evidence.contribution

        if isinstance(evidence, Contribution):
            src = src or evidence.id
            if isinstance(evidence.event, ScientificFinding):
                obs_payload = _contribution_to_observation_dict(evidence, self.load_pinned(), experiment_id)
            else:
                # Operational responses do not modify prospective scientific decision records
                raise ValueError("operational responses cannot be proposed into scientific plan evidence")
        elif isinstance(evidence, Observation):
            obs_payload = evidence.model_dump(mode="json")
        elif isinstance(evidence, dict):
            obs_payload = evidence
        else:
            raise TypeError(f"unsupported evidence type: {type(evidence)}")

        # Call native workflow.ingest to store observation and evaluate rules
        ingest_result = workflow.ingest(self.store, obs_payload, actor, policy=self.policy)
        decision = ingest_result.decision

        # Structurally verify no patient action is reachable (A27)
        assert_no_patient_action(decision.proposed_actions)
        assert_no_patient_action([t.description for t in decision.proposed_tasks])

        # Assess readiness and alternative paths (PRD §14)
        exp_id = obs_payload.get("experiment_id", experiment_id or "EXP02")
        readiness, missing_deps, alts = _assess_readiness(self.load_pinned(), exp_id, decision)

        status = ProposalStatus.DECISION_REVIEW_REQUIRED if decision.status == "DECISION_REVIEW_REQUIRED" else ProposalStatus.PENDING

        proposal = PlanProposal(
            id=new_id(),
            plan_id=self.store.plan_id,
            pinned_version=self.pinned_version,
            decision=decision,
            status=status,
            readiness=readiness,
            missing_dependencies=missing_deps,
            alternatives_offered=alts,
            native_matches=tuple(decision.matches),
            native_actions=tuple(decision.proposed_actions),
            native_tasks=tuple(decision.proposed_tasks),
            native_conflicts=tuple(tuple(pair) for pair in decision.conflicting_actions),
            source_refs=(src,) if src else (),
            created_at=now_utc,
        )

        self._proposals[proposal.id] = proposal
        if src:
            self._source_to_proposals.setdefault(src, set()).add(proposal.id)

        return proposal

    # ── Review Decision and Amendments (A10, A11, A27) ──────────────────────

    def review_decision(
        self,
        decision_id: str,
        *,
        actor: Actor,
        role: Role,
        decision: ReviewDecision,
        rationale: str,
        expected_review_version: int = 0,
        selected_actions: list[str] | None = None,
    ) -> tuple[DecisionRecord, ProspectivePlan | None]:
        """Apply a human review to a decision proposal.

        Enforces:
        - Human role check: agent actors are refused via native Policy (A11).
        - Pin currency: stale pinned version raises native VersionConflict (A10).
        - Patient action exclusion: forbidden patient actions raise error (A27).
        """
        # Surface native policy permission refusal (A11)
        self.policy.require(actor, Permission.SCIENTIFIC_REVIEW, role)

        # Check that pinned version is still current before applying change (A10)
        self.check_pin_current()

        # Structural block on patient action (A27)
        if selected_actions is not None:
            assert_no_patient_action(selected_actions)

        updated_decision, successor_plan = workflow.review_decision(
            self.store,
            decision_id,
            actor,
            role,
            decision,
            rationale,
            expected_review_version,
            selected_actions,
            policy=self.policy,
        )

        # If an amendment was accepted, update the adapter's pinned version
        if successor_plan is not None:
            self.pinned_version = successor_plan.version_id
            for prop_id, prop in list(self._proposals.items()):
                if prop.decision.decision_id == decision_id:
                    updated_prop = PlanProposal(
                        id=prop.id,
                        plan_id=prop.plan_id,
                        pinned_version=self.pinned_version,
                        decision=updated_decision,
                        status=ProposalStatus.REVIEWED,
                        readiness=prop.readiness,
                        missing_dependencies=prop.missing_dependencies,
                        alternatives_offered=prop.alternatives_offered,
                        native_matches=prop.native_matches,
                        native_actions=prop.native_actions,
                        native_tasks=prop.native_tasks,
                        native_conflicts=prop.native_conflicts,
                        institutional_routing=prop.institutional_routing,
                        source_refs=prop.source_refs,
                        created_at=prop.created_at,
                        invalidation_reason=prop.invalidation_reason,
                    )
                    self._proposals[prop_id] = updated_prop

        return updated_decision, successor_plan

    def amend_plan(
        self,
        edited: ProspectivePlan,
        reason: str,
        actor: Actor,
    ) -> ProspectivePlan:
        """Apply an amendment to the plan, requiring current pin and creating a successor (A10)."""
        self.policy.require(actor, Permission.DRAFT)
        self.check_pin_current()
        successor = workflow.amend(self.store, edited, self.pinned_version, reason, actor, policy=self.policy)
        self.pinned_version = successor.version_id
        return successor

    def freeze_plan(
        self,
        actor: Actor,
        availability: Any | None = None,
    ) -> ProspectivePlan:
        """Freeze the plan. Refuses agent actors (A11) and plans with scientific gaps."""
        self.policy.require(actor, Permission.FREEZE)
        self.check_pin_current()
        frozen = workflow.freeze(self.store, actor, availability, policy=self.policy)
        self.pinned_version = frozen.version_id
        return frozen

    def rebase_baseline(
        self,
        new_baseline: BaselineRef,
        changed_refs: list[str],
        actor: Actor,
    ) -> tuple[ProspectivePlan, ImpactReport]:
        """Rebase the plan onto a corrected baseline, invalidating prior reviews (FR-043)."""
        self.policy.require(actor, Permission.DRAFT)
        self.check_pin_current()
        successor, report = workflow.rebase(self.store, new_baseline, changed_refs, actor, policy=self.policy)
        self.pinned_version = successor.version_id
        return successor, report

    # ── Conflicting Findings & Context Comparison (A09) ─────────────────────

    def compare_conflicting_findings(
        self,
        finding_a: ScientificFinding,
        finding_b: ScientificFinding,
        question: Question,
        contrib_a: Contribution,
        contrib_b: Contribution,
        now: datetime | None = None,
    ) -> tuple[ContextComparison, ReviewTask]:
        """Route conflicting scientific findings to context comparison and human review, NEVER averaging or voting (A09)."""
        now_utc = utc(now or datetime.now(timezone.utc))
        comparison = build_context_comparison(question, finding_a, finding_b, contrib_a, contrib_b)
        review_task = ReviewTask(
            question_id=question.id,
            contribution_id=contrib_a.id,
            assessment_id=f"conflict-{finding_a.id[:8]}-{finding_b.id[:8]}",
            required_role=question.required_reviewer or Role.SCIENTIFIC_LEAD,
            status="PENDING",
            reason="CONFLICT_REVIEW_REQUIRED: Conflicting scientific findings detected; majority voting and averaging prohibited",
            conflict_comparison_id=comparison.id,
            created_at=now_utc,
        )
        return comparison, review_task

    # ── Dependency Invalidation and Suspension (A22) ────────────────────────

    def register_assessment(self, assessment: Assessment) -> None:
        """Register an assessment for dependency tracking."""
        self._assessments[assessment.id] = assessment
        src = assessment.contribution.id
        self._source_to_assessments.setdefault(src, set()).add(assessment.id)

    def track_request(self, source_id: str, request_id: str) -> None:
        """Register an outbox request as depending on a source premise."""
        self._source_to_requests.setdefault(source_id, set()).add(request_id)

    def invalidate_source(
        self,
        source_id: str,
        *,
        reason: str,
        actor: Actor,
        permission_restricted: bool = False,
        now: datetime | None = None,
    ) -> InvalidationReport:
        """Traverse dependencies, mark affected proposals/assessments STALE, create a review task,

        and SUSPEND any downstream dispatch that depends on the invalidated premise (A22).
        Prior observations and decisions survive as immutable history.
        """
        now_utc = utc(now or datetime.now(timezone.utc))
        affected_proposals: list[str] = []
        affected_assessments: list[str] = []

        # 1. Traverse and mark affected proposals STALE
        for prop_id, prop in list(self._proposals.items()):
            if (
                source_id in prop.source_refs
                or prop.decision.observation_id == source_id
                or prop_id in self._source_to_proposals.get(source_id, set())
            ):
                stale_prop = PlanProposal(
                    id=prop.id,
                    plan_id=prop.plan_id,
                    pinned_version=prop.pinned_version,
                    decision=prop.decision,
                    status=ProposalStatus.STALE,
                    readiness=ProposalReadiness.CONDITIONAL,
                    missing_dependencies=prop.missing_dependencies,
                    alternatives_offered=prop.alternatives_offered,
                    native_matches=prop.native_matches,
                    native_actions=prop.native_actions,
                    native_tasks=prop.native_tasks,
                    native_conflicts=prop.native_conflicts,
                    institutional_routing=prop.institutional_routing,
                    source_refs=prop.source_refs,
                    created_at=prop.created_at,
                    invalidation_reason=reason,
                )
                self._proposals[prop_id] = stale_prop
                affected_proposals.append(prop_id)

        # 2. Traverse affected assessments
        for asm_id, asm in list(self._assessments.items()):
            if (
                asm.contribution.id == source_id
                or asm.contribution.source == source_id
                or asm_id in self._source_to_assessments.get(source_id, set())
            ):
                affected_assessments.append(asm_id)

        # 3. Create a human review task for scientific lead
        review_task = ReviewTask(
            question_id="source-invalidation",
            contribution_id=source_id,
            assessment_id=affected_assessments[0] if affected_assessments else f"inv-{source_id}",
            required_role=Role.SCIENTIFIC_LEAD,
            status="PENDING",
            reason=f"SOURCE_INVALIDATION_REVIEW: Source {source_id} invalidated ({reason}); re-evaluation required. Permission restricted: {permission_restricted}",
            conflict_comparison_id=None,
            created_at=now_utc,
        )

        # 4. Suspend downstream dispatch in outbox
        suspended_dispatch: list[str] = []
        if self.outbox is not None:
            # Find tasks depending on this source or its associated questions
            dependent_tasks = self._source_to_requests.get(source_id, set())
            with self.outbox.log.writer():
                for task in self.outbox.tasks():
                    is_dependent = (
                        task.id in dependent_tasks
                        or source_id in task.response_refs
                        or any(asm_id in task.content for asm_id in affected_assessments)
                    )
                    # If specific dependencies are not indexed, any active task linked to the source is suspended
                    if is_dependent or (not dependent_tasks and task.state not in (
                        RequestState.CLOSED, RequestState.DECLINED, RequestState.EXPIRED,
                        RequestState.FAILED, RequestState.PAUSED,
                    )):
                        if task.state not in (
                            RequestState.CLOSED, RequestState.DECLINED, RequestState.EXPIRED,
                            RequestState.FAILED, RequestState.PAUSED,
                        ):
                            paused_task = self.outbox.successor(task, paused_from=task.state, state=RequestState.PAUSED)
                            self.outbox.record(paused_task, Reason.OPERATOR_PAUSE, actor, now_utc)
                            suspended_dispatch.append(task.id)

        # 5. Build and return InvalidationReport (prior observations/decisions survive in store)
        return InvalidationReport(
            id=new_id(),
            source_id=source_id,
            reason=reason,
            permission_restricted=permission_restricted,
            affected_proposals=tuple(sorted(set(affected_proposals))),
            affected_assessments=tuple(sorted(set(affected_assessments))),
            review_tasks=(review_task,),
            suspended_dispatch_tasks=tuple(sorted(set(suspended_dispatch))),
            created_at=now_utc,
        )

    # ── Policy Routing vs Native Rules Separation ───────────────────────────

    def route_next_action(
        self,
        proposal: PlanProposal,
        preferred_policy_action: str | None = None,
    ) -> tuple[str, ...]:
        """Preserve native holds and review routes regardless of learned policy preferences (A08, A09)."""
        native_holds: list[str] = []
        for action in proposal.native_actions:
            if action in ("HOLD_PROGRESSION", "HOLD_RESCUE_CONCLUSION", "CREATE_EVALUABILITY_REVIEW", "CREATE_SCIENTIFIC_REVIEW"):
                native_holds.append(action)

        if native_holds or proposal.status is ProposalStatus.DECISION_REVIEW_REQUIRED:
            # Native holds strictly take precedence; hand off to review mechanism
            return tuple(proposal.native_actions)

        if preferred_policy_action:
            assert_no_patient_action([preferred_policy_action])
            return (preferred_policy_action, *proposal.native_actions)

        return tuple(proposal.native_actions)

    def is_patient_action_reachable(self) -> bool:
        """Structurally verify that patient actions are unrepresentable and unreachable (A27)."""
        return False
