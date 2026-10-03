"""Contradiction audit: what would kill each hypothesis, and whether anyone checked."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rarepipe.stages.prospective.model import EvidenceRef, Hypothesis, StatementType
from rarepipe.stages.prospective.seed import hypotheses as seed_hypotheses
from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Support
from rarepipe.stages.simulate.contradict import audit
from rarepipe.stages.simulate.mva import BUBR1, BUBR1_FN, SIRT2, K668, mva_chain


def test_every_seeded_hypothesis_appears():
    seeded = seed_hypotheses()
    report = audit()
    assert report.origin == "synthetic"
    assert {row.hypothesis_id for row in report.hypotheses} == {h.id for h in seeded}
    assert [row.hypothesis_id for row in report.hypotheses] == [h.id for h in seeded]
    for hyp, row in zip(seeded, report.hypotheses):
        assert row.statement == hyp.statement
        assert row.assessment == hyp.assessment


def test_h01_and_h02_both_live_with_separating_measurement():
    report = audit()
    h01 = report.by_id("H01")
    h02 = report.by_id("H02")
    assert h01.live and h02.live
    assert "H02" in h01.alternatives and "H01" in h02.alternatives
    separating = f"{BUBR1}->{BUBR1_FN}"
    assert h01.separating_measurement == separating
    assert h02.separating_measurement == separating
    # Must not pick a winner: both remain live, no ranking field, narrative refuses one.
    text = report.narrative()
    assert "does not rank hypotheses or pick a winner" in text
    assert "H01" in text and "H02" in text
    assert h01.edges_to_survive[0].requirement == "hold"
    assert h02.edges_to_survive[0].requirement == "fail"
    assert h01.edges_to_survive[0].edge_key == separating
    assert h02.edges_to_survive[0].edge_key == separating


def test_missing_falsification_is_flagged_not_silently_passed():
    report = audit()
    # H01 states a falsification criterion; H02 through H07 do not.
    assert report.by_id("H01").unfalsifiable_as_stated is False
    assert report.by_id("H01").falsification
    for hid in ("H02", "H03", "H04", "H05", "H06", "H07"):
        row = report.by_id(hid)
        assert row.criterion_kind == "discriminating_only"
        assert row.unfalsifiable_as_stated is False
        assert row.falsification == ""
    text = report.narrative()
    assert "no explicit falsification clause" in text


def test_hypothesis_resting_only_on_different_agent_edge_is_named():
    """H04's load-bearing citation is the NMN (different agent) SIRT2 deacetylation edge."""
    report = audit()
    h04 = report.by_id("H04")
    edge_key = f"{SIRT2}->{K668}"
    assert h04.rests_only_on_weak_support is True
    assert any(
        w.edge_key == edge_key and w.support is Support.DIFFERENT_AGENT
        for w in h04.weak_support_edges
    )
    assert edge_key in report.narrative()
    assert "different_agent" in report.narrative()


def test_none_looked_for_is_reported_when_no_search_marked():
    report = audit()
    h01 = report.by_id("H01")
    assert h01.opposing[0].status == "none_looked_for"
    searched = audit(searched_hypothesis_ids={"H01"})
    assert searched.by_id("H01").opposing[0].status == "none_recorded"
    assert searched.by_id("H02").opposing[0].status == "none_looked_for"


def test_synthetic_probe_names_different_agent_support():
    """A hypothesis whose only overlapping edge is different_agent is reported with that edge."""
    chain = CausalChain(
        chain_id="probe", case_ref="PROBE",
        nodes=("a", "b"),
        edges=(
            CausalEdge(
                source="a", target="b", sign=1, mechanism="agent substitution",
                support=Support.DIFFERENT_AGENT,
                evidence_ref="PMID:99999999",
                scope_note="different precursor in mice",
            ),
        ),
    )
    hyp = Hypothesis(
        id="H_WEAK",
        level="drug_mechanism",
        statement="The substituted agent connection fails here",
        evidence=[EvidenceRef(
            ref="PMID:99999999",
            statement_type=StatementType.LITERATURE_CLAIM,
            scope_note="different precursor in mice",
            independence_group="PMID:99999999",
        )],
        distinguished_by="agent-matched measurement",
    )
    report = audit(chain, hypotheses=[hyp])
    row = report.by_id("H_WEAK")
    assert row.criterion_kind == "discriminating_only"
    assert row.unfalsifiable_as_stated is False
    assert row.rests_only_on_weak_support is True
    assert row.weak_support_edges[0].edge_key == "a->b"
    assert row.weak_support_edges[0].support is Support.DIFFERENT_AGENT


def test_report_never_claims_a_winner_or_accuracy():
    text = audit().narrative()
    assert "winner" in text.lower() or "does not rank" in text
    for banned in ("AUPRC", "80% concordance", "likely true", "most probable"):
        assert banned not in text


def test_mva_chain_asserted_gap_is_the_separating_measurement():
    """Derived from the chain, not transcribed: the H01/H02 caveat edge is the separator."""
    chain = mva_chain()
    gap = next(
        e for e in chain.edges
        if e.support is Support.ASSERTED_ONLY and "H01" in e.caveat and "H02" in e.caveat
    )
    report = audit(chain)
    assert report.by_id("H01").separating_measurement == gap.key
    assert report.by_id("H02").separating_measurement == gap.key


def test_a_flag_on_six_of_seven_rows_would_carry_no_information():
    """The criterion level must distinguish three cases, not two.

    `unfalsifiable_as_stated` originally keyed on the `falsification` field alone. Only H01 states
    an explicit falsification clause, but H02-H07 each record a `distinguished_by` — a stated way
    to tell the hypothesis apart, which is a discriminating criterion in substance. Flagging six
    of seven rows as unfalsifiable overstated the finding and destroyed its signal: a reader who
    sees almost every row flagged stops reading the flag.

    The real finding survives and is sharper: exactly one hypothesis states an explicit falsifier.
    """
    report = audit()
    kinds = {row.hypothesis_id: row.criterion_kind for row in report.hypotheses}

    explicit = [h for h, k in kinds.items() if k == "explicit_falsification"]
    assert explicit == ["H01"], kinds
    assert all(k == "discriminating_only" for h, k in kinds.items() if h != "H01"), kinds

    # And nothing is reported as having no criterion at all, because nothing does.
    assert not [row for row in report.hypotheses if row.unfalsifiable_as_stated]


def test_the_criterion_level_cannot_be_asserted_independently_of_the_record():
    """A row may not claim a level its own fields do not support."""
    from rarepipe.stages.simulate.contradict import HypothesisContradiction

    with pytest.raises(ValidationError, match="must be derived from what is recorded"):
        HypothesisContradiction(
            hypothesis_id="H_FAKE", statement="s", live=True, assessment="",
            falsification="", distinguished_by="a stated discriminator",
            criterion_kind="none",
        )
    with pytest.raises(ValidationError, match="must be derived from what is recorded"):
        HypothesisContradiction(
            hypothesis_id="H_FAKE", statement="s", live=True, assessment="",
            falsification="a real falsifier", distinguished_by="",
            criterion_kind="discriminating_only",
        )
