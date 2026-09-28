#!/usr/bin/env python3
"""Per-field accounting for an M5 packet (R02).

The first packet counted work-package coverage as field readiness: 39 analysis gaps were reported
ready while three of them held an explicit `null`, and a wildcard path stood in for individual
fields. This derives one status per real gap from the proposals' own `field_values` map, so a count
can never again be larger than the number of fields that actually carry a value.

Statuses, narrowest to widest:
  APPLY_READY        a complete value, no unresolved dependency: can be written into a successor version
  CONDITIONAL        a complete value whose use depends on a named unresolved input
  DISCUSSION_ONLY    a described option, not yet a value a reviewer could apply
  BLOCKED_EVIDENCE   deliberately null: needs a measurement or an institutional fact
  BLOCKED_HUMAN      needs a human decision or attestation
  UNMAPPED           no proposal claims it (a defect)
Only a human acceptance that passes the native validator moves a field beyond these.

Usage: uv run python tools/m5/field_accounting.py <packet-dir> [--write]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ORDER = ["APPLY_READY", "CONDITIONAL", "DISCUSSION_ONLY", "BLOCKED_EVIDENCE", "BLOCKED_HUMAN", "UNMAPPED"]


def build(packet: Path) -> dict:
    validator = json.loads((packet / "validator_output.json").read_text())
    proposals = json.loads((packet / "proposals.json").read_text())
    gaps = [g["gap_id"] for g in validator["scientific_readiness"]]
    owner = {g["gap_id"]: g["owner"] for g in validator["scientific_readiness"]}

    rows: dict[str, dict] = {}
    for item in proposals["items"]:
        declared = item.get("field_values") or {}
        for gid in item["source_gap_ids"]:
            entry = declared.get(gid)
            if entry is None:
                status = "DISCUSSION_ONLY"
                value_present = False
                depends: list[str] = []
                note = ("no per-field value declared: the proposal discusses this field but does not yet give a "
                        "value a reviewer could apply")
            else:
                value_present = entry.get("value") is not None
                depends = list(entry.get("depends_on") or [])
                note = entry.get("note", "")
                explicit = entry.get("status")
                if explicit in ORDER:
                    status = explicit
                elif not value_present:
                    status = "BLOCKED_HUMAN" if entry.get("blocked_on") == "human" else "BLOCKED_EVIDENCE"
                elif depends:
                    status = "CONDITIONAL"
                else:
                    status = "APPLY_READY"
            rows[gid] = {"gap_id": gid, "owner": owner.get(gid), "proposal": item["id"],
                         "proposal_status": item["status"], "field_status": status,
                         "value_present": value_present, "depends_on": depends, "note": note}
    for gid in gaps:
        rows.setdefault(gid, {"gap_id": gid, "owner": owner.get(gid), "proposal": None, "proposal_status": None,
                              "field_status": "UNMAPPED", "value_present": False, "depends_on": [],
                              "note": "no proposal claims this gap"})

    counts = Counter(r["field_status"] for r in rows.values())
    return {
        "schema_version": "1.0",
        "document_type": "M5_FIELD_ACCOUNTING",
        "source_validator_artifact": "validator_output.json",
        "plan_version": validator["plan_version"],
        "plan_content_digest": validator["plan_content_digest"],
        "total_validator_gaps": len(gaps),
        "counts": {k: counts.get(k, 0) for k in ORDER},
        "accepted_by_a_human": 0,
        "gaps_the_native_validator_still_reports": len(gaps),
        "interpretation": (
            "APPLY_READY counts fields that carry a complete value with no unresolved dependency. It is not a count "
            "of closed gaps: the native validator reports all "
            f"{len(gaps)} until a human accepts edits through the versioned workflow and a real validation run "
            "confirms them."),
        "fields": [rows[g] for g in gaps],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packet", type=Path)
    ap.add_argument("--write", action="store_true", help="write field_accounting.json into the packet")
    args = ap.parse_args()
    report = build(args.packet)
    if args.write:
        (args.packet / "field_accounting.json").write_text(json.dumps(report, indent=2) + "\n")
        register_path = args.packet / "gap_register.json"
        register = json.loads(register_path.read_text())
        c = report["counts"]
        register["progress"] = {
            "gaps_inspected": report["total_validator_gaps"],
            "fields_apply_ready": c["APPLY_READY"],
            "fields_conditional": c["CONDITIONAL"],
            "fields_discussion_only": c["DISCUSSION_ONLY"],
            "fields_blocked_on_evidence": c["BLOCKED_EVIDENCE"],
            "fields_blocked_on_human_decision": c["BLOCKED_HUMAN"],
            "fields_unmapped": c["UNMAPPED"],
            "externally_confirmed_facts": 0,
            "human_accepted_plan_fields": 0,
            "gaps_the_native_validator_still_reports": report["gaps_the_native_validator_still_reports"],
        }
        register_path.write_text(json.dumps(register, indent=2) + "\n")
    print(json.dumps({"counts": report["counts"], "total": report["total_validator_gaps"],
                      "accepted_by_a_human": 0}, indent=2))
    return 1 if report["counts"]["UNMAPPED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
