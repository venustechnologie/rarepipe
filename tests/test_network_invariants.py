"""The cross-cutting invariant scan must actually fire.

A checker that has never failed is indistinguishable from one that cannot fail, so every rule is
exercised against a deliberate violation here before it is trusted against the real tree.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "tools/network/check_invariants.py"


def _scan(package: Path, tests: Path) -> tuple[int, dict]:
    import json
    proc = subprocess.run(
        [sys.executable, str(SCANNER), "--package", str(package), "--tests", str(tests)],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def _tree(tmp_path: Path, name: str, body: str) -> tuple[Path, Path]:
    package = tmp_path / "network"
    tests = tmp_path / "tests"
    package.mkdir(parents=True, exist_ok=True)
    tests.mkdir(parents=True, exist_ok=True)
    (package / name).write_text(body)
    return package, tests


def test_the_real_network_layer_holds_every_invariant():
    code, report = _scan(ROOT / "src/rarepipe/stages/network", ROOT / "tests")
    assert report["findings"] == [], report["findings"]
    assert code == 0
    assert report["files_scanned"]["source"] > 0, "scanned nothing, so proved nothing"


@pytest.mark.parametrize(("rule", "body"), [
    ("process_random_hash", "def seed(node):\n    return hash(node) % 1000\n"),
    ("literal_digest",
     'PLAN = "sha256:' + "0" * 64 + '"\n'),
    ("latent_reachable", "from somewhere import LatentScientificTruth\n"),
    ("snapshot_mutation", "def go(r):\n    return r.model_copy(update={'origin': 'public_evidence'})\n"),
])
def test_each_rule_fires_on_a_deliberate_violation(tmp_path: Path, rule: str, body: str):
    package, tests = _tree(tmp_path, "offender.py", body)
    code, report = _scan(package, tests)
    assert code == 1
    assert rule in {f["rule"] for f in report["findings"]}, report["findings"]


def test_piped_pytest_is_caught(tmp_path: Path):
    package, tests = _tree(tmp_path, "clean.py", "x = 1\n")
    # Built from parts: a literal pipe here would make this file its own offender.
    pipe = chr(124)
    (tests / "run.sh").write_text(f"uv run pytest -q {pipe} tail -3\n")
    code, report = _scan(package, tests)
    assert code == 1
    assert "piped_pytest" in {f["rule"] for f in report["findings"]}


def test_a_clean_tree_produces_no_findings(tmp_path: Path):
    package, tests = _tree(tmp_path, "clean.py", "import zlib\n\n\ndef seed(node: str) -> int:\n    return zlib.crc32(node.encode())\n")
    code, report = _scan(package, tests)
    assert code == 0
    assert report["findings"] == []
