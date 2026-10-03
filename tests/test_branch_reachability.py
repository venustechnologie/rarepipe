"""A declared decision branch must be able to reach its inputs, or it is a hold in name only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "network"))

from check_branch_reachability import check  # noqa: E402


def test_exp01_cannot_fire_its_population_and_adverse_holds():
    """EXP01 omits cell_death, so four branches that declare they apply to it cannot fire.

    EXP01 is the experiment that gates PERMIT_DRUG_MECHANISM_PLANNING. A result with every
    functional endpoint normal but viability and division both falling reads there as a success,
    because B08, B09, B10 and B16 all require cell_death and the experiment does not measure it.

    This test pins the defect rather than the fix: it documents what is currently true so that
    adding cell_death to EXP01 — a plan change needing the scientific lead, not an engineer —
    fails it loudly and gets the test updated deliberately.
    """
    report = check()
    exp01 = {row["branch"]: row for row in report["unreachable"] if row["experiment"] == "EXP01"}

    assert set(exp01) == {"B08", "B09", "B10", "B16"}, sorted(exp01)
    for branch in exp01.values():
        assert branch["missing_endpoints"] == ["cell_death"]

    assert "HOLD_RESCUE_CONCLUSION" in exp01["B08"]["actions_that_cannot_fire"]
    assert "HOLD_PROGRESSION" in exp01["B09"]["actions_that_cannot_fire"]
    assert "RECORD_POPULATION_CHANGE" in exp01["B16"]["actions_that_cannot_fire"]


def test_exp03_cannot_test_the_mechanism_it_is_replicating():
    """EXP03 omits sirt2_activity and k668_acetylation, so the two branches that ask whether the
    mechanism explains a replicated signal cannot fire on the replication experiment."""
    report = check()
    exp03 = {row["branch"]: row for row in report["unreachable"] if row["experiment"] == "EXP03"}

    assert set(exp03) == {"B06", "B11"}, sorted(exp03)
    for branch in exp03.values():
        assert branch["missing_endpoints"] == ["k668_acetylation", "sirt2_activity"]


def test_exp02_can_reach_every_branch_that_declares_it():
    """EXP02 measures cell_death, so the same holds that are inert on EXP01 are live there."""
    report = check()
    assert [row for row in report["unreachable"] if row["experiment"] == "EXP02"] == []


def test_prose_and_context_requirements_are_not_counted_as_findings():
    """required_inputs carries prose placeholders and context.* fields; neither is an endpoint
    key, and reporting them as gaps would bury the real ones."""
    report = check()
    for row in report["unreachable"]:
        for missing in row["missing_endpoints"]:
            assert " " not in missing, missing
            assert not missing.startswith("context."), missing
    assert report["not_endpoint_keyed"], "nothing deferred — the classifier may have stopped working"
