# Evidence repair delta — MVA_001

> The test is not whether the old answer survives. The test is whether the answer changes correctly when the evidence changes.

Ledger `mva-evidence-repair-v1` · baseline captured at commit `4f9de0a` · 4 repairs, all at the evidence layer. No downstream verdict was edited by hand.

## What prompted this

A backward grounding audit over every load-bearing citation — the forward rule run over claims the system already believed. Of the citations the causal chain rests on:

| Audit state | Count (before repair) |
|---|---|
| `ATTRIBUTION_AMBIGUOUS` | 3 |
| `DOES_NOT_SUPPORT_ATTRIBUTION` | 2 |
| `PARTIALLY_SUPPORTS_ATTRIBUTION` | 1 |
| `SUPPORTS_ATTRIBUTION` | 8 |

Two attributions were disqualified. One was already known. The other was found only because the audit was run over everything rather than over the one that had already failed.

## REPAIR_R1 — `nicotinic_acid_exposure->bubr1_abundance`

**Kind:** `RETIRE_ATTRIBUTION`

**Before**

- claim version: `MVA_001_niacin_bubr1_v1 @ 4f9de0a`
- source assignment: PMID:42543917 (UNVERIFIED: no retrieval record)
- verdict: `contradicted`
- scope: the closest related nicotinic-acid experiment was null and reported no measurement of the chain

**Audit**

- verdict: `DOES_NOT_SUPPORT_ATTRIBUTION`
- The citation was retrieved and is a study of white adipocytes adapting to cooler temperatures. Its stored text contains neither 'niacin' nor 'nicotinic' nor any spelling of the protein, so it cannot report a null effect of one on the other.

**Recovery of the intended reference**

- outcome: `NO_INTENDED_REFERENCE_FOUND`
- searched inside the project:
    - the plan seed (prospective/seed.py, hypothesis H04)
    - the local mechanism corpus ids MC_0001 to MC_0013, which the project uses for curated artifacts instead of bare identifiers
    - the simulator chain's own reference constants
    - the commit that introduced the citation (stage10 prospective plans)
    - the earlier PRD response that already flagged both seed citations as having no retrieval record
- targeted external queries:
    - `("nicotinic acid" OR niacin) AND (BUBR1 OR BUB1B)`
    - `("nicotinic acid" OR niacin) AND "spindle assembly checkpoint"`
    - `("nicotinic acid" OR niacin) AND ("mitotic checkpoint" OR aneuploidy)`
    - `"nicotinic acid" AND SIRT2`
    - `niacin AND "chromosome missegregation"`
- The local mechanism corpus holds nothing about this precursor — every entry is about the protein and the disease — so no curated artifact was mis-transcribed into a bare identifier. A targeted search returned work on oocytes, ovarian ageing and reviews, and nothing reporting a null effect of this precursor on the protein. No substitute was adopted.

**After**

- claim version: `MVA_001_niacin_bubr1_v1 @ repair-r1`
- source assignment: *none*
- support level: `asserted_only`
- scope: no retrieved source addresses this relation in either direction

**Why this state and not another.** The support level is what the chain's own validator permits once the citation is withdrawn: an edge with no evidence reference may only be asserted_only. It was not relabelled as supported, and it was not deleted — deleting it would have hidden a hypothesis the case still holds.

**Downstream effects**

- `source_inventory`: chain_edges, unverified_labels
- `grounded_claims`: backward_audit, disqualified
- `contradiction_state`: contradicted_alternatives_to_abundance, excluded_contradicted_routes_to_abundance_count
- `direction_and_entitlement`: direct_route_step_entitlement
- `hypotheses`: h04_citations
- `control_model`: digest
- `physical_realizations`: abundance_digest, abundance_per_route, bypass_digest
- `experiment_implications`: case_ids_including, negative_record_state_for_direct_route, unmeasured_parameters

## REPAIR_R2 — `nicotinic_acid_exposure->nad_intracellular`

**Kind:** `CONNECT_EVIDENCE`

**Before**

- claim version: `MVA_001_niacin_bubr1_v1 @ 4f9de0a`
- source assignment: none; the reference was in the repository and cited by no edge
- verdict: `not represented; the only route to the intracellular pool was the blood-to-cell transfer, recorded as a different compartment`

**Audit**

- verdict: `not an audit failure`
- The previous state was not wrong, it was incomplete: a human trial already held in the repository measured the tissue pool, which is the compartment the blood-only route cannot speak to, and it was connected to nothing.

**Recovery of the intended reference**

- outcome: `NOT_ATTEMPTED`
- searched inside the project:
    - not applicable: this repair connects a reference the repository already held
- Nothing was missing to recover. The reference was present in the repository and attached to no edge of the causal chain.

**After**

- claim version: `MVA_001_niacin_bubr1_v1 @ repair-r2`
- source assignment: PMID:32386566
- support level: `human_experimental`
- scope: muscle NAD of adult-onset mitochondrial myopathy patients reached the level of matched controls; human skeletal muscle, not the cell type this case requires

**Why this state and not another.** The edge is recorded at the context the source supports and no wider. The cell type remains a transfer gap rather than a resolved step, and the scope note and caveat travel with the verdict, so the human-supported reading cannot be detached from the tissue it was measured in.

**Downstream effects**

- `source_inventory`: chain_edges, unverified_labels
- `causal_chain_support`: niacin_to_intracellular_nad_verdict
- `hypotheses`: h04_citations
- `control_model`: digest
- `physical_realizations`: abundance_digest, abundance_per_route, bypass_digest
- `capability_gaps`: digest
- `experiment_implications`: case_ids_including, negative_record_state_for_direct_route, unmeasured_parameters

## REPAIR_R3 — `nicotinic_acid_exposure->nad_whole_blood`

**Kind:** `LIFT_STALE_LABEL`

**Before**

- claim version: `MVA_001_niacin_bubr1_v1 @ 4f9de0a`
- source assignment: PMID:42628241 (UNVERIFIED: no retrieval record)
- verdict: `human_experimental, capped by an unverified-citation label`

**Audit**

- verdict: `SUPPORTS_ATTRIBUTION`
- The label said the citation had no retrieval record. It has one now, and the retrieved text states the attributed effect in so many words, so the label itself had become stale and was capping a claim the document supports.

**Recovery of the intended reference**

- outcome: `NOT_ATTEMPTED`
- searched inside the project:
    - not applicable: this repair connects a reference the repository already held
- Nothing was missing to recover. The reference was present in the repository and attached to no edge of the causal chain.

**After**

- claim version: `MVA_001_niacin_bubr1_v1 @ repair-r3`
- source assignment: PMID:42628241
- support level: `human_experimental`
- scope: whole-blood NAD in healthy adults

**Why this state and not another.** Only the retrieval label changed. The support level, the compartment and the scope are what they were, so nothing downstream gains strength from this beyond no longer being discounted for a missing retrieval that has since happened.

**Downstream effects**

- `source_inventory`: chain_edges, unverified_labels
- `capability_gaps`: digest

## REPAIR_R4 — `cell_death->division_rate`

**Kind:** `RETIRE_ATTRIBUTION`

**Before**

- claim version: `MVA_001_niacin_bubr1_v1 @ 4f9de0a`
- source assignment: PMID:20516114
- verdict: `model_experimental`
- scope: population-level consequence

**Audit**

- verdict: `DOES_NOT_SUPPORT_ATTRIBUTION`
- Found by running the backward audit over every load-bearing citation rather than only the one that had already failed. The cited document's stored text mentions neither cell death nor division rate in any recorded spelling, so it does not address this relation.

**Recovery of the intended reference**

- outcome: `NOT_ATTEMPTED`
- searched inside the project:
    - not applicable: this repair connects a reference the repository already held
- Nothing was missing to recover. The reference was present in the repository and attached to no edge of the causal chain.

**After**

- claim version: `MVA_001_niacin_bubr1_v1 @ repair-r4`
- source assignment: *none*
- support level: `asserted_only`
- scope: population-level consequence; no retrieved source addresses it

**Why this state and not another.** Retiring an unsupported label is the conservative action; keeping it would have been the aggressive one. The edge survives as an assertion rather than being deleted.

**Needs a human decision.** Only abstracts are stored, so the remedy may be retrieving the full article rather than leaving this edge as an assertion. A scientist should decide which.

**Downstream effects**

- `source_inventory`: chain_edges, unverified_labels
- `grounded_claims`: backward_audit, disqualified
- `experiment_implications`: case_ids_including, negative_record_state_for_direct_route, unmeasured_parameters

## The counterintuitive one

Withdrawing the refutation made the result **weaker**, not stronger. The direct precursor route used to be excluded from propagation as falsified; it is now an assertion with no evidence either way, so it contributes and the propagated verdict is capped by it. The system stopped knowing something it never had grounds for, and the honest consequence is that it now knows less.

## What this is not

Nothing in this document is a treatment recommendation. The human trial connected here reports that administered niacin raised muscle NAD in myopathy patients under that study's conditions. It does not say that niacin should be given to this child, that it would reach the relevant cells, or that it would do anything to the protein in question.

