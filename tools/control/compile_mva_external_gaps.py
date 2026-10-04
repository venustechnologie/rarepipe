#!/usr/bin/env python3
"""Compile the capability gaps against the frozen external corpus, and write both reports.

Reads the snapshot written by `retrieve_capability_evidence.py`. Never touches the network, so the
same snapshot gives the same verdicts and CI needs no connectivity.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.stages.control.discovery import mva_gaps  # noqa: E402
from rarepipe.stages.control.discovery.compiler import compile_discovery  # noqa: E402
from rarepipe.stages.control.discovery.external.trace import render as render_trace  # noqa: E402
from rarepipe.stages.control.discovery.report import render as render_gaps  # noqa: E402

GAPS_OUT = ROOT / "docs/control/MVA_CAPABILITY_GAPS_EXTERNAL.md"
TRACE_OUT = ROOT / "docs/control/MVA_CAPABILITY_DISCOVERY_TRACE.md"


def main() -> int:
    report = compile_discovery(mva_gaps.problem(), mva_gaps.targets())
    GAPS_OUT.parent.mkdir(parents=True, exist_ok=True)
    GAPS_OUT.write_text(render_gaps(report))
    TRACE_OUT.write_text(render_trace(report))
    print(f"{GAPS_OUT.relative_to(ROOT)} and {TRACE_OUT.relative_to(ROOT)}")
    print(f"  digest {report.content_digest}")
    for gap in report.gaps:
        print(f"  {gap.gap_id}: {gap.result.value}")
    for delta in report.gap_deltas:
        print(f"    {delta.note}")
    for item in report.citation_audit:
        if item.verdict.value != "SUPPORTS_ATTRIBUTION":
            print(f"  citation audit: {item.ref} {item.verdict.value}")
    for delta in report.recompiles:
        print(f"  recompile {delta.target}: {delta.before} -> {delta.after} "
              f"({'changed' if delta.changed else 'unchanged'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
