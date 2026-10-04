"""Proof gates for the capability-gap discovery compiler.

    missing function -> search specification -> candidate -> evidence -> capability -> recompile

Agents discover possibilities. Evidence establishes claims. Deterministic code decides whether a
capability exists. Each gate below would pass if the property it names were absent, so each is also
mutation tested.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest
from pydantic import ValidationError

from rarepipe.stages.control.discovery import mva_gaps
from rarepipe.stages.control.discovery.capabilities import GroundedCapability, NotEntitled
from rarepipe.stages.control.discovery.compiler import compile_discovery
from rarepipe.stages.control.discovery.kinds import (
    CapabilityEntitlement, GapResult, RejectionReason, VerificationLevel,
)
from rarepipe.stages.control.provenance import (
    GATE_NEVER_ASSIGNS, GATE_REFUSES_CLAIM, EpistemicType,
)
from rarepipe.stages.control.realization.kinds import EpistemicBurden, RealizationResult
from tests import discovery_toys as T


def run(problem, targets=()):
    return compile_discovery(problem, targets)


def one(report):
    return report.gaps[0]


def by_id(report, candidate_id):
    return next(a for a in one(report).assessments if a.candidate_id == candidate_id)


# ---------------------------------------------------------------- Gate 1: exact capability

def test_gate1_a_piece_that_exactly_satisfies_the_gap_is_found_and_grounded():
    report = run(T.exact())
    gap = one(report)
    assert gap.result is GapResult.CAPABILITY_FOUND
    assert len(gap.grounded_capabilities) == 1
    capability = gap.grounded_capabilities[0]
    assert capability.entitlement is CapabilityEntitlement.GROUNDED
    assert VerificationLevel.CAPABILITY_ENTITLED_FOR_CONTEXT in capability.verification
    assert capability.causal_depth == 1


def test_gate1_the_three_verification_levels_are_recorded_separately():
    """A verified source, a claim grounded in it, and entitlement for the context are not one thing."""
    capability = one(run(T.exact())).grounded_capabilities[0]
    assert set(capability.verification) == {VerificationLevel.SOURCE_VERIFIED,
                                            VerificationLevel.CLAIM_GROUNDED_IN_SOURCE,
                                            VerificationLevel.CAPABILITY_ENTITLED_FOR_CONTEXT}


# ---------------------------------------------------------------- Gate 2: wrong input

def test_gate2_a_capability_cannot_cite_a_claim_about_a_different_input():
    """The real bug this project already hit: A -> B may not cite evidence for C -> B."""
    report = run(T.wrong_input())
    borrowed = by_id(report, "CC_BORROWED")
    assert RejectionReason.INPUT_MISMATCH in borrowed.rejections
    assert not borrowed.can_ground
    assert borrowed.entitlement is CapabilityEntitlement.EVIDENCE_INSUFFICIENT
    assert "CC_BORROWED" in {r.candidate_id for r in one(report).rejected_candidates}
    assert not any(c.candidate_id == "CC_BORROWED" for c in one(report).grounded_capabilities)


# ---------------------------------------------------------------- Gate 3: wrong direction

def test_gate3_a_faithful_source_for_the_opposite_effect_does_not_answer_the_gap():
    report = run(T.wrong_direction())
    gap = one(report)
    assert gap.result is GapResult.NO_GROUNDED_CAPABILITY
    assessment = gap.assessments[0]
    assert RejectionReason.DIRECTION_MISMATCH in assessment.rejections
    assert any(c.validator == "gap_direction" and not c.passed for c in assessment.checks)
    assert any(c.validator == "direction_match" and c.passed for c in assessment.checks), \
        "the claim is cited faithfully; it is the gap it fails, and the two must be distinguishable"


# ---------------------------------------------------------------- Gate 4: forbidden dependency

def test_gate4_a_candidate_whose_mechanism_runs_through_the_forbidden_node_is_not_a_bypass():
    report = run(T.forbidden_dependency())
    gap = one(report)
    assert gap.result is GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND
    assessment = gap.assessments[0]
    assert assessment.forbidden_hits == ("blocked_node",)
    assert "dose" in assessment.ancestry, \
        "the check walks the whole ancestry, not just the candidate's own declaration"
    assert not gap.grounded_capabilities


def test_gate4_the_result_is_sharper_than_finding_nothing():
    gap = one(run(T.forbidden_dependency()))
    assert "sharper result than finding nothing" in gap.result_meaning


# ---------------------------------------------------------------- Gates 5-7: context

def test_gate5_a_right_mechanism_in_the_wrong_system_is_context_only():
    gap = one(run(T.wrong_system()))
    assert gap.result is GapResult.CONTEXT_ONLY_CAPABILITY
    assert RejectionReason.CONTEXT_MISMATCH in gap.assessments[0].rejections


def test_gate6_an_effect_shown_with_a_different_agent_is_not_inherited():
    gap = one(run(T.wrong_agent()))
    assert gap.result is GapResult.CONTEXT_ONLY_CAPABILITY
    assert RejectionReason.AGENT_MISMATCH in gap.assessments[0].rejections
    assert not gap.grounded_capabilities


def test_gate7_the_circulating_pool_is_not_the_intracellular_pool():
    gap = one(run(T.wrong_compartment()))
    assert gap.result is GapResult.CONTEXT_ONLY_CAPABILITY
    assert RejectionReason.COMPARTMENT_MISMATCH in gap.assessments[0].rejections


def test_gates5_to_7_each_dimension_fails_on_its_own():
    """Three separate rejections, so a report says which dimension broke rather than 'context'."""
    reasons = {
        "system": set(one(run(T.wrong_system())).assessments[0].rejections),
        "agent": set(one(run(T.wrong_agent())).assessments[0].rejections),
        "compartment": set(one(run(T.wrong_compartment())).assessments[0].rejections),
    }
    assert reasons["agent"] != reasons["compartment"] != reasons["system"]


# ---------------------------------------------------------------- Gate 8: unsupported intermediate

def test_gate8_a_chain_with_an_ungrounded_link_is_partial_and_names_the_link():
    report = run(T.unsupported_intermediate())
    gap = one(report)
    chain = by_id(report, "CC_CHAIN")
    assert chain.unsupported_intermediates
    assert RejectionReason.UNSUPPORTED_INTERMEDIATE in chain.rejections
    assert gap.result is GapResult.PARTIAL_CAPABILITY
    assert gap.remaining_missing_steps


def test_gate8_an_intermediate_claim_resolves_rather_than_counting_as_fabricated():
    """A chain citing a real upstream claim is auditable; refusing it would hide the real failure."""
    chain = by_id(run(T.unsupported_intermediate()), "CC_CHAIN")
    assert RejectionReason.FABRICATED not in chain.rejections
    assert chain.source_ids == ("dose->middle",)
    # The cited claim measures a different output than the candidate asserts, and that is its own
    # failure: a readout standing in for a function is not the function.
    assert RejectionReason.OUTPUT_MISMATCH in chain.rejections


# ---------------------------------------------------------------- Gate 9: contradiction

def test_gate9_a_null_or_opposite_result_appears_as_a_contradiction():
    gap = one(run(T.contradicted()))
    assert gap.result is GapResult.CONTRADICTED_CAPABILITY
    assert gap.contradictions
    assert gap.assessments[0].entitlement is CapabilityEntitlement.CONTRADICTED
    assert not gap.grounded_capabilities


# ---------------------------------------------------------------- Gate 10: fabrication

def test_gate10_an_invented_reference_does_not_enter_the_registry():
    report = run(T.fabricated())
    invented = by_id(report, "CC_INVENTED_SOURCE")
    assert RejectionReason.FABRICATED in invented.rejections
    assert not invented.can_ground


def test_gate10_an_invented_entity_citing_a_real_claim_is_rejected_too():
    report = run(T.fabricated())
    borrowed = by_id(report, "CC_INVENTED_ENTITY")
    assert RejectionReason.ENTITY_MISMATCH in borrowed.rejections
    assert not borrowed.can_ground


def test_gate10_a_candidate_with_no_source_is_rejected():
    report = run(T.fabricated())
    bare = by_id(report, "CC_NO_SOURCE")
    assert RejectionReason.NO_PROVENANCE in bare.rejections
    assert bare.entitlement is CapabilityEntitlement.EVIDENCE_INSUFFICIENT


def test_gate10_no_invented_candidate_produced_a_capability():
    report = run(T.fabricated())
    grounded_from = {c.candidate_id for c in one(report).grounded_capabilities}
    assert grounded_from.isdisjoint({"CC_INVENTED_SOURCE", "CC_INVENTED_ENTITY", "CC_NO_SOURCE"})


def test_gate10_an_agent_cannot_propose_a_grounded_capability_at_all():
    """Invariant 1, enforced at the gate rather than discovered downstream.

    Narrow on purpose. Claiming any *other* strong type stays recorded-and-ignored, so an honest
    proposal with a wrong label keeps its content and is typed down to what it is. A grounded
    capability is different: the request is to skip the validators, and there is nothing to salvage.
    """
    from rarepipe.stages.control.proposals import Proposal, ProposalKind, gate
    from rarepipe.stages.prospective.model import Actor, ActorType, Role
    assert EpistemicType.GROUNDED_CAPABILITY in GATE_REFUSES_CLAIM
    assert EpistemicType.GROUNDED_CAPABILITY in GATE_NEVER_ASSIGNS
    decision = gate(Proposal(
        proposal_id="PR_SNEAK", skill_id="evidence_grounding", skill_version="1.0",
        proposer=Actor(actor_type=ActorType.AGENT, identity="grounder", roles=(Role.ENGINEER,)),
        kind=ProposalKind.ARCHITECTURE,
        claimed_epistemic_type=EpistemicType.GROUNDED_CAPABILITY,
        payload={"architecture_id": "A", "family": "f", "composition": [["BB"]],
                 "composition_mode": "simultaneous", "origin": "compensatory",
                 "rationale": "an attempt to claim grounding"},
        rationale="attempts to self-certify"))
    assert not decision.accepted
    assert "deterministic validators" in decision.reason


def test_a_mislabelled_proposal_is_still_typed_down_rather_than_discarded():
    from rarepipe.stages.control.proposals import Proposal, ProposalKind, gate
    from rarepipe.stages.prospective.model import Actor, ActorType, Role
    decision = gate(Proposal(
        proposal_id="PR_MISLABELLED", skill_id="evidence_grounding", skill_version="1.0",
        proposer=Actor(actor_type=ActorType.AGENT, identity="grounder", roles=(Role.ENGINEER,)),
        kind=ProposalKind.ARCHITECTURE,
        claimed_epistemic_type=EpistemicType.OBSERVED_EMPIRICAL,
        payload={"architecture_id": "A_HONEST", "family": "f", "composition": [["BB"]],
                 "composition_mode": "simultaneous", "origin": "compensatory",
                 "rationale": "a real proposal carrying an over-confident label"},
        rationale="mislabelled but otherwise fine"))
    assert decision.accepted
    assert decision.assigned_epistemic_type is EpistemicType.PROPOSED_ARCHITECTURE


def test_gate10_the_builder_refuses_a_candidate_that_did_not_pass():
    from rarepipe.stages.control.discovery.validators import build
    report = run(T.contradicted())
    problem = T.contradicted()
    gap = problem.gaps[0]
    assessment = one(report).assessments[0]
    with pytest.raises(NotEntitled, match="CONTRADICTED"):
        build(T.candidate("CC_X", refs=("dose->func",)), gap, assessment, {})


def test_gate10_a_capability_cannot_be_constructed_with_another_epistemic_type():
    capability = one(run(T.exact())).grounded_capabilities[0]
    with pytest.raises(ValidationError, match="GROUNDED_CAPABILITY provenance"):
        GroundedCapability(**{**capability.model_dump(),
                              "provenance": {**capability.provenance.model_dump(),
                                             "epistemic_type": "literature_evidence"}})


# ---------------------------------------------------------------- Gate 11: ground and recompile

def test_gate11_grounding_a_capability_changes_the_compiled_realization():
    problem = T.exact()
    report = run(problem, (T.recompile_target(problem.inventory),))
    delta = report.recompiles[0]
    assert delta.before == RealizationResult.NO_GROUNDED_REALIZATION.value
    assert delta.after == RealizationResult.GROUNDED_REALIZATION_CANDIDATE.value
    assert delta.changed
    assert delta.capabilities_added
    assert any("NO_GROUNDED_REALIZATION -> GROUNDED_REALIZATION_CANDIDATE" in item
               for item in report.interfaces_whose_state_changed)


def test_gate11_the_recompile_happens_without_anybody_editing_a_realization():
    """The new piece lands on a function nobody wrote a mechanism for, and the compiler composes it."""
    problem = T.exact()
    target = T.recompile_target(problem.inventory)
    assert not target.realizations, "the target declares no mechanism for its required function"
    after = run(problem, (target,)).recompiles[0].after
    assert after == RealizationResult.GROUNDED_REALIZATION_CANDIDATE.value


def test_gate11_an_unchanged_result_is_stated_rather_than_omitted():
    problem = T.no_evidence()
    delta = run(problem, (T.recompile_target(problem.inventory),)).recompiles[0]
    assert not delta.changed
    assert "nothing was added and nothing recompiled differently" in delta.note


# ---------------------------------------------------------------- Gate 12: remove evidence

def test_gate12_removing_the_grounding_claim_degrades_the_result():
    with_claim = run(T.exact(), (T.recompile_target(T.exact().inventory),))
    without = run(T.no_evidence(), (T.recompile_target(T.no_evidence().inventory),))
    assert one(with_claim).result is GapResult.CAPABILITY_FOUND
    assert one(without).result is GapResult.NO_GROUNDED_CAPABILITY
    assert with_claim.recompiles[0].changed and not without.recompiles[0].changed


def test_gate12_an_unverified_citation_caps_the_result_at_conditional():
    """Section 21: UNVERIFIED_SOURCE -> at most CONDITIONAL, resolvable later without code changes."""
    report = run(T.unverified())
    gap = one(report)
    assert gap.result is GapResult.PARTIAL_CAPABILITY
    assert gap.assessments[0].entitlement is CapabilityEntitlement.UNVERIFIED_SOURCE
    capability = gap.grounded_capabilities[0]
    assert capability.entitlement is CapabilityEntitlement.CONDITIONAL
    assert VerificationLevel.SOURCE_VERIFIED not in capability.verification


# ---------------------------------------------------------------- Gates 13-14: the real gaps

def test_gate13_the_bypass_gaps_run_and_explain_why_they_stay_open():
    report = run(mva_gaps.problem(), mva_gaps.targets())
    bypass = [g for g in report.gaps if "WITHOUT_BUBR1" in g.gap_id]
    assert len(bypass) == 3
    for gap in bypass:
        assert gap.result is GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND
        assert gap.assessments, "a result with no candidate examined would explain nothing"
        assert all(a.forbidden_hits == ("bubr1_residual_function",) for a in gap.assessments)
        assert gap.reason and gap.universe_inspected


def test_gate13_the_burden_differs_across_the_three_bypass_gaps():
    report = run(mva_gaps.problem())
    burdens = {g.gap_id: g.epistemic_burden for g in report.gaps}
    assert burdens["GAP_A_CHECKPOINT_ACTIVATION_WITHOUT_BUBR1"] == \
        EpistemicBurden.BYPASSES_ESTABLISHED_RELATIONSHIP.value
    assert burdens["GAP_B_CHECKPOINT_SILENCING_WITHOUT_BUBR1"] == \
        EpistemicBurden.BYPASSES_ASSUMED_RELATIONSHIP.value


def test_gate14_the_cofactor_entry_gap_produces_a_grounded_verdict():
    """The methodological control: the steps after this one are already grounded."""
    gap = next(g for g in run(mva_gaps.problem()).gaps
               if g.gap_id == "GAP_D_INTRACELLULAR_COFACTOR_ENTRY")
    assert gap.result is GapResult.CONTEXT_ONLY_CAPABILITY
    assessment = gap.assessments[0]
    assert RejectionReason.COMPARTMENT_MISMATCH in assessment.rejections
    assert not assessment.forbidden_hits, "this gap forbids nothing; it is a chain-closing gap"
    assert gap.context_gaps


def test_gate14_the_previous_unknown_became_a_named_context_mismatch():
    """Section 31's metric: the epistemic state of a functional interface moved."""
    report = run(mva_gaps.problem(), mva_gaps.targets())
    assert any("GAP_D_INTRACELLULAR_COFACTOR_ENTRY: CONTEXT_ONLY_CAPABILITY" in item
               for item in report.interfaces_whose_state_changed)
    assert len(report.interfaces_whose_state_changed) == 4


def test_the_real_run_grounds_nothing_and_says_what_universe_was_searched():
    report = run(mva_gaps.problem(), mva_gaps.targets())
    assert not report.grounded_capabilities
    assert report.abstention_reason
    for gap in report.gaps:
        providers = {item["provider"] for item in gap.universe_inspected}
        assert providers == {"repository_inventory", "curated_claims"}
        curated = next(i for i in gap.universe_inspected if i["provider"] == "curated_claims")
        assert curated["corpus_size"] == 0
        assert "not evidence that no such claim exists" in curated["note"]


def test_a_negative_result_never_claims_biology():
    report = run(mva_gaps.problem())
    for gap in report.gaps:
        assert "never about biology" in gap.result_meaning or \
            "sharper result" in gap.result_meaning or "incompatible" in gap.result_meaning


# ---------------------------------------------------------------- Gate 15: determinism

def test_gate15_the_same_gaps_and_evidence_give_the_same_digest_across_processes():
    script = ("from rarepipe.stages.control.discovery import mva_gaps\n"
              "from rarepipe.stages.control.discovery.compiler import compile_discovery\n"
              "print(compile_discovery(mva_gaps.problem(), mva_gaps.targets()).content_digest)\n")
    digests = set()
    for seed in ("0", "11", "131071"):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                                  "PYTHONPATH": "src:."}, cwd="/Users/venus/Desktop/rarepipe")
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    assert len(digests) == 1, f"the discovery digest moved with the hash seed: {digests}"


def test_gate15_the_digest_covers_the_gap_contents_not_only_the_headline():
    """Section 18: the digest depends on claims and context metadata, not just the verdict.

    Two runs that reach the same result for different reasons must not share a digest, or a change
    in the evidence could leave a committed report looking current.
    """
    agent, compartment = run(T.wrong_agent()), run(T.wrong_compartment())
    assert one(agent).result is one(compartment).result
    assert agent.interfaces_whose_state_changed == compartment.interfaces_whose_state_changed
    assert not agent.grounded_capabilities and not compartment.grounded_capabilities
    assert one(agent).rejection_reasons != one(compartment).rejection_reasons
    assert agent.content_digest != compartment.content_digest


def test_gate15_the_digest_moves_when_the_evidence_moves():
    """Staleness: a change anywhere in the inputs must invalidate the previous report."""
    assert run(T.exact()).content_digest != run(T.no_evidence()).content_digest
    assert run(T.exact()).content_digest != run(T.unverified()).content_digest


# ---------------------------------------------------------------- governance

def test_no_case_level_genomic_content_reaches_a_gap_report():
    patterns = (r"\bc\.\d", r"\bp\.[A-Z][a-z]{2}\d", r"\bchr[0-9XYM]", r"\brs\d{3,}",
                r"\bg\.\d{4,}", r"\b[ACGT]{8,}\b")
    blob = run(mva_gaps.problem(), mva_gaps.targets()).model_dump_json()
    for pattern in patterns:
        assert not re.search(pattern, blob), f"{pattern} matched in a gap report"


def test_the_report_carries_no_recommendation_and_cannot_be_reworded():
    from rarepipe.stages.control.discovery.compiler import DiscoveryReport
    report = run(mva_gaps.problem())
    assert "no treatment recommendation" in report.no_treatment_recommendation
    with pytest.raises(ValidationError):
        DiscoveryReport(**{**report.model_dump(),
                           "no_treatment_recommendation": "see the attached protocol"})


def test_a_mechanism_hypothesis_cannot_claim_to_be_anything_stronger():
    from rarepipe.stages.control.discovery.candidates import MechanismHypothesis
    hypothesis = mva_gaps.hypotheses()[0]
    assert hypothesis.provenance.epistemic_type is EpistemicType.MECHANISM_HYPOTHESIS
    with pytest.raises(ValidationError, match="MECHANISM_HYPOTHESIS provenance"):
        MechanismHypothesis(**{**hypothesis.model_dump(),
                               "provenance": {**hypothesis.provenance.model_dump(),
                                              "epistemic_type": "literature_evidence",
                                              "references": ("PMID:1",)}})


def test_the_committed_gap_report_is_not_stale():
    from pathlib import Path

    from rarepipe.stages.control.discovery.report import render
    committed = (Path(__file__).resolve().parents[1]
                 / "docs/control/MVA_CAPABILITY_GAPS.md").read_text()
    assert committed == render(run(mva_gaps.problem(), mva_gaps.targets())), (
        "docs/control/MVA_CAPABILITY_GAPS.md is stale: run "
        "uv run python tools/control/compile_mva_gaps.py")
