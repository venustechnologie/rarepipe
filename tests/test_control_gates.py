"""Proof gates A-H for the Biological State Control Compiler.

These are judged by whether the compiler distinguishes what is controllable, observable, unsafe and
unknown — not by how many agents, simulations or hypotheses it produces.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from control_toys import control, model, problem, rel, start_at, var  # noqa: E402

from rarepipe.stages.control.compiler import compile_problem  # noqa: E402
from rarepipe.stages.control.dynamics import Plausibility  # noqa: E402
from rarepipe.stages.control.observability import ObservationModel, indistinguishable  # noqa: E402
from rarepipe.stages.control.result_types import SOLUTION_CLASSES, ResultClass  # noqa: E402
from rarepipe.stages.control.state_space import StateSpace  # noqa: E402

AND = lambda *xs: "1" if all(x == "1" for x in xs) else "0"  # noqa: E731
ID = lambda x: x  # noqa: E731


# ── Gate A — formal state compilation ────────────────────────────────────────────────────────

def test_gate_a_the_mva_case_compiles_without_inventing_values():
    from rarepipe.stages.control.mva import problem as mva_problem
    from rarepipe.stages.control.provenance import ApprovalStatus

    p = mva_problem()
    # Every value is a named category; nothing qualitative was turned into a number.
    for v in p.space.variables:
        assert all(not value.replace(".", "").isdigit() for value in v.domain), v.name
    # The decisive relationship is still unknown.
    rel_ = next(r for r in p.models[0].relationships
                if r.relationship_id == "REL_BUBR1_ABUNDANCE_FUNCTION")
    assert rel_.kind.value == "unknown_function"
    # The target is functional success and does not prescribe a mechanism.
    assert "bubr1_abundance" not in p.target.variables()
    # Nothing is approved, because no accountable scientist exists for this case.
    assert all(c.approval.status is ApprovalStatus.PROPOSED for c in p.target.constraints)
    report = compile_problem(p)
    assert report.target_accountability == "PROPOSED_UNAPPROVED"


# ── Gate B — known-unknown detection ─────────────────────────────────────────────────────────

def test_gate_b_a_removed_relationship_is_a_blocker_not_a_constant():
    """Delete the relationship defining a variable the target depends on. Treating that variable
    as a constant would silently fill the gap; the compiler must name it and stop."""
    full = [rel("R_b", ("a",), "b", ID), rel("R_t", ("b",), "t", ID)]
    p = problem([var("a", True), var("b"), var("t")], [model([full[1]])], [control("u", "a")],
                target_on=[("t", "1")], evidence=start_at(a="0"))
    report = compile_problem(p)
    assert report.result is ResultClass.CONTROL_INDETERMINATE
    assert any("missing_relationship:b" in b for b in report.blocking_relationships)
    assert report.control_strategy_candidates == ()


def test_gate_b_an_unknown_function_on_the_route_is_named():
    p = problem([var("a", True), var("b"), var("t")],
                [model([rel("R_b", ("a",), "b", unknown=True), rel("R_t", ("b",), "t", ID)])],
                [control("u", "a")], target_on=[("t", "1")], evidence=start_at(a="0", t="0"))
    report = compile_problem(p)
    assert report.result is ResultClass.CONTROL_INDETERMINATE
    assert "R_b" in report.blocking_relationships
    assert report.result not in SOLUTION_CLASSES


# ── Gate C — reachability on a network with a known solution ─────────────────────────────────

def test_gate_c_finds_the_known_path():
    p = problem([var("a", True), var("b", True), var("x"), var("t")],
                [model([rel("R_x", ("a",), "x", ID), rel("R_t", ("x", "b"), "t", AND)])],
                [control("ua", "a"), control("ub", "b")],
                target_on=[("t", "1")], evidence=start_at(a="0", b="0"))
    report = compile_problem(p)
    assert report.result is ResultClass.CONTROL_SOLUTION_CANDIDATE
    best = report.control_strategy_candidates[0].assessment
    assert set(best.controls) == {"ua", "ub"}


# ── Gate D — safety ──────────────────────────────────────────────────────────────────────────

def test_gate_d_the_shorter_unsafe_path_is_rejected_for_the_longer_safe_one():
    """u1 alone reaches the target in one control but passes through death=1. u2 and u3 together
    reach it safely. The one-control route must be rejected and reported as rejected."""
    p = problem([var("a", True), var("b", True), var("c", True), var("t"), var("death")],
                [model([rel("R_t", ("a", "b", "c"), "t",
                            lambda a, b, c: "1" if a == "1" or (b == "1" and c == "1") else "0"),
                        rel("R_death", ("a",), "death", ID)])],
                [control("u1", "a"), control("u2", "b"), control("u3", "c")],
                target_on=[("t", "1")], unsafe_on=[("death", "1")],
                evidence=start_at(a="0", b="0", c="0"))
    report = compile_problem(p)
    assert report.result is ResultClass.CONTROL_SOLUTION_CANDIDATE
    assert set(report.control_strategy_candidates[0].assessment.controls) == {"u2", "u3"}
    rejected = [r["strategy"] for r in report.unsafe_trajectories_rejected]
    assert [["u1"]] in rejected
    witness = next(r for r in report.unsafe_trajectories_rejected if r["strategy"] == [["u1"]])
    assert witness["violates"] == ["S_death"]


# ── Gate E — model disagreement ──────────────────────────────────────────────────────────────

def test_gate_e_disagreeing_models_do_not_produce_success():
    m1 = model([rel("R_t", ("a",), "t", ID)], "M1_u_reaches_target")
    m2 = model([rel("R_t", ("a",), "t", lambda a: "0")], "M2_u_does_not",
               plausibility=Plausibility.PLAUSIBLE_ALTERNATIVE)
    p = problem([var("a", True), var("t")], [m1, m2], [control("u", "a")],
                target_on=[("t", "1")], evidence=start_at(a="0", t="0"))
    report = compile_problem(p)
    assert report.result in {ResultClass.MODEL_DISAGREEMENT, ResultClass.CONTROL_INDETERMINATE}
    assert report.result not in SOLUTION_CLASSES
    assert report.model_disagreements


# ── Gate F — observability ───────────────────────────────────────────────────────────────────

def test_gate_f_indistinguishable_internal_states_are_detected():
    space = StateSpace(variables=(var("latent", latent=True), var("readout")))
    obs = ObservationModel(name="Y", observed=("readout",),
                           provenance=__import__("control_toys").prov(
                               __import__("rarepipe.stages.control.provenance",
                                          fromlist=["EpistemicType"]).EpistemicType.DECISION_RULE),
                           generated_under="toy")
    states = (("0", "1"), ("1", "1"))
    pairs = indistinguishable(space, states, obs, label=lambda s: s[0])
    assert pairs == ((("0", "1"), ("1", "1")),)


def test_gate_f_a_target_defined_on_an_unmeasured_variable_is_not_verifiable():
    p = problem([var("a", True), var("hidden", latent=True), var("t")],
                [model([rel("R_h", ("a",), "hidden", ID), rel("R_t", ("hidden",), "t", ID)])],
                [control("u", "a")], target_on=[("hidden", "1")],
                evidence=start_at(a="0"), observed=("a", "t"))
    report = compile_problem(p)
    assert report.result is ResultClass.OBSERVABILITY_INSUFFICIENT
    assert any("hidden" in u for u in report.unobservable_states)


def test_gate_f_safety_cannot_be_certified_by_a_prediction():
    """The model never moves `death`, but it is not measured: safety is unverifiable."""
    p = problem([var("a", True), var("t"), var("death", True)],
                [model([rel("R_t", ("a",), "t", ID)])], [control("u", "a")],
                target_on=[("t", "1")], unsafe_on=[("death", "1")],
                evidence=start_at(a="0", death="0"), observed=("a", "t"))
    report = compile_problem(p)
    assert report.result is ResultClass.OBSERVABILITY_INSUFFICIENT
    assert any("death" in u and "cannot be certified" in u for u in report.unobservable_states)


# ── Gate G — experiment compilation ──────────────────────────────────────────────────────────

def test_gate_g_names_the_measurement_that_separates_two_models():
    p = problem([var("a", True), var("x"), var("t")],
                [model([rel("R_x", ("a",), "x", unknown=True), rel("R_t", ("x",), "t", ID)])],
                [control("u", "a")], target_on=[("t", "1")], evidence=start_at(a="0", x="0", t="0"))
    report = compile_problem(p)
    measured = {(m.resolves, m.controls_held, m.variable) for m in report.required_measurements}
    assert ("R_x", ("u",), "x") in measured
    assert ("R_x", ("u",), "t") in measured


# ── Gate H — the real MVA case ───────────────────────────────────────────────────────────────

def test_gate_h_the_real_case_produces_an_intelligible_control_map():
    from rarepipe.stages.control.mva import problem as mva_problem

    report = compile_problem(mva_problem())

    # What is unknown, and that it blocks the abundance route specifically.
    assert report.result is ResultClass.CONTROL_INDETERMINATE
    assert "REL_BUBR1_ABUNDANCE_FUNCTION" in report.blocking_relationships
    by_controls = {s.assessment.strategy: s.assessment for s in report.control_strategy_candidates}
    abundance = by_controls[(("C_RESTORE_ABUNDANCE",),)]
    assert abundance.blocking_relationships == ("REL_BUBR1_ABUNDANCE_FUNCTION",)
    assert [w.split("=")[-1] for w in abundance.works_in] == ["H01"]

    # A route that does not depend on the unknown at all — blocked only by feasibility.
    replacement = by_controls[(("C_REPLACE_FUNCTION",),)]
    assert replacement.robust
    assert replacement.blocking_relationships == ()
    assert replacement.feasibility_blockers == ("control_feasibility:C_REPLACE_FUNCTION",)

    # The diagnosis rules out the biology in which the child would not have MVA.
    assert [e.variant_id.split("=")[-1] for e in report.excluded_models] == ["unnamed_1"]

    # Which measurement would change controllability, and which experiments carry it.
    measured = {(m.controls_held, m.variable) for m in report.required_measurements}
    assert (("C_RESTORE_ABUNDANCE",), "checkpoint_activation") in measured
    contributions = {c.experiment_id: c for c in report.experiment_contributions}
    assert "REL_BUBR1_ABUNDANCE_FUNCTION" in contributions["EXP01"].resolves
    assert contributions["EXP01"].conditional_on == ""
    assert contributions["EXP02"].premise_observable is True

    # EXP03 fails closed and the choice is left to a scientist.
    exp03 = contributions["EXP03"]
    assert exp03.fails_closed
    assert set(exp03.attribution_missing) == {"sirt2_activity", "k668_acetylation"}
    assert len(exp03.options_for_the_scientific_lead) == 3

    # What is forbidden, and that the target is not approved.
    assert {r["constraint"] for r in report.unsafe_region} == {"S_CELL_DEATH", "S_VIABILITY",
                                                                "S_DIVISION"}
    assert ResultClass.TARGET_SPECIFICATION_INCOMPLETE in report.secondary_results

    # The model registry refuses the downstream SAC import.
    assert [(a.model_id, a.admitted) for a in report.model_admissions] == [
        ("BIOMODELS_SAC_KINETIC_CLASS", False)]

    # And nothing quantitative was invented to get here.
    blob = json.dumps(report.model_dump(mode="json"))
    assert "mg" not in blob.split('"known_omissions"')[0].lower().split()


# ── Adversarial cases for defects the design anticipated ─────────────────────────────────────

def test_an_unknown_is_fixed_for_a_whole_trajectory_not_chosen_per_step():
    """If the search could choose an unknown function's output afresh at each step, it could
    'reach' targets no single biology supports. With the input held, the output is one value."""
    from rarepipe.stages.control.reachability import compile_variant, explore
    from rarepipe.stages.control.uncertainty import expand

    p = problem([var("a", True), var("b"), var("t")],
                [model([rel("R_b", ("a",), "b", unknown=True), rel("R_t", ("b",), "t", ID)])],
                [control("u", "a")], target_on=[("t", "1")])
    for variant in expand(p.space, p.models[0]):
        c = compile_variant(p.space, variant)
        ex = explore(c, ("1", "0", "0"), frozenset({0}), lambda s: False)
        assert len({s[1] for s in ex.attractors}) == 1, variant.variant_id


def test_evidence_that_contradicts_every_model_never_yields_success():
    """'Works for every initial state' is vacuously true of an empty set."""
    p = problem([var("a", True), var("t")], [model([rel("R_t", ("a",), "t", ID)])],
                [control("u", "a")], target_on=[("t", "1")],
                evidence=start_at(a="0", t="1"))  # t = a is violated at a=0
    report = compile_problem(p)
    assert report.result is ResultClass.CONTROL_INDETERMINATE
    assert report.blocking_relationships == ("no_model_variant_consistent_with_evidence",)


def test_an_unknown_off_the_route_is_irrelevant_not_blocking():
    """Reporting every unknown as a blocker would hide the real one in noise."""
    p = problem([var("a", True), var("t"), var("side")],
                [model([rel("R_t", ("a",), "t", ID), rel("R_side", ("a",), "side", unknown=True)])],
                [control("u", "a")], target_on=[("t", "1")], evidence=start_at(a="0"))
    report = compile_problem(p)
    assert "R_side" not in report.blocking_relationships
    assert "R_side" in report.irrelevant_unknowns
    assert report.result is ResultClass.ROBUST_CONTROL_SOLUTION_CANDIDATE


def test_a_reading_an_omitted_cause_could_fake_is_not_a_clean_discriminator():
    """B17/B18 generalised to experiment design.

    total_aneuploidy separates H01 from H02 in the model only because nothing in the model moves
    cell death. Its relationship takes cell_death as an input, so selective loss of aneuploid cells
    would produce the same fall. The measurement must say it is valid only alongside cell death,
    and an experiment that measured aneuploidy without death would not resolve anything with it.
    """
    from rarepipe.stages.control.mva import problem as mva_problem

    report = compile_problem(mva_problem())
    by_var = {m.variable: m for m in report.required_measurements}
    assert by_var["total_aneuploidy"].confounded_by == ("cell_death",)
    assert by_var["checkpoint_activation"].confounded_by == ()

    # An experiment that measures aneuploidy but not death gets no credit for it.
    from rarepipe.stages.control.compiler import ExperimentSpec
    from rarepipe.stages.control.mva import observation
    p = mva_problem()
    blind = ExperimentSpec(experiment_id="ANEUPLOIDY_ONLY", controls_held=("C_RESTORE_ABUNDANCE",),
                           observation=observation("ANEUPLOIDY_ONLY", ("total_aneuploidy",)),
                           interpretation="counts aneuploid cells and nothing else")
    p2 = p.model_validate({**p.model_dump(), "experiments": [blind.model_dump()]})
    contribution = compile_problem(p2).experiment_contributions[0]
    assert contribution.resolves == ()


def test_the_committed_control_map_is_current():
    """The map is generated. If the compiler or the case changes, regenerate it rather than edit it."""
    from rarepipe.stages.control.mva import problem as mva_problem
    from rarepipe.stages.control.render import render

    committed = (Path(__file__).resolve().parents[1] / "docs/control/MVA_CONTROL_MAP.md").read_text()
    assert committed == render(compile_problem(mva_problem())), (
        "docs/control/MVA_CONTROL_MAP.md is stale: run uv run python tools/control/compile_mva.py")
