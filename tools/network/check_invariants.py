#!/usr/bin/env python3
"""Cross-cutting invariant scan for the research-network layer.

Each task's own tests check that task. Nothing checks the seams between tasks, and every defect
this file looks for is one that actually occurred in this project or was found in a delegated
deliverable — a fabricated digest that reached a reviewer, seeds derived from Python's
process-randomised ``hash()``, a failing pytest hidden behind a pipe, latent world truth reachable
from a module a policy can see.

A task's author writes both the code and its tests, so the tests cannot be the only evidence that
the invariant holds. This scan is deliberately static and independent of them: it reads source,
not behaviour, and it runs over whatever exists, so it works while the layer is still being built.

Usage: uv run python tools/network/check_invariants.py [--package DIR] [--tests DIR]
Exit code 0 only if nothing was found.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIGEST_LITERAL = re.compile(r"""["']sha256:[0-9a-f]{64}["']""")
PIPED_PYTEST = re.compile(r"pytest[^\n|]*\|\s*(tail|head|grep)")

# Latent world truth may be named only where it is defined and where the scorer consumes it.
# Anything else — a view, a policy, a composer, an exporter — must not be able to reach it.
LATENT_NAMES = ("LatentScientificTruth", "latent_for_scorer", "scorer_only_bundle")
LATENT_ALLOWED = {"sim/world.py", "sim/reward.py", "sim/scenarios.py", "sim/institution.py"}


class Finding(dict):
    def __init__(self, rule: str, where: str, detail: str):
        super().__init__(rule=rule, where=where, detail=detail)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _sources(*dirs: Path):
    for d in dirs:
        if d.exists():
            yield from sorted(p for p in d.rglob("*.py") if "__pycache__" not in p.parts)


def check_no_process_random_hash(paths) -> list[Finding]:
    """`hash()` is randomised per process, so a 'fixed seed' built on it is not fixed.

    Two simulation runs once disagreed (23.2% vs 21.8%) for exactly this reason while both
    claimed a fixed seed.
    """
    out = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as exc:
            out.append(Finding("unparseable", _rel(path), f"{type(exc).__name__}: {exc}"))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "hash":
                out.append(Finding("process_random_hash", f"{_rel(path)}:{node.lineno}",
                                   "builtin hash() is randomised per process; use zlib.crc32 or hashlib"))
    return out


def check_no_literal_digests(paths) -> list[Finding]:
    """A digest written by hand is a claim about content that nothing verified.

    One was written as a plausible continuation of a real version prefix and reached a reviewer.
    Digests are generated from the thing they cover, or they are not digests.
    """
    out = []
    for path in paths:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if DIGEST_LITERAL.search(line) and "sha256:" in line:
                if "example" in line.lower() or "not a real digest" in line.lower():
                    continue
                out.append(Finding("literal_digest", f"{_rel(path)}:{lineno}",
                                   "a sha256 literal in source is a hand-written digest; generate it"))
    return out


def check_latent_containment(package: Path) -> list[Finding]:
    """Hidden world truth must be unreachable from anything a policy or an operator view sees."""
    out = []
    for path in _sources(package):
        rel = str(path.relative_to(package))
        if rel in LATENT_ALLOWED:
            continue
        text = path.read_text()
        for name in LATENT_NAMES:
            for lineno, line in enumerate(text.splitlines(), 1):
                if name in line and not line.lstrip().startswith("#"):
                    out.append(Finding("latent_reachable", f"{_rel(path)}:{lineno}",
                                       f"{name} is named outside {sorted(LATENT_ALLOWED)}; "
                                       "hidden truth must not be reachable here"))
    return out


def check_no_piped_pytest(dirs) -> list[Finding]:
    """`pytest | tail` reports the pipe's exit status, not pytest's.

    That hid a genuine failure here on 2026-09-29 and a broken commit shipped.
    """
    out = []
    for d in dirs:
        if not d.exists():
            continue
        for path in sorted(d.rglob("*")):
            if not path.is_file() or path.suffix not in {".sh", ".py", ".md", ".yml", ".yaml"}:
                continue
            if path.name == Path(__file__).name:
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if PIPED_PYTEST.search(line) and "exit status" not in line.lower():
                    out.append(Finding("piped_pytest", f"{_rel(path)}:{lineno}",
                                       "exit status is the pipe's, not pytest's"))
    return out


def check_snapshot_mutation(paths) -> list[Finding]:
    """`model_copy(update=...)` bypasses the validators that enforce origin and lineage."""
    out = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "model_copy"
                    and any(kw.arg == "update" for kw in node.keywords)):
                out.append(Finding("snapshot_mutation", f"{_rel(path)}:{node.lineno}",
                                   "model_copy(update=) skips validators; build a validated successor"))
    return out


CHECKS = {
    "process_random_hash": "no seed derives from Python's process-randomised hash()",
    "literal_digest": "no sha256 digest is written by hand",
    "latent_reachable": "hidden world truth is named only where it is defined or scored",
    "piped_pytest": "no pytest invocation reports a pipe's exit status",
    "snapshot_mutation": "no immutable record is edited through model_copy(update=)",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, default=ROOT / "src/rarepipe/stages/network")
    ap.add_argument("--tests", type=Path, default=ROOT / "tests")
    args = ap.parse_args()

    src = list(_sources(args.package))
    tests = [p for p in _sources(args.tests) if "network" in p.name]
    findings: list[Finding] = []
    findings += check_no_process_random_hash(src + tests)
    findings += check_no_literal_digests(src + tests)
    findings += check_latent_containment(args.package)
    findings += check_no_piped_pytest([args.package, args.tests, ROOT / "tools/network",
                                       ROOT / "docs/network", ROOT / ".github"])
    findings += check_snapshot_mutation(src)

    print(json.dumps({
        "status": "NETWORK_INVARIANTS_HOLD" if not findings else "NETWORK_INVARIANTS_VIOLATED",
        "files_scanned": {"source": len(src), "tests": len(tests)},
        "checked": CHECKS,
        "not_checked": [
            "whether the science is right",
            "whether a delegated module's behaviour matches its own tests",
            "anything requiring the code to run — this scan is static by design",
        ],
        "findings": findings,
    }, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
