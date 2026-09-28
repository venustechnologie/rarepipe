"""Data generating processes. All synthetic; see package docstring.

The clustering is modelled the way the assay actually runs: cells inside a vessel, vessels inside
an independently prepared batch ("preparation"), with a between-preparation variance component.
Two allocation structures are modelled separately, because M5_W004 is ambiguous between them and
they have very different operating characteristics:

  * ``block``          every arm appears in every preparation -> the preparation effect cancels
                       in the within-preparation contrast.
  * ``unit``           each preparation carries one arm -> the preparation effect is confounded
                       with the arm and enters the contrast at full variance. This is what
                       "one independently prepared batch ... assayed as a unit" reads like.
  * ``partial_block``  some preparations carry both arms, others only one (batch imbalance).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    return np.log(p / (1.0 - p))


# ── rate endpoints (missegregation, alignment defect fraction, MPM-2 positivity) ─────────────


@dataclass(frozen=True)
class RateDesign:
    """How many preparations, vessels and scorable units, and how arms sit across preparations."""

    arms: tuple[str, ...] = ("wt", "mut")
    n_prep: int = 3
    n_vessel: int = 2
    n_cells: int = 100
    allocation: str = "block"
    shared_preps: int = 1  # partial_block only: preparations carrying every arm
    cells_dispersion: float = 0.0  # >0 makes the scorable count per vessel vary (Poisson-like)


@dataclass(frozen=True)
class RateTruth:
    """The assumed truth on the logit scale. ``arm_logit`` is additive against ``base_logit``."""

    base_logit: float
    arm_logit: dict[str, float]
    sigma_prep: float
    sigma_vessel: float
    arm_sigma_prep: dict[str, float] = field(default_factory=dict)  # per-arm heterogeneity multiplier


@dataclass
class RateData:
    prep: np.ndarray
    arm: np.ndarray  # integer index into design.arms
    y: np.ndarray
    n: np.ndarray
    arms: tuple[str, ...]


def _prep_arm_layout(design: RateDesign, rng) -> list[tuple[int, int]]:
    """Return the (preparation, arm index) cells of the design."""
    n_arm = len(design.arms)
    out: list[tuple[int, int]] = []
    if design.allocation == "block":
        for p in range(design.n_prep):
            out += [(p, a) for a in range(n_arm)]
    elif design.allocation == "unit":
        # n_prep preparations *per arm*; each preparation carries exactly one arm.
        for a in range(n_arm):
            for k in range(design.n_prep):
                out.append((a * design.n_prep + k, a))
    elif design.allocation == "partial_block":
        shared = design.shared_preps
        for p in range(shared):
            out += [(p, a) for a in range(n_arm)]
        nxt = shared
        for a in range(n_arm):
            for _ in range(max(0, design.n_prep - shared)):
                out.append((nxt, a))
                nxt += 1
    else:  # pragma: no cover - guarded by the world registry
        raise ValueError(f"unknown allocation {design.allocation!r}")
    return out


def simulate_rate(rng, design: RateDesign, truth: RateTruth) -> RateData:
    layout = _prep_arm_layout(design, rng)
    n_prep_total = max(p for p, _ in layout) + 1
    u = rng.normal(0.0, 1.0, size=n_prep_total)  # standardised preparation effect
    prep_i, arm_i, ys, ns = [], [], [], []
    for p, a in layout:
        name = design.arms[a]
        sp = truth.sigma_prep * truth.arm_sigma_prep.get(name, 1.0)
        eta_pa = truth.base_logit + truth.arm_logit.get(name, 0.0) + sp * u[p]
        for _ in range(design.n_vessel):
            w = rng.normal(0.0, truth.sigma_vessel) if truth.sigma_vessel > 0 else 0.0
            n = design.n_cells
            if design.cells_dispersion > 0:
                n = int(max(5, rng.poisson(design.n_cells) if design.cells_dispersion >= 1
                            else design.n_cells * (1 + design.cells_dispersion * rng.normal())))
            p_err = float(expit(eta_pa + w))
            ys.append(rng.binomial(n, p_err))
            ns.append(n)
            prep_i.append(p)
            arm_i.append(a)
    return RateData(np.array(prep_i), np.array(arm_i), np.array(ys, float), np.array(ns, float), design.arms)


def marginal_rate(truth: RateTruth, arm: str, *, nodes: int = 41) -> float:
    """Population-averaged event probability for an arm, integrating over both variance components."""
    x, wq = np.polynomial.hermite.hermgauss(nodes)
    z, wz = np.sqrt(2) * x, wq / np.sqrt(np.pi)
    sp = truth.sigma_prep * truth.arm_sigma_prep.get(arm, 1.0)
    eta = truth.base_logit + truth.arm_logit.get(arm, 0.0)
    grid = eta + sp * z[:, None] + truth.sigma_vessel * z[None, :]
    return float(np.sum(np.outer(wz, wz) * expit(grid)))


# ── selective loss / changed observed population ─────────────────────────────────────────────


@dataclass(frozen=True)
class SelectionTruth:
    """Cell-level truth where the *observed* population is changed by the intervention.

    Per-cell latent error propensity gets a cell-level term; the intervention raises the death
    hazard of the cells with the highest propensity (or lowers their division probability). The
    per-cell propensity itself is unchanged by the intervention when ``arm_logit`` is 0, so any
    apparent improvement in the conditional rate is entirely a composition effect.
    """

    base_logit: float
    arm_logit: dict[str, float]
    sigma_prep: float
    sigma_vessel: float
    sigma_cell: float
    death_base: dict[str, float]  # probability of dying before a scorable division
    death_slope: dict[str, float]  # extra death log-odds per unit of latent error propensity
    divide_base: dict[str, float]  # probability a surviving cell produces a scorable division


@dataclass
class SelectionData:
    prep: np.ndarray
    arm: np.ndarray
    y_obs: np.ndarray  # errors among observed divisions
    n_obs: np.ndarray  # observed divisions (the conditional denominator)
    n_cohort: np.ndarray  # cells at risk at the start (the cohort denominator)
    n_error_free: np.ndarray  # error-free scorable divisions from the starting cohort
    deaths: np.ndarray
    nondiv: np.ndarray
    arms: tuple[str, ...]


def simulate_selection(rng, design: RateDesign, truth: SelectionTruth) -> SelectionData:
    layout = _prep_arm_layout(design, rng)
    n_prep_total = max(p for p, _ in layout) + 1
    u = rng.normal(0.0, 1.0, size=n_prep_total)
    cols: dict[str, list] = {k: [] for k in
                             ("prep", "arm", "y_obs", "n_obs", "n_cohort", "n_error_free", "deaths", "nondiv")}
    for p, a in layout:
        name = design.arms[a]
        eta_pa = truth.base_logit + truth.arm_logit.get(name, 0.0) + truth.sigma_prep * u[p]
        for _ in range(design.n_vessel):
            w = rng.normal(0.0, truth.sigma_vessel) if truth.sigma_vessel > 0 else 0.0
            n = design.n_cells
            e = rng.normal(0.0, truth.sigma_cell, size=n)  # latent per-cell error propensity
            eta_cell = eta_pa + w + e
            p_err = expit(eta_cell)
            err = rng.random(n) < p_err
            d_logit = logit(np.clip(truth.death_base.get(name, 0.05), 1e-6, 1 - 1e-6))
            p_death = expit(d_logit + truth.death_slope.get(name, 0.0) * e)
            died = rng.random(n) < p_death
            divided = (~died) & (rng.random(n) < truth.divide_base.get(name, 0.9))
            cols["prep"].append(p)
            cols["arm"].append(a)
            cols["y_obs"].append(int(np.sum(err & divided)))
            cols["n_obs"].append(int(np.sum(divided)))
            cols["n_cohort"].append(int(n))
            cols["n_error_free"].append(int(np.sum(divided & ~err)))
            cols["deaths"].append(int(np.sum(died)))
            cols["nondiv"].append(int(np.sum(~died & ~divided)))
    return SelectionData(*(np.array(cols[k], float) if k not in ("prep", "arm") else np.array(cols[k])
                           for k in ("prep", "arm", "y_obs", "n_obs", "n_cohort", "n_error_free", "deaths",
                                     "nondiv")), arms=design.arms)


# ── mitotic timing (alignment-to-anaphase interval and its competing outcomes) ───────────────


@dataclass(frozen=True)
class TimingTruth:
    """Four distinct mechanisms, all of which the plan reduces to one alignment-to-anaphase number.

    ``log_align`` / ``log_exit`` are lognormal medians (minutes) for time-to-alignment and for the
    alignment-to-anaphase interval. ``p_premature`` is the chance a cell enters anaphase without
    completing alignment; ``p_never_align`` the chance it never aligns; ``window`` the imaging
    window, so a cell whose total mitosis exceeds it has no observed exit. ``loss_hazard`` is an
    informative tracking-loss hazard per minute of observed mitosis.
    """

    log_align: dict[str, float]
    log_exit: dict[str, float]
    sd_align: float
    sd_exit: float
    sigma_prep: float
    p_premature: dict[str, float]
    p_never_align: dict[str, float]
    window: float
    loss_hazard: dict[str, float]


@dataclass
class TimingData:
    prep: np.ndarray
    arm: np.ndarray
    a2a: list[np.ndarray]  # observed alignment-to-anaphase intervals, per (prep, arm) cell group
    nebd2a: list[np.ndarray]  # observed NEBD-to-anaphase intervals for the same divisions
    counts: dict[str, np.ndarray]  # premature / never_align / no_exit / tracking_loss / scored
    arms: tuple[str, ...]


def simulate_timing(rng, design: RateDesign, truth: TimingTruth) -> TimingData:
    layout = _prep_arm_layout(design, rng)
    n_prep_total = max(p for p, _ in layout) + 1
    u = rng.normal(0.0, 1.0, size=n_prep_total)
    prep_i, arm_i, a2a, nebd, counts = [], [], [], [], {k: [] for k in
                                                        ("premature", "never_align", "no_exit", "tracking_loss",
                                                         "scored")}
    for p, a in layout:
        name = design.arms[a]
        n = design.n_cells * design.n_vessel
        shift = truth.sigma_prep * u[p]
        t_al = np.exp(truth.log_align[name] + shift + rng.normal(0, truth.sd_align, n))
        t_ex = np.exp(truth.log_exit[name] + shift + rng.normal(0, truth.sd_exit, n))
        never = rng.random(n) < truth.p_never_align.get(name, 0.0)
        prem = (~never) & (rng.random(n) < truth.p_premature.get(name, 0.0))
        total = t_al + t_ex
        no_exit = (~never) & (~prem) & (total > truth.window)
        # Informative tracking loss: hazard applies over the observed duration of mitosis.
        haz = truth.loss_hazard.get(name, 0.0)
        p_loss = 1.0 - np.exp(-haz * np.minimum(total, truth.window))
        lost = rng.random(n) < p_loss
        scored = (~never) & (~prem) & (~no_exit) & (~lost)
        prep_i.append(p)
        arm_i.append(a)
        a2a.append(t_ex[scored])
        nebd.append(total[scored])
        counts["premature"].append(int(prem.sum()))
        counts["never_align"].append(int(never.sum()))
        counts["no_exit"].append(int(no_exit.sum()))
        counts["tracking_loss"].append(int((lost & ~never & ~prem & ~no_exit).sum()))
        counts["scored"].append(int(scored.sum()))
    return TimingData(np.array(prep_i), np.array(arm_i), a2a, nebd,
                      {k: np.array(v, float) for k, v in counts.items()}, design.arms)


# ── per-cell expression matching (E01_EXPR) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class MatchingTruth:
    """Expression and fidelity both depend on a latent per-cell capacity.

    ``capacity_on_expression`` and ``capacity_on_fidelity`` make the matched subset a selected
    sample: if the altered-protein arm expresses lower on average, the cells that fall inside the
    wild-type window are drawn from its high-capacity tail, which is also the tail with better
    fidelity. The population-level truth is ``arm_logit``; the matched comparison estimates
    something else.
    """

    expr_mean: dict[str, float]
    expr_sd: float
    capacity_on_expression: float
    capacity_on_fidelity: float
    base_logit: float
    arm_logit: dict[str, float]
    sigma_prep: float
    min_matched_fraction: float = 0.30  # the M5_W001 operational rule


@dataclass
class MatchingData:
    prep: np.ndarray
    arm: np.ndarray
    matched_y: np.ndarray
    matched_n: np.ndarray
    full_y: np.ndarray
    full_n: np.ndarray
    matched_fraction: np.ndarray
    arms: tuple[str, ...]


def simulate_matching(rng, design: RateDesign, truth: MatchingTruth) -> MatchingData:
    layout = _prep_arm_layout(design, rng)
    n_prep_total = max(p for p, _ in layout) + 1
    u = rng.normal(0.0, 1.0, size=n_prep_total)
    rows: dict[str, list] = {k: [] for k in
                             ("prep", "arm", "matched_y", "matched_n", "full_y", "full_n", "matched_fraction")}
    for p, _a in {(p, a) for p, a in layout}:
        pass
    # The window is defined on the wild-type arm inside each preparation, then applied to both.
    by_prep: dict[int, dict[int, tuple]] = {}
    for p, a in layout:
        name = design.arms[a]
        n = design.n_cells * design.n_vessel
        cap = rng.normal(0, 1, n)
        expr = truth.expr_mean[name] + truth.capacity_on_expression * cap + rng.normal(0, truth.expr_sd, n)
        eta = (truth.base_logit + truth.arm_logit.get(name, 0.0) + truth.sigma_prep * u[p]
               - truth.capacity_on_fidelity * cap)
        err = rng.random(n) < expit(eta)
        by_prep.setdefault(p, {})[a] = (expr, err)
    wt_index = design.arms.index("wt") if "wt" in design.arms else 0
    for p, per_arm in sorted(by_prep.items()):
        ref = per_arm.get(wt_index)
        if ref is None:  # unit allocation: fall back to the pooled wild-type window
            all_wt = [v[wt_index][0] for v in by_prep.values() if wt_index in v]
            ref = (np.concatenate(all_wt), None)
        lo, hi = np.percentile(ref[0], [25, 75])
        for a, (expr, err) in sorted(per_arm.items()):
            inside = (expr >= lo) & (expr <= hi)
            rows["prep"].append(p)
            rows["arm"].append(a)
            rows["matched_y"].append(float(err[inside].sum()))
            rows["matched_n"].append(float(inside.sum()))
            rows["full_y"].append(float(err.sum()))
            rows["full_n"].append(float(err.size))
            rows["matched_fraction"].append(float(inside.mean()))
    return MatchingData(np.array(rows["prep"]), np.array(rows["arm"]), *(np.array(rows[k], float) for k in
                        ("matched_y", "matched_n", "full_y", "full_n", "matched_fraction")), arms=design.arms)
