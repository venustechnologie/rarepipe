"""T13: end-to-end operator runbook and verification at a known revision.

The acceptance map indexes IDs to the tests that NAME them; it does not measure whether a
criterion is exercised. These assertions are written to that weaker, true claim.

Asserts that:
- Every engineering acceptance ID (A01-A24, A26-A30) is named by at least one real test.
- Every cited test node id exists in the repository test suite.
- A25 is absent from the indexed set and present as an external milestone.
- RUNBOOK.md records the verification at a known revision matching HEAD.
- T14's external status is honestly stated with next authorized action.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rarepipe.stages.network.cli import (
    PRD_ACCEPTANCE_DESCRIPTIONS,
    app,
    collect_acceptance_map,
    render_acceptance_table_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_PATH = ROOT / "docs" / "network" / "RUNBOOK.md"


def test_acceptance_map_completeness_and_coverage():
    """Assert all 29 engineering IDs are covered and A25 is strictly an external milestone."""
    mapping = collect_acceptance_map(ROOT)
    assert len(mapping) == 30, f"Expected 30 acceptance IDs, got {len(mapping)}"

    covered_ids = [aid for aid, entry in mapping.items() if entry["status"] == "NAMED_BY_TEST"]
    uncovered_ids = [aid for aid, entry in mapping.items() if entry["status"] == "UNNAMED_BY_TEST"]
    external_ids = [aid for aid, entry in mapping.items() if entry["status"] == "EXTERNAL_MILESTONE"]

    # All engineering acceptance IDs (A01-A24, A26-A30) must be NAMED_BY_TEST
    expected_engineering_ids = [f"A{i:02d}" for i in range(1, 25)] + [f"A{i:02d}" for i in range(26, 31)]
    assert sorted(covered_ids) == expected_engineering_ids
    assert uncovered_ids == [], f"Found uncovered engineering IDs: {uncovered_ids}"

    # A25 must be absent from covered set and present as external milestone
    assert "A25" not in covered_ids
    assert external_ids == ["A25"]
    assert mapping["A25"]["test_nodes"] == []


def test_every_cited_test_node_id_exists():
    """Assert every test node ID in the acceptance map resolves to a real function in tests/."""
    mapping = collect_acceptance_map(ROOT)
    all_cited_nodes = []
    for aid, entry in mapping.items():
        all_cited_nodes.extend(entry["test_nodes"])

    assert len(all_cited_nodes) >= 29, "Expected at least 29 test references across engineering criteria"

    for node_id in all_cited_nodes:
        file_part, func_name = node_id.split("::", 1)
        test_file = ROOT / file_part
        assert test_file.is_file(), f"Cited test file does not exist: {test_file} (node {node_id})"

        # Parse AST to confirm the function exists
        tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=str(test_file))
        func_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert func_name in func_names, (
            f"Function {func_name} cited in node {node_id} not found in {file_part}"
        )


def test_runbook_file_exists_and_pinned_baseline_documented():
    """Assert RUNBOOK.md exists and accurately records the pinned baseline and controlled drive."""
    assert RUNBOOK_PATH.is_file(), f"Runbook missing at {RUNBOOK_PATH}"
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert len(text) > 1000, "Runbook is suspiciously short"

    # Baseline invariants from T01
    assert "PP_MVA_001_RH_001@0002-455419f1" in text
    assert "stage10-rules-1.1.0" in text
    assert "112" in text  # scientific readiness gaps
    assert "/Volumes/Lexar/rarepipe_work/MVA_001/prospective" in text
    assert "test -d /Volumes/Lexar/rarepipe_work/MVA_001/prospective" in text


def test_runbook_records_a_real_revision_that_this_repository_contains():
    """PRD 20: verification provenance must identify the code that actually produced it.

    This asserted equality with the current HEAD, which cannot hold past the next commit — it
    passed only while nothing had been committed since the runbook was written, and would have
    failed permanently from the following commit onward. The revision a verification ran at is a
    historical fact. What must be true is that it is a real commit in this repository and an
    ancestor of HEAD, so the runbook cannot cite a fabricated or foreign revision.
    """
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    shas = set(re.findall(r"\b[0-9a-f]{40}\b", text))
    assert shas, "RUNBOOK.md records no full git revision"

    for sha in shas:
        exists = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                                cwd=str(ROOT), capture_output=True)
        assert exists.returncode == 0, f"RUNBOOK.md cites {sha}, which is not a commit here"
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                                  cwd=str(ROOT), capture_output=True)
        assert ancestor.returncode == 0, (
            f"RUNBOOK.md cites {sha}, which is not an ancestor of HEAD: its recorded results do "
            "not describe this line of history"
        )


def test_runbook_says_how_to_tell_whether_its_results_are_stale():
    """A reader must be able to tell whether the recorded run still describes the code."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "cli verify runbook-revision" in text


def test_the_runbook_revision_check_reports_staleness_without_failing_the_suite():
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "runbook-revision", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["recorded_revisions"]
    assert payload["head"]
    assert payload["status"] in {"CURRENT", "STALE"}
    if payload["status"] == "STALE":
        assert payload["commits_since"] >= 1


def test_runbook_contains_all_operator_sections():
    """Assert RUNBOOK.md contains all required sections from clean checkout to handoff."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    required_topics = [
        "Installation & Prerequisites",
        "Configuration",
        "Seed Capability Registry",
        "Run Campaign in Synthetic Mode",
        "Compose and Inspect Requests",
        "Run Network Evaluation",
        "Generate Report and Export",
        "Pause and Cancel with Handoff",
        "Verification at Known Revision",
        "Acceptance Map",
        "External Milestone",
    ]
    for topic in required_topics:
        assert topic.lower() in text.lower(), f"Missing topic in RUNBOOK.md: {topic}"

    # Confirm no .env reading or writing
    assert "never read or write .env" in text.lower() or "never read or write `.env`" in text.lower()


def test_verification_section_faithfulness():
    """Assert verification results match actual non-integration test suite findings."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # Command and exit status
    assert 'uv run pytest -q -m "not integration"' in text
    assert "exit status: 0" in text.lower() or "exit status 0" in text.lower()

    # Skipped tests explanations
    assert "test_baseline_solver.py" in text
    assert "Exomiser" in text or "RAREPIPE_EXOMISER_HOME" in text
    assert "test_track1.py" in text
    assert "official evaluation.py" in text or "RAREPIPE_TRACK1_SCORER" in text

    # Integration marker explanation
    assert "not integration" in text
    assert "0" in text  # zero integration tests excluded


def test_external_milestone_t14_is_honest():
    """Assert T14/A25 status is stated truthfully without synthetic substitution."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    # State T14's real status
    assert "no verified recipient route" in text.lower()
    assert "no appointed clinical lead" in text.lower()
    assert "no authentic institutional reply" in text.lower()
    assert "nothing sent" in text.lower()

    # Next authorized action named
    assert "next authorized action" in text.lower()


def test_verify_cli_command_group():
    """Assert verify CLI command group runs and generates acceptance map and environment report."""
    runner = CliRunner()

    result_env = runner.invoke(app, ["verify", "environment"])
    assert result_env.exit_code == 0
    assert "baseline_plan_id" in result_env.stdout
    assert "PP_MVA_001_RH_001@0002-455419f1" in result_env.stdout

    result_map = runner.invoke(app, ["verify", "acceptance-map", "--json"])
    assert result_map.exit_code == 0
    parsed = json.loads(result_map.stdout)
    assert len(parsed) == 30
    assert parsed["A01"]["status"] == "NAMED_BY_TEST"
    assert parsed["A25"]["status"] == "EXTERNAL_MILESTONE"


def test_the_acceptance_map_states_what_it_measures():
    """The map's own wording must not overstate it.

    It was first rendered with the status `COVERED`, which reads as evidence that a criterion is
    exercised. It is built from test names and docstrings, so a test that names A08 and asserts
    nothing would carry the same status. Six of six delegated tasks had a real defect while their
    own tests passed, so a coverage word that means "a test mentions this" is exactly the kind of
    claim that misleads a reviewer here.
    """
    table = render_acceptance_table_markdown(collect_acceptance_map(ROOT))
    assert "COVERED" not in table
    assert "index built from test names and docstrings" in table
    assert "not evidence that the criterion is exercised" in table

    runbook = (ROOT / "docs/network/RUNBOOK.md").read_text()
    assert "It does **not** measure whether" in runbook
    assert "read the cited tests" in runbook


def test_an_empty_test_naming_an_id_would_still_be_indexed(tmp_path: Path):
    """Demonstrate the limitation the wording warns about, so it cannot be quietly forgotten."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_hollow.py").write_text(
        "def test_a08_asserts_absolutely_nothing():\n"
        '    """A08: this docstring names the ID and the body does nothing."""\n'
        "    pass\n"
    )
    mapping = collect_acceptance_map(tmp_path)
    assert mapping["A08"]["status"] == "NAMED_BY_TEST"
    assert mapping["A08"]["test_nodes"] == ["tests/test_hollow.py::test_a08_asserts_absolutely_nothing"]
    # Every other engineering ID is correctly reported as a definite gap.
    assert mapping["A01"]["status"] == "NOT_NAMED_BY_ANY_TEST"
    assert mapping["A25"]["status"] == "EXTERNAL_MILESTONE"
