"""Which endpoints change the decision — and which are measured but cannot."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "network"))

from endpoint_discrimination import contrasts_for, run  # noqa: E402


def _by_id(report):
    return {e["experiment"]: e for e in report["experiments"]}


def test_the_function_contrast_is_kind_dependent():
    """Allele-function branches read the function keys as normal/impaired; drug-mechanism and
    replication branches read the same keys as improved/worsened.

    Using one contrast for every kind made all four function readouts look inert on EXP02 and
    EXP03, which would have inverted the plan's own reasoning. Keep this asymmetry pinned.
    """
    allele = contrasts_for("ALLELE_FUNCTION")
    drug = contrasts_for("DRUG_MECHANISM_FUNCTION")
    assert allele["checkpoint_activation"] == ("normal", "impaired")
    assert "improved" in drug["checkpoint_activation"]
    assert "worsened" in drug["checkpoint_activation"]
    assert allele["viability"] == drug["viability"]


def test_exp01_reaches_only_three_decisions_and_two_endpoints_cannot_move_them():
    """EXP01's nine endpoints collapse to three reachable decisions.

    viability and division_rate are measured and cannot change the outcome, which is the other
    face of the reachability finding: the branches that would read them (B08, B09, B10, B16) need
    cell_death, and EXP01 does not measure it. See check_branch_reachability.py.
    """
    exp01 = _by_id(run())["EXP01"]
    # Was 3 before cell_death joined EXP01's readouts; the adverse and population holds are now
    # reachable, which doubles the decisions the experiment can reach.
    assert exp01["distinct_decisions"] == 6
    assert "cell_death" in exp01["load_bearing_endpoints"]
    # viability and division_rate still cannot move an allele-function decision on their own.
    assert "viability" in exp01["inert_for_this_rule_set"]
    assert "division_rate" in exp01["inert_for_this_rule_set"]


def test_total_aneuploidy_now_changes_the_decision_and_its_ambiguity_is_handled():
    """The disease's defining phenotype is measured by EXP02 and read by no rule.

    Aneuploidy is what mosaic variegated aneuploidy *is*. It sits in EXP02's endpoint list and no
    branch tests it, so however it reads, the decision is unchanged. That is a finding for the
    scientific lead — either a branch should read it, or the plan should say why measuring it
    informs something other than this decision.
    """
    rules_source = (ROOT / "src/rarepipe/stages/prospective/rules.py").read_text()
    assert "total_aneuploidy" in rules_source

    exp02 = _by_id(run())["EXP02"]
    assert "total_aneuploidy" in exp02["load_bearing_endpoints"]
    assert "total_aneuploidy" not in exp02["inert_for_this_rule_set"]


def test_a_minimal_set_is_never_smaller_than_the_load_bearing_set():
    """A minimal discriminating set must contain every endpoint that changes the decision."""
    for exp in run()["experiments"]:
        if exp.get("minimal_discriminating_set") is None:
            continue
        assert set(exp["load_bearing_endpoints"]) <= set(exp["minimal_discriminating_set"])


def test_the_report_says_what_inert_does_not_mean():
    """'Inert for this rule set' must never be readable as 'do not measure this'."""
    report = run()
    assert "does not mean the measurement is unnecessary" in report["reading"]
    assert any("what the cells will actually do" in n for n in report["not_checked"])
