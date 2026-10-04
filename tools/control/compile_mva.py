#!/usr/bin/env python3
"""Compile the MVA case and write its control map. Regenerate rather than edit the output.

Usage: uv run python tools/control/compile_mva.py [--out docs/control/MVA_CONTROL_MAP.md] [--json PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rarepipe.stages.control.compiler import compile_problem  # noqa: E402
from rarepipe.stages.control.mva import problem  # noqa: E402
from rarepipe.stages.control.render import render  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "docs/control/MVA_CONTROL_MAP.md")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    report = compile_problem(problem())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report))
    if args.json:
        args.json.write_text(report.model_dump_json(indent=2))
    print(f"{report.result.value} — wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
