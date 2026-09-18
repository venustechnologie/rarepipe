"""Stage 05 — the submission must be generated, not hand-made, and must survive the official parser."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import pytest

from rarepipe.stages.track1 import epcr, select
from rarepipe.stages.track1.model import CSV_COLUMNS, MAX_ROWS
from rarepipe.stages.track1.stage import ExportRequest, RecordRequest, Track1UsageError, record_result, run_export


def _variant(contig, pos, ref, alt, score=0.9, fc="missense_variant"):
    return {"variant_ref": f"{contig}:{pos}", "contig": contig, "position": pos, "ref": ref, "alt": alt,
            "solver_variant_score": score, "functional_class": fc, "hgvs": None, "genotype": "0/1",
            "source_filter_status": "PASS"}


def _candidate(rank, gene, moi, variants, pair=False):
    return {"rank": rank, "gene_symbol": gene, "gene_id": "1", "inheritance_model": moi, "p_value": 0.01,
            "score_combined": 0.5, "score_phenotype": 0.5, "score_variant": 0.9,
            "contributing_variants": variants, "contributing_variant_count": len(variants),
            "is_variant_pair": pair, "phase": None, "any_contributing_variant_non_pass": False, "solver_evidence": {}}


@pytest.fixture
def case(tmp_path: Path):
    """A synthetic case: one adjudicated pair plus baseline candidates across two profiles."""
    a = _variant("chr15", 40200000, "C", "T", 1.0, "stop_gained")
    b = _variant("chr15", 40210911, "G", "A", 0.8, "missense_variant")
    other = [_candidate(2, "GENE2", "AD", [_variant("chr1", 1000, "A", "G", 0.7)]),
             _candidate(3, "GENE3", "AR", [_variant("chr2", 2000, "A", "G", 0.6),
                                           _variant("chr2", 2500, "T", "C", 0.5)], pair=True),
             _candidate(4, "GENE4", "AD", [_variant("chr3", 3000, "A", "G", 0.4)])]
    results = [{"profile_id": p, "status": "COMPLETED", "candidates": [_candidate(1, "BUB1B", "AR", [a, b], pair=True)] + other}
               for p in ("PROFILE_A", "PROFILE_B")]
    results[1]["candidates"].append(_candidate(5, "GENE5", "AD", [_variant("chr4", 4000, "A", "G", 0.3)]))
    candidates = {"case_id": "CASE_X", "schema": {"name": "RawCandidateSet", "version": "1.1.0"},
                  "profiles": [{"profile_id": "PROFILE_A"}, {"profile_id": "PROFILE_B"}], "results": results,
                  "stability": {"verdict": "STABLE", "verdict_basis": "top-1 identical across profiles"},
                  "semantic_digest": "sha256:baseline", "execution": {"run_id": "RUN_BASE"},
                  "provenance": {"source_case": {"case_manifest_run_id": "RUN_INTAKE"},
                                 "solver": {"name": "Exomiser", "version": "15.1.0"}}}
    adjudication = {"case_id": "CASE_X", "visibility": "private", "gene_symbol": "BUB1B", "inheritance_model": "AR",
                    "variants": [{"role": "variant_a", "assembly": "GRCh38", "contig": "chr15", "position": 40210911,
                                  "ref": "G", "alt": "A", "molecular_consequence": "missense_variant", "hgvs": "c.1A>G"},
                                 {"role": "variant_b", "assembly": "GRCh38", "contig": "chr15", "position": 40200000,
                                  "ref": "C", "alt": "T", "molecular_consequence": "stop_gained", "hgvs": "c.2C>T"}],
                    "claims": [{"claim_id": "C1", "statement": "x", "assessment": "supported"}],
                    "evidence_summary": {"overall": "unresolved", "overall_basis": "phase unresolved",
                                         "molecular_mechanistic": "supported"},
                    "phase": {"status": "unresolved"}, "semantic_digest": "sha256:adj",
                    "execution": {"run_id": "RUN_ADJ"},
                    "provenance": {"source_hypothesis": {"raw_candidate_set_run_id": "RUN_BASE", "solver_rank": 1,
                                                         "normalized_case_run_id": "RUN_NORM",
                                                         "profiles_supporting": ["PROFILE_A", "PROFILE_B"]}}}
    cpath, apath = tmp_path / "candidates.json", tmp_path / "adjudication.private.json"
    cpath.write_text(json.dumps(candidates))
    apath.write_text(json.dumps(adjudication))
    return cpath, apath, tmp_path / "out"


COMPLETE_DISCLOSURE = ("Anthropic Claude (Claude Code), Max plan, no training on customer content; OpenAI ChatGPT, "
                       "Plus plan, chat history and training off. Used for code, methodology and review of sanitized "
                       "findings. No raw VCF/FASTQ, no exact coordinates, no genotype tables.")


def export(case, **kw):
    cpath, apath, out = case
    kw.setdefault("llm_disclosure", COMPLETE_DISCLOSURE)
    return run_export(ExportRequest(raw_candidate_set=cpath, adjudication=apath, output=out, argv=["test"], **kw))


def rows_of(result):
    return list(csv.DictReader(io.StringIO(result.csv_text)))


def test_submission_is_generated_and_valid(case):
    r = export(case)
    assert r.package.valid, [c for c in r.package.checks if not c.passed]
    assert next(csv.reader(io.StringIO(r.csv_text))) == CSV_COLUMNS
    assert 1 < len(rows_of(r)) <= MAX_ROWS


def test_leading_row_is_the_adjudicated_pair_in_coordinate_order(case):
    first = rows_of(export(case))[0]
    assert first["proband_id"] == "PROBAND01"
    assert (first["chrom_1"], int(first["pos_1"])) == ("chr15", 40200000)
    assert (first["chrom_2"], int(first["pos_2"])) == ("chr15", 40210911)
    assert float(first["epcr"]) == max(float(x["epcr"]) for x in rows_of(export(case)))


def test_the_pair_is_one_row_not_two(case):
    r = export(case)
    pair = {("chr15", "40200000"), ("chr15", "40210911")}
    singles = [x for x in rows_of(r) if not x["chrom_2"] and (x["chrom_1"], x["pos_1"]) in pair]
    assert not singles, "an allele of the adjudicated pair was also submitted on its own"
    assert r.package.rows[0].configuration == "candidate_compound_heterozygous"
    assert r.package.rows[0].phase == "unresolved"


def test_no_configuration_is_submitted_twice_despite_appearing_in_several_profiles(case):
    configs = [frozenset([(x["chrom_1"], x["pos_1"])] + ([(x["chrom_2"], x["pos_2"])] if x["chrom_2"] else []))
               for x in rows_of(export(case))]
    assert len(set(configs)) == len(configs)


def test_epcr_is_decreasing_distinct_and_in_range(case):
    values = [float(x["epcr"]) for x in rows_of(export(case))]
    assert values == sorted(values, reverse=True) and len(set(values)) == len(values)
    assert all(0 < v <= 1 for v in values)
    assert epcr.schedule(10)[0] == 0.90


def test_generation_is_deterministic(case):
    a, b = export(case), export(case)
    assert a.csv_text == b.csv_text
    assert a.package.provenance.prediction_digest == b.package.provenance.prediction_digest


def test_snapshot_records_what_was_known_before_the_answer(case):
    snap = export(case).package.provenance.validation_snapshot
    assert snap.created_before_ground_truth_query is True
    assert snap.baseline_run == "RUN_BASE" and snap.adjudication_run == "RUN_ADJ"
    assert snap.normalization_run == "RUN_NORM" and snap.intake_run == "RUN_INTAKE"


def test_manifest_carries_no_variant_identity_but_the_csv_does(case):
    r = export(case)
    manifest = json.dumps(r.manifest.model_dump(mode="json"))
    assert "40200000" not in manifest and "chr15" not in manifest
    assert "40200000" in r.csv_text
    assert json.loads(json.dumps(r.package.model_dump(mode="json")))["rows"][0]["variants"][0]["pos"] == 40200000


def test_methods_report_carries_no_coordinates(case):
    r = export(case)
    text = (r.run_dir / r.package.files[1].name).read_text()
    assert "40200000" not in text and "40210911" not in text
    assert "not empirically calibrated" in text and "unresolved" in text.lower()


def test_sanitized_adjudication_is_refused(case, tmp_path):
    cpath, apath, out = case
    sanitized = json.loads(apath.read_text())
    sanitized["visibility"] = "sanitized"
    for v in sanitized["variants"]:
        v["contig"] = v["position"] = v["ref"] = v["alt"] = None
    bad = tmp_path / "adj.sanitized.json"
    bad.write_text(json.dumps(sanitized))
    with pytest.raises(Track1UsageError):
        run_export(ExportRequest(raw_candidate_set=cpath, adjudication=bad, output=out, argv=["t"]))


def test_contig_naming_matches_what_the_evaluator_compares():
    assert select.ucsc_contig("15") == "chr15" and select.ucsc_contig("chr15") == "chr15"
    assert select.ucsc_contig("MT") == "chrM"
    with pytest.raises(ValueError):
        select.ucsc_contig("NC_000015.10")


def test_result_is_recorded_as_case_state_and_names_a_branch(case, tmp_path):
    r = export(case)
    response = tmp_path / "response.txt"
    response.write_text("FULL MATCH at rank 1; rank points 100; F-max 1.0")
    result, run_dir = record_result(RecordRequest(
        package_run=r.run_dir, output=tmp_path / "validation", match="FULL", raw_response=response.read_text(),
        full_match_rank=1, rank_points=100.0, f_max=1.0, f_max_threshold=0.9, argv=["t"]))
    assert result.branch == "A_full_match"
    assert result.prediction_digest == r.package.provenance.prediction_digest
    assert result.snapshot_digest == r.package.provenance.snapshot_digest
    assert "not a training signal" in result.upstream_modification
    assert (run_dir / "external_validation_result.json").exists()


def test_unknown_match_verdict_is_refused(case, tmp_path):
    r = export(case)
    with pytest.raises(Track1UsageError):
        record_result(RecordRequest(package_run=r.run_dir, output=tmp_path / "v2", match="probably", raw_response="x"))


@pytest.mark.skipif(not os.environ.get("RAREPIPE_TRACK1_SCORER"), reason="official evaluation.py not provisioned")
def test_official_parser_accepts_the_file(case):
    r = export(case, official_scorer=Path(os.environ["RAREPIPE_TRACK1_SCORER"]))
    assert r.package.official_scorer.parsed_ok is True
    assert r.package.official_scorer.ranks_as_submitted is True
    assert r.package.official_scorer.rows_parsed == len(r.package.rows)


def test_a_single_allele_of_an_already_submitted_pair_does_not_waste_a_row(case, tmp_path):
    """Exomiser reports the same gene under several models; one allele of a pair we already
    submitted cannot earn a point that pair does not already earn."""
    cpath, apath, out = case
    candidates = json.loads(cpath.read_text())
    lone = _candidate(2, "BUB1B", "AD", [_variant("chr15", 40200000, "C", "T", 1.0, "stop_gained")])
    for result in candidates["results"]:
        result["candidates"].insert(1, lone)
    cpath.write_text(json.dumps(candidates))
    r = export(case)
    rows = rows_of(r)
    assert not any(not x["chrom_2"] and x["pos_1"] == "40200000" for x in rows), "submitted half of our own pair"
    assert [x.gene_symbol for x in r.package.rows].count("BUB1B") == 1


def test_an_unfilled_ai_disclosure_blocks_the_package(case):
    """An unresolved placeholder in a required disclosure is worse than no disclosure."""
    r = run_export(ExportRequest(raw_candidate_set=case[0], adjudication=case[1], output=case[2], argv=["t"]))
    failed = [c.check for c in r.package.checks if not c.passed]
    assert not r.package.valid and any("AI-assistance disclosure" in c for c in failed)


def test_a_broken_provenance_chain_blocks_the_package(case, tmp_path):
    cpath, apath, out = case
    candidates = json.loads(cpath.read_text())
    del candidates["provenance"]["source_case"]["case_manifest_run_id"]
    cpath.write_text(json.dumps(candidates))
    r = export(case)
    assert not r.package.valid
    assert not r.package.provenance.validation_snapshot.provenance_chain_complete
    assert any("provenance chain" in c.check and not c.passed for c in r.package.checks)


def test_the_intake_run_is_recovered_from_the_normalized_case(case, tmp_path):
    cpath, apath, out = case
    candidates = json.loads(cpath.read_text())
    del candidates["provenance"]["source_case"]["case_manifest_run_id"]
    candidates["provenance"]["source_case"]["normalized_case_semantic_digest"] = "sha256:norm"
    cpath.write_text(json.dumps(candidates))
    norm = tmp_path / "normalized_case.sanitized.json"
    norm.write_text(json.dumps({"execution": {"run_id": "RUN_NORM"}, "semantic_digest": "sha256:norm",
                                "provenance": {"source_manifest": {"run_id": "RUN_INTAKE_2",
                                                                   "semantic_digest": "sha256:manifest"}}}))
    r = export(case, normalized_case=norm)
    snap = r.package.provenance.validation_snapshot
    assert snap.intake_run == "RUN_INTAKE_2" and snap.provenance_chain_complete
    assert snap.case_manifest_digest == "sha256:manifest"
    assert r.package.valid


def test_a_normalized_case_the_baseline_never_used_is_refused(case, tmp_path):
    cpath, apath, out = case
    candidates = json.loads(cpath.read_text())
    del candidates["provenance"]["source_case"]["case_manifest_run_id"]
    cpath.write_text(json.dumps(candidates))
    wrong = tmp_path / "other_normalized.json"
    wrong.write_text(json.dumps({"execution": {"run_id": "RUN_SOMETHING_ELSE"},
                                 "provenance": {"source_manifest": {"run_id": "RUN_X"}}}))
    with pytest.raises(Track1UsageError):
        export(case, normalized_case=wrong)


def test_submitter_name_lands_in_both_filenames(case):
    r = export(case, submitter="jane-doe")
    names = [f.name for f in r.package.files]
    assert "jane-doe_rarepipe-exomiser-adjudicated.csv" in names
    assert "jane-doe_track1_report.md" in names
    assert all((r.run_dir / n).exists() for n in names[:2])
    assert r.package.submission.recommended_upload_filename == "jane-doe_rarepipe-exomiser-adjudicated.csv"
