---
name: synthesis-architecture-generator
description: Use when proposing synthesis architectures beyond the deterministic search registry.
---

## skill_id
synthesis-architecture-generator

## version
0.1.0

## scope
Invent architectures the current deterministic search does not contain. Work backward from the functional target. Do not assume repair of the altered gene, restoration of its protein, a natural pathway, a single component or correction of every cell.

## required_inputs
Read `SynthesisProblem`, `SynthesisReport.required_functions`, `entry_points`, `architectures`, `families`, `search_note`, `known_omissions`, and underlying `Problem.space`, `target`, `unsafe`, `models`, and `observation`.

## reasoning_checklist
1. Consider repair, replacement, bypass, compensation, suppression, stabilization, synthetic combination, population control, cell replacement, feedback control and cross-pathway control. Record a candidate or a specific representation gap for each perspective. Do not invent enum members for these perspectives.
2. Compare capabilities and compositions against the registry and reported search. Explain what is absent; relabelling an enumerated architecture adds nothing.
3. Map every required function to a declared transformation. Expose missing mechanisms, context, delivery and evidence as assumptions.
4. Separate simultaneous composition from sequential claims. Request conflict, precondition, order and minimality checks; prose cannot establish that extra components are essential.
5. Submit gated proposals for evaluation across every evidence-compatible model and candidate. Preserve disagreements and keep logical and physical feasibility separate.

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

## uncertainty_language
Use “proposed architecture; implementation unassessed.” A failed finite search concerns this registry and model. An unrepresented family is a representation gap.

## abstention_conditions
Emit an advisory missing-input finding if target membership is undefined, a variable or value is absent, or a required component has no declared capability. Never invent dynamics to complete a route.

## validation_hooks
`ControlArchitecture` validates structure. `SynthesisProblem` resolves components. `synthesis.composition.conflicts`, `precondition_gaps` and `order_matters` check composition claims. `synthesis.compiler.compile_synthesis` evaluates gated architectures supplied through `proposed`.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `BB_CHECKPOINT_BYPASS_CIRCUIT` alone. Expected reasoning: separate three asserted checkpoint capabilities from demonstrated implementation and name their overrides. Compiler reports `TARGET_REACHABLE` in H01 and H02, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`.
2. Input: MVA composition of `BB_ALIGNMENT_COMPETENCE_SUPPLY`, `BB_ARREST_COMPETENCE_SUPPLY` and `BB_SILENCING_COMPETENCE_SUPPLY`. Expected reasoning: retain all three function requirements and implementation premises. Compiler reports `TARGET_REACHABLE` in both retained variants, physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `UNKNOWN_STABILITY`.
3. Input: MVA `F07_CELL_STATE_REPLACEMENT`. Expected reasoning: identify missing tissue-scale representation without declaring biological impossibility. Compiler reports `NOT_REPRESENTABLE`, with no family architectures because no registered component acts at `tissue_function` scale.

## retention_criterion
Compare against a generic agent on hidden cases. Measure distinct new architectures surviving deterministic validation, unsupported assertions and redundant compositions. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
