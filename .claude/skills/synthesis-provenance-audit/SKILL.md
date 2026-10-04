---
name: synthesis-provenance-audit
description: Use when auditing component lineage, quantitative sources and separation of derived claims from empirical evidence.
---

## skill_id
synthesis-provenance-audit

## version
0.1.0

## scope
Audit provenance and epistemic boundaries. Identify unsupported promotions and uncited constants without changing types, evidence or feasibility automatically.

## required_inputs
Read `Provenance`, `DERIVED_TYPES`, `EMPIRICAL_TYPES`, component `evidence_refs`, `feasibility_status`, `magnitude_if_known`, `time_dependence_if_known`, `SynthesisReport.origin`, `content_digest`, and proposal gate decisions.

## reasoning_checklist
1. Trace every component to provenance or explicit hypothetical status. Verify sources support the capability in its validity domain; internal citations are not external measurements.
2. Require sources for every quantitative constant, including magnitude and time dependence. Empty qualitative fields authorize no estimates.
3. Keep logical and physical feasibility separate. Inspect components' own feasibility fields; composition success cannot establish implementation.
4. Check that no derived type has been promoted to an empirical one without external measurement. `provenance.promote` raises `IllegalPromotion` for unsupported derived-to-empirical promotion.
5. Preserve proposal origin, compiler origin, gate-assigned type and references. A gate acceptance, digest, reviewer opinion or repeated report cannot turn derivation into observation.
6. Audit evidence linkage without treating citation presence as proof. State missing evidence and source scope limits.

## allowed_tools
Read-only repository access; in-memory native schema validation, `proposals.gate` and `synthesis.compiler.compile_synthesis`. Label counterfactual inputs explicitly. No evidence-store mutation, experimental execution or network transfer of case data. Reproduce the benchmark compilation with:

```sh
uv run python -c "from rarepipe.stages.control.synthesis import mva_synthesis; from rarepipe.stages.control.synthesis.compiler import compile_synthesis; r=compile_synthesis(mva_synthesis.problem()); print(r.result.value); [print(a.architecture_id, a.logical.value, a.physical.value, a.stability.value) for a in r.architectures]; [print(f.family_id, f.verdict.value) for f in r.families]"
```

## forbidden_inferences
Reason with agents. Prove with code. Never decide reachability, safety, robustness, observability, feasibility or a result class. The gate assigns the epistemic type, not the proposer. A proposal stating a verdict in any compiler-owned vocabulary, including `ROBUST_CONTROL_CANDIDATE`, `LOGICALLY_SYNTHESIZABLE`, `PHYSICALLY_FEASIBLE`, any `SynthesisResultClass`, or `VALID_CONTROL`, is rejected outright by `proposals.gate`. Keep quoted compiler results in advisory discussion, outside proposal payloads.

Never infer physical feasibility from logical success or promote simulation to evidence. No treatment recommendations, doses, drug names, invented quantitative constants, thresholds, sampling intervals or probabilities. No exact variant notation, genomic coordinates or personal identifiers. Describe the altered protein and its abundance or function qualitatively. Never approve targets, rewrite evidence or contact patients or families.

## output_schema
Emit an advisory Markdown finding with exactly four paragraphs: identify the component, proposal or report and its current provenance; trace references or explicit hypothetical status; identify an uncited constant, unsupported promotion or logical/physical conflation using native fields; state required external evidence or source clarification. Quote compiler results only as attributed records. Assign no replacement epistemic type or verdict. Mutate no record automatically.

## uncertainty_language
Use “explicitly hypothetical,” “source does not support this capability,” or “external measurement missing.” Keep `SIMULATED_PREDICTION` distinct from `OBSERVED_EMPIRICAL` even when reproducible.

## abstention_conditions
Do not certify lineage when sources cannot be inspected or constants lack citations. Report the missing references; manufacture no empirical records.

## validation_hooks
`Provenance` requires references for empirical and literature claims. `BuildingBlock` checks quantitative citations. `proposals.gate` assigns types. `provenance.promote` and `IllegalPromotion` guard promotion. `synthesis.synthesizability.physical_status` evaluates feasibility independently.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_FUNCTION_REPLACEMENT` alone. Expected reasoning: supplying sufficient function bypasses the abundance premise without establishing an implementing component. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`. Registry provenance remains `INFERRED_HYPOTHESIS` and feasibility remains `UNASSESSED`.
2. Input: MVA composition of `BB_ALIGNMENT_COMPETENCE_SUPPLY`, `BB_ARREST_COMPETENCE_SUPPLY` and `BB_SILENCING_COMPETENCE_SUPPLY`. Expected reasoning: retain all three function requirements and implementation premises. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`. Each component retains hypothetical provenance and its own feasibility blocker.

## retention_criterion
Compare against a generic agent on hidden cases. Measure unsupported promotions, uncited constants and feasibility conflations caught, alongside false accusations. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
