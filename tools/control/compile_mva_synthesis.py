#!/usr/bin/env python3
"""Compile the MVA case as a synthesis problem and write the architecture map.

The map is generated, never edited by hand: a test fails if the committed file does not match what
the compiler currently produces, so the document cannot drift away from the code that justifies it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.stages.control.synthesis import mva_synthesis  # noqa: E402
from rarepipe.stages.control.synthesis.compiler import compile_synthesis  # noqa: E402
from rarepipe.stages.control.synthesis.report import render  # noqa: E402

OUT = ROOT / "docs/control/MVA_ARCHITECTURE_MAP.md"


def main() -> int:
    report = compile_synthesis(mva_synthesis.problem())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(report))
    print(f"{OUT.relative_to(ROOT)}: {report.result.value}  digest {report.content_digest}")
    print(f"  {len(report.architectures)} architectures, "
          f"{len(report.families)} families, "
          f"{len(report.experiment_discriminators)} discriminators")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
