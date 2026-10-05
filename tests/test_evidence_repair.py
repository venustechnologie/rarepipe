"""Evidence repair and full recompile.

The test is not whether the old answer survives. The test is whether the answer changes correctly
when the evidence changes — so nothing here asserts a historical verdict. Every assertion is either
an invariant that must hold however the evidence moves, or a statement about the repair itself.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rarepipe.stages.control.discovery.external import corpus as C
from rarepipe.stages.control.discovery.external.citation_audit import (
    AttributionState, audit, attributions,
)
from rarepipe.stages.control.evidence_repair.mva_repair import ledger
from rarepipe.stages.control.evidence_repair.recompile import LAYER_ORDER, deltas, observe
from rarepipe.stages.control.evidence_repair.records import RecoveryOutcome, RepairKind
from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Support
from rarepipe.stages.simulate.mva import BUBR1, NAD_CELL, NIACIN, mva_chain

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = C.snapshot_path(ROOT, "mva-external-v1")


@pytest.fixture(scope="module")
def snapshot():
    return C.load(SNAPSHOT)


@pytest.fixture(scope="module")
def texts(snapshot):
    return {d.source_id: C.text_of(SNAPSHOT, d) for d in snapshot.documents}


# ---------------------------------------------------------------- section 14: the bad attribution

def test_the_disqualified_attribution_is_not_accepted_when_validated(snapshot, texts):
    """Given the retrieved document, the attribution must not be accepted."""
    probe = CausalChain(
        chain_id="probe", case_ref="PROBE", nodes=(NIACIN, BUBR1),
        edges=(CausalEdge(source=NIACIN, target=BUBR1, sign=1,
                          mechanism="a direct effect the document does not address",
                          support=Support.CONTRADICTED, evidence_ref="PMID:42543917",
                          scope_note="attributed for this test"),))
    result, = audit(snapshot, texts, probe)
    assert result.verdict is AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION
    assert result.disqualifies


def test_no_contradiction_survives_the_withdrawal_of_its_only_evidence():
    """The scientific invariant, not the historical answer.

    A contradicted verdict resting on exactly one citation cannot survive that citation being
    withdrawn. Asserted on the case's chain as it now stands, and on the general rule that an edge
    with no evidence reference cannot carry a contradicted support level.
    """
    chain = mva_chain()
    direct = next(e for e in chain.edges if e.source == NIACIN and e.target == BUBR1)
    assert direct.evidence_ref is None
    assert direct.support is not Support.CONTRADICTED
    assert chain.predict(NIACIN, BUBR1).contradicted_alternatives == ()

    with pytest.raises(Exception, match="evidence reference"):
        CausalEdge(source="a", target="b", sign=1, mechanism="m",
                   support=Support.CONTRADICTED, scope_note="no citation")


def test_the_withdrawn_attribution_appears_nowhere_as_live_evidence():
    """Section 20: the incorrect attribution no longer sustains any verdict."""
    chain = mva_chain()
    assert all("42543917" not in (e.evidence_ref or "") for e in chain.edges)
    assert all("42543917" not in a.ref for a in attributions(chain))
    live = ROOT / "src/rarepipe/stages"
    offenders = [p for p in live.rglob("*.py")
                 if "42543917" in p.read_text() and "evidence_repair" not in str(p)]
    assert not offenders, f"the retired citation is still live in {offenders}"


def test_the_history_is_preserved_rather_than_overwritten():
    """Section 3: it must be answerable why this edge used to be contradicted and now is not."""
    repair = next(r for r in ledger().repairs if r.repair_id == "REPAIR_R1")
    assert repair.previous_verdict == "contradicted"
    assert "42543917" in repair.previous_source_assignment
    assert repair.previous_claim_version and repair.new_version
    assert repair.audit_verdict is AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION
    assert "white adipocytes" in repair.reason_for_invalidation
    assert repair.new_support_level == "asserted_only"


def test_no_substitute_reference_was_invented():
    """Section 4, case B: the intended reference was searched for and not found."""
    repair = next(r for r in ledger().repairs if r.repair_id == "REPAIR_R1")
    assert repair.recovery.outcome is RecoveryOutcome.NO_INTENDED_REFERENCE_FOUND
    assert repair.recovery.recovered_reference == ""
    assert repair.recovery.external_queries, "the search has to be auditable"
    assert len(repair.recovery.searched_in_project) >= 3
    assert repair.new_source_assignment == ""


# ---------------------------------------------------------------- section 15: the human trial

def test_the_human_trial_is_groundable_at_the_tissue_it_was_measured_in():
    claim = mva_chain().predict(NIACIN, NAD_CELL)
    assert claim.weakest_support is Support.HUMAN_EXPERIMENTAL
    assert "skeletal muscle" in claim.limiting_scope_note


def test_the_human_trial_does_not_satisfy_the_patient_cell_context():
    """Section 5's forbidden grounding: tissue evidence is not patient-derived-cell evidence."""
    from rarepipe.stages.control.discovery import mva_gaps
    from rarepipe.stages.control.discovery.compiler import compile_discovery
    from rarepipe.stages.control.discovery.kinds import GapResult, RejectionReason
    report = compile_discovery(mva_gaps.problem())
    gap = next(g for g in report.gaps if g.gap_id == "GAP_D_INTRACELLULAR_COFACTOR_ENTRY")
    external = next(a for a in gap.assessments if "32386566" in a.candidate_id)
    assert gap.result is GapResult.CONTEXT_ONLY_CAPABILITY
    assert RejectionReason.CONTEXT_MISMATCH in external.rejections
    assert not gap.grounded_capabilities


def test_the_transfer_gap_replaced_the_compartment_blocker():
    """Section 6: the old blood-to-cell blocker is not kept as if nothing had changed."""
    from rarepipe.stages.control.discovery import mva_gaps
    from rarepipe.stages.control.discovery.compiler import compile_discovery
    from rarepipe.stages.control.discovery.kinds import RejectionReason
    report = compile_discovery(mva_gaps.problem())
    gap = next(g for g in report.gaps if g.gap_id == "GAP_D_INTRACELLULAR_COFACTOR_ENTRY")
    external = next(a for a in gap.assessments if "32386566" in a.candidate_id)
    assert RejectionReason.COMPARTMENT_MISMATCH not in external.rejections, \
        "the compartment objection was answered by a tissue measurement"
    assert gap.transfer_gaps, "and replaced by a transfer gap, which is an object, not a warning"


def test_the_human_evidence_never_travels_without_its_limits():
    """Section 18: the connected trial may not be read as a recommendation or as a full route."""
    claim = mva_chain().predict(NIACIN, NAD_CELL)
    joined = " ".join(claim.caveats) + claim.limitation if hasattr(claim, "limitation") \
        else " ".join(claim.caveats)
    assert "nothing here says niacin should be given to anyone" in joined
    assert "unmeasured" in joined


# ---------------------------------------------------------------- section 7: the whole audit

def test_the_backward_audit_covers_every_load_bearing_citation(snapshot, texts):
    chain = mva_chain()
    rows = audit(snapshot, texts, chain)
    cited = {f"{e.source}->{e.target}" for e in chain.edges if e.evidence_ref}
    assert {r.edge_id for r in rows} == cited
    assert all(r.checks for r in rows)
    machine = {c.name for r in rows for c in r.checks if c.outcome != "not_machine_checkable"}
    assert {"source exists", "retrieval record exists", "attributed input appears",
            "attributed output appears"} <= machine


def test_the_audit_says_which_of_its_checks_a_machine_cannot_make(snapshot, texts):
    """An audit that implied it had checked whether a claim follows from a source would overstate."""
    rows = audit(snapshot, texts, mva_chain())
    unchecked = {c.name for r in rows for c in r.checks if c.outcome == "not_machine_checkable"}
    assert "claim follows from the source" in unchecked
    assert "claimed direction supported" in unchecked


def test_the_second_disqualified_attribution_was_found_by_auditing_everything():
    """Section 7's point: do not assume the other references are fine."""
    repair = next(r for r in ledger().repairs if r.repair_id == "REPAIR_R4")
    assert repair.kind is RepairKind.RETIRE_ATTRIBUTION
    assert repair.previous_source_assignment == "PMID:20516114"
    assert "backward audit over every load-bearing citation" in repair.reason_for_invalidation


def test_r4s_open_question_was_answered_by_reading_the_whole_article():
    """R4 retired a label while conceding the stored copy was only an abstract.

    That concession was the whole of its open question: a scientist might reasonably have retrieved
    the full article instead of accepting an assertion. The article has since been read, and it does
    not measure cell loss anywhere, so the conservative label stands on the complete document rather
    than on a partial copy. The flag is closed because the work was done, not because the answer was
    preferred — so the reason has to say what was read.
    """
    repair = next(r for r in ledger().repairs if r.repair_id == "REPAIR_R4")
    assert "full article" in repair.reason_for_invalidation
    assert repair.new_support_level == "asserted_only"
    assert not repair.needs_human_decision


# ---------------------------------------------------------------- sections 9 to 12: propagation

def test_every_layer_in_the_dependency_order_is_recomputed():
    computed = deltas(ledger())
    assert tuple(d.layer for d in computed) == LAYER_ORDER
    assert all(d.why for d in computed), "a layer with no account of itself is not a report"
    assert [d.position for d in computed] == list(range(1, len(LAYER_ORDER) + 1))


def test_an_unchanged_layer_still_explains_itself():
    computed = deltas(ledger())
    for delta in computed:
        if not delta.changed:
            assert len(delta.why) > 40
            assert delta.before == delta.after


def test_the_recompile_reads_fresh_compilations_not_recorded_conclusions():
    """Observing twice must agree; the delta must come from a fresh observation, not the baseline.

    If `deltas` echoed the recorded baseline back as the "after" state, every layer would report
    UNCHANGED and the report would look like a successful no-op. So the test asserts both that the
    observation is stable and that the comparison actually moved something.
    """
    first, second = observe(), observe()
    assert first == second
    assert set(first) == set(LAYER_ORDER)
    assert first != ledger().baseline.layers, "nothing moved, which would make the phase pointless"
    computed = deltas(ledger())
    assert any(d.changed for d in computed), \
        "a delta set with nothing changed means the recompile was not run"
    assert [d.after for d in computed] == [first[d.layer] for d in computed], \
        "the after state must be the fresh observation, not the recorded baseline"


def test_a_digest_only_move_is_reported_as_such():
    """A report whose contents changed and whose conclusion did not must say both."""
    computed = [d for d in deltas(ledger()) if d.changed]
    digest_only = [d for d in computed
                   if all("digest" in k for k in set(d.before) | set(d.after)
                          if d.before.get(k) != d.after.get(k))]
    assert digest_only, "at least one layer moved only in its artifact identity"
    for delta in digest_only:
        assert "Only the artifact digest moved" in delta.why


def test_the_binding_constraint_on_the_case_did_not_move():
    """The repair corrected what the repository believed, not the question the case turns on."""
    after = observe()
    assert after["causal_chain_support"]["niacin_to_missegregation_weakest_link"] == \
        "bubr1_abundance->bubr1_residual_function"
    assert after["control_model"]["result"] == "CONTROL_INDETERMINATE"


# ---------------------------------------------------------------- section 17: determinism

def test_the_repaired_pipeline_is_deterministic_across_processes():
    script = ("from rarepipe.stages.control.evidence_repair.recompile import observe\n"
              "import json; print(json.dumps(observe(), sort_keys=True))\n")
    seen = set()
    for seed in ("0", "17", "8191"):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                                  "PYTHONPATH": "src:."}, cwd=str(ROOT))
        assert out.returncode == 0, out.stderr[-2000:]
        seen.add(out.stdout.strip())
    assert len(seen) == 1, "the recompiled state moved with the hash seed"


def test_the_committed_delta_reports_are_not_stale():
    from rarepipe.stages.control.evidence_repair.report import (
        render_evidence_delta, render_recompile_delta,
    )
    book = ledger()
    computed = deltas(book)
    for filename, rendered in (("MVA_EVIDENCE_REPAIR_DELTA.md",
                                render_evidence_delta(book, computed)),
                               ("MVA_FULL_RECOMPILE_DELTA.md",
                                render_recompile_delta(book, computed))):
        committed = (ROOT / "docs/control" / filename).read_text()
        assert committed == rendered, (
            f"docs/control/{filename} is stale: run "
            "uv run python tools/control/compile_evidence_repair.py")


def test_every_recorded_baseline_digest_is_corroborated_by_git():
    """The baseline is recorded data, so every digest in it must match the artifact committed then.

    This is what makes the record something other than a hand-written claim: each digest is checked
    against the file it covers, at the commit it was captured from.
    """
    book = ledger()
    commit = book.baseline.captured_at_commit
    artifacts = {
        ("control_model", "digest"): "MVA_CONTROL_MAP.md",
        ("synthesis_architectures", "digest"): "MVA_ARCHITECTURE_MAP.md",
        ("physical_realizations", "bypass_digest"): "MVA_REALIZATION_BYPASS.md",
        ("physical_realizations", "abundance_digest"): "MVA_REALIZATION_ABUNDANCE.md",
        ("capability_gaps", "digest"): "MVA_CAPABILITY_GAPS_EXTERNAL.md",
    }
    checked = 0
    for (layer, key), filename in artifacts.items():
        digest = book.baseline.layers[layer][key]
        shown = subprocess.run(["git", "show", f"{commit}:docs/control/{filename}"],
                               capture_output=True, text=True, cwd=str(ROOT))
        assert shown.returncode == 0, f"{filename} at {commit}: {shown.stderr}"
        assert digest in shown.stdout, (
            f"{layer}.{key} records {digest}, which is not in docs/control/{filename} at {commit}")
        checked += 1
    assert checked == len(artifacts)


def test_the_baseline_lives_in_data_not_in_source():
    """A digest written into source is a claim nothing verified."""
    from rarepipe.stages.control.evidence_repair.mva_repair import BASELINE_PATH
    assert BASELINE_PATH.exists()
    source = Path("src/rarepipe/stages/control/evidence_repair/mva_repair.py").read_text()
    assert "sha256:" not in source, "the ledger must read its baseline, not carry digests inline"
