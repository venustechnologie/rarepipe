"""Stage 04 — evidence adjudication. Offline; the fake solver's outputs stand in for a real candidate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rarepipe.core.console import Console
from rarepipe.stages.adjudicate.model import Direction, EvidenceClass, Strength
from rarepipe.stages.adjudicate.stage import AdjudicateRequest, AdjudicateUsageError, run_adjudication
from rarepipe.stages.baseline import exomiser
from rarepipe.stages.baseline.stage import BaselineRequest, run_baseline
from rarepipe.testing import baseline_fixtures as bf
from rarepipe.testing import normalize_fixtures as nf


@pytest.fixture(scope="module")
def candidate_set(tmp_path_factory):
    """A full 01 → 02 → 03 chain over synthetic data, then Stage 04 on its leading pair."""
    from rarepipe.stages.normalize.stage import NormalizeRequest, run_normalize

    tmp = tmp_path_factory.mktemp("adj")
    root = nf.build_case(tmp / "case", hpo_terms=["HP:0001250", "HP:0001263", "HP:0000252", "HP:0000007"])
    manifest = nf.run_intake_for(root, tmp / "intake")
    res = nf.build_resources(tmp / "resources")
    norm = run_normalize(NormalizeRequest(manifest=manifest, output=tmp / "norm", resources=res), Console(quiet=True))

    import pytest as _pytest

    mp = _pytest.MonkeyPatch()
    mp.setattr(exomiser, "run_job", bf.fake_run_job)
    mp.setattr(exomiser, "locate", lambda home, data: bf.fake_installation(tmp))
    baseline = run_baseline(BaselineRequest(normalized_case=norm.run_dir / "normalized_case.private.json",
                                            output=tmp / "baseline", exomiser_home=tmp / "exomiser"), Console(quiet=True))
    mp.undo()
    return tmp, baseline


@pytest.fixture
def adjudicated(candidate_set, tmp_path):
    tmp, baseline = candidate_set

    def _run(**kw):
        return run_adjudication(AdjudicateRequest(raw_candidate_set=baseline.run_dir / "raw_candidate_set.private.json",
                                                  output=tmp_path / "adj", **kw), Console(quiet=True))

    return _run


def test_leading_variant_pair_is_selected_and_both_variants_adjudicated(adjudicated):
    h = adjudicated().hypothesis
    assert h.gene_symbol == "SYNGENE1" and h.inheritance_model == "AR"
    assert [v.role for v in h.variants] == ["variant_a", "variant_b"]
    assert all(v.normalization_basis for v in h.variants)
    assert {c.claim_id for c in h.claims} == {"CLAIM_VARIANT_A", "CLAIM_VARIANT_B", "CLAIM_MECHANISM", "CLAIM_CONFIGURATION"}


def test_three_questions_are_kept_separate(adjudicated):
    h = adjudicated().hypothesis
    subjects = {c.subject: c for c in h.claims}
    assert subjects["gene_disease_mechanism"].assessment == "not_assessed"  # not retrievable locally; not faked
    assert subjects["configuration"].assessment == "unresolved"
    # no single collapsed score anywhere
    assert h.evidence_summary.overall in ("supported", "unresolved", "contradicted")
    assert not hasattr(h, "score")


def test_every_assertion_carries_provenance_strength_basis_and_limitations(adjudicated):
    h = adjudicated().hypothesis
    assert h.assertions
    for a in h.assertions:
        assert a.provenance.source and a.provenance.retrieval
        assert a.strength_basis and len(a.strength_basis) > 20
        assert a.claim_id in {c.claim_id for c in h.claims}
        if a.strength != Strength.NOT_APPLICABLE:
            assert a.limitations, f"{a.assertion_id} has no stated limitation"


def test_uncalibrated_predictors_do_not_claim_evidence_strength(adjudicated):
    h = adjudicated().hypothesis
    for a in h.assertions:
        if a.evidence_class == EvidenceClass.COMPUTATIONAL and "REVEL" not in (a.provenance.identifier or ""):
            assert a.strength == Strength.INDETERMINATE, f"{a.provenance.identifier} claimed strength {a.strength}"
            assert "not ClinGen-calibrated" in a.strength_basis or "No ClinGen-calibrated" in a.strength_basis


def test_contradicting_evidence_is_always_present_as_a_field(adjudicated):
    h = adjudicated().hypothesis
    assert isinstance(h.contradicting_assertion_ids, list)  # present even when empty
    assert all(by_id(h, i).direction == Direction.CONTRADICTS for i in h.contradicting_assertion_ids)


def by_id(h, assertion_id):
    return next(a for a in h.assertions if a.assertion_id == assertion_id)


def test_phase_is_recorded_not_inferred(adjudicated):
    h = adjudicated().hypothesis
    assert h.phase.status == "unresolved"
    assert "absence of evidence" in h.phase.note.lower()
    assert h.phase.parental_data == "unavailable" and h.phase.long_range_phase == "not_evaluated"


def test_evidence_request_asks_the_smallest_question(adjudicated):
    h = adjudicated().hypothesis
    req = next(r for r in h.evidence_requests if r.request_id == "REQ_PARENTAL_TRANSMISSION")
    assert req.raw_data_required is False
    assert "transmission" in req.minimum_information.lower()
    assert "not requesting parental sequence data" in req.draft_message
    assert req.blocks_this_stage is False


def test_what_would_change_our_mind_has_both_directions(adjudicated):
    h = adjudicated().hypothesis
    directions = {m.direction for m in h.what_would_change_our_mind}
    assert directions == {"would_strengthen", "would_weaken"}
    assert all(m.why for m in h.what_would_change_our_mind)


def test_next_actions_are_ranked_and_expensive_phasing_is_not_recommended(adjudicated):
    h = adjudicated().hypothesis
    actions = {a.action: a for a in h.next_actions}
    align = next(a for a in h.next_actions if "FASTQ" in a.action)
    assert align.cost == "very_high" and align.expected_information_gain in ("low", "uncertain")
    ask = next(a for a in h.next_actions if "organizers" in a.action)
    assert ask.expected_information_gain == "high" and ask.cost == "very_low"


def test_gaps_are_stated_rather_than_filled(adjudicated):
    h = adjudicated().hypothesis
    text = " ".join(h.evidence_gaps).lower()
    assert "functional" in text and "gene–disease validity" in text or "gene-disease validity" in text
    assert h.evidence_summary.functional.startswith("absent")


def test_no_diagnosis_therapy_or_classification_language(adjudicated):
    result = adjudicated()
    full = (result.run_dir / "adjudication_report.md").read_text().lower()
    body = full.split("## not done here")[0]  # the disclaimer legitimately names what is excluded
    for word in ("diagnosis is", "we recommend", "treatment", "therapy", "drug", "prescribe", "pathogenic variant causes"):
        assert word not in body, f"report body contains '{word}'"
    assert "not a diagnosis" in full and "not a clinical variant classification" in full
    assert not result.hypothesis.provisional_classifications  # none claimed unless explicitly justified


def test_case_specific_detail_is_private_only(adjudicated):
    result = adjudicated()
    priv = json.loads((result.run_dir / "adjudicated_hypothesis.private.json").read_text())
    san = json.loads((result.run_dir / "adjudicated_hypothesis.sanitized.json").read_text())
    assert priv["variants"][0]["position"] and priv["variants"][0]["contig"]
    assert san["variants"][0]["position"] is None and san["variants"][0]["contig"] is None
    assert san["variants"][0]["molecular_consequence"]  # the consequence is the finding, and survives
    report_text = (result.run_dir / "adjudication_report.md").read_text()
    assert "10001" not in report_text and "SYNTHKID" not in report_text


def test_sanitized_input_is_refused(candidate_set, tmp_path):
    tmp, baseline = candidate_set
    with pytest.raises(AdjudicateUsageError):
        run_adjudication(AdjudicateRequest(raw_candidate_set=baseline.run_dir / "raw_candidate_set.sanitized.json",
                                           output=tmp_path / "x"), Console(quiet=True))


def test_rerun_is_semantically_identical(adjudicated, tmp_path):
    first = adjudicated().hypothesis
    second = run_adjudication(AdjudicateRequest(raw_candidate_set=Path(first.execution.raw_candidate_set_path),
                                                output=tmp_path / "adj2"), Console(quiet=True)).hypothesis
    assert first.semantic_digest == second.semantic_digest
    assert first.execution.run_id != second.execution.run_id


def test_committed_schema_matches_code():
    from rarepipe.stages.adjudicate.schema import schema_json

    committed = (Path(__file__).resolve().parents[1] / "schemas" / "adjudicated_hypothesis.schema.json").read_text()
    assert committed == schema_json()
