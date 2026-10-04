"""Proof gates for the synthesis compiler. Each one would fail if the property it names were absent.

A gate that passes on the first run proves little, so the properties behind these are also mutation
tested: break the property deliberately and the matching gate must go red.
"""
from __future__ import annotations

import pytest

from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.synthesis.compiler import compile_synthesis
from rarepipe.stages.control.synthesis.kinds import (
    ArchitectureOrigin, FamilyVerdict, LogicalStatus, PhysicalStatus, RobustnessClass,
    StabilityClass, SynthesisResultClass, TransformationScale,
)
from tests import synthesis_toys as T


def run(problem, blocks, **kw):
    return compile_synthesis(T.synthesis(problem, blocks, **kw))


def clear_ones(report):
    return [a for a in report.architectures if a.clear]


# ---------------------------------------------------------------- Gate 1: direct repair

def test_gate1_synthesizes_repair_when_repair_is_the_only_route():
    report = run(*T.repair_only())
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
    clear = clear_ones(report)
    assert clear, "repair is available, established and sufficient; something must be synthesized"
    assert all(a.components == ("B_REPAIR",) for a in clear)
    assert clear[0].origin is ArchitectureOrigin.NATURAL_PATHWAY
    assert clear[0].logical is LogicalStatus.TARGET_REACHABLE
    assert clear[0].physical is PhysicalStatus.PHYSICALLY_FEASIBLE


def test_gate1_decomposition_names_the_entry_point_without_naming_an_intervention():
    report = run(*T.repair_only())
    requirement = report.required_functions.required[0]
    assert requirement.variable == "func" and requirement.must_enter == ("1",)
    assert not requirement.already_satisfied
    assert requirement.entry_points == ("lesion",)
    assert "B_REPAIR" not in report.required_functions.note


# ---------------------------------------------------------------- Gate 2: bypass

def test_gate2_synthesizes_a_bypass_when_the_damaged_node_cannot_be_touched():
    report = run(*T.bypass())
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
    clear = clear_ones(report)
    assert [a.components for a in clear] == [("B_ALT",)]
    assert clear[0].origin is ArchitectureOrigin.NATURAL_BYPASS
    # The lesion is still an entry point for the upstream requirement, and nothing acts on it.
    assert "lesion" in report.required_functions.required[0].causal_ancestors


# ---------------------------------------------------------------- Gate 3: composition

def test_gate3_finds_the_pair_when_no_single_component_is_enough():
    report = run(*T.two_needed())
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
    clear = clear_ones(report)
    assert clear
    assert all(set(a.components) == {"B_A", "B_B"} for a in clear), \
        "one component can never reach this target; a single-component architecture would be wrong"
    assert any(a.composition == (("B_A", "B_B"),) for a in clear)


# ---------------------------------------------------------------- Gate 4: unsafe shortcut

def test_gate4_rejects_the_route_that_reaches_the_reading_by_killing_the_cells():
    report = run(*T.unsafe_shortcut())
    by_id = {a.architecture_id: a for a in report.architectures}
    killers = [a for a in by_id.values() if "B_KILL" in a.components]
    assert killers, "the unsafe route must appear in the report, so the rejection is visible"
    assert all(a.unsafe_in and not a.clear for a in killers)
    assert all(a.logical is LogicalStatus.UNSAFE for a in killers if a.components == ("B_KILL",))
    fixers = [a for a in by_id.values() if a.components == ("B_FIX",)]
    assert fixers and fixers[0].clear
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
    # Safety is a filter, not a term that a big enough benefit could outweigh.
    assert report.architectures[0].clear


def test_gate4_the_unsafe_path_is_recorded_not_merely_flagged():
    report = run(*T.unsafe_shortcut())
    killer = next(a for a in report.architectures if a.components == ("B_KILL",))
    assert killer.unsafe_path, "a rejection nobody can inspect is not reviewable"
    assert killer.unsafe_path[-1]["dead"] == "increased"


# ---------------------------------------------------------------- Gate 5: population solution

def test_gate5_reaches_a_population_level_function_without_correcting_any_cell():
    problem, blocks, population = T.population_rescue()
    report = run(problem, blocks, population=population)
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
    architecture = clear_ones(report)[0]
    assert architecture.origin is ArchitectureOrigin.POPULATION_CONTROL
    assert architecture.scales == (TransformationScale.POPULATION,)
    assert "No cell is corrected" in architecture.rescue_scope
    assert "not evidence of cellular rescue" in report.rescue_scope_statement


def test_gate5_a_population_effect_with_no_stated_differential_is_flagged():
    problem, blocks, population = T.population_rescue(declare_mechanism=False)
    report = run(problem, blocks, population=population)
    architecture = next(a for a in report.architectures if a.works_in)
    assert architecture.undeclared_population_mechanisms == ("functional_fraction",), \
        "a population change with no mechanism saying what makes it selective is a wish"


def test_gate5_cell_function_is_untouched_in_the_decomposition():
    problem, blocks, population = T.population_rescue()
    report = run(problem, blocks, population=population)
    requirement = report.required_functions.required[0]
    assert requirement.scale is TransformationScale.POPULATION
    assert "cell_function" in requirement.causal_ancestors


# ---------------------------------------------------------------- Gate 6: confounded population

def test_gate6_detects_that_the_population_reading_could_be_selective_death():
    problem, blocks, population = T.population_rescue(confounder=True)
    report = run(problem, blocks, population=population)
    assert report.result is SynthesisResultClass.ARCHITECTURE_OBSERVABILITY_INSUFFICIENT
    assert report.confounder_gaps
    gap = report.confounder_gaps[0]
    assert gap.process_id == "P_SELECTIVE_DEATH"
    assert gap.missing_observables == ("apoptosis_marker",)
    assert not clear_ones(report), "an unexcludable confounder cannot leave an architecture clear"


def test_gate6_measuring_the_confounder_restores_the_result():
    problem, blocks, population = T.population_rescue(confounder=True, observe_marker=True)
    report = run(problem, blocks, population=population)
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
    assert not report.confounder_gaps


# ---------------------------------------------------------------- Gate 7: temporal sequence

def test_gate7_preserves_the_order_that_works_and_rejects_the_one_that_does_not():
    report = run(*T.order_matters())
    working = {a.composition for a in report.architectures if a.works_in}
    assert (("B_A",), ("B_C",)) in working
    assert (("B_C",), ("B_A",)) not in working
    assert (("B_A", "B_C"),) not in working, "applying both at once closes the window"


def test_gate7_reports_the_order_as_load_bearing_with_the_evidence_for_it():
    report = run(*T.order_matters())
    winner = next(a for a in report.architectures
                  if a.composition == (("B_A",), ("B_C",)))
    assert winner.order_is_load_bearing
    assert "all components at once" in winner.order_note


def test_gate7_a_single_step_architecture_does_not_claim_a_load_bearing_order():
    report = run(*T.repair_only())
    assert all(not a.order_is_load_bearing for a in report.architectures)


# ---------------------------------------------------------------- Gate 8: feedback

def test_gate8_static_intervention_fails_where_the_loop_maintains_the_target():
    problem, blocks, loop = T.feedback_needed()
    static = run(problem, blocks)
    assert not [a for a in static.architectures if a.works_in], \
        "holding the push settles outside the target; a static strategy cannot release it"

    closed = run(problem, blocks, policies=(loop,))
    maintained = [a for a in closed.architectures if a.feedback_policy == "PI_HOLD_OK"]
    assert maintained and maintained[0].works_in
    assert maintained[0].origin is ArchitectureOrigin.FEEDBACK_CONTROL
    assert maintained[0].stability in {StabilityClass.MAINTAINED_TARGET,
                                       StabilityClass.SELF_STABILIZING_TARGET}


def test_gate8_a_policy_keyed_on_an_unmeasured_variable_is_refused():
    problem, blocks, _ = T.feedback_needed()
    blind = T.policy("PI_BLIND", ("m", "1", T.ACTIVATE, "B_PUSH::u"))
    narrowed = problem.model_copy(update={
        "observation": problem.observation.model_copy(update={"observed": ("u", "x")})})
    report = run(narrowed, blocks, policies=(blind,))
    policy_architecture = next(a for a in report.architectures if a.feedback_policy == "PI_BLIND")
    assert policy_architecture.unobservable_policy_inputs == ("m",)
    assert not policy_architecture.works_in, "a controller keyed on an unmeasured variable is not a controller"


def test_gate8_releasing_a_control_that_never_said_what_reverts_is_refused():
    problem, blocks, _ = T.feedback_needed()
    irreversible = [T.block("B_PUSH", T.tf("u", "on"))]
    loop = T.policy("PI_RELEASE", ("x", "high", T.DEACTIVATE, "B_PUSH::u"))
    report = run(problem, irreversible, policies=(loop,))
    architecture = next(a for a in report.architectures if a.feedback_policy == "PI_RELEASE")
    assert architecture.missing_release_declarations == ("B_PUSH::u",)
    assert not architecture.works_in


# ---------------------------------------------------------------- Gate 9: model disagreement

def test_gate9_returns_the_disagreement_rather_than_the_favourable_half():
    report = run(*T.disagreeing_models())
    assert report.result is SynthesisResultClass.ARCHITECTURE_MODEL_DISAGREEMENT
    architecture = next(a for a in report.architectures if a.components == ("B_A",))
    assert architecture.robustness is RobustnessClass.MODEL_DISAGREEMENT
    assert not architecture.clear
    assert dict(architecture.per_model) == {"M_RESPONSIVE": "ALL", "M_UNRESPONSIVE": "NONE"}


# ---------------------------------------------------------------- Gate 10: missing actuator

def test_gate10_separates_a_logical_solution_from_a_feasible_intervention():
    report = run(*T.repair_only(feasibility=Feasibility.UNASSESSED))
    assert report.result is SynthesisResultClass.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN
    architecture = next(a for a in report.architectures if a.works_in)
    assert architecture.logically_synthesizable
    assert not architecture.physically_feasible
    assert architecture.physical is PhysicalStatus.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN
    assert architecture.feasibility_blockers == ("B_REPAIR",)
    assert architecture.robustness is RobustnessClass.ROBUST_CONTROL_CANDIDATE, \
        "the biology is settled here; only the implementation is not"


def test_gate10_an_infeasible_component_is_not_composed_at_all():
    report = run(*T.repair_only(feasibility=Feasibility.INFEASIBLE))
    assert report.result is SynthesisResultClass.NO_ARCHITECTURE_SYNTHESIZED
    assert not report.architectures


# ---------------------------------------------------------------- Gate 12: no invented path

def test_gate12_a_removed_relationship_produces_a_blocker_not_a_path():
    report = run(*T.repair_only(drop_relationship=True))
    assert report.result is SynthesisResultClass.ARCHITECTURE_INDETERMINATE
    assert any("missing_relationship:func" in m for m in report.missing_relationships)
    assert not report.architectures, "with the relationship gone there is no path to compose"


def test_gate12_the_search_fails_closed_rather_than_truncating():
    from rarepipe.stages.control.synthesis.search import TooBroadToSynthesize, enumerate_compositions
    with pytest.raises(TooBroadToSynthesize):
        enumerate_compositions([f"B{i}" for i in range(40)], 4, 4)


# ---------------------------------------------------------------- families (PRD section 31)

def test_a_family_with_no_registered_component_is_unknown_not_unsupported():
    from rarepipe.stages.control.synthesis.compiler import FamilySpec
    problem, blocks = T.repair_only()
    family = FamilySpec(family_id="F_POPULATION", description="replace the cell population",
                        requires_scale=TransformationScale.POPULATION,
                        rationale="asked for explicitly, whether or not anything implements it")
    report = run(problem, blocks, families=(family,))
    outcome = next(f for f in report.families if f.family_id == "F_POPULATION")
    assert outcome.verdict is FamilyVerdict.NOT_REPRESENTABLE
    assert "not a claim that it is" in outcome.reason


def test_gate4_rejects_harm_that_appears_downstream_of_the_component():
    """The component sets nothing unsafe; the relationships it triggers do.

    Separate from the shortcut gate: there the unsafe value is pinned by the control and is already
    present in the first state, so the initial check catches it. Here only the per-successor check
    can, and without it the architecture would be reported as a clean route.
    """
    report = run(*T.unsafe_downstream())
    pusher = next(a for a in report.architectures if a.components == ("B_PUSH",))
    assert pusher.unsafe_in and not pusher.clear
    assert pusher.unsafe_path[-1]["toxicity"] == "high"
    assert pusher.unsafe_path[0]["toxicity"] == "baseline", \
        "the harm must arise during the trajectory, or this gate duplicates the shortcut gate"
    safe = next(a for a in report.architectures if a.components == ("B_SAFE",))
    assert safe.clear
    assert report.result is SynthesisResultClass.ARCHITECTURE_SYNTHESIZED
