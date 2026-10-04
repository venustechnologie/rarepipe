"""The eighteen invariants of the synthesis layer, each as an executable check.

An invariant stated in a design document constrains nobody. These are the same statements, written
so that violating one turns a test red.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from pydantic import ValidationError

from rarepipe.stages.control.controllability import StrategyAssessment, VariantOutcome
from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.objective import rank, rank_key
from rarepipe.stages.control.proposals import Proposal, ProposalKind, gate
from rarepipe.stages.control.provenance import (
    DERIVED_TYPES, EpistemicType, IllegalPromotion, Provenance, promote,
)
from rarepipe.stages.control.synthesis.architecture import ArchitectureAssessment
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlock
from rarepipe.stages.control.synthesis.compiler import (
    NO_RECOMMENDATION, SynthesisReport, compile_synthesis,
)
from rarepipe.stages.control.synthesis.kinds import (
    LogicalStatus, PhysicalStatus, RobustnessClass, TransformationScale,
)
from rarepipe.stages.control.synthesis.population import rescue_scope
from rarepipe.stages.prospective.model import Actor, ActorType, Role
from tests import synthesis_toys as T

AGENT = Actor(actor_type=ActorType.AGENT, identity="architecture-generator",
              roles=(Role.ENGINEER,))


def run(problem, blocks, **kw):
    return compile_synthesis(T.synthesis(problem, blocks, **kw))


# I1 -- no synthetic route becomes empirical evidence

def test_i1_a_derived_result_cannot_be_promoted_to_evidence_without_a_measurement():
    for derived in sorted(DERIVED_TYPES, key=lambda t: t.value):
        with pytest.raises(IllegalPromotion):
            promote(derived, EpistemicType.OBSERVED_EMPIRICAL)
        assert promote(derived, EpistemicType.OBSERVED_EMPIRICAL,
                       ("PMID:00000000",)) is EpistemicType.OBSERVED_EMPIRICAL


def test_i1_every_synthesis_report_is_a_simulated_prediction():
    report = run(*T.repair_only())
    assert report.origin == "simulated_prediction"
    with pytest.raises(ValidationError):
        SynthesisReport(**{**report.model_dump(), "origin": "observed_empirical"})


# I2 -- no agent-created edge enters the dynamics untyped

def test_i2_an_agent_proposed_architecture_is_typed_as_proposed_not_composed():
    proposal = Proposal(
        proposal_id="PR_ARCH", skill_id="architecture_generator", skill_version="1.0",
        proposer=AGENT, kind=ProposalKind.ARCHITECTURE,
        payload={"architecture_id": "A_AGENT", "family": "bypass", "composition": [["B_REPAIR"]],
                 "composition_mode": "simultaneous", "origin": "natural_bypass",
                 "rationale": "route around the damaged node"},
        rationale="imagined by the generator")
    decision = gate(proposal)
    assert decision.accepted
    assert decision.assigned_epistemic_type is EpistemicType.PROPOSED_ARCHITECTURE


@pytest.mark.parametrize("claim", ["ROBUST_CONTROL_CANDIDATE", "LOGICALLY_SYNTHESIZABLE",
                                   "PHYSICALLY_FEASIBLE", "VALID_CONTROL",
                                   "ARCHITECTURE_SYNTHESIZED"])
def test_i2_a_proposal_cannot_state_a_verdict_the_compiler_owns(claim):
    proposal = Proposal(
        proposal_id="PR_CLAIM", skill_id="architecture_generator", skill_version="1.0",
        proposer=AGENT, kind=ProposalKind.ARCHITECTURE,
        payload={"architecture_id": "A_AGENT", "family": "bypass", "composition": [["B_REPAIR"]],
                 "composition_mode": "simultaneous", "origin": "natural_bypass",
                 "rationale": f"this is a {claim}"},
        rationale="imagined by the generator")
    assert not gate(proposal).accepted


def test_i2_an_agent_cannot_assert_a_component_is_feasible_or_quantified():
    payload = json.loads(T.block("B_AGENT", T.tf("lesion", "1")).model_dump_json())
    payload.pop("provenance")
    payload["feasibility_status"] = Feasibility.ESTABLISHED.value
    payload["state_transformations"][0]["magnitude_if_known"] = "two-fold"
    proposal = Proposal(proposal_id="PR_BB", skill_id="building_block_discovery",
                        skill_version="1.0", proposer=AGENT, kind=ProposalKind.BUILDING_BLOCK,
                        payload=payload, rationale="proposed by discovery")
    decision = gate(proposal)
    assert decision.accepted
    assert decision.assigned_epistemic_type is EpistemicType.INFERRED_HYPOTHESIS
    accepted = decision.accepted_object
    assert accepted["feasibility_status"] == Feasibility.UNASSESSED.value
    assert accepted["state_transformations"][0]["magnitude_if_known"] == ""


# I3 -- hard safety cannot be optimised away

def test_i3_safety_outranks_every_benefit_in_the_lexicographic_order():
    def assessment(aid, unsafe, works):
        return StrategyAssessment(
            strategy=((aid,),), controls=(aid,),
            outcomes=(VariantOutcome(variant_id="v", model_id="M", status="SUCCESS"),),
            works_in=tuple(f"v{i}" for i in range(works)),
            unsafe_in=("v0",) if unsafe else (), per_model=(("M", "ALL"),),
            blocking_relationships=(), irrelevant_unknowns=(), model_disagreement=False,
            feasibility_blockers=(), relies_on=(), unresolved_relied_on=())

    unsafe_but_universal = assessment("UNSAFE", unsafe=True, works=99)
    safe_but_narrow = assessment("SAFE", unsafe=False, works=1)
    assert rank([unsafe_but_universal, safe_but_narrow])[0] is safe_but_narrow
    assert rank_key(safe_but_narrow)[0] is False and rank_key(unsafe_but_universal)[0] is True


def test_i3_no_weight_can_trade_safety_against_anything():
    key = rank_key(StrategyAssessment(
        strategy=(("c",),), controls=("c",), outcomes=(), works_in=(), unsafe_in=(),
        per_model=(), blocking_relationships=(), irrelevant_unknowns=(),
        model_disagreement=False, feasibility_blockers=(), relies_on=(),
        unresolved_relied_on=()))
    assert not any(isinstance(component, float) for component in key), \
        "a float in the ranking key is a weight, and a weight can be tuned until safety loses"


# I4 -- missing biology remains missing (see also the gates)

def test_i4_a_hole_in_the_model_is_never_filled_by_the_search():
    report = run(*T.repair_only(drop_relationship=True))
    assert report.missing_relationships and not report.architectures


# I5 -- the two feasibilities stay apart

def test_i5_an_assessment_cannot_claim_physical_feasibility_with_unbuilt_components():
    report = run(*T.repair_only(feasibility=Feasibility.UNASSESSED))
    working = next(a for a in report.architectures if a.works_in)
    with pytest.raises(ValidationError):
        ArchitectureAssessment(**{**working.model_dump(),
                                  "physical": PhysicalStatus.PHYSICALLY_FEASIBLE.value})


def test_i5_logical_reachability_does_not_set_the_physical_verdict():
    reachable = run(*T.repair_only(feasibility=Feasibility.UNASSESSED)).architectures[0]
    assert reachable.logical is LogicalStatus.TARGET_REACHABLE
    assert reachable.physical is PhysicalStatus.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN


# I6 / I7 -- population improvement is not cellular rescue

def test_i6_a_population_only_architecture_states_that_no_cell_was_corrected():
    assert "not evidence of cellular rescue" in rescue_scope((TransformationScale.POPULATION,))
    assert "separate claim" in rescue_scope((TransformationScale.INTRACELLULAR,))


def test_i7_a_composition_reading_needs_its_confounders_excluded():
    problem, blocks, population = T.population_rescue(confounder=True)
    report = run(problem, blocks, population=population)
    assert report.confounder_gaps
    assert all("supports no conclusion" in g.consequence for g in report.confounder_gaps)


# I8 / I9 -- provenance on components and on constants

def test_i8_a_building_block_must_carry_a_capability_or_hypothesis_type():
    good = T.block("B_OK", T.tf("lesion", "1"))
    with pytest.raises(ValidationError):
        BuildingBlock(**{**good.model_dump(),
                         "provenance": Provenance(epistemic_type=EpistemicType.OBSERVED_EMPIRICAL,
                                                  source="s", proposed_by="p",
                                                  references=("PMID:1",)).model_dump()})


def test_i9_a_magnitude_without_a_citation_is_refused():
    with pytest.raises(ValidationError):
        T.block("B_NUM", T.tf("lesion", "1", magnitude="two-fold increase"))
    T.block("B_NUM", T.tf("lesion", "1", magnitude="two-fold increase"), refs=("PMID:00000000",))


# I10 / I11 / I12 -- every architecture records its assumptions, scale and models

@pytest.mark.parametrize("toy", ["repair_only", "bypass", "two_needed", "unsafe_downstream"])
def test_i10_i11_i12_every_assessment_records_assumptions_scale_and_models(toy):
    report = run(*getattr(T, toy)())
    assert report.architectures
    for architecture in report.architectures:
        assert architecture.assumptions, "an architecture with no stated assumptions hides them"
        assert architecture.scales, "an architecture must say what scale it acts at"
        assert architecture.per_model, "an architecture must say which models it was judged under"
        assert architecture.rescue_scope


# I13 -- a feedback policy reads something that is measured

def test_i13_a_policy_on_an_unmeasured_variable_cannot_succeed():
    problem, blocks, _ = T.feedback_needed()
    blind = T.policy("PI_BLIND", ("m", "1", T.ACTIVATE, "B_PUSH::u"))
    narrowed = problem.model_copy(update={
        "observation": problem.observation.model_copy(update={"observed": ("u", "x")})})
    architecture = next(a for a in run(narrowed, blocks, policies=(blind,)).architectures
                        if a.feedback_policy == "PI_BLIND")
    assert architecture.unobservable_policy_inputs and not architecture.works_in


# I14 -- a population control says what makes it selective

def test_i14_a_population_mechanism_must_state_its_source_of_differential():
    from rarepipe.stages.control.synthesis.population import PopulationMechanism
    with pytest.raises(ValidationError):
        PopulationMechanism(mechanism_id="M", produces="competition", drives="functional_fraction",
                            source_of_differential="selection",
                            provenance=T.prov(EpistemicType.POPULATION_CONTROL))


# I15 -- no treatment recommendation

def test_i15_the_no_recommendation_statement_is_fixed():
    report = run(*T.repair_only())
    assert report.no_treatment_recommendation == NO_RECOMMENDATION
    with pytest.raises(ValidationError):
        SynthesisReport(**{**report.model_dump(),
                           "no_treatment_recommendation": "see the attached protocol"})


def test_i15_advisory_language_is_refused_wherever_it_appears():
    report = run(*T.repair_only())
    with pytest.raises(ValidationError, match="advises rather than reports"):
        SynthesisReport(**{**report.model_dump(),
                           "abstention_reason": "the patient should start treatment now"})


def test_i15_the_advisory_scan_does_not_fire_on_ordinary_scientific_language():
    report = run(*T.repair_only())
    for innocent in ["the effect is dose-dependent across the measured range",
                     "a recommended reading order for the appendix",
                     "the authors recommend caution interpreting the assay",
                     "treatment-naive cells were used in the cited experiment",
                     "the dosing literature is outside this model's validity domain"]:
        SynthesisReport(**{**report.model_dump(), "abstention_reason": innocent})


# I16 / I17 -- plans stay versioned and human-controlled; case data stays inside its boundary

def test_i16_every_report_carries_the_versions_it_was_produced_under():
    report = run(*T.repair_only())
    for field in ("synthesis_compiler_version", "control_compiler_version",
                  "synthesis_model_version", "state_model_version", "rule_version",
                  "case_context_version"):
        assert getattr(report, field), f"{field} must travel with the report"
    assert report.content_digest.startswith("sha256:")


_CASE_PATTERNS = (r"\bc\.\d", r"\bp\.[A-Z][a-z]{2}\d", r"\bchr[0-9XYM]", r"\brs\d{3,}",
                  r"\bg\.\d{4,}", r"\b[ACGT]{8,}\b")


def test_i17_no_case_level_genomic_content_reaches_a_synthesis_report():
    report = run(*T.repair_only())
    blob = report.model_dump_json()
    for pattern in _CASE_PATTERNS:
        assert not re.search(pattern, blob), f"{pattern} matched in a synthesis report"


# I18 -- reproducibility

def test_i18_the_same_inputs_give_the_same_digest_across_processes():
    script = (
        "from rarepipe.stages.control.synthesis.compiler import compile_synthesis\n"
        "from tests import synthesis_toys as T\n"
        "problem, blocks, population = T.population_rescue(confounder=True)\n"
        "print(compile_synthesis(T.synthesis(problem, blocks, population=population)).content_digest)\n"
    )
    digests = set()
    for seed in ("0", "1", "12345"):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                                  "PYTHONPATH": "src:."}, cwd="/Users/venus/Desktop/rarepipe")
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    assert len(digests) == 1, f"the digest moved with the hash seed: {digests}"


def test_i18_a_conflicting_composition_is_refused_rather_than_resolved_by_sort_order():
    from rarepipe.stages.control.synthesis.composition import conflicts
    from rarepipe.stages.control.synthesis.building_blocks import BuildingBlockRegistry
    registry = BuildingBlockRegistry(blocks=(
        T.block("B_UP", T.tf("lesion", "1")), T.block("B_DOWN", T.tf("lesion", "0"))))
    assert conflicts(registry, (("B_UP", "B_DOWN"),))
    report = run(*T.repair_only())
    assert all(len(set(a.components)) == len(a.components) for a in report.architectures)


# The proposal path end to end: an agent imagines, the gate types it, the compiler judges it.

def _gated_architecture(payload):
    from rarepipe.stages.control.synthesis.architecture import ControlArchitecture
    decision = gate(Proposal(
        proposal_id="PR_E2E", skill_id="synthesis-architecture-generator", skill_version="0.1.0",
        proposer=AGENT, kind=ProposalKind.ARCHITECTURE, payload=payload,
        rationale="imagined by the generator"))
    assert decision.accepted, decision.reason
    assert decision.assigned_epistemic_type is EpistemicType.PROPOSED_ARCHITECTURE
    return ControlArchitecture(**decision.accepted_object)


def test_an_agent_proposal_is_evaluated_by_the_same_code_as_an_enumerated_one():
    problem, blocks = T.two_needed()
    architecture = _gated_architecture({
        "architecture_id": "A_AGENT_PAIR", "family": "pair",
        "composition": [["B_A", "B_B"]], "composition_mode": "simultaneous",
        "origin": "synthetic_composition",
        "rationale": "both components together", "assumptions": ["they act together"]})
    assert architecture.provenance.epistemic_type is EpistemicType.PROPOSED_ARCHITECTURE
    report = run(problem, blocks, proposed=(architecture,))
    assessed = next(a for a in report.proposed_architectures
                    if a.architecture_id == "A_AGENT_PAIR")
    assert assessed.logical is LogicalStatus.TARGET_REACHABLE
    assert assessed.per_model, "a proposal gets the same per-model judgement as any architecture"


def test_a_result_carried_only_by_a_proposed_architecture_still_validates():
    """Regression: the report's own validator must look at both lists.

    When the search is too narrow to find a composition but an agent proposes it, the result is
    driven by the proposed architecture. A validator that inspected only the enumerated list made
    the compiler raise instead of reporting — failing in the one case the proposal path exists for.
    """
    problem, blocks = T.two_needed()
    architecture = _gated_architecture({
        "architecture_id": "A_AGENT_PAIR", "family": "pair",
        "composition": [["B_A", "B_B"]], "composition_mode": "simultaneous",
        "origin": "synthetic_composition", "rationale": "the pair a starved search cannot reach",
        "assumptions": ["they act together"]})
    report = run(problem, blocks, proposed=(architecture,), max_depth=1, max_per_step=1)
    assert not report.architectures, "the starved search must find nothing on its own"
    assert report.result.value == "ARCHITECTURE_SYNTHESIZED"
    assert [a.clear for a in report.proposed_architectures] == [True]


def test_the_compiler_contradicts_a_proposers_own_framing_with_evidence():
    """An agent may call its composition sequential; whether the order matters is not its call."""
    problem, blocks = T.two_needed()
    architecture = _gated_architecture({
        "architecture_id": "A_AGENT_STAGED", "family": "pair",
        "composition": [["B_A"], ["B_B"]], "composition_mode": "sequential",
        "origin": "synthetic_composition", "rationale": "apply one and then the other",
        "assumptions": ["staging matters"]})
    assessed = next(a for a in run(problem, blocks, proposed=(architecture,))
                    .proposed_architectures if a.architecture_id == "A_AGENT_STAGED")
    assert assessed.works_in
    assert not assessed.order_is_load_bearing
    assert "not load-bearing" in assessed.order_note


def test_an_architecture_naming_an_unregistered_component_is_refused_before_compiling():
    problem, blocks = T.two_needed()
    architecture = _gated_architecture({
        "architecture_id": "A_AGENT_GHOST", "family": "ghost",
        "composition": [["B_DOES_NOT_EXIST"]], "composition_mode": "simultaneous",
        "origin": "synthetic_composition", "rationale": "names a component nobody declared",
        "assumptions": ["none"]})
    with pytest.raises(ValidationError, match="unregistered components"):
        run(problem, blocks, proposed=(architecture,))
