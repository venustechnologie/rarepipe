#!/usr/bin/env python3
"""Can every decision branch that declares it applies to an experiment actually fire on it?

A branch declares `applies_to` an experiment kind and `required_inputs` it needs to reach a
verdict. If the experiment's endpoint set cannot supply those inputs, the branch is present,
claims to apply, and is unreachable — a safety hold that looks enforced and is inert.

This found a real one: EXP01 omits `cell_death`, so B08 (hold the rescue conclusion), B09
(adverse hold), B10 and B16 (record a population change) cannot fire on the first experiment —
the one that gates PERMIT_DRUG_MECHANISM_PLANNING. A result with every function normal but
viability and division both falling reads as a success there.

Two kinds of entry in `required_inputs` are not endpoint keys and are reported separately rather
than counted as findings: prose placeholders ("required readouts", "all of the above") and
`context.*` fields supplied outside the endpoint set.

Usage: uv run python tools/network/check_branch_reachability.py [--json]
Exit code 0 only if no branch is unreachable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rarepipe.stages.prospective import rules, seed  # noqa: E402
from rarepipe.stages.prospective.model import BaselineRef, ProspectivePlan  # noqa: E402

_PROBE_BASELINE = BaselineRef(
    package_path="reachability-probe", package_sha256="0" * 64, manifest_entries=0,
    manifest_verified=False, stage_runs={}, semantic_digests={},
)


def _classify(requirement: str) -> str:
    """Endpoint key, a context field, or prose that names no key at all."""
    if requirement.startswith("qc."):
        return "qc"
    if requirement.startswith("context."):
        return "context"
    if " " in requirement:
        return "prose"
    return "endpoint"


def check(plan: ProspectivePlan | None = None) -> dict:
    plan = plan or seed.seed_plan(_PROBE_BASELINE)
    by_id = {e.id: e for e in plan.endpoints}
    unreachable, not_endpoint_keyed = [], []

    for experiment in plan.experiments:
        measured = {by_id[i].key for i in experiment.endpoints if i in by_id}
        for descriptor in rules.descriptors():
            if experiment.kind not in descriptor.applies_to:
                continue
            missing, deferred = [], []
            for requirement in descriptor.required_inputs:
                kind = _classify(requirement)
                if kind == "endpoint":
                    if requirement not in measured:
                        missing.append(requirement)
                elif kind in {"context", "prose"}:
                    deferred.append({"requirement": requirement, "kind": kind})
            if missing:
                unreachable.append({
                    "experiment": experiment.id,
                    "experiment_kind": experiment.kind.value,
                    "branch": descriptor.branch,
                    "missing_endpoints": sorted(missing),
                    "actions_that_cannot_fire": list(descriptor.actions),
                    "rationale": descriptor.rationale,
                })
            if deferred:
                not_endpoint_keyed.append({
                    "experiment": experiment.id, "branch": descriptor.branch,
                    "entries": deferred,
                })

    return {
        "status": "ALL_DECLARED_BRANCHES_REACHABLE" if not unreachable else "UNREACHABLE_BRANCHES",
        "rules_version": rules.RULES_VERSION,
        "experiments_checked": [e.id for e in plan.experiments],
        "unreachable": unreachable,
        "not_endpoint_keyed": not_endpoint_keyed,
        "checked": "every branch declaring applies_to an experiment's kind has its endpoint-keyed "
                   "required_inputs present in that experiment's endpoint set",
        "not_checked": [
            "whether an endpoint is scientifically adequate",
            "whether a reachable branch is scientifically correct",
            "context.* inputs, which are supplied outside the endpoint set",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = check()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report["status"], f"({report['rules_version']})")
        for row in report["unreachable"]:
            print(f"\n  {row['experiment']} / {row['branch']} — does not measure "
                  f"{', '.join(row['missing_endpoints'])}")
            print(f"    cannot fire: {', '.join(row['actions_that_cannot_fire'])}")
            print(f"    branch means: {row['rationale'][:96]}")
        if not report["unreachable"]:
            print("  every declared branch can reach its inputs")
    return 1 if report["unreachable"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
