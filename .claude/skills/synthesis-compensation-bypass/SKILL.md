---
name: synthesis-compensation-bypass
description: Use when finding synthesis routes around a blocked node and identifying their relationship overrides.
---

## skill_id
synthesis-compensation-bypass

## version
0.1.0

## scope
Propose compensation and bypass architectures around blocked biology. Preserve the target and expose independently supplied functions as implementation requirements.

## required_inputs
Read `RequiredFunction.causal_ancestors`, `unresolved_dependencies`, `BuildingBlockRegistry`, relationship `epistemic_status`, and `ArchitectureAssessment.overrides_relationships` and `blocking_relationships`.

## reasoning_checklist
1. Identify the blocked node and downstream functions required by the target. Separate bypassing a dependency from resolving it.
2. Holding a variable that a relationship already defines is an override of that relationship. Each override is a requirement of its own. Name its supplying mechanism or the missing capability.
3. Overriding an `established` relationship is a larger claim than filling a gap. Preserve the epistemic status beside every override.
4. Compare one mechanism supplying several functions with separate compensating components. State their distinct specificity, coupling and implementation burdens.
5. Inspect preconditions, conflicting held values, unintended transformations and population effects. Refer composition outcomes to code.

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

Use `ProposalKind.ARCHITECTURE`. The payload follows `ControlArchitecture`: `architecture_id`, `family`, `composition`, `composition_mode`, `target_constraints`, `required_conditions`, `feedback`, `origin`, `rationale`, and `assumptions`. The gate supplies `provenance` and assigns `EpistemicType.PROPOSED_ARCHITECTURE`. Output remains `PROPOSED_ARCHITECTURE`, never `VALID_CONTROL`. Components must resolve in `BuildingBlockRegistry` before constructing `SynthesisProblem`; propose missing capabilities separately. No assessment fields belong in the payload.

Record each override and missing supplying mechanism in `assumptions`; explain the bypass in `rationale`. Advisory gaps change no relationship automatically.

## uncertainty_language
Use “asserted downstream function” and “override requirement.” Compiler-reported independence from an unknown does not resolve it.

## abstention_conditions
Return an advisory gap for an absent variable or unspecified transformation. Never erase an established relationship to make a bypass appear natural.

## validation_hooks
`synthesis.composition.moved_variables` identifies controlled outputs. `synthesis.search.assess_composition` records `overrides_relationships`. `synthesis.compiler.compile_synthesis` owns outcomes; `conflicts` and `precondition_gaps` expose incompatible capabilities.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_CHECKPOINT_BYPASS_CIRCUIT` alone. Expected reasoning: separate three asserted checkpoint capabilities from demonstrated implementation and name their overrides. Compiler reports `TARGET_REACHABLE` in H01 and H02, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`. Recorded overrides are `REL_FUNCTION_ACTIVATION` (established), `REL_FUNCTION_ALIGNMENT` (assumed) and `REL_FUNCTION_SILENCING` (assumed).
2. Input: MVA composition of `BB_ALIGNMENT_COMPETENCE_SUPPLY`, `BB_ARREST_COMPETENCE_SUPPLY` and `BB_SILENCING_COMPETENCE_SUPPLY`. Expected reasoning: retain all three function requirements and implementation premises. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`.
3. Input: MVA `BB_FUNCTION_REPLACEMENT` alone. Expected reasoning: supplying sufficient function bypasses the abundance premise without establishing an implementing component. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`. Its override is `REL_BUBR1_ABUNDANCE_FUNCTION` (unresolved).

## retention_criterion
Compare against a generic agent on hidden cases. Measure new bypass requirements identified, missed overrides and unsupported claims of resolving blocked biology. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
