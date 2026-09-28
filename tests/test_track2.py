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
        "active_ingredient": "niacin", "statement": "worth testing", "predicted_direction": "concordant",
        "observed_direction": "unknown", "observed_upstream_effects": ["blood NAD+ rises"],
        "efficacy_dependencies": [{"dependency": "residual BUBR1 function", "status": "unresolved"}],
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
    assert any("wrong way" in c for c in
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
        "provenance": {"mechanism_run_id": "RUN_MECH", "mechanism_digest": "sha256:mech",
                       "validation_run_id": "RUN_VAL"}}))
    r = make(discovery, workspace, tmp_path, intervention_map_run=imap_run)
    b = r.hypothesis_set.baseline
    assert b.validation_run_id == "RUN_VAL", "the validation link must not be filled with another run's id"
    assert b.mechanism_run_id == "RUN_MECH" and b.mechanism_digest == "sha256:mech"
    assert b.intervention_map_run_id == "RUN_MAP" and b.discovery_run_id == "RUN_DISC"


def test_a_mismatched_intervention_map_is_refused(discovery, workspace, tmp_path):
    other = tmp_path / "other" / "RUN_OTHER"
    other.mkdir(parents=True)
    (other / "intervention_map.private.json").write_text(json.dumps({
        "execution": {"run_id": "RUN_OTHER"}, "provenance": {"mechanism_run_id": "RUN_MECH"}}))
    with pytest.raises(Track2UsageError):
        make(discovery, workspace, tmp_path, intervention_map_run=other)


def test_an_absence_claim_is_scoped_to_the_corpus(discovery, workspace, tmp_path):
    """A claim about our corpus is not a claim about the world.

    An attempt reported only as unpublished data, in a methods aside, or in a full text we could
    not reach would never appear in the corpus — so "nobody has tested this" is a claim the
    pipeline is not entitled to make.
    """
    r = make(discovery, workspace, tmp_path)
    blob = json.dumps(r.hypothesis_set.model_dump(mode="json")).lower()
    for overclaim in ("never been tested", "has never been tried", "appears untested",
                      "nobody has tested", "untested space"):
        assert overclaim not in blob, f"unscoped absence claim: {overclaim!r}"
    negatives = [o for o in r.hypothesis_set.search_outcomes
                 if o.result.value in ("NO_EVIDENCE_FOUND", "EXHAUSTED_TO_THRESHOLD")]
    assert negatives
    for outcome in negatives:
        assert "corpus searched" in outcome.interpretation.lower() or "corpus" in outcome.does_not_mean.lower()
    claim = next(c for c in r.hypothesis_set.submission_claims if c.id == "SC_003")
    assert "corpus searched" in claim.statement
    assert "not proof that no attempt exists" in claim.statement


def test_the_pitch_does_not_claim_more_than_the_corpus_supports(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    r = make(discovery, workspace, tmp_path)
    pitch = (r.run_dir / "track2_pitch_script.md").read_text().lower()
    assert "never been tested" not in pitch
    assert "corpus we searched" in pitch or "corpus we searched" in pitch
    assert "not a proof about the world" in pitch


def test_the_status_line_itself_is_corpus_scoped(discovery, workspace, tmp_path):
    """The headline sentence is the one most likely to be quoted, so it must not overclaim either."""
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    r = make(discovery, workspace, tmp_path)
    basis = r.hypothesis_set.status_basis.lower()
    assert "corpus searched" in basis
    for overclaim in ("none has been tested", "has never been tested", "nobody has tested"):
        assert overclaim not in basis



# ── predicted is not observed; generating is not depending ──────────────────

def test_an_upstream_effect_cannot_stand_in_for_an_observed_rescue(discovery, workspace, tmp_path):
    """A measured rise in blood NAD+ is not an observed effect on BUBR1 or the checkpoint."""
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    h = make(discovery, workspace, tmp_path).hypothesis_set.hypotheses[0]
    assert h.predicted_direction == "concordant" and h.observed_direction == "unknown"
    assert h.observed_upstream_effects
    assert h.state.value.startswith("TRACK2_ELIGIBLE"), "an unobserved rescue is fine for a research hypothesis"


def test_a_hypothesis_whose_prediction_is_unknown_cannot_be_promoted(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis(predicted_direction="unknown")])))
    h = make(discovery, workspace, tmp_path).hypothesis_set.hypotheses[0]
    assert any("predicted direction" in c.check and not c.passed for c in h.gate)


def test_efficacy_dependencies_must_be_named(discovery, workspace, tmp_path):
    """Generating a hypothesis without the exact allele is not expecting it to work regardless of the allele."""
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis(efficacy_dependencies=[])])))
    h = make(discovery, workspace, tmp_path).hypothesis_set.hypotheses[0]
    assert any("efficacy dependencies" in c.check and not c.passed for c in h.gate)


def test_the_lane_b_outcome_is_derived_from_the_evidence(discovery, workspace, tmp_path):
    """The sentence used to be a constant, and a reviewer's single citation made it false."""
    r = make(discovery, workspace, tmp_path)
    assert r.hypothesis_set.search_outcomes[0].result.value == "NO_EVIDENCE_FOUND"

    payload = json.loads((discovery / "intervention_discovery.private.json").read_text())
    payload["experiences"] = [{
        "id": "IX_1", "intervention_ingredient": "sirolimus (rapamycin)", "lane": "B_rescue_in_deficient_biology",
        "model": "BubR1-deficient mice", "subject_scope": "animal", "outcome": "no_effect",
        "measured_endpoints": [{"endpoint": "age-related phenotypes", "direction": "unchanged"}],
        "evidence_source": {"source_id": "PMID:23602569", "quote": "similar rates"}}]
    (discovery / "intervention_discovery.private.json").write_text(json.dumps(payload))
    r = make(discovery, workspace, tmp_path / "second")
    outcome = r.hypothesis_set.search_outcomes[0]
    assert outcome.result.value == "NEGATIVE_EXPERIENCE_FOUND"
    assert "sirolimus" in outcome.interpretation and "IX_1" in outcome.evidence
    assert "not a demonstrated null" in outcome.does_not_mean
    claim = next(c for c in r.hypothesis_set.submission_claims if c.id == "SC_003")
    assert "One reported attempt was found" in claim.statement and claim.evidence_ids == ["IX_1"]


def _mechanism(tmp_path, run_id="RUN_MECH", decision="INSUFFICIENT"):
    run = tmp_path / "mech" / run_id
    run.mkdir(parents=True)
    (run / "mechanism_dossier.sanitized.json").write_text(json.dumps({
        "execution": {"run_id": run_id},
        "residual_function": {"class_level": "function_persists", "exact_allele": "insufficient", "decision": decision,
                              "class_level_basis": "2 altered proteins in the protein kinase domain (I909T, L1012P) "
                                                   "were restored",
                              "exact_allele_basis": "no experiment expressed this child's exact substitution",
                              "class_level_endpoints": ["checkpoint activation (nocodazole response)"],
                              "distinguishing_experiment": "express the exact substitution at matched abundance"}}))
    imap = tmp_path / "map" / "RUN_MAP"
    imap.mkdir(parents=True, exist_ok=True)
    (imap / "intervention_map.private.json").write_text(json.dumps({
        "execution": {"run_id": "RUN_MAP"}, "provenance": {"mechanism_run_id": "RUN_MECH"}}))
    return run, imap


def test_the_residual_function_dependency_is_derived_from_stage06(discovery, workspace, tmp_path):
    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()])))
    mech, imap = _mechanism(tmp_path)
    r = make(discovery, workspace, tmp_path, intervention_map_run=imap, mechanism_run=mech)
    [dep] = [d for h in r.hypothesis_set.hypotheses for d in h.efficacy_dependencies if "residual" in d.dependency]
    assert dep.status == "unresolved" and "I909T, L1012P" in dep.why_it_matters
    assert dep.what_would_resolve_it == "express the exact substitution at matched abundance"
    assert "RUN_MECH" in dep.basis
    sc004 = next(c for c in r.hypothesis_set.submission_claims if c.id == "SC_004")
    assert "checkpoint activation (nocodazole response) returned once abundance was restored" in sc004.statement
    assert "remains unresolved" in sc004.statement
    from rarepipe.stages.track2.report import pitch
    r.sanitized.residual_function["class_level_variants"] = ["I909T", "L1012P"]
    text = pitch(r.sanitized, {"experiences": []})
    assert "I909T and L1012P" in text and "not proven for this child" in text


def test_a_mechanism_run_from_another_chain_is_refused(discovery, workspace, tmp_path):
    _, imap = _mechanism(tmp_path)
    other, _ = _mechanism(tmp_path / "x", run_id="RUN_OTHER")
    with pytest.raises(Track2UsageError, match="built from RUN_MECH"):
        make(discovery, workspace, tmp_path, intervention_map_run=imap, mechanism_run=other)


def test_a_superseding_session_replaces_the_earlier_record(discovery, workspace, tmp_path):
    from rarepipe.stages.track2.ingest import load_all

    save(workspace, import_hypotheses(workspace, _write(workspace, [_hypothesis()]), session_index=1))
    path = _write(workspace, [_hypothesis(statement="revised wording")], name="h2.yaml")
    payload = yaml.safe_load(path.read_text())
    payload["session"]["supersedes"] = "LLMRS_0001"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    save(workspace, import_hypotheses(workspace, path, session_index=2))
    sessions, hypotheses, _, _ = load_all(workspace)
    assert [s.session_id for s in sessions] == ["LLMRS_0002"] and sessions[0].supersedes == "LLMRS_0001"
    assert [h.statement for h in hypotheses] == ["revised wording"]
    assert (workspace / "hypotheses" / "LLMRS_0001.json").exists(), "the superseded record is kept, not deleted"
