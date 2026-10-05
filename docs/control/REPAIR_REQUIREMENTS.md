# Evidence repair — requirements and where each is enforced

Condensed from the *Evidence Seed Repair & Full Recompile* instructions that Xavier supplied. The
original document is not in the repository; this file records its normative requirements and maps
each to the test that enforces it. One test asserts every reference here resolves; another asserts
every test in the repair suite is cited.

Build authorization was **repair and recompile only** — no new discovery features, providers, corpus,
solvers or architectures. See [`REPAIR_DESIGN.md`](REPAIR_DESIGN.md) for what the recompile found.

## Requirements

| PRD section | Requirement | Enforced by |
|---|---|---|
| 2, 14 | the incorrect attribution no longer sustains any verdict | `tests/test_evidence_repair.py::test_the_disqualified_attribution_is_not_accepted_when_validated` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_no_contradiction_survives_the_withdrawal_of_its_only_evidence` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_withdrawn_attribution_appears_nowhere_as_live_evidence` |
| 3 | history is preserved, not overwritten | `tests/test_evidence_repair.py::test_the_history_is_preserved_rather_than_overwritten` |
| 4 | the intended reference was searched for, and no substitute was invented | `tests/test_evidence_repair.py::test_no_substitute_reference_was_invented` |
| 5, 15 | the human trial is grounded at the context it supports and no wider | `tests/test_evidence_repair.py::test_the_human_trial_is_groundable_at_the_tissue_it_was_measured_in` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_human_trial_does_not_satisfy_the_patient_cell_context` |
| 6 | the compartment blocker is replaced by a transfer gap, not kept as if nothing changed | `tests/test_evidence_repair.py::test_the_transfer_gap_replaced_the_compartment_blocker` |
| 7 | every load-bearing citation was audited, not only the one that failed | `tests/test_evidence_repair.py::test_the_backward_audit_covers_every_load_bearing_citation` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_audit_says_which_of_its_checks_a_machine_cannot_make` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_second_disqualified_attribution_was_found_by_auditing_everything` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_r4s_open_question_was_answered_by_reading_the_whole_article` |
| 9, 10, 12 | every dependent layer was recomputed in dependency order, and each explains itself | `tests/test_evidence_repair.py::test_every_layer_in_the_dependency_order_is_recomputed` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_an_unchanged_layer_still_explains_itself` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_recompile_reads_fresh_compilations_not_recorded_conclusions` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_a_digest_only_move_is_reported_as_such` |
| 17 | same evidence and versions produce the same verdicts and digests | `tests/test_evidence_repair.py::test_the_repaired_pipeline_is_deterministic_across_processes` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_committed_delta_reports_are_not_stale` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_every_recorded_baseline_digest_is_corroborated_by_git` |
|  | supporting assertion | `tests/test_evidence_repair.py::test_the_baseline_lives_in_data_not_in_source` |
| 18 | no result is a therapeutic recommendation | `tests/test_evidence_repair.py::test_the_human_evidence_never_travels_without_its_limits` |
| 19 | the binding constraint on the case did not move, and that is reported | `tests/test_evidence_repair.py::test_the_binding_constraint_on_the_case_did_not_move` |

## Section 13 — tests that were rewritten rather than updated

The instruction was explicit: do not write tests that protect the historical conclusion. Five
existing tests had to change, and how they changed matters.

| Test | Was | Is |
|---|---|---|
| `tests/test_simulate_chain.py::test_a_null_result_on_a_shorter_route_stays_visible` | asserted the case's own route is contradicted | asserts the property on a constructed chain |
| `tests/test_simulate_chain.py::test_propagation_excludes_contradicted_routes_and_caps_on_contributors` | asserted the case's own exclusion | asserts the property on a constructed chain |
| `tests/test_simulate_chain.py::test_every_unmeasured_rate_is_an_explicit_interval` | asserted a count of six | asserts the rule, for any count |
| `tests/test_simulate_engine.py::test_an_unvalued_parameter_is_never_collapsed_to_a_midpoint` | asserted a count of six | asserts the rule, for any count |
| `tests/test_simulate_validate.py::test_a_chain_claiming_more_than_its_source_is_caught` | was `test_dropping_the_null_result_is_caught`, validating the chain against a null nobody published | asserts the same property on a case whose source exists |

Two tests were added to state what the repair actually did, rather than leaving it implicit:
`tests/test_simulate_chain.py::test_withdrawing_a_refutations_only_citation_removes_the_refutation`
and
`tests/test_simulate_chain.py::test_the_cases_own_propagation_now_carries_the_withdrawn_route_as_an_assertion`.
One more guards the honesty of the new human-supported step:
`tests/test_simulate_chain.py::test_a_human_supported_step_never_travels_without_the_tissue_it_was_measured_in`.

## Section 16 — mutation testing

Nine controls broken deliberately, all caught: re-associating the withdrawn citation with its old
edge, letting a source with no relevant terms pass, widening skeletal muscle to the required cell
system, removing the context check, echoing the baseline back instead of recompiling, allowing a
contradicted verdict with no evidence behind it, letting a downstream artifact keep a constant
digest, treating tissue evidence as patient-derived-cell evidence, and dropping the transfer gap
once the compartment matches.

Two needed re-aiming. The chain carries two identical evidence-required guards, on `Parameter` and
on `CausalEdge`, and the first attempt mutated the wrong one: the control was never inert, the
mutation was. The other needed an assertion that the delta's "after" state is a fresh observation
rather than the recorded baseline, which the suite had not been making.

## Section 20 — acceptance criteria

| Criterion | Status |
|---|---|
| the incorrect attribution no longer sustains any verdict | met; the citation appears in no live module |
| `PMID:32386566` grounded with its limited context | met; human skeletal muscle, with a transfer gap for the cell type |
| all foundational evidence passed a backward audit | met; 13 attributions, 0 disqualified, 0 stale labels |
| all downstream artifacts recompiled from scratch | met; 11 layers in dependency order |
| no downstream verdict edited by hand | met; every observable is read from a fresh compilation |
| a complete before/after delta exists | met; two generated reports, both staleness-checked |
| mutation testing shows the controls are load-bearing | met; nine mutations, all caught |
| all artifacts have coherent new digests | met; every generated map regenerated, and each baseline digest is corroborated against the artifact committed at its commit |
| any change of scientific frontier appears explicitly | met; the one unchanged layer and the unmoved binding constraint are both stated |

## Not enforced here

- Whether the retired attributions should be replaced by full-text retrieval rather than left as
  assertions. `REPAIR_R4` carries that question for a scientist; the code took the conservative
  action of weakening an unsupported label rather than keeping it.
- Whether the human trial's result would transfer to the relevant cells. That is the transfer gap,
  and it is an experiment, not an inference.
- Whether the three `ATTRIBUTION_AMBIGUOUS` references support the relations attributed to them.
  Only abstracts are stored, so the audit records that it cannot isolate them.
