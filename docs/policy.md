# Robust contingent policy search

> Reason with agents. Prove with code. This is the code half: given a compiled AND/OR decision
> graph, it answers whether a *plan* exists that reaches a target whatever the admissible results
> turn out to be — and when there is none, what the best next experiment is and why the answer is no.
>
> No language model is anywhere in this path. That is the point. The mathematical result has to
> exist without one; only then is it handed to a model to explain.

## The question this answers

The contingent route map (`docs/control/MVA_CONTINGENT_ROUTE_MAP.md`) computes two reachability
claims and explicitly declines the third:

| claim | meaning | computed by |
|---|---|---|
| `CONDITIONAL_REACHABLE` | reachable if the branches fall a particular way | `compile_route_map.py` |
| `SINGLE_OUTCOME_RESILIENT` | no *single* admissible result closes it | `compile_route_map.py` |
| `ROBUST_REACHABLE` | a policy that wins under **every** admissible combination | **here** |

Formally, with `K` a knowledge state, `a` an action and `o` an outcome:

```
ROBUST(K, h) = ∃a ∀o ∈ Outcomes(a, K) : ROBUST(UPDATE(K, a, o), h−1)
```

with terminal cases for success, a closed route, an unsafe closure and an exhausted horizon. The
route map's own code says in as many words that it searches no such policy space, and that calling
single-outcome resilience "robust" overstated it.

## Three-valued, on purpose

`robust_reachable` is `TRUE`, `FALSE`, or `NOT_ESTABLISHED` with a reason:

- `HORIZON` — no policy was found within the campaign budget. A deeper search might find one.
- `BUDGET` — the search stopped before it could tell.

Neither is `FALSE`. A solver that reported "no robust policy within 6 campaigns" as "no robust
policy" would be repeating exactly the overstatement that got the earlier claim renamed, and a
solver that reported *running out of time* as a negative result would be worse.

## Layout, and the boundary that matters

```
src/rarepipe/stages/control/policy/     ← domain-neutral. Knows no biology.
    graph.py          the input language: four node kinds, five terminal roles
    state.py          K = (R, U, C, S), immutable, canonical; the actuator registry
    actions.py        declared campaigns, undeclared resolvers, unavailable branches
    update.py         UPDATE(K, a, o) and the predicates the search asks of a state
    reachability.py   conditional reachability; the cheap relaxation; the branch floor
    ranking.py        lexicographic ordering and the guaranteed-progress vector
    certificates.py   why the answer is no, in a checkable form
    robust_policy.py  the search; solve_policy(...) is the entry point
    solvers/exact.py  the reference solver: the definition, with nothing clever in it

tools/control/solve_mva_policy.py       ← the only place MVA vocabulary meets the solver
```

The arrow points one way and `tests/test_policy_boundary.py` enforces it: the adapter imports the
engine, the engine imports nothing of the adapter's, names no case vocabulary in its code, and
cannot read a file. That is what lets the solver be lifted out behind a package boundary later
without the algorithm being rewritten.

```python
solve_policy(graph, knowledge_state, target, constraints, horizon)
```

## Running it

```bash
uv run rarepipe reason --horizon 3                       # the verdict, with certificates
uv run rarepipe reason --horizon 3 --output answer.json  # the full machine-readable answer
uv run python tools/control/solve_mva_policy.py --horizon 2           # regenerate the report
uv run python tools/control/solve_mva_policy.py --check --horizon 2   # CI: it is not stale
```

`docs/control/MVA_ROBUST_POLICY.md` is committed at **horizon 2**, which re-derives in about
twenty seconds, because CI re-derives it on every push and the search costs roughly thirty times
more per unit of horizon. The horizon-3 result — *no robust policy using three campaigns or
fewer*, searched exhaustively — is reproduced with `uv run rarepipe reason --horizon 3` and takes
a couple of minutes. Nothing about the structural findings below depends on the horizon.

## Decisions a reader should know about

**An action is not a branch.** Branches are units of ignorance; actions are units of work, and one
campaign can settle several branches. The action space is the declared campaigns plus, for every
branch no campaign covers, an `UNDECLARED_RESOLVER` — tagged, because it is *not* a claim that a
runnable experiment exists. A recommendation resting on one is a recommendation to go and design an
experiment, and it reads that way in the output. Branches gated behind a capability the caller has
not declared available are not actions at all; they are reported with the capability each needs,
because "we are not authorised to do this" and "this would not help" are different findings.

**Invalid runs are not results.** An outcome recording that an assay voided its own validity gates
is a failure to observe, not a state of the world. Quantifying over those would make every policy
fail robustness on the grounds that any experiment can break — true, and useless. They are excluded
from the ∀ by default, the exclusion is listed in the output, and the report gives the verdict both
ways so the choice is a number rather than an argument.

**Arm state is canonical, not logged.** Observing that one actuator harms the population does not
establish that its control variable is unsafe, and does not close the other actuators that reach
the same variable. Closures are recorded per actuator in `K`; a control variable closes only when
every one of its actuators has failed a test that actually engaged the target. A null without
validated engagement leaves the variable open. At planning time the engine closes nothing, because
it cannot know which arm will fail and guessing would invent a closure.

**Nothing is a weighted sum.** Policy ranking is the specification's seven rules, lexicographically.
Guaranteed progress is a five-component vector, also lexicographic. A sum would need weights that
nothing grounds, and would let a soft criterion outvote a safety constraint.

**Two progress components have no data behind them** in a graph that does not annotate them, and
they come back `null` rather than `0`, with the reason stated:

- *hypotheses eliminated* needs each hypothesis to name the branches that discriminate it;
- *families resolved* needs node-to-family membership.

Inferring either from identifier spelling is the shortcut that has already produced one wrong
answer in this repository, so it is not done.

## How it is made affordable, and what that costs

The full map has 56 branches, most with three to seven outcomes. Blind enumeration is hopeless, so:

- the action space is restricted to branches the target can actually depend on — exact, because
  settling anything else can only remove routes to the target and never add one;
- the ∀ loop tests the outcome most likely to defeat an action first, and exits there;
- the ∃ loop stops at the first robust action, except at the root, where every action is scored so
  that **all** tied optima are returned rather than one of them;
- states are memoised on a canonical form that excludes history, and both verdicts are monotone in
  the horizon, so a `FALSE` is never recomputed at a deeper one;
- the recursion asks a boolean relaxation (compiled once per target) rather than enumerating
  minimal branch sets — 0.2 ms against 330 ms on this map, and
  `tests/test_policy_reachability.py` asserts the two never disagree, which is what licenses the
  substitution;
- subtrees that cannot fit in the remaining horizon are skipped using an admissible floor on the
  branches still to resolve. Admissible, never an overestimate, and tested as such — pruning on a
  bound that overstated the distance would discard a reachable policy.

**The honest limit.** Even so, recursion states grow by roughly a factor of thirty per unit of
horizon on this map — 36 at horizon 2, 1 232 at horizon 3, and horizon 4 exhausts a twenty-thousand
state budget without settling. The exact verdict is affordable to horizon 3; beyond that the search
reports `NOT_ESTABLISHED/BUDGET` rather than guessing, and `no_robust_policy_within` records the
deepest horizon whose policy space *was* searched exhaustively, which is the claim a reader can
rely on. Closing the gap is what the specification's symbolic solver — BDD for sets of worlds,
SAT/SMT for constraints — is for, and on this evidence it is required for the horizon-6 question
rather than an optional optimisation. The structural certificates below are not subject to that
limit and are computed exactly.

The budget counts **state evaluations**, not recursion entries. One recursion step examines a few
hundred candidate successors, and those are what cost the time and fill the memo tables; a budget
counting entries bounded neither, and let a search report twenty thousand states while holding over
a gigabyte of cached statuses.

## No silent truncation

An earlier implementation of the minimal-set frontier elsewhere in this repository capped candidate
sets at eight per node to bound the cross-product at conjunctions, and the cap was invisible in the
output. That matters because enumerating every tied optimum is a correctness property here: with
the cap removed, the cellular target turns out to have **four** tied minimal routes where the
published document presents one as "the" smallest. The frontier in this package is uncapped by
default; where a caller sets a cap, every affected node is named in the output.

The ranking does read distance off a capped frontier, which is sound for that one question: pruning
discards the *largest* sets and so cannot change the smallest one's size. It would undercount the
set of outstanding branches, which is why that number comes from the graph instead. Both properties
are tested.

## Certificates

When the answer is not `TRUE`, the output carries:

- **minimal closing combinations** — sets of results that leave the target structurally
  unreachable, smallest first, with the searched size stated. Absence from the list is not evidence
  that none exists at a larger size, and the output says so.
- **the robust subset** — which conjuncts of the target *are* robustly reachable. "Nothing works"
  and "three of four conjuncts are guaranteed and the fourth is not" are different findings.
- **an adversary witness** — for every action the planner could take, the outcome that defeats it,
  recursively. The counter-policy, replayable by hand against the map.

## What this does not establish

- Nothing about any patient. The target is a cell-level functional state in a model system.
- No probability. None is computed and none is available; the schema may reserve the field, and
  this version never writes it.
- No claim that an undeclared resolver is a runnable experiment.
- Reaching the cell-level target says nothing about the organism-level target, which keeps its own
  gates and is not solved here.
