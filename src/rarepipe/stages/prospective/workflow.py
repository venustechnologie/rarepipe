"""Plan operations: validate, freeze, ingest, preview, review, amend, rebase (PRD §6, §14, FR-040..FR-044).

Every mutation goes through PlanStore.commit with the version it was made against, so a stale edit is
a conflict, never a silent overwrite. Frozen versions are never touched: any change is a successor.
Previews write nothing and send nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.prospective import rules
from rarepipe.stages.prospective.diff import ImpactReport, impact
from rarepipe.stages.prospective.model import (
    ANALYSIS_REQUIRED,
    Actor,
    BaselineRef,
    DecisionRecord,
    EndpointSpec,
    EvaluationMode,
    Knowledge,
    ModelIdentity,
    Observation,
    OutcomeAvailability,
    PlanState,
    ProspectivePlan,
    QualityChecks,
    ReviewDecision,
    ReviewRecord,
    Role,
    TemporalStatus,
    Unresolved,
)
from rarepipe.stages.prospective.policy import DEFAULT_POLICY, Permission, Policy
from rarepipe.stages.prospective.store import PlanStore, VersionConflict, content_digest, review_digest

FREEZE_REVIEW_ROLES = (Role.SCIENTIFIC_LEAD, Role.ASSAY_SCIENTIST, Role.STATISTICIAN)


class WorkflowError(ValueError):
    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message + ("" if not problems else ": " + "; ".join(problems)))
        self.problems = problems or []


# ── validation and readiness ─────────────────────────────────────────────────


@dataclass
class ValidationReport:
    structural: list[str] = field(default_factory=list)
    scientific_readiness: list[Unresolved] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    policy: list[str] = field(default_factory=list)

    @property
    def freezable(self) -> bool:
        return not (self.structural or self.scientific_readiness or self.provenance or self.policy)

    def render(self) -> str:
        lines = [f"structural: {len(self.structural)}", *[f"  - {x}" for x in self.structural],
                 f"scientific readiness: {len(self.scientific_readiness)}",
                 *[f"  - {u.object_ref}.{u.field} — {u.reason} (owner: {u.owner.value}; blocks {u.blocks})"
                   for u in self.scientific_readiness],
                 f"provenance: {len(self.provenance)}", *[f"  - {x}" for x in self.provenance],
                 f"policy: {len(self.policy)}", *[f"  - {x}" for x in self.policy],
                 "FREEZABLE" if self.freezable else "NOT FREEZABLE — the gaps above are named, owned work"]
        return "\n".join(lines)


def validate(plan: ProspectivePlan) -> ValidationReport:
    r = ValidationReport()
    ids = [x.id for coll in (plan.hypotheses, plan.endpoints, plan.experiments, plan.forecasts, plan.assumptions)
           for x in coll]
    r.structural += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    hyp = {h.id for h in plan.hypotheses}
    eps = {e.id: e for e in plan.endpoints}
    exps = {e.id: e for e in plan.experiments}
    for f in plan.forecasts:
        for ref, pool in ((f.hypothesis, hyp), (f.experiment, exps), (f.endpoint, eps)):
            if ref not in pool:
                r.structural.append(f"{f.id} references unknown {ref}")
    for e in plan.experiments:
        r.structural += [f"{e.id} references unknown endpoint {x}" for x in e.endpoints if x not in eps]
    if plan.rules_version != rules.RULES_VERSION:
        r.structural.append(f"pinned rules {plan.rules_version} differ from the engine {rules.RULES_VERSION}")

    def gap(obj, fld, why, owner, blocks="scientific_freeze"):
        if not any(u.object_ref == obj and u.field == fld for u in r.scientific_readiness):
            r.scientific_readiness.append(Unresolved(object_ref=obj, field=fld, reason=why, owner=owner,
                                                     blocks=blocks))

    for e in plan.experiments:
        if not any(m.availability in ("AVAILABLE", "PERMITTED") for m in e.model_requirements) and \
                e.model_requirements:
            gap(e.id, "model_requirements.availability", "no required model is known to be available and "
                "permitted", Role.RESEARCH_OPERATIONS, "real_experiment_readiness")
        if e.feasibility in (Knowledge.UNKNOWN, Knowledge.UNAVAILABLE):
            gap(e.id, "feasibility", "laboratory feasibility not assessed", Role.ASSAY_SCIENTIST,
                "real_experiment_readiness")
        for name in ANALYSIS_REQUIRED:
            if getattr(e.analysis, name) in (None, ""):
                gap(e.id, f"analysis.{name}", "required analysis field (§8.4) not specified", Role.STATISTICIAN)
        if not e.analysis.primary_endpoints:
            gap(e.id, "analysis.primary_endpoints", "no primary endpoint declared", Role.STATISTICIAN)
        for ep_id in e.endpoints:
            ep = eps.get(ep_id)
            if not ep or not ep.required:
                continue
            if not ep.method:
                gap(ep.id, "method", "measurement method not chosen", ep.owner)
            if ep.effect_criterion.value is None:
                gap(ep.id, "effect_criterion", "numeric threshold required for interpretation is null (FR-040)",
                    ep.owner)
            if not ep.threshold_version:
                gap(ep.id, "threshold_version", "threshold not versioned", ep.owner)
            if not ep.validity_criteria:
                gap(ep.id, "validity_criteria", "measurement validity criteria not set", ep.owner)
    if plan.outcome_availability is None:
        gap("plan", "outcome_availability", "no result-availability declaration recorded (FR-014)",
            Role.RESEARCH_OPERATIONS)
    digest = review_digest(plan)
    for role in FREEZE_REVIEW_ROLES:
        if not any(rv.role is role and rv.decision is ReviewDecision.APPROVE_FOR_FREEZE and rv.object_version == digest
                   and rv.actor.actor_type.value == "HUMAN" for rv in plan.reviews):
            gap("plan", f"reviews.{role.value}", "no human review of this exact content approves freezing", role)

    if not plan.baseline.manifest_verified:
        r.provenance.append("baseline manifest not verified")
    if plan.baseline.status != "FROZEN" and not plan.synthetic_fixture:
        r.provenance.append("baseline is a CANDIDATE: a real scientific freeze needs the intended frozen baseline")
    if plan.synthetic_fixture != (plan.evaluation_mode is EvaluationMode.SYNTHETIC_DEMO):
        r.policy.append("a synthetic fixture must use SYNTHETIC_DEMO evaluation mode, and only a fixture may")
    return r


def record_plan_review(store: PlanStore, actor: Actor, role: Role, decision: ReviewDecision, rationale: str,
                       policy: Policy = DEFAULT_POLICY) -> ProspectivePlan:
    policy.require(actor, Permission.SCIENTIFIC_REVIEW, role)
    if not rationale.strip():
        raise WorkflowError("a review needs a rationale")
    plan = store.load()
    review = ReviewRecord(review_id=f"RV_{len(plan.reviews) + 1:03d}_{role.value}", actor=actor, role=role,
                          object_ref=plan.plan_id, object_version=review_digest(plan), decision=decision,
                          rationale=rationale, timestamp=utc_now().isoformat())
    successor = plan.model_copy(deep=True)
    successor.reviews.append(review)
    if successor.lifecycle is PlanState.DRAFT:
        successor.lifecycle = PlanState.REVIEW_REQUIRED
    return store.commit(successor, expected_parent=plan.version_id, reason=f"review by {role.value}",
                        kind="operational", actor=actor.identity)


def freeze(store: PlanStore, actor: Actor, availability: OutcomeAvailability | None = None,
           policy: Policy = DEFAULT_POLICY) -> ProspectivePlan:
    policy.require(actor, Permission.FREEZE)
    plan = store.load()
    if plan.lifecycle is PlanState.FROZEN:
        raise WorkflowError("already frozen; changes create a successor")
    if availability is not None:
        plan = plan.model_copy(update={"outcome_availability": availability}, deep=True)
    report = validate(plan)
    if not report.freezable:
        gaps = report.structural + [f"{u.object_ref}.{u.field}: {u.reason} (owner {u.owner.value})"
                                    for u in report.scientific_readiness] + report.provenance + report.policy
        raise WorkflowError("scientific freeze refused", gaps)
    frozen = plan.model_copy(deep=True)
    frozen.lifecycle = PlanState.FROZEN
    evidenced = bool(frozen.outcome_availability.timestamp_evidence) and \
        not frozen.outcome_availability.first_result_access and not frozen.outcome_availability.earliest_result_generation
    frozen.temporal_status = TemporalStatus.PRE_RESULT_EVIDENCED if evidenced else \
        TemporalStatus.TEMPORAL_STATUS_UNVERIFIED
    for f in frozen.forecasts:
        f.temporal = frozen.outcome_availability.model_copy(update={"status": frozen.temporal_status})
    return store.commit(frozen, expected_parent=plan.version_id,
                        reason="scientific freeze" + (" (synthetic fixture; preregisters nothing)"
                                                      if frozen.synthetic_fixture else ""),
                        kind="operational", actor=actor.identity)


# ── observations ─────────────────────────────────────────────────────────────


def _required_endpoints(plan: ProspectivePlan, experiment_id: str) -> list[EndpointSpec]:
    exp = next(e for e in plan.experiments if e.id == experiment_id)
    by_id = {e.id: e for e in plan.endpoints}
    return [by_id[i] for i in exp.endpoints if i in by_id]


def check_observation(plan: ProspectivePlan, obs: Observation) -> list[str]:
    problems: list[str] = []
    exp = next((e for e in plan.experiments if e.id == obs.experiment_id), None)
    if exp is None:
        return [f"unknown experiment {obs.experiment_id}"]
    if obs.origin == "SYNTHETIC" and not plan.synthetic_fixture:
        problems.append("a synthetic result cannot be promoted into a real plan's evidence (AT19)")
    if obs.origin == "REAL" and plan.synthetic_fixture:
        problems.append("a real result cannot enter a synthetic fixture plan")
    if (obs.origin == "SYNTHETIC") != (obs.evaluation_mode is EvaluationMode.SYNTHETIC_DEMO):
        problems.append("SYNTHETIC_DEMO evaluation mode is for synthetic results only, and they must use it")
    allowed = {m.applicability for m in exp.model_requirements}
    if allowed and obs.model_identity.applicability not in allowed:
        problems.append(f"model identity {obs.model_identity.applicability.value} is not one {exp.id} specifies")
    by_key = {e.key: e for e in _required_endpoints(plan, obs.experiment_id)}
    for v in obs.values:
        ep = by_key.get(v.endpoint_key)
        if ep is None:
            problems.append(f"{v.endpoint_key}: not an endpoint of {exp.id}")
            continue
        if v.quantity is not None and v.quantity.value is not None and ep.unit and v.quantity.unit != ep.unit:
            problems.append(f"{v.endpoint_key}: unit {v.quantity.unit!r} is incompatible with {ep.unit!r}; not coerced")
        if ep.denominator and v.category not in (None, *Knowledge) and (not v.denominator or v.denominator_n is None):
            problems.append(f"{v.endpoint_key}: missing denominator ({ep.denominator}) and its count")
        if v.category not in (None, *Knowledge):
            if v.quantity is not None and v.quantity.value is not None and not (v.analysis_ref and v.threshold_version) \
                    and not v.adjudicated_by:
                problems.append(f"{v.endpoint_key}: a derived category needs an AnalysisSpec reference and threshold "
                                "version, or a named human adjudicator")
            if (v.quantity is None or v.quantity.value is None) and not (v.derivation or v.adjudicated_by):
                problems.append(f"{v.endpoint_key}: a category without a value needs its derivation or adjudicator")
    return problems


def observation_id(obs: Observation) -> str:
    return "OBS_" + content_digest(obs, {"observation_id"}).split(":")[1][:16]


def _decision(plan: ProspectivePlan, obs: Observation, *, scenario: bool) -> DecisionRecord:
    exp = next(e for e in plan.experiments if e.id == obs.experiment_id)
    required = _required_endpoints(plan, obs.experiment_id)
    ev = rules.evaluate(obs, exp.kind, required)
    pinned = content_digest({"observation": obs.model_dump(mode="json"), "rules_version": rules.RULES_VERSION,
                             "endpoints": [e.model_dump(mode="json") for e in required]})
    interpretation = (["HYPOTHETICAL SCENARIO — not evidence, not a decision"] if scenario else []) + ev.interpretation
    return DecisionRecord(
        decision_id=("SCN_" if scenario else "DR_") + (obs.observation_id or "preview"), plan_id=plan.plan_id,
        plan_version=plan.version_id or "unversioned", observation_id=None if scenario else obs.observation_id,
        scenario=scenario, rules_version=rules.RULES_VERSION, pinned_inputs_digest=pinned, predicates=ev.predicates,
        matches=ev.matches, inadmissible_matches=ev.inadmissible, unknown_inputs=ev.unknown_inputs,
        information_requests=ev.information_requests, proposed_actions=ev.actions, conflicting_actions=ev.conflicts,
        status=ev.status, interpretation=interpretation, cannot_conclude=ev.cannot_conclude,
        hypothesis_updates=ev.hypothesis_updates,
        proposed_tasks=[t.model_copy(update={"origin": ("SCN_" if scenario else "DR_") + (obs.observation_id or ""),
                                             "id": f"{t.id}_{(obs.observation_id or 'SCN')[-6:]}"})
                        for t in ev.tasks])


@dataclass
class IngestResult:
    observation: Observation
    decision: DecisionRecord
    duplicate: bool


def ingest(store: PlanStore, payload: dict, actor: Actor, raw_file: Path | None = None,
           policy: Policy = DEFAULT_POLICY) -> IngestResult:
    policy.require(actor, Permission.DRAFT)
    plan = store.load()
    try:
        obs = Observation(**payload)
    except ValidationError as exc:
        raise WorkflowError("observation failed validation", [f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                                              for e in exc.errors()]) from None
    if raw_file is not None and hashlib.sha256(raw_file.read_bytes()).hexdigest() != obs.raw_result_sha256:
        raise WorkflowError("INTEGRITY_MISMATCH: the raw result bytes do not match raw_result_sha256")
    problems = check_observation(plan, obs)
    if problems:
        store.audit("ingest_rejected", actor=actor.identity, experiment=obs.experiment_id, problems=len(problems))
        raise WorkflowError("observation rejected", problems)
    obs.observation_id = observation_id(obs)
    stored, created = store.put_observation(obs)
    if not created:
        store.audit("ingest_duplicate", actor=actor.identity, observation=obs.observation_id)
        return IngestResult(stored, store.load_decision("DR_" + obs.observation_id), True)
    record = _decision(plan, stored, scenario=False)
    store.put_decision(record)
    store.set_execution(obs.experiment_id, "RESULT_REVIEW_REQUIRED", obs.observation_id)
    store.audit("ingest", actor=actor.identity, observation=obs.observation_id, decision=record.decision_id,
                matches=record.matches, status=record.status)
    return IngestResult(stored, record, False)


def preview(plan: ProspectivePlan, scenario: dict) -> DecisionRecord:
    """Hypothetical inputs only. Takes no store: it cannot write, send or change the case (AT18)."""
    exp = next((e for e in plan.experiments if e.id == scenario["experiment_id"]), None)
    if exp is None:
        raise WorkflowError(f"unknown experiment {scenario.get('experiment_id')}")
    values = [{"endpoint_key": k, "category": c, "derivation": "hypothetical scenario input"}
              for k, c in (scenario.get("values") or {}).items()]
    qc = {"identity_verified": True, "provenance_verified": True, "controls_valid": True, "precision_adequate": True,
          **(scenario.get("qc") or {})}
    applicability = exp.model_requirements[0].applicability if exp.model_requirements else "NOT_SPECIFIED"
    obs = Observation(experiment_id=exp.id, execution_ref="hypothetical", origin="SYNTHETIC",
                      evaluation_mode=EvaluationMode.SYNTHETIC_DEMO, raw_result_sha256="hypothetical",
                      values=values, qc=QualityChecks(**qc), context=scenario.get("context") or {},
                      model_identity=ModelIdentity(applicability=scenario.get("applicability", applicability)))
    obs.observation_id = "SCENARIO_" + observation_id(obs)[4:12]
    return _decision(plan, obs, scenario=True)


# ── review, amendment and rebase ─────────────────────────────────────────────


def review_decision(store: PlanStore, decision_id: str, actor: Actor, role: Role, decision: ReviewDecision,
                    rationale: str, expected_review_version: int, selected_actions: list[str] | None = None,
                    policy: Policy = DEFAULT_POLICY) -> tuple[DecisionRecord, ProspectivePlan | None]:
    """Human interpretation of a proposal. Rule evaluation and human judgement stay separate events."""
    policy.require(actor, Permission.SCIENTIFIC_REVIEW, role)
    if not rationale.strip():
        raise WorkflowError("a review needs a rationale")
    record = store.load_decision(decision_id)
    if record.scenario:
        raise WorkflowError("a scenario preview cannot be reviewed into the case")
    if record.review_version != expected_review_version:
        raise VersionConflict(f"{decision_id} was reviewed since you opened it (now at review version "
                              f"{record.review_version}, you edited {expected_review_version}); reconcile explicitly",
                              [f"existing review: {record.review.decision.value} by {record.review.actor.identity}"
                               if record.review else "no review yet"])
    selected = selected_actions if selected_actions is not None else [
        a for a in record.proposed_actions if not any(a in pair for pair in record.conflicting_actions)]
    forbidden = [a for a in selected if "ADMINIST" in a or "PRESCRIB" in a or "TREAT" in a]
    if forbidden:
        raise WorkflowError("no transition reaches a patient (FR-007)", forbidden)
    deviations = sorted(set(selected) ^ set(record.proposed_actions))
    review = ReviewRecord(review_id=f"RV_{decision_id}_{record.review_version + 1}", actor=actor, role=role,
                          object_ref=decision_id, object_version=str(record.review_version), decision=decision,
                          rationale=rationale + (f" [deviation from suggested actions: {', '.join(deviations)}]"
                                                 if deviations else ""),
                          timestamp=utc_now().isoformat())
    accepted = decision in (ReviewDecision.ACCEPT_INTERPRETATION, ReviewDecision.AMEND_WITH_REASON)
    updated = record.model_copy(update={
        "review": review, "review_version": record.review_version + 1, "selected_actions": selected,
        "status": "REVIEWED" if accepted else record.status,
        "case_state_delta": dict(record.hypothesis_updates) if accepted else {}}, deep=True)
    store.put_decision(updated)
    store.put_review(review)
    store.audit("review", actor=actor.identity, role=role.value, decision=decision_id, outcome=decision.value)
    if not accepted:
        return updated, None
    plan = store.load()
    successor = plan.model_copy(deep=True)
    successor.lifecycle = PlanState.DRAFT
    successor.reviews = []
    for h in successor.hypotheses:
        if h.id in updated.case_state_delta:
            h.assessment = updated.case_state_delta[h.id]  # type: ignore[assignment]
            h.assessment_note = f"updated by {decision_id} (reviewed by {role.value}); measured endpoints only"
    known = {t.id for t in successor.tasks}
    successor.tasks += [t for t in updated.proposed_tasks if t.id not in known
                        and any(a for a in selected if t.id.startswith(f"TASK_{a}"))]
    committed = store.commit(successor, expected_parent=plan.version_id, reason=f"reviewed {decision_id}",
                             kind="scientific", actor=actor.identity)
    return updated, committed


def amend(store: PlanStore, edited: ProspectivePlan, expected_parent: str, reason: str, actor: Actor,
          policy: Policy = DEFAULT_POLICY) -> ProspectivePlan:
    """Any change after a freeze is a successor. If outcomes were available, it is a post-result amendment."""
    policy.require(actor, Permission.DRAFT)
    parent = store.load(expected_parent)
    successor = edited.model_copy(deep=True)
    kind = "scientific"
    if parent.lifecycle is PlanState.FROZEN:
        successor.lifecycle = PlanState.DRAFT
        successor.reviews = []
        received = {exp for exp, e in store.execution().items() if e.get("observations")}
        changed = {f.id for f in successor.forecasts
                   if next((o for o in parent.forecasts if o.id == f.id), None) != f}
        endpoint_changes = {e.id for e in successor.endpoints
                            if next((o for o in parent.endpoints if o.id == e.id), None) != e}
        for f in successor.forecasts:
            touched = f.id in changed or f.endpoint in endpoint_changes
            if touched and f.experiment in received:
                f.temporal = f.temporal.model_copy(update={"status": TemporalStatus.POST_RESULT_AMENDMENT})
                kind = "post_result_amendment"
    return store.commit(successor, expected_parent=expected_parent, reason=reason, kind=kind, actor=actor.identity)


def rebase(store: PlanStore, new_baseline: BaselineRef, changed_refs: list[str], actor: Actor,
           policy: Policy = DEFAULT_POLICY) -> tuple[ProspectivePlan, ImpactReport]:
    """Rebase onto a corrected baseline. History stays; the successor's reviews are invalidated (FR-043)."""
    policy.require(actor, Permission.DRAFT)
    plan = store.load()
    report = impact(plan, new_baseline, changed_refs)
    successor = plan.model_copy(deep=True)
    successor.baseline = new_baseline
    successor.reviews = []
    successor.lifecycle = PlanState.REVIEW_REQUIRED
    snap = new_baseline.semantic_digests.get("stage09")
    for f in successor.forecasts:
        if f.id in report.affected_forecasts:
            f.cannot_conclude = list(dict.fromkeys(f.cannot_conclude + [
                f"re-evaluation required after baseline change; originally made against {f.evidence_snapshot}"]))
            f.evidence_snapshot = snap or f.evidence_snapshot
    committed = store.commit(successor, expected_parent=plan.version_id,
                             reason="rebase onto corrected baseline: " + json.dumps(changed_refs),
                             kind="scientific", actor=actor.identity)
    return committed, report


def replay(store: PlanStore, decision_id: str) -> tuple[bool, list[str]]:
    """Re-run the rules on the pinned inputs; the evaluation must reproduce exactly (§10.2)."""
    record = store.load_decision(decision_id)
    plan = store.load(record.plan_version)
    obs = next(o for o in store.observations() if o.observation_id == record.observation_id)
    again = _decision(plan, obs, scenario=False)
    diffs = [name for name in ("pinned_inputs_digest", "predicates", "matches", "inadmissible_matches",
                               "unknown_inputs", "proposed_actions", "conflicting_actions", "status",
                               "hypothesis_updates")
             if getattr(again, name) != getattr(record, name) and not (name == "status" and record.status == "REVIEWED")]
    return not diffs, diffs
