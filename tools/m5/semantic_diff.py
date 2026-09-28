#!/usr/bin/env python3
"""Semantic diff between two packet proposal files, naming its exact before/after artifacts.

Written because a summary of newly added fields missed the actual failure: corrected field values had
been added while the contradictory proposal objects stayed active, so the diff has to report unchanged
objects that now conflict, not only what was added.

Usage: uv run python tools/m5/semantic_diff.py <before.json> <after.json> [--out diff.md]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CONFLICT_MARKERS = [
    ("30%", "an arbitrary matched-subset threshold"),
    ("resolves all 32", "one pilot resolving every threshold gap"),
    ("comes from the M5_W003 pilot", "a pilot-derived margin"),
    ("Holm adjustment across them as the default", "a defaulted multiplicity procedure"),
    ("complete in every other respect", "a claim of completeness apart from meaningful effect"),
    ("complete in structure", "a claim of structural completeness"),
]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


WITHDRAWN = ("remains removed", "is withdrawn", "no longer applies", "cutoff removed", "rule is withdrawn")


def scan(obj) -> list[str]:
    """A sentence recording that a rule was withdrawn is not the rule still being active."""
    text = json.dumps(obj)
    found = []
    for marker, why in CONFLICT_MARKERS:
        start = 0
        while (i := text.find(marker, start)) != -1:
            window = text[max(0, i - 160):i + 160]
            if not any(w in window for w in WITHDRAWN):
                found.append(why)
                break
            start = i + len(marker)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    a, b = json.loads(args.before.read_text()), json.loads(args.after.read_text())
    ai = {i["id"]: i for i in a["items"]}
    bi = {i["id"]: i for i in b["items"]}

    o: list[str] = []
    w = o.append
    w("# Semantic diff — M5 proposal packet\n")
    w("| | artifact | sha256 |")
    w("|---|---|---|")
    w(f"| before | `{args.before}` | `{digest(args.before)}` |")
    w(f"| after | `{args.after}` | `{digest(args.after)}` |")
    w("")
    w("These are the exact bytes compared. Values are compared, not whitespace; items are aligned by "
      "their stable `id`.\n")
    w("## Per item\n")
    w("| Item | status | fields | proposal.value | reviewer question | superseded object kept | stale "
      "content still active |")
    w("|---|---|---|---|---|---|---|")
    for key in sorted(set(ai) | set(bi)):
        x, y = ai.get(key, {}), bi.get(key, {})
        status = "unchanged" if x.get("status") == y.get("status") else f"{x.get('status')} → {y.get('status')}"
        nx, ny = len(x.get("field_values") or {}), len(y.get("field_values") or {})
        fields = "unchanged" if nx == ny else f"{nx} → {ny}"
        pv = "unchanged" if x.get("proposal", {}).get("value") == y.get("proposal", {}).get("value") else "regenerated"
        rq = "unchanged" if x.get("reviewer_question") == y.get("reviewer_question") else "**regenerated**"
        sup = "yes" if y.get("superseded_proposal") else "no"
        stale = scan(y.get("proposal")) + scan({"q": y.get("reviewer_question")})
        w(f"| {key} | {status} | {fields} | {pv} | {rq} | {sup} | "
          f"{'; '.join(stale) if stale else 'none found'} |")
    w("")
    w("## Field status movement\n")
    w("| Item | before | after |")
    w("|---|---|---|")
    for key in sorted(set(ai) | set(bi)):
        def summarise(item):
            fv = item.get("field_values") or {}
            if not fv:
                return "no field values"
            c: dict[str, int] = {}
            for v in fv.values():
                c[v.get("status")] = c.get(v.get("status"), 0) + 1
            return ", ".join(f"{v} {k}" for k, v in sorted(c.items()))
        w(f"| {key} | {summarise(ai.get(key, {}))} | {summarise(bi.get(key, {}))} |")
    w("")
    w("## Document level\n")
    for field in ("sources", "corrections", "producer", "baseline"):
        before_n = len(a.get(field, [])) if isinstance(a.get(field), list) else "object"
        after_n = len(b.get(field, [])) if isinstance(b.get(field), list) else "object"
        same = a.get(field) == b.get(field)
        w(f"- `{field}`: {'unchanged' if same else f'changed ({before_n} → {after_n})'}")
    w("")
    stale_total = sum(len(scan(y.get("proposal")) + scan({"q": y.get("reviewer_question")})) for y in bi.values())
    w(f"**Stale conflicting content still active in the after artifact: {stale_total}.** A non-zero count "
      "means two specifications are live at once, which is the defect this diff exists to catch.\n")
    text = "\n".join(o) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)
    return 1 if stale_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
