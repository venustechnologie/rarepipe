"""The synthetic worlds from the second review's table, and what each one is a trap for.

Every parameter is labelled by where it comes from. None is an MVA measurement, and none of this is a
statement about the child: these worlds exist to ask whether the proposed decision system gets the
right answer when the truth is known, which is the one thing a real experiment can never tell us.

Provenance labels:
  LIT     taken from a retrieved source's reported design (counts, arms), not its biology
  STRESS  deliberately chosen to make a design fail, so the failure is visible
  ASSUME  a plausible working value with no measurement behind it
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import dgp

# Design sizes. The three-preparation floor is the packet's own proposal, traced to the retrieved
# studies reporting "average of 3 experiments"; the cell counts follow "at least 100 cells".
DESIGN_3 = dgp.RateDesign(arms=("ref", "test"), n_prep=3, n_vessel=2, n_cells=110,
                          allocation="block")                                               # LIT
DESIGN_3_SPLIT = dgp.RateDesign(arms=("ref", "test"), n_prep=3, n_vessel=2, n_cells=110,
                                allocation="unit")                                          # STRESS
DESIGN_3_PARTIAL = dgp.RateDesign(arms=("ref", "test"), n_prep=3, n_vessel=2, n_cells=110,
                                  allocation="partial_block", shared_preps=1)               # STRESS

# Between-preparation SD on the logit scale. No pilot exists, so these are the stress range the
# packet's M5_W003 says must be estimated before any criterion can be set.
SIGMA_LOW, SIGMA_MID, SIGMA_HIGH = 0.15, 0.45, 0.90                                         # STRESS

# A meaningful-effect margin has to be supplied to compare framings at all. It is NOT a proposal:
# A4's whole point is that this number is a scientific judgement nobody has made yet.
MARGIN_RATE = 0.10                                                                          # ASSUME
MARGIN_MIN = 6.0                                                                            # ASSUME


@dataclass(frozen=True)
class World:
    key: str
    title: str
    trap: str
    kind: str                     # rate | selection | timing | matching
    truth: object
    design: dgp.RateDesign
    wrong_if: tuple[str, ...]     # branch ids that would be the wrong answer here
    right_if: tuple[str, ...] = ()
    notes: str = ""
    params: dict = field(default_factory=dict)


def rate_truth(base: float, arm_shift: float, sigma_prep: float, sigma_vessel: float = 0.12):
    return dgp.RateTruth(base_logit=dgp.logit(base), arm_logit={"ref": 0.0, "test": arm_shift},
                         sigma_prep=sigma_prep, sigma_vessel=sigma_vessel)


def selection_truth(arm_shift: float, death_slope: float, divide_test: float, death_test: float = 0.05):
    return dgp.SelectionTruth(
        base_logit=dgp.logit(0.30), arm_logit={"ref": 0.0, "test": arm_shift}, sigma_prep=SIGMA_MID,
        sigma_vessel=0.12, sigma_cell=0.8,
        death_base={"ref": 0.05, "test": death_test}, death_slope={"ref": 0.0, "test": death_slope},
        divide_base={"ref": 0.85, "test": divide_test})


def worlds() -> list[World]:
    out: list[World] = []

    # 1. No functional improvement. The trap is a design that reads "not significant" as adequate,
    #    or noise as rescue.
    out.append(World(
        "no_improvement", "No functional improvement",
        "false rescue, or 'no significant difference' reported as adequacy",
        "rate", rate_truth(0.30, 0.0, SIGMA_MID), DESIGN_3,
        wrong_if=("B10", "B03"), right_if=("B01", "B07", "B15"),
        params={"base_rate": "0.30 ASSUME", "arm_shift": "0.0 (exactly no effect)",
                "sigma_prep": f"{SIGMA_MID} STRESS"}))

    # 2. Partial improvement that stays below the normal reference. The trap is throwing it away.
    out.append(World(
        "partial_improvement", "Partial improvement, still below the normal reference",
        "a real partial signal discarded as complete failure, or promoted to full rescue",
        "rate", rate_truth(0.30, -0.55, SIGMA_MID), DESIGN_3,
        wrong_if=("B03",), right_if=("B10", "B07", "B01"),
        params={"arm_shift": "-0.55 logit ≈ 12pp improvement ASSUME", "sigma_prep": f"{SIGMA_MID} STRESS"}))

    # 3. The error rate falls only because the cells that missegregate stop being observed.
    out.append(World(
        "selective_loss", "Fewer observed errors caused by selective death and fewer divisions",
        "false rescue produced by a changed observed population",
        "selection",
        selection_truth(arm_shift=0.0, death_slope=1.6, divide_test=0.70),
        DESIGN_3,
        wrong_if=("B10", "B03"), right_if=("B08", "B09"),
        notes="true per-cell error probability is identical in both arms",
        params={"death_given_error": "1.6 logit, error-prone cells preferentially lost STRESS",
                "divide_logit test": "0.85 → 0.70 STRESS"}))

    # 4. Real improvement that arrives with harm.
    out.append(World(
        "benefit_with_harm", "Genuine functional improvement accompanied by harm",
        "harm hidden by a favourable endpoint, or benefit declared impossible because harm exists",
        "selection",
        selection_truth(arm_shift=-0.8, death_slope=0.0, divide_test=0.84, death_test=0.22),
        DESIGN_3,
        wrong_if=("B03",), right_if=("B08", "B09", "B14"),
        notes="a real per-cell improvement AND a real rise in death; both facts must survive",
        params={"arm_shift": "-0.8 logit ASSUME", "death 0.05 → 0.22": "STRESS"}))

    # 5. Both arms fail their assay controls.
    out.append(World(
        "invalid_assay", "Reference and test arms both fail assay controls",
        "an invalid assay treated as evidence of adequacy",
        "rate", rate_truth(0.30, 0.0, SIGMA_HIGH), DESIGN_3,
        wrong_if=("B03", "B10", "B04"), right_if=("B00", "B01"),
        notes="controls_valid is False in the observation vector; nothing downstream may be concluded",
        params={"qc": "controls_valid=False, precision_adequate=False"}))

    # 6. Expression windows overlap only because a strongly selected subset was compared.
    out.append(World(
        "matching_illusion", "Apparent expression overlap from strongly selected subsets",
        "conditional matching overread as population rescue",
        "matching",
        dgp.MatchingTruth(expr_mean={"ref": 0.0, "test": -1.2}, expr_sd=0.55, sigma_prep=SIGMA_LOW,
                          capacity_on_expression=0.9, capacity_on_fidelity=-0.6,
                          base_logit=dgp.logit(0.30), arm_logit={"ref": 0.0, "test": 0.0}),
        DESIGN_3,
        wrong_if=("B03",), right_if=("B02", "B01"),
        notes="the test arm's matched cells are its upper tail; the matched comparison is not the population",
        params={"expr_mean shift": "-1.2, test arm systematically lower STRESS",
                "capacity_on_fidelity": "-0.6 STRESS", "arm_logit": "0.0 — no true population effect"}))

    # 7. Four different timing mechanisms that one interval collapses into one number.
    # These fields are on the LOG scale: the DGP exponentiates them. Values are written as
    # log(minutes) so the intended median is readable. Passing minutes directly makes every cell
    # exceed the imaging window — a bug this suite hit once and now guards against.
    L = math.log
    base_align = {"ref": L(22.0), "test": L(22.0)}          # 22 min median to alignment  ASSUME
    base_exit = {"ref": L(18.0), "test": L(18.0)}           # 18 min median alignment→anaphase ASSUME
    for key, title, exit_med, align_med, prem, never, trap in [
        ("timing_delayed_exit", "Delayed exit (silencing defect)", {"ref": L(18.0), "test": L(30.0)}, base_align,
         {"ref": 0.02, "test": 0.02}, {"ref": 0.03, "test": 0.03}, "read as an arrest, or as normal"),
        ("timing_delayed_align", "Delayed alignment, normal exit", base_exit, {"ref": L(22.0), "test": L(36.0)},
         {"ref": 0.02, "test": 0.02}, {"ref": 0.03, "test": 0.03},
         "an alignment defect misread as a silencing defect from NEBD-to-anaphase"),
        ("timing_premature", "Premature progression without full alignment", base_exit, base_align,
         {"ref": 0.02, "test": 0.30}, {"ref": 0.03, "test": 0.03},
         "cells that never complete alignment drop out, so the interval looks normal or improved"),
        ("timing_no_exit", "Cells that never exit within the window", base_exit, base_align,
         {"ref": 0.02, "test": 0.02}, {"ref": 0.03, "test": 0.28},
         "the most affected cells are unobservable, so the observed interval looks fine"),
    ]:
        out.append(World(
            key, title, trap, "timing",
            dgp.TimingTruth(log_align=align_med, log_exit=exit_med, sd_align=0.35, sd_exit=0.40,
                            sigma_prep=0.20, p_premature=prem, p_never_align=never, window=180.0,
                            loss_hazard={"ref": 0.002, "test": 0.002}),
            DESIGN_3, wrong_if=("B03",), right_if=("B04", "B01"),
            params={"medians (min)": "align/exit medians on the log scale; see code ASSUME",
                    "premature": f"{prem} STRESS", "never_align": f"{never} STRESS",
                    "window": "180 min ASSUME"}))

    # 8. Upstream marker moves, function does not.
    out.append(World(
        "upstream_only", "Intracellular NAD+ rises with no functional improvement",
        "an upstream biomarker treated as rescue",
        "rate", rate_truth(0.30, 0.0, SIGMA_MID), DESIGN_3,
        wrong_if=("B10", "B03"), right_if=("B07", "B06", "B01", "B15"),
        notes="observation vector carries nad_intracellular=increased with every function endpoint unchanged",
        params={"nad": "increased (set directly in the vector)", "arm_shift": "0.0"}))

    # 9. Few preparations, imbalance and heterogeneity.
    out.append(World(
        "few_preps_heterogeneous", "Three preparations, arm-confounded, high heterogeneity",
        "false precision and unstable inference",
        "rate", rate_truth(0.30, -0.35, SIGMA_HIGH), DESIGN_3_SPLIT,
        wrong_if=(), right_if=("B01",),
        notes="arms split across preparations, so preparation and arm are partly confounded",
        params={"sigma_prep": f"{SIGMA_HIGH} STRESS", "allocation": "unit — arms split across preparations STRESS"}))

    # 10. Informative tracking loss.
    out.append(World(
        "informative_loss", "Informative tracking loss",
        "missingness read as a successful or a negative experiment",
        "timing",
        dgp.TimingTruth(log_align=base_align, log_exit={"ref": L(18.0), "test": L(26.0)}, sd_align=0.35,
                        sd_exit=0.40, sigma_prep=0.20, p_premature={"ref": 0.02, "test": 0.02},
                        p_never_align={"ref": 0.03, "test": 0.03}, window=180.0,
                        loss_hazard={"ref": 0.002, "test": 0.020}),
        DESIGN_3, wrong_if=("B03",), right_if=("B01", "B04"),
        notes="the test arm loses long mitoses preferentially, shortening its observed interval",
        params={"loss_hazard": "0.002 vs 0.020 per min STRESS"}))

    # 11. A real, clean improvement: the design must be able to find one.
    out.append(World(
        "true_benefit_clean", "Genuine improvement, no harm, no selection",
        "a design so conservative it cannot detect a real effect",
        "rate", rate_truth(0.30, -1.1, SIGMA_MID), DESIGN_3,
        wrong_if=(), right_if=("B10",),
        notes="the positive control for the decision system itself",
        params={"arm_shift": "-1.1 logit ≈ 18pp improvement ASSUME"}))

    return out
