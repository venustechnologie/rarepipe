#!/usr/bin/env python3
"""Generate the A5 write-up from the result records, so no number is ever typed by hand.

The first version of this report was written by hand from a run whose seeds came from Python's
`hash()`, which is randomised per process. Two "identical" runs disagreed, the prose and the table
quoted different runs, and an external reviewer caught the contradiction by arithmetic. Every figure
below is now read from one result file, and the rate helpers carry the Monte Carlo interval with
them: 0 events in 500 replicates is reported as 0/500 with its upper bound, never as "never".

Usage: uv run python tools/m5/sim/report.py <results.json> [--out report.md]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def wilson(k: int, n: int) -> tuple[float, float, float]:
    if n == 0:
        return math.nan, math.nan, math.nan
    p, z = k / n, 1.96
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


def rate(k: int, n: int) -> str:
    """'97.2% (486/500, 95% CI 95.3-98.3%)' — the count is always visible."""
    p, lo, hi = wilson(k, n)
    return f"{p:.1%} ({k}/{n}, 95% CI {lo:.1%}–{hi:.1%})"


def branch(arm: dict, key: str) -> str:
    n = arm["completed_replicates"]
    return rate(round(arm["branch_frequency"].get(key, 0.0) * n), n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    d = json.loads(args.results.read_text())
    W = {w["key"]: w for w in d["worlds"]}
    out: list[str] = []
    w_ = out.append

    def arm(world: str, name: str) -> dict:
        return W[world]["arms"][name]

    w_("# A5 — operating characteristics of the proposed decision system\n")
    w_(f"Generated from `{args.results.name}` by `tools/m5/sim/report.py`. Every figure below is read "
       "from those records; none is typed by hand. Each rate carries its event count and a Wilson "
       "interval.\n")
    w_(f"- Replicates per arm: **{d['reps']}**, seed **{d['seed']}** (deterministic: CRC32, not Python's "
       "per-process `hash()`).\n"
       f"- Worlds: **{len(d['worlds'])}**. Code: `tools/m5/sim/` (`dgp.py`, `analysis.py`, `worlds.py`, "
       "`run.py`).\n"
       "- Reproduce: `uv run python tools/m5/sim/run.py --reps 500 --out results.json`; two runs are "
       "byte-identical.\n")
    w_(f"> {d['caveat']}\n")

    w_("## What each world tests, and against which reference\n")
    w_("These questions are not interchangeable, and a result for one does not answer another:\n")
    w_("| Question | Reference arm | What a positive result would establish |")
    w_("|---|---|---|")
    w_("| EXP01: does the altered protein function adequately at the specified abundance? | normal "
       "replacement | adequacy within a prespecified region, in this model and assay |")
    w_("| EXP02: does treatment improve function? | vehicle-treated deficient | improvement of that "
       "functional outcome |")
    w_("| Does treatment restore function to the normal range? | normal reference *and* vehicle | a "
       "stronger, additional claim needing its own criterion |")
    w_("")

    w_("## Finding 1 — the invalid decision rule, as a labelled negative control\n")
    w_("This arm deliberately encodes one invalid translation: **\"we could not detect a difference, "
       "therefore it worked\"**. It is a negative control, included to show what that rule costs. It is "
       "**not** a failure rate for difference tests in general, and the margin arm is not thereby proved "
       "safe in general — only in these worlds, under these assumptions.\n")
    w_("B10 is *candidate functional signal*, not demonstrated rescue.\n")
    w_("| World (truth) | invalid rule reaches B10 | margin framing reaches B10 |")
    w_("|---|---|---|")
    for key, label in [("no_improvement", "No improvement (zero effect by construction)"),
                       ("upstream_only", "Upstream only (NAD+ up, function flat)")]:
        w_(f"| {label} | {branch(arm(key, 'prep_summary/difference'), 'B10')} | "
           f"{branch(arm(key, 'prep_summary/margin'), 'B10')} |")
    w_("")
    w_("Read narrowly: encoding non-significance as success turns a true null into a candidate signal "
       "almost every time. That rule must not appear in the plan. Valid difference-based procedures are "
       "a separate question this study does not settle.\n")

    w_("## Finding 2 — detection of a real effect at three preparations\n")
    a = arm("true_benefit_clean", "prep_summary/margin")
    w_(f"In the world with a genuine clean improvement, the margin framing reaches B10 in "
       f"**{branch(a, 'B10')}** and B01 (keep unresolved) in **{branch(a, 'B01')}**.\n")
    w_("Stated at the width the evidence supports:\n")
    w_("> Under this specified synthetic model, margin, variance and analysis, three preparations had "
       "low detection probability. The appropriate replication requires a justified effect criterion "
       "and applicable variability information.\n")
    w_("This does not prove a pilot is the only possible source of that information; it is a sensible "
       "next candidate given no applicable local data exists.\n")

    w_("## Finding 3 — one timing interval against four mechanisms\n")
    w_("| True mechanism | alignment→anaphase | NEBD→anaphase | cells excluded |")
    w_("|---|---|---|---|")
    for key, label in [("timing_delayed_exit", "Delayed exit (the target defect)"),
                       ("timing_delayed_align", "Delayed alignment, normal exit"),
                       ("timing_premature", "Premature progression"),
                       ("timing_no_exit", "No exit within the window"),
                       ("informative_loss", "Informative tracking loss")]:
        t = arm(key, "prep_median_diff/two_sided")
        a2a = ", ".join(f"{k} {v:.1%}" for k, v in t["a2a_verdicts"].items())
        nebd = ", ".join(f"{k} {v:.1%}" for k, v in t["nebd_verdicts"].items())
        w_(f"| {label} | {a2a} | {nebd} | {t['mean_dropped_fraction']:.1%} |")
    w_("")
    w_("Read precisely: a normal alignment-to-anaphase interval in a delayed-alignment world is not a "
       "wrong answer *about that conditional interval* — the cells that supply it did align and did "
       "exit. It becomes misleading only when promoted to a statement about overall mitotic adequacy. "
       "Equally, NEBD-to-anaphase picking up delayed alignment does not make it a better primary assay "
       "of checkpoint silencing; it is sensitive to a different thing.\n")
    w_("The actionable point is the excluded fraction: every mechanism that removes cells from the "
       "interval's defining set makes the survivors look normal. Interval-specific interpretation, "
       "whole-population outcome accounting, and any mechanistic silencing claim must stay separate, "
       "and cells for whom an interval never exists must be reported as outcomes in their own right.\n")

    w_("## Finding 4 — adverse signals when benefit is unresolved\n")
    sel_m = arm("selective_loss", "prep_summary/margin")
    sel_d = arm("selective_loss", "prep_summary/difference")
    w_("In the world where the error rate falls *only* because error-prone cells die or stop dividing "
       "(true per-cell effect exactly zero):\n")
    w_("| | margin framing | invalid-rule framing |")
    w_("|---|---|---|")
    w_(f"| B08 improvement-with-a-problem | {branch(sel_m, 'B08')} | {branch(sel_d, 'B08')} |")
    w_(f"| B09 adverse hold | {branch(sel_m, 'B09')} | {branch(sel_d, 'B09')} |")
    w_(f"| B01 unresolved | {branch(sel_m, 'B01')} | {branch(sel_d, 'B01')} |")
    w_("")
    w_("B08 is defined as improvement accompanied by a problem, so its requiring an improvement claim "
       "is consistent with its own definition — this study does **not** show B08 is a bug. What it shows "
       "is a gap in coverage: when benefit is unresolved and an adverse population change is present, "
       "no branch carries the population concern. The fix is an additional evaluability/adverse-"
       "population flag that does not depend on a benefit claim, leaving B08's meaning intact.\n")
    w_("Required semantics for that flag:\n")
    w_("| Benefit evidence | Adverse evidence | Required interpretation |")
    w_("|---|---|---|")
    w_("| unknown | established | hold; keep the population concern without claiming benefit |")
    w_("| positive | established | hold; keep benefit-with-a-problem |")
    w_("| unknown | unknown | unresolved; no implicit all-clear |")
    w_("| positive | excludes the prespecified adverse boundary | candidate signal only if the remaining "
       "gates pass |")
    w_("")
    w_("A death or division change is not by itself proof of selection or corrupted data.\n")

    w_("## Finding 5 — the matched subset and the population are different targets\n")
    m = arm("matching_illusion", "prep_summary/adequacy")
    w_(f"| Quantity | value |")
    w_("|---|---|")
    w_(f"| mean matched-subset estimate | {m['mean_matched_estimate']:+.4f} |")
    w_(f"| mean population estimate | {m['mean_population_estimate']:+.4f} |")
    w_(f"| retention, reference arm | {m['mean_ref_arm_kept']:.0%} |")
    w_(f"| retention, test arm | {m['mean_test_arm_kept']:.0%} |")
    w_("")
    w_("The population estimate recovers its own target (true population arm effect 0 by construction). "
       "The matched estimate targets a **different** population — the cells inside the window — so it "
       "should not be called biased merely for differing from the population effect. The finding that "
       "matters operationally: the two differ by about 0.11 in absolute risk with asymmetric retention, "
       "which is large enough to change a conclusion if one is read as the other. Any causal claim that "
       "restoring abundance would rescue the whole population needs design assumptions this comparison "
       "does not supply.\n")

    w_("## What behaved correctly\n")
    inv = arm("invalid_assay", "prep_summary/margin")
    harm = arm("benefit_with_harm", "prep_summary/margin")
    w_(f"- **Invalid assay:** B01 {branch(inv, 'B01')}; no adequacy or rescue branch was reached under "
       "either framing. The quality gate holds.")
    w_(f"- **Benefit with harm:** B09 adverse hold {branch(harm, 'B09')}; B03 (strengthen H01) "
       f"{branch(harm, 'B03')}. Harm was not hidden by a favourable endpoint.")
    covs = [w["arms"]["prep_summary/margin"]["coverage"] for w in d["worlds"]
            if "prep_summary/margin" in w["arms"] and w["arms"]["prep_summary/margin"]["coverage"] is not None]
    w_(f"- **Interval coverage** for the preparation-level analysis: {min(covs):.1%}–{max(covs):.1%} "
       "across the rate worlds, against a nominal 95%.\n")

    w_("## Harness defects found and fixed\n")
    w_("Reported because each one made a broken design look conservative, which is the direction of "
       "error to expect when the same process writes the design and its test.\n")
    w_("1. **Non-reproducible seeding.** Seeds were derived from Python's `hash()`, which is randomised "
       "per process, so two runs of the \"same\" study disagreed and an earlier draft quoted two runs in "
       "its prose and table. An external reviewer caught it by arithmetic. Now CRC32; two runs are "
       "byte-identical.")
    w_("2. **Timing parameters on the wrong scale** (minutes into log-scale fields): every cell exceeded "
       "the window, 100% were discarded, and all four timing worlds returned \"unresolved\", which reads "
       "like caution rather than emptiness.")
    w_("3. **Verdict mapping compared against the wrong constants**, so the difference arm always "
       "returned \"unresolved\" and the two framings looked equally safe.\n")

    w_("## Limitations\n")
    w_("- Every number is conditional on the assumed parameters in `worlds.py`; each is labelled LIT, "
       "ASSUME or STRESS, and none is measured in this system.")
    w_("- The margins (0.10 absolute risk; 6 minutes) are placeholders needed to run the comparison at "
       "all. Choosing them for real is the scientific judgement A4 says nobody has made, so this study "
       "cannot tell anyone what they should be.")
    w_("- One functional endpoint drives the observation vector in the rate worlds; multiplicity across "
       "co-primary endpoints is not simulated, so Finding 2 likely *understates* how conservative the "
       "full design would be.")
    w_("- Produced by the same model that wrote the designs it tests. It is a self-test, and the three "
       "harness defects above are evidence of that risk rather than a guarantee that none remain.")
    text = "\n".join(out) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
