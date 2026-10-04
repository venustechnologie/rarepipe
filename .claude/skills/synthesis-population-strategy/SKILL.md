---
name: synthesis-population-strategy
description: Use when proposing population-scale architectures with explicit differential mechanisms and confounder measurements.
---

## skill_id
synthesis-population-strategy

## version
0.1.0

## scope
Propose population control and cell replacement concepts. Never equate population improvement with cellular rescue. A changed fraction and restored function in an individual cell are separate claims.

## required_inputs
Read `PopulationLayer`, `PopulationMechanism`, `ConfoundingProcess`, `PopulationRequirement`, `Problem.observation`, `target`, `unsafe`, and `ArchitectureAssessment.rescue_scope`.

## reasoning_checklist
1. Name the population variable and what produces the differential: growth, death, transition, replacement or competition. “Selection” is not an answer. State why subpopulations respond differently.
2. Declare every process that could fake the reading, including omitted processes with no graph node. Name observables that would exclude each and check whether they are measured.
3. Use `source_of_differential` for the mechanism and `excluded_by` for confounder observables. Retain denominator effects and direct measurements of death, viability and division.
4. Preserve target membership and human ownership of thresholds. A population-only architecture corrects no cell; state this beside any quoted population result.
5. Expose missing tissue-scale variables and capabilities as gaps. Do not replace a cellular target with a population endpoint.

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

Attach a separate advisory finding describing proposed population declarations. Use native `PopulationMechanism` fields `mechanism_id`, `produces`, `drives`, `requires`, `source_of_differential`, `affects_scale`, and `provenance`. Use `ConfoundingProcess` fields `process_id`, `could_produce`, `reading`, `mechanism`, `excluded_by`, `represented_in_model`, and `provenance`. There is no population proposal kind. These declarations remain advisory; do not insert them as extra architecture fields or mutate `PopulationLayer` automatically.

## uncertainty_language
Use “population composition change; no cellular rescue established.” No declared confounder gap does not establish that all biological confounders are represented.

## abstention_conditions
Return an advisory missing-input finding when the differential is unnamed, confounders lack distinguishing observables, or success requires an invented threshold.

## validation_hooks
`PopulationLayer.check`, `undeclared_movers` and `gaps` check representation and measurement coverage. `synthesis.population.rescue_scope` records scale. `synthesis.compiler.compile_synthesis` owns outcomes.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_ANEUPLOID_SELECTION`, including unintended increased `cell_death`. Expected reasoning: selective death changes population composition without cellular rescue; preserve its harmful transformation. Compiler reports `UNSAFE` in both retained variants and physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. `F06_POPULATION_STATE_CONTROL` is `UNSUPPORTED`.
2. Input: MVA `F07_CELL_STATE_REPLACEMENT`. Expected reasoning: identify missing tissue-scale representation without declaring biological impossibility. Compiler reports `NOT_REPRESENTABLE`, with no family architectures because no registered component acts at `tissue_function` scale.

## retention_criterion
Compare against a generic agent on hidden cases. Measure undeclared differentials, confounders with distinguishing observables and false cellular-rescue interpretations. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
