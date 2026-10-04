#!/usr/bin/env python3
"""Compile the MVA capability gaps and write the gap report.

Also recompiles both physical realization targets, so a newly grounded capability shows up as a
change in the compiled architecture rather than as a line in a list of findings.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.stages.control.discovery import mva_gaps  # noqa: E402
from rarepipe.stages.control.discovery.compiler import compile_discovery  # noqa: E402
from rarepipe.stages.control.discovery.report import render  # noqa: E402

OUT = ROOT / "docs/control/MVA_CAPABILITY_GAPS.md"


def main() -> int:
    report = compile_discovery(mva_gaps.problem(), mva_gaps.targets())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(report))
    print(f"{OUT.relative_to(ROOT)}: {len(report.gaps)} gaps, "
          f"{len(report.grounded_capabilities)} grounded  digest {report.content_digest}")
    for gap in report.gaps:
        print(f"  {gap.gap_id}: {gap.result.value}")
    for delta in report.recompiles:
        print(f"  recompile {delta.target}: {delta.before} -> {delta.after} "
              f"({'changed' if delta.changed else 'unchanged'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
