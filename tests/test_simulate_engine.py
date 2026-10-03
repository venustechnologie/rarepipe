"""Tests for the Monte Carlo simulation engine over causal chains."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from rarepipe.stages.simulate.chain import (
    CausalChain,
    CausalEdge,
    Parameter,
    Support,
)
from rarepipe.stages.simulate.engine import (
    DirectionalSummary,
    DistributionSummary,
    ParameterDrawSummary,
    SimulationResult,
    compute_wilson_interval,
    run,
)
from rarepipe.stages.simulate.mva import (
    ANEUPLOIDY,
    BUBR1,
    BUBR1_FN,
    DEATH,
    DIVISION,
    K668,
    MISSEG,
    NAD_CELL,
    NIACIN,
    mva_chain,
)

REPO = Path(__file__).resolve().parents[1]


def test_cross_process_determinism():
    """Two runs in separate processes with the same seed must produce byte-identical output."""
    script = textwrap.dedent(
        """
        import json
        from rarepipe.stages.simulate.mva import mva_chain, MISSEG
        from rarepipe.stages.simulate.engine import run

        chain = mva_chain()
        result = run(chain, target=MISSEG, master_seed=20261004, draws=256)
        out = {
            "mean": result.distribution.mean,
            "std": result.distribution.std,
            "median": result.distribution.median,
            "min": result.distribution.min,
            "max": result.distribution.max,
            "p5": result.distribution.p5,
            "p95": result.distribution.p95,
            "fraction": result.directional_summary.fraction,
            "numerator": result.directional_summary.numerator,
            "denominator": result.directional_summary.denominator,
            "wilson": list(result.directional_summary.wilson_interval),
            "params": [
                {
                    "name": p.parameter_name,
                    "mean": p.mean,
                    "std": p.std,
                    "min": p.min,
                    "max": p.max,
                }
                for p in result.parameters
            ],
        }
        print(json.dumps(out, sort_keys=True))
        """
    )
    env1 = {**os.environ, "PYTHONHASHSEED": "42", "PYTHONPATH": str(REPO / "src")}
    env2 = {**os.environ, "PYTHONHASHSEED": "99999", "PYTHONPATH": str(REPO / "src")}

    r1 = subprocess.run(
        [sys.executable, "-c", script],
        env=env1,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    r2 = subprocess.run(
        [sys.executable, "-c", script],
        env=env2,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )

    assert r1.returncode == 0, f"Process 1 failed: {r1.stderr}"
    assert r2.returncode == 0, f"Process 2 failed: {r2.stderr}"
    assert r1.stdout.strip() == r2.stdout.strip(), (
        f"Cross-process output diverged across PYTHONHASHSEED:\n"
        f"P1: {r1.stdout}\nP2: {r2.stdout}"
    )


def test_an_unvalued_parameter_is_never_collapsed_to_a_midpoint():
    """Any rate with value=None is drawn from its prior; midpoint is never an estimate."""
    chain = mva_chain()
    result = run(chain, target=MISSEG, master_seed=20261004, draws=500)

    # 6 unmeasured parameters in mva_chain
    assert len(result.parameters) == 6
    for p in result.parameters:
        assert p.is_measured is False
        assert p.measured_value is None
        low, high = p.interval
        assert low < high
        midpoint = (low + high) / 2.0

        # Draws must have variance and span the interval
        assert p.std > 0.0, f"parameter {p.parameter_name} had zero variance"
        assert p.min < midpoint < p.max, (
            f"parameter {p.parameter_name} draws do not span midpoint: "
            f"min={p.min}, midpoint={midpoint}, max={p.max}"
        )
        assert abs(p.mean - midpoint) > 1e-6 or p.std > 0.0

    # Target distribution must have variance, not a single point estimate
    assert result.distribution.std > 0.0
    assert result.distribution.min < result.distribution.max


def test_sign_propagation():
    """An odd number of negative edges decreases the target; even increases it."""
    chain = mva_chain()

    # 0 negative edges: NIACIN -> NAD_CELL (increase)
    res_nad = run(chain, target=NAD_CELL, master_seed=101, draws=100)
    assert res_nad.claim.direction == "increase"
    assert res_nad.distribution.mean > 0.0
    assert res_nad.directional_summary.fraction == 1.0

    # 1 negative edge: NIACIN -> K668 (SIRT2->K668 has sign -1)
    res_k668 = run(chain, target=K668, master_seed=101, draws=100)
    assert res_k668.claim.direction == "decrease"
    assert res_k668.distribution.mean < 0.0
    assert res_k668.directional_summary.fraction == 1.0

    # 2 negative edges: NIACIN -> BUBR1 (SIRT2->K668 (-1) and K668->BUBR1 (-1))
    res_bubr1 = run(chain, target=BUBR1, master_seed=101, draws=100)
    assert res_bubr1.claim.direction == "increase"
    assert res_bubr1.distribution.mean > 0.0
    assert res_bubr1.directional_summary.fraction == 1.0

    # 3 negative edges: NIACIN -> MISSEG (CHECKPOINT->MISSEG (-1) and ALIGNMENT->MISSEG (-1))
    res_misseg = run(chain, target=MISSEG, master_seed=101, draws=100)
    assert res_misseg.claim.direction == "decrease"
    assert res_misseg.distribution.mean < 0.0
    assert res_misseg.directional_summary.fraction == 1.0

    # 4 negative edges: NIACIN -> DIVISION (DEATH->DIVISION (-1))
    res_div = run(chain, target=DIVISION, master_seed=101, draws=100)
    assert res_div.claim.direction == "increase"
    assert res_div.distribution.mean > 0.0
    assert res_div.directional_summary.fraction == 1.0


def test_synthetic_probe_chain_sign_propagation():
    """Explicit probe chain verifying that flipping edge sign flips target response."""
    chain_pos = CausalChain(
        chain_id="probe_pos",
        case_ref="PROBE",
        nodes=("n1", "n2", "n3"),
        edges=(
            CausalEdge(
                source="n1", target="n2", sign=1, mechanism="m1",
                support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                scope_note="measured",
                parameter=Parameter(name="k1", unit="u", prior=(1.0, 2.0),
                                    support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1"),
            ),
            CausalEdge(
                source="n2", target="n3", sign=1, mechanism="m2",
                support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                scope_note="measured",
                parameter=Parameter(name="k2", unit="u", prior=(1.0, 2.0),
                                    support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1"),
            ),
        ),
    )
    res_pos = run(chain_pos, target="n3", master_seed=1, draws=50)
    assert res_pos.claim.direction == "increase"
    assert res_pos.distribution.mean > 0.0

    chain_neg = CausalChain(
        chain_id="probe_neg",
        case_ref="PROBE",
        nodes=("n1", "n2", "n3"),
        edges=(
            CausalEdge(
                source="n1", target="n2", sign=1, mechanism="m1",
                support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                scope_note="measured",
                parameter=Parameter(name="k1", unit="u", prior=(1.0, 2.0),
                                    support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1"),
            ),
            CausalEdge(
                source="n2", target="n3", sign=-1, mechanism="m2",
                support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                scope_note="measured",
                parameter=Parameter(name="k2", unit="u", prior=(1.0, 2.0),
                                    support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1"),
            ),
        ),
    )
    res_neg = run(chain_neg, target="n3", master_seed=1, draws=50)
    assert res_neg.claim.direction == "decrease"
    assert res_neg.distribution.mean < 0.0


def test_verdict_travels_with_the_distribution():
    """The distribution carries the verdict and limiting edge, printed adjacent to any number."""
    chain = mva_chain()
    result = run(chain, target=MISSEG, master_seed=20261004, draws=100)

    # Path to missegregation is capped at ASSERTION_ONLY via bubr1_abundance->bubr1_residual_function
    expected_verdict = "ASSERTION_ONLY"
    expected_limiting_edge = f"{BUBR1}->{BUBR1_FN}"

    assert result.verdict == expected_verdict
    assert result.limiting_edge == expected_limiting_edge
    assert result.distribution.verdict == expected_verdict
    assert result.distribution.limiting_edge == expected_limiting_edge
    assert result.directional_summary.verdict == expected_verdict
    assert result.directional_summary.limiting_edge == expected_limiting_edge

    rendered = result.render()
    cap_tag = f"[CAP: {expected_verdict} via {expected_limiting_edge}]"

    # The cap tag must appear in the rendered output
    assert cap_tag in rendered

    # Every distribution metric line must include the cap
    for metric_name in ("Mean:", "Median:", "Std:", "Min:", "Max:", "Q05:", "Q25:", "Q75:", "Q95:"):
        line = next(line for line in rendered.splitlines() if metric_name in line)
        assert cap_tag in line, f"metric {metric_name} was printed without its cap: {line}"

    # Directional consistency must carry the cap
    dir_line = next(line for line in rendered.splitlines() if "Fraction:" in line)
    assert cap_tag in dir_line


def test_contradicted_path_refuses_to_report_favourable():
    """A run against a chain whose path is CONTRADICTED refuses to report direction as favourable."""
    contra_chain = CausalChain(
        chain_id="contra_probe_v1",
        case_ref="PROBE",
        nodes=("source_a", "target_b"),
        edges=(
            CausalEdge(
                source="source_a",
                target="target_b",
                sign=1,
                mechanism="direct test that yielded null",
                support=Support.CONTRADICTED,
                evidence_ref="PMID:42543917",
                scope_note="refuted direct effect",
                parameter=Parameter(
                    name="k_contra",
                    unit="fold",
                    prior=(1.0, 2.0),
                    support=Support.CONTRADICTED,
                    evidence_ref="PMID:42543917",
                ),
            ),
        ),
    )

    result = run(contra_chain, target="target_b", master_seed=777, draws=100)

    # Claim and result must show CONTRADICTED_ON_PATH
    assert result.claim.verdict == "CONTRADICTED_ON_PATH"
    assert result.verdict == "CONTRADICTED_ON_PATH"
    assert result.limiting_support is Support.CONTRADICTED

    # Favourable reporting is refused
    assert result.is_favourable is False
    assert result.favourable is False
    assert "refuse" in result.favourable_note.lower()

    # Querying favourable direction explicitly raises an error
    with pytest.raises(ValueError, match="Refuses to report direction as favourable"):
        result.direction_is_favourable()

    # Renderer states the refusal
    rendered = result.render()
    assert "refuses to report direction as favourable" in rendered.lower()


def test_directional_fraction_and_wilson_interval():
    """Fraction carries numerator, denominator, and valid Wilson confidence bounds."""
    chain = mva_chain()
    result = run(chain, target=ANEUPLOIDY, master_seed=20261004, draws=200)

    ds = result.directional_summary
    assert ds.predicted_direction == "decrease"
    assert ds.denominator == 200
    assert 0 <= ds.numerator <= 200
    assert ds.fraction == ds.numerator / 200.0

    low, high = ds.wilson_interval
    assert 0.0 <= low <= high <= 1.0
    assert low <= ds.fraction <= high

    # Interval text explicitly states it is a property of assumed priors, not the child
    assert "assumed parameter intervals" in ds.note
    assert "not a probability about the child" in ds.note


def test_compute_wilson_interval_edge_cases():
    """Wilson interval handles zero and full bounds properly."""
    low_0, high_0 = compute_wilson_interval(0, 100)
    assert low_0 == 0.0
    assert 0.0 < high_0 < 0.05

    low_all, high_all = compute_wilson_interval(100, 100)
    assert 0.95 < low_all < 1.0
    assert high_all == 1.0

    # 0 denominator
    assert compute_wilson_interval(0, 0) == (0.0, 0.0)


def test_result_origin_is_synthetic_and_immutable():
    """Origin is synthetic, prediction claim is attached verbatim, and record is frozen."""
    chain = mva_chain()
    result = run(chain, target=MISSEG, master_seed=42, draws=50)

    assert result.origin == "synthetic"
    assert result.claim.origin == "synthetic"

    # Prediction claim attached verbatim
    direct_claim = chain.predict(NIACIN, MISSEG)
    assert result.claim == direct_claim

    # Record immutability
    with pytest.raises(ValidationError):
        result.draws = 999  # type: ignore[misc]


def test_invalid_parameters_rejected():
    """Engine refuses invalid draw counts and undeclared nodes."""
    chain = mva_chain()
    with pytest.raises(ValueError, match="positive"):
        run(chain, target=MISSEG, master_seed=1, draws=0)

    with pytest.raises(ValueError, match="positive"):
        run(chain, target=MISSEG, master_seed=1, draws=-10)

    with pytest.raises(ValueError, match="not a node"):
        run(chain, target="nonexistent_endpoint", master_seed=1, draws=100)
