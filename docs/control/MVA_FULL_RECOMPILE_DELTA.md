# Full recompile delta — MVA_001

> Evidence correction → epistemic correction → model correction → architecture correction.

Every layer below was recomputed from the repaired evidence in dependency order. No verdict was edited by hand. A layer that did not move still has a line, because "unchanged" without a reason is indistinguishable from "not recomputed".

Baseline captured at commit `4f9de0a`; 10 of 11 layers moved.

| # | Layer | Moved | Following |
|---|---|---|---|
| 1 | `source_inventory` | **yes** | REPAIR_R1, REPAIR_R2, REPAIR_R3, REPAIR_R4 |
| 2 | `grounded_claims` | **yes** | REPAIR_R1, REPAIR_R4 |
| 3 | `causal_chain_support` | **yes** | REPAIR_R2 |
| 4 | `contradiction_state` | **yes** | REPAIR_R1 |
| 5 | `direction_and_entitlement` | **yes** | REPAIR_R1 |
| 6 | `hypotheses` | **yes** | REPAIR_R1, REPAIR_R2 |
| 7 | `control_model` | **yes** | REPAIR_R1, REPAIR_R2 |
| 8 | `synthesis_architectures` | no | — |
| 9 | `physical_realizations` | **yes** | REPAIR_R1, REPAIR_R2 |
| 10 | `capability_gaps` | **yes** | REPAIR_R2, REPAIR_R3 |
| 11 | `experiment_implications` | **yes** | REPAIR_R1, REPAIR_R2, REPAIR_R4 |

## 1. `source_inventory`

**Changed.** chain_edges, unverified_labels moved, following ['REPAIR_R1', 'REPAIR_R2', 'REPAIR_R3', 'REPAIR_R4'].

| Observable | Before | After |
|---|---|---|
| `chain_edges` | `15` | `16` |
| `unverified_labels` | `["PMID:42543917", "PMID:42628241"]` | `[]` |

Unchanged in this layer: `cited_refs`.

## 2. `grounded_claims`

**Changed.** backward_audit, disqualified moved, following ['REPAIR_R1', 'REPAIR_R4'].

| Observable | Before | After |
|---|---|---|
| `backward_audit` | `{"ATTRIBUTION_AMBIGUOUS": 3, "DOES_NOT_SUPPORT_ATTRIBUTION": 2, "PARTIALLY_SUPPORTS_ATTRIBUTION": 1, "SUPPORTS_ATTRIBUTION": 8}` | `{"ATTRIBUTION_AMBIGUOUS": 3, "PARTIALLY_SUPPORTS_ATTRIBUTION": 1, "SUPPORTS_ATTRIBUTION": 9}` |
| `disqualified` | `["PMID:20516114@cell_death->division_rate", "PMID:42543917@nicotinic_acid_exposure->bubr1_abundance"]` | `[]` |

## 3. `causal_chain_support`

**Changed.** niacin_to_intracellular_nad_verdict moved, following ['REPAIR_R2'].

| Observable | Before | After |
|---|---|---|
| `niacin_to_intracellular_nad_verdict` | `"CONDITIONAL_ON_UNVERIFIED_SUBSTITUTION"` | `"SUPPORTED_IN_HUMANS"` |

Unchanged in this layer: `niacin_to_missegregation_verdict`, `niacin_to_missegregation_weakest_link`.

## 4. `contradiction_state`

**Changed.** contradicted_alternatives_to_abundance, excluded_contradicted_routes_to_abundance_count moved, following ['REPAIR_R1'].

| Observable | Before | After |
|---|---|---|
| `contradicted_alternatives_to_abundance` | `["nicotinic_acid_exposure -> bubr1_abundance"]` | `[]` |
| `excluded_contradicted_routes_to_abundance_count` | `1` | `0` |

## 5. `direction_and_entitlement`

**Changed.** direct_route_step_entitlement moved, following ['REPAIR_R1'].

| Observable | Before | After |
|---|---|---|
| `direct_route_step_entitlement` | `"CONTRADICTED"` | `"UNSUPPORTED"` |

## 6. `hypotheses`

**Changed.** h04_citations moved, following ['REPAIR_R1', 'REPAIR_R2'].

| Observable | Before | After |
|---|---|---|
| `h04_citations` | `["PMID:24825348", "PMID:42543917"]` | `["PMID:24825348", "PMID:32386566"]` |

## 7. `control_model`

**Changed.** digest moved, following ['REPAIR_R1', 'REPAIR_R2']. Only the artifact digest moved: the report's contents changed and its conclusion did not.

| Observable | Before | After |
|---|---|---|
| `digest` | `"sha256:8e670337e0ed05daedfeb4db435a2bb5ef99a41fca419051b6d03d4e1bdca9ae"` | `"sha256:dd4c7fecc5e0cc493f174283dd9a7dd6bf95bd018be520ff0e7cee56d2c00eaa"` |

Unchanged in this layer: `result`.

## 8. `synthesis_architectures`

**Unchanged.** Architectures are composed from declared transformations, and no component's feasibility changed. The repair altered what is known about a route's evidence, not what any piece is declared able to do..

Unchanged in this layer: `digest`, `result`.

## 9. `physical_realizations`

**Changed.** abundance_digest, abundance_per_route, bypass_digest moved, following ['REPAIR_R1', 'REPAIR_R2'].

| Observable | Before | After |
|---|---|---|
| `abundance_digest` | `"sha256:46d272efbe04b4edea372e5b022486d3d9218a6dea56ef68f79fa5451496e4f0"` | `"sha256:b8e2a2d7b2e3da605f5420c1649aa498ade74e500a64a7e3ce8efc156e8abc25"` |
| `abundance_per_route` | `{"MR_ABUNDANCE_DIRECTLY": "NO_GROUNDED_REALIZATION", "MR_ABUNDANCE_VIA_NICOTINIC_ACID": "CONTEXT_MISMATCH", "MR_ABUNDANCE_VIA_NMN": "EVIDENCE_INSUFFICIENT"}` | `{"MR_ABUNDANCE_DIRECTLY": "EVIDENCE_INSUFFICIENT", "MR_ABUNDANCE_VIA_NICOTINIC_ACID": "CONTEXT_MISMATCH", "MR_ABUNDANCE_VIA_NMN": "EVIDENCE_INSUFFICIENT"}` |
| `bypass_digest` | `"sha256:40631d94f7124bece2a0ba79d81947bae1d146bb00f4b0ba7a037f39fa6378af"` | `"sha256:7d9c5ad3baf1b52c3b965aeb2e34d8022cf65227d0bfde703fef01e0f83b9b9d"` |

Unchanged in this layer: `abundance`, `bypass`.

## 10. `capability_gaps`

**Changed.** digest moved, following ['REPAIR_R2', 'REPAIR_R3']. Only the artifact digest moved: the report's contents changed and its conclusion did not.

| Observable | Before | After |
|---|---|---|
| `digest` | `"sha256:1d1685c423a8cda584ddd1dea2743aec0f01c2a2a681af5716f60858442b7888"` | `"sha256:9485860a19706d97b3106fbde4735221a514437e93e5137f0a175ccf66e2fa2e"` |

Unchanged in this layer: `results`.

## 11. `experiment_implications`

**Changed.** case_ids_including, negative_record_state_for_direct_route, unmeasured_parameters moved, following ['REPAIR_R1', 'REPAIR_R2', 'REPAIR_R4'].

| Observable | Before | After |
|---|---|---|
| `case_ids_including` | `["NULL01_closest_niacin_experiment_was_null"]` | `["HUMAN02_niacin_raises_tissue_nad_in_human_muscle", "NAD01_niacin_raises_circulating_nad", "NAD02_circulating_nad_is_not_intracellular_nad", "SAC01_restored_ab` |
| `negative_record_state_for_direct_route` | `"MEASURED_NO_EFFECT"` | `"NO_RELEVANT_DATA"` |
| `unmeasured_parameters` | `6` | `7` |

Unchanged in this layer: `published_behaviour_cases`.

## What did not change, and why that matters

The binding constraint on the whole case is unchanged. The chain to missegregation is still capped by whether this child's altered protein functions at restored abundance, and the control compiler is still indeterminate for exactly that reason. The repair corrected what the repository believed about its own evidence; it did not move the question the case turns on, and it was not expected to.

## What this is not

Nothing in this document is a treatment recommendation. The human trial connected here reports that administered niacin raised muscle NAD in myopathy patients under that study's conditions. It does not say that niacin should be given to this child, that it would reach the relevant cells, or that it would do anything to the protein in question.

