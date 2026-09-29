#!/usr/bin/env python3
"""One auditable trace per replicate, and the test the successor review asked for.

Finding 4 claimed an engine coverage gap: with benefit unresolved and an adverse population change
present, no branch carries the population concern. The review objected that ground-truth harm in the
generator is not the same as an *established adverse observation* after noisy measurement — if the
adverse verdict is itself UNKNOWN, the problem is limited detection, not a rules-engine omission.

This settles it by conditioning on the observation vector rather than on the generator's truth:
select replicates where the adverse verdict IS established and the benefit verdict is UNKNOWN, then
report which branches actually fire. It also prints a full chain for one replicate:

    synthetic measurements -> estimate/interval -> observation verdicts -> branches -> actions

Usage: uv run python tools/m5/sim/trace.py [--reps 500] [--out trace.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from rarepipe.stages.prospective import rules  # noqa: E402
from rarepipe.stages.prospective.model import ExperimentKind  # noqa: E402
from sim import analysis, dgp, worlds  # noqa: E402
from sim.run import FUNCTION_KEYS, _seed, endpoints_for, observe  # noqa: E402


POP_DELTA = 0.05  # harness convenience only; see the note in one_replicate()


def one_replicate(world, rng, margin: float) -> dict:
    """Run a single selective-loss replicate and record every step."""
    data = dgp.simulate_selection(rng, world.design, world.truth)
    ref, test = data.arm == 0, data.arm == 1
    death_rate = [float(data.deaths[m].sum() / max(1, data.n_cohort[m].sum())) for m in (ref, test)]
    div_rate = [float(data.n_obs[m].sum() / max(1, (data.n_cohort[m] - data.deaths[m]).sum())) for m in (ref, test)]
    est = analysis.prep_summary(data.prep, data.arm, data.y_obs, data.n_obs, 0, 1)
    verdict = analysis.framing_benefit(est, margin, beneficial_sign=-1, require_margin=True)
    mis = verdict if verdict in ("improved", "worsened", "unchanged") else "UNKNOWN"
    # These two verdicts are categorised by a crude absolute-difference rule, stated here so the
    # classification can be audited rather than inferred. It is a simulation harness convenience, NOT a
    # proposed assay criterion: the real criteria are exactly the ones M5_W003 leaves unresolved, and no
    # uncertainty is attached to these differences.
    death_delta, div_delta = death_rate[1] - death_rate[0], div_rate[1] - div_rate[0]
    death_cat = "increased" if death_delta > POP_DELTA else "unchanged"
    div_cat = "decreased" if div_delta < -POP_DELTA else "unchanged"
    values = {k: "unchanged" for k in FUNCTION_KEYS}
    values["missegregation"] = mis
    values.update({"viability": "decreased" if death_cat == "increased" else "unchanged",
                   "cell_death": death_cat, "division_rate": div_cat,
                   "nad_intracellular": "unchanged", "bubr1_abundance": "unchanged"})
    obs = observe(ExperimentKind.DRUG_MECHANISM_FUNCTION, values,
                  {"identity_verified": True, "provenance_verified": True, "controls_valid": True,
                   "precision_adequate": True})
    ev = rules.evaluate(obs, ExperimentKind.DRUG_MECHANISM_FUNCTION,
                        endpoints_for(ExperimentKind.DRUG_MECHANISM_FUNCTION))
    return {
        "measurements": {
            "observed error rate, reference": round(float(data.y_obs[ref].sum() / max(1, data.n_obs[ref].sum())), 4),
            "observed error rate, test": round(float(data.y_obs[test].sum() / max(1, data.n_obs[test].sum())), 4),
            "death rate ref/test": [round(x, 4) for x in death_rate],
            "division rate ref/test": [round(x, 4) for x in div_rate],
            "observed divisions ref/test": [int(data.n_obs[ref].sum()), int(data.n_obs[test].sum())],
            "starting cohort ref/test": [int(data.n_cohort[ref].sum()), int(data.n_cohort[test].sum())],
        },
        "estimate": {"difference": round(float(est.est), 4), "ci": [round(float(est.lo), 4), round(float(est.hi), 4)],
                     "method": est.method, "margin_used": margin},
        "population_endpoint_classification": {
            "rule": (f"absolute difference in the pooled rate against the reference arm; |delta| > {POP_DELTA} "
                     "classifies, otherwise 'unchanged'. Harness convenience, not a proposed assay criterion, and "
                     "no uncertainty is attached to the difference."),
            "cell_death": {"reference": round(death_rate[0], 4), "test": round(death_rate[1], 4),
                           "delta": round(death_delta, 4), "threshold": POP_DELTA,
                           "classified": death_cat,
                           "why": (f"delta {death_delta:+.4f} "
                                   + ("exceeds" if death_delta > POP_DELTA else "does not exceed")
                                   + f" +{POP_DELTA}. The two rates differ, but this rule does not treat that "
                                     "difference as meaningful unless it clears the threshold, and it carries no "
                                     "interval, so 'unchanged' here means 'not classified by this rule', not "
                                     "'shown to be equal'.")},
            "division_rate": {"reference": round(div_rate[0], 4), "test": round(div_rate[1], 4),
                              "delta": round(div_delta, 4), "threshold": -POP_DELTA,
                              "classified": div_cat,
                              "why": (f"delta {div_delta:+.4f} "
                                      + ("is below" if div_delta < -POP_DELTA else "is not below")
                                      + f" -{POP_DELTA}.")},
        },
        "verdicts": {"missegregation": mis, "cell_death": death_cat, "division_rate": div_cat},
        "adverse_established": death_cat == "increased" or div_cat == "decreased",
        "benefit_unknown": mis == "UNKNOWN",
        "branches": sorted(ev.matches),
        "predicates": {k: v for k, v in ev.predicates.items()
                       if k in ("any_function_endpoint_improved", "death_division_or_viability_problematic",
                                "interpretable_functional_benefit", "adverse_direction")},
        "actions": ev.actions,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    world = next(w for w in worlds.worlds() if w.key == "selective_loss")
    rng = np.random.default_rng(_seed(args.seed, "selective_loss", "trace"))

    rows = [one_replicate(world, rng, worlds.MARGIN_RATE) for _ in range(args.reps)]
    cond = [r for r in rows if r["adverse_established"] and r["benefit_unknown"]]
    branch_counts = Counter(b for r in cond for b in r["branches"])
    any_hold = sum(1 for r in cond if {"B08", "B09"} & set(r["branches"]))
    # Which adverse signal was established matters: the engine's adverse predicate reads cell death
    # and worsened function, but not a fall in division rate.
    by_signal = {}
    for label, pick in (("death_increased", lambda r: r["verdicts"]["cell_death"] == "increased"),
                        ("division_decreased_only", lambda r: r["verdicts"]["division_rate"] == "decreased"
                         and r["verdicts"]["cell_death"] != "increased")):
        sub = [r for r in cond if pick(r)]
        by_signal[label] = {"replicates": len(sub),
                            "reaching_B08_or_B09": sum(1 for r in sub if {"B08", "B09"} & set(r["branches"])),
                            "branches": dict(Counter(b for r in sub for b in r["branches"]))}
    adverse_unknown = sum(1 for r in rows if not r["adverse_established"])

    verdict = (
        "CONFIRMED_COVERAGE_GAP" if cond and any_hold == 0 else
        "NOT_A_COVERAGE_GAP: a hold fires whenever the adverse verdict is established" if cond and any_hold == len(cond)
        else "PARTIAL" if cond else "UNTESTABLE_IN_THIS_WORLD: the adverse verdict was never established")

    report = {
        "world": world.key,
        "question": ("With the benefit verdict UNKNOWN and the adverse verdict ESTABLISHED, does any branch carry "
                     "the population concern?"),
        "replicates": len(rows),
        "replicates_with_adverse_verdict_unknown": adverse_unknown,
        "replicates_meeting_the_condition": len(cond),
        "of_those_reaching_B08_or_B09": any_hold,
        "branch_counts_under_the_condition": dict(branch_counts),
        "split_by_established_adverse_signal": by_signal,
        "verdict": verdict,
        "classification_caveat": (
            "The population verdicts come from an absolute-difference rule with no uncertainty attached. That is "
            "enough to show the routing consequence — an established 'decreased' reaches no hold — but it says "
            "nothing about how reliably a real assay would produce that verdict. Detection reliability is a separate "
            "question this trace does not answer."),
        "interpretation": (
            "The condition is defined on the observation vector, not on the generator's truth, which is the "
            "distinction the successor review drew. Where the adverse verdict is not established, any failure to "
            "hold is limited detection or measurement information, not a rules-engine omission."),
        "example_trace": rows[0],
        "example_trace_meeting_condition": cond[0] if cond else None,
    }
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}")
    print(json.dumps({k: report[k] for k in ("replicates", "replicates_with_adverse_verdict_unknown",
                                             "replicates_meeting_the_condition", "of_those_reaching_B08_or_B09",
                                             "branch_counts_under_the_condition", "verdict")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
