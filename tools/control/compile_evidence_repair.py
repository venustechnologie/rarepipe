#!/usr/bin/env python3
"""Recompile every layer from the repaired evidence and write both delta reports.

Reads nothing cached: each layer's observable comes out of a fresh compilation, and the comparison
is against the baseline recorded in the repair ledger.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.stages.control.evidence_repair.mva_repair import ledger  # noqa: E402
from rarepipe.stages.control.evidence_repair.recompile import deltas  # noqa: E402
from rarepipe.stages.control.evidence_repair.report import (  # noqa: E402
    render_evidence_delta, render_recompile_delta,
)

EVIDENCE_OUT = ROOT / "docs/control/MVA_EVIDENCE_REPAIR_DELTA.md"
RECOMPILE_OUT = ROOT / "docs/control/MVA_FULL_RECOMPILE_DELTA.md"


def main() -> int:
    book = ledger()
    computed = deltas(book)
    EVIDENCE_OUT.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUT.write_text(render_evidence_delta(book, computed))
    RECOMPILE_OUT.write_text(render_recompile_delta(book, computed))
    moved = sum(1 for d in computed if d.changed)
    print(f"{EVIDENCE_OUT.relative_to(ROOT)} and {RECOMPILE_OUT.relative_to(ROOT)}")
    print(f"  {len(book.repairs)} repairs; {moved} of {len(computed)} layers moved")
    for delta in computed:
        print(f"  {delta.position:2d}. {delta.layer:28s} "
              f"{'CHANGED' if delta.changed else 'UNCHANGED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
