---
name: synthesis-safety-architecture
description: Use when translating conceptual risks into formalizable constraints and unintended component transformations.
---

## skill_id
synthesis-safety-architecture

## version
0.1.0

## scope
Identify conceptual risks and formalizable constraints for deterministic evaluation. Never decide safety or trade a prohibited state for target improvement.

## required_inputs
Read `Problem.unsafe`, `Problem.space`, `SafetyConstraint`, `BlockTransformation`, component `known_off_targets`, `population_effects`, `safety_effects`, and `ArchitectureAssessment.unsafe_path`.

## reasoning_checklist
1. Name each risk, its affected variable, harmful categorical state and excluded-region requirement. Increased proliferation becomes a requirement that uncontrolled proliferation stays excluded using existing vocabulary and an accountable safety definition.
2. Turn each risk into a formalizable constraint that code evaluates. Record absent variables, relationships or thresholds as modelling gaps.
3. A declared risk living only in prose cannot reject anything. A component effect must become a `BlockTransformation` with `intended` set to false so the hard safety filter sees it. Keep intended and unintended effects in the same composition step.
4. Inspect immediate and downstream harm across every interleaving. Never assume safety-triggered release outruns an unsafe plant transition.
5. Preserve human ownership of safety definitions. Never approve a constraint, invent a threshold, weaken an exclusion or infer empirical safety from missing modelled harm.

## allowed_tools
Read-only repository access; in-memory native schema validation, `proposals.gate` and `synthesis.compiler.compile_synthesis`. Label counterfactual inputs explicitly. No evidence-store mutation, experimental execution or network transfer of case data. Reproduce the benchmark compilation with:

```sh
uv run python -c "from rarepipe.stages.control.synthesis import mva_synthesis; from rarepipe.stages.control.synthesis.compiler import compile_synthesis; r=compile_synthesis(mva_synthesis.problem()); print(r.result.value); [print(a.architecture_id, a.logical.value, a.physical.value, a.stability.value) for a in r.architectures]; [print(f.family_id, f.verdict.value) for f in r.families]"
```

## forbidden_inferences
Reason with agents. Prove with code. Never decide reachability, safety, robustness, observability, feasibility or a result class. The gate assigns the epistemic type, not the proposer. A proposal stating a verdict in any compiler-owned vocabulary, including `ROBUST_CONTROL_CANDIDATE`, `LOGICALLY_SYNTHESIZABLE`, `PHYSICALLY_FEASIBLE`, any `SynthesisResultClass`, or `VALID_CONTROL`, is rejected outright by `proposals.gate`. Keep quoted compiler results in advisory discussion, outside proposal payloads.

Never infer physical feasibility from logical success or promote simulation to evidence. No treatment recommendations, doses, drug names, invented quantitative constants, thresholds, sampling intervals or probabilities. No exact variant notation, genomic coordinates or personal identifiers. Describe the altered protein and its abundance or function qualitatively. Never approve targets, rewrite evidence or contact patients or families.

## output_schema
Emit an advisory Markdown finding with exactly four paragraphs: identify the component and conceptual risk; specify the existing variable, harmful value and excluded-region requirement; describe a proposed `BlockTransformation` with `intended` set to false and its source or hypothetical status; name the missing representation or deterministic check. Use native transformation fields `variable`, `to`, `direction`, `scale`, and `control_kind`. Change no block or safety region automatically. A separate block revision must use `ProposalKind.BUILDING_BLOCK` through `proposals.gate`. The finding assigns no safety verdict.

## uncertainty_language
Use “declared harmful transformation” or “unrepresented safety mechanism.” Quote a compiler rejection with its assumptions. An absent unsafe path is not empirical safety evidence.

## abstention_conditions
Return an advisory gap when harm cannot be expressed in the state space or a safety definition is missing. Invent no safe value, quantitative limit or probability.

## validation_hooks
`BuildingBlock.controls` includes unintended transformations. `synthesis.composition.expand` preserves joint action. `UnsafeRegion.contains`, `UnsafeRegion.violated_by` and deterministic exploration evaluate exclusions. `synthesis.compiler.compile_synthesis` records `unsafe_in` and `unsafe_path`.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_ANEUPLOID_SELECTION`, including unintended increased `cell_death`. Expected reasoning: selective death changes population composition without cellular rescue; preserve its harmful transformation. Compiler reports `UNSAFE` in both retained variants and physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. `F06_POPULATION_STATE_CONTROL` is `UNSUPPORTED`.
2. Input: MVA `BB_CHECKPOINT_BYPASS_CIRCUIT` alone. Expected reasoning: separate three asserted checkpoint capabilities from demonstrated implementation and name their overrides. Compiler reports `TARGET_REACHABLE` in H01 and H02, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`. Its lack of rejected variants does not evaluate unrepresented toxicity or establish physical safety.

## retention_criterion
Compare against a generic agent on hidden cases. Measure risks made evaluable, omitted harmful transformations caught and unsupported safety assurances. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
