"""Stage 07 — intervention logic. It must define what a treatment would do, and name no treatment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rarepipe.stages.intervention.model import Direction, PointStatus, Status
from rarepipe.stages.intervention.stage import (
    BuildRequest,
    InterventionUsageError,
    build,
    negative_predictions,
)


def _evidence(eid, source, assay, result, rescue=False, level="primary_literature", direction="supports",
              quote="q"):
    return {"evidence_id": eid, "source_id": source, "statement": f"{assay} {result}", "quote": quote,
            "epistemic_class": "external_evidence", "evidence_level": level, "experimental_level": "not_applicable",
            "scope": "gene_level", "applicability_to_case": "indirect", "direction": direction, "assay": assay,
            "result": result, "rescue_experiment": rescue, "limitations": [], "extracted_by": "test",
            "verified_from_source": True}


def _claim(cid, ctype, status, evidence=(), statement="s"):
    return {"id": cid, "type": ctype, "statement": statement, "status": status, "scope": "gene_level",
            "epistemic_class": "external_evidence", "evidence": list(evidence), "indirect_evidence": [],
            "contradicting_evidence": [], "limitations": []}


@pytest.fixture
def dossier(tmp_path: Path) -> Path:
    evidence = [
        _evidence("EV_0001", "PMID:111", "rescue / complementation", "restored checkpoint", rescue=True,
                  level="human_experimental",
                  quote="Ectopic expression of BUBR1 restored mitotic checkpoint activity in patient cells."),
        _evidence("EV_0004", "PMID:333", "rescue / complementation", "restored checkpoint in ARF-null cells",
                  rescue=True, level="animal_model",
                  quote="Expression of ARF-YFP was sufficient to restore mitotic checkpoint activity in ARF-/- cells."),
        _evidence("EV_0002", "PMID:111", "mitotic checkpoint activity", "impaired", level="human_experimental"),
        _evidence("EV_0003", "PMID:222", "aneuploidy / karyotype", "mosaic aneuploidy"),
        _evidence("EV_AG_1", "ALPHAGENOME_ATLAS:BUB1B:1-2", "AlphaGenome Atlas AVI_SCORE_FEATURE_IMPORTANCE:ALPHAMISSENSE", "0.76"),
        _evidence("EV_AG_2", "ALPHAGENOME_ATLAS:BUB1B:1-2", "AlphaGenome Atlas AVI_SCORE_FEATURE_IMPORTANCE:MERGED_SPLICING", "0.015"),
        _evidence("EV_AG_3", "ALPHAGENOME_ATLAS:BUB1B:1-2", "AlphaGenome Atlas AVI_SCORE_FEATURE_IMPORTANCE:MAX_ABS_RNA_SEQ", "0.0038"),
    ]
    claims = [_claim(f"MC_{i:04d}", t, s, e) for i, t, s, e in [
        (1, "gene_disease", "SUPPORTED", ["EV_0003"]), (2, "transcript_effect", "SUPPORTED", []),
        (3, "transcript_effect", "SUPPORTED", []), (4, "protein_effect", "SUPPORTED", ["EV_0001"]),
        (5, "protein_effect", "PARTIALLY_SUPPORTED", ["EV_0001"]), (6, "protein_effect", "UNRESOLVED", []),
        (7, "combined_genotype", "PARTIALLY_SUPPORTED", []), (8, "checkpoint_effect", "PARTIALLY_SUPPORTED", ["EV_0002"]),
        (9, "segregation_effect", "PARTIALLY_SUPPORTED", ["EV_0002"]), (10, "aneuploidy", "PARTIALLY_SUPPORTED", ["EV_0003"]),
        (11, "disease_bridge", "SUPPORTED", ["EV_0003"]), (12, "protein_effect", "PARTIALLY_SUPPORTED", ["EV_0001"]),
        (13, "protein_effect", "PARTIALLY_SUPPORTED", [])]]
    claims.append({"id": "MC_IMP_LLMRS_0001_01", "type": "checkpoint_effect",
                   "statement": "A checkpoint defect can be rescued by restoring the missing regulator.",
                   "status": "PARTIALLY_SUPPORTED", "scope": "gene_level", "epistemic_class": "derived_inference",
                   "evidence": ["EV_0004"], "indirect_evidence": [], "contradicting_evidence": [], "limitations": []})
    payload = {
        "case_id": "CASE_X", "visibility": "private", "gene_symbol": "BUB1B",
        "status": "MECHANISM_READY_FOR_INTERVENTION_SEARCH", "semantic_digest": "sha256:m",
        "claims": claims, "evidence": evidence,
        "state": {"allele_b": {"protein_effect_status": "UNRESOLVED"}, "gene_symbol": "BUB1B"},
        "graph": {"nodes": [], "edges": [], "unknown_edges": [], "qualifications": ["MC_X: a ciliary role exists"]},
        "assays": [{"assay": "BUBR1 protein abundance", "sources": ["PMID:111"]},
                   {"assay": "mitotic checkpoint activity", "sources": ["PMID:111"]},
                   {"assay": "aneuploidy / karyotype", "sources": ["PMID:222"]}],
        "knowledge_tasks": [{"id": "KT_0001"}], "execution": {"run_id": "RUN_MECH"},
        "provenance": {"validation_run_id": "RUN_VAL"}}
    run = tmp_path / "mechanism" / "RUN_MECH"
    run.mkdir(parents=True)
    (run / "mechanism_dossier.private.json").write_text(json.dumps(payload))
    return run


def make(dossier, tmp_path, **kw):
    return build(BuildRequest(mechanism_run=dossier, output=tmp_path / "intervention", argv=["t"], **kw))


def test_no_medication_is_named_anywhere(dossier, tmp_path):
    r = make(dossier, tmp_path)
    text = (r.run_dir / "intervention_logic.md").read_text().lower()
    blob = json.dumps(r.intervention_map.model_dump(mode="json")).lower()
    # Terms that would indicate an actual candidate or a recommendation — not the word "drug",
    # which the stage's own disclaimer has to be allowed to use.
    for forbidden in ("mg/kg", "dose of", "prescrib", "we recommend treating", "should be given",
                      "drugbank", "drugcentral", "chembl", "dailymed", "open targets", "fda label",
                      "candidate medication", "candidate compound", "therapeutic option for this"):
        assert forbidden not in text, f"{forbidden!r} in the report"
        assert forbidden not in blob, f"{forbidden!r} in the artifact"
    assert "no medication, compound or drug class is named" in text
    assert "no drug, chemical or medication database was consulted" in text


def test_every_intervention_point_has_an_explicit_direction(dossier, tmp_path):
    r = make(dossier, tmp_path)
    for point in r.intervention_map.intervention_points:
        assert point.desired_effect.direction is not None
        if point.status is PointStatus.SUPPORTED:
            assert point.desired_effect.direction is not Direction.UNKNOWN
            assert point.validation_endpoints.cellular, "a supported point needs a measurable endpoint"
            assert point.establishing_rescue_evidence, "a supported point needs establishing rescue evidence"


def test_forbidden_directions_come_from_mechanism_not_from_a_predictor(dossier, tmp_path):
    r = make(dossier, tmp_path)
    assert r.intervention_map.forbidden_effects
    for effect in r.intervention_map.forbidden_effects:
        assert effect.derived_from in ("mechanism_graph", "functional_evidence")
        for eid in effect.evidence:
            source = next(e for e in json.loads((dossier / "mechanism_dossier.private.json").read_text())["evidence"]
                          if e["evidence_id"] == eid)
            assert not source["source_id"].startswith("ALPHAGENOME"), "a prediction cannot forbid a direction"


def test_a_weak_model_signal_deprioritizes_and_does_not_refute(dossier, tmp_path):
    r = make(dossier, tmp_path)
    negatives = r.intervention_map.negative_predictions
    assert {n.hypothesis for n in negatives} == {"major_splice_effect", "transcriptional_or_expression_effect"}
    for n in negatives:
        assert n.consequence == "deprioritize"
        assert "does not establish" or n.does_not_establish
        assert n.strength == "computational_only"
    for axis in r.intervention_map.deprioritized_axes:
        assert axis.state.value == "DEPRIORITIZED" and axis.reopen_if
    text = (r.run_dir / "intervention_logic.md").read_text()
    assert "never a refutation" in text


def test_a_point_depending_on_the_unresolved_allele_is_not_justified(dossier, tmp_path):
    r = make(dossier, tmp_path)
    exact = next(p for p in r.intervention_map.intervention_points if p.requires_exact_allele_mechanism)
    assert exact.status is PointStatus.NOT_JUSTIFIED
    assert any("unresolved" in limit for limit in exact.limitations)
    assert all(not s.exact_allele_dependency for s in r.intervention_map.search_specs)


def test_the_first_point_stays_broad_rather_than_naming_a_modality(dossier, tmp_path):
    r = make(dossier, tmp_path)
    ip1 = r.intervention_map.intervention_points[0]
    assert ip1.desired_effect.direction is Direction.RESTORE
    assert "stabilis" not in ip1.biological_state and "stabiliz" not in ip1.biological_state
    assert ip1.requires_exact_allele_mechanism is False


def test_search_specs_say_what_must_not_happen(dossier, tmp_path):
    r = make(dossier, tmp_path)
    assert r.intervention_map.search_specs
    for spec in r.intervention_map.search_specs:
        assert spec.disallowed_mechanisms and spec.expected_rescue_readout
        assert spec.constraints.get("pediatric_case") is True


def test_a_blocked_mechanism_cannot_produce_intervention_logic(dossier, tmp_path):
    payload = json.loads((dossier / "mechanism_dossier.private.json").read_text())
    payload["status"] = "MECHANISM_BLOCKED"
    (dossier / "mechanism_dossier.private.json").write_text(json.dumps(payload))
    with pytest.raises(InterventionUsageError):
        make(dossier, tmp_path)


def test_negative_prediction_needs_atlas_evidence_to_exist():
    assert negative_predictions([]) == []
    assert negative_predictions([_evidence("EV_1", "PMID:1", "checkpoint", "x")]) == []


def test_action_outcomes_record_what_the_research_bought(dossier, tmp_path):
    r = make(dossier, tmp_path)
    outcomes = r.intervention_map.action_outcomes
    assert outcomes and all(o.lesson for o in outcomes)
    assert any(o.information_gain == "none" for o in outcomes), "a null result must be recorded as one"


def test_adjacent_rescue_evidence_does_not_count_as_establishing(dossier, tmp_path):
    """Rescue somewhere on this biology is not the bypass this point claims."""
    r = make(dossier, tmp_path)
    ip2 = next(p for p in r.intervention_map.intervention_points if p.id == "IP_002")
    assert ip2.establishing_rescue_evidence == [], "restoring a different regulator is not downstream compensation"
    assert ip2.related_rescue_evidence, "the adjacent evidence must still be recorded, not dropped"
    assert all(rel.why_not_establishing for rel in ip2.related_rescue_evidence)
    assert ip2.rescue_criterion and "WITHOUT restoring" in ip2.rescue_criterion
    assert ip2.status is PointStatus.UNRESOLVED

    ip1 = next(p for p in r.intervention_map.intervention_points if p.id == "IP_001")
    assert ip1.establishing_rescue_evidence, "restoring BUBR1 itself does establish IP_001"

    text = (r.run_dir / "intervention_logic.md").read_text()
    assert "does not establish this point" in text
    assert "counts as establishing only if" in text


def test_the_rescue_classifier_reads_what_was_restored(dossier, tmp_path):
    from rarepipe.stages.intervention.stage import classify_rescue

    bubr1 = {"quote": "Ectopic expression of BUBR1 restored mitotic checkpoint activity.", "statement": ""}
    other = {"quote": "Expression of ARF-YFP was sufficient to restore mitotic checkpoint activity in ARF-/- cells.",
             "statement": ""}
    bypass = {"quote": "Aneuploidy was reduced in BUB1B-deficient cells by an intervention acting downstream.",
              "statement": ""}
    assert classify_rescue(bubr1, "IP_001") == "establishing"
    assert classify_rescue(other, "IP_001") == "related"
    assert classify_rescue(other, "IP_002") == "related"
    assert classify_rescue(bubr1, "IP_002") == "related", "restoring the gene is not downstream compensation"
    assert classify_rescue(bypass, "IP_002") == "establishing"


def test_the_search_spec_will_not_accept_generic_mitotic_improvement(dossier, tmp_path):
    r = make(dossier, tmp_path)
    spec = r.intervention_map.search_specs[0]
    assert len(spec.acceptable_mechanisms) == 2
    assert spec.acceptable_mechanisms[0].startswith("A.") and spec.acceptable_mechanisms[1].startswith("B.")
    assert "BUB1B-deficient" in spec.acceptable_mechanisms[1]
    assert spec.insufficient_for_match, "generic mitotic improvement must be named as insufficient"
    assert "discovery evidence only" in spec.insufficient_for_match[0]
    assert not any("improving mitotic fidelity in cells deficient for it" in m for m in spec.acceptable_mechanisms)
    text = (r.run_dir / "intervention_logic.md").read_text()
    assert "not sufficient for a mechanism match" in text
