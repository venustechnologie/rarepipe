"""Global sensitivity ranks unmeasured parameters; measured chains yield an empty list."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Parameter, Support
from rarepipe.stages.simulate.sensitivity import (
    SensitivityRanking,
    rank,
)

REPO = Path(__file__).resolve().parents[1]


def _dominant_chain() -> CausalChain:
    """Two unknowns: one wide asserted gap, one narrow measured-support factor."""
    return CausalChain(
        chain_id="sens_dominant_v1",
        case_ref="PROBE",
        nodes=("src", "mid", "tgt"),
        edges=(
            CausalEdge(
                source="src", target="mid", sign=1, mechanism="dominant unknown",
                support=Support.ASSERTED_ONLY,
                parameter=Parameter(
                    name="k_dominant", unit="relative",
                    prior=(0.0, 10.0), support=Support.ASSERTED_ONLY,
                    note="wide unmeasured interval",
                ),
            ),
            CausalEdge(
                source="mid", target="tgt", sign=1, mechanism="weak nuisance",
                support=Support.MODEL_EXPERIMENTAL, evidence_ref="PMID:1",
                scope_note="model system",
                parameter=Parameter(
                    name="k_weak", unit="relative",
                    prior=(0.9, 1.1), support=Support.MODEL_EXPERIMENTAL,
                    evidence_ref="PMID:1",
                    note="narrow interval",
                ),
            ),
        ),
    )


def _all_measured_chain() -> CausalChain:
    return CausalChain(
        chain_id="sens_measured_v1",
        case_ref="PROBE",
        nodes=("a", "b"),
        edges=(
            CausalEdge(
                source="a", target="b", sign=1, mechanism="known",
                support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:2",
                scope_note="measured",
                parameter=Parameter(
                    name="k_known", unit="relative", value=1.5,
                    support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:2",
                ),
            ),
        ),
    )


def test_dominant_unmeasured_parameter_ranks_first():
    result = rank(_dominant_chain(), target="tgt", master_seed=20261003, draws=128)
    tuples = result.as_tuples()
    assert tuples, "expected a non-empty ranking over unmeasured parameters"
    assert tuples[0][0] == "k_dominant"
    assert tuples[0][3] is Support.ASSERTED_ONLY
    # Total-order influence of the wide parameter must exceed the narrow nuisance.
    assert tuples[0][2] > tuples[1][2]


def test_support_kind_travels_with_the_ranking():
    result = rank(_dominant_chain(), target="tgt", master_seed=7, draws=128)
    by_name = {name: support for name, _, _, support in result}
    assert by_name["k_dominant"] is Support.ASSERTED_ONLY
    assert by_name["k_weak"] is Support.MODEL_EXPERIMENTAL
    assert result.most_valuable_measurement is not None
    assert "k_dominant" in result.most_valuable_measurement
    assert "asserted_only" in result.most_valuable_measurement
    assert "most valuable measurement" in result.most_valuable_measurement
    prose = result.narrative()
    assert "not a recommendation to drop" in prose
    assert "N=128" in prose


def test_indices_state_draw_count_and_refuse_too_few_draws():
    ok = rank(_dominant_chain(), target="tgt", master_seed=1, draws=64)
    assert ok.convergence_ok is True
    assert all(row.draws == 64 for row in ok.ranking)
    assert all(row.interval_applies is False for row in ok.ranking)
    assert all(row.no_interval_reason for row in ok.ranking)

    thin = rank(_dominant_chain(), target="tgt", master_seed=1, draws=8)
    assert thin.convergence_ok is False
    assert "not an index" in thin.convergence_note
    assert thin.most_valuable_measurement is None
    assert "provisional" in thin.narrative()


def test_all_measured_chain_yields_explicitly_empty_ranking():
    result = rank(_all_measured_chain(), target="b", master_seed=99, draws=128)
    assert isinstance(result, SensitivityRanking)
    assert result.ranking == ()
    assert result.as_tuples() == []
    assert list(result) == []
    assert result.n_parameters == 0
    assert result.n_model_evaluations == 0
    assert "empty" in result.convergence_note.lower()
    assert "measured" in result.narrative().lower()


def test_result_is_synthetic_and_carries_path_cap():
    result = rank(_dominant_chain(), target="tgt", master_seed=3, draws=64)
    assert result.origin == "synthetic"
    assert result.claim is not None
    assert result.claim.origin == "synthetic"
    assert result.claim.verdict == "ASSERTION_ONLY"
    assert result.claim.weakest_link == "src->mid"
    narrative = result.narrative()
    assert "ASSERTION_ONLY" in narrative
    assert "src->mid" in narrative


def test_indices_are_reproducible_across_processes():
    """PYTHONHASHSEED must not change Saltelli output; seeding uses zlib.crc32."""
    script = textwrap.dedent(
        """
        import json
        from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Parameter, Support
        from rarepipe.stages.simulate.sensitivity import rank

        chain = CausalChain(
            chain_id="sens_dominant_v1",
            case_ref="PROBE",
            nodes=("src", "mid", "tgt"),
            edges=(
                CausalEdge(
                    source="src", target="mid", sign=1, mechanism="dominant unknown",
                    support=Support.ASSERTED_ONLY,
                    parameter=Parameter(
                        name="k_dominant", unit="relative",
                        prior=(0.0, 10.0), support=Support.ASSERTED_ONLY,
                    ),
                ),
                CausalEdge(
                    source="mid", target="tgt", sign=1, mechanism="weak nuisance",
                    support=Support.MODEL_EXPERIMENTAL, evidence_ref="PMID:1",
                    scope_note="model system",
                    parameter=Parameter(
                        name="k_weak", unit="relative",
                        prior=(0.9, 1.1), support=Support.MODEL_EXPERIMENTAL,
                        evidence_ref="PMID:1",
                    ),
                ),
            ),
        )
        result = rank(chain, target="tgt", master_seed=20261003, draws=64)
        print(json.dumps(result.as_tuples()))
        """
    )
    env1 = {**os.environ, "PYTHONHASHSEED": "1", "PYTHONPATH": str(REPO / "src")}
    env2 = {**os.environ, "PYTHONHASHSEED": "2", "PYTHONPATH": str(REPO / "src")}
    r1 = subprocess.run(
        [sys.executable, "-c", script],
        env=env1, cwd=str(REPO), capture_output=True, text=True, check=False,
    )
    r2 = subprocess.run(
        [sys.executable, "-c", script],
        env=env2, cwd=str(REPO), capture_output=True, text=True, check=False,
    )
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    assert r1.stdout.strip() == r2.stdout.strip()
    assert "k_dominant" in r1.stdout


def test_unknown_target_is_rejected():
    with pytest.raises(ValueError, match="not a node"):
        rank(_dominant_chain(), target="ghost", master_seed=1, draws=64)
