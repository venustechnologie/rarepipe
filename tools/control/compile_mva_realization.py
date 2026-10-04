#!/usr/bin/env python3
"""Compile the MVA case at the physical layer and write both realization maps.

Two targets are compiled because the contrast is the finding: the bypass the synthesis layer
reports as reaching the state target under every compatible model, and the one route the
repository actually holds a physical chain for.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.stages.control.realization import mva_realization  # noqa: E402
from rarepipe.stages.control.realization.compiler import compile_realization  # noqa: E402
from rarepipe.stages.control.realization.report import render  # noqa: E402

TARGETS = (("problem", "MVA_REALIZATION_BYPASS.md"),
           ("abundance_problem", "MVA_REALIZATION_ABUNDANCE.md"))


def main() -> int:
    out = ROOT / "docs/control"
    out.mkdir(parents=True, exist_ok=True)
    for builder, filename in TARGETS:
        report = compile_realization(getattr(mva_realization, builder)())
        (out / filename).write_text(render(report))
        print(f"docs/control/{filename}: {report.result.value}  digest {report.content_digest}")
        print(f"  {len(report.functions)} required transformations, "
              f"{len(report.missing_capabilities)} missing capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
