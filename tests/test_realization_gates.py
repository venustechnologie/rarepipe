"""Proof gates for the physical-realization compiler.

The frontier this phase has to cross is `abstract function -> real mechanism -> real physical piece`.
Each gate below would pass if the property it names were absent, so each is also mutation tested:
the property is broken deliberately and the gate has to go red.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from rarepipe.stages.control.realization import mva_realization
from rarepipe.stages.control.realization.compiler import compile_realization
from rarepipe.stages.control.realization.evidence import (
    Unentitled, entitle, inventory_from_repo,
)
from rarepipe.stages.control.realization.kinds import (
    Entitlement, EpistemicBurden, RealizationResult,
)
from rarepipe.stages.control.realization.primitives import UnknownPrimitive
from rarepipe.stages.simulate.chain import Support
from tests import realization_toys as T


def run(problem):
    return compile_realization(problem)


def only(report):
    return report.functions[0].realizations[0]


# ---------------------------------------------------------------- Gate 1: a simple transformation

def test_gate1_a_transformation_with_a_known_mechanism_compiles_to_a_grounded_chain():
    report = run(T.grounded())
    assert report.result is RealizationResult.GROUNDED_REALIZATION_CANDIDATE
    assessment = only(report)
    assert [s.entitlement for s in assessment.steps] == [Entitlement.SUPPORTED]
    assert all(s.grounded for s in assessment.steps)
    assert not assessment.transfer_gaps
    assert not report.missing_capabilities


def test_gate1_a_grounded_chain_is_still_not_a_treatment():
    report = run(T.grounded())
    assert "no treatment recommendation" in report.no_treatment_recommendation
    assert report.origin == "simulated_prediction"


# ---------------------------------------------------------------- Gate 2: wrong direction

def test_gate2_a_component_with_the_opposite_effect_is_rejected():
    report = run(T.wrong_direction())
    assert report.result is RealizationResult.NO_GROUNDED_REALIZATION
    assessment = only(report)
    assert any(f.kind == "direction" for f in assessment.findings)
    assert "implies decrease" in " ".join(f.detail for f in assessment.findings)


def test_gate2_the_direction_check_reads_the_cited_claim_not_the_declaration():
    """The sign comes from the evidence, so a component cannot declare its way out of it."""
    report = run(T.wrong_direction())
    detail = " ".join(f.detail for f in only(report).findings if f.kind == "direction")
    assert "dose->level" in detail, "the finding must name the claim it contradicts"


# ---------------------------------------------------------------- Gate 3: wrong context

def test_gate3_support_from_a_different_agent_is_not_a_realization():
    report = run(T.wrong_agent())
    assert report.result is RealizationResult.CONTEXT_MISMATCH
    step = only(report).steps[0]
    assert step.entitlement is Entitlement.CONTEXT_MISMATCH
    assert not step.grounded


def test_gate3_support_from_a_different_system_is_a_transfer_gap_not_a_pass():
    report = run(T.grounded(system=T.OTHER_SYSTEM))
    assert report.result is RealizationResult.CONTEXT_MISMATCH
    assert report.transfer_gaps
    assert all(s.grounded for s in only(report).steps), \
        "the mechanism is entitled where it was measured; what fails is the transfer"


def test_gate3_matching_the_agent_the_measurement_used_lifts_that_penalty_only():
    """A chain administering the compound the experiment used is not making a substitution."""
    inventory = inventory_from_repo()
    with_wrong_agent = entitle(inventory, "sirt2_activity->k668_acetylation",
                               agent="nicotinic acid")
    with_right_agent = entitle(inventory, "sirt2_activity->k668_acetylation",
                               agent="nicotinamide mononucleotide")
    assert with_wrong_agent.entitlement is Entitlement.CONTEXT_MISMATCH
    assert with_right_agent.entitlement is Entitlement.SUPPORTED
    assert with_right_agent.support is Support.DIFFERENT_AGENT, \
        "the chain's label is unchanged; only what it entitles for this chain changed"


# ---------------------------------------------------------------- Gate 4: missing link

def test_gate4_a_chain_with_a_hole_is_partial_and_names_the_hole():
    report = run(T.missing_link())
    assert report.result is RealizationResult.PARTIAL_REALIZATION
    assessment = only(report)
    assert assessment.missing_links
    assert "c (needed by S2)" in assessment.missing_links[0]
    assert report.missing_capabilities, "PARTIAL must say what is missing"


# ---------------------------------------------------------------- Gate 5: evidence downgrade

def test_gate5_downgrading_the_evidence_changes_the_verdict():
    supported = run(T.grounded(support=Support.MODEL_EXPERIMENTAL))
    asserted = run(T.grounded(support=Support.ASSERTED_ONLY))
    assert supported.result is RealizationResult.GROUNDED_REALIZATION_CANDIDATE
    assert asserted.result is RealizationResult.EVIDENCE_INSUFFICIENT
    assert only(asserted).steps[0].entitlement is Entitlement.UNSUPPORTED


def test_gate5_an_unverified_citation_is_conditional_not_supported():
    report = run(T.grounded(verified=False))
    step = only(report).steps[0]
    assert step.entitlement is Entitlement.CONDITIONAL
    assert "no retrieval record" in step.entitlings[0].reason


# ---------------------------------------------------------------- Gate 6: provenance removal

def test_gate6_removing_the_source_prevents_treating_a_step_as_grounded():
    report = run(T.grounded(cite=False))
    assert report.result is RealizationResult.EVIDENCE_INSUFFICIENT
    step = only(report).steps[0]
    assert step.entitlement is Entitlement.UNKNOWN and not step.grounded
    assert any(f.kind == "provenance" for f in only(report).findings)


# ---------------------------------------------------------------- Gate 7: redundant component

def test_gate7_an_unnecessary_component_is_detected():
    report = run(T.redundant())
    assessment = only(report)
    assert assessment.redundant_steps == ("S2",)
    assert any(f.kind == "redundancy" for f in assessment.findings)


def test_gate7_a_minimal_chain_is_not_flagged():
    assert not only(run(T.grounded())).redundant_steps


# ---------------------------------------------------------------- Gate 8: unsafe realization

def test_gate8_producing_the_function_by_killing_the_cells_is_rejected():
    report = run(T.unsafe())
    assert report.result is RealizationResult.UNSAFE_REALIZATION
    assert any(f.kind == "safety" for f in only(report).findings)
    assert report.safety_dependencies


def test_gate8_a_capability_touching_a_safety_variable_must_say_what_it_drives_it_to():
    from rarepipe.stages.control.realization.checks import safety_findings
    problem = T.unsafe()
    realization = problem.realizations[0]
    silent = T.primitive("PP_SILENT", T.capability("CAP_SILENT", "death", edges=("dose->death",)))
    registry = problem.registry.model_copy(update={"primitives": (*problem.registry.primitives,
                                                                 silent)})
    patched = realization.model_copy(update={"steps": (
        *realization.steps[:1],
        realization.steps[1].model_copy(update={"uses_primitive": "PP_SILENT",
                                                "capability_id": "CAP_SILENT"}))})
    findings = safety_findings(patched, registry, problem.synthesis.problem.unsafe,
                              problem.synthesis.problem.space)
    assert findings and "without saying what value" in findings[0].detail


# ---------------------------------------------------------------- Gate 9: confounding

def test_gate9_a_caveated_claim_requires_the_observable_that_would_exclude_it():
    report = run(T.confounded())
    assert report.result is RealizationResult.EVIDENCE_INSUFFICIENT
    assert any(f.kind == "confound" for f in only(report).findings)


def test_gate9_naming_and_measuring_the_observable_restores_the_verdict():
    report = run(T.confounded(name_observable=True,
                              observed=("origin", "func", "death_marker")))
    assert report.result is RealizationResult.GROUNDED_REALIZATION_CANDIDATE


def test_gate9_naming_an_observable_nobody_measures_does_not_restore_it():
    report = run(T.confounded(name_observable=True, observed=("origin", "func")))
    assert report.result is RealizationResult.EVIDENCE_INSUFFICIENT
    confounds = [f for f in only(report).findings if f.kind == "confound"]
    assert confounds, "naming an observable nobody measures is not excluding the confound"
    assert "death_marker" in confounds[0].detail


# ---------------------------------------------------------------- Gate 10: invented components

def test_gate10_a_step_naming_an_unregistered_primitive_is_refused():
    problem = T.grounded()
    ghost = problem.realizations[0].model_copy(update={"steps": (
        problem.realizations[0].steps[0].model_copy(update={"uses_primitive": "PP_INVENTED"}),)})
    with pytest.raises(UnknownPrimitive):
        problem.model_copy(update={"realizations": (ghost,)}).registry.get("PP_INVENTED")
    with pytest.raises(Exception, match="PP_INVENTED"):
        type(problem)(**{**problem.model_dump(), "realizations": (ghost.model_dump(),)})


def test_gate10_a_capability_citing_a_claim_nobody_made_is_refused():
    inventory = inventory_from_repo()
    with pytest.raises(Unentitled, match="invented"):
        inventory.edge("invented->claim")
    registry = mva_realization.registry()
    invented = registry.primitives[0].model_copy(update={"capabilities": (
        registry.primitives[0].capabilities[0].model_copy(
            update={"evidence_edges": ("invented->claim",)}),)})
    with pytest.raises(Unentitled):
        type(registry)(primitives=(invented,)).check(inventory)


def test_gate10_a_capability_citing_a_claim_about_a_different_input_is_flagged():
    from rarepipe.stages.control.realization.checks import sign_findings
    problem = T.missing_link()
    realization = problem.realizations[0]
    borrowed = problem.registry.model_copy(update={"primitives": tuple(
        p.model_copy(update={"capabilities": tuple(
            c.model_copy(update={"evidence_edges": ("dose->b",)}) if c.capability_id == "CAP_C"
            else c for c in p.capabilities)}) for p in problem.registry.primitives)})
    findings = sign_findings(realization, borrowed, problem.inventory)
    assert any("claim about" in f.detail for f in findings)


# ---------------------------------------------------------------- Gate 11: the MVA pipeline

def test_gate11_the_bypass_runs_end_to_end_and_says_exactly_what_is_missing():
    report = run(mva_realization.problem())
    assert report.target_architecture == "BB_CHECKPOINT_BYPASS_CIRCUIT"
    assert report.logically_sufficient, \
        "the synthesis layer reports this architecture as reaching the state target"
    assert report.result is RealizationResult.NO_GROUNDED_REALIZATION
    assert len(report.functions) == 3
    assert {f.variable for f in report.functions} == {
        "checkpoint_activation", "checkpoint_silencing", "chromosome_alignment"}
    assert len(report.missing_capabilities) == 3
    for item in report.missing_capabilities:
        assert "bubr1_residual_function" in item, \
            "the inventory attributes every checkpoint function to the altered protein, and the " \
            "missing capability has to say so"
    assert report.abstention_reason


def test_gate11_the_burden_is_read_from_what_each_function_would_replace():
    report = run(mva_realization.problem())
    burdens = {f.variable: f.burden for f in report.functions}
    assert burdens["checkpoint_activation"] is EpistemicBurden.BYPASSES_ESTABLISHED_RELATIONSHIP
    assert burdens["checkpoint_silencing"] is EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP
    assert burdens["chromosome_alignment"] is EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP


def test_gate11_a_transformation_with_no_direct_chain_recurses_into_what_it_reduces_to():
    report = run(mva_realization.problem())
    alignment = next(f for f in report.functions if f.variable == "chromosome_alignment")
    assert [c.function for c in alignment.children] == ["pp2a_b56_recruitment->normal"]
    assert alignment.children[0].status is RealizationResult.NO_GROUNDED_REALIZATION
    assert alignment.children[0].missing_capability


def test_gate11_the_abundance_route_discriminates_rather_than_refusing_everything():
    """The contrast is the finding: the two chains break at different steps."""
    report = run(mva_realization.abundance_problem())
    by_id = {a.realization_id: a for a in report.functions[0].realizations}
    assert by_id["MR_ABUNDANCE_DIRECTLY"].status is RealizationResult.NO_GROUNDED_REALIZATION
    assert by_id["MR_ABUNDANCE_DIRECTLY"].steps[0].entitlement is Entitlement.CONTRADICTED

    acid = by_id["MR_ABUNDANCE_VIA_NICOTINIC_ACID"]
    nmn = by_id["MR_ABUNDANCE_VIA_NMN"]
    acid_broken = {s.step_id for s in acid.steps if not s.grounded}
    nmn_broken = {s.step_id for s in nmn.steps if not s.grounded}
    assert acid_broken == {"S1b", "S3"}, "the transfer step and the agent substitution"
    assert nmn_broken == {"S1"}, "nothing in the inventory raises the intracellular pool"
    assert acid_broken != nmn_broken, \
        "if both chains broke in the same place the layer would be discriminating nothing"
    assert not (acid_broken & nmn_broken), \
        "between them the two chains ground every step except getting the precursor into the cell"


def test_gate11_nothing_in_the_mva_registry_cites_a_claim_the_repository_lacks():
    """Every citation resolves to a claim the chain holds, and resolves to a known support level."""
    problem = mva_realization.problem()
    problem.registry.check(problem.inventory)
    cited = [edge_id for primitive in problem.registry.primitives
             for capability in primitive.capabilities
             for edge_id in capability.evidence_edges]
    assert cited, "a registry that cites nothing would pass this vacuously"
    for edge_id in cited:
        edge = problem.inventory.edge(edge_id)       # raises Unentitled if invented
        assert edge.support in set(Support), f"{edge_id} carries a support level nothing maps"
        assert edge.ref, f"{edge_id} resolves but carries no citation"


# ---------------------------------------------------------------- Gate 12: determinism

def test_gate12_the_same_inputs_give_the_same_digest_across_processes():
    script = (
        "from rarepipe.stages.control.realization import mva_realization\n"
        "from rarepipe.stages.control.realization.compiler import compile_realization\n"
        "for builder in ('problem', 'abundance_problem'):\n"
        "    print(compile_realization(getattr(mva_realization, builder)()).content_digest)\n")
    digests = set()
    for seed in ("0", "3", "65537"):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                                  "PYTHONPATH": "src:."}, cwd="/Users/venus/Desktop/rarepipe")
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    assert len(digests) == 1, f"the realization digest moved with the hash seed: {digests}"


# ---------------------------------------------------------------- the inventory is derived

def test_the_evidence_inventory_is_the_repositorys_own_chain():
    from rarepipe.stages.simulate.mva import mva_chain
    inventory = inventory_from_repo()
    chain = {f"{e.source}->{e.target}" for e in mva_chain().edges}
    assert {e.edge_id for e in inventory.edges} == chain, \
        "the inventory must be the chain, not a copy of it that can drift"


def test_the_transcribed_contexts_still_match_the_scope_notes_they_came_from():
    """A transcription with no consistency check is a second source of truth."""
    from rarepipe.stages.control.realization.evidence import _CONTEXT
    from rarepipe.stages.simulate.mva import mva_chain
    notes = {f"{e.source}->{e.target}": f"{e.scope_note} {e.caveat}" for e in mva_chain().edges}
    for ref, data in _CONTEXT.items():
        note = notes[data["transcribed_from"]]
        for term in data["must_appear"]:
            assert term.lower() in note.lower(), (
                f"{ref}: the context transcribed from {data['transcribed_from']} no longer matches "
                f"its scope note; {term!r} is gone")


def test_no_case_level_genomic_content_reaches_a_realization_report():
    patterns = (r"\bc\.\d", r"\bp\.[A-Z][a-z]{2}\d", r"\bchr[0-9XYM]", r"\brs\d{3,}",
                r"\bg\.\d{4,}", r"\b[ACGT]{8,}\b")
    for builder in ("problem", "abundance_problem"):
        blob = run(getattr(mva_realization, builder)()).model_dump_json()
        for pattern in patterns:
            assert not re.search(pattern, blob), f"{pattern} matched in a realization report"


def test_the_committed_realization_maps_are_not_stale():
    from pathlib import Path

    from rarepipe.stages.control.realization.report import render
    root = Path(__file__).resolve().parents[1]
    for builder, filename in (("problem", "MVA_REALIZATION_BYPASS.md"),
                              ("abundance_problem", "MVA_REALIZATION_ABUNDANCE.md")):
        committed = (root / "docs/control" / filename).read_text()
        assert committed == render(run(getattr(mva_realization, builder)())), (
            f"docs/control/{filename} is stale: run "
            "uv run python tools/control/compile_mva_realization.py")
