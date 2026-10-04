"""The compiler: P = (X0, X_target, X_unsafe, M, U, Y, E) in, an immutable report out.

Result precedence, most fundamental first, so the headline never overstates:

1. TARGET_SPECIFICATION_INCOMPLETE — success is not defined, so nothing else can be evaluated.
2. CONTROL_INDETERMINATE (fail-closed) — a relevant variable has no defining relationship, an
   unknown is too broad to enumerate, or no model variant is consistent with the evidence.
3. A strategy that reaches the target under every consistent variant, with every control's
   feasibility established: ROBUST_CONTROL_SOLUTION_CANDIDATE when more than one variant was in
   play, CONTROL_SOLUTION_CANDIDATE when only one — unless its target or safety cannot be observed,
   which gives OBSERVABILITY_INSUFFICIENT.
4. MODEL_DISAGREEMENT — named, evidence-compatible models disagree about a strategy.
5. CONTROL_INDETERMINATE — some strategy reaches the target somewhere, but not unconditionally;
   every blocker is named.
6. CURRENTLY_UNCONTROLLABLE — no strategy reaches the target safely under any consistent variant.

No agent can produce a result: only this function constructs one, and the report validates that
its contents support the class it carries.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from pydantic import Field, model_validator

from rarepipe.stages.control.actuator_registry import (
    ActuatorCandidate, ActuatorMapping, map_actuators,
)
from rarepipe.stages.control.controllability import StrategyAssessment, assess
from rarepipe.stages.control.controls import ControlVariable, Feasibility
from rarepipe.stages.control.dynamics import Model
from rarepipe.stages.control.experiment_design import DiscriminatingMeasurement, discriminate
from rarepipe.stages.control.model_registry import Admission, ModelRegistryEntry, admit
from rarepipe.stages.control.objective import rank
from rarepipe.stages.control.observability import ObservabilityGaps, ObservationModel, direct_gaps
from rarepipe.stages.control.provenance import Immutable, Provenance
from rarepipe.stages.control.reachability import compile_variant, run_strategy, search
from rarepipe.stages.control.result_types import MEANING, SOLUTION_CLASSES, ResultClass
from rarepipe.stages.control.safety_constraints import UnsafeRegion
from rarepipe.stages.control.state_space import State, StateSpace
from rarepipe.stages.control.target_constraints import TargetRegion
from rarepipe.stages.control.uncertainty import (
    StateEvidence, TooBroadToEnumerate, Variant, expand, initial_states,
)
from rarepipe.stages.prospective.store import content_digest

COMPILER_VERSION = "control-compiler-0.1.0"

SCIENTIFIC_OPTIONS_FOR_UNREACHABLE_BRANCHES = (
    "add the missing observables to the experiment",
    "narrow the branch's declared applicability so it no longer claims this experiment",
    "explicitly record the mechanism as unresolved for this experiment",
)


class ExperimentSpec(Immutable):
    """An existing experiment, compiled for what it contributes — never redesigned."""

    experiment_id: str
    controls_held: tuple[str, ...]
    observation: ObservationModel
    interpretation: str = Field(min_length=1)
    attribution_actuator: str | None = None
    unreachable_branches: tuple[str, ...] = Field(
        (), description="Decision branches that declare this experiment but cannot fire on it.")


class Problem(Immutable):
    problem_id: str
    case_ref: str
    space: StateSpace
    evidence: tuple[StateEvidence, ...]
    target: TargetRegion
    unsafe: UnsafeRegion
    models: tuple[Model, ...] = Field(min_length=1)
    controls: tuple[ControlVariable, ...]
    observation: ObservationModel
    experiments: tuple[ExperimentSpec, ...] = ()
    actuators: tuple[ActuatorCandidate, ...] = ()
    registry: tuple[ModelRegistryEntry, ...] = ()
    assumptions: tuple[Provenance, ...] = ()
    known_omissions: tuple[str, ...] = ()
    state_model_version: str
    rule_version: str
    case_context_version: str
    max_depth: int = Field(3, ge=1, le=6)

    @model_validator(mode="after")
    def _references_resolve(self):
        names = set(self.space.names)
        for c in self.controls:
            if c.sets not in names:
                raise ValueError(f"control {c.control_id} sets unknown variable {c.sets}")
            if c.to not in self.space.variable(c.sets).domain:
                raise ValueError(f"control {c.control_id}: {c.to!r} is not in {c.sets}'s domain")
        for c in self.target.constraints:
            if c.predicate and c.predicate.variable not in names:
                raise ValueError(f"target {c.constraint_id} refers to unknown {c.predicate.variable}")
        for c in self.unsafe.constraints:
            if c.unsafe_when.variable not in names:
                raise ValueError(f"safety {c.constraint_id} refers to unknown {c.unsafe_when.variable}")
        for m in self.models:
            m.check(self.space)
        return self


class ExcludedVariant(Immutable):
    variant_id: str
    reason: str


class ExperimentContribution(Immutable):
    experiment_id: str
    interpretation: str
    resolves: tuple[str, ...]
    conditional_on: str = Field(
        "", description="Set when the experiment implements its control through an actuator whose "
                        "feasibility is not established: what it resolves holds only if the "
                        "actuator actually achieves the control.")
    premise_observable: bool | None = Field(
        None, description="Whether the experiment measures the variable its control is meant to "
                          "move, so it can check its own premise.")
    observability: ObservabilityGaps
    attribution_missing: tuple[str, ...] = ()
    fails_closed: bool
    fail_closed_reason: str = ""
    options_for_the_scientific_lead: tuple[str, ...] = ()


class StrategyReport(Immutable):
    assessment: StrategyAssessment
    holds_under: tuple[str, ...] = Field(description="The variants under which it reaches the target.")


class ControlCompilationReport(Immutable):
    origin: str = "simulated_prediction"
    compiler_version: str
    state_model_version: str
    rule_version: str
    case_context_version: str
    problem_id: str
    case_ref: str

    result: ResultClass
    result_meaning: str
    secondary_results: tuple[ResultClass, ...] = ()
    target_accountability: str
    reachable_target: str

    initial_state: tuple[tuple[str, tuple[dict, ...]], ...]
    target_region: tuple[dict, ...]
    unsafe_region: tuple[dict, ...]
    candidate_models: tuple[str, ...]
    excluded_models: tuple[ExcludedVariant, ...]
    candidate_controls: tuple[dict, ...]
    control_strategy_candidates: tuple[StrategyReport, ...]
    unsafe_trajectories_rejected: tuple[dict, ...]
    model_disagreements: tuple[str, ...]
    unobservable_states: tuple[str, ...]
    blocking_relationships: tuple[str, ...]
    irrelevant_unknowns: tuple[str, ...]
    required_measurements: tuple[DiscriminatingMeasurement, ...]
    experiment_contributions: tuple[ExperimentContribution, ...]
    possible_actuator_classes: tuple[ActuatorMapping, ...]
    model_admissions: tuple[Admission, ...]
    assumptions: tuple[Provenance, ...]
    evidence_entitlement: tuple[dict, ...]
    known_omissions: tuple[str, ...]
    abstention_reason: str
    reproducibility: dict
    content_digest: str = ""

    @model_validator(mode="after")
    def _contents_support_the_result(self):
        clear = [s for s in self.control_strategy_candidates
                 if s.assessment.robust and not s.assessment.feasibility_blockers
                 and not s.assessment.unsafe_in]
        if self.result in SOLUTION_CLASSES and not clear:
            raise ValueError("a solution class requires a strategy that is robust, feasible and "
                             "safe under every consistent variant; prose cannot supply one")
        if self.result is ResultClass.CONTROL_INDETERMINATE and not self.blocking_relationships:
            raise ValueError("CONTROL_INDETERMINATE must name what blocks it")
        if self.result is ResultClass.MODEL_DISAGREEMENT and not self.model_disagreements:
            raise ValueError("MODEL_DISAGREEMENT must name the disagreement")
        if self.result is ResultClass.CURRENTLY_UNCONTROLLABLE and any(
                s.assessment.works_in for s in self.control_strategy_candidates):
            raise ValueError("a strategy reaches the target somewhere, so the system is not "
                             "uncontrollable under the current model")
        if self.origin != "simulated_prediction":
            raise ValueError("a compilation report is a simulated prediction, never an observation")
        return self

    def with_digest(self) -> "ControlCompilationReport":
        digest = content_digest(self, exclude={"content_digest", "reproducibility"})
        return ControlCompilationReport(**{**self.model_dump(), "content_digest": digest})


def _relevant_ancestors(problem: Problem, model: Model) -> set[str]:
    frontier = set(problem.target.variables()) | set(problem.unsafe.variables())
    seen = set(frontier)
    while frontier:
        name = frontier.pop()
        rel = model.defining(name)
        if rel is None:
            continue
        for parent in rel.inputs:
            if parent not in seen:
                seen.add(parent)
                frontier.add(parent)
    return seen


def _missing_relationships(problem: Problem) -> list[str]:
    missing = set()
    for model in problem.models:
        for name in sorted(_relevant_ancestors(problem, model)):
            var = problem.space.variable(name)
            if not var.exogenous and model.defining(name) is None:
                missing.add(f"missing_relationship:{name} (model {model.model_id})")
    return sorted(missing)


def _states(space: StateSpace, states: tuple[State, ...]) -> tuple[dict, ...]:
    return tuple(space.as_dict(s) for s in states)


def _repro() -> dict:
    root = Path(__file__).resolve().parents[4]
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001 — reproducibility metadata is best-effort
            return "unavailable"
    return {"code_revision": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
            "python": platform.python_version(),
            "digest_covers": "every field except content_digest and this block"}


def compile_problem(problem: Problem) -> ControlCompilationReport:
    space = problem.space
    target_ok = lambda s: problem.target.contains(space, s)  # noqa: E731
    unsafe_ok = lambda s: problem.unsafe.contains(space, s)  # noqa: E731
    controls = {c.control_id: c for c in problem.controls if c.feasibility is not Feasibility.INFEASIBLE}
    accountability = problem.target.accountability()
    gaps = direct_gaps(problem.target, problem.unsafe, problem.observation)
    unobservable = tuple(
        [f"target variable not measured by {gaps.observation_model}: {v}"
         for v in gaps.unobserved_target_variables]
        + [f"safety variable not measured by {gaps.observation_model}: {v} — safety cannot be "
           "certified by a model's prediction that it will not move"
           for v in gaps.unobserved_safety_variables])

    base = dict(
        compiler_version=COMPILER_VERSION, state_model_version=problem.state_model_version,
        rule_version=problem.rule_version, case_context_version=problem.case_context_version,
        problem_id=problem.problem_id, case_ref=problem.case_ref,
        target_accountability=accountability,
        target_region=tuple({"constraint": c.constraint_id, "meaning": c.meaning,
                             "requires": (dict(c.predicate) if c.predicate else None),
                             "approval": c.approval.status.value}
                            for c in problem.target.constraints),
        unsafe_region=tuple({"constraint": c.constraint_id, "meaning": c.meaning,
                             "unsafe_when": dict(c.unsafe_when),
                             "approval": c.approval.status.value}
                            for c in problem.unsafe.constraints),
        candidate_controls=tuple({"control": c.control_id, "holds": f"{c.sets}={c.to}",
                                  "kind": c.kind.value, "route_class": c.route_class.value,
                                  "interpretation": c.interpretation,
                                  "feasibility": c.feasibility.value,
                                  "epistemic_type": c.provenance.epistemic_type.value}
                                 for c in problem.controls),
        assumptions=problem.assumptions, known_omissions=problem.known_omissions,
        unobservable_states=unobservable,
        evidence_entitlement=tuple(
            {"relationship": r.relationship_id, "model": m.model_id, "output": r.output,
             "epistemic_status": r.epistemic_status,
             "epistemic_type": r.provenance.epistemic_type.value,
             "support": list(r.support), "contradictions": list(r.contradictions),
             "validity_domain": r.validity_domain}
            for m in problem.models for r in sorted(m.relationships, key=lambda r: r.relationship_id)),
        reproducibility=_repro(),
    )
    empty = dict(initial_state=(), candidate_models=(), excluded_models=(),
                 control_strategy_candidates=(), unsafe_trajectories_rejected=(),
                 model_disagreements=(), irrelevant_unknowns=(), required_measurements=(),
                 experiment_contributions=(), possible_actuator_classes=(), model_admissions=())

    def finish(result: ResultClass, *, secondary=(), reachable="indeterminate", blocking=(),
               abstention="", **fields) -> ControlCompilationReport:
        merged = {**empty, **fields}
        return ControlCompilationReport(
            **base, **merged, result=result, result_meaning=MEANING[result],
            secondary_results=tuple(sorted(set(secondary) - {result}, key=lambda r: r.value)),
            reachable_target=reachable, blocking_relationships=tuple(blocking),
            abstention_reason=abstention).with_digest()

    # 1. Success must be defined.
    unspecified = problem.target.unspecified()
    if unspecified:
        return finish(ResultClass.TARGET_SPECIFICATION_INCOMPLETE,
                      blocking=tuple(f"target_unspecified:{c.constraint_id}" for c in unspecified),
                      abstention="success is not defined: " + "; ".join(
                          f"{c.constraint_id} ({c.approval.note})" for c in unspecified))

    # 2. Fail closed on missing relationships rather than treating a variable as constant.
    missing = _missing_relationships(problem)
    if missing:
        return finish(ResultClass.CONTROL_INDETERMINATE, blocking=tuple(missing),
                      abstention="a variable the target or safety depends on has no defining "
                                 "relationship; treating it as constant would fill an unknown")

    variants: list[Variant] = []
    try:
        for model in problem.models:
            variants.extend(expand(space, model))
    except TooBroadToEnumerate as exc:
        return finish(ResultClass.CONTROL_INDETERMINATE, blocking=(f"too_broad:{exc}",),
                      abstention=str(exc))

    x0: dict[str, tuple[State, ...]] = {}
    consistent: list[Variant] = []
    excluded: list[ExcludedVariant] = []
    for v in variants:
        states = initial_states(space, v, problem.evidence)
        if states:
            consistent.append(v)
            x0[v.variant_id] = states
        else:
            excluded.append(ExcludedVariant(
                variant_id=v.variant_id,
                reason="no state is both consistent with the recorded evidence and at steady "
                       "state under this variant, so the evidence falsifies it"))
    if not consistent:
        return finish(ResultClass.CONTROL_INDETERMINATE,
                      blocking=("no_model_variant_consistent_with_evidence",),
                      excluded_models=tuple(excluded),
                      abstention="every model variant is contradicted by the evidence; the model "
                                 "set cannot explain this case, so nothing about control follows")

    compiled = {v.variant_id: compile_variant(space, v) for v in consistent}

    # 3. Search per variant, then judge every candidate strategy on every variant.
    candidates: set = set()
    rejected: dict = {}
    for v in consistent:
        found = search(compiled[v.variant_id], x0[v.variant_id], controls, target_ok, unsafe_ok,
                       problem.max_depth)
        candidates.update(found.successes)
        for strategy, outcome in found.rejected:
            rejected.setdefault(strategy, []).append((v.variant_id, outcome))

    def unsafe_ids(outcome):
        if outcome.status != "UNSAFE" or not outcome.unsafe_path:
            return ()
        return problem.unsafe.violated_by(space, outcome.unsafe_path[-1])

    assessments: list[StrategyAssessment] = []
    for strategy in sorted(candidates):
        outcomes = {v.variant_id: run_strategy(compiled[v.variant_id], x0[v.variant_id], strategy,
                                               controls, target_ok, unsafe_ok)
                    for v in consistent}
        assessments.append(assess(strategy, consistent, outcomes, controls, unsafe_ids))
    ranked = rank(assessments)

    rejected_rows = []
    for strategy in sorted(rejected):
        if strategy in candidates:
            continue
        for vid, outcome in sorted(rejected[strategy], key=lambda t: t[0]):
            rejected_rows.append({
                "strategy": [list(step) for step in strategy], "variant": vid,
                "violates": list(unsafe_ids(outcome)),
                "path": [space.as_dict(s) for s in outcome.unsafe_path]})

    # 4. Experiments: what each one resolves, whether it can be verified, and where it fails closed.
    control_sets = sorted({tuple(sorted({c for step in a.strategy for c in step})) for a in ranked})
    measurements: list[DiscriminatingMeasurement] = []
    disagreements: list[str] = []
    for a in ranked:
        if not a.works_in or a.robust:
            continue
        works = list(a.works_in)
        fails = [o.variant_id for o in a.outcomes if o.status != "SUCCESS"]
        for rid in a.blocking_relationships:
            measurements.extend(discriminate(rid, works, fails, compiled, x0, controls,
                                             control_sets, unsafe_ok,
                                             tuple(e.observation for e in problem.experiments)
                                             or (problem.observation,)))
        if a.model_disagreement:
            disagreements.append(
                f"strategy {[list(s) for s in a.strategy]}: " +
                ", ".join(f"{m}={verdict}" for m, verdict in a.per_model))
            measurements.extend(discriminate("model_disagreement", works, fails, compiled, x0,
                                             controls, control_sets, unsafe_ok,
                                             tuple(e.observation for e in problem.experiments)
                                             or (problem.observation,)))
    measurements = sorted({m.model_dump_json(): m for m in measurements}.values(),
                          key=lambda m: (m.resolves, m.controls_held, m.variable))

    actuator_by_id = {a.actuator_id: a for a in problem.actuators}
    contributions = []
    for exp in problem.experiments:
        exp_gaps = direct_gaps(problem.target, problem.unsafe, exp.observation)
        # A confounded reading counts only if the experiment also measures what could fake it.
        resolves = sorted({m.resolves for m in measurements
                           if m.controls_held == tuple(sorted(exp.controls_held))
                           and m.variable in exp.observation.observed
                           and all(c in exp.observation.observed for c in m.confounded_by)})
        attribution = ()
        if exp.attribution_actuator:
            needed = actuator_by_id[exp.attribution_actuator].attribution_observables
            attribution = tuple(v for v in needed if v not in exp.observation.observed)
        reasons = []
        if exp.unreachable_branches:
            reasons.append(f"branches {list(exp.unreachable_branches)} declare this experiment but "
                           "cannot fire on it")
        if attribution:
            reasons.append(f"attributing an effect to {exp.attribution_actuator} needs "
                           f"{list(attribution)}, which this experiment does not measure")
        conditional, premise = "", None
        if exp.attribution_actuator:
            actuator = actuator_by_id[exp.attribution_actuator]
            if actuator.feasibility is not Feasibility.ESTABLISHED:
                held = controls[actuator.implements_control]
                premise = held.sets in exp.observation.observed
                conditional = (f"{exp.attribution_actuator} achieving {held.control_id} "
                               f"({held.sets}={held.to}), which is not established. "
                               + ("The experiment measures that variable, so it can check its own "
                                  "premise." if premise else
                                  "The experiment does not measure that variable, so it cannot "
                                  "tell a failed actuator from a resolved relationship."))
        contributions.append(ExperimentContribution(
            experiment_id=exp.experiment_id, interpretation=exp.interpretation,
            resolves=tuple(resolves), conditional_on=conditional, premise_observable=premise,
            observability=exp_gaps, attribution_missing=attribution,
            fails_closed=bool(reasons), fail_closed_reason="; ".join(reasons),
            options_for_the_scientific_lead=SCIENTIFIC_OPTIONS_FOR_UNREACHABLE_BRANCHES if reasons else ()))

    working_controls = tuple(sorted({c for a in ranked if a.works_in for c in a.controls}))
    mappings = map_actuators(working_controls, problem.actuators) if working_controls else ()
    unresolved_outputs = tuple(sorted({fn.output for v in consistent for fn in v.functions
                                       if fn.candidate_label is not None}))
    admissions = tuple(admit(e, unresolved_outputs) for e in problem.registry)

    reports = tuple(StrategyReport(assessment=a, holds_under=a.works_in) for a in ranked)
    shared = dict(
        initial_state=tuple((v.variant_id, _states(space, x0[v.variant_id])) for v in consistent),
        candidate_models=tuple(v.variant_id for v in consistent),
        excluded_models=tuple(excluded), control_strategy_candidates=reports,
        unsafe_trajectories_rejected=tuple(rejected_rows),
        model_disagreements=tuple(disagreements),
        irrelevant_unknowns=tuple(sorted({u for a in ranked for u in a.irrelevant_unknowns}
                                         - {b for a in ranked for b in a.blocking_relationships})),
        required_measurements=tuple(measurements), experiment_contributions=tuple(contributions),
        possible_actuator_classes=mappings, model_admissions=admissions)

    secondary = []
    if not gaps.sufficient:
        secondary.append(ResultClass.OBSERVABILITY_INSUFFICIENT)
    if any(c.fails_closed for c in contributions):
        secondary.append(ResultClass.OBSERVABILITY_INSUFFICIENT)
    if accountability != "APPROVED":
        secondary.append(ResultClass.TARGET_SPECIFICATION_INCOMPLETE)

    clear = [a for a in ranked if a.robust and not a.feasibility_blockers and not a.unsafe_in]
    if clear:
        if not gaps.sufficient:
            return finish(ResultClass.OBSERVABILITY_INSUFFICIENT, secondary=secondary,
                          reachable="yes", blocking=unobservable, **shared,
                          abstention="a route exists, but its target or safety is not measured")
        result = (ResultClass.ROBUST_CONTROL_SOLUTION_CANDIDATE if len(consistent) > 1
                  else ResultClass.CONTROL_SOLUTION_CANDIDATE)
        return finish(result, secondary=secondary, reachable="yes", **shared,
                      abstention=("" if accountability == "APPROVED" else
                                  "conditional on a target that no accountable scientist has "
                                  "approved"))

    if disagreements:
        return finish(ResultClass.MODEL_DISAGREEMENT, secondary=secondary, reachable="indeterminate",
                      blocking=tuple(sorted({b for a in ranked for b in a.blocking_relationships})),
                      **shared, abstention="evidence-compatible models disagree about every route")

    somewhere = [a for a in ranked if a.works_in]
    if somewhere:
        blockers = sorted({b for a in somewhere for b in (*a.blocking_relationships,
                                                           *a.feasibility_blockers)})
        return finish(ResultClass.CONTROL_INDETERMINATE, secondary=secondary,
                      reachable="indeterminate", blocking=tuple(blockers), **shared,
                      abstention="every route that reaches the target depends on something not yet "
                                 "known; the blockers are named")

    return finish(ResultClass.CURRENTLY_UNCONTROLLABLE, secondary=secondary, reachable="no",
                  **shared, abstention="no strategy reaches the target safely under any "
                                       "evidence-consistent variant of the current model with the "
                                       "current controls")
