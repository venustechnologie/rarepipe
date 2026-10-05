"""The validation suite must be able to fail.

It reproduced 6 of 6 on its first run, which is the shape of a test that cannot fail: the chain and
the case list were built from the same source material, so agreement proves little on its own.
These are negative controls — each mutates the chain in a way the suite is supposed to catch.
"""
from __future__ import annotations

from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Support
from rarepipe.stages.simulate.mva import (
    BUBR1, K668, NIACIN, NAD_BLOOD, SIRT2, mva_chain,
)
from rarepipe.stages.simulate.validate import published_behaviours, validate


NAD_CELL_NODE = "nad_intracellular"


def _replace(chain: CausalChain, key: str, **changes) -> CausalChain:
    edges = []
    for edge in chain.edges:
        if edge.key == key:
            edges.append(CausalEdge(**{**edge.model_dump(), **changes}))
        else:
            edges.append(edge)
    return CausalChain(**{**chain.model_dump(), "edges": tuple(edges)})


def test_the_real_chain_reproduces_every_representable_case():
    report = validate()
    assert report.total == len(published_behaviours())
    assert report.reproduced == report.representable
    assert all(r.outcome == "REPRODUCED" for r in report.results)


def test_over_claiming_a_source_is_caught():
    """The decisive check: getting the direction right by over-claiming is not validation.

    SIRT2 -> K668 is `different_agent` because the supporting work used NMN. Relabel it as
    human_experimental and the direction still agrees, so a direction-only suite would pass it.
    """
    chain = _replace(mva_chain(), f"{SIRT2}->{K668}",
                     support=Support.HUMAN_EXPERIMENTAL, scope_note="relabelled for this test")
    report = validate(chain)
    sirt = next(r for r in report.results
                if r.case_id == "SIRT01_sirt2_deacetylation_stabilises_bubr1")
    assert sirt.outcome == "OVER_CLAIMS_ITS_SOURCE"
    assert sirt.chain_direction == "increase", "the direction still agrees — that is the point"
    assert report.reproduced < report.representable


def test_a_flipped_direction_is_caught():
    chain = _replace(mva_chain(), f"{NIACIN}->{NAD_BLOOD}", sign=-1)
    report = validate(chain)
    nad = next(r for r in report.results if r.case_id == "NAD01_niacin_raises_circulating_nad")
    assert nad.outcome == "WRONG_DIRECTION"
    assert nad.chain_direction == "decrease"


def test_a_chain_claiming_more_than_its_source_is_caught():
    """The invariant the retired null case used to carry.

    That case validated the chain against a published null, and the citation carrying the null does
    not report one, so the benchmark was testing a behaviour nobody published. The property it was
    protecting — a chain may not claim more than its source entitles — is tested here on a case
    whose source does exist.
    """
    chain = _replace(mva_chain(), f"{NAD_BLOOD}->{NAD_CELL_NODE}",
                     support=Support.HUMAN_EXPERIMENTAL, scope_note="relabelled for this test")
    report = validate(chain)
    case = next(r for r in report.results
                if r.case_id == "NAD02_circulating_nad_is_not_intracellular_nad")
    assert case.outcome == "OVER_CLAIMS_ITS_SOURCE"


def test_a_case_outside_the_chain_is_not_counted_as_a_pass_or_a_failure():
    """Mitotic checkpoint dynamics are real, published, and outside this chain entirely."""
    bare = CausalChain(chain_id="bare", case_ref="MVA_001", nodes=(NIACIN,), edges=())
    report = validate(bare)
    assert all(r.outcome == "NOT_REPRESENTABLE" for r in report.results)
    assert report.representable == 0
    assert report.reproduced == 0


def test_the_real_chain_no_longer_rests_on_any_unverified_source():
    """Every citation has been retrieved, so the chain's own unverified labels were repaired."""
    report = validate()
    assert report.unverified_sources == ()
    assert report.reproduced_on_verified_sources == report.reproduced


def test_the_headline_count_does_not_hide_unverified_sources():
    """The invariant, on a supplied case whose source is unverified. The count is not the property.

    Asserting that the real chain *has* unverified sources would mean that verifying them broke a
    test about surfacing them.
    """
    from rarepipe.stages.simulate.validate import PublishedBehaviour
    cases = (*published_behaviours(), PublishedBehaviour(
        case_id="PROBE_unverified",
        source="PMID:00000003 (UNVERIFIED: no retrieval record)",
        reported="nicotinic acid raised whole-blood NAD",
        scope="a source with no retrieval record",
        start=NIACIN, end=NAD_BLOOD, expected_direction="increase",
        entitled_to_at_most=Support.HUMAN_EXPERIMENTAL))
    report = validate(cases=cases)
    assert report.unverified_sources
    assert report.reproduced_on_verified_sources < report.reproduced
    rendered = report.render()
    assert "cannot verify" in rendered
    assert "UNVERIFIED SOURCE" in rendered


def test_the_report_states_what_it_does_not_check():
    report = validate()
    joined = " ".join(report.not_checked)
    assert "quantitative dynamics" in joined
    assert "Mad2" in joined
    assert "EXP01 and EXP02 have never run" in joined
    assert "not a sampling rate" in report.rate_note
