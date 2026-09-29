"""Run every synthetic world through the candidate analyses AND the real Stage 10 decision engine.

The point is not to compare statistical procedures in the abstract. It is to ask whether the whole
system — measurement, analysis, framing, and the branch rules in
`rarepipe.stages.prospective.rules` — reaches the right conclusion when we already know the truth.
A world with harm must not reach a rescue conclusion; an invalid assay must not reach adequacy.

Usage:
    uv run python tools/m5/sim/run.py [--reps 400] [--out PATH]

Every number printed is conditional on the assumptions in `worlds.py`. None is a measurement, an MVA
parameter, or any probability about a patient.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from rarepipe.stages.prospective import rules  # noqa: E402
from rarepipe.stages.prospective.model import (  # noqa: E402
    EndpointSpec,
    EvaluationMode,
    ExperimentKind,
    ModelIdentity,
    Observation,
    ObservationValue,
    QualityChecks,
)
from sim import analysis, dgp, worlds  # noqa: E402

FUNCTION_KEYS = ("checkpoint_activation", "checkpoint_silencing", "chromosome_alignment", "missegregation")


def _seed(base: int, *parts: str) -> int:
    """Deterministic across processes. `hash()` is randomized per process by PYTHONHASHSEED, so using
    it here silently reseeded every run — two runs of the "same" study did not agree."""
    return base + zlib.crc32("|".join(parts).encode()) % 1_000_000


def endpoints_for(kind: ExperimentKind) -> list[EndpointSpec]:
    keys = {
        ExperimentKind.ALLELE_FUNCTION: [("expression_comparability", True), ("checkpoint_activation", True),
                                         ("checkpoint_silencing", True), ("chromosome_alignment", True),
                                         ("missegregation", True), ("viability", True), ("division_rate", True)],
        ExperimentKind.DRUG_MECHANISM_FUNCTION: [("nad_intracellular", True), ("bubr1_abundance", True),
                                                 ("checkpoint_activation", True), ("checkpoint_silencing", True),
                                                 ("chromosome_alignment", True), ("missegregation", True),
                                                 ("viability", True), ("cell_death", True), ("division_rate", True)],
    }[kind]
    return [EndpointSpec(id=f"E_{k}", key=k, biological_meaning=k, desired="reference range", required=req)
            for k, req in keys]


def observe(kind: ExperimentKind, values: dict[str, str], qc: dict, context: dict | None = None) -> Observation:
    return Observation(
        observation_id="SIM", experiment_id="EXP01" if kind is ExperimentKind.ALLELE_FUNCTION else "EXP02",
        execution_ref="simulation", origin="SYNTHETIC", evaluation_mode=EvaluationMode.SYNTHETIC_DEMO,
        raw_result_sha256="simulated",
        values=[ObservationValue(endpoint_key=k, category=v, derivation="simulated") for k, v in values.items()],
        qc=QualityChecks(**qc), model_identity=ModelIdentity(applicability="GENERIC_BUB1B_DEFICIENT"),
        context=context or {})


def _wilson(k: int, n: int) -> tuple[float, float, float]:
    """Point estimate and a Monte Carlo interval for a simulated rate."""
    if n == 0:
        return math.nan, math.nan, math.nan
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


def run_rate_world(world, rng, reps: int, margin: float, procedure: str, framing: str) -> dict:
    """Rate-endpoint worlds: one functional endpoint drives the vector, the rest are held normal."""
    calls, branch_hits, unresolved = [], [], 0
    covered = 0
    truth_marginal = (dgp.marginal_rate(world.truth, "test") - dgp.marginal_rate(world.truth, "ref")) \
        if world.kind == "rate" else math.nan
    for _ in range(reps):
        if world.kind == "rate":
            data = dgp.simulate_rate(rng, world.design, world.truth)
            y, n, prep, arm = data.y, data.n, data.prep, data.arm
            death_cat, div_cat, via_cat = "unchanged", "unchanged", "unchanged"
        else:  # selection
            data = dgp.simulate_selection(rng, world.design, world.truth)
            y, n, prep, arm = data.y_obs, data.n_obs, data.prep, data.arm
            ref, test = arm == 0, arm == 1
            death_rate = [float(data.deaths[m].sum() / max(1, data.n_cohort[m].sum())) for m in (ref, test)]
            div_rate = [float(data.n_obs[m].sum() / max(1, (data.n_cohort[m] - data.deaths[m]).sum()))
                        for m in (ref, test)]
            death_cat = "increased" if death_rate[1] > death_rate[0] + 0.05 else "unchanged"
            div_cat = "decreased" if div_rate[1] < div_rate[0] - 0.05 else "unchanged"
            via_cat = "decreased" if death_cat == "increased" else "unchanged"
        est = (analysis.prep_summary if procedure == "prep_summary" else analysis.glmm)(prep, arm, y, n, 0, 1)
        if world.kind == "rate" and np.isfinite(est.lo) and np.isfinite(est.hi):
            covered += int(est.lo <= truth_marginal <= est.hi)
        verdict = (analysis.framing_benefit(est, margin, beneficial_sign=-1,
                                            require_margin=(framing == "margin"))
                   if framing != "difference" else
                   {analysis.ADEQUATE: "improved", analysis.INADEQUATE: "worsened",
                    analysis.UNRESOLVED: analysis.UNRESOLVED}.get(
                       analysis.framing_difference(est, adverse_sign=1), analysis.UNRESOLVED))
        mis = {"improved": "improved", "worsened": "worsened", "unchanged": "unchanged"}.get(verdict, "UNKNOWN")
        if mis == "UNKNOWN":
            unresolved += 1
        values = {k: "unchanged" for k in FUNCTION_KEYS}
        values["missegregation"] = mis
        values.update({"viability": via_cat, "cell_death": death_cat, "division_rate": div_cat,
                       "nad_intracellular": "increased" if world.key == "upstream_only" else "unchanged",
                       "bubr1_abundance": "increased" if world.key == "upstream_only" else "unchanged"})
        qc = {"identity_verified": True, "provenance_verified": True,
              "controls_valid": world.key != "invalid_assay",
              "precision_adequate": world.key != "invalid_assay"}
        ev = rules.evaluate(observe(ExperimentKind.DRUG_MECHANISM_FUNCTION, values, qc),
                            ExperimentKind.DRUG_MECHANISM_FUNCTION,
                            endpoints_for(ExperimentKind.DRUG_MECHANISM_FUNCTION))
        branch_hits.append(set(ev.matches))
        calls.append(verdict)
    wrong = sum(1 for b in branch_hits if b & set(world.wrong_if))
    right = sum(1 for b in branch_hits if b & set(world.right_if)) if world.right_if else 0
    freq: dict[str, int] = {}
    for b in branch_hits:
        for br in b:
            freq[br] = freq.get(br, 0) + 1
    p, lo, hi = _wilson(wrong, reps)
    return {"procedure": procedure, "framing": framing, "reps": reps,
            "completed_replicates": len(branch_hits),
            "wrong_count": wrong, "right_count": right,
            "branch_frequency": {k: round(v / reps, 3) for k, v in sorted(freq.items())},
            "wrong_branch_rate": round(p, 4), "wrong_ci": [round(lo, 4), round(hi, 4)],
            "right_branch_rate": round(right / reps, 4),
            "unresolved_rate": round(unresolved / reps, 4),
            "coverage": round(covered / reps, 4) if world.kind == "rate" else None,
            "true_marginal_difference": None if math.isnan(truth_marginal) else round(truth_marginal, 4),
            "verdicts": {v: round(calls.count(v) / reps, 3) for v in sorted(set(calls))}}


def run_timing_world(world, rng, reps: int, margin: float) -> dict:
    """Timing worlds: the question is whether one interval can carry four different mechanisms."""
    out = {"a2a_verdicts": [], "nebd_verdicts": [], "dropped_fraction": [], "branches": []}
    for _ in range(reps):
        data = dgp.simulate_timing(rng, world.design, world.truth)
        est_a2a = analysis.prep_median_diff(data.prep, data.arm, data.a2a, 0, 1)
        est_nebd = analysis.prep_median_diff(data.prep, data.arm, data.nebd2a, 0, 1)
        scored = data.counts["scored"].sum()
        dropped = sum(data.counts[k].sum() for k in ("premature", "never_align", "no_exit", "tracking_loss"))
        out["dropped_fraction"].append(dropped / max(1, scored + dropped))
        v_a2a = analysis.framing_adequacy(est_a2a, margin, adverse_sign=1, two_sided_region=True)
        v_nebd = analysis.framing_adequacy(est_nebd, margin, adverse_sign=1, two_sided_region=True)
        out["a2a_verdicts"].append(v_a2a)
        out["nebd_verdicts"].append(v_nebd)
        sil = {analysis.ADEQUATE: "normal", analysis.INADEQUATE: "impaired"}.get(v_a2a, "UNKNOWN")
        values = {k: "normal" for k in FUNCTION_KEYS}
        values["checkpoint_silencing"] = sil
        values.update({"expression_comparability": "matched", "viability": "unchanged",
                       "division_rate": "unchanged"})
        ev = rules.evaluate(observe(ExperimentKind.ALLELE_FUNCTION, values,
                                    {"identity_verified": True, "provenance_verified": True,
                                     "controls_valid": True, "precision_adequate": True}),
                            ExperimentKind.ALLELE_FUNCTION, endpoints_for(ExperimentKind.ALLELE_FUNCTION))
        out["branches"].append(set(ev.matches))
    wrong = sum(1 for b in out["branches"] if b & set(world.wrong_if))
    p, lo, hi = _wilson(wrong, reps)
    return {"procedure": "prep_median_diff", "framing": "two_sided_region", "reps": reps,
            "wrong_branch_rate": round(p, 4), "wrong_ci": [round(lo, 4), round(hi, 4)],
            "a2a_verdicts": {v: round(out["a2a_verdicts"].count(v) / reps, 3)
                             for v in sorted(set(out["a2a_verdicts"]))},
            "nebd_verdicts": {v: round(out["nebd_verdicts"].count(v) / reps, 3)
                              for v in sorted(set(out["nebd_verdicts"]))},
            "mean_dropped_fraction": round(float(np.mean(out["dropped_fraction"])), 4)}


def run_matching_world(world, rng, reps: int, margin: float) -> dict:
    """Does a matched window make a conditional comparison look like a population result?"""
    rows = []
    for _ in range(reps):
        data = dgp.simulate_matching(rng, world.design, world.truth)
        est_matched = analysis.prep_summary(data.prep, data.arm, data.matched_y, data.matched_n, 0, 1)
        est_all = analysis.prep_summary(data.prep, data.arm, data.full_y, data.full_n, 0, 1)
        rows.append({
            "matched": analysis.framing_adequacy(est_matched, margin, adverse_sign=1),
            "population": analysis.framing_adequacy(est_all, margin, adverse_sign=1),
            "test_arm_kept": float(data.matched_fraction[data.arm == 1].mean()),
            "ref_arm_kept": float(data.matched_fraction[data.arm == 0].mean()),
            "matched_est": est_matched.est, "population_est": est_all.est})
    disagree = sum(1 for r in rows if r["matched"] == analysis.ADEQUATE and r["population"] != analysis.ADEQUATE)
    p, lo, hi = _wilson(disagree, reps)
    return {"procedure": "prep_summary", "framing": "adequacy", "reps": reps,
            "matched_adequate_while_population_not": round(p, 4), "ci": [round(lo, 4), round(hi, 4)],
            "mean_test_arm_kept": round(float(np.mean([r["test_arm_kept"] for r in rows])), 4),
            "mean_ref_arm_kept": round(float(np.mean([r["ref_arm_kept"] for r in rows])), 4),
            "mean_matched_estimate": round(float(np.nanmean([r["matched_est"] for r in rows])), 4),
            "mean_population_estimate": round(float(np.nanmean([r["population_est"] for r in rows])), 4)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    import platform
    import subprocess
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parents[3]).stdout.strip() or "unknown"
    except Exception:
        rev = "unknown"
    results = {"generated_by": "tools/m5/sim/run.py", "reps": args.reps, "seed": args.seed,
               "code_revision": rev, "python": platform.python_version(), "numpy": np.__version__,
               "seed_derivation": "base seed + zlib.crc32('world|procedure|framing') % 1_000_000",
               "margin_rate": worlds.MARGIN_RATE, "margin_minutes": worlds.MARGIN_MIN,
               "caveat": ("Every value is conditional on the assumptions in worlds.py. None is a measurement, an "
                          "MVA parameter, or a probability about any patient. Margins are placeholders supplied "
                          "only so the framings can be compared: choosing them is the scientific judgement A4 "
                          "says nobody has made."),
               "worlds": []}
    for world in worlds.worlds():
        rng = np.random.default_rng(_seed(args.seed, world.key))
        entry = {"key": world.key, "title": world.title, "trap": world.trap, "kind": world.kind,
                 "wrong_if": list(world.wrong_if), "right_if": list(world.right_if), "notes": world.notes,
                 "params": world.params, "arms": {}}
        if world.kind in ("rate", "selection"):
            for procedure in ("prep_summary", "glmm"):
                for framing in ("margin", "difference"):
                    entry["arms"][f"{procedure}/{framing}"] = run_rate_world(
                        world, np.random.default_rng(_seed(args.seed, world.key, procedure, framing)),
                        args.reps, worlds.MARGIN_RATE, procedure, framing)
        elif world.kind == "timing":
            entry["arms"]["prep_median_diff/two_sided"] = run_timing_world(world, rng, args.reps, worlds.MARGIN_MIN)
        elif world.kind == "matching":
            entry["arms"]["prep_summary/adequacy"] = run_matching_world(world, rng, args.reps, worlds.MARGIN_RATE)
        results["worlds"].append(entry)
        print(f"{world.key:28} {world.kind:10} done", file=sys.stderr)

    # A stable identifier can still collide; check rather than assume.
    streams: dict[int, list[str]] = {}
    for world in worlds.worlds():
        for procedure in ("prep_summary", "glmm"):
            for framing in ("margin", "difference"):
                streams.setdefault(_seed(args.seed, world.key, procedure, framing), []).append(
                    f"{world.key}|{procedure}|{framing}")
        streams.setdefault(_seed(args.seed, world.key), []).append(world.key)
    collisions = {k: v for k, v in streams.items() if len(v) > 1}
    results["stream_collisions"] = ("none: " + f"{len(streams)} distinct streams"
                                    if not collisions else f"COLLISIONS: {collisions}")
    text = json.dumps(results, indent=2)
    results["results_digest"] = {
        "sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
        "covers": ("the full 64-character SHA256 of this results document serialised as json.dumps(indent=2) with "
                   "every field except results_digest and reproducibility_note present"),
    }
    text = json.dumps(results, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
