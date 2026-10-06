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
    for drug_query in ("BUB1B kinase treatment", "BUBR1 gene therapy rescue", "aneuploidy drug repurposing"):
        with pytest.raises(RetrievalRefused):
            check_search_query(drug_query)


def test_perturbation_vocabulary_is_searchable_and_therapeutic_intent_is_not():
    """Search governance and therapeutic-output governance are separate concerns.

    Refusing the word "inhibitor" made experimental cell biology unsearchable: a mechanism is
    established by perturbing a system and measuring what moves, and the paper this case rests on
    identifies its own mechanism with geldanamycin, cycloheximide and MG132. The module contradicted
    itself, too — "knockdown" and "sirna" score positively in RELEVANCE_TERMS, so triage rewarded the
    experiments retrieval refused to look for. Perturbation vocabulary is therefore allowed and
    therapeutic framing is still refused; the prohibition on turning "inhibiting X raised Y" into
    "administer an inhibitor of X" is enforced over the output, not by crippling the search.
    """
    for mechanistic in ("BUBR1 HSP90 inhibition protein level", "BUBR1 proteasome inhibition MG132",
                        "FBXW7 knockdown BubR1 stability", "SIRT2 depletion BubR1 abundance",
                        "BUBR1 degrader", "kinase inhibition BUBR1 turnover",
                        "BUBR1 shRNA rescue overexpression",
                        # Laboratory methods, opened for mechanistic retrieval: a screen is how the
                        # unbiased form of "what changes this protein's abundance" gets asked.
                        "CRISPR screen BUBR1 stability", "HSP90 small molecule BUBR1 protein level",
                        "compound screen BubR1 abundance", "genetic modifier screen protein stability",
                        "proteostasis screen destabilised protein"):
        assert check_search_query(mechanistic), mechanistic
    for therapeutic in ("BUBR1 drug treatment", "niacin therapy for aneuploidy",
                        "BUBR1 therapeutic repurposing", "BUBR1 clinical trial dosing",
                        "gene therapy BUB1B", "BUBR1 efficacy in patients", "treating aneuploidy",
                        # A method word does not launder therapeutic intent in the same query.
                        "CRISPR gene therapy for aneuploidy", "small molecule treatment of MVA",
                        "compound screen for therapeutic repurposing", "small molecule drug candidate",
                        "clinical efficacy BUBR1"):
        with pytest.raises(RetrievalRefused):
            check_search_query(therapeutic)


def test_every_named_perturbation_term_actually_passes_the_gate():
    """The allow-list is not decoration: each term must be searchable on its own."""
    from rarepipe.stages.mechanism.retrieve import PERTURBATION_VOCABULARY
    for term in PERTURBATION_VOCABULARY:
        assert check_search_query(f"BUBR1 {term}"), term


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


def test_task_ids_never_collide_with_an_existing_task(tmp_path, corpus):
    """A workspace that adopts tasks from a corpus run has gaps, and a count-based id lands in one."""
    from rarepipe.stages.mechanism.model import DisclosureLevel, KnowledgeTask

    root = _workspace(tmp_path, corpus)  # creates KT_0001
    for task_id in ("KT_0004", "KT_0008"):
        research.save_task(root, KnowledgeTask(id=task_id, question=f"adopted {task_id}", reason="r",
                                               disclosure_level=DisclosureLevel.PUBLIC_GENE_LEVEL,
                                               retrieval_plan=["Europe PMC"], queries=["BUB1B"]))
    assert research.next_task_id(root) == "KT_0009"
    new = KnowledgeTask(id=research.next_task_id(root), question="a new question", reason="r",
                        disclosure_level=DisclosureLevel.PUBLIC_GENE_LEVEL, retrieval_plan=["Europe PMC"],
                        queries=["BUB1B"])
    research.save_task(root, new, allow_overwrite=False)
    assert research.load_task(root, "KT_0008").question == "adopted KT_0008"

    clash = new.model_copy(update={"id": "KT_0008", "question": "something else entirely"})
    with pytest.raises(research.ResearchError):
        research.save_task(root, clash, allow_overwrite=False)



def test_full_text_is_stored_only_under_a_licence_that_permits_it(monkeypatch):
    """NCBI PMC serves some articles Europe PMC flags as closed. Only a stated text-mining licence lets us keep them."""
    from rarepipe.stages.mechanism import retrieve as mod

    def closed(url, timeout=90):
        if "europepmc" in url:
            raise OSError("not open access")
        return b"<article><license><license-p>All rights reserved.</license-p></license><body>text</body></article>"

    monkeypatch.setattr(mod, "_get", closed)
    body, note = mod.fetch_full_text("PMC1")
    assert body is None and "licence does not state text-mining permission" in note

    def licensed(url, timeout=90):
        if "europepmc" in url:
            raise OSError("not open access")
        return (b"<article><license><license-p>This file is available for text mining.</license-p></license>"
                b"<body><p>In preliminary studies, mice developed phenotypes at similar rates.</p></body></article>")

    monkeypatch.setattr(mod, "_get", licensed)
    body, note = mod.fetch_full_text("PMC1")
    assert body and "similar rates" in body
    assert "under its stated licence" in note and "text mining" in note


def test_a_superseding_analysis_session_replaces_the_earlier_one(tmp_path):
    import json as _json

    from rarepipe.stages.mechanism.research import load_analyses

    folder = tmp_path / "analyses"
    folder.mkdir()
    base = {"accepted_claims": [], "accepted_evidence": [], "rejected": []}
    for sid, sup in (("LLMRS_0001", None), ("LLMRS_0002", "LLMRS_0001")):
        session = {"session_id": sid, "provider": "p", "interface": "i", "model": "m", "knowledge_task": "KT_1",
                   "supersedes": sup}
        (folder / f"{sid}.json").write_text(_json.dumps({"session": session, **base}))
    sessions, *_ = load_analyses(tmp_path)
    assert [s.session_id for s in sessions] == ["LLMRS_0002"]


# ── provenance-aware residue release ────────────────────────────────────────

def test_a_residue_leaves_the_boundary_only_when_a_stored_source_attests_it():
    """Not a whitelist of residue syntax. Positive, checkable evidence that the residue is published.

    The default stays fail-closed. A residue token may go out only when the caller names the public
    source and that source's committed text carries the token — so the licence is per token, per
    source, and auditable after the fact rather than a claim made at call time.
    """
    from pathlib import Path

    from rarepipe.stages.adjudicate.disclosure import PublicResidueProvenance

    root = Path(__file__).resolve().parents[1] / "data/literature/mva-bypass-v1"
    good = PublicResidueProvenance(residues=("K668", "L669", "I672", "E674"),
                                   source_id="PMID:33892776", corpus_roots=(root,),
                                   reason="published KARD/B56 motif residues")
    assert check_search_query("BubR1 K668 B56 binding", provenance=good)
    assert check_search_query("BubR1 L669 I672 E674 motif", provenance=good)

    # no provenance: unchanged behaviour
    with pytest.raises(DisclosureRefused):
        check_search_query("BubR1 K668 B56 binding")
    # a token the provenance does not name, or that the source does not carry
    with pytest.raises(DisclosureRefused):
        check_search_query("BubR1 Q999 binding", provenance=good)
    # a source that is not in the snapshot cannot attest anything
    absent = PublicResidueProvenance(residues=("K668",), source_id="PMID:99999999",
                                     corpus_roots=(root,))
    with pytest.raises(DisclosureRefused):
        check_search_query("BubR1 K668 binding", provenance=absent)


def test_provenance_never_releases_identity_grade_patterns():
    """A coordinate, an rsID, a ClinVar id or an HPO code is identifying whatever its origin."""
    from pathlib import Path

    from rarepipe.stages.adjudicate.disclosure import PublicResidueProvenance

    root = Path(__file__).resolve().parents[1] / "data/literature/mva-bypass-v1"
    prov = PublicResidueProvenance(residues=("K668",), source_id="PMID:33892776", corpus_roots=(root,))
    for identifying in ("chr15:40000000 BUB1B", "rs12345678 BUB1B", "HP:0001249 BUB1B",
                        "NM_001211.6:c.2211A>G"):
        with pytest.raises(DisclosureRefused):
            check_search_query(identifying, provenance=prov)


def test_a_residue_from_the_private_case_stays_refused_however_well_attested():
    """The private boundary is not a question of whether a string is public somewhere.

    This check now runs first and on every residue-like token, which is what the provenance work
    exposed: a bare position such as "K668" matched no pattern at all, so the cross-check against the
    case's own residue had nothing to compare and a private position could have gone out unexamined.
    """
    from pathlib import Path

    from rarepipe.stages.adjudicate.disclosure import PublicResidueProvenance, check_query

    root = Path(__file__).resolve().parents[1] / "data/literature/mva-bypass-v1"
    prov = PublicResidueProvenance(residues=("K668",), source_id="PMID:33892776", corpus_roots=(root,))
    with pytest.raises(DisclosureRefused) as caught:
        check_search_query("BubR1 K668 binding", provenance=prov,
                           private_residues=frozenset({"K668"}))
    assert "private case" in str(caught.value)
    # and with no provenance at all, for a position that trips the pattern on its own
    with pytest.raises(DisclosureRefused):
        check_query("BUBR1 N1067 function", private_residues=frozenset({"N1067"}))


def test_a_bare_residue_position_is_gated_at_all():
    """It was not. "K668" matched no case-specific pattern before this work."""
    from rarepipe.stages.adjudicate.disclosure import case_specific_reasons

    assert "residue position" in case_specific_reasons("BubR1 K668 acetylation")
    assert case_specific_reasons("BUBR1 protein abundance") == []
