# Biological State Control Compiler — design

## The principle

> **Reason with agents. Prove with code.**
>
> Agents may propose biological states, mechanisms, alternative routes, models, controls,
> actuators and experiments. Deterministic mathematical code must evaluate constraints,
> reachability, consistency, observability, provenance and safety wherever those concepts have
> formal semantics. Missing biological knowledge must remain an explicit unknown. The system must
> never manufacture quantitative semantics merely to complete a computation.
>
> **We do not ask only what an intervention will do.**
> **We specify what biology must do, then solve for how to make it happen.**

## The inverse problem

Forward: *intervention → predicted outcome*. Inverse: *desired state → required controls →
possible interventions*. Given

```
P = (X0, X_target, X_unsafe, M, U, Y, E)
```

the compiler asks whether some control strategy drives every evidence-compatible initial state
into the target region without any trajectory entering the unsafe region — and, when it cannot
decide, names exactly what is missing.

## Decisions that shape everything

**Unknown functions are universally quantified, and fixed per trajectory.** An `UNKNOWN_FUNCTION`
relationship expands into every function consistent with what is known about it. Each candidate is
a separate variant, fixed for that variant's whole trajectory. If a route works under every
candidate, the unknown is irrelevant to the question; under none, the route fails regardless; under
some, that relationship is the named blocker. Letting the search choose the unknown's value afresh
at each step would let it exploit ignorance.

**The initial state is a set, and an empty set is a falsified model.** X0 is every state consistent
with the evidence and at steady state under a variant. A variant with empty X0 is excluded and
reported as excluded, because "works for every initial state" is vacuously true of nothing. In the
MVA case this is how the diagnosis rules out the biology in which the child would not have MVA.

**All interleavings, hard safety.** With controls held, any out-of-equilibrium relationship may
fire, in any order. A step is safe only if no reachable state under any interleaving is unsafe.
Safety is never a weighted term: ranking is lexicographic with safety first, so no benefit can buy
back a violation.

**Missing is not constant.** A non-exogenous variable that the target or safety depends on, with no
defining relationship, makes the compiler fail closed. Declaring a variable exogenous requires a
stated reason.

**Safety must be observed, not predicted.** Every variable a safety constraint refers to must be
measured by the verifying experiment. A model's prediction that cell death will not move is
precisely what cannot certify safety, because the model's omissions are why death is measured.

**A discriminator must be unfakeable by omitted causes.** A measurement separates two biologies
only if no uncontrolled exogenous ancestor could produce the same reading. Otherwise it is valid
only alongside a measurement of that ancestor — rules B17/B18 generalised.

**Agents propose; the gate assigns the epistemic type.** A proposal claiming to be observed or
established is not believed; agents cannot approve targets or assert feasibility; no proposal can
carry a result class. Only `compile_problem` constructs a result, and the report validates that its
contents support the class it carries.

## What this phase is not

Not a virtual cell, not an ODE solver, not a treatment recommender. This phase implements the
finite-state formalism because every measurement in the first case is categorical. Interval, ODE
and stochastic formalisms are named in the model contract and refused until an adapter to an
established solver is added.

## Layout

| Module | Role |
|---|---|
| `provenance.py` | epistemic types, provenance, accountable approval |
| `state_space.py` | hybrid state space; qualitative values stay qualitative |
| `target_constraints.py`, `safety_constraints.py` | target region, unsafe region — separate, first-class |
| `dynamics.py` | relationships (table or explicit unknown) and models |
| `uncertainty.py` | unknown-function expansion, initial-state sets |
| `controls.py` | biological control variables, never drugs |
| `reachability.py` | all-interleaving exploration, attractors, strategy search |
| `observability.py` | direct-observation and distinguishability checks |
| `experiment_design.py` | deterministic discriminating measurements |
| `controllability.py` | per-strategy verdicts and blocker attribution |
| `objective.py` | lexicographic ranking; safety first, no weights |
| `model_registry.py`, `actuator_registry.py` | admission rule; actuators only after a route exists |
| `proposals.py` | the agent boundary |
| `compiler.py`, `render.py` | the pipeline, the immutable report, the control map |
| `mva.py` | the first case |

Proof gates A–H: `tests/test_control_gates.py`. Invariants I1–I12: `tests/test_control_invariants.py`.
Both were mutation-tested: each was confirmed to fail when the property it guards was deliberately
broken.
