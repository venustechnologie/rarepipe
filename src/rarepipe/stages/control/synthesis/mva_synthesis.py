"""The MVA case as a synthesis problem: what else could produce the target state.

The control compiler represented two transformations — restore the altered protein's abundance, or
supply its checkpoint-competent function directly. This module keeps both, as one family among
several, and asks the question the previous phase could not: what architectures reach the same
functional target **without** depending on either of them.

The alternatives are entered as declared capabilities with their feasibility unassessed, which is
the honest status: nothing here has been shown to work in the relevant cells, and the compiler is
built so that a composition reaching the target cannot be mistaken for evidence that it can be
built. Every component that holds a variable the model already defines is recorded as overriding
that relationship, because supplying a function the model attributes to BubR1 is a requirement of
its own, not a free move.

One family is included specifically to be rejected: selecting against the aneuploid cells drives
the aneuploid fraction down while killing the cells that carry it. The compiler must refuse it on
the safety constraint, and separately note that it does not satisfy a target defined on checkpoint
behaviour.
"""
from __future__ import annotations

from rarepipe.stages.control import mva
from rarepipe.stages.control.controls import BiologicalControlKind, Feasibility, RouteClass
from rarepipe.stages.control.provenance import EpistemicType, Provenance
from rarepipe.stages.control.synthesis.building_blocks import (
    BlockTransformation, BuildingBlock, BuildingBlockRegistry,
)
from rarepipe.stages.control.synthesis.compiler import FamilySpec, SynthesisProblem
from rarepipe.stages.control.synthesis.feedback import (
    FeedbackAction, FeedbackPolicy, FeedbackRule,
)
from rarepipe.stages.control.synthesis.kinds import (
    BlockClass, Direction, Reversibility, TransformationScale,
)
from rarepipe.stages.control.synthesis.population import (
    ConfoundingProcess, PopulationLayer, PopulationMechanism,
)
from rarepipe.stages.control.target_constraints import Membership

SYNTHESIS_MODEL_VERSION = "mva-synthesis-v1"
PROPOSER = ("rarepipe synthesis compiler, MVA architecture families (prepared by AI; no human "
            "review)")
INTRA = TransformationScale.INTRACELLULAR
POP = TransformationScale.POPULATION

_UNASSESSED = ("no mechanism has been shown to produce this transformation in the patient's cell "
               "type; the transformation is what the architecture requires, not something "
               "available")


def _p(kind: EpistemicType, source: str, *, refs: tuple[str, ...] = (), rationale: str = "") -> Provenance:
    return Provenance(epistemic_type=kind, source=source, proposed_by=PROPOSER, references=refs,
                      rationale=rationale)


def _tf(variable, to, *, direction=Direction.SET, scale=INTRA, intended=True, released_to=None,
        rationale="", kind=BiologicalControlKind.PATHWAY_ACTIVATION):
    return BlockTransformation(variable=variable, to=to, direction=direction, scale=scale,
                               control_kind=kind, intended=intended, released_to=released_to,
                               release_rationale=rationale)


def _block(bid, *transformations, mechanism, route, scale=INTRA, kind=BlockClass.CELLULAR_PROCESS,
           reversibility=Reversibility.UNKNOWN, requires=(), population=(), safety=(),
           off_targets=(), evidence, refs=(), validity, uncertainty,
           feasibility=Feasibility.UNASSESSED, note=_UNASSESSED,
           epistemic=EpistemicType.INFERRED_HYPOTHESIS):
    return BuildingBlock(
        building_block_id=bid, block_class=kind, mechanism=mechanism, route_class=route,
        input_state_requirements=tuple(requires), state_transformations=tuple(transformations),
        scale=scale, reversibility=reversibility,
        cell_type="patient-derived cells of the type the endpoints are measured in",
        tissue_context="not specified; the state model does not represent tissue context",
        delivery_requirements="unspecified; a delivery route is part of what is unassessed",
        known_off_targets=tuple(off_targets), population_effects=tuple(population),
        safety_effects=tuple(safety), evidence=evidence, evidence_refs=refs,
        validity_domain=validity, uncertainty=uncertainty, feasibility_status=feasibility,
        feasibility_note=note, provenance=_p(epistemic, f"MVA architecture family for {bid}",
                                             refs=refs, rationale=uncertainty))


def registry() -> BuildingBlockRegistry:
    checkpoint_evidence = (
        "the state model's own relationships: each checkpoint readout is attributed to "
        "checkpoint-competent BubR1 function, so holding one directly asserts a mechanism the "
        "model does not contain")
    return BuildingBlockRegistry(blocks=(
        # --- the two transformations the control compiler already represented
        _block("BB_ABUNDANCE_STABILIZATION",
               _tf("bubr1_abundance", "restored", direction=Direction.INCREASE,
                   released_to="low", kind=BiologicalControlKind.PROTEIN_STABILITY,
                   rationale=("the variant's effect on steady-state level is unchanged by any "
                              "stabilising mechanism, so abundance returns to its baseline when "
                              "the mechanism stops")),
               mechanism=("raise the steady-state level of the altered protein without changing "
                          "its sequence, by slowing its turnover or raising its production"),
               route=RouteClass.STABILIZATION, kind=BlockClass.PROTEIN_STABILIZATION,
               reversibility=Reversibility.REVERSIBLE,
               evidence=("the abundance route the control compiler already evaluates; whether "
                         "more of the altered protein restores function is the open question"),
               validity="the qualitative relation only; no magnitude or timing is represented",
               uncertainty=("depends entirely on the unresolved abundance-to-function "
                            "relationship")),
        _block("BB_FUNCTION_REPLACEMENT",
               _tf("bubr1_function", "sufficient",
                   kind=BiologicalControlKind.FUNCTIONAL_REPLACEMENT),
               mechanism=("supply checkpoint-competent BubR1 activity directly, so the target no "
                          "longer depends on whether the altered protein regains function"),
               route=RouteClass.REPLACEMENT, kind=BlockClass.PROTEIN,
               evidence=("the replacement route the control compiler already evaluates; it "
                         "reaches the target under both candidates for the open relationship"),
               validity="the qualitative relation only",
               uncertainty=("the transformation is well defined; nothing is known to produce it "
                            "in the relevant cells")),

        # --- bypass: supply the checkpoint functions without BubR1 at all
        _block("BB_CHECKPOINT_BYPASS_CIRCUIT",
               _tf("checkpoint_activation", "normal"),
               _tf("checkpoint_silencing", "normal"),
               _tf("chromosome_alignment", "normal"),
               mechanism=("one mechanism that supplies arrest competence, timely exit and "
                          "alignment competence together, without passing through BubR1"),
               route=RouteClass.BYPASS, kind=BlockClass.SYNTHETIC_CIRCUIT,
               evidence=checkpoint_evidence,
               validity="the qualitative relation only; nothing about how one mechanism would do all three",
               uncertainty=("asserts a single mechanism can supply three functions the model "
                            "attributes to BubR1; the strongest assumption in the registry")),

        # --- compensation: three separate partial mechanisms, one per function
        _block("BB_ARREST_COMPETENCE_SUPPLY", _tf("checkpoint_activation", "normal"),
               mechanism=("supply mitotic arrest competence when spindles are disrupted by a "
                          "route that does not require BubR1"),
               route=RouteClass.COMPENSATION, evidence=checkpoint_evidence,
               validity="the qualitative relation only",
               uncertainty="one of three functions that must all be supplied for the target to hold"),
        _block("BB_SILENCING_COMPETENCE_SUPPLY", _tf("checkpoint_silencing", "normal"),
               mechanism=("restore timely checkpoint exit once chromosomes are attached, by a "
                          "route that does not require BubR1"),
               route=RouteClass.COMPENSATION, evidence=checkpoint_evidence,
               validity="the qualitative relation only",
               uncertainty="one of three functions that must all be supplied for the target to hold"),
        _block("BB_ALIGNMENT_COMPETENCE_SUPPLY", _tf("chromosome_alignment", "normal"),
               mechanism=("restore chromosome alignment by a route that does not require BubR1 — "
                          "for instance by acting on the phosphatase recruitment it normally "
                          "mediates"),
               route=RouteClass.COMPENSATION, evidence=checkpoint_evidence,
               validity="the qualitative relation only",
               uncertainty="one of three functions that must all be supplied for the target to hold"),

        # --- suppression of the error rate without restoring checkpoint behaviour
        _block("BB_MISSEGREGATION_SUPPRESSION", _tf("missegregation", "normal",
                                                     direction=Direction.DECREASE),
               mechanism=("lower the chromosome-missegregation rate directly, without restoring "
                          "the checkpoint behaviour the target is defined on"),
               route=RouteClass.SUPPRESSION,
               evidence=("the model drives missegregation from arrest competence and alignment; "
                         "holding it directly asserts a mechanism that bypasses both"),
               validity="the qualitative relation only",
               uncertainty=("reaches one of the four target constraints and leaves the other "
                            "three untouched")),

        # --- population composition: included so the compiler has to refuse it
        _block("BB_ANEUPLOID_SELECTION",
               _tf("total_aneuploidy", "reduced", direction=Direction.DECREASE, scale=POP),
               _tf("cell_death", "increased", direction=Direction.INCREASE, scale=POP,
                   intended=False),
               mechanism=("shift the population towards euploid cells by selecting against the "
                          "aneuploid ones, which removes them rather than correcting them"),
               route=RouteClass.SUPPRESSION, kind=BlockClass.CELL_POPULATION, scale=POP,
               population=("lowers the aneuploid fraction by removing aneuploid cells",),
               safety=("raises cell death, which is a declared unsafe state",),
               evidence=("the aneuploid fraction can fall for two reasons, and selective loss is "
                         "one of them; this is the family that makes that confusion concrete"),
               validity="the qualitative relation only",
               uncertainty=("the declared off-target effect is the mechanism, not a side effect: "
                            "the fraction falls because cells die")),
    ))


def population() -> PopulationLayer:
    return PopulationLayer(
        population_variables=("total_aneuploidy", "cell_death", "viability", "division_rate"),
        mechanisms=(PopulationMechanism(
            mechanism_id="M_SELECTIVE_LOSS", produces="differential_death",
            drives="total_aneuploidy",
            source_of_differential=("aneuploid cells carry an unbalanced genome and are less "
                                    "tolerant of further stress, so a pressure applied to the "
                                    "whole population removes them preferentially"),
            provenance=_p(EpistemicType.POPULATION_CONTROL,
                          "the mechanism behind the aneuploidy confound",
                          rationale="states what makes the loss selective rather than uniform")),),
        confounders=(ConfoundingProcess(
            process_id="P_SELECTIVE_LOSS", could_produce="total_aneuploidy", reading=("reduced",),
            mechanism=("losing the aneuploid cells lowers the aneuploid fraction without "
                       "improving any surviving cell"),
            excluded_by=("cell_death", "viability"), represented_in_model=True,
            provenance=_p(EpistemicType.MODEL_ASSUMPTION,
                          "generalised from the control compiler's finding on this measurement",
                          rationale=("the fraction is a ratio, so anything that changes the "
                                     "denominator changes the reading"))),),
    )


def policy() -> FeedbackPolicy:
    """Close the loop on the abundance route, with the stop condition on a safety variable."""
    return FeedbackPolicy(
        policy_id="PI_ABUNDANCE_SAFETY_GUARDED",
        rules=(
            FeedbackRule(rule_id="R_START",
                         when=Membership(variable="checkpoint_activation", allowed=("impaired",)),
                         action=FeedbackAction.ACTIVATE,
                         control_id="BB_ABUNDANCE_STABILIZATION::bubr1_abundance",
                         rationale="hold the stabilising mechanism while arrest competence is impaired"),
            FeedbackRule(rule_id="R_STOP",
                         when=Membership(variable="cell_death", allowed=("increased",)),
                         action=FeedbackAction.DEACTIVATE,
                         control_id="BB_ABUNDANCE_STABILIZATION::bubr1_abundance",
                         rationale="withdraw it if cell death rises, which is a declared unsafe state"),
        ),
        sampling=("one reading of the measured endpoints per decision point; no interval is "
                  "claimed, and the loop is evaluated over every interleaving instead"),
        provenance=_p(EpistemicType.FEEDBACK_POLICY,
                      "the closed-loop variant of the abundance route",
                      rationale=("tests whether closing the loop removes the dependence on the "
                                 "unresolved relationship, rather than assuming it does")),
    )


def families() -> tuple[FamilySpec, ...]:
    return (
        FamilySpec(family_id="F01_RESTORE_BUBR1_ABUNDANCE",
                   description="raise the altered protein's level and hope function follows",
                   members=("BB_ABUNDANCE_STABILIZATION",),
                   rationale="the route the disease mechanism makes obvious"),
        FamilySpec(family_id="F02_REPLACE_BUBR1_FUNCTION",
                   description="supply checkpoint-competent activity directly",
                   members=("BB_FUNCTION_REPLACEMENT",),
                   rationale="the route that does not depend on the unresolved relationship"),
        FamilySpec(family_id="F03_BYPASS_BUBR1_DEPENDENCE",
                   description="supply the checkpoint functions by one mechanism that is not BubR1",
                   members=("BB_CHECKPOINT_BYPASS_CIRCUIT",),
                   rationale="asks whether the target needs BubR1 at all, in any form"),
        FamilySpec(family_id="F04_COMPENSATE_CHECKPOINT_FUNCTION",
                   description="supply each checkpoint function separately",
                   members=("BB_ARREST_COMPETENCE_SUPPLY", "BB_SILENCING_COMPETENCE_SUPPLY",
                            "BB_ALIGNMENT_COMPETENCE_SUPPLY"),
                   rationale=("several incomplete mechanisms that may jointly produce the target; "
                              "a different feasibility burden from one mechanism doing all three")),
        FamilySpec(family_id="F05_REDUCE_SEGREGATION_ERRORS",
                   description="lower the error rate without restoring checkpoint behaviour",
                   members=("BB_MISSEGREGATION_SUPPRESSION",),
                   rationale="tests whether the target as written can be met further downstream"),
        FamilySpec(family_id="F06_POPULATION_STATE_CONTROL",
                   description="change the composition of the population instead of any cell",
                   members=("BB_ANEUPLOID_SELECTION",),
                   rationale=("included so the compiler has to refuse the route that reaches the "
                              "reading by removing the cells that carry it")),
        FamilySpec(family_id="F07_CELL_STATE_REPLACEMENT",
                   description="replace the dysfunctional population with a functional one",
                   requires_scale=TransformationScale.TISSUE_FUNCTION,
                   rationale=("asked for explicitly; the state model has no tissue-function "
                              "variable, so the answer should be that it cannot be expressed")),
        FamilySpec(family_id="F08_FEEDBACK_CONTROLLED_ROUTE",
                   description="measure, decide, act, measure again",
                   requires_feedback=True,
                   rationale=("tests whether closing the loop changes what is reachable, rather "
                              "than assuming feedback helps")),
    )


def problem() -> SynthesisProblem:
    return SynthesisProblem(
        problem=mva.problem(), registry=registry(), population=population(),
        policies=(policy(),), families=families(),
        synthesis_model_version=SYNTHESIS_MODEL_VERSION, max_depth=2, max_per_step=3)
