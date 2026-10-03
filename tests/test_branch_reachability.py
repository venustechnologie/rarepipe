"""A declared decision branch must be able to reach its inputs, or it is a hold in name only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "network"))

from check_branch_reachability import check  # noqa: E402


def test_exp01_can_now_fire_the_holds_it_could_not():
    """EXP01 measures cell_death as of rules 1.2.0, so its adverse and population holds work.

    Before: B08, B09, B10 and B16 all declared they applied to EXP01 and none could fire, so a
    result with every functional readout normal but viability and division falling read as a
    success that unlocked drug-mechanism planning.
    """
    report = check()
    assert [row for row in report["unreachable"] if row["experiment"] == "EXP01"] == []


def test_the_result_that_used_to_read_as_a_success_now_holds():
    """The exact vector from the original finding, end to end through the real engine."""
    from rarepipe.stages.prospective import fixtures as FX, rules, seed
    from rarepipe.stages.prospective.model import BaselineRef, Observation

    baseline = BaselineRef(package_path="probe", package_sha256="0" * 64, manifest_entries=0,
                           manifest_verified=False, stage_runs={}, semantic_digests={})
    plan = seed.seed_plan(baseline)
    by_id = {e.id: e for e in plan.endpoints}
    experiment = next(e for e in plan.experiments if e.id == "EXP01")
    required = [by_id[i] for i in experiment.endpoints if i in by_id]

    values = dict(FX.EXP01_ALL)
    values.update(viability="decreased", division_rate="decreased", cell_death="increased")
    observation = Observation.model_validate(FX.observation("EXP01", values))
    evaluation = rules.evaluate(observation, experiment.kind, required)

    assert "B09" in evaluation.matches
    assert "HOLD_PROGRESSION" in evaluation.actions
    assert "CREATE_SCIENTIFIC_REVIEW" in evaluation.actions
    assert evaluation.status == "DECISION_REVIEW_REQUIRED"


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
