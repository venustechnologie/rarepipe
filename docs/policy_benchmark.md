# Policy benchmark (ENIGMA-002A)

> The harness is built before the symbolic solver, deliberately, so that errors in the episodes,
> the schemas and the metrics surface now rather than after a deeper solver exists.
>
> Nothing here runs a language model. What is built first is the part that decides whether an
> answer is **right**, because a benchmark whose scorer is unverified measures nothing.

## What exists, and what does not

| piece | state |
|---|---|
| exact oracle, with refusal | built |
| episode generator over legal states | built |
| synthetic graphs with known answers | built — eleven of them |
| development / validation / locked splits, sealed | built |
| response contract and its validator | built |
| the six primary metrics | built |
| runner, provenance, reproducibility | built |
| **Arm E — engine only** | built |
| **Arms A–D** (model alone / + map / + generic tools / + engine) | **not built** |
| locked competitive comparison | **not run** |

There is no competitive result here and nothing in this page should be read as one. Arm E is the
engine answering with the engine's own answer: it measures the harness and the solver, never an
advantage over anything.

## The restriction that makes it honest

Real episodes are confined to the region where the exhaustive solver is exact — a horizon of three
today. That is a restriction on the *episodes*, not a softening of the oracle. An episode whose
answer could not be computed exactly is **refused**, and three things disqualify one:

- the search budget ran out;
- the horizon was not exhausted, so nothing is established about the question asked;
- the frontier reported truncation.

The third matters most. Route completeness is scored against the tied-optimum list, so an oracle
that had itself dropped a tied optimum would mark a correct answer wrong.

A `NOT_ESTABLISHED/HORIZON` verdict **is** admissible when the space up to that horizon was
exhausted, because "no robust policy uses N actions or fewer" is itself an exact result.

Refusals are counted and published rather than dropped. The refusal rate is how far the exhaustive
solver reaches, and that is the number that decides when the symbolic solver stops being optional —
which is the acceptance criterion ENIGMA-003 inherits: **symbolic must equal exact everywhere exact
computation is feasible**, and `oracle.py` is what certifies feasible.

## Why synthetic graphs as well as the real one

One hand-built graph is one shape, and a solver tuned until it passes it has learned that graph
rather than the problem. The eleven synthetic cases have answers that follow from their
construction, so a disagreement is a solver bug rather than a question about biology. They cover
alternative routes, AND nodes, safety closures, campaigns resolving several branches, invalid-run
outcomes, dead ends, multiple tied optima and a deceptively short route.

Both the optimised and the reference solver match every one.

## Frozen, and checkable

"Frozen before any prompt or algorithm is tuned" only means something if it is written down and
verifiable, so two mechanisms replace the promise:

**Assignment is by content.** An episode's split comes from a digest of its own id and the salt, so
adding a hundred episodes moves none of the existing ones — tested directly. Each source is split
and sealed separately, so adding a source cannot move another source's locked episodes.

**The locked split carries a seal** over its episodes and their oracle answers, recomputed in CI.
An edited, re-split or regenerated locked set stops matching, so a published figure can be traced
to the exact set it was measured on. Rebuilding the set is a deliberate act that changes the seals.

The runner refuses to touch the locked split without an explicit `allow_locked=True`, because a
default that quietly used it is how a test set gets tuned against by accident.

## Two rules in the metrics

**A metric that does not apply reports `null`, not zero.** Outcome coverage of a policy that should
not exist is not zero coverage; it is not a measurement. Averaging absence as zero punishes a
system for correctly declining to answer.

**Malformed is not the same as wrong.** An arm that cannot produce the schema has told us something
about itself, so those rows are counted and reported as a malformed rate rather than discarded,
which would flatter it.

Every aggregate publishes the denominator of its mean. Two arms scoring 0.9 on a metric that
applied to forty episodes and to four are not comparable, and that stays visible instead of
requiring trust.

## What the metrics are for

Each exists because one particular way of being wrong would otherwise go unmeasured:

| metric | the failure it catches |
|---|---|
| `policy_validity` | a confident answer about a branch or outcome not in the graph at all |
| `robust_reachability_accuracy` | the three-valued verdict, exactly; no partial credit |
| `outcome_coverage` | a policy that does not say what to do after some admissible result |
| `safety_error` | a branch ending `UNSAFE` offered as an acceptable continuation |
| `optimality_regret` | choosing a worse action, measured in worst-case further campaigns |
| `route_completeness` | returning one tied optimum as though it were unique |

Plus `reproducibility`, reported beside accuracy and never instead of it — a system can be
consistently wrong.

Naming an action the episode does not offer is tracked as its own error rather than folded into a
large regret, because it is a different mistake.

## Running it

```bash
uv run python tools/control/build_policy_benchmark.py --count 24 --horizon 2   # build and seal
uv run python tools/control/build_policy_benchmark.py --check                  # CI: seals verify
```

The committed artifacts are `data/policy_benchmark/episodes.json` and the generated report
`docs/control/MVA_POLICY_BENCHMARK.md`.

## Adding an arm

An arm is a callable that sees an episode and returns a response in the contract. That is the whole
interface, which is what lets a deterministic solver and a language model be compared on the same
footing:

```python
from rarepipe.stages.control.benchmark import arms

def answer(episode, context) -> dict:    # raw response JSON
    ...

arm = arms.from_callable("A_llm_only", answer)
```

An arm that raises becomes a malformed response rather than a crash, because an arm falling over is
a finding to record.

## What this does not establish

- No competitive claim of any kind. Arms A–D do not exist.
- Nothing about any patient. An episode is a partial knowledge state over a formal graph.
- No probability anywhere.
- The locked splits have not been measured. They are for once, at the end.
