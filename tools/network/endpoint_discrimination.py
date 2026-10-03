#!/usr/bin/env python3
"""Which measurements actually change the decision?

The question blocking this case is not what the cells will do — nobody answers that without the
experiment. It is which endpoints change what we do with the result. That is a property of the
decision rules, so it is exactly computable with no biology, no parameters, and no outcome data.

For each experiment: enumerate the reachable outcome vectors over its endpoints, run each through
the real rule engine, and report

  * how many distinct decisions the experiment can actually reach;
  * which endpoints are load-bearing — dropping one merges decisions that were distinct;
  * which are inert for this rule set, which is NOT the same as scientifically unnecessary;
  * the smallest endpoint subsets that preserve every distinction.

A minimal subset is a costing question for an assay scientist, never a recommendation to measure
less. An endpoint can be essential for interpretation, for QC, or for a branch that needs an input
this experiment does not carry, and still not move this decision.

Usage: uv run python tools/network/endpoint_discrimination.py [--experiment EXP01] [--json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rarepipe.stages.prospective import rules, seed  # noqa: E402
from rarepipe.stages.prospective.model import (  # noqa: E402
    Applicability, BaselineRef, EvaluationMode, ModelIdentity, Observation, ObservationValue,
    QualityChecks,
)

_PROBE_BASELINE = BaselineRef(
    package_path="discrimination-probe", package_sha256="0" * 64, manifest_entries=0,
    manifest_verified=False, stage_runs={}, semantic_digests={},
)

# The contrast each endpoint is read for, taken from the literals the rule engine tests. These are
# kind-dependent and getting it wrong silently produces nonsense: the allele-function branches test
# the four function readouts as normal/impaired, while the drug-mechanism and replication branches
# test the same keys as improved/worsened. Using one contrast for both made every function readout
# look inert on EXP02 and EXP03, which would have inverted the plan's own logic.
_SHARED: dict[str, tuple[str, ...]] = {
    "expression_comparability": ("matched", "not_matched"),
    "kinetochore_localization": ("present", "absent"),
    "pp2a_b56_recruitment": ("present", "absent"),
    "viability": ("unchanged", "decreased"),
    "division_rate": ("unchanged", "decreased"),
    "cell_death": ("unchanged", "increased"),
    "nad_intracellular": ("increased", "unchanged"),
    "sirt2_activity": ("increased", "unchanged"),
    "bubr1_abundance": ("increased", "unchanged"),
    "k668_acetylation": ("decreased", "unchanged"),
    "total_aneuploidy": ("decreased", "unchanged"),
}
_FUNCTION_KEYS = ("checkpoint_activation", "checkpoint_silencing",
                  "chromosome_alignment", "missegregation")
_FUNCTION_CONTRAST = {
    "ALLELE_FUNCTION": ("normal", "impaired"),
    "DRUG_MECHANISM_FUNCTION": ("improved", "worsened", "unchanged"),
    "REPLICATION_RELEVANCE": ("improved", "worsened", "unchanged"),
}


def contrasts_for(kind: str) -> dict[str, tuple[str, ...]]:
    """The value space to enumerate for one experiment kind."""
    out = dict(_SHARED)
    function = _FUNCTION_CONTRAST.get(kind)
    if function is None:
        raise KeyError(f"no function-readout contrast recorded for kind {kind!r}")
    for key in _FUNCTION_KEYS:
        out[key] = function
    return out


MAX_VECTORS = 1 << 16


def _decide(experiment, required, assignment) -> tuple[tuple[str, ...], str]:
    obs = Observation(
        observation_id="probe", experiment_id=experiment.id, execution_ref="probe",
        origin="SYNTHETIC", evaluation_mode=EvaluationMode.SYNTHETIC_DEMO,
        raw_result_sha256="0" * 64,
        values=[ObservationValue(endpoint_key=k, category=v) for k, v in assignment.items()],
        model_identity=ModelIdentity(applicability=Applicability.EXACT_ALLELE_ENGINEERED),
        qc=QualityChecks(identity_verified=True, provenance_verified=True,
                         precision_adequate=True, controls_valid=True),
    )
    ev = rules.evaluate(obs, experiment.kind, required)
    return tuple(sorted(ev.actions)), ev.status


def analyse(experiment, endpoints_by_id) -> dict:
    required = [endpoints_by_id[i] for i in experiment.endpoints if i in endpoints_by_id]
    space = contrasts_for(experiment.kind.value)
    keys = [e.key for e in required if e.key in space]
    unmodelled = [e.key for e in required if e.key not in space]

    total = 1
    for k in keys:
        total *= len(space[k])
    if total > MAX_VECTORS:
        return {"experiment": experiment.id, "skipped": f"{total} vectors exceeds cap"}

    decisions: dict[tuple, tuple] = {}
    for combo in itertools.product(*(space[k] for k in keys)):
        decisions[combo] = _decide(experiment, required, dict(zip(keys, combo)))

    def merges_without(subset: list[str]) -> bool:
        """Does restricting to `subset` make two previously distinct decisions collide?"""
        seen: dict[tuple, tuple] = {}
        for combo, decision in decisions.items():
            sig = tuple(combo[keys.index(k)] for k in subset)
            if sig in seen and seen[sig] != decision:
                return True
            seen[sig] = decision
        return False

    load_bearing = [k for k in keys if merges_without([x for x in keys if x != k])]
    inert = [k for k in keys if k not in load_bearing]

    # Smallest subsets preserving every distinction. load_bearing is necessary by construction;
    # confirm it is also sufficient, and otherwise grow it.
    minimal = None
    if not merges_without(load_bearing):
        minimal = sorted(load_bearing)
    else:
        for size in range(len(load_bearing), len(keys) + 1):
            for subset in itertools.combinations(keys, size):
                if set(load_bearing) <= set(subset) and not merges_without(list(subset)):
                    minimal = sorted(subset)
                    break
            if minimal:
                break

    distinct = sorted({d for d in decisions.values()})
    return {
        "experiment": experiment.id,
        "experiment_kind": experiment.kind.value,
        "endpoints_enumerated": keys,
        "function_readout_contrast": list(_FUNCTION_CONTRAST[experiment.kind.value]),
        "endpoints_without_a_modelled_contrast": unmodelled,
        "outcome_vectors": len(decisions),
        "distinct_decisions": len(distinct),
        "decisions": [{"status": s, "actions": list(a)} for a, s in distinct],
        "load_bearing_endpoints": sorted(load_bearing),
        "inert_for_this_rule_set": sorted(inert),
        "minimal_discriminating_set": minimal,
    }


def run(plan=None) -> dict:
    plan = plan or seed.seed_plan(_PROBE_BASELINE)
    by_id = {e.id: e for e in plan.endpoints}
    return {
        "rules_version": rules.RULES_VERSION,
        "experiments": [analyse(e, by_id) for e in plan.experiments],
        "reading": (
            "'inert_for_this_rule_set' means the rules reach the same decision whichever way the "
            "endpoint reads. It does not mean the measurement is unnecessary: it may be needed "
            "for interpretation, for QC, or by a branch whose other inputs this experiment does "
            "not carry — see check_branch_reachability.py."
        ),
        "not_checked": [
            "whether an endpoint is scientifically adequate or well measured",
            "whether the decision the rules reach is scientifically right",
            "anything about what the cells will actually do",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = run()
    if args.experiment:
        report["experiments"] = [e for e in report["experiments"]
                                 if e["experiment"] == args.experiment]
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"endpoint discrimination ({report['rules_version']})\n")
    for e in report["experiments"]:
        if "skipped" in e:
            print(f"{e['experiment']}: {e['skipped']}")
            continue
        print(f"{e['experiment']} ({e['experiment_kind']})")
        print(f"  {e['outcome_vectors']} outcome vectors -> "
              f"{e['distinct_decisions']} distinct decisions")
        print(f"  changes the decision : {', '.join(e['load_bearing_endpoints']) or 'none'}")
        print(f"  does not             : {', '.join(e['inert_for_this_rule_set']) or 'none'}")
        if e["minimal_discriminating_set"] is not None:
            print(f"  smallest set that keeps every distinction: "
                  f"{', '.join(e['minimal_discriminating_set'])}")
        if e["endpoints_without_a_modelled_contrast"]:
            print(f"  no modelled contrast : "
                  f"{', '.join(e['endpoints_without_a_modelled_contrast'])}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
