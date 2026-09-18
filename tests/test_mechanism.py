"""Stage 06 — the stage exists to stop a fluent story replacing evidence, so the tests attack that."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rarepipe.stages.adjudicate.disclosure import DisclosureRefused
from rarepipe.stages.mechanism import claims as C
from rarepipe.stages.mechanism import extract, llm, questions
from rarepipe.stages.mechanism.model import (
    ClaimStatus,
    Direction,
    EpistemicClass,
    EvidenceLevel,
    EvidenceRecord,
    ExperimentalLevel,
    RetrievedDocument,
    Scope,
    Status,
)
from rarepipe.stages.mechanism.retrieve import RetrievalRefused, check_search_query, relevance
from rarepipe.stages.mechanism.stage import MechanismUsageError, ResolveRequest, residue_needles, run_resolve

PATIENT_TEXT = (
    "Molecular causes for BUBR1 dysfunction. Here, we show that cell lines derived from MVA patients with biallelic "
    "BUB1B mutations have an impaired mitotic checkpoint, chromosome alignment defects, and low overall BUBR1 protein "
    "abundance. Ectopic expression of BUBR1 restored mitotic checkpoint activity in patient cells. Karyotyping "
    "confirmed mosaic variegated aneuploidy with trisomy and monosomy in these patients. Nonsense-mediated decay of "
    "the truncating BUB1B transcript was demonstrated by RT-PCR in patient fibroblasts."
)
CONTRA_TEXT = (
    "In Bub1b transgenic MEFs, BUBR1 protein levels were unchanged compared to wild-type. There was no significant "
    "difference in aneuploidy rates between mutant and wild-type MEFs, and the kinase activity of BUBR1 was "
    "dispensable for checkpoint signalling in this system."
)


def _doc(source_id: str, title: str, year: int = 2010) -> dict:
    return {"source_id": source_id, "source_type": "journal_article", "title": title, "pmid": source_id.split(":")[1],
            "retrieved_at": "2026-09-18T00:00:00+00:00", "query": "BUB1B patient cells checkpoint",
            "content_hash": "sha256:x", "full_text": True, "pub_year": year, "characters_stored": 100}


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus" / "RUN_TEST"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "PMID_111.txt").write_text(PATIENT_TEXT)
    (root / "docs" / "PMID_222.txt").write_text(CONTRA_TEXT)
    index = {"schema": {"name": "MechanismCorpus", "version": "1.0.0"}, "created_at": "2026-09-18T00:00:00+00:00",
             "corpus_digest": "sha256:corpus", "llm": {"provider": "none", "model": "deterministic_fallback"},
             "documents": [_doc("PMID:111", "Molecular causes for BUBR1 dysfunction in MVA"),
                           _doc("PMID:222", "Bub1b domain requirements in mice", 2016)],
             "knowledge_tasks": [t.model_dump(mode="json") for t in questions.seed_tasks()],
             "query_log": [], "agent_runs": []}
    (root / "corpus_index.json").write_text(json.dumps(index))
    return root


@pytest.fixture
def adjudication(tmp_path: Path) -> Path:
    payload = {
        "case_id": "CASE_X", "visibility": "private", "gene_symbol": "BUB1B", "inheritance_model": "AR",
        "variants": [
            {"role": "variant_a", "assembly": "GRCh38", "contig": "chr15", "position": 40200000, "ref": "C",
             "alt": "T", "molecular_consequence": "stop_gained", "hgvs_protein": None},
            {"role": "variant_b", "assembly": "GRCh38", "contig": "chr15", "position": 40210911, "ref": "G",
             "alt": "A", "molecular_consequence": "missense_variant", "hgvs_protein": "p.(Asn1067Ser)",
             "hgvs": "c.3200A>G"}],
        "claims": [], "assertions": [
            {"assertion_id": "EA_1", "claim_id": "CLAIM_VARIANT_B", "evidence_class": "molecular_mechanistic",
             "statement": "The affected residue lies within an annotated functional feature of the protein.",
             "direction": "supports", "result": "Domain: Protein kinase (766-1050); reference residue confirmed",
             "limitations": []},
            {"assertion_id": "EA_2", "claim_id": "CLAIM_VARIANT_B", "evidence_class": "computational",
             "statement": "REVEL scores this missense variant 0.472, which falls in the indeterminate band.",
             "direction": "uncertain", "result": "0.472", "limitations": []}],
        "evidence_summary": {"overall": "unresolved"}, "phase": {"status": "unresolved", "note": "no read-backed phase"},
        "semantic_digest": "sha256:adj", "execution": {"run_id": "RUN_ADJ"},
        "provenance": {"source_hypothesis": {"raw_candidate_set_run_id": "RUN_BASE", "solver_rank": 1}}}
    path = tmp_path / "adjudicated_hypothesis.private.json"
    path.write_text(json.dumps(payload))
    return path


def resolve(corpus, adjudication, tmp_path, **kw):
    return run_resolve(ResolveRequest(corpus_run=corpus, adjudication=adjudication,
                                      output=tmp_path / "mechanism", argv=["test"], **kw))


# ── the disclosure boundary ─────────────────────────────────────────────────

def test_case_identity_and_drug_hunting_are_both_refused_before_a_query_is_sent():
    assert check_search_query("BUB1B BUBR1 kinase domain protein abundance")
    with pytest.raises(DisclosureRefused):
        check_search_query("BUB1B p.(Asn1067Ser) functional assay")
    for drug_query in ("BUB1B inhibitor treatment", "BUBR1 gene therapy rescue", "aneuploidy drug repurposing"):
        with pytest.raises(RetrievalRefused):
            check_search_query(drug_query)


def test_the_exact_allele_is_searched_locally_and_never_becomes_a_query(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    needles, _ = residue_needles(json.loads(adjudication.read_text()))
    assert needles, "the missense allele produced no local search pattern"
    for record in r.dossier.query_log:
        for needle in needles:
            assert needle not in record.query
    for task in r.dossier.knowledge_tasks:
        if task.disclosure_level.value == "local_only":
            assert task.status == "completed" and not task.queries


def test_sanitized_dossier_carries_no_case_identity(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    needles, _ = residue_needles(json.loads(adjudication.read_text()))
    blob = json.dumps(r.sanitized.model_dump(mode="json")) + (r.run_dir / "mechanism_dossier.md").read_text()
    for needle in needles:
        assert needle not in blob, f"{needle} reached a sanitized artifact"
    assert "40210911" not in blob and "chr15" not in blob


# ── evidence discipline ─────────────────────────────────────────────────────

def test_every_evidence_quote_is_re_found_in_its_stored_source(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    literature = [e for e in r.dossier.evidence if e.source_id.startswith("PMID")]
    assert literature and all(e.verified_from_source for e in literature)
    for e in literature[:10]:
        stored = (corpus / "docs" / f"{e.source_id.replace(':', '_')}.txt").read_text()
        assert e.quote.rstrip(".") in stored or e.quote[:-3] in stored


def test_a_fabricated_quote_is_rejected_as_an_invalid_inference(corpus):
    doc = RetrievedDocument(**_doc("PMID:111", "Molecular causes for BUBR1 dysfunction in MVA"))
    fabricated = EvidenceRecord(
        evidence_id="EV_9999", source_id="PMID:111",
        statement="BUBR1 loss causes premature chromatid separation.",
        quote="This sentence does not appear anywhere in the stored source.",
        epistemic_class=EpistemicClass.EXTERNAL_EVIDENCE, evidence_level=EvidenceLevel.PRIMARY_LITERATURE,
        scope=Scope.GENE_LEVEL, applicability_to_case="indirect", direction=Direction.SUPPORTS,
        extracted_by="llm:pretend-model:evidence_extractor_v1")
    good, invalid = extract.verify([fabricated], {"PMID:111": doc}, corpus)
    assert not good and invalid[0].reason == "quote_not_found_in_source"
    missing_source = fabricated.model_copy(update={"source_id": "PMID:999"})
    good, invalid = extract.verify([missing_source], {"PMID:111": doc}, corpus)
    assert not good and invalid[0].reason == "source_not_in_corpus"


def test_class_level_evidence_cannot_establish_a_claim_about_this_childs_allele(corpus, adjudication, tmp_path):
    """The whole point of `scope`: other kinase-domain variants are not this allele."""
    r = resolve(corpus, adjudication, tmp_path)
    by_id = {c.id: c for c in r.dossier.claims}
    exact = by_id["MC_0006"]
    klass = by_id["MC_0005"]
    assert klass.status is not ClaimStatus.UNRESOLVED and klass.evidence
    assert exact.status is ClaimStatus.UNRESOLVED and not exact.evidence
    assert exact.unknown_reason
    assert any("scope" in limit for limit in exact.limitations)


def test_predictors_and_domain_annotations_are_recorded_but_cannot_establish_function(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    exact = next(c for c in r.dossier.claims if c.id == "MC_0006")
    assert exact.indirect_evidence, "the predictor and domain evidence should be recorded, not discarded"
    levels = {e.evidence_level for e in r.dossier.evidence if e.evidence_id in exact.indirect_evidence}
    assert levels <= {EvidenceLevel.THIS_CASE, EvidenceLevel.COMPUTATIONAL}
    assert exact.status is ClaimStatus.UNRESOLVED


def test_a_claim_that_is_not_unresolved_always_cites_evidence(corpus, adjudication, tmp_path):
    """Fail closed on citations (PRD 006 §33)."""
    r = resolve(corpus, adjudication, tmp_path)
    for claim in r.dossier.claims:
        if claim.status is not ClaimStatus.UNRESOLVED:
            assert claim.evidence or claim.contradicting_evidence, f"{claim.id} asserts a status with no evidence"


def test_unknown_links_stay_in_the_graph(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.graph.unknown_edges
    unresolved = [e for e in r.dossier.graph.edges if e.status is ClaimStatus.UNRESOLVED]
    assert unresolved and all(f"{e.from_node} → {e.to_node}" in r.dossier.graph.unknown_edges for e in unresolved)


def test_contradicting_evidence_survives_into_the_dossier(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.contradictions, "the corpus contains contradicting statements and they must not be smoothed away"
    assert any(e.direction is Direction.CONTRADICTS for e in r.dossier.evidence)


def test_disagreeing_sources_become_separate_mechanistic_classes_not_an_average(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    classes = r.dossier.state.mechanistic_classes
    assert any("reduce" in c for c in classes) and any("preserved" in c or "unchanged" in c for c in classes)


# ── the gate ────────────────────────────────────────────────────────────────

def test_an_unresolved_disease_chain_blocks_intervention_search(corpus, adjudication, tmp_path):
    """A corpus that measures nothing must not produce a mechanism ready to act on."""
    for name in ("PMID_111.txt", "PMID_222.txt"):
        (corpus / "docs" / name).write_text("BUB1B is a gene discussed in the context of mitosis.")
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.status is Status.BLOCKED
    assert "unresolved" in r.dossier.status_basis.lower()
    assert r.dossier.next_actions[-1].importance_for_intervention_search == "blocking"


def test_a_contradicted_chain_also_blocks(corpus, adjudication, tmp_path):
    (corpus / "docs" / "PMID_111.txt").write_text(
        "In MVA patient cells the karyotype showed no significant difference in aneuploidy compared with controls, "
        "and mosaic variegated aneuploidy was not detected.")
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.status is Status.BLOCKED
    assert "contradicted" in r.dossier.status_basis.lower()


def test_no_intervention_reasoning_appears_anywhere_in_the_dossier(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    text = (r.run_dir / "mechanism_dossier.md").read_text().lower()
    for forbidden in ("we recommend", "treatment with", "should be treated", "therapeutic option", "drug candidate"):
        assert forbidden not in text
    assert "no drug, treatment, repurposing or intervention reasoning" in text


def test_sanitized_adjudication_is_refused(corpus, adjudication, tmp_path):
    payload = json.loads(adjudication.read_text())
    payload["visibility"] = "sanitized"
    bad = tmp_path / "sanitized.json"
    bad.write_text(json.dumps(payload))
    with pytest.raises(MechanismUsageError):
        run_resolve(ResolveRequest(corpus_run=corpus, adjudication=bad, output=tmp_path / "out", argv=["t"]))


# ── the research process is data ────────────────────────────────────────────

def test_knowledge_tasks_and_queries_are_recorded_with_stop_reasons(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.knowledge_tasks
    for task in r.dossier.knowledge_tasks:
        assert task.question and task.reason
        if task.status == "completed":
            assert task.stop_reason


def test_agent_prompts_are_versioned_artifacts():
    for name in ("query_planner", "evidence_extractor", "contradiction_agent", "mechanism_synthesizer", "paper_triage"):
        prompt = llm.load_prompt(name)
        assert prompt.version and len(prompt.sha256) == 64
        assert "never" in prompt.text.lower() or "not" in prompt.text.lower()


def test_a_run_without_an_llm_says_so_rather_than_implying_agents_ran(corpus, adjudication, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.provenance.agent_runs
    assert all(run.provider == "none" and "no provider was configured" in run.note
               for run in r.dossier.provenance.agent_runs)
    assert all(e.extracted_by.startswith("rarepipe.") for e in r.dossier.evidence)


def test_triage_scores_patient_evidence_above_background():
    patient = {"title": "Molecular causes for BUBR1 dysfunction in MVA patient cells",
               "abstractText": "Patient-derived cell lines showed impaired mitotic checkpoint and reduced BUBR1 protein abundance; rescue restored function."}
    background = {"title": "BUB1B expression in colorectal cancer prognosis",
                  "abstractText": "We performed a bioinformatic analysis of BUB1B expression as a biomarker for prognosis."}
    assert relevance(patient)[0] > relevance(background)[0]
    assert relevance(patient)[1], "selection reasons must be recorded"
