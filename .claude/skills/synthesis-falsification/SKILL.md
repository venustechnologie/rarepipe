---
name: synthesis-falsification
description: Use when attacking synthesis architectures for biological failures, confounding and uncertain premises.
---

## skill_id
synthesis-falsification

## version
0.1.0

## scope
Destroy weak architectures by exposing counterexamples and missing premises. Emit advisory findings only. Change no models, evidence or assessments automatically.

## required_inputs
Read `ControlArchitecture`, component `state_transformations`, `ArchitectureAssessment`, `known_omissions`, `unsafe_path`, `blocking_relationships`, `unresolved_relied_on`, and `experiment_discriminators`.

## reasoning_checklist
1. Attack biological compensation, toxicity, lack of specificity, redundant pathways, adaptation, unwanted selection, population effects, loss of the target phenotype and dependence on a single uncertain hypothesis.
2. Tie each attack to a transformation, relationship, stored source or explicit omission. Separate supported counterexamples from unrepresented mechanisms.
3. Examine unsafe intermediate states and every retained model variant. A favorable terminal state cannot erase an unsafe transient; one successful variant cannot erase another's failure.
4. Check whether population readings improve while cellular function stays defective. Preserve denominator and selection explanations.
5. Separate failed implementation from refuted architecture using the component's premise measurement. Use deterministic elimination; invent no prior over architectures.
6. Return the smallest supported attack and its distinguishing observation. No counterexample in this finite model is not a safety certificate.

## allowed_tools
Read-only repository access; in-memory native schema validation, `proposals.gate` and `synthesis.compiler.compile_synthesis`. Label counterfactual inputs explicitly. No evidence-store mutation, experimental execution or network transfer of case data. Reproduce the benchmark compilation with:

```sh
uv run python -c "from rarepipe.stages.control.synthesis import mva_synthesis; from rarepipe.stages.control.synthesis.compiler import compile_synthesis; r=compile_synthesis(mva_synthesis.problem()); print(r.result.value); [print(a.architecture_id, a.logical.value, a.physical.value, a.stability.value) for a in r.architectures]; [print(f.family_id, f.verdict.value) for f in r.families]"
```

## forbidden_inferences
Reason with agents. Prove with code. Never decide reachability, safety, robustness, observability, feasibility or a result class. The gate assigns the epistemic type, not the proposer. A proposal stating a verdict in any compiler-owned vocabulary, including `ROBUST_CONTROL_CANDIDATE`, `LOGICALLY_SYNTHESIZABLE`, `PHYSICALLY_FEASIBLE`, any `SynthesisResultClass`, or `VALID_CONTROL`, is rejected outright by `proposals.gate`. Keep quoted compiler results in advisory discussion, outside proposal payloads.

Never infer physical feasibility from logical success or promote simulation to evidence. No treatment recommendations, doses, drug names, invented quantitative constants, thresholds, sampling intervals or probabilities. No exact variant notation, genomic coordinates or personal identifiers. Describe the altered protein and its abundance or function qualitatively. Never approve targets, rewrite evidence or contact patients or families.

## output_schema
Emit an advisory Markdown finding with exactly four paragraphs: identify the architecture and load-bearing premise; describe the counterexample or omission with its stored source; quote relevant compiler assessment fields and model scope; state the unresolved measurement or modelling requirement. Label counterfactual inputs explicitly. Emit no new verdict. There is no falsification proposal kind; advisory findings change nothing automatically.

## uncertainty_language
Use “competing explanation” for an unobserved mechanism, “model omission” for absent dynamics and “compiler-reported counterexample” for an evaluated path. An unsupported accusation is not falsification.

## abstention_conditions
Stop short of causal accusations when evidence, population denominators or premise measurements are absent. Report missing inputs without inventing outcomes or timing.

## validation_hooks
`synthesis.search.assess_composition` and `synthesis.compiler.compile_synthesis` produce scoped assessments. `UnsafeRegion.violated_by` identifies prohibited states. `synthesis.experiments.premise_tests` and `relationship_discriminators` separate implementation and relationship questions.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_ANEUPLOID_SELECTION`, including unintended increased `cell_death`. Expected reasoning: selective death changes population composition without cellular rescue; preserve its harmful transformation. Compiler reports `UNSAFE` in both retained variants and physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. `F06_POPULATION_STATE_CONTROL` is `UNSUPPORTED`.
2. Input: MVA open-loop `BB_ABUNDANCE_STABILIZATION`. Expected reasoning: restored abundance does not settle the altered protein's function. Compiler reports `REACHABLE_UNDER_SOME_MODELS`: H01 succeeds and H02 fails; physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `MAINTAINED_TARGET`. `REL_BUBR1_ABUNDANCE_FUNCTION` remains blocking.
3. Input: MVA `BB_FUNCTION_REPLACEMENT` alone. Expected reasoning: supplying sufficient function bypasses the abundance premise without establishing an implementing component. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`. Its premise discriminator for `bubr1_function` reports `measurable` as false; no available direct premise reading distinguishes implementation failure.

## retention_criterion
Compare against a generic agent on hidden cases. Measure supported failure modes found, unsupported accusations and missed single-premise dependencies. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
