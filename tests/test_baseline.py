"""Stage 03 — baseline causal-hypothesis generation. Offline: a fake solver stands in for Exomiser.

Tests that genuinely require the solver (multiallelic handling, numeric/decoy contigs,
real PASS vs non-PASS behaviour) live in test_baseline_solver.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from rarepipe.core.console import Console
from rarepipe.stages.baseline import exomiser, profiles as prof
from rarepipe.stages.baseline.model import Status
from rarepipe.stages.baseline.stage import BaselineRequest, BaselineUsageError, run_baseline
from rarepipe.testing import baseline_fixtures as bf
from rarepipe.testing import normalize_fixtures as nf


@pytest.fixture
def normalized(tmp_path):
    """A real Stage 01 + Stage 02 chain over synthetic inputs, with 8 HPO terms (7 phenotypic abnormality)."""
    from rarepipe.stages.normalize.stage import NormalizeRequest, run_normalize

    terms = ["HP:0001250", "HP:0001263", "HP:0000252", "HP:0000007"]  # last one is mode_of_inheritance
    root = nf.build_case(tmp_path / "case", hpo_terms=terms)
    manifest = nf.run_intake_for(root, tmp_path / "intake")
    res = nf.build_resources(tmp_path / "resources")
    result = run_normalize(NormalizeRequest(manifest=manifest, output=tmp_path / "norm", resources=res), Console(quiet=True))
    return result.run_dir / "normalized_case.private.json"


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    def _run(normalized_case: Path, *, runner=bf.fake_run_job, install=True, out="baseline", **kw):
        monkeypatch.setattr(exomiser, "run_job", runner)
        monkeypatch.setattr(exomiser, "locate", lambda home, data: bf.fake_installation(tmp_path) if install else None)
        req = BaselineRequest(normalized_case=normalized_case, output=tmp_path / out, exomiser_home=tmp_path / "exomiser", **kw)
        return run_baseline(req, Console(quiet=True))

    return _run


def codes(c, severity=None):
    return {i.code for i in c.issues if severity is None or i.severity.value == severity}


# ── profile construction ────────────────────────────────────────────────────


def test_four_profiles_vary_exactly_two_things(normalized, baseline):
    c = baseline(normalized).candidate_set
    assert [p.profile_id for p in c.profiles] == ["PROFILE_A", "PROFILE_B", "PROFILE_C", "PROFILE_D"]
    assert all(p.filter_policy.analysis_mode == "PASS_ONLY" for p in c.profiles)  # constant: it is a memory strategy
    by_id = {p.profile_id: p for p in c.profiles}
    assert (by_id["PROFILE_A"].phenotype.term_count, by_id["PROFILE_A"].filter_policy.failed_variant_filter) == (3, True)
    assert (by_id["PROFILE_B"].phenotype.term_count, by_id["PROFILE_B"].filter_policy.failed_variant_filter) == (3, False)
    assert (by_id["PROFILE_C"].phenotype.term_count, by_id["PROFILE_C"].filter_policy.failed_variant_filter) == (4, True)
    assert (by_id["PROFILE_D"].phenotype.term_count, by_id["PROFILE_D"].filter_policy.failed_variant_filter) == (4, False)
    assert {p.inheritance_modes["AUTOSOMAL_RECESSIVE_COMP_HET"] for p in c.profiles} == {2.0}
    assert all(p.filter_policy.source_filter_labels_modified is False for p in c.profiles)


def test_phenotype_rule_selects_by_hpo_branch(normalized, baseline):
    c = baseline(normalized).candidate_set
    narrow = next(p for p in c.profiles if p.profile_id == "PROFILE_A")
    wide = next(p for p in c.profiles if p.profile_id == "PROFILE_C")
    assert narrow.phenotype.branches_included == ["phenotypic_abnormality"]
    assert "mode_of_inheritance" in wide.phenotype.branches_included
    assert set(narrow.phenotype.term_ids) < set(wide.phenotype.term_ids)


def test_generated_documents_match_the_exomiser_15_cli_shape(tmp_path):
    spec = prof.PROFILE_SPECS[0]
    sample = yaml.safe_load(prof.sample_yaml("SYNTH", ["HP:0001250"]))
    analysis = yaml.safe_load(prof.analysis_yaml(spec))
    output = yaml.safe_load(prof.output_options_yaml())
    assert set(sample) >= {"subject", "phenotypicFeatures"} and sample["subject"]["id"] == "SYNTH"
    assert analysis["analysisMode"] == "PASS_ONLY"  # flat analysis script, as the shipped presets are
    assert [list(s)[0] for s in analysis["steps"]][0] == "hiPhivePrioritiser"  # memory-sensible genome ordering
    assert output["outputFormats"] == ["JSON", "TSV_GENE", "TSV_VARIANT"] and output["numGenes"] == 0
    assert prof.GENOME_ASSEMBLY == "GRCh38"


def test_failed_variant_filter_is_the_only_step_difference():
    a = yaml.safe_load(prof.analysis_yaml(prof.PROFILE_SPECS[0]))
    b = yaml.safe_load(prof.analysis_yaml(prof.PROFILE_SPECS[1]))
    steps_a = [list(s)[0] for s in a["steps"]]
    steps_b = [list(s)[0] for s in b["steps"]]
    assert set(steps_a) - set(steps_b) == {"failedVariantFilter"}
    assert steps_b == [s for s in steps_a if s != "failedVariantFilter"]
    assert a["analysisMode"] == b["analysisMode"] == "PASS_ONLY"
    assert {k: v for k, v in a.items() if k != "steps"} == {k: v for k, v in b.items() if k != "steps"}


def test_no_disease_or_gene_shortcut_reaches_the_solver(normalized, baseline, tmp_path):
    baseline(normalized)
    for doc in (tmp_path / "baseline" / "native").rglob("*.yml"):
        text = doc.read_text()
        assert "genePanelFilter" not in text and "seedGeneIds" not in text
        assert not any(w in text.lower() for w in ("mva", "aneuploidy", "mosaic", "bub1b", "diagnosis"))
    samples = list((tmp_path / "baseline" / "native").rglob("sample.yml"))
    assert samples and all(set(yaml.safe_load(p.read_text())) >= {"subject", "phenotypicFeatures"} for p in samples)


# ── ingest ──────────────────────────────────────────────────────────────────


def test_candidates_preserve_solver_ranks_and_scores(normalized, baseline):
    c = baseline(normalized).candidate_set
    a = next(r for r in c.results if r.profile_id == "PROFILE_A")
    assert [x.gene_symbol for x in a.candidates] == ["SYNGENE1", "SYNGENE2"]
    assert [x.rank for x in a.candidates] == [1, 2]  # exactly the solver's ranks; nothing reordered
    assert a.candidates[0].score_combined == 0.9321 and a.candidates[0].score_phenotype == 0.8712
    assert a.candidates[0].solver_evidence["HUMAN_PHENO_EVIDENCE"].startswith("synthetic phenotype match")


def test_compound_het_is_represented_as_a_pair_with_unresolved_phase(normalized, baseline):
    c = baseline(normalized).candidate_set
    pair = next(x for r in c.results if r.profile_id == "PROFILE_A" for x in r.candidates if x.gene_symbol == "SYNGENE1")
    assert pair.inheritance_model.endswith("COMP_HET") and pair.is_variant_pair
    assert pair.contributing_variant_count == 2 and len(pair.contributing_variants) == 2
    assert pair.phase.status == "unresolved" and "not proof they are in trans" in pair.phase.note.lower()
    single = next(x for r in c.results if r.profile_id == "PROFILE_A" for x in r.candidates if x.gene_symbol == "SYNGENE2")
    assert not single.is_variant_pair and single.phase is None


def test_non_contributing_variants_are_not_promoted(normalized, baseline):
    c = baseline(normalized).candidate_set
    for r in c.results:
        for cand in r.candidates:
            assert cand.contributing_variant_count == len(cand.contributing_variants)
            assert all(v.solver_variant_score and v.solver_variant_score > 0.5 for v in cand.contributing_variants)


def test_source_filter_labels_are_carried_not_rewritten(normalized, baseline):
    c = baseline(normalized).candidate_set
    b = next(r for r in c.results if r.profile_id == "PROFILE_B")
    gene3 = next(x for x in b.candidates if x.gene_symbol == "SYNGENE3")
    # read back from the source VCF at that locus — the solver's own FILTER column says PASS
    assert [v.source_filter_status for v in gene3.contributing_variants] == ["LowQual"]
    assert gene3.any_contributing_variant_non_pass
    a = next(r for r in c.results if r.profile_id == "PROFILE_A")
    assert not any(x.any_contributing_variant_non_pass for x in a.candidates)


# ── sensitivity matrix ──────────────────────────────────────────────────────


def test_filter_and_phenotype_sensitivity_are_measured(normalized, baseline):
    c = baseline(normalized).candidate_set
    st = c.stability
    assert st.profiles_compared == ["PROFILE_A", "PROFILE_B", "PROFILE_C", "PROFILE_D"]
    assert st.genes_only_when_non_pass_permitted == ["SYNGENE3"]
    assert st.genes_only_with_eighth_term == ["SYNGENE4"]
    assert set(st.genes_in_all_profiles) == {"SYNGENE1", "SYNGENE2"}
    assert all(p.top1_same_gene for p in st.pairwise)
    assert st.verdict in ("stable", "partially_stable")
    assert "NON_PASS_ONLY_CANDIDATE" in codes(c, "WARNING")


def test_unstable_profiles_are_reported_as_such():
    from rarepipe.stages.baseline.compare import compare
    from rarepipe.stages.baseline.model import Candidate, ProfileResult

    def result(pid, genes):
        return ProfileResult(profile_id=pid, status="completed", candidate_count=len(genes), candidates=[
            Candidate(rank=i + 1, gene_symbol=g, inheritance_model="AUTOSOMAL_DOMINANT", contributing_variants=[],
                      contributing_variant_count=0, is_variant_pair=False, any_contributing_variant_non_pass=False)
            for i, g in enumerate(genes)])

    st = compare([result("PROFILE_A", ["X1", "X2"]), result("PROFILE_B", ["Y1", "Y2"])],
                 {"PROFILE_A": False, "PROFILE_B": True}, {"PROFILE_A": 7, "PROFILE_B": 7})
    assert st.verdict == "unstable" and not st.genes_in_all_profiles


# ── failure behaviour (PRD §25: a blocked stage is a result, not a defect) ──


def test_solver_out_of_memory_blocks_with_an_actionable_message(normalized, baseline):
    c = baseline(normalized, runner=bf.failing_run_job("oom")).candidate_set
    assert c.status == Status.BASELINE_ANALYSIS_BLOCKED
    assert "SOLVER_OUT_OF_MEMORY" in codes(c, "BLOCKER")
    issue = next(i for i in c.issues if i.code == "SOLVER_OUT_OF_MEMORY")
    assert "8 GB" in issue.suggested_action and all(r.status == "failed" for r in c.results)


def test_solver_rejecting_the_input_names_the_missing_capability(normalized, baseline):
    c = baseline(normalized, runner=bf.failing_run_job("rejected")).candidate_set
    assert c.status == Status.BASELINE_ANALYSIS_BLOCKED and "SOLVER_REJECTED_INPUT" in codes(c, "BLOCKER")
    issue = next(i for i in c.issues if i.code == "SOLVER_REJECTED_INPUT")
    assert "Do not rewrite the VCF" in issue.suggested_action and "decomposition" in issue.suggested_action


def test_missing_solver_blocks_without_pretending(normalized, baseline):
    c = baseline(normalized, install=False).candidate_set
    assert c.status == Status.BASELINE_ANALYSIS_BLOCKED and "SOLVER_UNAVAILABLE" in codes(c, "BLOCKER")
    assert all(r.status == "not_run" for r in c.results) and c.stability.verdict == "insufficient"


def test_changed_source_vcf_blocks(normalized, baseline, tmp_path):
    (tmp_path / "case" / "case.vcf.gz").write_bytes(b"\x1f\x8b" + b"tampered")
    c = baseline(normalized).candidate_set
    assert c.status == Status.BASELINE_ANALYSIS_BLOCKED and "SOURCE_ASSET_CHANGED" in codes(c, "BLOCKER")


def test_sanitized_normalized_case_is_refused(normalized, baseline):
    with pytest.raises(BaselineUsageError):
        baseline(normalized.parent / "normalized_case.sanitized.json")


def test_dry_run_writes_configuration_without_running(normalized, baseline, tmp_path):
    c = baseline(normalized, dry_run=True).candidate_set
    assert all(r.status == "not_run" for r in c.results)
    analyses = list((tmp_path / "baseline" / "native").rglob("analysis.yml"))
    assert len(analyses) == 4 and all(yaml.safe_load(a.read_text())["analysisMode"] == "PASS_ONLY" for a in analyses)


# ── artifact, privacy, retention ────────────────────────────────────────────


def test_assumptions_are_recorded_not_written_back_into_the_case(normalized, baseline):
    result = baseline(normalized)
    ids = {a.id for a in result.candidate_set.profiles[0].assumptions}
    assert ids == {"ASSUME_HPO_DESCRIBE_PROBAND", "ASSUME_ANALYSIS_ROLE_PROBAND", "ASSUME_NO_REMM_NONCODING_SCORING"}
    assert all(a.scope == "this_analysis" for a in result.candidate_set.profiles[0].assumptions)
    norm = json.loads(normalized.read_text())
    assert norm["phenotype"]["polarity_counts"] == {"unspecified": 4}  # Stage 02 truth untouched
    assert all(s["role"] == "unknown" for s in norm["genome"]["samples"])


def test_variant_level_details_are_private_only(normalized, baseline):
    result = baseline(normalized)
    private = json.loads((result.run_dir / "raw_candidate_set.private.json").read_text())
    sanitized = json.loads((result.run_dir / "raw_candidate_set.sanitized.json").read_text())
    priv_variant = private["results"][0]["candidates"][0]["contributing_variants"][0]
    san_variant = sanitized["results"][0]["candidates"][0]["contributing_variants"][0]
    assert priv_variant["contig"] and priv_variant["position"] and priv_variant["hgvs"]
    assert san_variant["contig"] is None and san_variant["position"] is None and san_variant["hgvs"] is None
    assert san_variant["source_filter_status"] == priv_variant["source_filter_status"]  # evidence survives
    assert san_variant["variant_ref"] == priv_variant["variant_ref"]  # stable reference for later stages


def test_report_carries_genes_but_no_variant_rows_or_labels(normalized, baseline):
    result = baseline(normalized)
    text = (result.run_dir / "baseline_report.md").read_text()
    log = (result.run_dir / "baseline.log").read_text()
    assert "SYNGENE1" in text and "compound-het" in text.lower()
    from rarepipe.testing.fixtures import PROBAND

    for blob in (text, log):
        assert PROBAND not in blob
        assert "p.(Lys34Arg)" not in blob and "1000100" not in blob and "rs000000" not in blob
    assert "not a diagnosis" in text.lower() and "no candidate was reranked" in text.lower()


def test_retention_marks_native_outputs_for_deletion(normalized, baseline):
    c = baseline(normalized).candidate_set
    assert c.retention.native_solver_outputs == "delete_required"
    assert c.retention.raw_candidate_set == "delete_required_review"
    assert c.retention.top_n_findings == "retainable_after_review"
    native = [f for r in c.results for f in r.native_output_files]
    assert native and not any(f.startswith("/") for f in native)  # relative: the absolute root is private + run-specific
    assert c.execution.native_output_root and "/native/" in c.execution.native_output_root


def test_rerun_is_semantically_identical(normalized, baseline):
    first = baseline(normalized, out="b1").candidate_set
    second = baseline(normalized, out="b2").candidate_set
    assert first.execution.run_id != second.execution.run_id
    assert first.semantic_digest == second.semantic_digest


def test_committed_schema_matches_code():
    from rarepipe.stages.baseline.schema import schema_json

    committed = (Path(__file__).resolve().parents[1] / "schemas" / "raw_candidate_set.schema.json").read_text()
    assert committed == schema_json(), "run: uv run rarepipe schema --artifact raw_candidate_set --output schemas/raw_candidate_set.schema.json"


def test_solver_resources_are_pinned_from_the_lock(normalized, baseline, tmp_path):
    from rarepipe.resources.lock import ResourceKind, register

    res = tmp_path / "res"
    (res / "exomiser").mkdir(parents=True)
    dist = res / "exomiser" / "exomiser-cli-15.1.0-distribution.zip"
    dist.write_bytes(b"synthetic distribution")
    data = res / "exomiser" / "2602_hg38.zip"
    data.write_bytes(b"synthetic data bundle")
    register(res, ResourceKind.EXOMISER_DISTRIBUTION, dist, name="Exomiser CLI 15.1.0", version="15.1.0")
    register(res, ResourceKind.EXOMISER_DATA, data, name="Exomiser hg38 data", version="2602_hg38")
    c = baseline(normalized, resources=res).candidate_set
    assert c.provenance.solver.distribution_sha256 and c.provenance.solver.data_sha256["exomiser_data:2602_hg38"]
