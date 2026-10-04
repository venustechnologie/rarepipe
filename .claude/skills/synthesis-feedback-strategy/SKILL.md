---
name: synthesis-feedback-strategy
description: Use when proposing measured feedback policies with declared release behavior and no invented sampling interval.
---

## skill_id
synthesis-feedback-strategy

## version
0.1.0

## scope
Propose u = π(y) policies. Every rule reads a measured variable. Policy design is a hypothesis; deterministic exploration decides closed-loop maintenance.

## required_inputs
Read `FeedbackPolicy`, `FeedbackRule`, `Problem.observation`, `BuildingBlockRegistry.controls`, `BlockTransformation.released_to`, `release_rationale`, and `ArchitectureAssessment.feedback_status`.

## reasoning_checklist
1. Map every rule condition to a variable measured by the observation model. A useful latent variable does not become a sensor.
2. Declare activate or deactivate actions against existing controls. A control may only be released if it declares what its variable returns to and what returns it.
3. Describe readings in words. Invent no sampling interval, response delay or race probability.
4. Request exploration of plant states and controls held across every plant/controller interleaving. A loop is only reported as maintaining the target when the unsafe region is structurally unreachable and every terminal strongly connected component lies inside the target. Merely being unlikely to race into danger is insufficient.
5. Separate maintenance under control from survival after withdrawal. Compare the policy with its static architecture and retain model dependence.

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

Use `CompositionMode.CONDITIONAL`. Attach `feedback` as `FeedbackPolicy` with `policy_id`, `rules`, `sampling`, and `provenance` typed `EpistemicType.FEEDBACK_POLICY`. Each `FeedbackRule` supplies `rule_id`, `when` as `Membership`, `action` as `FeedbackAction`, `control_id`, and `rationale`. Policy provenance labels a policy, not a proven loop. The enclosing architecture remains a proposal.

## uncertainty_language
Use “proposed measured policy; maintenance unevaluated.” Quote stability only from code and include the variants where the policy fails.

## abstention_conditions
Do not submit an executable loop with an unmeasured condition or undeclared release. Return an advisory measurement or release gap; invent no reversion mechanism.

## validation_hooks
`synthesis.feedback.unobservable_inputs` and `undeclared_releases` identify gaps. `ReleaseUndeclared` prevents invented releases. `run_closed_loop` explores interleavings; `synthesis.stability.classify` evaluates withdrawal separately.

## benchmark_cases
These cases were checked by compiling the unmodified `mva_synthesis.problem()`. The headline is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`. These are compiler outputs under recorded assumptions, not empirical findings.

1. Input: MVA `PI_ABUNDANCE_SAFETY_GUARDED` using `BB_ABUNDANCE_STABILIZATION`. Expected reasoning: measured feedback and declared release do not resolve the abundance/function hypothesis. Compiler reports `REACHABLE_UNDER_SOME_MODELS`: H01 succeeds and H02 fails; physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `MAINTAINED_TARGET`. `F08_FEEDBACK_CONTROLLED_ROUTE` is `CONDITIONALLY_SUPPORTED`.
2. Input: MVA open-loop `BB_ABUNDANCE_STABILIZATION`. Expected reasoning: restored abundance does not settle the altered protein's function. Compiler reports `REACHABLE_UNDER_SOME_MODELS`: H01 succeeds and H02 fails; physical `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`, stability `MAINTAINED_TARGET`. `REL_BUBR1_ABUNDANCE_FUNCTION` remains blocking.

## retention_criterion
Compare against a generic agent on hidden cases. Measure unmeasured rules and undeclared releases caught, meaningful policy alternatives and unsupported maintenance claims. Retain only demonstrated added value. This comparative evaluation has not been run. Derive metrics from stored records with numerator, denominator and an appropriate interval, or state why no interval applies.
