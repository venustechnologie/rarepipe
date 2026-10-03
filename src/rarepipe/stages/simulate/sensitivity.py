"""Variance-based global sensitivity over unmeasured causal-chain parameters.

Answers which unknown most determines whether a target moves — i.e. which measurement
would most reduce uncertainty. A simulated ranking is never evidence about a patient:
every result carries origin="synthetic".

Sobol first-order and total indices are estimated from a Saltelli-style design implemented
with numpy only (no SALib). Indices are variance ratios over the assumed priors; they are
not accuracy claims about biology, and a binomial interval does not apply to them.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from rarepipe.stages.simulate.chain import (
    CausalChain,
    Immutable,
    Parameter,
    PredictionClaim,
    Support,
)

# Saltelli base-sample size below which Monte Carlo Sobol figures are not reported as indices.
_MIN_DRAWS_FOR_INDEX = 64
_VARIANCE_FLOOR = 1e-18


class SensitivityIndex(Immutable):
    """One parameter's Sobol figures, with the draw count they were computed from."""

    parameter_name: str
    first_order: float
    total: float
    support_kind: Support
    draws: int = Field(description="Saltelli base sample size N used for this estimate.")
    interval_applies: bool = False
    no_interval_reason: str = (
        "Sobol first-order and total indices are variance ratios from a Saltelli sample; "
        "a binomial confidence interval does not apply to this sampling unit"
    )

    @model_validator(mode="after")
    def _draws_required(self):
        if self.draws < 1:
            raise ValueError("an index must state the draw count it was computed from")
        if self.interval_applies:
            raise ValueError("Sobol indices must not claim a binomial interval")
        if not self.no_interval_reason:
            raise ValueError("when no interval applies, state why")
        return self


class SensitivityRanking(Immutable):
    """Ranked uncertainty list. Synthetic; not a recommendation to drop endpoints."""

    origin: Literal["synthetic"] = "synthetic"
    target: str
    draws: int
    n_parameters: int
    n_model_evaluations: int
    convergence_ok: bool
    convergence_note: str
    ranking: tuple[SensitivityIndex, ...]
    claim: PredictionClaim | None = None
    most_valuable_measurement: str | None = None

    def as_tuples(self) -> list[tuple[str, float, float, Support]]:
        """Ordered (parameter_name, first_order, total, support_kind), highest influence first."""
        return [
            (row.parameter_name, row.first_order, row.total, row.support_kind)
            for row in self.ranking
        ]

    def __iter__(self):
        return iter(self.as_tuples())

    def narrative(self) -> str:
        """Prose generated from this record. Never transcribes a hand-written rate."""
        lines = [
            f"origin={self.origin}",
            (
                f"Global sensitivity of target {self.target!r} over "
                f"{self.n_parameters} unmeasured parameter(s)."
            ),
            (
                f"Saltelli base draws N={self.draws}; "
                f"model evaluations={self.n_model_evaluations} "
                f"(N*(k+2) with k={self.n_parameters})."
            ),
            self.convergence_note,
        ]
        if self.claim is not None:
            lines.append(
                f"Path verdict: {self.claim.verdict}; limiting edge: "
                f"{self.claim.weakest_link} ({self.claim.weakest_support.value})."
            )
        if not self.ranking:
            lines.append(
                "No unmeasured parameters enter the ranking: the list is empty "
                "(not a noise ranking over measured constants)."
            )
        else:
            for i, row in enumerate(self.ranking, start=1):
                if self.convergence_ok:
                    lines.append(
                        f"{i}. {row.parameter_name}: "
                        f"first_order={row.first_order:.6f} (N={row.draws}), "
                        f"total={row.total:.6f} (N={row.draws}), "
                        f"support={row.support_kind.value}"
                    )
                else:
                    lines.append(
                        f"{i}. {row.parameter_name}: provisional Saltelli figures only "
                        f"(not indices; N={row.draws} below minimum "
                        f"{_MIN_DRAWS_FOR_INDEX}), support={row.support_kind.value}"
                    )
        if self.most_valuable_measurement:
            lines.append(self.most_valuable_measurement)
        lines.append(
            "This is a ranked uncertainty list for an assay scientist to cost; "
            "it is not a recommendation to drop any endpoint or measure less."
        )
        return "\n".join(lines)


def rank(
    chain: CausalChain,
    *,
    target: str,
    master_seed: int,
    draws: int,
) -> SensitivityRanking:
    """Sobol ranking of unmeasured parameters for influence on `target`.

    Returns an ordered ranking (highest total-order index first). When every parameter
    is measured, the ranking is explicitly empty.
    """
    if draws < 1:
        raise ValueError("draws must be a positive Saltelli base sample size")
    if target not in chain.nodes:
        raise ValueError(f"target {target!r} is not a node of chain {chain.chain_id!r}")

    unknowns = list(chain.unknown_parameters())
    source = _drive_source(chain, target)
    claim = chain.predict(source, target) if source is not None else None

    if not unknowns:
        return SensitivityRanking(
            target=target,
            draws=draws,
            n_parameters=0,
            n_model_evaluations=0,
            convergence_ok=True,
            convergence_note=(
                f"N={draws} draws requested; ranking is empty because every parameter "
                "on this chain is measured, so there is no unmeasured uncertainty to rank."
            ),
            ranking=(),
            claim=claim,
            most_valuable_measurement=None,
        )

    k = len(unknowns)
    n_eval = draws * (k + 2)
    convergence_ok = draws >= _MIN_DRAWS_FOR_INDEX
    if convergence_ok:
        convergence_note = (
            f"N={draws} Saltelli base draws "
            f"({n_eval} model evaluations): at or above the minimum "
            f"({_MIN_DRAWS_FOR_INDEX}) for reporting first-order and total indices."
        )
    else:
        convergence_note = (
            f"N={draws} Saltelli base draws "
            f"({n_eval} model evaluations): below the minimum "
            f"({_MIN_DRAWS_FOR_INDEX}). An index from too few draws is not an index; "
            "figures below are provisional ordering aids only."
        )

    lows = np.array([p.interval()[0] for p in unknowns], dtype=float)
    highs = np.array([p.interval()[1] for p in unknowns], dtype=float)

    seed_a = chain.seed_for(f"sensitivity|A|{target}", master_seed)
    seed_b = chain.seed_for(f"sensitivity|B|{target}", master_seed)
    if seed_a == seed_b:
        seed_b = chain.seed_for(f"sensitivity|B_alt|{target}", master_seed)
    if seed_a == seed_b:
        raise RuntimeError(
            f"seed collision for sensitivity streams on chain {chain.chain_id!r} "
            f"target={target!r} master_seed={master_seed}"
        )

    rng_a = np.random.default_rng(seed_a)
    rng_b = np.random.default_rng(seed_b)
    A = rng_a.random((draws, k))
    B = rng_b.random((draws, k))

    y_a = _evaluate_matrix(chain, target, unknowns, A, lows, highs)
    y_b = _evaluate_matrix(chain, target, unknowns, B, lows, highs)
    # Jansen estimators need Var(Y); pool A and B for a stabler estimate.
    y_pool = np.concatenate([y_a, y_b])
    var_y = float(np.var(y_pool, ddof=0))

    first_orders = np.zeros(k, dtype=float)
    totals = np.zeros(k, dtype=float)
    if var_y > _VARIANCE_FLOOR:
        for i in range(k):
            ab_i = A.copy()
            ab_i[:, i] = B[:, i]
            y_abi = _evaluate_matrix(chain, target, unknowns, ab_i, lows, highs)
            # Jansen (1999) / Saltelli et al. estimators.
            first_orders[i] = (
                var_y - (0.5 / draws) * float(np.sum((y_b - y_abi) ** 2))
            ) / var_y
            totals[i] = ((0.5 / draws) * float(np.sum((y_a - y_abi) ** 2))) / var_y
    # else: constant response — all indices remain 0

    order = sorted(
        range(k),
        key=lambda i: (-totals[i], -first_orders[i], unknowns[i].name),
    )
    ranking = tuple(
        SensitivityIndex(
            parameter_name=unknowns[i].name,
            first_order=float(first_orders[i]),
            total=float(totals[i]),
            support_kind=unknowns[i].support,
            draws=draws,
        )
        for i in order
    )

    most_valuable = None
    if ranking and convergence_ok and ranking[0].support_kind is Support.ASSERTED_ONLY:
        top = ranking[0]
        most_valuable = (
            f"Most influential parameter {top.parameter_name} is asserted_only "
            f"(total={top.total:.6f} at N={top.draws}): it is the single most valuable "
            "measurement in this chain — highest influence and weakest evidence."
        )

    return SensitivityRanking(
        target=target,
        draws=draws,
        n_parameters=k,
        n_model_evaluations=n_eval,
        convergence_ok=convergence_ok,
        convergence_note=convergence_note,
        ranking=ranking,
        claim=claim,
        most_valuable_measurement=most_valuable,
    )


def _drive_source(chain: CausalChain, target: str) -> str | None:
    """Root that can reach target along non-contradicted edges, else any path source."""
    contradicted = {e.key for e in chain.edges if e.support is Support.CONTRADICTED}
    incoming: dict[str, int] = {n: 0 for n in chain.nodes}
    for edge in chain.edges:
        if edge.key in contradicted:
            continue
        incoming[edge.target] = incoming.get(edge.target, 0) + 1
    roots = [n for n in chain.nodes if incoming.get(n, 0) == 0]
    for root in roots:
        if chain.paths(root, target):
            return root
    for node in chain.nodes:
        if node != target and chain.paths(node, target):
            return node
    return None


def _evaluate_matrix(
    chain: CausalChain,
    target: str,
    params: list[Parameter],
    unit_cube: np.ndarray,
    lows: np.ndarray,
    highs: np.ndarray,
) -> np.ndarray:
    n = unit_cube.shape[0]
    out = np.empty(n, dtype=float)
    names = [p.name for p in params]
    for row in range(n):
        values = {
            names[i]: float(lows[i] + (highs[i] - lows[i]) * unit_cube[row, i])
            for i in range(len(names))
        }
        out[row] = _response(chain, target, values)
    return out


def _response(chain: CausalChain, target: str, values: dict[str, float]) -> float:
    """Signed effect at `target` under unit drive at every root.

    Each non-contradicted edge multiplies upstream state by its parameter (drawn or
    measured) and its sign, then adds into the downstream node. Edges without a
    parameter contribute a factor of 1. Unknowns are taken from `values`; measured
    parameters use their recorded value — never a prior midpoint.
    """
    contradicted = {e.key for e in chain.edges if e.support is Support.CONTRADICTED}
    incoming: dict[str, int] = {n: 0 for n in chain.nodes}
    for edge in chain.edges:
        if edge.key in contradicted:
            continue
        incoming[edge.target] = incoming.get(edge.target, 0) + 1

    state = {n: 0.0 for n in chain.nodes}
    for node in chain.nodes:
        if incoming.get(node, 0) == 0:
            state[node] = 1.0

    remaining = {n: incoming.get(n, 0) for n in chain.nodes}
    ready = [n for n in chain.nodes if remaining[n] == 0]
    seen = 0
    while ready:
        node = ready.pop()
        seen += 1
        for edge in chain.out_edges(node):
            if edge.key in contradicted:
                continue
            mult = 1.0
            if edge.parameter is not None:
                if edge.parameter.value is not None:
                    mult = float(edge.parameter.value)
                else:
                    mult = float(values[edge.parameter.name])
            state[edge.target] += state[node] * mult * edge.sign
            remaining[edge.target] -= 1
            if remaining[edge.target] == 0:
                ready.append(edge.target)
    if seen != len(chain.nodes):
        # Cycle or only-contradicted connectivity: fall back to best-path product.
        return _best_path_product(chain, target, values)
    return float(state[target])


def _best_path_product(
    chain: CausalChain,
    target: str,
    values: dict[str, float],
) -> float:
    """Fallback: product of parameters along the strongest path from a drive source."""
    source = _drive_source(chain, target)
    if source is None:
        return 0.0
    routes = chain.paths(source, target)
    if not routes:
        return 0.0
    from rarepipe.stages.simulate.chain import STRENGTH

    best = max(routes, key=lambda p: int(STRENGTH[p.weakest().support]))
    effect = 1.0
    for edge in best.edges:
        effect *= edge.sign
        if edge.parameter is None:
            continue
        if edge.parameter.value is not None:
            effect *= float(edge.parameter.value)
        else:
            effect *= float(values[edge.parameter.name])
    return float(effect)
