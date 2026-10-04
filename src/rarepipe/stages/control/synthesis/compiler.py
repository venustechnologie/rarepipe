"""The synthesis compiler: a desired state in, an immutable architecture report out.

Pipeline, in the order the PRD specifies it, with the fail-closed points marked:

  1-3. the current state, the target region and the unsafe regions, taken from the control problem
   4.  decompose the target into the functions that must become true, and the entry points a
       transformation would have to act on                                  (requirements)
   5.  the controls already known, as one family among several
   6-8. architectures proposed by agents, already typed and gated: a proposal is a
       PROPOSED_ARCHITECTURE and nothing else                               (proposals)
   9.  compose candidates deterministically                                 (search)
  10-11. reachability and unsafe-region intersection, through the existing engine
  12-13. observability and confounders                                      (population)
  14-15. every evidence-compatible model, then robustness                   (robustness)
  16.  logical synthesizability                                             (synthesizability)
  17-18. components and their physical feasibility, kept separate           (building_blocks)
  19.  relationships that are missing rather than unknown  -> fail closed
  20.  the experiment that would resolve the blockers                       (experiments)
  21.  this report, digested

Result precedence puts the most fundamental limitation first, so the headline never overstates:
an undefined target outranks everything, missing biology outranks any search result, and a
composition that works only because feasibility was never assessed is reported as exactly that.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from rarepipe.stages.control.compiler import Problem, _missing_relationships, _repro
from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.observability import direct_gaps
from rarepipe.stages.control.provenance import Immutable, Provenance
from rarepipe.stages.control.reachability import compile_variant
from rarepipe.stages.control.synthesis import SYNTHESIS_PRINCIPLE
from rarepipe.stages.control.synthesis.architecture import (
    ArchitectureAssessment, ControlArchitecture,
)
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlockRegistry
from rarepipe.stages.control.synthesis.experiments import (
    CRITERION, ArchitectureDiscriminator, compile_experiments,
)
from rarepipe.stages.control.synthesis.feedback import FeedbackPolicy
from rarepipe.stages.control.synthesis.kinds import (
    SYNTHESIS_MEANING, ArchitectureOrigin, FamilyVerdict, LogicalStatus, PhysicalStatus,
    RobustnessClass, SynthesisResultClass, TransformationScale,
)
from rarepipe.stages.control.synthesis.population import ConfounderGap, PopulationLayer
from rarepipe.stages.control.synthesis.requirements import Decomposition, decompose
from rarepipe.stages.control.synthesis.search import (
    SynthesisSearch, TooBroadToSynthesize, VariantContext, assess_composition, synthesize,
)
from rarepipe.stages.control.uncertainty import TooBroadToEnumerate, expand, initial_states
from rarepipe.stages.prospective.store import content_digest

SYNTHESIS_COMPILER_VERSION = "synthesis-compiler-0.1.0"

NO_RECOMMENDATION = (
    "This report contains no treatment recommendation and no clinical advice. It states which "
    "biological transformations would, under the stated models, move the system into the target "
    "region, and which of them nothing is known to implement. Deciding whether any of it is worth "
    "testing is a judgement for a scientific lead and a treating clinician."
)

LOGICAL_VS_PHYSICAL = (
    "LOGICALLY_SYNTHESIZABLE means a composition of the declared transformations reaches the target "
    "in the mathematics. PHYSICALLY_FEASIBLE means there is evidence those transformations can be "
    "produced in the relevant cells. The second does not follow from the first, and this report "
    "computes it only from the components' own feasibility fields."
)

# Narrow on purpose: each phrase is an act of advising, not a word that merely appears near one.
# "dose-dependent", "recommended by the authors" and "indicated in the model" are legitimate
# scientific language and must not trip this.
_ADVISORY_PHRASES = (
    "we recommend", "i recommend", "it is recommended that", "recommended treatment",
    "recommended therapy", "recommended dose", "should be given", "should be administered",
    "should be prescribed", "should be treated with", "the patient should", "the child should",
    "start treatment", "begin treatment", "mg/kg", "mg per kg", "twice daily", "once daily",
)


class FamilySpec(Immutable):
    """A family of architectures the compiler was asked to consider, whether or not any exists."""

    family_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    members: tuple[str, ...] = Field((), description="Building blocks that belong to this family.")
    requires_variables: tuple[str, ...] = ()
    requires_scale: TransformationScale | None = None
    requires_feedback: bool = Field(
        False, description="True for a family defined by closing the loop rather than by which "
                           "components it uses.")
    rationale: str = Field(min_length=1)


class FamilyOutcome(Immutable):
    family_id: str
    description: str
    verdict: FamilyVerdict
    architectures: tuple[str, ...]
    reason: str


class SynthesisProblem(Immutable):
    problem: Problem
    registry: BuildingBlockRegistry
    population: PopulationLayer = PopulationLayer()
    policies: tuple[FeedbackPolicy, ...] = ()
    proposed: tuple[ControlArchitecture, ...] = ()
    families: tuple[FamilySpec, ...] = ()
    synthesis_model_version: str = Field(min_length=1)
    max_depth: int = Field(2, ge=1, le=4)
    max_per_step: int = Field(2, ge=1, le=4)

    @model_validator(mode="after")
    def _references_resolve(self):
        self.registry.check(self.problem.space)
        self.population.check(self.problem.space)
        known = {b.building_block_id for b in self.registry.blocks}
        for architecture in self.proposed:
            missing = [b for b in architecture.components if b not in known]
            if missing:
                raise ValueError(f"{architecture.architecture_id} names unregistered components "
                                 f"{missing}; a component with no declared capability cannot be "
                                 "composed")
        for family in self.families:
            for name in family.requires_variables:
                self.problem.space.index(name)
        return self


class SynthesisReport(Immutable):
    origin: str = "simulated_prediction"
    principle: str = SYNTHESIS_PRINCIPLE
    synthesis_compiler_version: str
    control_compiler_version: str
    synthesis_model_version: str
    state_model_version: str
    rule_version: str
    case_context_version: str
    problem_id: str
    case_ref: str

    result: SynthesisResultClass
    result_meaning: str
    secondary_results: tuple[SynthesisResultClass, ...] = ()

    required_functions: Decomposition
    entry_points: tuple[str, ...]
    building_blocks: tuple[dict, ...]
    architectures: tuple[ArchitectureAssessment, ...]
    proposed_architectures: tuple[ArchitectureAssessment, ...] = ()
    families: tuple[FamilyOutcome, ...] = ()
    confounder_gaps: tuple[ConfounderGap, ...] = ()
    experiment_discriminators: tuple[ArchitectureDiscriminator, ...] = ()
    experiment_criterion: str = CRITERION
    experiment_criterion_note: str

    blocking_relationships: tuple[str, ...] = ()
    missing_relationships: tuple[str, ...] = ()
    unobservable_states: tuple[str, ...] = ()
    irrelevant_unknowns: tuple[str, ...] = ()
    excluded_variants: tuple[str, ...] = ()
    candidate_variants: tuple[str, ...] = ()

    compositions_examined: int = 0
    search_note: str = ""
    logical_vs_physical: str = LOGICAL_VS_PHYSICAL
    rescue_scope_statement: str
    no_treatment_recommendation: str = NO_RECOMMENDATION
    target_accountability: str
    assumptions: tuple[Provenance, ...] = ()
    known_omissions: tuple[str, ...] = ()
    abstention_reason: str = ""
    reproducibility: dict
    content_digest: str = ""

    @model_validator(mode="after")
    def _contents_support_the_result(self):
        if self.origin != "simulated_prediction":
            raise ValueError("a synthesis report is a simulated prediction, never an observation")
        if self.no_treatment_recommendation != NO_RECOMMENDATION:
            raise ValueError("the no-recommendation statement is fixed and may not be reworded")
        clear = [a for a in self.architectures if a.clear]
        if self.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED and not clear:
            raise ValueError(
                "ARCHITECTURE_SYNTHESIZED requires an architecture that is robust across every "
                "consistent variant, safe, observable and built from components whose "
                "implementation is established; prose cannot supply one")
        if self.result is SynthesisResultClass.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN:
            if not any(a.logically_synthesizable and not a.physically_feasible
                       for a in self.architectures):
                raise ValueError("SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN requires a composition that "
                                 "reaches the target and names what cannot yet be built")
        if (self.result is SynthesisResultClass.ARCHITECTURE_INDETERMINATE
                and not (self.blocking_relationships or self.missing_relationships)):
            raise ValueError("ARCHITECTURE_INDETERMINATE must name what blocks it")
        if (self.result is SynthesisResultClass.NO_ARCHITECTURE_SYNTHESIZED
                and any(a.works_in for a in self.architectures)):
            raise ValueError("a composition reaches the target, so something was synthesized")
        haystack = " ".join([
            self.abstention_reason, self.rescue_scope_statement, self.search_note,
            *(" ".join([a.rescue_scope, a.stability_note, a.order_note, a.feedback_status,
                        *a.notes, *a.assumptions]) for a in self.architectures),
            *(f.reason for f in self.families),
            *(d.note for d in self.experiment_discriminators),
        ]).lower()
        hits = sorted({p for p in _ADVISORY_PHRASES if p in haystack})
        if hits:
            raise ValueError(f"the report advises rather than reports: {hits}")
        return self

    def with_digest(self) -> "SynthesisReport":
        return SynthesisReport(**{**self.model_dump(),
                                  "content_digest": content_digest(
                                      self, exclude={"content_digest", "reproducibility"})})


def _family_outcome(family: FamilySpec, assessments: tuple[ArchitectureAssessment, ...],
                    registry: BuildingBlockRegistry, space) -> FamilyOutcome:
    missing_scale = (family.requires_scale is not None
                     and not any(family.requires_scale in b.scales for b in registry.blocks))
    if missing_scale:
        return FamilyOutcome(
            family_id=family.family_id, description=family.description,
            verdict=FamilyVerdict.NOT_REPRESENTABLE, architectures=(),
            reason=(f"no registered component acts at {family.requires_scale.value} scale, so the "
                    "family cannot be expressed in this state space — not a claim that it is "
                    "biologically impossible"))
    mine = []
    for a in assessments:
        if family.requires_feedback:
            if a.feedback_policy is not None:
                mine.append(a)
            continue
        if family.members and set(a.components) <= set(family.members):
            mine.append(a)
        elif family.requires_variables and set(family.requires_variables) & set(
                v for b in a.components for v in registry.get(b).variables):
            mine.append(a)
    ids = tuple(sorted(a.architecture_id for a in mine))
    if not mine and family.requires_feedback:
        return FamilyOutcome(
            family_id=family.family_id, description=family.description,
            verdict=FamilyVerdict.UNKNOWN, architectures=(),
            reason=("no feedback policy was supplied for this problem, so the compiler composed "
                    "no closed-loop architecture and says nothing about the family"))
    if not mine:
        registered = [b for b in registry.blocks
                      if (family.members and b.building_block_id in family.members)
                      or (family.requires_variables
                          and set(family.requires_variables) & set(b.variables))]
        if not registered:
            return FamilyOutcome(
                family_id=family.family_id, description=family.description,
                verdict=FamilyVerdict.UNKNOWN, architectures=(),
                reason=("the family is expressible but no building block is registered that acts "
                        "on it, so the compiler has nothing to compose and says nothing about it"))
        return FamilyOutcome(
            family_id=family.family_id, description=family.description,
            verdict=FamilyVerdict.UNSUPPORTED, architectures=(),
            reason=(f"components {[b.building_block_id for b in registered]} are registered but no "
                    "composition of them reached the target under any evidence-consistent variant"))
    if any(a.clear for a in mine):
        return FamilyOutcome(family_id=family.family_id, description=family.description,
                             verdict=FamilyVerdict.SUPPORTED, architectures=ids,
                             reason="a composition in this family is robust, safe and buildable")
    working = [a for a in mine if a.works_in]
    if working:
        why = sorted({*(b for a in working for b in a.feasibility_blockers),
                      *(b for a in working for b in a.blocking_relationships)})
        return FamilyOutcome(
            family_id=family.family_id, description=family.description,
            verdict=FamilyVerdict.CONDITIONALLY_SUPPORTED, architectures=ids,
            reason=f"reaches the target, conditional on {why}")
    return FamilyOutcome(family_id=family.family_id, description=family.description,
                         verdict=FamilyVerdict.UNSUPPORTED, architectures=ids,
                         reason="compositions exist but none reaches the target safely")


def _blocks_table(registry: BuildingBlockRegistry) -> tuple[dict, ...]:
    return tuple({
        "building_block": b.building_block_id, "class": b.block_class.value,
        "mechanism": b.mechanism, "route_class": b.route_class.value,
        "transformations": [f"{t.direction.value} {t.variable} -> {t.to}"
                            + ("" if t.intended else " (declared off-target)")
                            for t in b.state_transformations],
        "scale": [s.value for s in b.scales], "reversibility": b.reversibility.value,
        "cell_type": b.cell_type, "feasibility": b.feasibility_status.value,
        "feasibility_note": b.feasibility_note, "evidence": b.evidence,
        "uncertainty": b.uncertainty, "validity_domain": b.validity_domain,
        "epistemic_type": b.provenance.epistemic_type.value,
    } for b in sorted(registry.blocks, key=lambda b: b.building_block_id))


def compile_synthesis(sp: SynthesisProblem) -> SynthesisReport:
    problem: Problem = sp.problem
    space = problem.space
    gaps = direct_gaps(problem.target, problem.unsafe, problem.observation)
    unobservable = tuple(
        [f"target variable not measured by {gaps.observation_model}: {v}"
         for v in gaps.unobserved_target_variables]
        + [f"safety variable not measured by {gaps.observation_model}: {v}"
           for v in gaps.unobserved_safety_variables])

    base = dict(
        synthesis_compiler_version=SYNTHESIS_COMPILER_VERSION,
        control_compiler_version="control-compiler-0.1.0",
        synthesis_model_version=sp.synthesis_model_version,
        state_model_version=problem.state_model_version, rule_version=problem.rule_version,
        case_context_version=problem.case_context_version, problem_id=problem.problem_id,
        case_ref=problem.case_ref, building_blocks=_blocks_table(sp.registry),
        unobservable_states=unobservable, target_accountability=problem.target.accountability(),
        assumptions=problem.assumptions, known_omissions=problem.known_omissions,
        experiment_criterion_note=(
            "Deterministic elimination. Expected information gain is not computed: it needs a "
            "probability distribution over the candidate architectures, and none is grounded here."),
        reproducibility=_repro(),
    )

    def finish(result: SynthesisResultClass, *, required, entry_points=(), architectures=(),
               families=(), secondary=(), blocking=(), missing=(), abstention="",
               rescue="", **fields) -> SynthesisReport:
        return SynthesisReport(
            **base, result=result, result_meaning=SYNTHESIS_MEANING[result],
            secondary_results=tuple(sorted(set(secondary) - {result}, key=lambda r: r.value)),
            required_functions=required, entry_points=tuple(entry_points),
            architectures=tuple(architectures), families=tuple(families),
            blocking_relationships=tuple(blocking), missing_relationships=tuple(missing),
            abstention_reason=abstention,
            rescue_scope_statement=rescue or (
                "no architecture reached the target, so nothing was reached at any scale"),
            **fields).with_digest()

    empty_decomposition = Decomposition(
        required=(), unmet=(), entry_points=(),
        note="not computed: the specification or the model blocks it")

    # 1. Success must be defined before anything can be synthesized for it.
    unspecified = problem.target.unspecified()
    if unspecified:
        return finish(SynthesisResultClass.SPECIFICATION_INCOMPLETE, required=empty_decomposition,
                      blocking=tuple(f"target_unspecified:{c.constraint_id}" for c in unspecified),
                      abstention="what counts as success is not defined: " + "; ".join(
                          f"{c.constraint_id} ({c.approval.note})" for c in unspecified))

    # 2. Missing biology stays missing: fail closed rather than compose around a hole.
    missing = _missing_relationships(problem)
    if missing:
        return finish(SynthesisResultClass.ARCHITECTURE_INDETERMINATE, required=empty_decomposition,
                      missing=tuple(missing), blocking=tuple(missing),
                      abstention="a variable the target or safety depends on has no defining "
                                 "relationship; composing an architecture across that hole would "
                                 "invent the biology it needs")

    try:
        variants = [v for model in problem.models for v in expand(space, model)]
    except TooBroadToEnumerate as exc:
        return finish(SynthesisResultClass.ARCHITECTURE_INDETERMINATE, required=empty_decomposition,
                      blocking=(f"too_broad:{exc}",), abstention=str(exc))

    x0, consistent, excluded = {}, [], []
    for v in variants:
        states = initial_states(space, v, problem.evidence)
        if states:
            consistent.append(v)
            x0[v.variant_id] = states
        else:
            excluded.append(v.variant_id)
    if not consistent:
        return finish(SynthesisResultClass.ARCHITECTURE_INDETERMINATE, required=empty_decomposition,
                      blocking=("no_model_variant_consistent_with_evidence",),
                      excluded_variants=tuple(sorted(excluded)),
                      abstention="every model variant is contradicted by the evidence, so nothing "
                                 "about control or architecture follows from it")

    ctx = VariantContext(tuple(consistent), {v.variant_id: compile_variant(space, v)
                                             for v in consistent},
                         {k: x0[k] for k in sorted(x0)})

    # 4. The inversion: what must become true, and where a transformation would have to act.
    required = decompose(problem, ctx.x0, sp.population.population_variables,
                         sp.population.tissue_variables)

    # 9-18. Compose, evaluate, and keep the two feasibilities apart.
    try:
        found: SynthesisSearch = synthesize(problem, ctx, sp.registry, sp.population,
                                            max_depth=sp.max_depth, max_per_step=sp.max_per_step,
                                            policies=sp.policies)
    except TooBroadToSynthesize as exc:
        return finish(SynthesisResultClass.ARCHITECTURE_INDETERMINATE, required=required,
                      entry_points=required.entry_points, blocking=(f"search_too_broad:{exc}",),
                      candidate_variants=ctx.ids, excluded_variants=tuple(sorted(excluded)),
                      abstention=str(exc))

    proposed = tuple(assess_composition(problem, ctx, sp.registry, sp.population, a)
                     for a in sorted(sp.proposed, key=lambda a: a.architecture_id))
    everything = tuple(found.assessments) + proposed
    families = tuple(_family_outcome(f, everything, sp.registry, space)
                     for f in sorted(sp.families, key=lambda f: f.family_id))
    # Label each architecture with the declared families that claim it, so the map names the
    # question each one answers instead of a label derived from its own shape.
    claimed: dict[str, list[str]] = {}
    for outcome in families:
        for aid in outcome.architectures:
            claimed.setdefault(aid, []).append(outcome.family_id)
    if claimed:
        def relabel(a: ArchitectureAssessment) -> ArchitectureAssessment:
            if a.architecture_id not in claimed:
                return a
            # Rebuilt through the constructor so the validators run on what the report carries.
            return ArchitectureAssessment(**{**a.model_dump(),
                                             "family": ", ".join(claimed[a.architecture_id])})

        found = SynthesisSearch(assessments=tuple(relabel(a) for a in found.assessments),
                                compositions_examined=found.compositions_examined,
                                note=found.note)
        proposed = tuple(relabel(a) for a in proposed)
        everything = tuple(found.assessments) + proposed

    controls = sp.registry.controls()
    discriminators = compile_experiments(problem, ctx, sp.registry, everything, controls)

    confounder_gaps = tuple(sorted(
        {g.model_dump_json(): g for a in everything for g in a.confounder_gaps}.values(),
        key=lambda g: (g.variable, g.process_id)))
    blocking = tuple(sorted({b for a in everything for b in a.blocking_relationships}))
    irrelevant = tuple(sorted({u for a in everything for u in a.irrelevant_unknowns} - set(blocking)))

    shared = dict(
        architectures=found.assessments, proposed_architectures=proposed, families=families,
        confounder_gaps=confounder_gaps, experiment_discriminators=discriminators,
        candidate_variants=ctx.ids, excluded_variants=tuple(sorted(excluded)),
        compositions_examined=found.compositions_examined, search_note=found.note,
        irrelevant_unknowns=irrelevant,
    )

    secondary = []
    if not gaps.sufficient:
        secondary.append(SynthesisResultClass.ARCHITECTURE_OBSERVABILITY_INSUFFICIENT)
    if problem.target.accountability() != "APPROVED":
        secondary.append(SynthesisResultClass.SPECIFICATION_INCOMPLETE)

    robust = [a for a in everything
              if a.logical is LogicalStatus.TARGET_REACHABLE and not a.unsafe_in
              and a.robustness is RobustnessClass.ROBUST_CONTROL_CANDIDATE]
    rescue = (robust[0].rescue_scope if robust else
              (everything[0].rescue_scope if everything and everything[0].works_in else ""))

    if robust:
        feasible = [a for a in robust if a.physically_feasible]
        if feasible:
            blocked_by_observation = [a for a in feasible
                                      if a.confounder_gaps or a.unobservable_policy_inputs]
            if not gaps.sufficient or blocked_by_observation:
                return finish(SynthesisResultClass.ARCHITECTURE_OBSERVABILITY_INSUFFICIENT,
                              required=required, entry_points=required.entry_points,
                              secondary=secondary, blocking=blocking, rescue=rescue, **shared,
                              abstention="a composition reaches the target, but what would be "
                                         "measured cannot distinguish it from a process that "
                                         "produces the same reading")
            return finish(SynthesisResultClass.ARCHITECTURE_SYNTHESIZED, required=required,
                          entry_points=required.entry_points, secondary=secondary,
                          blocking=blocking, rescue=rescue, **shared,
                          abstention=("" if problem.target.accountability() == "APPROVED" else
                                      "conditional on a target that no accountable scientist has "
                                      "approved"))
        return finish(SynthesisResultClass.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN, required=required,
                      entry_points=required.entry_points, secondary=secondary, blocking=blocking,
                      rescue=rescue, **shared,
                      abstention="a composition reaches the target under every evidence-compatible "
                                 "model; what is missing is a demonstrated way to produce its "
                                 "declared transformations, which is named per component")

    disagreeing = [a for a in everything if a.robustness is RobustnessClass.MODEL_DISAGREEMENT]
    if disagreeing:
        return finish(SynthesisResultClass.ARCHITECTURE_MODEL_DISAGREEMENT, required=required,
                      entry_points=required.entry_points, secondary=secondary, blocking=blocking,
                      rescue=rescue, **shared,
                      abstention="evidence-compatible models imply different architectures; the "
                                 "disagreement is the result, not the favourable half of it")

    if any(a.works_in for a in everything):
        return finish(SynthesisResultClass.ARCHITECTURE_INDETERMINATE, required=required,
                      entry_points=required.entry_points, secondary=secondary,
                      blocking=blocking or ("no_blocking_relationship_identified",),
                      rescue=rescue, **shared,
                      abstention="every composition that reaches the target depends on something "
                                 "not yet known; the blockers are named per architecture")

    return finish(SynthesisResultClass.NO_ARCHITECTURE_SYNTHESIZED, required=required,
                  entry_points=required.entry_points, secondary=secondary, blocking=blocking,
                  **shared,
                  abstention="no composition of the registered building blocks reaches the target "
                             "safely under any evidence-consistent variant — a statement about the "
                             "registry and the model, not about biology")
