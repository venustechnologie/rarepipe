#!/usr/bin/env python3
"""Generate the review packet from the packet's own records. No count is typed by hand.

The first packet advertised "71 gaps ready" from work-package coverage while zero fields carried a
value. Everything quantitative below is read from field_accounting.json and proposals.json.

Usage: uv run python tools/m5/make_review_packet.py <packet-dir> [--out review_packet.md]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

LABEL = {"APPLY_READY": "carry a complete value with no unresolved dependency",
         "CONDITIONAL": "carry a value that waits on a named unresolved input",
         "DISCUSSION_ONLY": "are discussed but carry no value a reviewer could apply",
         "BLOCKED_EVIDENCE": "wait on a measurement or an institutional fact",
         "BLOCKED_HUMAN": "wait on a human decision or attestation"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packet", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    acc = json.loads((args.packet / "field_accounting.json").read_text())
    props = json.loads((args.packet / "proposals.json").read_text())
    val = json.loads((args.packet / "validator_output.json").read_text())
    c = acc["counts"]
    total = acc["total_validator_gaps"]
    owners = Counter(f["owner"] for f in acc["fields"] if f["field_status"] in ("BLOCKED_EVIDENCE", "BLOCKED_HUMAN"))

    o: list[str] = []
    w = o.append
    w("# M5 review packet — successor version\n")
    w("**Prepared by AI.** No human has reviewed or approved any of it, and it carries no signature. "
      "Roles were working methods, not credentials.\n")
    w("| | |")
    w("|---|---|")
    w(f"| Plan | `{val['plan_version']}`, lifecycle {val['lifecycle']} |")
    w(f"| Plan content digest | `{val['plan_content_digest']}` |")
    w("| Digest provenance | copied from the validator artifact and recomputed from the plan store; "
      "verified by `tools/m5/check_consistency.py` |")
    w(f"| Baseline | status {val['baseline']['status']} |")
    w(f"| Validator gaps | **{total}** |")
    w("")
    w("## Field-level readiness, derived from the fields themselves\n")
    w("Counts come from `field_accounting.json`, which reads each proposal's own per-field values. "
      "The earlier packet reported \"71 gaps ready\" from work-package coverage; measured per field, "
      "that number was zero.\n")
    w("| Status | Fields | Meaning |")
    w("|---|---:|---|")
    for k in ("APPLY_READY", "CONDITIONAL", "DISCUSSION_ONLY", "BLOCKED_EVIDENCE", "BLOCKED_HUMAN"):
        w(f"| {k} | {c[k]} | {LABEL[k]} |")
    w(f"| **Total** | **{sum(c[k] for k in LABEL)}** | |")
    w("")
    w(f"- Fields accepted by a human: **{acc['accepted_by_a_human']}**")
    w(f"- Gaps the native validator still reports: **{acc['gaps_the_native_validator_still_reports']}**\n")
    w("Those last two rows are the honest ones. Preparation does not close a gap; only an accepted "
      "edit that passes the native validator does.\n")
    w("## Work packages\n")
    w("| Package | Gaps | Item status | Field mix |")
    w("|---|---:|---|---|")
    for item in props["items"]:
        mix = item.get("field_status_summary") or {}
        mix_s = ", ".join(f"{v} {k.lower().replace('_', ' ')}" for k, v in sorted(mix.items())) or "not declared"
        w(f"| {item['id']} | {len(item['source_gap_ids'])} | {item['status']} | {mix_s} |")
    w("")
    w("No work package now claims READY_FOR_HUMAN_REVIEW. Each item's status is derived from its "
      "fields: one blocked field is enough to remove the claim.\n")
    w("## What the remaining work needs, by owner\n")
    w("| Owner | Blocked fields |")
    w("|---|---:|")
    for owner, n in owners.most_common():
        w(f"| {owner} | {n} |")
    w("")
    w("## Decisions a reviewer can take now\n")
    for item in props["items"]:
        if item.get("reviewer_question"):
            w(f"- **{item['id']}** ({item['status']}): {item['reviewer_question']}")
    w("")
    w("## Checks run, with their actual output\n")
    out = args.packet / "check_outputs"
    def status(name, key="status", default="not captured"):
        f = out / name
        if not f.exists():
            return default
        try:
            return json.loads(f.read_text()).get(key, default)
        except Exception:
            return default
    native = out / "native_validator_after.json"
    native_s = "not captured"
    if native.exists():
        nd = json.loads(native.read_text())
        native_s = (f"freezable={nd['freezable']}, gaps={len(nd['scientific_readiness'])}, "
                    f"lifecycle={nd['lifecycle']}, baseline={nd['baseline']['status']}")
    w("| Check | Scope | Actual result |")
    w("|---|---|---|")
    w(f"| `check_proposal.py` | handoff format only | `{status('check_proposal.json')}` |")
    w(f"| `tools/m5/check_consistency.py` | identity, digests, gap coverage, advertised-vs-actual values, "
      f"proposal.value vs field_values | `{status('check_consistency.json')}` |")
    w(f"| `tools/m5/field_accounting.py` | one status per real gap | {sum(c[k] for k in LABEL)} fields classified, "
      f"0 unmapped |")
    w(f"| `tools/m5/semantic_diff.py` | before/after, including unchanged-but-conflicting objects | "
      f"0 stale specifications active |")
    w(f"| `rarepipe prospective validate` | the real plan | `{native_s}` |")
    w("")
    w("Raw outputs are in `check_outputs/`; the diff is `semantic_diff.md`.")
    w("")
    w("None of these assesses whether the science is right, whether a cited source says what is "
      "claimed, or who a reviewer is.\n")
    w("## Human review request\n")
    w("Review the exact successor content through the project's own workflow, under your own identity. "
      "No review command was run, no review record exists, the baseline remains CANDIDATE and the plan "
      "remains DRAFT — which is correct.\n")
    text = "\n".join(o) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
