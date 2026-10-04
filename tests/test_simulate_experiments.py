"""A priority order that reshuffles with the sample size must not be reported as one."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Parameter, Support
from rarepipe.stages.simulate.experiments import (
    ExperimentReport, PriorityExperiment, audit_priors, report,
)
from rarepipe.stages.simulate.mva import MISSEG, mva_chain
from rarepipe.stages.simulate.sensitivity import assess_stability


def test_the_ranking_does_not_survive_doubling_the_sample():
    """convergence_ok was true at every sample size while the top three changed at every one.

    It only checked that the draw count exceeded a floor of 64, which is not convergence. Measured
    properly the ordering is not stable here, and at N=8192 five of six indices cluster within
    0.032 of each other, so no single parameter dominates.
    """
    stability = assess_stability(mva_chain(), target=MISSEG, master_seed=11, draws=512)
    assert stability.order_stable is False
    assert stability.detail


def test_no_experiment_carries_a_rank_while_the_order_is_unstable():
    built = report(MISSEG, draws=512)
    assert built.ordering_is_reportable is False
    assert all(e.position is None for e in built.experiments)
    rendered = built.render()
    assert "UNORDERED" in rendered
    assert "distributed, not dominated" in rendered
    assert "no single most valuable measurement" in rendered


def test_a_report_cannot_claim_ranks_it_has_not_earned():
    """The validator must refuse a hand-built report that asserts an order without stability."""
    built = report(MISSEG, draws=512)
    ranked = PriorityExperiment(
        **{**built.experiments[0].model_dump(), "position": 1},
    )
    with pytest.raises(ValidationError, match="reshuffling order"):
        ExperimentReport(**{**built.model_dump(), "experiments": (ranked,)})


def test_a_wild_type_centred_prior_is_refused():
    """Centring residual_function_fraction on expected wild-type activity assumes H01.

    That is the unresolved question, and the assumption drops the parameter from second to last in
    the ranking, removing it from any priority list.
    """
    chain = mva_chain()
    assert audit_priors(chain).any_prior_encodes_an_answer is False

    edges = []
    for edge in chain.edges:
        if edge.parameter is not None and edge.parameter.name == "residual_function_fraction":
            data = edge.parameter.model_dump()
            data["prior"] = (0.8, 1.2)
            edges.append(CausalEdge(**{**edge.model_dump(), "parameter": Parameter(**data)}))
        else:
            edges.append(edge)
    biased = CausalChain(**{**chain.model_dump(), "edges": tuple(edges)})

    audit = audit_priors(biased)
    assert audit.any_prior_encodes_an_answer is True
    finding = next(f for f in audit.findings if f.parameter == "residual_function_fraction")
    assert finding.encodes_an_answer is True
    assert "assumes H01" in finding.why_it_matters


def test_each_measurement_names_what_it_will_not_settle():
    for row in report(MISSEG, draws=256).experiments:
        assert row.does_not_resolve
        assert row.campaign_question.startswith("Q")


def test_the_report_never_licenses_a_reduced_panel():
    built = report(MISSEG, draws=256)
    assert "not a reduced panel" in built.not_a_recommendation_to_measure_less
    assert "all twelve" in built.endpoints_note
    assert any("none has been contacted" in n for n in built.not_checked)


def test_measurements_are_linked_to_groups_identified_from_public_work():
    """The simulator and the outreach list must point at the same thing."""
    built = report(MISSEG, draws=256)
    nad = next(e for e in built.experiments if e.parameter == "f_blood_to_intracellular")
    assert nad.campaign_question == "Q02"
    assert any("Helsinki" in g or "Oulu" in g for g in nad.candidate_groups), nad.candidate_groups
