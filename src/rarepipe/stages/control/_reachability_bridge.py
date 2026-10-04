"""Unreachable decision branches per experiment, from the existing deterministic check.

The compiler fails closed on an experiment whose declared branches cannot fire. The check already
exists as a tool; this loads it rather than reimplementing it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def unreachable_branches() -> dict[str, tuple[str, ...]]:
    path = Path(__file__).resolve().parents[4] / "tools" / "network" / "check_branch_reachability.py"
    spec = importlib.util.spec_from_file_location("_branch_reachability", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out: dict[str, list[str]] = {}
    for row in module.check()["unreachable"]:
        out.setdefault(row["experiment"], []).append(row["branch"])
    return {k: tuple(sorted(v)) for k, v in out.items()}
