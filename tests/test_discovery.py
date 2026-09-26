"""Stage 08 — discovery. The rule under test: absence of evidence is never observed failure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from rarepipe.stages.adjudicate.disclosure import DisclosureRefused
from rarepipe.stages.discovery.ingest import import_experiences, save
from rarepipe.stages.discovery.lanes import check_intervention_query
from rarepipe.stages.discovery.model import CandidateState, MatchStatus, Outcome, Status
from rarepipe.stages.discovery.stage import BuildRequest, DiscoveryUsageError, build

QUOTE_HARM = "Treatment weakened the mitotic checkpoint, leading to aneuploidy in treated cells."
QUOTE_GOOD = "Treatment restored BUBR1 protein levels and improved chromosome segregation in BUB1B-deficient cells."
QUOTE_WITHHELD = "We decided not to administer adjuvant chemotherapy using taxanes after surgery."


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "research"
    bundle = root / "bundles" / "KT_0001"
    (bundle / "docs").mkdir(parents=True)
    (bundle / "docs" / "PMID_111.txt").write_text(f"{QUOTE_HARM} {QUOTE_GOOD} {QUOTE_WITHHELD}")
    (bundle / "bundle.json").write_text(json.dumps({
        "bundle": {"bundle_id": "KT_0001", "knowledge_task": "KT_0001", "created_at": "2026-09-26T00:00:00+00:00"},
        "documents": [{"source_id": "PMID:111", "title": "t", "pub_year": 2026}]}))
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "tasks" / "KT_0001.json").write_text(json.dumps({
        "id": "KT_0001", "question": "lane question", "reason": "[D_failure_or_negative_experience] why",
        "disclosure_level": "public_gene_level", "retrieval_plan": ["Europe PMC"], "queries": ["q"],
        "documents_found": ["PMID:111"]}))
    return root


@pytest.fixture
def imap(tmp_path: Path) -> Path:
    run = tmp_path / "intervention" / "RUN_MAP"
    run.mkdir(parents=True)
    (run / "intervention_map.private.json").write_text(json.dumps({
        "case_id": "CASE_X", "gene_symbol": "BUB1B", "semantic_digest": "sha256:map",
        "status": "INTERVENTION_LOGIC_READY_FOR_APPROVED_DRUG_SEARCH",
        "search_specs": [{"spec_id": "SPEC_001", "desired_effect": "restore_toward_normal"}],
        "forbidden_effects": [{"biological_state": "checkpoint", "prohibited_direction": "decrease"}],
        "execution": {"run_id": "RUN_MAP"}}))
    return run


def _write(root: Path, experiences: list[dict], name="a.yaml") -> Path:
    path = root / name
    path.write_text(yaml.safe_dump({"session": {"provider": "Anthropic", "interface": "Claude Code",
                                                "model": "Claude Opus 5", "knowledge_task": "KT_0001",
                                                "human_reviewed": True},
                                    "experiences": experiences}, sort_keys=False))
    return path


def _exp(**kw):
    base = {"intervention_ingredient": "metformin", "source_id": "PMID:111", "lane": "D_failure_or_negative_experience",
            "subject_scope": "engineered_human_cells", "outcome": "worsened", "quote": QUOTE_HARM,
            "measured_endpoints": [{"endpoint": "aneuploidy", "direction": "worsened"}]}
    base.update(kw)
    return base


def make(imap, workspace, tmp_path, **kw):
    return build(BuildRequest(intervention_map_run=imap, research_dir=workspace, output=tmp_path / "out",
                              offline=True, argv=["t"], **kw))


# ── the guard changes here, and only in one direction ───────────────────────

def test_therapy_terms_are_permitted_now_but_case_identity_still_is_not():
    assert check_intervention_query("BUBR1 degradation inhibitor proteasome mitosis")
    assert check_intervention_query("drug treatment aneuploidy rescue trial")
    for leak in ("BUB1B p.(Asn1067Ser) inhibitor", "chr15:40210911 C>T drug", "HP:0001250 treatment"):
        with pytest.raises(DisclosureRefused):
            check_intervention_query(leak)


# ── the import gate ─────────────────────────────────────────────────────────

def test_an_experience_needs_a_source_that_was_retrieved_and_a_verbatim_quote(workspace):
    ok = import_experiences(workspace, _write(workspace, [_exp()]))
    assert len(ok.experiences) == 1 and not ok.rejected
    assert ok.experiences[0].evidence_source.verified_from_source

    bad_source = import_experiences(workspace, _write(workspace, [_exp(source_id="PMID:999")], "b.yaml"))
    assert bad_source.rejected[0].reason == "source_not_in_corpus"

    bad_quote = import_experiences(workspace, _write(workspace, [_exp(quote="invented sentence")], "c.yaml"))
    assert bad_quote.rejected[0].reason == "quote_not_found_in_source"


def test_an_outcome_claim_without_an_endpoint_is_refused(workspace):
    """'No effect' is meaningless without saying what was measured."""
    result = import_experiences(workspace, _write(workspace, [_exp(outcome="no_effect", measured_endpoints=[])]))
    assert not result.experiences
    assert result.rejected[0].reason == "no_citation"
    assert "not reusable" in result.rejected[0].detail


def test_unknown_outcome_needs_no_endpoint_because_nothing_was_measured(workspace):
    result = import_experiences(workspace, _write(workspace, [
        _exp(outcome="unknown", quote=QUOTE_WITHHELD, measured_endpoints=[])]))
    assert len(result.experiences) == 1 and result.experiences[0].outcome is Outcome.UNKNOWN


# ── the distinction the whole stage exists for ──────────────────────────────

def test_considered_but_never_measured_is_not_recorded_as_harm(imap, workspace, tmp_path):
    save(workspace, import_experiences(workspace, _write(workspace, [
        _exp(intervention_ingredient="paclitaxel", outcome="unknown", quote=QUOTE_WITHHELD,
             measured_endpoints=[])])))
    r = make(imap, workspace, tmp_path)
    candidate = next(c for c in r.discovery.candidates if c.ingredient == "paclitaxel")
    assert candidate.experiences_harmful == [], "a withheld medicine was never observed doing anything"
    assert candidate.experiences_unknown
    assert candidate.state is CandidateState.INSUFFICIENT_EVIDENCE
    assert candidate.mechanism_match.direction == "unknown"
    assert "inference" in " ".join(candidate.limitations)


def test_observed_harm_contradicts_the_candidate(imap, workspace, tmp_path):
    save(workspace, import_experiences(workspace, _write(workspace, [_exp()])))
    r = make(imap, workspace, tmp_path)
    candidate = r.discovery.candidates[0]
    assert candidate.state is CandidateState.CONTRADICTED
    assert candidate.mechanism_match.status is MatchStatus.NO_MATCH
    assert candidate.mechanism_match.direction == "discordant"
    assert candidate.forbidden_direction_conflict


def test_an_unapproved_ingredient_cannot_become_a_candidate(imap, workspace, tmp_path):
    save(workspace, import_experiences(workspace, _write(workspace, [
        _exp(intervention_ingredient="AM-9022", outcome="improved", quote=QUOTE_GOOD,
             measured_endpoints=[{"endpoint": "segregation", "direction": "improved"}])])))
    r = make(imap, workspace, tmp_path)
    assert not r.discovery.candidates, "nothing unapproved may become a Track 2 candidate"
    assert r.discovery.reference_compounds[0].track2_eligible is False
    assert any(x.rejected_because.value == "NOT_APPROVED" for x in r.discovery.rejected)


def test_a_search_that_found_nothing_produces_no_experience(imap, workspace, tmp_path):
    r = make(imap, workspace, tmp_path)
    assert r.discovery.experiences == []
    assert r.discovery.status is Status.NONE_FOUND
    assert "absence of published evidence" in r.discovery.status_basis
    text = (r.run_dir / "intervention_discovery.md").read_text()
    assert "untested, not failed" in text or "untested" in text


def test_unresolved_needs_become_node_query_specs_that_are_not_sent(imap, workspace, tmp_path):
    r = make(imap, workspace, tmp_path)
    assert r.discovery.node_query_specs
    for spec in r.discovery.node_query_specs:
        assert spec.sent is False
        assert spec.patient_identity_required is False
        assert spec.useful_negative_result is True
        assert spec.arises_from


def test_nothing_is_ranked_and_no_dose_appears(imap, workspace, tmp_path):
    save(workspace, import_experiences(workspace, _write(workspace, [_exp()])))
    r = make(imap, workspace, tmp_path)
    text = (r.run_dir / "intervention_discovery.md").read_text().lower()
    for forbidden in ("mg/kg", "recommended dose", "first-line", "#1 ", "rank 1", "we recommend"):
        assert forbidden not in text
    assert "no ranking" in text and "no dose" in text


def test_a_blocked_intervention_map_cannot_start_a_drug_search(imap, workspace, tmp_path):
    payload = json.loads((imap / "intervention_map.private.json").read_text())
    payload["status"] = "INTERVENTION_LOGIC_BLOCKED"
    (imap / "intervention_map.private.json").write_text(json.dumps(payload))
    with pytest.raises(DiscoveryUsageError):
        make(imap, workspace, tmp_path)


# ── approval: the bug that made a homeopathic listing look approved ─────────

def test_directory_presence_is_identity_evidence_not_approval(monkeypatch):
    """The FDA says NDC inclusion does not indicate approval. The first version of this ignored that
    and marked an ingredient approved on an UNAPPROVED HOMEOPATHIC listing."""
    from rarepipe.stages.discovery import approval as mod

    def fake_get(url, timeout=60):
        if "rxcui.json" in url:
            return {"idGroup": {"rxnormId": ["7393"]}}
        if "properties.json" in url:
            return {"properties": {"name": "widgetol"}}
        if "drugsfda" in url:
            return {"results": []}  # no approved application anywhere
        return {"results": [{"marketing_category": "UNAPPROVED HOMEOPATHIC", "finished": True,
                             "product_type": "HUMAN OTC DRUG", "generic_name": "Circulation Drops"}],
                "meta": {"results": {"total": 69}}}

    monkeypatch.setattr(mod, "_get", fake_get)
    record = mod.verify("widgetol")
    assert record.verified is False, "a directory listing must never establish approval"
    assert record.approval_basis is None
    assert record.marketed_products_identity["total_products"] == 69
    assert "UNAPPROVED HOMEOPATHIC" in record.marketed_products_identity["non_approval_categories_present"]
    assert "does not indicate approval" in record.marketed_products_identity["note"]


def test_an_approved_application_is_what_establishes_approval(monkeypatch):
    from rarepipe.stages.discovery import approval as mod

    def fake_get(url, timeout=60):
        if "rxcui.json" in url:
            return {"idGroup": {"rxnormId": ["7393"]}}
        if "properties.json" in url:
            return {"properties": {"name": "niacin"}}
        if "drugsfda" in url:
            return {"results": [{"application_number": "ANDA040378", "sponsor_name": "AVONDALE PHARMS",
                                 "submissions": [{"submission_status": "AP", "submission_status_date": "20000503"}],
                                 "products": [{"brand_name": "NIACIN", "dosage_form": "TABLET, EXTENDED RELEASE",
                                               "marketing_status": "Prescription"}]}]}
        return {"results": [], "meta": {"results": {"total": 0}}}

    monkeypatch.setattr(mod, "_get", fake_get)
    record = mod.verify("niacin (nicotinic acid)")
    assert record.verified is True
    assert record.authority_source.startswith("Drugs@FDA")
    assert "ANDA040378" in record.approval_basis and "20000503" in record.approval_basis
    assert record.applications[0]["approved_submissions"] == 1


def test_an_application_without_an_approved_submission_does_not_count(monkeypatch):
    from rarepipe.stages.discovery import approval as mod

    def fake_get(url, timeout=60):
        if "rxcui.json" in url:
            return {"idGroup": {"rxnormId": ["1"]}}
        if "properties.json" in url:
            return {"properties": {"name": "thing"}}
        if "drugsfda" in url:
            return {"results": [{"application_number": "ANDA999999", "sponsor_name": "X",
                                 "submissions": [{"submission_status": "TA"}], "products": []}]}
        return {"results": [], "meta": {"results": {"total": 0}}}

    monkeypatch.setattr(mod, "_get", fake_get)
    assert mod.verify("thing").verified is False


def test_the_synonym_comes_from_an_authority_not_from_memory(monkeypatch):
    from rarepipe.stages.discovery import approval as mod

    monkeypatch.setattr(mod, "_get", lambda url, timeout=60: {"properties": {"name": "niacin"}})
    variants = mod.name_variants("nicotinic acid", "7393")
    assert variants[0] == "nicotinic acid" and "niacin" in variants
    assert mod.name_variants("niacin (nicotinic acid)", None) == ["niacin (nicotinic acid)", "niacin",
                                                                  "nicotinic acid"]
