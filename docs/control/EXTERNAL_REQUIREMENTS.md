# External evidence (Phase 1) — requirements and where each is enforced

Condensed from the *Biological Capability Universe, Phase 1* PRD that Xavier supplied. The original
document is not in the repository; this file records its normative requirements and maps each to the
test that enforces it. One test asserts every reference here resolves; another asserts every gate is
cited.

Build authorization for that PRD is **Phase 1 only**. See
[`EXTERNAL_DESIGN.md`](EXTERNAL_DESIGN.md) for the formalism and what the run found.

## Proof gates

| Gate | Requirement | Enforced by |
|---|---|---|
| 1 | a query returns a real, verifiable source | `tests/test_external_gates.py::test_gate1_the_snapshot_holds_real_verifiable_sources` |
| 1b | supporting assertion | `tests/test_external_gates.py::test_gate1_queries_are_functional_not_gene_name_lookups` |
| 1c | supporting assertion | `tests/test_external_gates.py::test_gate1_the_plan_records_what_it_deliberately_does_not_search_by` |
| 2 | a claim points at the real passage that supports it | `tests/test_external_gates.py::test_gate2_every_extracted_claim_points_at_a_real_passage` |
| 2b | supporting assertion | `tests/test_external_gates.py::test_gate2_a_paraphrase_is_not_a_span` |
| 3 | an invented citation is refused | `tests/test_external_gates.py::test_gate3_a_claim_citing_a_document_the_corpus_lacks_is_reported_not_dropped` |
| 4 | a real paper is not evidence for a different input | `tests/test_external_gates.py::test_gate4_a_real_source_is_not_evidence_for_a_different_input` |
| 5 | a related readout is not the required output | `tests/test_external_gates.py::test_gate5_a_real_source_is_not_evidence_for_a_different_output` |
| 6 | a real relation with the opposite or wrong kind of effect is refused | `tests/test_external_gates.py::test_gate6_a_reported_increase_is_not_a_restored_function` |
| 6b | supporting assertion | `tests/test_external_gates.py::test_gate6_the_state_specification_names_what_a_naive_reading_would_accept` |
| 6c | supporting assertion | `tests/test_external_gates.py::test_gate6_no_global_effect_to_state_rule_exists` |
| 7 | a correct relation in a different context is a transfer gap, not a grounding | `tests/test_external_gates.py::test_gate7_a_relation_shown_elsewhere_is_a_transfer_gap_not_a_grounding` |
| 7b | supporting assertion | `tests/test_external_gates.py::test_gate7_the_compartment_transfer_rule_is_explicit` |
| 7c | supporting assertion | `tests/test_external_gates.py::test_gate7_transfer_gaps_are_objects_with_what_is_missing` |
| 8 | an external candidate that returns causally to the forbidden node is not a bypass | `tests/test_external_gates.py::test_gate8_an_external_candidate_declaring_a_forbidden_dependency_is_not_a_bypass` |
| 8b | supporting assertion | `tests/test_external_gates.py::test_gate8_a_new_entity_does_not_get_independence_for_free` |
| 8c | supporting assertion | `tests/test_external_gates.py::test_gate8_a_source_that_states_independence_can_satisfy_a_bypass_gap` |
| 8d | supporting assertion | `tests/test_external_gates.py::test_gate8_ancestry_is_scoped_to_the_candidates_own_mechanism` |
| 9 | an association cannot satisfy a causal capability | `tests/test_external_gates.py::test_gate9_an_association_cannot_satisfy_a_causal_capability` |
| 9b | supporting assertion | `tests/test_external_gates.py::test_gate9_every_real_claim_carries_a_causal_grade` |
| 10 | relevant contradicting evidence appears in the report | `tests/test_external_gates.py::test_gate10_a_contradicting_claim_stays_visible_in_the_report` |
| 10b | supporting assertion | `tests/test_external_gates.py::test_gate10_each_real_claim_records_what_its_own_source_does_not_establish` |
| 11 | a previously absent capability enters the registry from external evidence | `tests/test_external_gates.py::test_gate11_an_external_source_can_produce_a_previously_absent_capability` |
| 12 | the new capability recompiles the architecture automatically | `tests/test_external_gates.py::test_gate12_and_13_the_new_capability_recompiles_the_architecture_automatically` |
| 13 | the realization state changes, with the evidence carried into its inventory | `tests/test_external_gates.py::test_gate13_the_grounded_claim_enters_the_realization_inventory_with_its_evidence` |
| 14 | a capability that lands nowhere does not change the architecture | `tests/test_external_gates.py::test_gate14_a_capability_that_lands_nowhere_does_not_change_the_architecture` |
| 15 | removing the evidence degrades the capability and reverts the delta | `tests/test_external_gates.py::test_gate15_removing_the_evidence_degrades_the_capability_and_reverts_the_delta` |
| 16 | a negative result declares exactly what universe was inspected | `tests/test_external_gates.py::test_gate16_a_search_that_returned_nothing_is_not_an_absence_in_biology` |
| 16b | supporting assertion | `tests/test_external_gates.py::test_gate16_a_provider_that_could_not_run_is_a_different_fact_again` |
| 16c | supporting assertion | `tests/test_external_gates.py::test_gate16_the_real_negative_declares_its_universe_in_numbers` |

## Invariants and governance

| Requirement | Enforced by |
|---|---|
| section 20: the metric is a change of epistemic state, measured against the previous run | `tests/test_external_gates.py::test_the_metric_is_measured_against_a_recorded_baseline` |
| section 20: a headline that holds while the reasons change is reported as a different thing | `tests/test_external_gates.py::test_an_unchanged_headline_with_new_grounds_is_not_reported_as_a_change` |
| invariant 19: same evidence and version, same verdict | `tests/test_external_gates.py::test_the_same_snapshot_gives_the_same_digest_across_processes` |
| retrieval is a separate step; a compile that needed the index would not be reproducible | `tests/test_external_gates.py::test_compilation_never_touches_the_network` |
| invariant 17 and section 26: the case-identity guard is not lifted by this phase | `tests/test_external_gates.py::test_no_query_in_the_snapshot_was_case_specific` |
| the snapshot's scope is stated and enforced, which bounds what can be grounded | `tests/test_external_gates.py::test_the_corpus_stores_no_full_text` |
| the baseline stays reproducible rather than becoming a constant | `tests/test_external_gates.py::test_the_recorded_baseline_matches_a_fresh_repository_only_compilation` |
| invariant 18: new evidence forces a staleness evaluation | `tests/test_external_gates.py::test_the_committed_external_reports_are_not_stale` |
| the audit's transcribed terms cannot drift from the chain they came from | `tests/test_external_gates.py::test_the_citation_audit_tracks_the_chains_own_edges` |
| the grounding rule applied backwards to the repository's own citations | `tests/test_external_gates.py::test_the_audit_finds_the_attribution_that_cannot_hold` |

## Mutation testing (PRD section 40)

Green tests were not accepted as evidence. Each of the fourteen properties the PRD names was broken
deliberately, plus two more — independence-as-default and evidence carried into the recompile. All
sixteen mutations were caught: source resolution, span grounding, entity identity, input match,
output match, direction, causal type, compartment, context, forbidden ancestry,
independence-as-default, contradiction propagation, architecture recompilation, evidence carried into
the recompile, digest staleness, corpus accounting.

## Operational counts, which are not success metrics

The gap reports carry providers used, queries issued, sources retrieved and screened, claims
extracted and capabilities accepted. The PRD is explicit that these are process metrics. The
scientific metric is the number of previously-open functional interfaces whose epistemic state
changed, and it is measured against a recorded, re-runnable baseline.

## What is not built (PRD section 45)

No universal biomedical knowledge graph, no indiscriminate literature ingestion, no catalogue of all
drugs or genes or molecules, no global combinatorial search, no docking, no molecular simulation or
dynamics, no clinical prediction, no therapeutic ranking, no invented probabilities, no new
mathematical solvers. The structured-mechanism and perturbation-evidence providers from sections 11
and 12 are not implemented either: `CapabilitySourceProvider` is the seam they would arrive behind,
and adding one requires no change to the validation layer.

## Not enforced here

- Whether a retrieved paper's own conclusion is correct. The layer checks that a claim is about what
  it says it is about, in the context it says, and refuses it otherwise.
- Whether a mechanism absent from this corpus exists in biology. Every negative names the providers
  searched and the size of their corpora.
- Whether a claim's support in a figure or methods section would change the verdict. The snapshot
  stores abstracts only, which is stated in every report.
