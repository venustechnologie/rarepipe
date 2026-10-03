"""A prediction may not outrun its weakest link."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rarepipe.stages.simulate.chain import (
    CausalChain, CausalEdge, Parameter, Support,
)
from rarepipe.stages.simulate.mva import (
    ANEUPLOIDY, BUBR1, BUBR1_FN, MISSEG, NAD_CELL, NIACIN, mva_chain,
)


def test_an_unknown_parameter_cannot_fall_back_on_a_default():
    with pytest.raises(ValidationError, match="never fall back on a default"):
        Parameter(name="k", unit="x")
    assert Parameter(name="k", unit="x", prior=(0.0, 1.0)).interval() == (0.0, 1.0)


def test_claimed_support_requires_an_evidence_reference():
    with pytest.raises(ValidationError, match="no evidence reference"):
        Parameter(name="k", unit="x", prior=(0, 1), support=Support.HUMAN_EXPERIMENTAL)
    with pytest.raises(ValidationError, match="no evidence reference"):
        CausalEdge(source="a", target="b", sign=1, mechanism="m",
                   support=Support.MODEL_EXPERIMENTAL)


def test_a_substitution_must_say_what_was_actually_measured():
    """DIFFERENT_AGENT without a scope note makes the substitution invisible, which is the exact
    failure this case turns on: the SIRT2 result used NMN, not nicotinic acid."""
    with pytest.raises(ValidationError, match="the substitution is invisible"):
        CausalEdge(source="a", target="b", sign=1, mechanism="m",
                   support=Support.DIFFERENT_AGENT, evidence_ref="PMID:1")


def test_the_mva_chain_breaks_where_the_plan_says_it_breaks():
    """The decisive gap is residual function, not the precursor substitution.

    Derived, not asserted: the chain to missegregation is capped by H01-versus-H02, while the
    chain to intracellular NAD is capped earlier by the whole-blood compartment gap.
    """
    chain = mva_chain()

    to_nad = chain.predict(NIACIN, NAD_CELL)
    assert to_nad.verdict == "CONDITIONAL_ON_UNVERIFIED_SUBSTITUTION"
    assert to_nad.weakest_support is Support.DIFFERENT_COMPARTMENT
    assert "blood NAD was the readout" in to_nad.limiting_scope_note

    to_misseg = chain.predict(NIACIN, MISSEG)
    assert to_misseg.verdict == "ASSERTION_ONLY"
    assert to_misseg.weakest_link == f"{BUBR1}->{BUBR1_FN}"
    assert to_misseg.direction == "decrease"
    assert "unresolved" in to_misseg.limiting_scope_note


def test_a_null_result_on_a_shorter_route_stays_visible():
    """The strongest route must not hide a contradicted one to the same target."""
    claim = mva_chain().predict(NIACIN, BUBR1)
    assert claim.contradicted_alternatives == (f"{NIACIN} -> {BUBR1}",)


def test_adding_assertions_can_never_raise_a_verdict():
    """Chaining unsupported links must not manufacture support."""
    chain = CausalChain(
        chain_id="probe", case_ref="PROBE", nodes=("a", "b", "c"),
        edges=(
            CausalEdge(source="a", target="b", sign=1, mechanism="m",
                       support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                       scope_note="measured"),
            CausalEdge(source="b", target="c", sign=1, mechanism="m",
                       support=Support.ASSERTED_ONLY),
        ),
    )
    assert chain.predict("a", "b").verdict == "SUPPORTED_IN_HUMANS"
    assert chain.predict("a", "c").verdict == "ASSERTION_ONLY"
    assert chain.predict("a", "c").unsupported_links == ("b->c",)


def test_a_prediction_is_synthetic_and_cannot_claim_establishment():
    claim = mva_chain().predict(NIACIN, ANEUPLOIDY)
    assert claim.origin == "synthetic"
    assert "ESTABLISH" not in claim.verdict.upper()
    assert "PROVEN" not in claim.verdict.upper()


def test_every_unmeasured_rate_is_an_explicit_interval():
    """Six rate constants in this chain are unmeasured for this case. Each states its range."""
    unknown = mva_chain().unknown_parameters()
    assert len(unknown) == 6
    for parameter in unknown:
        assert parameter.prior is not None
        assert parameter.value is None


def test_seeding_is_stable_across_processes():
    chain = mva_chain()
    assert chain.seed_for("exp01", 20260930) == chain.seed_for("exp01", 20260930)
    assert chain.seed_for("exp01", 20260930) != chain.seed_for("exp02", 20260930)


def test_an_edge_cannot_use_an_undeclared_node():
    with pytest.raises(ValidationError, match="undeclared node"):
        CausalChain(chain_id="p", case_ref="P", nodes=("a",),
                    edges=(CausalEdge(source="a", target="ghost", sign=1, mechanism="m",
                                      support=Support.ASSERTED_ONLY),))
