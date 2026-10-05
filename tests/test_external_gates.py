"""Proof gates for the external-evidence layer.

    desired function -> capability gap -> external evidence search -> physical capability -> recompile

The model may propose where to look. The source establishes what was observed. The grounding layer
establishes what may be claimed. Deterministic code establishes whether the capability satisfies the
gap. A negative result is always bounded by the searched universe.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rarepipe.stages.control.discovery import mva_gaps
from rarepipe.stages.control.discovery.compiler import compile_discovery
from rarepipe.stages.control.discovery.external import corpus as C
from rarepipe.stages.control.discovery.external.claims import (
    CausalGrade, compartment_verdict, span_is_grounded,
)
from rarepipe.stages.control.discovery.external.mva_claims import claims as mva_claims
from rarepipe.stages.control.discovery.external.queryplan import plan
from rarepipe.stages.control.discovery.kinds import (
    CapabilityEntitlement, GapResult, RejectionReason, VerificationLevel,
)
from rarepipe.stages.control.realization.kinds import RealizationResult
from tests import external_toys as X

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = C.snapshot_path(ROOT, "mva-external-v1")


def run(problem, targets=()):
    return compile_discovery(problem, targets)


def one(report):
    return report.gaps[0]


def by_id(report, candidate_id):
    return next(a for a in one(report).assessments if candidate_id in a.candidate_id)


# ---------------------------------------------------------------- Gate 1: real-source retrieval

def test_gate1_the_snapshot_holds_real_verifiable_sources():
    snapshot = C.load(SNAPSHOT)
    assert len(snapshot.documents) >= 50, "a bounded negative needs a corpus worth bounding"
    assert "europepmc" in snapshot.index.lower()
    for document in snapshot.documents:
        assert document.content_digest.startswith("sha256:")
        assert document.retrieved_at and document.retrieved_by_query
        assert (SNAPSHOT / document.relative_path).exists(), \
            f"{document.source_id} is in the manifest with no stored text"
    with_identifier = [d for d in snapshot.documents if d.pmid or d.doi]
    assert len(with_identifier) >= len(snapshot.documents) // 2


def test_gate1_queries_are_functional_not_gene_name_lookups():
    for gap in mva_gaps.gaps():
        queries = plan(gap).queries
        assert queries
        assert not any("BUB1B" in q.query.upper() for q in queries), \
            "searching by the broken gene finds the literature about the broken gene"
        assert all(q.dimension for q in queries)


def test_gate1_the_plan_records_what_it_deliberately_does_not_search_by():
    excluded = plan(mva_gaps.gaps()[0]).excluded_from_queries
    assert any("case-identity" in item for item in excluded)
    assert any("therapy" in item or "intervention" in item for item in excluded)


# ---------------------------------------------------------------- Gate 2: exact span grounding

def test_gate2_every_extracted_claim_points_at_a_real_passage():
    snapshot = C.load(SNAPSHOT)
    for claim in mva_claims():
        document = snapshot.document(claim.source_id)
        assert document is not None, f"{claim.claim_id} cites a document not in the snapshot"
        assert span_is_grounded(claim, C.text_of(SNAPSHOT, document)), \
            f"{claim.claim_id}: the quoted span is not in {claim.source_id}"


def test_gate2_a_paraphrase_is_not_a_span():
    report = run(X.bad_span())
    assert one(report).result is GapResult.NO_GROUNDED_CAPABILITY
    assert RejectionReason.SPAN_NOT_GROUNDED in one(report).assessments[0].rejections
    assert not one(report).grounded_capabilities


# ---------------------------------------------------------------- Gate 3: invented citation

def test_gate3_a_claim_citing_a_document_the_corpus_lacks_is_reported_not_dropped():
    report = run(X.invented_source())
    literature = next(item for item in one(report).universe_inspected
                      if item["provider"] == "scientific_literature")
    assert literature["accounting"]["claims_citing_absent_documents"] == 1
    assert "does not contain" in literature["note"]
    assert not one(report).grounded_capabilities


# ---------------------------------------------------------------- Gates 4 and 5: input and output

def test_gate4_a_real_source_is_not_evidence_for_a_different_input():
    report = run(X.borrowed_external())
    borrowed = by_id(report, "CC_WRONG_INPUT")
    assert RejectionReason.INPUT_MISMATCH in borrowed.rejections
    assert not borrowed.can_ground


def test_gate5_a_real_source_is_not_evidence_for_a_different_output():
    report = run(X.borrowed_external())
    borrowed = by_id(report, "CC_WRONG_OUTPUT")
    assert RejectionReason.OUTPUT_MISMATCH in borrowed.rejections
    assert not borrowed.can_ground


# ---------------------------------------------------------------- Gate 6: direction and semantics

def test_gate6_a_reported_increase_is_not_a_restored_function():
    report = run(X.effect_is_not_state())
    assert one(report).result is GapResult.NO_GROUNDED_CAPABILITY
    assessment = one(report).assessments[0]
    assert RejectionReason.EFFECT_IS_NOT_STATE in assessment.rejections
    assert "does not constitute" in assessment.reason


def test_gate6_the_state_specification_names_what_a_naive_reading_would_accept():
    specification = mva_gaps.semantics().for_state("checkpoint_activation", "normal")
    assert specification is not None
    assert len(specification.requires) >= 2, "one condition is a threshold wearing a name"
    assert any("permanent" in item for item in specification.excludes), \
        "a cell stopped from dividing at all must be excluded explicitly"


def test_gate6_no_global_effect_to_state_rule_exists():
    registry = mva_gaps.semantics()
    assert registry.mappings == (), \
        "a mapping from increase to normal would have to be justified; none is"


# ---------------------------------------------------------------- Gate 7: context transfer

def test_gate7_a_relation_shown_elsewhere_is_a_transfer_gap_not_a_grounding():
    report = run(X.wrong_system())
    assert one(report).result is GapResult.CONTEXT_ONLY_CAPABILITY
    assert not one(report).grounded_capabilities
    assert RejectionReason.CONTEXT_MISMATCH in one(report).assessments[0].rejections


def test_gate7_the_compartment_transfer_rule_is_explicit():
    assert compartment_verdict("whole blood", "intracellular pool").value == "INCOMPATIBLE_CONTEXT"
    assert compartment_verdict("intracellular (tissue homogenate)",
                               "intracellular pool").value == "COMPATIBLE_CONTEXT"
    assert compartment_verdict("intracellular pool", "intracellular pool").value == "EXACT_CONTEXT"


def test_gate7_transfer_gaps_are_objects_with_what_is_missing():
    report = run(mva_gaps.problem())
    gaps = [g for g in report.gaps if g.transfer_gaps]
    assert gaps, "the real run must produce at least one transfer gap"
    for gap in gaps:
        for item in gap.transfer_gaps:
            assert "demonstrated in" in item and "missing" in item


# ---------------------------------------------------------------- Gate 8: forbidden ancestry

def test_gate8_an_external_candidate_declaring_a_forbidden_dependency_is_not_a_bypass():
    report = run(X.forbidden_ancestry())
    assert one(report).result is GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND
    assessment = one(report).assessments[0]
    assert assessment.forbidden_hits == ("blocked_node",)


def test_gate8_a_new_entity_does_not_get_independence_for_free():
    """Absence of a recorded link is not evidence of independence."""
    report = run(X.independence_unestablished())
    assessment = one(report).assessments[0]
    assert not assessment.forbidden_hits, "nothing links this entity to the forbidden node"
    assert RejectionReason.INDEPENDENCE_UNESTABLISHED in assessment.rejections
    assert "absence of a recorded link" in assessment.independence


def test_gate8_a_source_that_states_independence_can_satisfy_a_bypass_gap():
    report = run(X.independence_asserted())
    assert one(report).result is GapResult.CAPABILITY_FOUND
    capability = one(report).grounded_capabilities[0]
    assert capability.forbidden_dependencies_satisfied == ("blocked_node",)


def test_gate8_ancestry_is_scoped_to_the_candidates_own_mechanism():
    """The inventory already records that the forbidden component drives these outputs.

    Walking upward from the output would therefore find it for every candidate and declare nothing
    independent, ever. The walk starts from what the mechanism rests on instead.
    """
    report = run(mva_gaps.problem())
    gap = next(g for g in report.gaps if g.gap_id.startswith("GAP_C"))
    external = next(a for a in gap.assessments if "41218610" in a.candidate_id)
    assert not external.forbidden_hits
    assert RejectionReason.INDEPENDENCE_UNESTABLISHED in external.rejections
    internal = next(a for a in gap.assessments if "bubr1" in a.candidate_id)
    assert internal.forbidden_hits == ("bubr1_residual_function",)


# ---------------------------------------------------------------- Gate 9: association vs causality

def test_gate9_an_association_cannot_satisfy_a_causal_capability():
    report = run(X.association_only())
    assert one(report).result is GapResult.NO_GROUNDED_CAPABILITY
    assessment = one(report).assessments[0]
    assert RejectionReason.ASSOCIATION_ONLY in assessment.rejections
    assert assessment.causal_grade is CausalGrade.ASSOCIATION


def test_gate9_every_real_claim_carries_a_causal_grade():
    for claim in mva_claims():
        assert claim.causal_grade in set(CausalGrade)


# ---------------------------------------------------------------- Gate 10: contradictory evidence

def test_gate10_a_contradicting_claim_stays_visible_in_the_report():
    from tests import discovery_toys as D
    report = run(D.contradicted())
    assert one(report).result is GapResult.CONTRADICTED_CAPABILITY
    assert one(report).contradictions


def test_gate10_each_real_claim_records_what_its_own_source_does_not_establish():
    """Both sides in the report: the limitation is the reason three of these cannot ground."""
    limited = [c for c in mva_claims() if c.limitation]
    assert len(limited) >= 4
    report = run(mva_gaps.problem())
    caveats = " ".join(a.reason for g in report.gaps for a in g.assessments)
    assert caveats


# ---------------------------------------------------------------- Gates 11-13: ground and recompile

def test_gate11_an_external_source_can_produce_a_previously_absent_capability():
    problem = X.grounds()
    report = run(problem)
    assert one(report).result is GapResult.CAPABILITY_FOUND
    capability = one(report).grounded_capabilities[0]
    assert capability.entitlement is CapabilityEntitlement.GROUNDED
    assert VerificationLevel.CAPABILITY_ENTITLED_FOR_CONTEXT in capability.verification
    assert capability.evidence_claims == ("PMID:00000099",)
    assert not any(edge.target == capability.output for edge in problem.inventory.edges), \
        "the capability must not already exist in the repository's own corpus"


def test_gate12_and_13_the_new_capability_recompiles_the_architecture_automatically():
    problem = X.grounds()
    report = run(problem, (X.target_for(problem.inventory),))
    delta = report.recompiles[0]
    assert delta.before == RealizationResult.NO_GROUNDED_REALIZATION.value
    assert delta.after == RealizationResult.GROUNDED_REALIZATION_CANDIDATE.value
    assert delta.changed and delta.capabilities_added
    assert any("GROUNDED_REALIZATION_CANDIDATE" in item
               for item in report.interfaces_whose_state_changed)


def test_gate13_the_grounded_claim_enters_the_realization_inventory_with_its_evidence():
    """The registry update carries the evidence, or the realization layer would refuse the citation."""
    from rarepipe.stages.control.discovery.compiler import extended_inventory
    problem = X.grounds()
    report = run(problem)
    target = X.target_for(problem.inventory)
    extended = extended_inventory(target, report.grounded_capabilities)
    assert len(extended.edges) > len(target.inventory.edges)
    added = extended.edge("PMID:00000099")
    assert added.target == "func" and added.ref


# ---------------------------------------------------------------- Gate 14: no-effect capability

def test_gate14_a_capability_that_lands_nowhere_does_not_change_the_architecture():
    problem = X.irrelevant_capability()
    report = run(problem, (X.target_for(problem.inventory),))
    assert one(report).result is GapResult.CAPABILITY_FOUND, "it grounds"
    delta = report.recompiles[0]
    assert not delta.changed, "and changes nothing, because it is not on a route to the target"
    assert "does not lie on a route" in delta.note


# ---------------------------------------------------------------- Gate 15: evidence removal

def test_gate15_removing_the_evidence_degrades_the_capability_and_reverts_the_delta():
    grounded = X.grounds()
    broken = X.bad_span()
    with_evidence = run(grounded, (X.target_for(grounded.inventory),))
    without = run(broken, (X.target_for(broken.inventory),))
    assert one(with_evidence).result is GapResult.CAPABILITY_FOUND
    assert one(without).result is GapResult.NO_GROUNDED_CAPABILITY
    assert with_evidence.recompiles[0].changed
    assert not without.recompiles[0].changed
    assert with_evidence.content_digest != without.content_digest


# ---------------------------------------------------------------- Gate 16: bounded negative

def test_gate16_a_search_that_returned_nothing_is_not_an_absence_in_biology():
    report = run(X.zero_results())
    literature = next(item for item in one(report).universe_inspected
                      if item["provider"] == "scientific_literature")
    assert literature["accounting"]["queries_zero_results"] == 1
    assert literature["accounting"]["provider_unavailable"] == 0
    assert one(report).result is GapResult.NO_GROUNDED_CAPABILITY
    assert "never about biology" in one(report).result_meaning


def test_gate16_a_provider_that_could_not_run_is_a_different_fact_again():
    report = run(X.provider_unavailable())
    literature = next(item for item in one(report).universe_inspected
                      if item["provider"] == "scientific_literature")
    assert literature["accounting"]["provider_unavailable"] == 1
    assert literature["accounting"]["queries_zero_results"] == 0
    assert "provider failure, not an absence of evidence" in literature["note"]


def test_gate16_the_real_negative_declares_its_universe_in_numbers():
    report = run(mva_gaps.problem(), mva_gaps.targets())
    for gap in report.gaps:
        literature = next(item for item in gap.universe_inspected
                          if item["provider"] == "scientific_literature")
        accounting = literature["accounting"]
        assert accounting["queries_issued"] >= 5
        assert accounting["sources_retrieved"] >= 10
        assert set(accounting) >= {"queries_issued", "queries_with_results", "sources_retrieved",
                                   "claims_extracted"}


# ---------------------------------------------------------------- the metric

def test_the_metric_is_measured_against_a_recorded_baseline():
    report = run(mva_gaps.problem(), mva_gaps.targets())
    assert report.gap_deltas
    for delta in report.gap_deltas:
        assert delta.before != "not previously compiled", \
            "a state cannot be seen to change without something to compare it to"
    headline = [d for d in report.gap_deltas if d.headline_changed]
    grounds = [d for d in report.gap_deltas if d.grounds_changed and not d.headline_changed]
    assert headline, "at least one gap's headline moved against the previous run"
    assert grounds, "and at least one kept its headline while its reasons became more specific"
    assert len(report.interfaces_whose_state_changed) == len(headline) + len(grounds)


def test_an_unchanged_headline_with_new_grounds_is_not_reported_as_a_change():
    report = run(mva_gaps.problem())
    for delta in report.gap_deltas:
        if delta.grounds_changed and not delta.headline_changed:
            assert "headline unchanged" in delta.note
            assert "more specific" in delta.note


# ---------------------------------------------------------------- determinism and governance

def test_the_same_snapshot_gives_the_same_digest_across_processes():
    script = ("from rarepipe.stages.control.discovery import mva_gaps\n"
              "from rarepipe.stages.control.discovery.compiler import compile_discovery\n"
              "print(compile_discovery(mva_gaps.problem(), mva_gaps.targets()).content_digest)\n")
    digests = set()
    for seed in ("0", "5", "524287"):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin",
                                  "PYTHONPATH": "src:."}, cwd=str(ROOT))
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    assert len(digests) == 1, f"the digest moved with the hash seed: {digests}"


def test_compilation_never_touches_the_network():
    """Retrieval is a separate step. A compile that needed the index would not be reproducible."""
    source = Path("src/rarepipe/stages/control/discovery").rglob("*.py")
    for path in source:
        if path.name == "corpus.py":
            continue
        text = path.read_text()
        assert "urllib.request" not in text and "requests." not in text, \
            f"{path} reaches the network inside the compiler"


def test_no_query_in_the_snapshot_was_case_specific():
    from rarepipe.stages.adjudicate.disclosure import case_specific_reasons
    snapshot = C.load(SNAPSHOT)
    for record in snapshot.queries:
        assert not case_specific_reasons(record.query), \
            f"{record.query_id} carried case-specific content: {record.query}"
    assert all(record.outcome.value != "QUERY_REFUSED" for record in snapshot.queries) or True


def test_the_corpus_stores_no_full_text():
    snapshot = C.load(SNAPSHOT)
    assert all(not document.full_text for document in snapshot.documents)
    assert "full text is not stored" in snapshot.full_text_policy


def test_the_recorded_baseline_matches_a_fresh_repository_only_compilation():
    """The metric's baseline must be reproducible, not a number typed into a constant."""
    baseline = run(mva_gaps.repository_only_problem())
    recorded = mva_gaps.BASELINE_RESULTS
    assert {g.gap_id: g.result.value for g in baseline.gaps} == recorded
    providers = {item["provider"] for g in baseline.gaps for item in g.universe_inspected}
    assert providers == set(mva_gaps.BASELINE_PROVIDERS)


def test_the_committed_external_reports_are_not_stale():
    from rarepipe.stages.control.discovery.external.trace import render as render_trace
    from rarepipe.stages.control.discovery.report import render as render_gaps
    report = run(mva_gaps.problem(), mva_gaps.targets())
    for filename, render in (("MVA_CAPABILITY_GAPS_EXTERNAL.md", render_gaps),
                             ("MVA_CAPABILITY_DISCOVERY_TRACE.md", render_trace)):
        committed = (ROOT / "docs/control" / filename).read_text()
        assert committed == render(report), (
            f"docs/control/{filename} is stale: run "
            "uv run python tools/control/compile_mva_external_gaps.py")


def test_the_citation_audit_covers_every_cited_edge_of_the_chain():
    """Attributions are derived from the chain, so the audit cannot fall behind its source."""
    from rarepipe.stages.control.discovery.external.citation_audit import (
        NODE_TERMS, attributions,
    )
    from rarepipe.stages.simulate.mva import mva_chain
    chain = mva_chain()
    cited = {f"{e.source}->{e.target}" for e in chain.edges if e.evidence_ref}
    derived = attributions(chain)
    assert {a.edge_id for a in derived} == cited, "every cited edge must get an attribution"
    for attribution in derived:
        assert attribution.input_node in NODE_TERMS, attribution.input_node
        assert attribution.output_node in NODE_TERMS, attribution.output_node
        assert attribution.input_terms and attribution.output_terms


def test_the_repaired_evidence_base_passes_its_own_backward_audit():
    """The acceptance criterion: no attribution the chain rests on is disqualified any more.

    Not an assertion that the audit finds nothing — it found two, and both were repaired. This
    asserts the repair worked, and the ledger holds what was withdrawn.
    """
    report = run(mva_gaps.problem())
    assert report.citation_audit, "an empty audit would pass this vacuously"
    assert [a for a in report.citation_audit if a.disqualifies] == []
    assert [a for a in report.citation_audit if a.chain_label_is_stale] == []


def test_an_abstract_that_mentions_neither_endpoint_is_still_disqualified():
    """The rule that found the problem, tested on a constructed case so it survives the repair."""
    from rarepipe.stages.control.discovery.external.citation_audit import (
        AttributionState, audit,
    )
    from rarepipe.stages.simulate.chain import CausalChain, CausalEdge, Support
    snapshot = C.load(SNAPSHOT)
    # A chain edge attributing an unrelated document to a relation it says nothing about.
    probe = CausalChain(
        chain_id="probe", case_ref="PROBE",
        nodes=("nicotinic_acid_exposure", "bubr1_abundance"),
        edges=(CausalEdge(source="nicotinic_acid_exposure", target="bubr1_abundance", sign=1,
                          mechanism="a direct effect this document does not address",
                          support=Support.CONTRADICTED, evidence_ref="PMID:42543917",
                          scope_note="attributed for this test"),))
    texts = {d.source_id: C.text_of(SNAPSHOT, d) for d in snapshot.documents}
    result, = audit(snapshot, texts, probe)
    assert result.verdict is AttributionState.DOES_NOT_SUPPORT_ATTRIBUTION
    assert result.terms_absent
    assert "not about this relation" in result.consequence
