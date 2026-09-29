"""The M5 packet checks: they must catch a fabricated digest and an over-counted field (R01, R02)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "m5"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


consistency = _load("check_consistency")
accounting = _load("field_accounting")

REAL = "sha256:" + "a" * 64
FAKE = "sha256:" + "b" * 64


def _packet(tmp_path: Path, *, digest: str = REAL, field_values: dict | None = None,
            gap_ids: list[str] | None = None) -> Path:
    packet = tmp_path / "packet"
    packet.mkdir(parents=True)
    gaps = [{"gap_id": "E01_ACT.method", "owner": "assay_scientist", "object_ref": "E01_ACT", "field": "method",
             "reason": "r", "blocks": "scientific_freeze"},
            {"gap_id": "EXP01.analysis.meaningful_effect", "owner": "statistician", "object_ref": "EXP01",
             "field": "analysis.meaningful_effect", "reason": "r", "blocks": "scientific_freeze"}]
    (packet / "validator_output.json").write_text(json.dumps({
        "plan_id": "PP_X", "plan_version": "PP_X@0001-aaaa", "plan_content_digest": REAL,
        "review_digest": "sha256:" + "c" * 64, "lifecycle": "DRAFT",
        "baseline": {"status": "CANDIDATE"}, "freezable": False, "structural": [], "provenance": [], "policy": [],
        "scientific_readiness": gaps}))
    (packet / "gap_register.json").write_text(json.dumps({
        "source_plan_version": "PP_X@0001-aaaa", "source_plan_content_digest": REAL,
        "source_gap_records": gaps, "work_packages": [], "progress": {}}))
    (packet / "proposals.json").write_text(json.dumps({
        "baseline": {"plan_id": "PP_X", "plan_version": "PP_X@0001-aaaa", "plan_content_hash": digest},
        "items": [{"id": "W1", "status": "READY_FOR_HUMAN_REVIEW",
                   "source_gap_ids": gap_ids or [g["gap_id"] for g in gaps],
                   "field_values": field_values} if field_values is not None else
                  {"id": "W1", "status": "READY_FOR_HUMAN_REVIEW",
                   "source_gap_ids": gap_ids or [g["gap_id"] for g in gaps]}]}))
    return packet


def test_a_fabricated_digest_is_caught(tmp_path):
    problems = consistency.check(_packet(tmp_path, digest=FAKE), None, None)
    assert any("plan_content_hash" in p and "disagrees" in p for p in problems)
    assert not consistency.check(_packet(tmp_path / "ok", digest=REAL), None, None), "a correct packet passes"


def test_a_digest_in_prose_that_the_packet_does_not_carry_is_caught(tmp_path):
    packet = _packet(tmp_path)
    (packet / "review_packet.md").write_text(f"Plan digest `{FAKE}` as reviewed.")
    assert any(FAKE in p and "review_packet.md" in p for p in consistency.check(packet, None, None))


def test_missing_double_claimed_and_invented_gaps_are_caught(tmp_path):
    packet = _packet(tmp_path, gap_ids=["E01_ACT.method", "E01_ACT.method", "NOT_A_GAP.field"])
    problems = consistency.check(packet, None, None)
    assert any("absent from the validator output" in p for p in problems)
    assert any("covered by no proposal" in p for p in problems)
    assert any("more than one proposal" in p for p in problems)


def test_a_ready_item_advertising_a_null_field_is_caught(tmp_path):
    packet = _packet(tmp_path, field_values={
        "E01_ACT.method": {"value": "MPM-2 flow cytometry"},
        "EXP01.analysis.meaningful_effect": {"value": None}})
    assert any("carry no value" in p and "meaningful_effect" in p for p in consistency.check(packet, None, None))


def test_field_accounting_never_counts_a_null_as_ready(tmp_path):
    packet = _packet(tmp_path, field_values={
        "E01_ACT.method": {"value": "MPM-2 flow cytometry"},
        "EXP01.analysis.meaningful_effect": {"value": None, "note": "needs a scientific judgement"}})
    report = accounting.build(packet)
    assert report["counts"]["APPLY_READY"] == 1
    assert report["counts"]["BLOCKED_EVIDENCE"] == 1
    assert report["accepted_by_a_human"] == 0
    assert report["gaps_the_native_validator_still_reports"] == report["total_validator_gaps"] == 2


def test_a_value_with_an_unresolved_dependency_is_conditional_not_ready(tmp_path):
    packet = _packet(tmp_path, field_values={
        "E01_ACT.method": {"value": "MPM-2 flow", "depends_on": ["platform confirmation"]},
        "EXP01.analysis.meaningful_effect": {"value": None}})
    assert accounting.build(packet)["counts"] == {"APPLY_READY": 0, "CONDITIONAL": 1, "DISCUSSION_ONLY": 0,
                                                 "BLOCKED_EVIDENCE": 1, "BLOCKED_HUMAN": 0, "UNMAPPED": 0}


def test_a_gap_no_proposal_claims_is_unmapped(tmp_path):
    packet = _packet(tmp_path, gap_ids=["E01_ACT.method"])
    report = accounting.build(packet)
    assert report["counts"]["UNMAPPED"] == 1


def test_an_undeclared_field_is_discussion_only_not_ready(tmp_path):
    report = accounting.build(_packet(tmp_path))
    assert report["counts"]["DISCUSSION_ONLY"] == 2 and report["counts"]["APPLY_READY"] == 0


def test_a_stale_proposal_value_beside_corrected_fields_is_caught(tmp_path):
    """The successor-review defect: two active specifications in one document."""
    packet = _packet(tmp_path, field_values={
        "E01_ACT.method": {"value": "MPM-2 flow cytometry", "status": "CONDITIONAL"},
        "EXP01.analysis.meaningful_effect": {"value": None, "status": "BLOCKED_HUMAN"}})
    proposals = json.loads((packet / "proposals.json").read_text())
    item = proposals["items"][0]
    item["status"] = "NEEDS_EXTERNAL_EVIDENCE"
    item["proposal"] = {"value": {"E01_ACT.method": "a 30% cutoff the fields already rejected",
                                 "EXP01.analysis.meaningful_effect": None}}
    (packet / "proposals.json").write_text(json.dumps(proposals))
    problems = consistency.check(packet, None, None)
    assert any("disagrees with field_values" in p for p in problems)

    item["proposal"]["value"]["E01_ACT.method"] = "MPM-2 flow cytometry"
    (packet / "proposals.json").write_text(json.dumps(proposals))
    assert not [p for p in consistency.check(packet, None, None) if "field_values" in p]


def test_an_undeclared_superseded_reason_is_caught(tmp_path):
    packet = _packet(tmp_path, field_values={"E01_ACT.method": {"value": "x", "status": "CONDITIONAL"},
                                             "EXP01.analysis.meaningful_effect": {"value": None,
                                                                                  "status": "BLOCKED_HUMAN"}})
    proposals = json.loads((packet / "proposals.json").read_text())
    item = proposals["items"][0]
    item["status"] = "NEEDS_EXTERNAL_EVIDENCE"
    item["proposal"] = {"value": {"E01_ACT.method": "x", "EXP01.analysis.meaningful_effect": None}}
    item["superseded_proposal"] = {"object": {"old": True}}
    (packet / "proposals.json").write_text(json.dumps(proposals))
    assert any("must say why it was superseded" in p for p in consistency.check(packet, None, None))


def test_a_stale_field_status_summary_is_caught(tmp_path):
    """The work-package table read a stored summary that no longer matched its fields."""
    packet = _packet(tmp_path, field_values={
        "E01_ACT.method": {"value": "x", "status": "CONDITIONAL"},
        "EXP01.analysis.meaningful_effect": {"value": None, "status": "BLOCKED_HUMAN"}})
    proposals = json.loads((packet / "proposals.json").read_text())
    item = proposals["items"][0]
    item["status"] = "NEEDS_EXTERNAL_EVIDENCE"
    item["proposal"] = {"value": {"E01_ACT.method": "x", "EXP01.analysis.meaningful_effect": None}}
    item["field_status_summary"] = {"APPLY_READY": 2}
    (packet / "proposals.json").write_text(json.dumps(proposals))
    assert any("field_status_summary" in p and "disagrees" in p for p in consistency.check(packet, None, None))

    item["field_status_summary"] = {"CONDITIONAL": 1, "BLOCKED_HUMAN": 1}
    (packet / "proposals.json").write_text(json.dumps(proposals))
    assert not [p for p in consistency.check(packet, None, None) if "field_status_summary" in p]
