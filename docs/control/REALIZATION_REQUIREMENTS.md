# Physical realization compiler — requirements and where each is enforced

Condensed from the *Physical Realization Compiler, Part 1* PRD that Xavier supplied. The original
document is not in the repository; this file records its normative requirements and maps each to the
code and test that enforces it. A test fails if any test referenced here stops existing, and another
fails if a gate stops being cited.

Build authorization for that PRD is **Part 1 only**: the global building-block universe is not
opened. See [`REALIZATION_DESIGN.md`](REALIZATION_DESIGN.md) for the formalism.

## Output classes

| Class | Meaning | Exercised by |
|---|---|---|
| `GROUNDED_REALIZATION_CANDIDATE` | real components with sufficient evidence for every step | `tests/test_realization_gates.py::test_gate1_a_transformation_with_a_known_mechanism_compiles_to_a_grounded_chain` |
| `PARTIAL_REALIZATION` | some grounded, the missing piece named exactly | `tests/test_realization_gates.py::test_gate4_a_chain_with_a_hole_is_partial_and_names_the_hole` |
| `NO_GROUNDED_REALIZATION` | nothing evidence-backed found, with the reason | `tests/test_realization_gates.py::test_gate11_the_bypass_runs_end_to_end_and_says_exactly_what_is_missing` |
| `CONTEXT_MISMATCH` | the mechanism exists, not in the required context | `tests/test_realization_gates.py::test_gate3_support_from_a_different_agent_is_not_a_realization` |
| `EVIDENCE_INSUFFICIENT` | plausible, but the evidence does not entitle it | `tests/test_realization_gates.py::test_gate5_downgrading_the_evidence_changes_the_verdict` |
| `UNSAFE_REALIZATION` | the function is produced by entering a forbidden state | `tests/test_realization_gates.py::test_gate8_producing_the_function_by_killing_the_cells_is_rejected` |
| `NOT_REPRESENTABLE` | the mechanism needs variables the state model lacks | `src/rarepipe/stages/control/realization/checks.py` (`assess`, unrepresentable branch) |

## Proof gates

| Gate | Requirement | Enforced by |
|---|---|---|
| 1 | a transformation with a known mechanism compiles | `tests/test_realization_gates.py::test_gate1_a_transformation_with_a_known_mechanism_compiles_to_a_grounded_chain` |
| 1b | a grounded chain is still not a treatment | `tests/test_realization_gates.py::test_gate1_a_grounded_chain_is_still_not_a_treatment` |
| 2 | a component with the opposite effect is rejected | `tests/test_realization_gates.py::test_gate2_a_component_with_the_opposite_effect_is_rejected` |
| 2b | the direction check reads the cited claim, not the declaration | `tests/test_realization_gates.py::test_gate2_the_direction_check_reads_the_cited_claim_not_the_declaration` |
| 3 | support from a different agent is not a realization | `tests/test_realization_gates.py::test_gate3_support_from_a_different_agent_is_not_a_realization` |
| 3b | a different system is a transfer gap, not a pass | `tests/test_realization_gates.py::test_gate3_support_from_a_different_system_is_a_transfer_gap_not_a_pass` |
| 3c | matching the measured agent lifts that penalty and only that one | `tests/test_realization_gates.py::test_gate3_matching_the_agent_the_measurement_used_lifts_that_penalty_only` |
| 4 | a chain with a hole is partial and names the hole | `tests/test_realization_gates.py::test_gate4_a_chain_with_a_hole_is_partial_and_names_the_hole` |
| 5 | downgrading the evidence changes the verdict | `tests/test_realization_gates.py::test_gate5_downgrading_the_evidence_changes_the_verdict` |
| 5b | an unverified citation is conditional, not supported | `tests/test_realization_gates.py::test_gate5_an_unverified_citation_is_conditional_not_supported` |
| 6 | removing the source prevents treating a step as grounded | `tests/test_realization_gates.py::test_gate6_removing_the_source_prevents_treating_a_step_as_grounded` |
| 7 | an unnecessary component is detected | `tests/test_realization_gates.py::test_gate7_an_unnecessary_component_is_detected` |
| 7b | a minimal chain is not flagged | `tests/test_realization_gates.py::test_gate7_a_minimal_chain_is_not_flagged` |
| 8 | producing the function by killing the cells is rejected | `tests/test_realization_gates.py::test_gate8_producing_the_function_by_killing_the_cells_is_rejected` |
| 8b | a capability touching a safety variable must declare its value | `tests/test_realization_gates.py::test_gate8_a_capability_touching_a_safety_variable_must_say_what_it_drives_it_to` |
| 9 | a caveated claim requires the observable that would exclude it | `tests/test_realization_gates.py::test_gate9_a_caveated_claim_requires_the_observable_that_would_exclude_it` |
| 9b | naming and measuring the observable restores the verdict | `tests/test_realization_gates.py::test_gate9_naming_and_measuring_the_observable_restores_the_verdict` |
| 9c | naming an observable nobody measures does not | `tests/test_realization_gates.py::test_gate9_naming_an_observable_nobody_measures_does_not_restore_it` |
| 10 | a step naming an unregistered primitive is refused | `tests/test_realization_gates.py::test_gate10_a_step_naming_an_unregistered_primitive_is_refused` |
| 10b | a capability citing a claim nobody made is refused | `tests/test_realization_gates.py::test_gate10_a_capability_citing_a_claim_nobody_made_is_refused` |
| 10c | a capability citing a claim about a different input is flagged | `tests/test_realization_gates.py::test_gate10_a_capability_citing_a_claim_about_a_different_input_is_flagged` |
| 11 | the bypass runs end to end and says what is missing | `tests/test_realization_gates.py::test_gate11_the_bypass_runs_end_to_end_and_says_exactly_what_is_missing` |
| 11b | the burden is read from what each function would replace | `tests/test_realization_gates.py::test_gate11_the_burden_is_read_from_what_each_function_would_replace` |
| 11c | a transformation with no direct chain recurses | `tests/test_realization_gates.py::test_gate11_a_transformation_with_no_direct_chain_recurses_into_what_it_reduces_to` |
| 11d | the abundance route discriminates rather than refusing everything | `tests/test_realization_gates.py::test_gate11_the_abundance_route_discriminates_rather_than_refusing_everything` |
| 11e | nothing in the registry cites a claim the repository lacks | `tests/test_realization_gates.py::test_gate11_nothing_in_the_mva_registry_cites_a_claim_the_repository_lacks` |
| 12 | same inputs and versions give the same digest | `tests/test_realization_gates.py::test_gate12_the_same_inputs_give_the_same_digest_across_processes` |

## The evidence inventory

The requirement that nothing here invents biology is structural, not a matter of care.

| Requirement | Enforced by |
|---|---|
| the inventory is the repository's own chain, not a copy that can drift | `tests/test_realization_gates.py::test_the_evidence_inventory_is_the_repositorys_own_chain` |
| the transcribed contexts still match the scope notes they came from | `tests/test_realization_gates.py::test_the_transcribed_contexts_still_match_the_scope_notes_they_came_from` |
| no case-level genomic content reaches a report | `tests/test_realization_gates.py::test_no_case_level_genomic_content_reaches_a_realization_report` |
| the generated maps are not stale | `tests/test_realization_gates.py::test_the_committed_realization_maps_are_not_stale` |

## Permitted and forbidden vocabulary (PRD section 12)

Permitted: `SUPPORTED`, `CONDITIONAL`, `UNSUPPORTED`, `CONTRADICTED`, `UNKNOWN`,
`CONTEXT_MISMATCH` — the `Entitlement` enum, which is closed.

Forbidden and absent: invented probabilities, expected information gain without probabilities,
arbitrary efficacy scores, model-generated confidence. There is no float anywhere in a verdict;
`src/rarepipe/stages/control/realization/kinds.py` says so in its module docstring and the type
system enforces it, since every verdict field is one of the closed enums.

## Out of scope for Part 1 (PRD section 17)

Not built, deliberately: an exhaustive drug catalogue, an exhaustive gene catalogue, a molecular
catalogue, a molecular simulator, binding prediction, molecular dynamics, searching millions of
combinations, pharmacokinetics, delivery, concrete therapies, multi-organism optimisation, a full
tissue model. The interfaces are shaped so each can be added — `PhysicalPrimitive` already carries
`delivery_requirements` and `temporal_properties` fields that are filled with `unknown` rather than
with invented values — but none is implemented.

## Not enforced here

- Whether any declared capability is biologically real beyond what the cited claim says.
- Whether the five citations the chain rests on are themselves correct; two are marked as having no
  retrieval record, and the compiler downgrades anything resting on them to `CONDITIONAL` rather
  than resolving the question.
- Whether the target definition is right. It remains `PROPOSED_UNAPPROVED`.
