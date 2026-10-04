# Capability gap discovery — requirements and where each is enforced

Condensed from the *Capability Gap Discovery & Grounding Compiler* PRD (phase 2 of the physical
realization compiler) that Xavier supplied. The original document is not in the repository; this file
records its normative requirements and maps each to the test that enforces it. One test asserts every
reference here resolves; another asserts every gate is cited.

Build authorization for that PRD is **this phase only** — no exhaustive catalogue of genes, drugs,
molecules or proteins. See [`DISCOVERY_DESIGN.md`](DISCOVERY_DESIGN.md) for the formalism.

## Gap result classes

| Class | Exercised by |
|---|---|
| `CAPABILITY_FOUND` | `tests/test_discovery_gates.py::test_gate1_a_piece_that_exactly_satisfies_the_gap_is_found_and_grounded` |
| `PARTIAL_CAPABILITY` | `tests/test_discovery_gates.py::test_gate8_a_chain_with_an_ungrounded_link_is_partial_and_names_the_link` |
| `ONLY_DEPENDENT_CAPABILITIES_FOUND` | `tests/test_discovery_gates.py::test_gate4_a_candidate_whose_mechanism_runs_through_the_forbidden_node_is_not_a_bypass` |
| `CONTEXT_ONLY_CAPABILITY` | `tests/test_discovery_gates.py::test_gate5_a_right_mechanism_in_the_wrong_system_is_context_only` |
| `CONTRADICTED_CAPABILITY` | `tests/test_discovery_gates.py::test_gate9_a_null_or_opposite_result_appears_as_a_contradiction` |
| `NO_GROUNDED_CAPABILITY` | `tests/test_discovery_gates.py::test_gate3_a_faithful_source_for_the_opposite_effect_does_not_answer_the_gap` |

## Proof gates

| Gate | Requirement | Enforced by |
|---|---|---|
| 1 | a piece that exactly satisfies the gap is found and grounded | `tests/test_discovery_gates.py::test_gate1_a_piece_that_exactly_satisfies_the_gap_is_found_and_grounded` |
| 1b | supporting assertion | `tests/test_discovery_gates.py::test_gate1_the_three_verification_levels_are_recorded_separately` |
| 2 | the right output from the wrong input is refused | `tests/test_discovery_gates.py::test_gate2_a_capability_cannot_cite_a_claim_about_a_different_input` |
| 3 | the right output with the opposite sign is refused | `tests/test_discovery_gates.py::test_gate3_a_faithful_source_for_the_opposite_effect_does_not_answer_the_gap` |
| 4 | a candidate routing through the forbidden node is not a bypass | `tests/test_discovery_gates.py::test_gate4_a_candidate_whose_mechanism_runs_through_the_forbidden_node_is_not_a_bypass` |
| 4b | supporting assertion | `tests/test_discovery_gates.py::test_gate4_the_result_is_sharper_than_finding_nothing` |
| 5 | right mechanism, incompatible system | `tests/test_discovery_gates.py::test_gate5_a_right_mechanism_in_the_wrong_system_is_context_only` |
| 6 | an effect shown with a different agent is not inherited | `tests/test_discovery_gates.py::test_gate6_an_effect_shown_with_a_different_agent_is_not_inherited` |
| 7 | the circulating pool is not the intracellular pool | `tests/test_discovery_gates.py::test_gate7_the_circulating_pool_is_not_the_intracellular_pool` |
| 7b | supporting assertion | `tests/test_discovery_gates.py::test_gates5_to_7_each_dimension_fails_on_its_own` |
| 8 | a chain with an ungrounded link is partial and names the link | `tests/test_discovery_gates.py::test_gate8_a_chain_with_an_ungrounded_link_is_partial_and_names_the_link` |
| 8b | supporting assertion | `tests/test_discovery_gates.py::test_gate8_an_intermediate_claim_resolves_rather_than_counting_as_fabricated` |
| 9 | a null or opposite result appears as a contradiction | `tests/test_discovery_gates.py::test_gate9_a_null_or_opposite_result_appears_as_a_contradiction` |
| 10 | an invented entity, claim or reference does not enter the registry | `tests/test_discovery_gates.py::test_gate10_an_invented_reference_does_not_enter_the_registry` |
| 10b | supporting assertion | `tests/test_discovery_gates.py::test_gate10_an_invented_entity_citing_a_real_claim_is_rejected_too` |
| 10c | supporting assertion | `tests/test_discovery_gates.py::test_gate10_a_candidate_with_no_source_is_rejected` |
| 10d | supporting assertion | `tests/test_discovery_gates.py::test_gate10_no_invented_candidate_produced_a_capability` |
| 10e | supporting assertion | `tests/test_discovery_gates.py::test_gate10_an_agent_cannot_propose_a_grounded_capability_at_all` |
| 10f | supporting assertion | `tests/test_discovery_gates.py::test_gate10_the_builder_refuses_a_candidate_that_did_not_pass` |
| 10g | supporting assertion | `tests/test_discovery_gates.py::test_gate10_a_capability_cannot_be_constructed_with_another_epistemic_type` |
| 11 | grounding a valid capability changes the compiled realization automatically | `tests/test_discovery_gates.py::test_gate11_grounding_a_capability_changes_the_compiled_realization` |
| 11b | supporting assertion | `tests/test_discovery_gates.py::test_gate11_the_recompile_happens_without_anybody_editing_a_realization` |
| 11c | supporting assertion | `tests/test_discovery_gates.py::test_gate11_an_unchanged_result_is_stated_rather_than_omitted` |
| 12 | removing the grounding claim degrades the result | `tests/test_discovery_gates.py::test_gate12_removing_the_grounding_claim_degrades_the_result` |
| 12b | supporting assertion | `tests/test_discovery_gates.py::test_gate12_an_unverified_citation_caps_the_result_at_conditional` |
| 13 | the real bypass gap runs and explains why it stays open | `tests/test_discovery_gates.py::test_gate13_the_bypass_gaps_run_and_explain_why_they_stay_open` |
| 13b | supporting assertion | `tests/test_discovery_gates.py::test_gate13_the_burden_differs_across_the_three_bypass_gaps` |
| 14 | the intracellular cofactor gap produces a grounded verdict | `tests/test_discovery_gates.py::test_gate14_the_cofactor_entry_gap_produces_a_grounded_verdict` |
| 14b | supporting assertion | `tests/test_discovery_gates.py::test_gate14_the_previous_unknown_became_a_named_context_mismatch` |
| 15 | same gaps, evidence and versions give the same digest | `tests/test_discovery_gates.py::test_gate15_the_same_gaps_and_evidence_give_the_same_digest_across_processes` |
| 15b | supporting assertion | `tests/test_discovery_gates.py::test_gate15_the_digest_covers_the_gap_contents_not_only_the_headline` |
| 15c | supporting assertion | `tests/test_discovery_gates.py::test_gate15_the_digest_moves_when_the_evidence_moves` |

## Invariants and governance

The PRD's eighteen invariants. Several are inherited from earlier phases and enforced by their own
suites; the ones this phase adds or strengthens are below.

| Requirement | Enforced by |
|---|---|
| invariant 1, narrowly: a mislabelled proposal keeps its content and is typed down | `tests/test_discovery_gates.py::test_a_mislabelled_proposal_is_still_typed_down_rather_than_discarded` |
| invariant 12: nothing absent from the registry implies biological non-existence | `tests/test_discovery_gates.py::test_the_real_run_grounds_nothing_and_says_what_universe_was_searched` |
| invariant 12: every negative result class names the universe, not the world | `tests/test_discovery_gates.py::test_a_negative_result_never_claims_biology` |
| invariant 17: case data stays inside its governance boundary | `tests/test_discovery_gates.py::test_no_case_level_genomic_content_reaches_a_gap_report` |
| invariant 13: no result constitutes a therapeutic recommendation | `tests/test_discovery_gates.py::test_the_report_carries_no_recommendation_and_cannot_be_reworded` |
| invariant 4: an agent's hypothesis does not become causality | `tests/test_discovery_gates.py::test_a_mechanism_hypothesis_cannot_claim_to_be_anything_stronger` |
| invariant 15: changed evidence forces recompilation | `tests/test_discovery_gates.py::test_the_committed_gap_report_is_not_stale` |

## Mutation testing (PRD section 27)

Green tests were not accepted as evidence. Each property the PRD names was broken deliberately and
the matching gate had to fail: input matching, output matching, direction, context, forbidden
ancestry, provenance, contradiction handling, registry self-grading, the recompile trigger and
staleness. Eleven of twelve were caught immediately. The staleness mutation was not — the digest test
only detected changes visible in the headline fields — so
`tests/test_discovery_gates.py::test_gate15_the_digest_covers_the_gap_contents_not_only_the_headline`
was added for two runs that reach the same verdict for different reasons. With it, all twelve are
caught.

## What is not built (PRD section 29)

No catalogue of all human genes, all drugs or all known molecules. No global chemical search engine,
no molecular docking, no structure prediction, no molecular dynamics, no universal biomedical
knowledge graph, no thousands of agents, no virtual combinatorial screening, no invented
probabilities of success, no recommendation engine. Combinations are not enumerated: composition is
allowed only where an explicit gap requires more than one capability, so nothing searches
`C(N,2)` over the registry.

`CapabilitySourceProvider` is the seam each of those would arrive behind. Two implementations exist,
and neither can invent anything.

## Not enforced here

- Whether the five citations the corpus rests on are correct. Two have no retrieval record, and
  anything resting on them is capped at `CONDITIONAL` rather than resolved.
- Whether a capability class that no provider holds a claim about exists in biology. The compiler
  states the corpus it searched and declines to generalise beyond it.
- Whether the mechanism classes proposed as search directions are biologically sensible. They are
  typed `MECHANISM_HYPOTHESIS` and name no entities, because no corpus here could support one.
