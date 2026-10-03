"""Monte Carlo simulation engine over causal chains.

Propagates parameter uncertainty from explicit priors through causal chains to report
distributions rather than point estimates. Every simulated result is synthetic:
a simulated result can never become evidence about a patient.

Key invariants:
- A prediction inherits the weakest link on its path: distributions and directional
  fractions carry their verdict and limiting edge. A number without its cap is not
  a result.
- An unknown quantity is drawn from its stated prior interval; no midpoint is ever
  substituted as an estimate.
- Stream seeding uses `chain.seed_for()` (crc32), guaranteeing byte-identical numeric
  reproducibility across separate processes regardless of PYTHONHASHSEED.
- Sign propagation: an odd number of negative edges decreases its target.
- A contradicted path refuses to report any direction as favourable.
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
import scipy.stats
from pydantic import Field, model_validator

from rarepipe.stages.simulate.chain import (
    CausalChain,
    CausalEdge,
    Immutable,
    Parameter,
    PredictionClaim,
    Support,
)


def compute_wilson_interval(
    numerator: int,
    denominator: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion."""
    if denominator <= 0:
        return (0.0, 0.0)
    z = float(scipy.stats.norm.ppf(1.0 - (1.0 - confidence) / 2.0))
    p = numerator / denominator
    n = float(denominator)
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    spread = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    lower = 0.0 if numerator == 0 else max(0.0, float(center - spread))
    upper = 1.0 if numerator == denominator else min(1.0, float(center + spread))
    return (lower, upper)


class ParameterDrawSummary(Immutable):
    """Summary of parameter draws across Monte Carlo iterations."""

    parameter_name: str
    interval: tuple[float, float]
    support: Support
    draws: int
    mean: float
    std: float
    min: float
    max: float
    is_measured: bool = False
    measured_value: float | None = None

    @model_validator(mode="after")
    def _validate_summary(self):
        if self.draws < 1:
            raise ValueError("draws must be positive")
        if self.interval[0] > self.interval[1]:
            raise ValueError(f"parameter {self.parameter_name!r} has an inverted interval")
        return self


class DistributionSummary(Immutable):
    """Output distribution for a target node, carrying its evidence cap."""

    target: str
    draws: int
    mean: float
    std: float
    median: float
    p5: float
    p25: float
    p75: float
    p95: float
    min: float
    max: float
    verdict: str
    limiting_edge: str
    limiting_support: Support
    values: tuple[float, ...] = ()

    @model_validator(mode="after")
    def _validate_cap(self):
        if not self.verdict:
            raise ValueError("distribution must carry a path verdict")
        if not self.limiting_edge:
            raise ValueError("distribution must carry its limiting edge")
        return self

    def format_capped(self, value: float) -> str:
        """Format a numeric value with its evidence cap."""
        return f"{value:.6f} [CAP: {self.verdict} via {self.limiting_edge}]"


class DirectionalSummary(Immutable):
    """Fraction of draws in which target moved in predicted direction."""

    predicted_direction: Literal["increase", "decrease"]
    numerator: int
    denominator: int
    fraction: float
    wilson_interval: tuple[float, float]
    confidence: float = 0.95
    verdict: str
    limiting_edge: str
    limiting_support: Support
    note: str = (
        "This fraction is a property of the assumed parameter intervals and prior distributions, "
        "not a probability about the child or a clinical response rate."
    )

    @model_validator(mode="after")
    def _validate_counts(self):
        if self.denominator < 1:
            raise ValueError("denominator must be at least 1")
        if self.numerator < 0 or self.numerator > self.denominator:
            raise ValueError("numerator must be between 0 and denominator")
        return self


class SimulationResult(Immutable):
    """Immutable record of a Monte Carlo run over a causal chain."""

    origin: Literal["synthetic"] = "synthetic"
    chain_id: str
    target: str
    source: str
    master_seed: int
    draws: int
    verdict: str
    limiting_edge: str
    limiting_support: Support
    claim: PredictionClaim
    parameters: tuple[ParameterDrawSummary, ...]
    distribution: DistributionSummary
    directional_summary: DirectionalSummary
    is_favourable: bool = False
    favourable_note: str = ""

    @property
    def favourable(self) -> bool:
        """Alias for is_favourable."""
        return self.is_favourable

    def direction_is_favourable(self) -> bool:
        """Query whether the predicted direction is favourable.

        Refuses if the path is contradicted by evidence.
        """
        if (
            self.claim.weakest_support is Support.CONTRADICTED
            or self.verdict == "CONTRADICTED_ON_PATH"
        ):
            raise ValueError(
                f"Refuses to report direction as favourable: path is {self.verdict} "
                f"(limiting edge: {self.limiting_edge})"
            )
        return self.is_favourable

    def render(self) -> str:
        """Render distribution and directional figures with verdict caps adjacent to every number."""
        cap_tag = f"[CAP: {self.verdict} via {self.limiting_edge}]"
        lines = [
            f"=== Simulation Result ({self.origin}) ===",
            f"Chain: {self.chain_id} | Source: {self.source} -> Target: {self.target}",
            f"Path Verdict: {self.verdict} | Limiting Edge: {self.limiting_edge} ({self.limiting_support.value})",
            f"Master Seed: {self.master_seed} | Draws: {self.draws}",
            "",
            f"Output Distribution for {self.target} {cap_tag}:",
            f"  Mean:   {self.distribution.mean:+.6f} {cap_tag}",
            f"  Median: {self.distribution.median:+.6f} {cap_tag}",
            f"  Std:    {self.distribution.std:.6f} {cap_tag}",
            f"  Min:    {self.distribution.min:+.6f} {cap_tag}",
            f"  Max:    {self.distribution.max:+.6f} {cap_tag}",
            f"  Q05:    {self.distribution.p5:+.6f} {cap_tag}",
            f"  Q25:    {self.distribution.p25:+.6f} {cap_tag}",
            f"  Q75:    {self.distribution.p75:+.6f} {cap_tag}",
            f"  Q95:    {self.distribution.p95:+.6f} {cap_tag}",
            "",
            f"Directional Consistency {cap_tag}:",
            f"  Predicted Direction: {self.directional_summary.predicted_direction}",
            f"  Draws Moving in Predicted Direction: {self.directional_summary.numerator} / {self.directional_summary.denominator} {cap_tag}",
            f"  Fraction: {self.directional_summary.fraction:.6f} {cap_tag}",
            f"  {int(self.directional_summary.confidence * 100)}% Wilson Interval: "
            f"[{self.directional_summary.wilson_interval[0]:.6f}, {self.directional_summary.wilson_interval[1]:.6f}] {cap_tag}",
            f"  Note: {self.directional_summary.note}",
            "",
            "Parameter Draws Summary:",
        ]
        for p in self.parameters:
            if p.is_measured:
                lines.append(
                    f"  {p.parameter_name} (measured: {p.measured_value:.6f}) "
                    f"support={p.support.value} {cap_tag}"
                )
            else:
                lines.append(
                    f"  {p.parameter_name} prior={p.interval} support={p.support.value}: "
                    f"mean={p.mean:.6f} std={p.std:.6f} min={p.min:.6f} max={p.max:.6f} {cap_tag}"
                )
        if self.favourable_note:
            lines.append(f"\nFavourable Assessment: {self.favourable_note}")
        return "\n".join(lines)

    def narrative(self) -> str:
        """Generated prose narrative from this record."""
        return self.render()


def _drive_source(chain: CausalChain, target: str) -> str | None:
    """Find root node that can reach target along non-contradicted edges, else any path source."""
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


def _evaluate_best_path(
    chain: CausalChain,
    source: str,
    target: str,
    draws_matrix: dict[str, np.ndarray],
    draws: int,
) -> np.ndarray:
    """Propagate every draw through the chain's single canonical rule.

    This took the product along one best route while sensitivity.py summed all routes into the
    target; the two disagreed by a factor of two on niacin -> missegregation. Both now call
    CausalChain.propagate, so a sensitivity index describes this distribution rather than a
    different model.
    """
    names = list(draws_matrix)
    effect = np.empty(draws, dtype=float)
    for i in range(draws):
        values = {name: float(draws_matrix[name][i]) for name in names}
        effect[i] = chain.propagate(source, target, values).magnitude
    return effect


def run(
    chain: CausalChain,
    *,
    target: str,
    master_seed: int,
    draws: int,
    source: str | None = None,
) -> SimulationResult:
    """Propagate parameter uncertainty through causal chain to target.

    Draws parameters with value=None from their prior intervals, seeds all RNG streams
    via chain.seed_for(), propagates edge signs, and reports distributions and directional
    fractions carrying verdict and limiting edge caps.
    """
    if draws < 1:
        raise ValueError("draws must be a positive integer")
    if target not in chain.nodes:
        raise ValueError(f"target {target!r} is not a node of chain {chain.chain_id!r}")

    resolved_source = source if source is not None else _drive_source(chain, target)
    if resolved_source is None:
        raise ValueError(f"no path found reaching target {target!r} in chain {chain.chain_id!r}")
    if resolved_source not in chain.nodes:
        raise ValueError(f"source {resolved_source!r} is not a node of chain {chain.chain_id!r}")

    claim = chain.predict(resolved_source, target)
    if claim is None:
        raise ValueError(f"no path from {resolved_source!r} to {target!r} in chain {chain.chain_id!r}")

    # Collect parameters across edges
    seen_params: dict[str, Parameter] = {}
    for edge in chain.edges:
        if edge.parameter is not None and edge.parameter.name not in seen_params:
            seen_params[edge.parameter.name] = edge.parameter

    draws_matrix: dict[str, np.ndarray] = {}
    param_summaries: list[ParameterDrawSummary] = []
    used_seeds: dict[str, int] = {}

    for name, param in seen_params.items():
        if param.value is not None:
            val = float(param.value)
            draws_matrix[name] = np.full(draws, val, dtype=float)
            param_summaries.append(
                ParameterDrawSummary(
                    parameter_name=name,
                    interval=param.interval(),
                    support=param.support,
                    draws=draws,
                    mean=val,
                    std=0.0,
                    min=val,
                    max=val,
                    is_measured=True,
                    measured_value=val,
                )
            )
        else:
            seed_label = f"engine|param|{name}"
            seed = chain.seed_for(seed_label, master_seed)
            if seed in used_seeds.values():
                seed = chain.seed_for(f"engine|param_alt|{name}", master_seed)
            used_seeds[name] = seed

            rng = np.random.default_rng(seed)
            low, high = param.interval()
            sampled = rng.uniform(low, high, size=draws)
            draws_matrix[name] = sampled
            param_summaries.append(
                ParameterDrawSummary(
                    parameter_name=name,
                    interval=(low, high),
                    support=param.support,
                    draws=draws,
                    mean=float(np.mean(sampled)),
                    std=float(np.std(sampled)),
                    min=float(np.min(sampled)),
                    max=float(np.max(sampled)),
                    is_measured=False,
                )
            )

    # Sort param summaries alphabetically by name for consistency
    param_summaries.sort(key=lambda p: p.parameter_name)

    # Propagate across active non-contradicted DAG paths
    all_paths = chain.paths(resolved_source, target)
    non_contra_paths = [
        p for p in all_paths
        if not any(e.support is Support.CONTRADICTED for e in p.edges)
    ]

    if non_contra_paths:
        active_nodes: set[str] = {resolved_source}
        for p in non_contra_paths:
            active_nodes.update(p.nodes)

        active_edges = [
            e for e in chain.edges
            if e.source in active_nodes
            and e.target in active_nodes
            and e.support is not Support.CONTRADICTED
        ]

        incoming = {n: 0 for n in active_nodes}
        for e in active_edges:
            incoming[e.target] += 1

        state: dict[str, np.ndarray] = {n: np.zeros(draws, dtype=float) for n in active_nodes}
        state[resolved_source] = np.ones(draws, dtype=float)

        ready = [n for n in active_nodes if incoming[n] == 0]
        remaining = dict(incoming)
        seen = 0
        while ready:
            node = ready.pop(0)
            seen += 1
            for edge in chain.out_edges(node):
                if edge.target not in active_nodes or edge.support is Support.CONTRADICTED:
                    continue
                mult = draws_matrix[edge.parameter.name] if edge.parameter is not None else 1.0
                state[edge.target] += state[node] * mult * edge.sign
                remaining[edge.target] -= 1
                if remaining[edge.target] == 0:
                    ready.append(edge.target)

        if seen == len(active_nodes):
            target_values = state[target]
        else:
            target_values = _evaluate_best_path(chain, resolved_source, target, draws_matrix, draws)
    else:
        target_values = _evaluate_best_path(chain, resolved_source, target, draws_matrix, draws)

    # Output distribution summary
    dist_summary = DistributionSummary(
        target=target,
        draws=draws,
        mean=float(np.mean(target_values)),
        std=float(np.std(target_values)),
        median=float(np.median(target_values)),
        p5=float(np.percentile(target_values, 5)),
        p25=float(np.percentile(target_values, 25)),
        p75=float(np.percentile(target_values, 75)),
        p95=float(np.percentile(target_values, 95)),
        min=float(np.min(target_values)),
        max=float(np.max(target_values)),
        verdict=claim.verdict,
        limiting_edge=claim.weakest_link,
        limiting_support=claim.weakest_support,
        values=tuple(float(v) for v in target_values),
    )

    # Directional consistency
    if claim.direction == "increase":
        numerator = int(np.sum(target_values > 0))
    else:
        numerator = int(np.sum(target_values < 0))

    fraction = float(numerator / draws)
    wilson_interval = compute_wilson_interval(numerator, draws, confidence=0.95)

    dir_summary = DirectionalSummary(
        predicted_direction=claim.direction,
        numerator=numerator,
        denominator=draws,
        fraction=fraction,
        wilson_interval=wilson_interval,
        confidence=0.95,
        verdict=claim.verdict,
        limiting_edge=claim.weakest_link,
        limiting_support=claim.weakest_support,
    )

    # Favourable assessment: contradicted paths REFUSE to report favourable
    is_contradicted = (
        claim.weakest_support is Support.CONTRADICTED
        or claim.verdict == "CONTRADICTED_ON_PATH"
    )
    if is_contradicted:
        is_favourable = False
        favourable_note = (
            f"Refuses to report direction as favourable: path verdict is {claim.verdict} "
            f"(limiting edge: {claim.weakest_link}). Evidence contradicts this path."
        )
    elif fraction > 0.5:
        is_favourable = True
        favourable_note = (
            f"Target consistently moved in predicted direction '{claim.direction}' in "
            f"{numerator}/{draws} draws ({fraction:.2%}). Path verdict: {claim.verdict}."
        )
    else:
        is_favourable = False
        favourable_note = (
            f"Target did not move in predicted direction '{claim.direction}' in majority "
            f"of draws ({numerator}/{draws} draws, {fraction:.2%})."
        )

    return SimulationResult(
        chain_id=chain.chain_id,
        target=target,
        source=resolved_source,
        master_seed=master_seed,
        draws=draws,
        verdict=claim.verdict,
        limiting_edge=claim.weakest_link,
        limiting_support=claim.weakest_support,
        claim=claim,
        parameters=tuple(param_summaries),
        distribution=dist_summary,
        directional_summary=dir_summary,
        is_favourable=is_favourable,
        favourable_note=favourable_note,
    )
