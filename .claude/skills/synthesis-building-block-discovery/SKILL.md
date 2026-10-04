---
name: synthesis-building-block-discovery
description: Use when a required state transformation lacks an implementing component class.
---

## skill_id
synthesis-building-block-discovery

## version
0.1.0

## scope
Propose classes of components that could implement a required transformation. Store what a piece can do, never a drug name. A proposal remains a hypothesis until linked to evidence.

## required_inputs
Read `RequiredFunction`, `BuildingBlockRegistry`, `BlockClass`, `BlockTransformation`, `Problem.space`, `models`, and `SynthesisReport.experiment_discriminators`.

## reasoning_checklist
1. Specify the required variable, value, direction, scale and function before proposing a component class.
2. Consider protein, enzyme, regulation, cellular-process, population or circuit capabilities using existing `BlockClass` values. Describe a mechanism without asserting its existence.
3. Declare input-state requirements, cell type, tissue context, delivery requirements and validity domain. Record absent evidence explicitly.
4. Encode unintended and population effects as transformations. Declare what returns each reversible variable to its release value.
5. Leave magnitude empty. Quantitative and time-dependent claims require sources. The agent gate strips any magnitude and forces feasibility to `UNASSESSED`.
6. Identify the component's target measurement as its premise test. An unmeasured capability is a measurement gap, not a refuted architecture.

## allowed_tools
Read-only repository access; in-memory native schema validation, `proposals.gate` and `synthesis.compiler.compile_synthesis`. Label counterfactual inputs explicitly. No evidence-store mutation, experimental execution or network transfer of case data. Reproduce the benchmark compilation with:

```sh
uv run python -c "from rarepipe.stages.control.synthesis import mva_synthesis; from rarepipe.stages.control.synthesis.compiler import compile_synthesis; r=compile_synthesis(mva_synthesis.problem()); print(r.result.value); [print(a.architecture_id, a.logical.value, a.physical.value, a.stability.value) for a in r.architectures]; [print(f.family_id, f.verdict.value) for f in r.families]"
```

## forbidden_inferences
Reason with agents. Prove with code. Never decide reachability, safety, robustness, observability, feasibility or a result class. The gate assigns the epistemic type, not the proposer. A proposal stating a verdict in any compiler-owned vocabulary, including `ROBUST_CONTROL_CANDIDATE`, `LOGICALLY_SYNTHESIZABLE`, `PHYSICALLY_FEASIBLE`, any `SynthesisResultClass`, or `VALID_CONTROL`, is rejected outright by `proposals.gate`. Keep quoted compiler results in advisory discussion, outside proposal payloads.

Never infer physical feasibility from logical success or promote simulation to evidence. No treatment recommendations, doses, drug names, invented quantitative constants, thresholds, sampling intervals or probabilities. No exact variant notation, genomic coordinates or personal identifiers. Describe the altered protein and its abundance or function qualitatively. Never approve targets, rewrite evidence or contact patients or families.

## output_schema
Emit `proposals.Proposal` with `proposal_id` generated in code, `skill_id` equal to this directory name, `skill_version` equal to 0.1.0, `proposer` as the actual native `Actor` with `ActorType.AGENT`, `kind`, `payload`, `claimed_epistemic_type` unset, `rationale`, and `references`. Reuse identifiers for revisions. The gate supplies provenance and assigns the epistemic type; gate acceptance is not a scientific verdict.

Use `ProposalKind.BUILDING_BLOCK`. The payload follows `BuildingBlock`: `building_block_id`, `block_class`, `mechanism`, `route_class`, `input_state_requirements`, `state_transformations`, `scale`, `reversibility`, `cell_type`, `tissue_context`, `delivery_requirements`, `known_off_targets`, `population_effects`, `safety_effects`, `evidence`, `evidence_refs`, `validity_domain`, `uncertainty`, `feasibility_status`, and `feasibility_note`. Each `BlockTransformation` has `variable`, `to`, `direction`, `scale`, `control_kind`, `intended`, `released_to`, `release_rationale`, `magnitude_if_known`, and `time_dependence_if_known`. Leave unsupported quantitative fields empty. The gate replaces `provenance`, assigns `INFERRED_HYPOTHESIS`, forces `Feasibility.UNASSESSED`, and strips magnitude. Evidence linkage alone does not establish feasibility.

## uncertainty_language
Use “required capability; hypothetical implementation.” Distinguish evidence about a component class from evidence of the declared transformation in the relevant cells.

## abstention_conditions
Return an advisory gap if the function, domain or scale is absent. Do not estimate missing magnitude, timing, delivery or evidence.

## validation_hooks
`BuildingBlock` validates quantitative citations and releases. `BuildingBlockRegistry.check` resolves domains. `proposals.gate` bounds agent claims. `synthesis.experiments.premise_tests` identifies measurements; `synthesis.synthesizability.physical_status` uses component feasibility only.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_FUNCTION_REPLACEMENT` alone. Expected reasoning: supplying sufficient function bypasses the abundance premise without establishing an implementing component. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`.
2. Input: MVA `BB_CHECKPOINT_BYPASS_CIRCUIT` alone. Expected reasoning: separate three asserted checkpoint capabilities from demonstrated implementation and name their overrides. Compiler reports `TARGET_REACHABLE` in H01 and H02, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`.

## retention_criterion
Compare against a generic agent on hidden cases. Measure useful capability classes, premise-test coverage and unsupported implementation assertions. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
