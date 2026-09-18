"""Stage 06 — the stage exists to stop a fluent story replacing evidence, so the tests attack that."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rarepipe.stages.adjudicate.disclosure import DisclosureRefused
from rarepipe.stages.mechanism import claims as C
from rarepipe.stages.mechanism import extract, questions, research
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


def test_prompt_templates_are_versioned_artifacts():
    for name in ("research_query_planning", "evidence_extractor", "contradiction_agent", "mechanism_synthesizer",
                 "paper_triage"):
        text, template_id = research.load_prompt_template(name)
        assert template_id.endswith("_v1") and text.strip()


def test_the_pipeline_never_calls_a_model_and_says_so(corpus, adjudication, tmp_path):
    """Substituting the assistant must not change pipeline semantics, so nothing may depend on one."""
    import rarepipe.stages.mechanism as pkg

    assert not (Path(pkg.__file__).parent / "llm.py").exists(), "the LLM client came back"
    source = "".join((Path(pkg.__file__).parent / name).read_text()
                     for name in ("stage.py", "research.py", "retrieve.py", "claims.py", "extract.py"))
    for forbidden in ("api.anthropic.com", "openai", "ANTHROPIC_API_KEY", "chat.completions"):
        assert forbidden not in source, f"stage code references {forbidden}"
    r = resolve(corpus, adjudication, tmp_path)
    assert r.dossier.automation_status.pipeline_depends_on_an_llm is False
    assert r.dossier.automation_status.automated_llm_orchestration == "deferred"
    assert r.dossier.automation_status.current_mode == "deterministic_only"
    assert all(e.extracted_by.startswith("rarepipe.") for e in r.dossier.evidence)


def test_triage_scores_patient_evidence_above_background():
    patient = {"title": "Molecular causes for BUBR1 dysfunction in MVA patient cells",
               "abstractText": "Patient-derived cell lines showed impaired mitotic checkpoint and reduced BUBR1 protein abundance; rescue restored function."}
    background = {"title": "BUB1B expression in colorectal cancer prognosis",
                  "abstractText": "We performed a bioinformatic analysis of BUB1B expression as a biomarker for prognosis."}
    assert relevance(patient)[0] > relevance(background)[0]
    assert relevance(patient)[1], "selection reasons must be recorded"


# ── the human-in-the-loop research workflow ─────────────────────────────────

def _workspace(tmp_path: Path, corpus: Path) -> Path:
    from rarepipe.stages.mechanism.model import DisclosureLevel, KnowledgeTask

    root = research.workspace(tmp_path / "research")
    task = KnowledgeTask(id="KT_0001", question="Do BUB1B variants reduce BUBR1 abundance?",
                         reason="resolves MC_0005", disclosure_level=DisclosureLevel.PUBLIC_GENE_LEVEL,
                         retrieval_plan=["Europe PMC"], queries=["BUB1B patient cells checkpoint"])
    research.save_task(root, task)
    research.bundle_from_corpus(corpus, task, root)
    return root


def _analysis(root: Path, claims: list[dict], name: str = "analysis.yaml") -> Path:
    import yaml

    path = root / name
    path.write_text(yaml.safe_dump({"session": {"provider": "Anthropic", "interface": "Claude Code",
                                                "model": "Claude Opus 5", "knowledge_task": "KT_0001",
                                                "prompt_template": "evidence_extractor_v1", "human_reviewed": True},
                                    "proposed_claims": claims}, sort_keys=False))
    return path


def test_a_proposal_is_accepted_only_when_every_citation_checks_out(tmp_path, corpus):
    root = _workspace(tmp_path, corpus)
    good = _analysis(root, [{"statement": "Patient cells with biallelic mutations have an impaired mitotic checkpoint.",
                             "claim_type": "checkpoint_effect", "scope": "disease_level", "direction": "supports",
                             "confidence": "high", "reasoning": "stated in the source",
                             "evidence": [{"source_id": "PMID:111",
                                           "quote": "cell lines derived from MVA patients with biallelic BUB1B mutations have an impaired mitotic checkpoint",
                                           "experimental_level": "patient_derived_cells"}]}])
    result = research.import_analysis(root, good)
    assert result.ok and len(result.accepted_claims) == 1
    claim = result.accepted_claims[0]
    assert claim.epistemic_class is EpistemicClass.DERIVED_INFERENCE
    assert claim.inference.derived_by.startswith("Anthropic:Claude Opus 5")
    assert result.accepted_evidence[0].verified_from_source
    assert result.session.case_specific_genomic_data_supplied is False
    assert result.session.human_reviewed


@pytest.mark.parametrize("proposal,reason", [
    ({"statement": "BUBR1 loss weakens the checkpoint.", "claim_type": "checkpoint_effect", "scope": "gene_level",
      "direction": "supports", "confidence": "high", "reasoning": "well established", "evidence": []},
     "no_citation"),
    ({"statement": "Abundance was reduced.", "claim_type": "protein_effect", "scope": "gene_level",
      "direction": "supports", "confidence": "high", "reasoning": "reported",
      "evidence": [{"source_id": "PMID:111", "quote": "a sentence that is nowhere in the stored document"}]},
     "quote_not_found_in_source"),
    ({"statement": "Reported elsewhere.", "claim_type": "protein_effect", "scope": "gene_level",
      "direction": "supports", "confidence": "high", "reasoning": "cited",
      "evidence": [{"source_id": "PMID:999999", "quote": "low overall BUBR1 protein abundance"}]},
     "source_not_in_corpus"),
    ({"statement": "This child's allele destabilises BUBR1.", "claim_type": "protein_effect", "scope": "exact_variant",
      "direction": "supports", "confidence": "moderate", "reasoning": "it is in the kinase domain",
      "evidence": [{"source_id": "PMID:111", "quote": "low overall BUBR1 protein abundance"}]},
     "scope_overreach"),
])
def test_the_import_gate_rejects_what_it_cannot_verify(tmp_path, corpus, adjudication, proposal, reason):
    root = _workspace(tmp_path, corpus)
    needles, _ = residue_needles(json.loads(adjudication.read_text()))
    result = research.import_analysis(root, _analysis(root, [proposal]), residue_needles=needles)
    assert not result.accepted_claims
    assert result.rejected[0].reason == reason
    assert "Claude Opus 5" in result.rejected[0].produced_by


def test_imported_claims_reach_the_dossier_with_their_session_recorded(tmp_path, corpus, adjudication):
    root = _workspace(tmp_path, corpus)
    good = _analysis(root, [{"statement": "Ectopic BUBR1 restored checkpoint activity in patient cells.",
                             "claim_type": "protein_effect", "scope": "disease_level", "direction": "supports",
                             "confidence": "high", "reasoning": "a rescue experiment is reported",
                             "evidence": [{"source_id": "PMID:111",
                                           "quote": "Ectopic expression of BUBR1 restored mitotic checkpoint activity in patient cells",
                                           "experimental_level": "patient_derived_cells", "rescue_experiment": True}]}])
    research.save_analysis(root, research.import_analysis(root, good))
    r = resolve(corpus, adjudication, tmp_path, research_dir=root)
    imported = [c for c in r.dossier.claims if c.id.startswith("MC_IMP")]
    assert imported and imported[0].inference.reasoning
    assert r.dossier.automation_status.current_mode == "human_operated_llm_assistance"
    session = r.dossier.provenance.research_sessions[0]
    assert session.model == "Claude Opus 5" and session.knowledge_task == "KT_0001"
    assert session.accepted == [imported[0].id]
    text = (r.run_dir / "mechanism_dossier.md").read_text()
    assert session.session_id in text and "human_operated" in text


def test_a_brief_carries_the_rules_and_the_documents_but_no_case_identity(tmp_path, corpus, adjudication):
    from rarepipe.stages.mechanism.model import EvidenceBundle

    root = _workspace(tmp_path, corpus)
    payload = json.loads((root / "bundles" / "KT_0001" / "bundle.json").read_text())
    text, template_id = research.load_prompt_template("evidence_extractor")
    brief = research.render_brief(research.load_task(root, "KT_0001"), EvidenceBundle(**payload["bundle"]),
                                  payload["documents"], text, template_id)
    assert "Answer **only** from the documents listed below" in brief
    assert "PMID:111" in brief and "proposed_claims" in brief
    needles, _ = residue_needles(json.loads(adjudication.read_text()))
    for needle in needles:
        assert needle not in brief
    assert "chr15" not in brief and "40210911" not in brief


def test_a_task_that_was_only_retrieved_does_not_read_as_reviewed(corpus, adjudication, tmp_path):
    """'We searched this' must not look like 'a reasoning process examined this'."""
    r = resolve(corpus, adjudication, tmp_path)
    public = [t for t in r.dossier.knowledge_tasks if t.disclosure_level.value != "local_only"]
    assert public, "no public task in the fixture"
    for task in public:
        assert task.progress.semantic_review == "not_started"
        assert task.state.value in ("RETRIEVED", "DETERMINISTICALLY_EXTRACTED", "BLOCKED", "PLANNED")
        assert not task.reviewed_by
    assert "0 of" in r.dossier.readiness.semantic_review_coverage


def test_readiness_separates_the_disease_mechanism_from_the_allele(corpus, adjudication, tmp_path):
    r = resolve(corpus, adjudication, tmp_path)
    readiness = r.dossier.readiness
    assert readiness.exact_allele_mechanism_complete is False
    assert readiness.exact_allele_blocker == "missense_function_unresolved"
    assert readiness.disease_mechanism_ready_for_intervention_search is (r.dossier.status is Status.READY_FOR_INTERVENTION_SEARCH)
    text = (r.run_dir / "mechanism_dossier.md").read_text()
    assert "Readiness, in two dimensions" in text and "missense_function_unresolved" in text


def test_a_reviewed_task_is_marked_reviewed_and_counted(corpus, adjudication, tmp_path):
    root = _workspace(tmp_path, corpus)
    good = _analysis(root, [{"statement": "Patient cells with biallelic mutations have an impaired mitotic checkpoint.",
                             "claim_type": "checkpoint_effect", "scope": "disease_level", "direction": "supports",
                             "confidence": "high", "reasoning": "stated in the source",
                             "evidence": [{"source_id": "PMID:111",
                                           "quote": "cell lines derived from MVA patients with biallelic BUB1B mutations have an impaired mitotic checkpoint",
                                           "experimental_level": "patient_derived_cells"}]}])
    research.save_analysis(root, research.import_analysis(root, good))
    r = resolve(corpus, adjudication, tmp_path, research_dir=root)
    reviewed = next(t for t in r.dossier.knowledge_tasks if t.id == "KT_0001")
    assert reviewed.progress.semantic_review == "complete"
    assert reviewed.state.value == "ADJUDICATED" and reviewed.reviewed_by


def test_a_synthesis_may_only_reconcile_evidence_already_accepted(tmp_path, corpus):
    root = _workspace(tmp_path, corpus)
    first = _analysis(root, [{"statement": "Patient cells have an impaired mitotic checkpoint.",
                              "claim_type": "checkpoint_effect", "scope": "disease_level", "direction": "supports",
                              "confidence": "high", "reasoning": "stated",
                              "evidence": [{"source_id": "PMID:111",
                                            "quote": "cell lines derived from MVA patients with biallelic BUB1B mutations have an impaired mitotic checkpoint",
                                            "experimental_level": "patient_derived_cells"}]}], "first.yaml")
    research.save_analysis(root, research.import_analysis(root, first))

    reconcile = _analysis(root, [{"statement": "The checkpoint defect is the established cellular phenotype.",
                                  "claim_type": "checkpoint_effect", "scope": "disease_level", "direction": "supports",
                                  "confidence": "moderate", "reasoning": "reconciles an accepted finding",
                                  "evidence": [{"source_id": "PMID:111",
                                                "quote": "cell lines derived from MVA patients with biallelic BUB1B mutations have an impaired mitotic checkpoint"}]}],
                                "reconcile.yaml")
    assert research.import_analysis(root, reconcile, synthesis_only=True).accepted_claims

    novel = _analysis(root, [{"statement": "A fact no earlier session accepted.", "claim_type": "protein_effect",
                              "scope": "gene_level", "direction": "supports", "confidence": "high",
                              "reasoning": "synthesis",
                              "evidence": [{"source_id": "PMID:111",
                                            "quote": "Karyotyping confirmed mosaic variegated aneuploidy with trisomy and monosomy in these patients"}]}],
                             "novel.yaml")
    result = research.import_analysis(root, novel, synthesis_only=True)
    assert not result.accepted_claims and result.rejected[0].reason == "scope_overreach"
    assert "already accepted" in result.rejected[0].detail


def test_an_objection_becomes_a_qualification_not_a_silent_drop(tmp_path, corpus, adjudication):
    """Evidence that the chain is incomplete must survive without inventing an arrow for it."""
    root = _workspace(tmp_path, corpus)
    objection = _analysis(root, [{"statement": "BUBR1 has roles beyond the mitotic checkpoint.",
                                  "claim_type": "protein_effect", "scope": "gene_level", "direction": "contradicts",
                                  "confidence": "moderate", "reasoning": "stated in the source",
                                  "evidence": [{"source_id": "PMID:222",
                                                "quote": "the kinase activity of BUBR1 was dispensable for checkpoint signalling in this system",
                                                "experimental_level": "animal_model"}]}])
    research.save_analysis(root, research.import_analysis(root, objection))
    r = resolve(corpus, adjudication, tmp_path, research_dir=root)
    assert r.dossier.graph.qualifications, "an accepted objection vanished from the graph"
    assert any("beyond the mitotic checkpoint" in q for q in r.dossier.graph.qualifications)
    assert "is not the whole story" in (r.run_dir / "mechanism_dossier.md").read_text()
