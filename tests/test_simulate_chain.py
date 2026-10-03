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


def test_the_engine_and_sensitivity_share_one_propagation_rule():
    """Two propagation rules is worse than one wrong one.

    engine.py took the product along a single best route while sensitivity.py summed every route
    into the target. On niacin -> missegregation they disagreed by a factor of two, which would
    have made every sensitivity index describe a different model than the distribution it was
    meant to explain. Both now delegate to CausalChain.propagate; this fails if either forks again.
    """
    import numpy as np

    from rarepipe.stages.simulate.engine import _evaluate_best_path
    from rarepipe.stages.simulate.sensitivity import _response

    chain = mva_chain()
    values = {p.name: 0.5 for p in chain.unknown_parameters()}

    canonical = chain.propagate(NIACIN, MISSEG, values).magnitude
    assert _response(chain, MISSEG, values) == pytest.approx(canonical)
    matrix = {k: np.full(1, v) for k, v in values.items()}
    assert float(_evaluate_best_path(chain, NIACIN, MISSEG, matrix, 1)[0]) == pytest.approx(
        canonical
    )


def test_propagation_excludes_contradicted_routes_and_caps_on_contributors():
    """A falsified route must carry no magnitude, and support may not be borrowed.

    The verdict is capped by the weakest link across *contributing* routes rather than the best
    one, so an unsupported route that adds magnitude cannot ride on a well-supported route that
    does none of the work.
    """
    chain = mva_chain()
    effect = chain.propagate(NIACIN, MISSEG, {p.name: 0.5 for p in chain.unknown_parameters()})

    assert effect.origin == "synthetic"
    assert effect.excluded_contradicted_routes, "the null direct route should be excluded here"
    assert all("nicotinic_acid_exposure -> bubr1_abundance ->" not in r
               or r in effect.excluded_contradicted_routes
               for r in effect.contributing_routes)
    assert effect.verdict == "ASSERTION_ONLY"
    assert effect.weakest_link == f"{BUBR1}->{BUBR1_FN}"


def test_a_target_with_no_route_is_not_reported_as_an_effect_of_zero():
    chain = mva_chain()
    effect = chain.propagate(MISSEG, NIACIN, {})
    assert effect.verdict == "NO_ROUTE"
    assert effect.contributing_routes == ()
