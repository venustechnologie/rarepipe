"""The physical-realization compiler: an abstract transformation in, a chain of real pieces out —
or an exact account of why there isn't one.

    required function  ->  mechanistic realization  ->  physical primitives

Three outcomes are equally valid, and the compiler is not pushed towards the first. Finding real
components that implement the whole architecture would be remarkable. Finding that two of three
functions are grounded and naming the third reduces the open problem to one sentence. Finding that
nothing survives the audit is also knowledge, provided the compiler says exactly what was missing.

Two things are computed rather than carried over on trust:

* **logical sufficiency** — whether the target architecture reaches the state target at all is
  re-derived by compiling the synthesis problem, not copied from a previous report;
* **epistemic burden** — read from the epistemic status of the relationship the architecture
  bypasses. Replacing something the model records as established demands evidence that stands on
  its own, and no proposer gets to set that bar for itself.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from pydantic import Field, model_validator

from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.checks import (
    STATUS_ORDER, RealizationAssessment, assess,
)
from rarepipe.stages.control.realization.evidence import EvidenceInventory
from rarepipe.stages.control.realization.kinds import (
    BURDEN_OF_STATUS, REALIZATION_MEANING, EpistemicBurden, RealizationResult,
)
from rarepipe.stages.control.realization.mechanisms import MechanisticRealization, Step
from rarepipe.stages.control.realization.primitives import PhysicalPrimitiveRegistry
from rarepipe.stages.control.synthesis.compiler import SynthesisProblem, compile_synthesis
from rarepipe.stages.control.synthesis.kinds import LogicalStatus
from rarepipe.stages.prospective.store import content_digest

REALIZATION_COMPILER_VERSION = "realization-compiler-0.1.0"

NO_RECOMMENDATION = (
    "This report contains no treatment recommendation and no clinical advice. It states which "
    "physical components could, on evidence this repository already holds, produce a required "
    "biological transformation — and where that evidence runs out. A grounded chain here is a "
    "candidate for a scientist to argue with, not a therapy."
)


class RealizationProblem(Immutable):
    problem_id: str = Field(min_length=1)
    case_ref: str = Field(min_length=1)
    synthesis: SynthesisProblem
    target_architecture: str = Field(
        min_length=1, description="The architecture whose transformations are to be realized.")
    registry: PhysicalPrimitiveRegistry
    inventory: EvidenceInventory
    realizations: tuple[MechanisticRealization, ...] = ()
    required_system: str = Field(
        min_length=1, description="The system the case needs this to work in. Transfer gaps are "
                                  "measured against this and never silently excused.")
    realization_model_version: str = Field(min_length=1)
    max_depth: int = Field(3, ge=1, le=5)

    @model_validator(mode="after")
    def _references_resolve(self):
        # Gate 10: an invented component or an invented citation is refused here, before anything
        # is reasoned about. A checker that runs later would already be reasoning about a ghost.
        self.registry.check(self.inventory)
        self.synthesis.registry.get(self.target_architecture)
        for realization in self.realizations:
            for step in realization.steps:
                self.registry.get(step.uses_primitive).capability(step.capability_id)
        return self


class FunctionOutcome(Immutable):
    function: str
    variable: str
    value: str
    burden: EpistemicBurden
    burden_from: str = Field(description="The relationship this bypasses, and how well established.")
    status: RealizationResult
    realizations: tuple[RealizationAssessment, ...] = ()
    children: tuple["FunctionOutcome", ...] = ()
    missing_capability: str = ""
    reason: str


class RealizationReport(Immutable):
    origin: str = "simulated_prediction"
    realization_compiler_version: str
    synthesis_compiler_version: str
    realization_model_version: str
    state_model_version: str
    case_context_version: str
    problem_id: str
    case_ref: str
    target_architecture: str
    required_system: str

    result: RealizationResult
    result_meaning: str
    logically_sufficient: bool = Field(
        description="Whether the architecture reaches the state target at all. Re-derived by "
                    "compiling the synthesis problem, never carried over on trust.")
    logical_status: str
    functions: tuple[FunctionOutcome, ...]
    missing_capabilities: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    safety_dependencies: tuple[str, ...] = ()
    transfer_gaps: tuple[str, ...] = ()
    evidence_edges_used: tuple[str, ...] = ()
    evidence_inventory_size: int = 0
    primitives_declared: tuple[dict, ...] = ()
    no_treatment_recommendation: str = NO_RECOMMENDATION
    abstention_reason: str = ""
    reproducibility: dict
    content_digest: str = ""

    @model_validator(mode="after")
    def _contents_support_the_result(self):
        if self.origin != "simulated_prediction":
            raise ValueError("a realization report is a simulated prediction, never an observation")
        if self.no_treatment_recommendation != NO_RECOMMENDATION:
            raise ValueError("the no-recommendation statement is fixed and may not be reworded")
        grounded = [f for f in self.functions
                    if f.status is RealizationResult.GROUNDED_REALIZATION_CANDIDATE]
        if self.result is RealizationResult.GROUNDED_REALIZATION_CANDIDATE and (
                not self.functions or len(grounded) != len(self.functions)):
            raise ValueError(
                "GROUNDED_REALIZATION_CANDIDATE requires every required transformation to be "
                "grounded; prose cannot supply the missing one")
        if self.result is RealizationResult.PARTIAL_REALIZATION and not self.missing_capabilities:
            raise ValueError("PARTIAL_REALIZATION must name exactly what is missing")
        if (self.result is RealizationResult.NO_GROUNDED_REALIZATION
                and not self.abstention_reason):
            raise ValueError("NO_GROUNDED_REALIZATION must say what was looked for and not found")
        return self

    def with_digest(self) -> "RealizationReport":
        return RealizationReport(**{**self.model_dump(),
                                    "content_digest": content_digest(
                                        self, exclude={"content_digest", "reproducibility"})})


def _repro() -> dict:
    root = Path(__file__).resolve().parents[5]

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001 — reproducibility metadata is best-effort
            return "unavailable"
    return {"code_revision": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "python": platform.python_version(),
            "digest_covers": "every field except content_digest and this block"}


def _burden_for(problem: RealizationProblem, variable: str) -> tuple[EpistemicBurden, str]:
    """Read the burden from the relationship being replaced, not from the proposer."""
    control = problem.synthesis.problem
    for model in control.models:
        relationship = model.defining(variable)
        if relationship is not None:
            return (BURDEN_OF_STATUS[relationship.epistemic_status],
                    f"{relationship.relationship_id} is recorded as "
                    f"{relationship.epistemic_status}; replacing it carries that burden")
    return (EpistemicBurden.BYPASSES_UNRESOLVED_RELATIONSHIP,
            f"no relationship in the model defines {variable}, so nothing better established is "
            "being replaced")


def _synthesised(problem: RealizationProblem, variable: str, value: str
                 ) -> tuple[MechanisticRealization, ...]:
    """One-step realizations from registry primitives that act on this variable directly.

    Only used where no realization was declared for the transformation. That is the case a newly
    grounded capability is supposed to change: a piece that lands on a function nobody had a
    mechanism for should turn the verdict without anyone hand-writing a chain for it. Where a
    realization *was* declared, the declared one stands, so this never quietly adds noise beside it.
    """
    out: list[MechanisticRealization] = []
    for primitive_id, capability in problem.registry.affecting(variable):
        if capability.to is not None and capability.to != value:
            continue
        out.append(MechanisticRealization(
            realization_id=f"MR_AUTO::{primitive_id}::{capability.capability_id}",
            required_transformation=f"{variable}->{value}", target_variable=variable,
            target_value=value, required_effect=capability.effect,
            mechanism=(f"{capability.claim}, composed directly from the registered capability "
                       f"{capability.capability_id} because no realization was declared for this "
                       "transformation"),
            steps=(Step(step_id="S1", uses_primitive=primitive_id,
                        capability_id=capability.capability_id,
                        rationale="the registry declares this capability acts on the required "
                                  "variable, so the compiler composes it rather than reporting no "
                                  "mechanism at all"),),
            agent=capability.agent, context_system=problem.required_system,
            provenance=Provenance(
                epistemic_type=EpistemicType.BUILDING_BLOCK_CAPABILITY,
                source=f"composed by the realization compiler from {primitive_id}",
                proposed_by="rarepipe realization compiler (deterministic composition)",
                rationale="no realization was declared for this transformation, and the registry "
                          "holds a capability that acts on it")))
    return tuple(sorted(out, key=lambda r: r.realization_id))


def _missing_capability(problem: RealizationProblem, variable: str) -> str:
    attributed = sorted({e.source for e in problem.inventory.edges_into(variable)})
    declared = sorted({pid for pid, _ in problem.registry.affecting(variable)})
    return (f"a physical primitive with a capability that affects {variable} without acting through "
            f"{attributed or ['nothing recorded']}. The inventory attributes {variable} only to "
            f"{attributed or 'no claim at all'}, and the registry declares "
            f"{declared or 'no primitive'} affecting it.")


def _compile_function(problem: RealizationProblem, variable: str, value: str, depth: int,
                      seen: frozenset[str], observed: tuple[str, ...]) -> FunctionOutcome:
    control = problem.synthesis.problem
    function = f"{variable}->{value}"
    burden, burden_from = _burden_for(problem, variable)
    mine = tuple(sorted((r for r in problem.realizations
                         if r.target_variable == variable and r.target_value == value),
                        key=lambda r: r.realization_id))
    if not mine:
        mine = _synthesised(problem, variable, value)
    if not mine:
        return FunctionOutcome(
            function=function, variable=variable, value=value, burden=burden,
            burden_from=burden_from, status=RealizationResult.NO_GROUNDED_REALIZATION,
            missing_capability=_missing_capability(problem, variable),
            reason=("no mechanistic realization was proposed for this transformation, and the "
                    "registry declares no primitive that could supply one"))
    assessments = tuple(assess(r, problem.registry, problem.inventory, burden, control.unsafe,
                               control.space, observed) for r in mine)
    children: list[FunctionOutcome] = []
    if depth < problem.max_depth:
        for realization in mine:
            for child in realization.decomposes_into:
                if child in seen or "->" not in child:
                    continue
                child_variable, child_value = child.split("->", 1)
                children.append(_compile_function(problem, child_variable, child_value, depth + 1,
                                                  seen | {child}, observed))
    best = min(assessments, key=lambda a: STATUS_ORDER[a.status])
    status, reason = best.status, best.reason
    # A transformation that only decomposes takes its status from what it decomposes into.
    if children and status is RealizationResult.PARTIAL_REALIZATION:
        worst = max(children, key=lambda c: STATUS_ORDER[c.status])
        if STATUS_ORDER[worst.status] > STATUS_ORDER[status]:
            status = worst.status
            reason = (f"{best.reason}; the sub-transformation {worst.function} is {worst.status.value}")
    missing = "" if status is RealizationResult.GROUNDED_REALIZATION_CANDIDATE else (
        _missing_capability(problem, variable) if status is RealizationResult.NO_GROUNDED_REALIZATION
        else "; ".join([*best.missing_links, *best.unknown_steps]) or best.reason)
    return FunctionOutcome(function=function, variable=variable, value=value, burden=burden,
                           burden_from=burden_from, status=status, realizations=assessments,
                           children=tuple(children), missing_capability=missing, reason=reason)


def compile_realization(problem: RealizationProblem) -> RealizationReport:
    control = problem.synthesis.problem
    synthesis_report = compile_synthesis(problem.synthesis)
    architecture = next(
        (a for a in (*synthesis_report.architectures, *synthesis_report.proposed_architectures)
         if problem.target_architecture in a.components), None)
    logical = architecture.logical if architecture else LogicalStatus.NOT_REPRESENTABLE
    sufficient = logical is LogicalStatus.TARGET_REACHABLE

    block = problem.synthesis.registry.get(problem.target_architecture)
    wanted = tuple(sorted(((t.variable, t.to) for t in block.state_transformations if t.intended),
                          key=lambda pair: pair[0]))
    observed = control.observation.observed + tuple(
        o for e in control.experiments for o in e.observation.observed)

    functions = tuple(_compile_function(problem, variable, value, 0, frozenset({f"{variable}->{value}"}),
                                        observed)
                      for variable, value in wanted)

    statuses = [f.status for f in functions]
    grounded = [f for f in functions
                if f.status is RealizationResult.GROUNDED_REALIZATION_CANDIDATE]
    if RealizationResult.UNSAFE_REALIZATION in statuses:
        result = RealizationResult.UNSAFE_REALIZATION
        abstention = "a required transformation is produced only by a route that enters a forbidden state"
    elif functions and len(grounded) == len(functions):
        result = RealizationResult.GROUNDED_REALIZATION_CANDIDATE
        abstention = ""
    elif grounded:
        result = RealizationResult.PARTIAL_REALIZATION
        abstention = (f"{len(grounded)} of {len(functions)} required transformations are grounded; "
                      "the rest are named with exactly what is missing")
    elif statuses and all(s is RealizationResult.CONTEXT_MISMATCH for s in statuses):
        result = RealizationResult.CONTEXT_MISMATCH
        abstention = ("each required transformation has a mechanism whose evidence was obtained "
                      f"outside {problem.required_system}")
    elif statuses and all(s is RealizationResult.NO_GROUNDED_REALIZATION for s in statuses):
        result = RealizationResult.NO_GROUNDED_REALIZATION
        abstention = ("no evidence-backed way to implement any required transformation was found. "
                      "What was looked for is named per function; this is a statement about this "
                      "registry and this inventory, not about biology")
    else:
        result = max(statuses, key=lambda s: STATUS_ORDER[s]) if statuses else \
            RealizationResult.NOT_REPRESENTABLE
        abstention = ("the required transformations do not reach a single verdict; each is reported "
                      "with its own")
        if result is RealizationResult.NO_GROUNDED_REALIZATION:
            abstention = ("at least one required transformation has no evidence-backed "
                          "implementation, and nothing else is grounded either")

    conflicts = tuple(sorted({f.detail for fn in functions for a in fn.realizations
                              for f in a.findings
                              if f.kind in {"compatibility", "dependency", "direction"}}))
    safety = tuple(sorted({d for fn in functions for a in fn.realizations
                           for r in problem.realizations if r.realization_id == a.realization_id
                           for d in r.safety_dependencies}
                          | {f.detail for fn in functions for a in fn.realizations
                             for f in a.findings if f.kind == "safety"}))
    gaps = tuple(sorted({g for fn in functions for a in fn.realizations for g in a.transfer_gaps}))
    used = tuple(sorted({e for fn in functions for a in fn.realizations for s in a.steps
                         for e in (x.edge_id for x in s.entitlings)}))
    missing = tuple(sorted({f.missing_capability for f in functions if f.missing_capability}))

    return RealizationReport(
        realization_compiler_version=REALIZATION_COMPILER_VERSION,
        synthesis_compiler_version=synthesis_report.synthesis_compiler_version,
        realization_model_version=problem.realization_model_version,
        state_model_version=control.state_model_version,
        case_context_version=control.case_context_version,
        problem_id=problem.problem_id, case_ref=problem.case_ref,
        target_architecture=problem.target_architecture, required_system=problem.required_system,
        result=result, result_meaning=REALIZATION_MEANING[result],
        logically_sufficient=sufficient, logical_status=logical.value, functions=functions,
        missing_capabilities=missing, conflicts=conflicts, safety_dependencies=safety,
        transfer_gaps=gaps, evidence_edges_used=used,
        evidence_inventory_size=len(problem.inventory.edges),
        primitives_declared=tuple({
            "primitive": p.primitive_id, "class": p.primitive_class.value, "identity": p.identity,
            "capabilities": [f"{c.capability_id}: {c.effect.value} {c.affects}"
                             + (f" (acting on {c.acts_on})" if c.acts_on else " (applied directly)")
                             for c in p.capabilities],
            "cell_type": p.cell_type, "feasibility": p.feasibility_status,
            "evidence": p.evidence, "uncertainty": p.uncertainty,
            "epistemic_type": p.provenance.epistemic_type.value,
        } for p in sorted(problem.registry.primitives, key=lambda p: p.primitive_id)),
        abstention_reason=abstention, reproducibility=_repro()).with_digest()
