"""Stage 06F — experiments, directness grading, residual-function decision, corpus refresh, comparison.

All variants below are either published ones or synthetic; no case data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from rarepipe.core.redaction import clear_restricted
from rarepipe.stages.mechanism import refresh as R
from rarepipe.stages.mechanism.compare import compare
from rarepipe.stages.mechanism.experiments import (
    Directness, ExperimentError, VariantExperiment, assess, child_missense, grade, load_experiments,
    notation_aliases)

DOC = ("forced overexpression of the poorly expressed substitution mutants I909T and L1012P to levels comparable "
       "to wild-type BUBR1 fully restored the response to nocodazole ( Fig. 4D ). This showed that these mutations "
       "do not impose significant constraints on BUBR1 function. L844F was poorly expressed and unable to restore "
       "any of the defects. Checkpoint function was restored by expression of wild-type LAP-BUBR1. "
       "The Ile909Thr protein was unstable.")


def child(pos: int = 905, alt: str = "Thr", transcript: str = "ENST00000287598.10") -> dict:
    return {"variants": [{"hgvs_protein": "p.Glu10Ter", "transcript": transcript},
                         {"hgvs_protein": f"p.(Ile{pos}{alt})", "transcript": transcript}]}


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "PMID_1.txt").write_text(DOC)
    return tmp_path


def exp(**kw) -> dict:
    base = dict(experiment_id="VX_1", source_id="PMID:1", variant_label="I909T", position=909, ref_residue="I",
                alt_residue="T", protein_tested="altered_protein", abundance_condition="restored_to_wild_type_level",
                function_at_restored_abundance="restored",
                readouts=[{"kind": "checkpoint_activity", "result": "restored",
                           "quote": "I909T and L1012P to levels comparable to wild-type BUBR1 fully restored"}])
    base.update(kw)
    return base


def write(tmp_path: Path, *items: dict) -> Path:
    path = tmp_path / "x.yaml"
    path.write_text(yaml.safe_dump({"experiments": list(items)}))
    return path


def test_quotes_are_verified_verbatim(corpus, tmp_path):
    assert load_experiments(write(tmp_path, exp()), corpus)[0].region == "protein kinase domain"
    bad = exp(readouts=[{"kind": "checkpoint_activity", "result": "restored", "quote": "I909T fully rescued everything"}])
    with pytest.raises(ExperimentError, match="not found verbatim"):
        load_experiments(write(tmp_path, bad), corpus)


def test_authors_interpretation_must_be_their_words(corpus, tmp_path):
    with pytest.raises(ExperimentError, match="verbatim"):
        load_experiments(write(tmp_path, exp(authors_interpretation="the mutations are harmless")), corpus)
    ok = exp(authors_interpretation="these mutations do not impose significant constraints on BUBR1 function")
    assert load_experiments(write(tmp_path, ok), corpus)


def test_variant_must_be_named_in_some_notation(corpus, tmp_path):
    three_letter = exp(readouts=[{"kind": "protein_turnover", "result": "increased",
                                  "quote": "The Ile909Thr protein was unstable."}],
                       abundance_condition="ectopic_below_wild_type", function_at_restored_abundance="not_tested")
    assert load_experiments(write(tmp_path, three_letter), corpus)
    unnamed = exp(variant_label="R814H", position=814, ref_residue="R", alt_residue="H")
    with pytest.raises(ExperimentError, match="no quote names R814H"):
        load_experiments(write(tmp_path, unnamed), corpus)
    assert {"Ile909Thr", "p.(Ile909Thr)", "LAP-I909T"} <= set(notation_aliases("I909T"))
    assert "*731" in notation_aliases("731X")


def test_restored_abundance_claims_need_a_restored_abundance_condition(corpus, tmp_path):
    low = exp(variant_label="L844F", position=844, abundance_condition="ectopic_below_wild_type",
              readouts=[{"kind": "checkpoint_activity", "result": "not_restored",
                         "quote": "L844F was poorly expressed and unable to restore"}])
    with pytest.raises(ExperimentError, match="not a restored-abundance test"):
        load_experiments(write(tmp_path, low), corpus)


def test_normal_protein_replacement_cannot_answer_residual_function(corpus, tmp_path):
    wt = exp(variant_label="WT", position=None, protein_tested="normal_protein_replacement",
             readouts=[{"kind": "checkpoint_activity", "result": "restored",
                        "quote": "Checkpoint function was restored by expression of wild-type LAP-BUBR1"}])
    with pytest.raises(ExperimentError, match="normal-protein replacement"):
        load_experiments(write(tmp_path, wt), corpus)


def _e(**kw) -> VariantExperiment:
    return VariantExperiment(**exp(**kw))


def test_directness_grades():
    c = child_missense(child(905))
    assert grade(_e(position=905, alt_residue="T"), c) is Directness.EXACT
    assert grade(_e(position=905, alt_residue="N"), c) is Directness.SAME_POSITION
    assert grade(_e(position=909), c) is Directness.NEARBY
    assert grade(_e(position=1012), c) is Directness.SAME_REGION
    assert grade(_e(position=155), c) is Directness.DIFFERENT_REGION
    assert grade(_e(variant_label="WT", position=None, protein_tested="normal_protein_replacement",
                    function_at_restored_abundance="not_tested"), c) is Directness.NOT_A_VARIANT_TEST
    assert grade(_e(position=905), child_missense(child(905, transcript="ENST00000999999.1"))) \
        is Directness.NUMBERING_UNVERIFIED


def test_class_evidence_does_not_decide_the_childs_allele():
    experiments = [_e(experiment_id="VX_1", position=909), _e(experiment_id="VX_2", variant_label="L1012P", position=1012)]
    a = assess(experiments, child_missense(child(850)))
    assert a.class_level == "function_persists"
    assert a.exact_allele == "insufficient"
    assert a.decision == "INSUFFICIENT"
    assert "leans toward function persisting" in a.decision_meaning
    assert "chromosome segregation and chromosome alignment" in a.class_level_basis


def test_exact_allele_decides_both_ways():
    ok = assess([_e(position=905)], child_missense(child(905)))
    assert ok.decision == "STRENGTHENS_STABILIZATION"
    bad = assess([_e(position=905, function_at_restored_abundance="impaired")], child_missense(child(905)))
    assert bad.decision == "WEAKENS_ABUNDANCE_ONLY"


def test_normal_protein_never_counts_toward_residual_function():
    wt = _e(variant_label="WT", position=None, protein_tested="normal_protein_replacement",
            function_at_restored_abundance="not_tested")
    a = assess([wt], child_missense(child(905)))
    assert a.class_level == "insufficient" and a.decision == "INSUFFICIENT"


def test_directness_never_leaves_the_private_artifact():
    experiments = [_e(position=909)]
    a = assess(experiments, child_missense(child(905)))
    assert experiments[0].directness is Directness.NEARBY and a.directness_counts and a.closest_experiment
    clear_restricted(experiments)
    clear_restricted(a)
    assert experiments[0].directness is None and a.directness_counts == {} and a.closest_experiment is None
    public = json.dumps(a.model_dump()) + json.dumps([e.model_dump() for e in experiments])
    assert "NEARBY" not in public and "905" not in public


def test_refresh_records_every_outcome_and_never_touches_the_frozen_corpus(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    (frozen / "docs").mkdir(parents=True)
    docs = [{"source_id": "PMID:1", "pmcid": "PMC1", "full_text": False, "content_hash": "sha256:a", "title": "One"},
            {"source_id": "PMID:2", "pmcid": "PMC2", "full_text": False, "content_hash": "sha256:b", "title": "Two"},
            {"source_id": "PMID:3", "pmcid": None, "full_text": False, "content_hash": "sha256:c", "title": "Three"},
            {"source_id": "PMID:4", "pmcid": "PMC4", "full_text": True, "content_hash": "sha256:d", "title": "Four"}]
    for d in docs:
        (frozen / "docs" / f"{d['source_id'].replace(':', '_')}.txt").write_text("abstract")
    (frozen / "corpus_index.json").write_text(json.dumps({"documents": docs, "corpus_digest": "sha256:old"}))
    before = {p.name: p.read_text() for p in (frozen / "docs").iterdir()}

    monkeypatch.setattr(R, "fetch_full_text", lambda pmcid: ("BODY", "licensed") if pmcid == "PMC1" else (None, "no body"))
    xml = b'<supplementary-material><label>S1</label><media xlink:href="s1.pdf"/></supplementary-material>'
    monkeypatch.setattr(R, "_get", lambda url: xml if "efetch" in url else b"<html>reCAPTCHA check</html>")

    run = R.refresh(frozen, tmp_path / "out")
    index = json.loads((run / "corpus_index.json").read_text())
    outcome = {r["source_id"]: r for r in index["refresh"]}
    assert outcome["PMID:1"]["after"] == "full_text_recovered"
    assert outcome["PMID:1"]["supplements"][0]["state"] == "inaccessible_bot_challenge"
    assert outcome["PMID:2"]["after"] == "still_abstract_only" and outcome["PMID:2"]["reason"] == "no body"
    assert outcome["PMID:3"]["after"] == "no_pmcid"
    assert "PMID:4" not in outcome
    assert all(r["retrieved_at"] for r in index["refresh"])
    assert index["refreshed_from"]["corpus_digest"] == "sha256:old" and index["corpus_digest"] != "sha256:old"
    assert "BODY" in (run / "docs" / "PMID_1.txt").read_text()
    assert {p.name: p.read_text() for p in (frozen / "docs").iterdir()} == before
    assert (run / "SHA256SUMS").exists()


def _dossier(documents, status="READY", claims=None, **extra) -> dict:
    return {"documents": documents, "status": status, "semantic_digest": "sha256:x",
            "readiness": {"exact_allele_mechanism_complete": False},
            "state": {"allele_b": {"protein_effect_status": "UNRESOLVED"}},
            "claims": claims or [{"id": "MC_1", "status": "SUPPORTED"}], **extra}


def test_comparison_rows_are_computed_not_written(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "mechanism_dossier.sanitized.json").write_text(json.dumps(_dossier([{"full_text": False}] * 2)))
    t2 = tmp_path / "t2"
    t2.mkdir()
    (t2 / "track2_hypothesis_set.sanitized.json").write_text(json.dumps({"semantic_digest": "sha256:t", "hypotheses": [
        {"efficacy_dependencies": [{"dependency": "residual function: must work", "status": "unresolved",
                                    "why_it_matters": "not measured"}]}]}))
    rf = assess([_e(position=909)], child_missense(child(850))).model_dump(mode="json")
    new = _dossier([{"full_text": True}, {"full_text": False}], residual_function=rf, variant_experiments=[{}],
                   corpus_refresh=[{"supplements": [{"state": "inaccessible_bot_challenge"}]}])
    c = compare(base, new, t2, "v0.1.2")
    rows = {r.topic: r for r in c.rows}
    assert rows["documents with full text"].changed and rows["documents with full text"].now == "1 of 2"
    assert not rows["disease-mechanism status"].changed
    assert rows["supplementary files read"].now == "0 of 1 listed"
    assert "unresolved: not measured" in rows["residual function — this child's allele"].frozen
    assert any("Stage 09" in x for x in c.regenerate)


def test_direction_corrections_need_a_reason_and_report_stale_matches(tmp_path):
    from rarepipe.stages.mechanism.research import ResearchError, load_corrections

    (tmp_path / "corrections").mkdir()
    (tmp_path / "corrections" / "a.yaml").write_text(yaml.safe_dump({"corrections": [
        {"source_id": "PMID:1", "quote_contains": "x", "direction": "uncertain", "reason": " ", "reviewed_by": "r"}]}))
    with pytest.raises(ResearchError, match="needs a reason"):
        load_corrections(tmp_path)
    (tmp_path / "corrections" / "a.yaml").write_text(yaml.safe_dump({"corrections": [
        {"source_id": "PMID:1", "quote_contains": "x", "direction": "uncertain", "reason": "cue word",
         "reviewed_by": "r"}]}))
    (tmp_path / "corrections" / "._a.yaml").write_bytes(b"\x00\x05\x16\x07\xb0")
    [c] = load_corrections(tmp_path)
    assert c.applied_to == 0 and c.direction.value == "uncertain"
