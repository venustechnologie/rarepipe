"""The control skills must reference only what the compiler defines, and carry nothing forbidden."""
from __future__ import annotations

import re

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "control"))

from check_skills import REQUIRED, check  # noqa: E402

ROLES = ("control-state-modeler", "control-causal-dynamics", "control-strategy-generator",
         "control-falsification", "control-observability-design", "control-actuator-mapper",
         "control-provenance-auditor")


def test_all_seven_skills_exist_and_are_consistent():
    present = sorted(p.parent.name for p in (ROOT / ".claude/skills").glob("control-*/SKILL.md"))
    assert present == sorted(ROLES)
    report = check()
    assert report["findings"] == [], report["findings"]


def _skill(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "control-probe" / "SKILL.md"
    path.parent.mkdir()
    sections = "\n".join(f"## {name}\ncontent" for name in REQUIRED)
    path.write_text(f"---\nname: control-probe\ndescription: probe\n---\n{sections}\n{body}\n")
    return path


def test_an_invented_reference_is_caught(tmp_path: Path):
    report = check([_skill(tmp_path, "Use `ControlOracle.solve` to finish.")])
    assert any("ControlOracle.solve" in f["issue"] for f in report["findings"])


def test_a_dose_or_a_recommendation_is_caught(tmp_path: Path):
    report = check([_skill(tmp_path, "We recommend 500 mg daily.")])
    issues = " ".join(f["issue"] for f in report["findings"])
    assert "dose" in issues and "recommendation" in issues


def test_variant_notation_is_caught(tmp_path: Path):
    report = check([_skill(tmp_path, "Consider the c.1234G>T allele.")])
    assert any("variant notation" in f["issue"] for f in report["findings"])


def test_a_missing_section_is_caught(tmp_path: Path):
    path = tmp_path / "control-probe" / "SKILL.md"
    path.parent.mkdir()
    path.write_text("---\nname: control-probe\ndescription: probe\n---\n## scope\ncontent\n")
    report = check([path])
    assert any("missing section benchmark_cases" in f["issue"] for f in report["findings"])


def test_every_test_the_requirements_map_cites_exists():
    """The traceability map must not outlive the tests it points at."""
    import re

    text = (ROOT / "docs/control/REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 25
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_the_synthesis_requirements_map_cites_tests_that_exist():
    """The traceability map is only worth having if it cannot rot."""
    text = (ROOT / "docs/control/SYNTHESIS_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 40
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_every_synthesis_proof_gate_and_invariant_is_cited():
    """A gate or invariant the map does not mention is one nobody is tracking."""
    text = (ROOT / "docs/control/SYNTHESIS_REQUIREMENTS.md").read_text()
    for path in ("tests/test_synthesis_gates.py", "tests/test_synthesis_invariants.py"):
        source = (ROOT / path).read_text()
        defined = set(re.findall(r"^def (test_\w+)\(", source, re.M))
        cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
        missing = sorted(defined - cited)
        assert not missing, f"{path} defines tests the requirements map never cites: {missing}"


def test_the_realization_requirements_map_cites_tests_that_exist():
    text = (ROOT / "docs/control/REALIZATION_REQUIREMENTS.md").read_text()
    cited = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", text)
    assert len(cited) >= 25
    for path, name in cited:
        source = (ROOT / path).read_text()
        assert f"def {name}(" in source, f"{path}::{name} is cited but does not exist"


def test_every_realization_gate_is_cited():
    text = (ROOT / "docs/control/REALIZATION_REQUIREMENTS.md").read_text()
    path = "tests/test_realization_gates.py"
    defined = set(re.findall(r"^def (test_\w+)\(", (ROOT / path).read_text(), re.M))
    cited = set(re.findall(rf"`{re.escape(path)}::(\w+)`", text))
    missing = sorted(defined - cited)
    assert not missing, f"{path} defines tests the requirements map never cites: {missing}"
