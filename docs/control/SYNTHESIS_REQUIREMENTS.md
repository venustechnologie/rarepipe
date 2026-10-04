# Synthesis compiler — requirements and where each is enforced

Condensed from the *Synthetic Biological Control Architecture Compiler* PRD (version 2.0) that
Xavier supplied. The original document is not in the repository; this file records its normative
requirements and maps each to the code and test that enforces it. A test fails if any test
referenced here stops existing.

See [`SYNTHESIS_DESIGN.md`](SYNTHESIS_DESIGN.md) for the formalism and the reasons behind each
decision, and [`MVA_ARCHITECTURE_MAP.md`](MVA_ARCHITECTURE_MAP.md) for the generated output.

## Output classes

Every class is a legitimate result. `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN` in particular is a
successful output of the compiler, not a near miss.

| Class | Meaning | Exercised by |
|---|---|---|
| `ARCHITECTURE_SYNTHESIZED` | robust, safe, observable, every component established | `tests/test_synthesis_gates.py::test_gate1_synthesizes_repair_when_repair_is_the_only_route` |
| `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN` | reaches the target; nothing is known to build it | `tests/test_synthesis_gates.py::test_gate10_separates_a_logical_solution_from_a_feasible_intervention` |
| `ARCHITECTURE_OBSERVABILITY_INSUFFICIENT` | the reading cannot be distinguished from a process that fakes it | `tests/test_synthesis_gates.py::test_gate6_detects_that_the_population_reading_could_be_selective_death` |
| `ARCHITECTURE_MODEL_DISAGREEMENT` | compatible models imply different architectures | `tests/test_synthesis_gates.py::test_gate9_returns_the_disagreement_rather_than_the_favourable_half` |
| `ARCHITECTURE_INDETERMINATE` | blocked by biology that is not yet known | `tests/test_synthesis_gates.py::test_gate12_a_removed_relationship_produces_a_blocker_not_a_path` |
| `NO_ARCHITECTURE_SYNTHESIZED` | about this registry and model, not about biology | `tests/test_synthesis_gates.py::test_gate10_an_infeasible_component_is_not_composed_at_all` |
| `SPECIFICATION_INCOMPLETE` | success is not defined, so nothing can be synthesized for it | `src/rarepipe/stages/control/synthesis/compiler.py` (first branch) |

## Proof gates

| Gate | Requirement | Enforced by |
|---|---|---|
| 1 | synthesize repair where repair is the only route | `tests/test_synthesis_gates.py::test_gate1_synthesizes_repair_when_repair_is_the_only_route` |
| 2 | synthesize the bypass when the damaged node cannot be touched | `tests/test_synthesis_gates.py::test_gate2_synthesizes_a_bypass_when_the_damaged_node_cannot_be_touched` |
| 3 | find the combination where no single control suffices | `tests/test_synthesis_gates.py::test_gate3_finds_the_pair_when_no_single_component_is_enough` |
| 4 | reject the route that reaches the reading by killing the cells | `tests/test_synthesis_gates.py::test_gate4_rejects_the_route_that_reaches_the_reading_by_killing_the_cells` |
| 4b | reject harm that appears downstream of the component, not at its own variable | `tests/test_synthesis_gates.py::test_gate4_rejects_harm_that_appears_downstream_of_the_component` |
| 5 | a population-level function reached without correcting any cell | `tests/test_synthesis_gates.py::test_gate5_reaches_a_population_level_function_without_correcting_any_cell` |
| 6 | detect that the apparent population improvement could be selective death | `tests/test_synthesis_gates.py::test_gate6_detects_that_the_population_reading_could_be_selective_death` |
| 7 | preserve a load-bearing order | `tests/test_synthesis_gates.py::test_gate7_preserves_the_order_that_works_and_rejects_the_one_that_does_not` |
| 8 | feedback maintains what static control cannot | `tests/test_synthesis_gates.py::test_gate8_static_intervention_fails_where_the_loop_maintains_the_target` |
| 9 | return the disagreement, not robust success | `tests/test_synthesis_gates.py::test_gate9_returns_the_disagreement_rather_than_the_favourable_half` |
| 10 | logically synthesizable with physical feasibility unknown | `tests/test_synthesis_gates.py::test_gate10_separates_a_logical_solution_from_a_feasible_intervention` |
| 11 | an MVA architecture structurally distinct from both known routes | `tests/test_synthesis_mva.py::test_gate11_produces_an_architecture_structurally_distinct_from_both_known_routes` |
| 12 | a removed relationship gives a blocker, never an invented path | `tests/test_synthesis_gates.py::test_gate12_a_removed_relationship_produces_a_blocker_not_a_path` |

Gate 11 is satisfied by expressibility, not feasibility, and a separate test holds that line:
`tests/test_synthesis_mva.py::test_gate11_distinctness_is_not_a_feasibility_claim`.

### Supporting assertions on the same gates

A gate that only checks a headline verdict can pass while the reasoning behind it is wrong. These
check the parts a scientist would actually act on.

| Requirement | Enforced by |
|---|---|
| the decomposition names the entry point without naming an intervention | `tests/test_synthesis_gates.py::test_gate1_decomposition_names_the_entry_point_without_naming_an_intervention` |
| a rejection on safety records the trajectory, not just a flag | `tests/test_synthesis_gates.py::test_gate4_the_unsafe_path_is_recorded_not_merely_flagged` |
| a population effect with no stated differential is flagged | `tests/test_synthesis_gates.py::test_gate5_a_population_effect_with_no_stated_differential_is_flagged` |
| the cell itself stays uncorrected in a population route's decomposition | `tests/test_synthesis_gates.py::test_gate5_cell_function_is_untouched_in_the_decomposition` |
| measuring the confounder restores the result | `tests/test_synthesis_gates.py::test_gate6_measuring_the_confounder_restores_the_result` |
| a load-bearing order is reported with the evidence for it | `tests/test_synthesis_gates.py::test_gate7_reports_the_order_as_load_bearing_with_the_evidence_for_it` |
| a single-step architecture does not claim a load-bearing order | `tests/test_synthesis_gates.py::test_gate7_a_single_step_architecture_does_not_claim_a_load_bearing_order` |
| a policy keyed on an unmeasured variable is refused | `tests/test_synthesis_gates.py::test_gate8_a_policy_keyed_on_an_unmeasured_variable_is_refused` |
| releasing a control that never said what reverts is refused | `tests/test_synthesis_gates.py::test_gate8_releasing_a_control_that_never_said_what_reverts_is_refused` |
| the composition search fails closed rather than truncating | `tests/test_synthesis_gates.py::test_gate12_the_search_fails_closed_rather_than_truncating` |
| a family with no registered component is unknown, not unsupported | `tests/test_synthesis_gates.py::test_a_family_with_no_registered_component_is_unknown_not_unsupported` |

## Invariants

| # | Invariant | Enforced by |
|---|---|---|
| 1 | no synthetic route becomes empirical evidence | `tests/test_synthesis_invariants.py::test_i1_a_derived_result_cannot_be_promoted_to_evidence_without_a_measurement` |
| 1b | every report is a simulated prediction | `tests/test_synthesis_invariants.py::test_i1_every_synthesis_report_is_a_simulated_prediction` |
| 2 | no agent-created edge enters the dynamics untyped | `tests/test_synthesis_invariants.py::test_i2_an_agent_proposed_architecture_is_typed_as_proposed_not_composed` |
| 2b | a proposal cannot state a verdict the compiler owns | `tests/test_synthesis_invariants.py::test_i2_a_proposal_cannot_state_a_verdict_the_compiler_owns` |
| 2c | an agent cannot assert feasibility or a magnitude | `tests/test_synthesis_invariants.py::test_i2_an_agent_cannot_assert_a_component_is_feasible_or_quantified` |
| 3 | hard safety cannot be optimized away | `tests/test_synthesis_invariants.py::test_i3_safety_outranks_every_benefit_in_the_lexicographic_order` |
| 3b | no weight can trade safety against anything | `tests/test_synthesis_invariants.py::test_i3_no_weight_can_trade_safety_against_anything` |
| 4 | missing biology remains missing | `tests/test_synthesis_invariants.py::test_i4_a_hole_in_the_model_is_never_filled_by_the_search` |
| 5 | logical synthesizability and physical feasibility stay separate | `tests/test_synthesis_invariants.py::test_i5_an_assessment_cannot_claim_physical_feasibility_with_unbuilt_components` |
| 5b | logical reachability does not set the physical verdict | `tests/test_synthesis_invariants.py::test_i5_logical_reachability_does_not_set_the_physical_verdict` |
| 6 | population improvement cannot imply cellular rescue | `tests/test_synthesis_invariants.py::test_i6_a_population_only_architecture_states_that_no_cell_was_corrected` |
| 7 | a composition reading needs its confounders excluded | `tests/test_synthesis_invariants.py::test_i7_a_composition_reading_needs_its_confounders_excluded` |
| 8 | every building block carries provenance or is explicitly hypothetical | `tests/test_synthesis_invariants.py::test_i8_a_building_block_must_carry_a_capability_or_hypothesis_type` |
| 9 | every quantitative constant cites its source | `tests/test_synthesis_invariants.py::test_i9_a_magnitude_without_a_citation_is_refused` |
| 10–12 | every architecture records its assumptions, scale and competing models | `tests/test_synthesis_invariants.py::test_i10_i11_i12_every_assessment_records_assumptions_scale_and_models` |
| 13 | every feedback policy reads a measured variable | `tests/test_synthesis_invariants.py::test_i13_a_policy_on_an_unmeasured_variable_cannot_succeed` |
| 14 | every population control states its source of differential | `tests/test_synthesis_invariants.py::test_i14_a_population_mechanism_must_state_its_source_of_differential` |
| 15 | no treatment recommendation can be produced | `tests/test_synthesis_invariants.py::test_i15_the_no_recommendation_statement_is_fixed` |
| 15b | advisory language is refused wherever it appears | `tests/test_synthesis_invariants.py::test_i15_advisory_language_is_refused_wherever_it_appears` |
| 15c | the scan does not fire on ordinary scientific language | `tests/test_synthesis_invariants.py::test_i15_the_advisory_scan_does_not_fire_on_ordinary_scientific_language` |
| 16 | plans stay versioned | `tests/test_synthesis_invariants.py::test_i16_every_report_carries_the_versions_it_was_produced_under` |
| 17 | case data stays inside its governance boundary | `tests/test_synthesis_invariants.py::test_i17_no_case_level_genomic_content_reaches_a_synthesis_report` |
| 17b | the same holds for the MVA report | `tests/test_synthesis_mva.py::test_no_case_level_genomic_content_reaches_the_mva_synthesis_report` |
| 18 | same inputs and versions give the same output | `tests/test_synthesis_invariants.py::test_i18_the_same_inputs_give_the_same_digest_across_processes` |
| 18b | a conflicting composition is refused, not resolved by sort order | `tests/test_synthesis_invariants.py::test_i18_a_conflicting_composition_is_refused_rather_than_resolved_by_sort_order` |
| 18c | the MVA digest is stable across hash seeds | `tests/test_synthesis_mva.py::test_the_mva_synthesis_digest_is_stable_across_hash_seeds` |

## The proposal path

Agents propose; the compiler judges. The path is exercised end to end, including the case the
path exists for — a composition the search is too narrow to find.

| Requirement | Enforced by |
|---|---|
| a proposal is evaluated by the same code as an enumerated architecture | `tests/test_synthesis_invariants.py::test_an_agent_proposal_is_evaluated_by_the_same_code_as_an_enumerated_one` |
| a result carried only by a proposed architecture still validates | `tests/test_synthesis_invariants.py::test_a_result_carried_only_by_a_proposed_architecture_still_validates` |
| the compiler contradicts a proposer's own framing with evidence | `tests/test_synthesis_invariants.py::test_the_compiler_contradicts_a_proposers_own_framing_with_evidence` |
| an architecture naming an unregistered component is refused | `tests/test_synthesis_invariants.py::test_an_architecture_naming_an_unregistered_component_is_refused_before_compiling` |

## Section 31 — the MVA families

Each family is answered whether or not anything implements it, so that a family nobody has a
mechanism for is distinguishable from one that was never considered.

| Requirement | Enforced by |
|---|---|
| both original routes are retained as families | `tests/test_synthesis_mva.py::test_both_original_routes_are_retained_as_families` |
| the abundance route is still blocked by the same unknown | `tests/test_synthesis_mva.py::test_the_abundance_route_is_still_blocked_by_the_same_unknown` |
| a bypass names what it overrides and how well supported it is | `tests/test_synthesis_mva.py::test_a_bypass_says_which_relationships_it_overrides_and_how_well_supported_they_are` |
| lowering the error rate alone does not satisfy a checkpoint target | `tests/test_synthesis_mva.py::test_lowering_the_error_rate_alone_does_not_satisfy_a_checkpoint_target` |
| selecting against the aneuploid cells is refused on safety | `tests/test_synthesis_mva.py::test_selecting_against_the_aneuploid_cells_is_refused_on_safety` |
| a family the state space cannot express says so without calling it impossible | `tests/test_synthesis_mva.py::test_a_family_the_state_space_cannot_express_says_so_without_calling_it_impossible` |
| closing the loop does not remove the dependence on the unknown | `tests/test_synthesis_mva.py::test_closing_the_loop_does_not_remove_the_dependence_on_the_unknown` |
| the loop does not claim the state survives withdrawal | `tests/test_synthesis_mva.py::test_the_loop_does_not_claim_the_state_survives_withdrawal` |
| the generated map is not stale | `tests/test_synthesis_mva.py::test_the_committed_architecture_map_is_not_stale` |

## Section 21 — the experiment compiler

| Requirement | Enforced by |
|---|---|
| the measurement that settles the open relationship is identified and measurable | `tests/test_synthesis_mva.py::test_the_measurement_that_settles_the_abundance_question_is_identified_and_measurable` |
| a reading nobody can take is a gap, not an experiment | `tests/test_synthesis_mva.py::test_a_reading_nobody_can_take_is_reported_as_a_gap_not_as_an_experiment` |
| deterministic elimination, never an invented prior | `src/rarepipe/stages/control/synthesis/experiments.py` (module docstring and `CRITERION`) |

## Section 35 — what is not built

No universal virtual cell, no bespoke differential-equation solver, no drug recommendation engine,
no agent per gene, no numerical embedding standing in for a biological equation, no dashboard of
speculative probabilities, and no combination searched merely because combinations exist. The last
is enforced by minimality: `src/rarepipe/stages/control/synthesis/search.py::_minimal`. `INTERVAL`
variables are recognised by the contract and refused by this engine, so the scale path is an
adapter to an established solver rather than silent discretisation.

## Not enforced here

- Whether the reasoning in a skill is scientifically sound.
- Whether any declared transformation is biologically achievable: every component in the MVA
  registry is `UNASSESSED`, which is the honest status and the reason the headline result is
  `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`.
- Whether the target definition is right. No accountable scientist has approved it, so the
  compilation reports `PROPOSED_UNAPPROVED` and every verdict is conditional on it.
