"""Candidate analyses and candidate decision framings. All synthetic; see package docstring.

Three analyses of the same clustered rate data, all reporting the contrast on the
risk-difference scale that M5_W004 chose as the effect scale, so the margins mean the same thing
for all three:

  1. ``prep_summary``  — one proportion per preparation per arm, then a paired or two-sample t
     interval on K-1 degrees of freedom. This is the "preparation-level summary" of M5_W004.
  2. ``glmm``          — binomial-logit-normal generalised linear mixed model with a random
     intercept per preparation *and* per vessel, fitted by nested Gauss-Hermite quadrature; the
     contrast is the population-averaged risk difference obtained by integrating over both
     variance components, with a delta-method interval. Reported with a normal critical value
     (as a generic mixed-model routine would) and with a t(K-1) critical value.
  3. ``cluster_robust`` — logistic regression ignoring the random effects with a
     cluster-robust sandwich clustered on preparation, both with a normal and a t(K-1)
     critical value. This is the sensitivity analysis M5_W004 specifies.

Two decision framings on top of each analysis:

  * ``difference``  — two-sided test of no difference. "No significant difference from the
    wild-type arm" is read as adequacy. This is the framing R04 warns about; it is simulated in
    order to measure its false-adequacy rate, not because it is recommended.
  * ``adequacy``    — a margin is stated in advance; adequacy requires the interval to exclude an
    adverse difference as large as the margin, inadequacy requires the interval to lie entirely
    beyond it, and anything else is explicitly UNRESOLVED.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, special, stats

from .dgp import expit


@dataclass
class Estimate:
    """A contrast on the risk-difference (or minutes) scale with an interval and a p-value."""

    est: float
    lo: float
    hi: float
    p_two_sided: float
    se: float
    df: float
    method: str
    ok: bool = True
    note: str = ""


def _nan_estimate(method: str, note: str) -> Estimate:
    return Estimate(np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, method, ok=False, note=note)


# ── analysis 1: preparation-level summary ───────────────────────────────────────────────────


def prep_summary(prep, arm, y, n, a: int, b: int, alpha: float = 0.05,
                 method_label: str = "prep_summary") -> Estimate:
    """Contrast arm ``b`` minus arm ``a`` as a difference of preparation-level proportions."""
    props: dict[tuple[int, int], float] = {}
    for p in np.unique(prep):
        for k in (a, b):
            m = (prep == p) & (arm == k)
            if m.any() and n[m].sum() > 0:
                props[(int(p), k)] = float(y[m].sum() / n[m].sum())
    preps_a = {p for (p, k) in props if k == a}
    preps_b = {p for (p, k) in props if k == b}
    paired = sorted(preps_a & preps_b)
    only_a, only_b = sorted(preps_a - preps_b), sorted(preps_b - preps_a)
    if paired and not only_a and not only_b:
        d = np.array([props[(p, b)] - props[(p, a)] for p in paired])
        k = d.size
        if k < 2:
            return _nan_estimate(method_label, "fewer than two paired preparations")
        est, se, df = float(d.mean()), float(d.std(ddof=1) / np.sqrt(k)), k - 1
    elif not paired:
        xa = np.array([props[(p, a)] for p in only_a])
        xb = np.array([props[(p, b)] for p in only_b])
        if xa.size < 2 or xb.size < 2:
            return _nan_estimate(method_label, "fewer than two preparations in an arm")
        va, vb = xa.var(ddof=1) / xa.size, xb.var(ddof=1) / xb.size
        est, se = float(xb.mean() - xa.mean()), float(np.sqrt(va + vb))
        df = (va + vb) ** 2 / (va ** 2 / (xa.size - 1) + vb ** 2 / (xb.size - 1)) if se > 0 else 1.0
    else:
        # Batch imbalance: paired preparations plus unpaired ones. Analysed as the paired
        # contrast only, which is what a within-preparation summary can support, and the
        # discarded preparations are recorded in the note.
        d = np.array([props[(p, b)] - props[(p, a)] for p in paired])
        if d.size < 2:
            return _nan_estimate(method_label, "imbalanced design leaves <2 paired preparations")
        est, se, df = float(d.mean()), float(d.std(ddof=1) / np.sqrt(d.size)), d.size - 1
        method_label += f"(paired {d.size}; dropped {len(only_a) + len(only_b)} unpaired)"
    if not np.isfinite(se) or se == 0:
        return _nan_estimate(method_label, "zero or undefined standard error (no between-preparation spread)")
    crit = stats.t.ppf(1 - alpha / 2, df)
    p = 2 * (1 - stats.t.cdf(abs(est / se), df))
    return Estimate(est, est - crit * se, est + crit * se, float(p), se, float(df), method_label)


# ── analysis 2: binomial-logit-normal GLMM by nested Gauss-Hermite quadrature ────────────────

_GH_NODES = 11
_X, _W = np.polynomial.hermite.hermgauss(_GH_NODES)
_Z = np.sqrt(2.0) * _X
_LOGW = np.log(_W / np.sqrt(np.pi))


def _glmm_negll(theta, prep, arm_dummies, y, n, n_arm):
    beta = theta[:n_arm]
    sig_p, sig_v = np.exp(theta[n_arm]), np.exp(theta[n_arm + 1])
    eta0 = arm_dummies @ beta
    total = 0.0
    for p in np.unique(prep):
        m = prep == p
        e = eta0[m][:, None, None] + sig_p * _Z[None, :, None] + sig_v * _Z[None, None, :]
        kern = y[m][:, None, None] * e - n[m][:, None, None] * np.logaddexp(0.0, e)
        log_inner = special.logsumexp(_LOGW[None, None, :] + kern, axis=2)  # (vessel, node_p)
        total += special.logsumexp(_LOGW + log_inner.sum(axis=0))
    return -total


def _marginal_probs(theta, n_arm):
    beta = theta[:n_arm]
    sig_p, sig_v = np.exp(theta[n_arm]), np.exp(theta[n_arm + 1])
    grid = beta[:, None, None] + sig_p * _Z[None, :, None] + sig_v * _Z[None, None, :]
    w2 = np.exp(_LOGW)[None, :, None] * np.exp(_LOGW)[None, None, :]
    return np.sum(w2 * expit(grid), axis=(1, 2))


def _numeric_hessian(f, x, h=1e-4):
    k = x.size
    H = np.zeros((k, k))
    f0 = f(x)
    for i in range(k):
        for j in range(i, k):
            ei, ej = np.zeros(k), np.zeros(k)
            ei[i] = h
            ej[j] = h
            if i == j:
                H[i, i] = (f(x + ei) - 2 * f0 + f(x - ei)) / h ** 2
            else:
                v = (f(x + ei + ej) - f(x + ei - ej) - f(x - ei + ej) + f(x - ei - ej)) / (4 * h ** 2)
                H[i, j] = H[j, i] = v
    return H


def glmm(prep, arm, y, n, a: int, b: int, alpha: float = 0.05, small_sample: bool = True) -> Estimate:
    """Population-averaged risk difference (arm b minus arm a) from a two-level binomial GLMM."""
    arms_present = sorted(set(int(v) for v in np.unique(arm)))
    idx = {v: i for i, v in enumerate(arms_present)}
    n_arm = len(arms_present)
    D = np.zeros((arm.size, n_arm))
    D[np.arange(arm.size), [idx[int(v)] for v in arm]] = 1.0
    p0 = np.clip(y.sum() / max(n.sum(), 1), 1e-3, 1 - 1e-3)
    theta0 = np.r_[np.full(n_arm, np.log(p0 / (1 - p0))), np.log(0.4), np.log(0.2)]
    bounds = [(-12, 12)] * n_arm + [(-7, 2.5), (-7, 2.5)]
    fun = lambda t: _glmm_negll(t, prep, D, y, n, n_arm)  # noqa: E731
    try:
        res = optimize.minimize(fun, theta0, method="L-BFGS-B", bounds=bounds)
    except Exception as exc:  # pragma: no cover - numerical guard
        return _nan_estimate("glmm", f"fit failed: {exc}")
    if not np.isfinite(res.fun):
        return _nan_estimate("glmm", "non-finite likelihood")
    th = res.x
    H = _numeric_hessian(fun, th)
    try:
        V = np.linalg.pinv(H)
    except np.linalg.LinAlgError:  # pragma: no cover
        return _nan_estimate("glmm", "singular Hessian")
    ia, ib = idx[a], idx[b]
    g = lambda t: float(_marginal_probs(t, n_arm)[ib] - _marginal_probs(t, n_arm)[ia])  # noqa: E731
    est = g(th)
    grad = np.zeros(th.size)
    for i in range(th.size):
        e = np.zeros(th.size)
        e[i] = 1e-5
        grad[i] = (g(th + e) - g(th - e)) / (2e-5)
    var = float(grad @ V @ grad)
    if not np.isfinite(var) or var <= 0:
        return _nan_estimate("glmm", "non-positive delta-method variance (variance component at boundary)")
    se = float(np.sqrt(var))
    k_prep = int(np.unique(prep).size)
    df = max(k_prep - 1, 1) if small_sample else np.inf
    crit = stats.t.ppf(1 - alpha / 2, df) if np.isfinite(df) else stats.norm.ppf(1 - alpha / 2)
    p = 2 * (1 - (stats.t.cdf(abs(est / se), df) if np.isfinite(df) else stats.norm.cdf(abs(est / se))))
    label = "glmm_t(K-1)" if small_sample else "glmm_wald"
    boundary = th[n_arm] <= -6.5 or th[n_arm + 1] <= -6.5
    return Estimate(est, est - crit * se, est + crit * se, float(p), se, float(df), label,
                    note="variance component at boundary" if boundary else "")


# ── analysis 3: logistic GLM with a cluster-robust sandwich ──────────────────────────────────


def cluster_robust(prep, arm, y, n, a: int, b: int, alpha: float = 0.05, small_sample: bool = True) -> Estimate:
    arms_present = sorted(set(int(v) for v in np.unique(arm)))
    idx = {v: i for i, v in enumerate(arms_present)}
    k = len(arms_present)
    X = np.zeros((arm.size, k))
    X[np.arange(arm.size), [idx[int(v)] for v in arm]] = 1.0
    beta = np.zeros(k)
    for _ in range(100):  # IRLS on aggregated binomial data
        eta = X @ beta
        mu = expit(eta)
        wv = n * mu * (1 - mu)
        if np.any(wv <= 1e-12):
            wv = np.maximum(wv, 1e-12)
        z = eta + (y - n * mu) / wv
        A = X.T @ (wv[:, None] * X)
        try:
            new = np.linalg.solve(A, X.T @ (wv * z))
        except np.linalg.LinAlgError:  # pragma: no cover
            return _nan_estimate("cluster_robust", "singular information matrix")
        if np.max(np.abs(new - beta)) < 1e-10:
            beta = new
            break
        beta = np.clip(new, -12, 12)
    eta = X @ beta
    mu = expit(eta)
    wv = np.maximum(n * mu * (1 - mu), 1e-12)
    bread = np.linalg.pinv(X.T @ (wv[:, None] * X))
    meat = np.zeros((k, k))
    clusters = np.unique(prep)
    for p in clusters:
        m = prep == p
        s = X[m].T @ (y[m] - n[m] * mu[m])
        meat += np.outer(s, s)
    K = clusters.size
    corr = K / max(K - 1, 1) * (n.size - 1) / max(n.size - k, 1)  # CR1-style small-sample scaling
    V = bread @ (corr * meat) @ bread
    ia, ib = idx[a], idx[b]
    pa, pb = expit(beta[ia]), expit(beta[ib])
    grad = np.zeros(k)
    grad[ia] = -pa * (1 - pa)
    grad[ib] = pb * (1 - pb)
    var = float(grad @ V @ grad)
    if not np.isfinite(var) or var <= 0:
        return _nan_estimate("cluster_robust", "non-positive sandwich variance")
    se = float(np.sqrt(var))
    est = float(pb - pa)
    df = max(K - 1, 1) if small_sample else np.inf
    crit = stats.t.ppf(1 - alpha / 2, df) if np.isfinite(df) else stats.norm.ppf(1 - alpha / 2)
    p = 2 * (1 - (stats.t.cdf(abs(est / se), df) if np.isfinite(df) else stats.norm.cdf(abs(est / se))))
    return Estimate(est, est - crit * se, est + crit * se, float(p), se, float(df),
                    "cluster_robust_t(K-1)" if small_sample else "cluster_robust_z")


# ── timing analyses ──────────────────────────────────────────────────────────────────────────


def prep_median_diff(prep, arm, groups: list[np.ndarray], a: int, b: int, alpha: float = 0.05,
                     min_cells: int = 5) -> Estimate:
    """Difference in preparation-level median interval (minutes), arm b minus arm a."""
    med: dict[tuple[int, int], float] = {}
    for i, (p, k) in enumerate(zip(prep, arm)):
        g = groups[i]
        if g.size >= min_cells:
            med[(int(p), int(k))] = float(np.median(g))
    preps_a = {p for (p, k) in med if k == a}
    preps_b = {p for (p, k) in med if k == b}
    paired = sorted(preps_a & preps_b)
    if len(paired) >= 2:
        d = np.array([med[(p, b)] - med[(p, a)] for p in paired])
        est, se, df = float(d.mean()), float(d.std(ddof=1) / np.sqrt(d.size)), d.size - 1
    else:
        xa = np.array([med[(p, a)] for p in sorted(preps_a)])
        xb = np.array([med[(p, b)] for p in sorted(preps_b)])
        if xa.size < 2 or xb.size < 2:
            return _nan_estimate("prep_median", "fewer than two preparations with a scorable median")
        va, vb = xa.var(ddof=1) / xa.size, xb.var(ddof=1) / xb.size
        est, se = float(xb.mean() - xa.mean()), float(np.sqrt(va + vb))
        df = (va + vb) ** 2 / (va ** 2 / (xa.size - 1) + vb ** 2 / (xb.size - 1)) if se > 0 else 1.0
    if not np.isfinite(se) or se <= 0:
        return _nan_estimate("prep_median", "zero standard error")
    crit = stats.t.ppf(1 - alpha / 2, df)
    p = 2 * (1 - stats.t.cdf(abs(est / se), df))
    return Estimate(est, est - crit * se, est + crit * se, float(p), se, float(df), "prep_median")


def lmm_log_interval(prep, arm, groups: list[np.ndarray], a: int, b: int, alpha: float = 0.05) -> Estimate:
    """Random-intercept LMM on log interval; contrast back-transformed to a median ratio.

    Reported on the log scale (``est`` is the difference in log medians) so the caller can apply a
    ratio margin. Exact Gaussian likelihood with compound symmetry inside a preparation.
    """
    rows = []
    for i, (p, k) in enumerate(zip(prep, arm)):
        if int(k) in (a, b) and groups[i].size >= 3:
            rows.append((int(p), 1.0 if int(k) == b else 0.0, np.log(groups[i])))
    if len({r[0] for r in rows}) < 2 or len(rows) < 3:
        return _nan_estimate("lmm_log", "insufficient preparations for a variance component")
    preps = sorted({r[0] for r in rows})

    def negll(th):
        b0, d1, ls_p, ls_e = th
        sp2, se2 = np.exp(2 * ls_p), np.exp(2 * ls_e)
        tot = 0.0
        for p in preps:
            ys, xs = [], []
            for pp, x, lg in rows:
                if pp == p:
                    ys.append(lg)
                    xs.append(np.full(lg.size, x))
            yv, xv = np.concatenate(ys), np.concatenate(xs)
            r = yv - (b0 + d1 * xv)
            m = r.size
            # (se2 I + sp2 11')^-1 via Woodbury; logdet in closed form.
            s = r.sum()
            quad = (r @ r) / se2 - sp2 * s * s / (se2 * (se2 + m * sp2))
            logdet = (m - 1) * np.log(se2) + np.log(se2 + m * sp2)
            tot += 0.5 * (quad + logdet + m * np.log(2 * np.pi))
        return tot

    th0 = np.array([np.mean([r[2].mean() for r in rows]), 0.0, np.log(0.1), np.log(0.4)])
    res = optimize.minimize(negll, th0, method="L-BFGS-B",
                            bounds=[(-10, 10), (-5, 5), (-7, 2), (-7, 2)])
    th = res.x
    H = _numeric_hessian(negll, th, h=1e-4)
    V = np.linalg.pinv(H)
    se = float(np.sqrt(max(V[1, 1], 0)))
    if se <= 0 or not np.isfinite(se):
        return _nan_estimate("lmm_log", "non-positive variance for the contrast")
    est = float(th[1])
    df = max(len(preps) - 1, 1)
    crit = stats.t.ppf(1 - alpha / 2, df)
    p = 2 * (1 - stats.t.cdf(abs(est / se), df))
    return Estimate(est, est - crit * se, est + crit * se, float(p), se, float(df), "lmm_log_interval")


# ── decision framings ────────────────────────────────────────────────────────────────────────

ADEQUATE, INADEQUATE, UNRESOLVED, PARTIAL = "adequate", "inadequate", "unresolved", "partial"


def framing_difference(e: Estimate, adverse_sign: int, alpha: float = 0.05) -> str:
    """"No significant difference from the reference" is read as adequacy. Under test, not advised."""
    if not e.ok:
        return UNRESOLVED
    if e.p_two_sided < alpha:
        return INADEQUATE if e.est * adverse_sign > 0 else ADEQUATE
    return ADEQUATE


def framing_adequacy(e: Estimate, margin: float, adverse_sign: int, two_sided_region: bool = False) -> str:
    """Margin stated in advance; the third outcome is explicit."""
    if not e.ok:
        return UNRESOLVED
    lo, hi = (e.lo, e.hi) if adverse_sign > 0 else (-e.hi, -e.lo)
    if two_sided_region:
        if lo > -margin and hi < margin:
            return ADEQUATE
        if lo > margin or hi < -margin:
            return INADEQUATE
        return UNRESOLVED
    if hi < margin:
        return ADEQUATE
    if lo > margin:
        return INADEQUATE
    return UNRESOLVED


def framing_benefit(e: Estimate, margin: float, beneficial_sign: int, alpha: float = 0.05,
                    require_margin: bool = True) -> str:
    """EXP02: 'improved' / 'unchanged' / 'worsened' / unresolved.

    With ``require_margin`` the benefit claim needs the interval to exclude effects smaller than a
    stated meaningful effect, and 'unchanged' may only be asserted when the interval excludes a
    meaningful effect in both directions. Without it, a bare significance test decides, and
    non-significance is asserted as 'unchanged'.
    """
    if not e.ok:
        return UNRESOLVED
    lo, hi = (e.lo, e.hi) if beneficial_sign > 0 else (-e.hi, -e.lo)
    if not require_margin:
        if e.p_two_sided < alpha:
            return "improved" if (e.est * beneficial_sign) > 0 else "worsened"
        return "unchanged"
    if lo > margin:
        return "improved"
    if hi < -margin:
        return "worsened"
    if lo > -margin and hi < margin:
        return "unchanged"
    return UNRESOLVED


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm-adjusted rejection decisions, as M5_W004 specifies for the co-primary endpoints."""
    items = sorted(((k, v) for k, v in pvals.items() if np.isfinite(v)), key=lambda kv: kv[1])
    m = len(items)
    out = {k: False for k in pvals}
    for i, (k, p) in enumerate(items):
        if p <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out
