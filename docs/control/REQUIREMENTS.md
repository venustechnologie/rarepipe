# Control compiler — requirements and where each is enforced

Condensed from the *Biological State Control Compiler* PRD that Xavier supplied on 2026-10-04. The
original document is not in the repository; this file records its normative requirements and maps
each to the code and test that enforce it. A test fails if any test referenced here stops existing.

## Output classes

Every class is a legitimate result, not a failure.

| Class | Meaning | Exercised by |
|---|---|---|
| `CONTROL_SOLUTION_CANDIDATE` | a strategy reaches the target under the single accepted model | `tests/test_control_gates.py::test_gate_c_finds_the_known_path` |
| `ROBUST_CONTROL_SOLUTION_CANDIDATE` | works under every model and every candidate for each unknown | `tests/test_control_gates.py::test_an_unknown_off_the_route_is_irrelevant_not_blocking` |
| `CONTROL_INDETERMINATE` | depends on something unknown; names the blocker | `tests/test_control_gates.py::test_gate_b_an_unknown_function_on_the_route_is_named` |
| `CURRENTLY_UNCONTROLLABLE` | unreachable under the current model and controls — not impossible forever | `src/rarepipe/stages/control/compiler.py` (final branch) |
| `TARGET_SPECIFICATION_INCOMPLETE` | success is not defined | `tests/test_control_gates.py::test_gate_a_the_mva_case_compiles_without_inventing_values` |
| `OBSERVABILITY_INSUFFICIENT` | a route may exist but cannot be verified | `tests/test_control_gates.py::test_gate_f_safety_cannot_be_certified_by_a_prediction` |
| `MODEL_DISAGREEMENT` | evidence-compatible models imply different strategies | `tests/test_control_gates.py::test_gate_e_disagreeing_models_do_not_produce_success` |

## Proof gates

| Gate | Requirement | Test |
|---|---|---|
| A | the MVA case is represented as (X0, target, unsafe, M, U, Y) without inventing values | `tests/test_control_gates.py::test_gate_a_the_mva_case_compiles_without_inventing_values` |
| B | a deliberately removed relationship is a blocker, not silently filled | `tests/test_control_gates.py::test_gate_b_a_removed_relationship_is_a_blocker_not_a_constant` |
| C | on a toy network with a known solution, the path is found | `tests/test_control_gates.py::test_gate_c_finds_the_known_path` |
| D | a shorter path through an unsafe state is rejected for a longer safe one | `tests/test_control_gates.py::test_gate_d_the_shorter_unsafe_path_is_rejected_for_the_longer_safe_one` |
| E | M1 reaches the target, M2 does not: never success | `tests/test_control_gates.py::test_gate_e_disagreeing_models_do_not_produce_success` |
| F | indistinguishable internal states are detected | `tests/test_control_gates.py::test_gate_f_indistinguishable_internal_states_are_detected` |
| G | the measurement distinguishing two control-relevant models is identified | `tests/test_control_gates.py::test_gate_g_names_the_measurement_that_separates_two_models` |
| H | the real case yields an intelligible control map | `tests/test_control_gates.py::test_gate_h_the_real_case_produces_an_intelligible_control_map` |

## Invariants (fail CI if violated)

| | Requirement | Test |
|---|---|---|
| I1 | no fabricated parameters | `tests/test_control_invariants.py::test_i1_no_fabricated_parameters` |
| I2 | simulation is not observation | `tests/test_control_invariants.py::test_i2_simulation_is_not_observation` |
| I3 | safety constraints cannot be optimised away | `tests/test_control_invariants.py::test_i3_safety_cannot_be_optimised_away` |
| I4 | unknown relationships remain unknown | `tests/test_control_invariants.py::test_i4_unknown_relationships_remain_unknown` |
| I5 | agents cannot mutate frozen objects or promote their own claims | `tests/test_control_invariants.py::test_i5_agents_cannot_alter_frozen_objects_or_promote_their_own_claims` |
| I6 | every solution names the model it holds under | `tests/test_control_invariants.py::test_i6_every_solution_names_the_model_it_holds_under` |
| I7 | every external model declares a validity domain | `tests/test_control_invariants.py::test_i7_every_external_model_declares_a_validity_domain` |
| I8 | every target constraint has accountable provenance | `tests/test_control_invariants.py::test_i8_every_target_constraint_has_accountable_provenance` |
| I9 | every control has a biological interpretation | `tests/test_control_invariants.py::test_i9_every_control_has_a_biological_interpretation` |
| I10 | observations stay attached to the version that generated them | `tests/test_control_invariants.py::test_i10_observations_stay_attached_to_the_version_that_generated_them` |
| I11 | no robust claim while plausible models disagree | `tests/test_control_invariants.py::test_i11_no_robust_claim_while_plausible_models_disagree` |
| I12 | cross-process reproducibility | `tests/test_control_invariants.py::test_i12_compilation_is_reproducible_across_processes` |

## Beyond the PRD, found while building it

| Requirement | Why | Test |
|---|---|---|
| an unknown is fixed for a whole trajectory | choosing it per step lets the search exploit ignorance | `tests/test_control_gates.py::test_an_unknown_is_fixed_for_a_whole_trajectory_not_chosen_per_step` |
| evidence contradicting every model never yields success | "works for every initial state" is vacuous over an empty set | `tests/test_control_gates.py::test_evidence_that_contradicts_every_model_never_yields_success` |
| a reading an omitted cause could fake is not a clean discriminator | B17/B18 generalised to experiment design | `tests/test_control_gates.py::test_a_reading_an_omitted_cause_could_fake_is_not_a_clean_discriminator` |
| a report cannot claim a result its contents do not support | no result by prose | `tests/test_control_invariants.py::test_a_report_cannot_claim_a_result_its_contents_do_not_support` |
| skills reference only what the compiler defines | a skill naming something that does not exist misleads the model | `tests/test_control_skills.py::test_all_seven_skills_exist_and_are_consistent` |

## Non-goals of this phase

No universal virtual cell, no new ODE solver, no treatment recommendation, no automatic
prescription, no clinical-efficacy claim, no parameter inferred from intuition, no forced
quantification, no replacement of scientific accountability, no endpoint-count optimisation, no drug
list before a control objective is defined, and no literature plausibility treated as fact.

## Success criterion

Not "did we simulate the cell", but: did the system turn a biological problem into an explicit
control problem and correctly separate what is controllable, observable, unsafe and unknown, and what
new information would change the answer. Until a compiler-specified, non-obvious route is confirmed
by experiment, this is a biological control compiler — not a validated predictive treatment engine.
