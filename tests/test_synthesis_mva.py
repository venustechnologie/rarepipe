"""The MVA case compiled as a synthesis problem, including proof gate 11.

Gate 11 asks for at least one architecture family that is structurally distinct from the two
transformations the control compiler already represented. It is satisfied by finding a genuinely
distinct, formally expressible architecture — not by showing one is biologically feasible, which
nothing here claims.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from rarepipe.stages.control.controls import Feasibility
from rarepipe.stages.control.synthesis import mva_synthesis
from rarepipe.stages.control.synthesis.compiler import compile_synthesis
from rarepipe.stages.control.synthesis.kinds import (
    ArchitectureOrigin, FamilyVerdict, LogicalStatus, PhysicalStatus, RobustnessClass,
    StabilityClass, SynthesisResultClass,
)

KNOWN_ROUTES = {"BB_ABUNDANCE_STABILIZATION", "BB_FUNCTION_REPLACEMENT"}


@pytest.fixture(scope="module")
def report():
    return compile_synthesis(mva_synthesis.problem())


def verdict(report, family_id):
    return next(f for f in report.families if f.family_id == family_id).verdict


# ---------------------------------------------------------------- Gate 11

def test_gate11_produces_an_architecture_structurally_distinct_from_both_known_routes(report):
    distinct = [a for a in report.architectures
                if a.works_in and not (set(a.components) & KNOWN_ROUTES)]
    assert distinct, "the whole point of this phase is that the search is not closed around BubR1"
    for architecture in distinct:
        moved = {t.variable for b in architecture.components
                 for t in mva_synthesis.registry().get(b).state_transformations}
        assert not moved & {"bubr1_abundance", "bubr1_function"}, \
            f"{architecture.architecture_id} still acts on BubR1, so it is not a distinct family"


def test_gate11_the_distinct_routes_do_not_depend_on_the_unresolved_relationship(report):
    distinct = [a for a in report.architectures
                if a.works_in and not (set(a.components) & KNOWN_ROUTES)]
    for architecture in distinct:
        assert "REL_BUBR1_ABUNDANCE_FUNCTION" not in architecture.blocking_relationships
        assert architecture.robustness is RobustnessClass.ROBUST_CONTROL_CANDIDATE


def test_gate11_distinctness_is_not_a_feasibility_claim(report):
    assert all(b["feasibility"] == Feasibility.UNASSESSED.value for b in report.building_blocks), \
        "nothing in this registry has been shown to work; the gate is about expressibility"
    assert report.result is SynthesisResultClass.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN
    for architecture in report.architectures:
        assert architecture.physical is not PhysicalStatus.PHYSICALLY_FEASIBLE


# ---------------------------------------------------------------- the families

def test_both_original_routes_are_retained_as_families(report):
    assert verdict(report, "F01_RESTORE_BUBR1_ABUNDANCE") is FamilyVerdict.CONDITIONALLY_SUPPORTED
    assert verdict(report, "F02_REPLACE_BUBR1_FUNCTION") is FamilyVerdict.CONDITIONALLY_SUPPORTED


def test_the_abundance_route_is_still_blocked_by_the_same_unknown(report):
    abundance = next(a for a in report.architectures
                     if a.components == ("BB_ABUNDANCE_STABILIZATION",) and not a.feedback_policy)
    assert abundance.logical is LogicalStatus.REACHABLE_UNDER_SOME_MODELS
    assert abundance.blocking_relationships == ("REL_BUBR1_ABUNDANCE_FUNCTION",)
    assert abundance.robustness is RobustnessClass.MODEL_SPECIFIC_CONTROL


def test_a_bypass_says_which_relationships_it_overrides_and_how_well_supported_they_are(report):
    bypass = next(a for a in report.architectures
                  if a.components == ("BB_CHECKPOINT_BYPASS_CIRCUIT",))
    assert bypass.origin is ArchitectureOrigin.NATURAL_BYPASS
    assert "REL_FUNCTION_ACTIVATION (established)" in bypass.overrides_relationships
    assert any("contradicts the best supported part of the model" in n for n in bypass.notes), \
        "overriding an established relationship is a larger claim than filling a gap"


def test_lowering_the_error_rate_alone_does_not_satisfy_a_checkpoint_target(report):
    assert verdict(report, "F05_REDUCE_SEGREGATION_ERRORS") is FamilyVerdict.UNSUPPORTED
    assert not [a for a in report.architectures
                if a.components == ("BB_MISSEGREGATION_SUPPRESSION",) and a.works_in]


def test_selecting_against_the_aneuploid_cells_is_refused_on_safety(report):
    selection = next(a for a in report.architectures
                     if a.components == ("BB_ANEUPLOID_SELECTION",))
    assert selection.logical is LogicalStatus.UNSAFE
    assert not selection.works_in and selection.unsafe_in
    assert selection.unsafe_path[-1]["cell_death"] == "increased"
    assert verdict(report, "F06_POPULATION_STATE_CONTROL") is FamilyVerdict.UNSUPPORTED


def test_a_family_the_state_space_cannot_express_says_so_without_calling_it_impossible(report):
    outcome = next(f for f in report.families if f.family_id == "F07_CELL_STATE_REPLACEMENT")
    assert outcome.verdict is FamilyVerdict.NOT_REPRESENTABLE
    assert "not a claim that it is" in outcome.reason


def test_closing_the_loop_does_not_remove_the_dependence_on_the_unknown(report):
    loop = next(a for a in report.architectures if a.feedback_policy is not None)
    assert loop.feedback_policy == "PI_ABUNDANCE_SAFETY_GUARDED"
    assert loop.origin is ArchitectureOrigin.FEEDBACK_CONTROL
    assert loop.blocking_relationships == ("REL_BUBR1_ABUNDANCE_FUNCTION",), \
        "feedback changes when the control is held, not what the unknown relationship does"
    assert loop.unobservable_policy_inputs == ()
    assert verdict(report, "F08_FEEDBACK_CONTROLLED_ROUTE") is FamilyVerdict.CONDITIONALLY_SUPPORTED


def test_the_loop_does_not_claim_the_state_survives_withdrawal(report):
    loop = next(a for a in report.architectures if a.feedback_policy is not None)
    assert loop.stability is StabilityClass.MAINTAINED_TARGET
    assert "at the attractors" in loop.stability_note


def test_routes_whose_components_never_declare_a_release_report_unknown_stability(report):
    replacement = next(a for a in report.architectures
                       if a.components == ("BB_FUNCTION_REPLACEMENT",))
    assert replacement.stability is StabilityClass.UNKNOWN_STABILITY
    assert "not evaluable and is not assumed" in replacement.stability_note


# ---------------------------------------------------------------- the decomposition and experiments

def test_the_decomposition_names_what_must_become_true_not_what_to_do(report):
    assert {r.variable for r in report.required_functions.required} == {
        "checkpoint_activation", "checkpoint_silencing", "chromosome_alignment", "missegregation"}
    assert all(not r.already_satisfied for r in report.required_functions.required)
    assert report.entry_points == ("bubr1_abundance",), \
        "the only place the model lets anything act is the protein level"
    blob = report.required_functions.model_dump_json()
    assert "BB_" not in blob, "the requirements must not name components"


def test_the_measurement_that_settles_the_abundance_question_is_identified_and_measurable(report):
    settling = [d for d in report.experiment_discriminators
                if d.resolves == "REL_BUBR1_ABUNDANCE_FUNCTION" and d.measurable]
    assert settling
    assert {d.measurement for d in settling} >= {"checkpoint_activation", "chromosome_alignment"}
    assert all(d.controls_held == ("BB_ABUNDANCE_STABILIZATION::bubr1_abundance",)
               for d in settling)
    assert all(d.criterion == "deterministic_elimination" for d in settling)


def test_a_reading_nobody_can_take_is_reported_as_a_gap_not_as_an_experiment(report):
    latent = [d for d in report.experiment_discriminators if not d.measurable]
    assert latent, "the latent function variable would settle it and nothing measures it"
    assert all("gap in" in d.note or "No available experiment measures" in d.note
               for d in latent)
    measurable_first = [d.measurable for d in report.experiment_discriminators]
    assert measurable_first == sorted(measurable_first, reverse=True)


def test_the_aneuploidy_confound_is_satisfied_because_cell_death_is_measured(report):
    assert not report.confounder_gaps, \
        "the case's experiments measure cell death and viability, which is what excludes it"


# ---------------------------------------------------------------- governance and reproducibility

_CASE_PATTERNS = (r"\bc\.\d", r"\bp\.[A-Z][a-z]{2}\d", r"\bchr[0-9XYM]", r"\brs\d{3,}",
                  r"\bg\.\d{4,}", r"\b[ACGT]{8,}\b")


def test_no_case_level_genomic_content_reaches_the_mva_synthesis_report(report):
    blob = report.model_dump_json()
    for pattern in _CASE_PATTERNS:
        assert not re.search(pattern, blob), f"{pattern} matched in the MVA synthesis report"


def test_the_report_carries_no_recommendation_and_states_so(report):
    assert "no treatment recommendation" in report.no_treatment_recommendation
    assert report.target_accountability == "PROPOSED_UNAPPROVED"


def test_the_mva_synthesis_digest_is_stable_across_hash_seeds():
    script = ("from rarepipe.stages.control.synthesis import mva_synthesis\n"
              "from rarepipe.stages.control.synthesis.compiler import compile_synthesis\n"
              "print(compile_synthesis(mva_synthesis.problem()).content_digest)\n")
    digests = set()
    for seed in ("0", "7", "99991"):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                                  "PYTHONPATH": "src:."}, cwd="/Users/venus/Desktop/rarepipe")
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    assert len(digests) == 1, f"the MVA synthesis digest moved with the hash seed: {digests}"


def test_the_committed_architecture_map_is_not_stale(report):
    from pathlib import Path

    from rarepipe.stages.control.synthesis.report import render
    committed = (Path(__file__).resolve().parents[1]
                 / "docs/control/MVA_ARCHITECTURE_MAP.md").read_text()
    assert committed == render(report), (
        "docs/control/MVA_ARCHITECTURE_MAP.md is stale: run "
        "uv run python tools/control/compile_mva_synthesis.py")


def test_the_map_never_presents_an_unbuilt_route_as_available(report):
    from pathlib import Path

    committed = (Path(__file__).resolve().parents[1]
                 / "docs/control/MVA_ARCHITECTURE_MAP.md").read_text()
    assert "no treatment recommendation" in committed
    assert "LOGICALLY_SYNTHESIZABLE means" in committed
    # Every architecture row must carry its buildability verdict beside its reachability verdict.
    rows = [line for line in committed.splitlines()
            if line.startswith("| `BB_") and "TARGET_REACHABLE" in line]
    assert rows
    assert all("unknown" in row or "**yes**" in row or "no" in row for row in rows)
