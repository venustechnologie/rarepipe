# Physical Realization Compiler (Part 1) — design

The synthesis layer can start from a desired functional state and produce architectures that would
mathematically produce it. Its answer for this case is `SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`: a
composition reaches the target, and nothing is known to implement its declared transformations.

This layer tries to cross that frontier:

```
abstract biological transformation  ->  physical mechanism  ->  real components
```

The decomposition is mandatory and the shortcut is the thing being prevented:

```
required function -> mechanism -> biological operation -> physical piece
```

Jumping from `chromosome_alignment` to a drug name removes the entire interesting part of the
reasoning, so a realization is a sequence of steps, each naming the primitive it uses and the
capability of that primitive it relies on.

**Build authorization: Part 1 only.** The global building-block universe is not opened here. There
is no drug catalogue, no gene catalogue, no molecular simulator, no binding prediction, no
pharmacokinetics and no delivery modelling. The interfaces are shaped so those can be added; none
of them is implemented.

## The constraint that makes this honest

A physical layer could be populated with invented biology faster than anyone could check it. So the
evidence inventory is **derived from the repository**, by walking the case's own causal chain
(`simulate.mva.mva_chain()`). A capability does not cite a free-text reference it could have made
up; it cites an **evidence edge** that already exists, with the support level, scope and caveats the
chain already records. Consequences:

- a capability citing an edge the chain does not contain is refused, not graded (`Unentitled`);
- a capability cannot grade its own evidence — the entitlement is computed from what the repository
  recorded;
- when the chain's evidence changes, every entitlement recomputes and the committed maps go stale.

The chain holds five citations. Four concern the route through the altered protein's abundance, and
the fifth is a null result on the shortest version of that route.

## Two questions, kept apart

Whether evidence supports a mechanism at all is not whether it transfers to this child's cells.
Folding the second into the first makes every step fail for the same blanket reason and throws away
the only information worth having — *which* step breaks, and why.

- **`entitle`** answers the mechanistic question, and the chain's own label is authoritative. Where
  the chain flagged a substitution (`different_agent`, `different_compartment`), the realization
  must match on that dimension or the claim does not transfer. Where it did not flag one, the
  support level already accounts for it and this module does not second-guess it.
- **`transfer_gap`** answers the other question separately: the system a measurement was made in
  versus the one the case needs. Almost nothing here was measured in patient-derived cells, which is
  precisely why an experiment exists — and recording that as a gap rather than as a broken mechanism
  is what lets `CONTEXT_MISMATCH` mean *the mechanism exists, but not here*.

A relative label lifts only when the realization matches the dimension the label names. The
`different_agent` label on the deacetylation step means the effect was produced with a different
precursor than the case proposed; a chain that administers the precursor the experiment used is not
making a substitution, and its entitlement falls back to the measurement's own level. The agent
checked is the one the **realization administers**, never one a capability happens to declare —
otherwise a chain giving one compound would inherit the evidence of another.

## Epistemic burden

Non-probabilistic, and read from what is being replaced rather than set by the proposer:

| Burden | Sufficient entitlement |
|---|---|
| `BYPASSES_UNRESOLVED_RELATIONSHIP` | `SUPPORTED` or `CONDITIONAL` |
| `BYPASSES_ASSUMED_RELATIONSHIP` | `SUPPORTED` or `CONDITIONAL` |
| `BYPASSES_SUPPORTED_RELATIONSHIP` | `SUPPORTED` |
| `BYPASSES_ESTABLISHED_RELATIONSHIP` | `SUPPORTED` |

The better established the natural mechanism being substituted, the higher the evidence bar. The
bypass this phase targets replaces one relationship the model records as **established** and two it
records as **assumed**, so the three required functions do not carry the same burden — and the
report says which is which.

## No invented numbers

There is no probability of success, no expected information gain, no efficacy score and no
model-generated confidence anywhere in this layer. The permitted words are `SUPPORTED`,
`CONDITIONAL`, `UNSUPPORTED`, `CONTRADICTED`, `UNKNOWN` and `CONTEXT_MISMATCH`.

## The deterministic checks

Agents generate possibilities; these decide what may stand.

| Check | What it refuses |
|---|---|
| direction | a component whose effect on the target opposes what the transformation needs |
| sign | a capability claiming an effect the claim it cites does not imply |
| provenance | a step with no cited claim, or one citing a claim about a different input |
| connectivity | a chain whose step needs an input no step produces |
| dependency | a declared requirement nothing in the chain supplies |
| compatibility | two components where one destroys a precondition of the other |
| safety | a capability touching a safety variable without saying what value it drives it to, and any that drives one into a forbidden state |
| redundancy | a component whose removal changes nothing |
| confounding | a readout resting on a caveated claim with no observable that would exclude it |

## Recursive decomposition

A transformation with no direct chain is not a dead end: it may declare the sub-transformations it
reduces to, each compiled in turn, depth-capped and cycle-guarded. `chromosome_alignment` reduces to
`pp2a_b56_recruitment`, which is compiled and reported on its own — with its own burden, since the
relationship it would replace is recorded differently.

## What the MVA case produces

Two targets are compiled, because the contrast is the finding.

**`BB_CHECKPOINT_BYPASS_CIRCUIT`** → `NO_GROUNDED_REALIZATION`. The architecture is logically
sufficient (re-derived, not carried over). But the inventory attributes every checkpoint function to
the altered protein and to nothing else, so a bypass has nothing to cite. Each of the three
functions is reported with the capability that would have to exist.

**`BB_ABUNDANCE_STABILIZATION`** → `CONTEXT_MISMATCH`, and here the layer discriminates:

| Chain | Verdict | Breaks at |
|---|---|---|
| direct, with the proposed precursor | `NO_GROUNDED_REALIZATION` | the one step it has — the claim is `CONTRADICTED` by the null result |
| via the proposed precursor | `CONTEXT_MISMATCH` | the blood-to-cell transfer (compartment) and the deacetylation (agent) |
| via the precursor the cited work used | `EVIDENCE_INSUFFICIENT` | getting the precursor into the cell — nothing in the inventory claims any agent does |

The two indirect chains break at **different** steps, and between them they ground every step except
one: nothing in this repository grounds getting the precursor into the cell. That is the same gap the
simulator phase's sensitivity analysis identified as unmeasured, reached by an unrelated method.

## Stop condition

> Can we turn at least one abstract function into a grounded physical chain of real components?

Not yet, and the compiler says why in one sentence rather than in a shrug. Three outcomes were
equally acceptable; this is the middle one, and the open problem is now a single named measurement.

## Proof gates and mutation testing

Twelve gates in `tests/test_realization_gates.py`, mapped in
[`REALIZATION_REQUIREMENTS.md`](REALIZATION_REQUIREMENTS.md). All thirty-one tests passed on the
first run, which proves nothing on its own, so each property was broken deliberately. Ten mutations
were caught immediately. Two survived, and both turned out to be redundant enforcement rather than
inert gates: re-aiming at the load-bearing line — the relative-label lift, and the provenance
finding — caught both. Writing the toys also exposed a genuine hole in the checks: nothing verified
that a capability's cited claim was about the input it actually acts on, which is now its own check.
