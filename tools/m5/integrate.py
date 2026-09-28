#!/usr/bin/env python3
"""Merge the specialists' per-field values into proposals.json, tolerantly and visibly.

Each specialist report embeds a JSON field map. Extraction can fail: a report is written by a
language model and one of them emitted a duplicated key fragment. Nothing is guessed here — a field
that cannot be parsed is reported by name and left out, so it shows up as DISCUSSION_ONLY in the
accounting rather than silently inheriting a status it was never given.

Usage: uv run python tools/m5/integrate.py <packet-v3-dir> <proposals-in> <proposals-out>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATUSES = {"APPLY_READY", "CONDITIONAL", "DISCUSSION_ONLY", "BLOCKED_EVIDENCE", "BLOCKED_HUMAN"}
SOURCES = {"a2_decision_designs.md": "M5_W004", "a2_fields.md": "M5_W004",
           "a3_assay_choices.md": ("M5_W001", "M5_W002"),
           "a4_pilot_and_criteria.md": ("M5_W003", "M5_W004"), "a4_fields.md": "M5_W003"}


def _repair(text: str) -> tuple[str, list[str]]:
    """Fix only mechanical damage we can prove is damage; report each repair."""
    notes = []
    fixed, n = re.subn(r'"\w[\w ]*?\s{2,}("note"\s*:)', r'\1', text)
    if n:
        notes.append(f"removed {n} truncated duplicate key fragment(s)")
    return fixed, notes


def extract(path: Path) -> tuple[dict, list[str]]:
    text = path.read_text()
    problems: list[str] = []
    fields: dict = {}
    for block in re.findall(r"```json\s*\n(.*?)\n```", text, re.S):
        repaired, notes = _repair(block)
        problems += [f"{path.name}: {n}" for n in notes]
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: a JSON block did not parse ({exc.msg} at line {exc.lineno}); "
                            "its fields are omitted, not guessed")
            continue
        found = data.get("field_values") if isinstance(data, dict) else None
        if found is None and isinstance(data, dict) and any("." in k for k in data):
            found = data
        if isinstance(found, dict):
            fields.update(found)
    return fields, problems


def main() -> int:
    packet, src, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    proposals = json.loads(src.read_text())
    items = {i["id"]: i for i in proposals["items"]}
    real = set()
    validator = json.loads((packet.parent / "validator_output.json").read_text())
    real = {g["gap_id"] for g in validator["scientific_readiness"]}

    all_problems: list[str] = []
    merged_total = 0
    for name, target in SOURCES.items():
        path = packet / name
        if not path.exists():
            all_problems.append(f"{name}: missing, no field values merged from it")
            continue
        fields, problems = extract(path)
        all_problems += problems
        targets = (target,) if isinstance(target, str) else target
        for gid, spec in fields.items():
            if gid not in real:
                all_problems.append(f"{name}: '{gid}' is not a validator gap id; dropped")
                continue
            owner = next((t for t in targets if gid in items[t]["source_gap_ids"]), None)
            if owner is None:
                all_problems.append(f"{name}: '{gid}' is not owned by {targets}; dropped")
                continue
            if not isinstance(spec, dict) or "value" not in spec:
                all_problems.append(f"{name}: '{gid}' has no explicit value key; dropped")
                continue
            status = spec.get("status")
            if status is not None and status not in STATUSES:
                all_problems.append(f"{name}: '{gid}' has unknown status {status!r}; treated as DISCUSSION_ONLY")
                spec = {**spec, "status": "DISCUSSION_ONLY"}
            items[owner].setdefault("field_values", {})[gid] = spec
            merged_total += 1

    proposals.setdefault("corrections", []).append({
        "at": "2026-09-28",
        "finding": "Integration review: narrative-only corrections are insufficient; the embedded field values "
                   "must change with the text.",
        "correction": f"Merged {merged_total} per-field values from the corrected specialist reports via "
                      "tools/m5/integrate.py. Fields that could not be parsed or verified are listed in "
                      "integration_problems and were left unset, so they count as DISCUSSION_ONLY rather than "
                      "inheriting an unearned status.",
        "integration_problems": all_problems,
    })
    dst.write_text(json.dumps(proposals, indent=2) + "\n")
    print(json.dumps({"merged_fields": merged_total, "problems": all_problems,
                      "items_with_field_values": {k: len(v.get("field_values") or {}) for k, v in items.items()}},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
