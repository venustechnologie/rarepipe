"""Stage 09 — the promotion gate. A hypothesis is 'worth testing', never 'works'."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from rarepipe.stages.track2.ingest import IngestError, import_hypotheses, save
from rarepipe.stages.track2.model import EvidenceGrade, HypothesisState, Status
from rarepipe.stages.track2.stage import BuildRequest, Track2UsageError, build

Q1 = "High-dose nicotinic acid resulted in a 4-6-fold increase of blood NAD+ in healthy individuals."
Q2 = "Treatment with the NAD+ precursor increases BubR1 abundance in vivo."
Q3 = "Ectopic expression of BUBR1 restored mitotic checkpoint activity in patient cells."


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "research"
    bundle = root / "bundles" / "KT_0001"
    (bundle / "docs").mkdir(parents=True)
    (bundle / "docs" / "PMID_111.txt").write_text(f"{Q1} {Q2} {Q3}")
    (bundle / "bundle.json").write_text(json.dumps({
        "bundle": {"bundle_id": "KT_0001", "knowledge_task": "KT_0001", "created_at": "2026-09-26T00:00:00+00:00"},
        "documents": [{"source_id": "PMID:111", "title": "t", "pub_year": 2026}]}))
    return root


@pytest.fixture
def discovery(tmp_path: Path) -> Path:
    run = tmp_path / "discovery" / "RUN_DISC"
    run.mkdir(parents=True)
    (run / "intervention_discovery.private.json").write_text(json.dumps({
        "case_id": "CASE_X", "gene_symbol": "BUB1B", "semantic_digest": "sha256:disc",
        "status": "NO_DEFENSIBLE_APPROVED_DRUG_CANDIDATE_FOUND",
        "node_query_specs": [{"id": "NQS_001", "question": "q", "sent": False}],
        "execution": {"run_id": "RUN_DISC"},
        "provenance": {"intervention_map_run_id": "RUN_MAP", "intervention_map_digest": "sha256:map"}}))
    return run


def _hypothesis(**kw):
    base = {
        "active_ingredient": "niacin", "statement": "worth testing", "observed_direction": "concordant",
        "tested_in_bub1b_deficiency": False, "tested_in_mva": False, "not_tested_note": "never tested in MVA",
        "exact_allele_dependency": False,
        "proposed_chain": [
            {"step": "niacin raises NAD+", "kind": "evidenced",
             "evidence": [{"source_id": "PMID:111", "quote": Q1, "independence_group": "niacin_nad"}]},
            {"step": "NAD+ raises BubR1 abundance", "kind": "evidenced",
             "evidence": [{"source_id": "PMID:111", "quote": Q2, "independence_group": "sirt2_bubr1"}]},
            {"step": "different precursors may not behave alike", "kind": "inference", "evidence": []}],
        "validation_plan": {"system": "BUB1B-deficient cells", "intervention": "an approved NAD+ precursor",
                            "readouts": ["BUBR1 abundance"], "hypothesis": "abundance rises",
                            "falsification": "no change, or checkpoint weakens"},
        "limitations": ["never tested in this disease", "the in vivo result used a different precursor"]}
    base.update(kw)
    return base


def _write(root: Path, hypotheses: list[dict], name="h.yaml") -> Path:
    path = root / name
    path.write_text(yaml.safe_dump({"session": {"provider": "Anthropic", "interface": "Claude Code",
                                                "model": "Claude Opus 5", "knowledge_task": "KT_0001",
                                                "human_reviewed": True},
                                    "hypotheses": hypotheses}, sort_keys=False))
    return path


def make(discovery, workspace, tmp_path, **kw):
    return build(BuildRequest(discovery_run=discovery, research_dir=workspace, output=tmp_path / "out",
                              argv=["t"], **kw))


# ── the import gate: arrow by arrow ─────────────────────────────────────────

def test_an_arrow_claiming_evidence_must_produce_it(workspace):
    bad = _hypothesis(proposed_chain=[{"step": "niacin cures it", "kind": "evidenced", "evidence": []}])
    result = import_hypotheses(workspace, _write(workspace, [bad]))
    assert not result.hypotheses and result.rejected[0].reason == "no_citation"

    fabricated = _hypothesis(proposed_chain=[
        {"step": "s", "kind": "evidenced", "evidence": [{"source_id": "PMID:111", "quote": "not in the text"}]}])
    result = import_hypotheses(workspace, _write(workspace, [fabricated], "b.yaml"))
    assert result.rejected[0].reason == "quote_not_found_in_source"

    missing = _hypothesis(proposed_chain=[
        {"step": "s", "kind": "evidenced", "evidence": [{"source_id": "PMID:999", "quote": Q1}]}])
    result = import_hypotheses(workspace, _write(workspace, [missing], "c.yaml"))
    assert result.rejected[0].reason == "source_not_in_corpus"


def test_an_inference_arrow_needs_no_citation_but_is_marked(workspace):
    result = import_hypotheses(workspace, _write(workspace, [_hypothesis()]))
    kinds = [link.kind for link in result.hypotheses[0].proposed_chain]
    assert kinds == ["evidenced", "evidenced", "inference"]
    assert result.hypotheses[0].state is HypothesisState.DISCOVERY_ONLY, "nothing is promoted at import"


# ── the promotion gate ──────────────────────────────────────────────────────

def test_a_complete_hypothesis_is_promoted_with_an_explicit_grade(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    r = make(discovery, workspace, tmp_path)
    h = r.hypothesis_set.hypotheses[0]
    assert h.approval_verified and "US" in h.approval_jurisdictions
    assert all(c.passed for c in h.gate)
    assert h.evidence_grade in (EvidenceGrade.MECHANISTIC_INDIRECT, EvidenceGrade.STRONG_INDIRECT)
    assert h.state.value.startswith("TRACK2_ELIGIBLE")
    assert r.hypothesis_set.status is Status.READY
    assert h.treatment_recommendation is False and h.clinical_actionability == "NOT_ASSESSED"


def test_a_drug_class_cannot_be_promoted(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [
        _hypothesis(active_ingredient="CDK4/6 inhibitor")])))
    r = make(discovery, workspace, tmp_path)
    h = r.hypothesis_set.hypotheses[0]
    failed = [c.check for c in h.gate if not c.passed]
    assert any("active ingredient" in c for c in failed)
    assert r.hypothesis_set.status is Status.BLOCKED


def test_an_unapproved_ingredient_cannot_be_promoted(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [
        _hypothesis(active_ingredient="nicotinamide mononucleotide")])))
    r = make(discovery, workspace, tmp_path)
    h = r.hypothesis_set.hypotheses[0]
    assert not h.approval_verified
    assert h.state is HypothesisState.APPROVAL_UNVERIFIED
    assert r.hypothesis_set.status is Status.BLOCKED


def test_a_discordant_direction_cannot_be_promoted(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [
        _hypothesis(observed_direction="discordant")])))
    r = make(discovery, workspace, tmp_path)
    assert any("direction" in c for c in
               [x.check for x in r.hypothesis_set.hypotheses[0].gate if not x.passed])
    assert r.hypothesis_set.status is Status.BLOCKED


def test_a_hypothesis_without_a_falsifiable_experiment_cannot_be_promoted(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis(validation_plan=None)])))
    r = make(discovery, workspace, tmp_path)
    assert any("validation experiment" in c for c in
               [x.check for x in r.hypothesis_set.hypotheses[0].gate if not x.passed])


# ── the baseline, and what the stage refuses to say ─────────────────────────

def test_the_baseline_is_sealed_whichever_branch_is_taken(discovery, workspace, tmp_path):
    blocked = make(discovery, workspace, tmp_path)
    assert blocked.hypothesis_set.status is Status.BLOCKED
    assert (blocked.run_dir / "track2_baseline_snapshot.json").exists()
    baseline = blocked.hypothesis_set.baseline
    assert baseline.created_before_network_search and baseline.public_evidence_only
    assert baseline.discovery_run_id == "RUN_DISC" and baseline.discovery_digest == "sha256:disc"
    assert baseline.hypotheses_found == 0
    assert not (blocked.run_dir / "xaviramram_track2_report.md").exists(), "no report without a hypothesis"


def test_the_submission_package_appears_only_when_a_hypothesis_passes(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    r = make(discovery, workspace, tmp_path)
    for name in ("xaviramram_track2_report.md", "track2_submission_manifest.json", "track2_pitch_script.md"):
        assert (r.run_dir / name).exists()
    manifest = json.loads((r.run_dir / "track2_submission_manifest.json").read_text())
    assert manifest["submission"]["state"] == "ready_for_human_review"
    assert all(h["treatment_recommendation"] is False for h in manifest["eligible_hypotheses"])


def test_no_dose_and_no_recommendation_anywhere(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    r = make(discovery, workspace, tmp_path)
    for name in ("candidate_adjudication.md", "xaviramram_track2_report.md", "track2_pitch_script.md"):
        text = (r.run_dir / name).read_text().lower()
        for forbidden in ("mg/kg", "recommended dose", "should be given", "we recommend treating",
                          "prescrib", "take once daily"):
            assert forbidden not in text, f"{forbidden!r} in {name}"
    assert "not a treatment recommendation" in (r.run_dir / "xaviramram_track2_report.md").read_text().lower()


def test_search_outcomes_say_what_they_do_not_mean(discovery, workspace, tmp_path):
    r = make(discovery, workspace, tmp_path)
    assert r.hypothesis_set.search_outcomes
    for outcome in r.hypothesis_set.search_outcomes:
        assert outcome.does_not_mean
    text = (r.run_dir / "candidate_adjudication.md").read_text()
    assert "does not mean" in text.lower()


def test_submission_claims_carry_their_basis(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    r = make(discovery, workspace, tmp_path)
    assert r.hypothesis_set.submission_claims
    for claim in r.hypothesis_set.submission_claims:
        assert claim.evidence_ids or claim.basis_note, f"{claim.id} rests on nothing"


def test_a_missing_discovery_artifact_is_refused(workspace, tmp_path):
    with pytest.raises(Track2UsageError):
        build(BuildRequest(discovery_run=tmp_path / "nope", research_dir=workspace, output=tmp_path / "o",
                           argv=["t"]))


# ── Stage 09R closure ───────────────────────────────────────────────────────

def test_contradicting_evidence_must_also_be_verbatim(workspace):
    fabricated = _hypothesis(contradicting_evidence=[{"source_id": "PMID:111", "quote": "invented contradiction"}])
    result = import_hypotheses(workspace, _write(workspace, [fabricated]))
    assert any(r.reason == "quote_not_found_in_source" for r in result.rejected)

    real = _hypothesis(contradicting_evidence=[{"source_id": "PMID:111", "quote": Q3,
                                                "contradicts": "the pivotal arrow"}])
    result = import_hypotheses(workspace, _write(workspace, [real], "d.yaml"))
    assert result.hypotheses[0].contradicting_evidence


def test_a_no_evidence_outcome_must_say_what_was_searched(discovery, workspace, tmp_path):
    """Zero queries and zero documents is indistinguishable from never having searched."""
    (workspace / "tasks").mkdir(parents=True, exist_ok=True)
    (workspace / "tasks" / "KT_0001.json").write_text(json.dumps({
        "id": "KT_0001", "question": "q", "reason": "[D_failure_or_negative_experience] lane",
        "disclosure_level": "public_gene_level", "retrieval_plan": [], "queries": ["a", "b"],
        "documents_found": ["PMID:111", "PMID:222"]}))
    r = make(discovery, workspace, tmp_path)
    negatives = [o for o in r.hypothesis_set.search_outcomes
                 if o.result.value in ("NO_EVIDENCE_FOUND", "EXHAUSTED_TO_THRESHOLD")]
    assert negatives
    for outcome in negatives:
        assert outcome.queries, f"{outcome.result.value} with no queries recorded"
        assert outcome.documents_examined > 0


def test_the_baseline_resolves_the_whole_provenance_chain(discovery, workspace, tmp_path):
    imap_run = tmp_path / "map" / "RUN_MAP"
    imap_run.mkdir(parents=True)
    (imap_run / "intervention_map.private.json").write_text(json.dumps({
        "execution": {"run_id": "RUN_MAP"},
        "provenance": {"mechanism_run_id": "RUN_MECH", "mechanism_digest": "sha256:mech"}}))
    r = make(discovery, workspace, tmp_path, intervention_map_run=imap_run)
    b = r.hypothesis_set.baseline
    assert b.mechanism_run_id == "RUN_MECH" and b.mechanism_digest == "sha256:mech"
    assert b.intervention_map_run_id == "RUN_MAP" and b.discovery_run_id == "RUN_DISC"


def test_a_mismatched_intervention_map_is_refused(discovery, workspace, tmp_path):
    other = tmp_path / "other" / "RUN_OTHER"
    other.mkdir(parents=True)
    (other / "intervention_map.private.json").write_text(json.dumps({
        "execution": {"run_id": "RUN_OTHER"}, "provenance": {"mechanism_run_id": "RUN_MECH"}}))
    with pytest.raises(Track2UsageError):
        make(discovery, workspace, tmp_path, intervention_map_run=other)
