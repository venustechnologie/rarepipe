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

    Derived, not asserted. The cap on the chain to missegregation is still H01-versus-H02. The cap
    on the chain to the intracellular pool moved when a human trial already in the repository was
    connected to it: that step is now human-supported, and what remains is the cell type, not the
    compartment.
    """
    chain = mva_chain()

    to_nad = chain.predict(NIACIN, NAD_CELL)
    assert to_nad.weakest_support is Support.HUMAN_EXPERIMENTAL
    assert to_nad.verdict == "SUPPORTED_IN_HUMANS"

    to_misseg = chain.predict(NIACIN, MISSEG)
    assert to_misseg.verdict == "ASSERTION_ONLY"
    assert to_misseg.weakest_link == f"{BUBR1}->{BUBR1_FN}"
    assert to_misseg.direction == "decrease"
    assert "unresolved" in to_misseg.limiting_scope_note


def test_a_human_supported_step_never_travels_without_the_tissue_it_was_measured_in():
    """The invariant the repair had to respect: human evidence in muscle is not evidence in the
    patient's cells, and the verdict may not appear stripped of the context that bounds it."""
    claim = mva_chain().predict(NIACIN, NAD_CELL)
    assert claim.verdict == "SUPPORTED_IN_HUMANS"
    assert "skeletal muscle" in claim.limiting_scope_note
    assert "not the cell type this case requires" in claim.limiting_scope_note
    assert any("patient-derived cells is unmeasured" in c for c in claim.caveats)
    assert any("nothing here says niacin should be given to anyone" in c for c in claim.caveats)


def test_a_null_result_on_a_shorter_route_stays_visible():
    """The strongest route must not hide a contradicted one to the same target.

    Tested on a constructed chain rather than on the case's own, because the case's refutation was
    withdrawn when its citation turned out not to support it. The property has to survive that; the
    conclusion does not.
    """
    chain = CausalChain(
        chain_id="probe", case_ref="PROBE", nodes=("a", "b", "t"),
        edges=(
            CausalEdge(source="a", target="b", sign=1, mechanism="m",
                       support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                       scope_note="measured"),
            CausalEdge(source="b", target="t", sign=1, mechanism="m",
                       support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                       scope_note="measured"),
            CausalEdge(source="a", target="t", sign=1, mechanism="direct, tested, null",
                       support=Support.CONTRADICTED, evidence_ref="PMID:2",
                       scope_note="the direct route was null"),
        ))
    claim = chain.predict("a", "t")
    assert claim.contradicted_alternatives == ("a -> t",)


def test_withdrawing_a_refutations_only_citation_removes_the_refutation():
    """The scientific invariant, not the historical answer.

    A contradicted verdict that rested on exactly one citation cannot survive that citation being
    withdrawn. The case's direct precursor route is the instance: it is no longer refuted, and it is
    not supported either — what remains is an assertion with no evidence in either direction.
    """
    chain = mva_chain()
    direct = next(e for e in chain.edges if e.source == NIACIN and e.target == BUBR1)
    assert direct.support is Support.ASSERTED_ONLY
    assert direct.evidence_ref is None
    assert mva_chain().predict(NIACIN, BUBR1).contradicted_alternatives == ()
    assert "REPAIR_R1" in direct.caveat, "the withdrawal must point at its own record"


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
    """Every unmeasured rate states its range. The count is not the property; the rule is.

    Asserting a count here would mean that connecting a new piece of evidence, which legitimately
    adds a rate, broke a test about intervals.
    """
    unknown = mva_chain().unknown_parameters()
    assert unknown, "a chain with no unmeasured rate would pass this vacuously"
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

    On a constructed chain, because the case no longer has a falsified route. The verdict is capped
    by the weakest link across *contributing* routes rather than the best one, so an unsupported
    route that adds magnitude cannot ride on a well-supported route that does none of the work.
    """
    chain = CausalChain(
        chain_id="probe", case_ref="PROBE", nodes=("a", "b", "t"),
        edges=(
            CausalEdge(source="a", target="b", sign=1, mechanism="m",
                       support=Support.HUMAN_EXPERIMENTAL, evidence_ref="PMID:1",
                       scope_note="measured",
                       parameter=Parameter(name="k_ab", unit="u", value=1.0,
                                           support=Support.HUMAN_EXPERIMENTAL,
                                           evidence_ref="PMID:1")),
            CausalEdge(source="b", target="t", sign=1, mechanism="m",
                       support=Support.ASSERTED_ONLY, scope_note="asserted",
                       parameter=Parameter(name="k_bt", unit="u", prior=(0.0, 1.0),
                                           support=Support.ASSERTED_ONLY, note="unmeasured")),
            CausalEdge(source="a", target="t", sign=1, mechanism="direct, tested, null",
                       support=Support.CONTRADICTED, evidence_ref="PMID:2",
                       scope_note="the direct route was null",
                       parameter=Parameter(name="k_at", unit="u", value=5.0,
                                           support=Support.CONTRADICTED, evidence_ref="PMID:2")),
        ))
    effect = chain.propagate("a", "t", {p.name: 0.5 for p in chain.unknown_parameters()})

    assert effect.origin == "synthetic"
    assert effect.excluded_contradicted_routes == ("a -> t",)
    assert "a -> t" not in effect.contributing_routes
    assert effect.verdict == "ASSERTION_ONLY", "capped by the contributing route, not the best one"
    assert effect.weakest_link == "b->t"


def test_the_cases_own_propagation_now_carries_the_withdrawn_route_as_an_assertion():
    """What withdrawing the refutation actually did, stated rather than assumed.

    The direct route used to be excluded as falsified. It is now an assertion with no evidence, so
    it contributes and the cap falls to it. Removing a refutation made the result weaker, not
    stronger, which is the point: the system stopped knowing something it never had grounds for.
    """
    chain = mva_chain()
    effect = chain.propagate(NIACIN, BUBR1, {p.name: 0.5 for p in chain.unknown_parameters()})
    assert effect.excluded_contradicted_routes == ()
    assert f"{NIACIN} -> {BUBR1}" in effect.contributing_routes
    assert effect.verdict == "ASSERTION_ONLY"
    assert effect.weakest_link == f"{NIACIN}->{BUBR1}"


def test_a_target_with_no_route_is_not_reported_as_an_effect_of_zero():
    chain = mva_chain()
    effect = chain.propagate(MISSEG, NIACIN, {})
    assert effect.verdict == "NO_ROUTE"
    assert effect.contributing_routes == ()
