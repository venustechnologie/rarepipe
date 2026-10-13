# ENIGMA handover

Start from branch **`claude/kind-faraday-9pwjif`**, commit **`2a0da07`**.

Two tickets are done: **ENIGMA-001** (the reasoning engine) and **ENIGMA-002A** (the shallow
benchmark harness). Arms A–D and the symbolic solver are not built. Nothing in either ticket runs a
language model, which is deliberate — the mathematical result has to exist without one before it is
handed to a model for explanation.

Design rationale lives in [`docs/policy.md`](../../../../../docs/policy.md) and
[`docs/policy_benchmark.md`](../../../../../docs/policy_benchmark.md). This file is only what you
need to pick the work up.

---

## What ENIGMA-001 does

The compiled route map (`docs/control/MVA_CONTINGENT_ROUTE_MAP.yaml`) computes conditional
reachability and single-outcome resilience, and reports `ROBUST_REACHABILITY` as `NOT_ESTABLISHED`
because it searches no policy space. ENIGMA-001 searches it:

```
ROBUST(K, h) = ∃a ∀o ∈ Outcomes(a, K) : ROBUST(UPDATE(K, a, o), h−1)
```

The verdict is **three-valued**. `NOT_ESTABLISHED` carries a reason of `HORIZON` (no policy found
within the campaign budget) or `BUDGET` (the search stopped before it could tell). Neither is
`FALSE`. A separate field, `no_robust_policy_within`, records the deepest horizon whose policy
space was actually *exhausted* — that is the claim a reader can rely on, and it survives the search
later running out of budget.

When no robust policy exists the engine switches to discovery mode and returns the action whose
**worst** admissible outcome still guarantees the most progress (maximin over a five-component
lexicographic vector, never a weighted sum).

## What ENIGMA-002A does

The harness that decides whether an answer is *right*: an oracle that refuses rather than rounds,
episodes confined to where the exhaustive solver is exact, synthetic graphs whose answers follow
from their construction, content-addressed and sealed splits, a response contract, six metrics, and
a runner that records what a run was measured on.

**Arm E (engine only)** exists and is the harness's self-test — it recomputes rather than echoing
the stored oracle, so a broken solver surfaces there. It is not and cannot be a competitive claim.

---

## Where things live

```
src/rarepipe/stages/control/policy/          ← the engine. Domain-neutral, standard library only.
    graph.py          input language: 4 node kinds, 5 terminal roles
    state.py          K = (R, U, C, S), immutable + canonical; the actuator registry
    actions.py        declared campaigns, undeclared resolvers, unavailable branches
    update.py         UPDATE(K, a, o) and the predicates the search asks of a state
    reachability.py   conditional reachability; the cheap boolean relaxation; the branch floor
    ranking.py        lexicographic ordering + the guaranteed-progress vector
    certificates.py   cut sets, success sets, adversary witness
    robust_policy.py  the search. solve_policy(...) is the entry point
    solvers/exact.py  the reference solver: the definition, with nothing clever in it

src/rarepipe/stages/control/benchmark/       ← the harness. Imports the engine, never the reverse.
    oracle.py   episodes.py   splits.py   contracts.py   metrics.py   runner.py
    arms.py     synthetic.py

tools/control/solve_mva_policy.py            ← the ONLY place MVA vocabulary meets the solver
tools/control/build_policy_benchmark.py      ← builds and seals the episode set
data/policy_benchmark/episodes.json          ← the frozen, sealed set (committed on purpose)
docs/control/MVA_ROBUST_POLICY.md            ← generated; CI checks it is not stale
docs/control/MVA_POLICY_BENCHMARK.md         ← generated; CI checks the seals
```

**The dependency boundary is load-bearing and enforced**, not advisory. `tests/test_policy_boundary.py`
asserts that `policy/` imports nothing outside itself, names no case vocabulary in its *code*,
cannot read a file, and imports no third-party package. That is what lets the engine be lifted out
behind a package boundary later without rewriting the algorithm. If it fails because the engine grew
a convenient import, pass the value in as an argument instead of relaxing the test.

```python
solve_policy(graph, knowledge_state, target, constraints, horizon)
```

---

## Commands

```bash
uv sync

# the engine on the real map
uv run rarepipe reason --horizon 3
uv run rarepipe reason --horizon 3 --output answer.json

# regenerate the committed reports (CI checks both are current)
uv run python tools/control/solve_mva_policy.py --horizon 2
uv run python tools/control/solve_mva_policy.py --check --horizon 2

# build and seal the benchmark (minutes), or just verify the committed seals (seconds)
uv run python tools/control/build_policy_benchmark.py --count 24 --horizon 2
uv run python tools/control/build_policy_benchmark.py --check

# the tests
uv run pytest tests/test_policy_gates.py tests/test_policy_boundary.py \
               tests/test_policy_reachability.py tests/test_policy_mva.py \
               tests/test_policy_benchmark.py -q          # 146 pass, ~50s

uv run python tools/network/check_invariants.py --package src/rarepipe/stages/control
```

---

## The exact-solver limitation

Recursion states grow roughly thirtyfold per unit of horizon on the real map:

| horizon | states in the verdict search | time | verdict |
|---|---|---|---|
| 2 | 36 | ~1 s | no robust policy within 2, exhaustively searched |
| 3 | ~1 200 | ~30 s | no robust policy within 3, exhaustively searched |
| 4 | — | ~5 min | exhausts a practical budget; reports `NOT_ESTABLISHED/BUDGET` |

Those counts are the verdict search alone. `rarepipe reason` reports a larger
`states_considered`, because a full run also scores every root action and builds the
certificates — so compare CLI output against the figure in *Expected outputs* below, not
against this table.

**Horizon 3 is the exact ceiling.** Beyond it the search reports `NOT_ESTABLISHED/BUDGET` rather
than guessing. The specification asks for horizon 6, so closing that gap is ENIGMA-003's job and on
this evidence it is required rather than an optimisation.

The structural certificates (cut sets, success sets, tied minimal routes, single-outcome resilience)
are **not** subject to that limit and are computed exactly.

The budget counts **state evaluations**, not recursion entries — one recursion step examines a few
hundred candidate successors, and those are what cost the time and fill the memo tables. An earlier
version counted entries and bounded neither; a 20 000-"state" search held over a gigabyte.

---

## Expected outputs — use these to sanity-check your environment

If a fresh checkout disagrees with any of these, something is wrong with the environment or a
regression has landed. All are asserted by `tests/test_policy_mva.py`.

**From `uv run rarepipe reason --horizon 3`** (measured against commit `2a0da07`, ~2 min):

```
map              sha256:2402ca3b568046ca0f65ac42597210df27f5bd8e4daf6f3941c5e79f63204219
target           FUNCTIONAL_CELLULAR_TARGET
conditional      True
robust           {'value': 'NOT_ESTABLISHED', 'reason': 'HORIZON'}
minimal horizon  None
none within      3 campaigns (searched exhaustively)
mode             DISCOVERY
recommended      FLUX01  (1 tied)
states           3694
closes target    EXP01=alignment_defect     + SAFE01=harm
closes target    EXP01=matched_not_achieved + SAFE01=harm
closes target    EXP01=multiple_defects     + SAFE01=harm
closes target    EXP01=segregation_defect   + SAFE01=harm
closes target    EXP01=silencing_defect     + SAFE01=harm
closes target    SAFE01=harm                + SAFE02=harm
```

The map digest is the first thing to check: if it differs, you are solving a different map and
every number below will move. It changed last when `low_dose_taxol` was canonicalised and the
analysis-annotation schema was added.

**Four tied minimal routes** to `FUNCTIONAL_CELLULAR_TARGET`, not one:

```
DEP_ATTACH_TURNOVER + SAFE01      DEP_COHESION  + SAFE01
DEP_CELL_SIZE       + SAFE01      DEP_FLUX      + SAFE01
```

The published route map presents one of these as "the smallest set" and separately recommends the
campaign covering a different one. Both statements were true; the eight-row frontier had been
truncated by an invisible cap of eight sets per node. **Never truncate a semantic result in the
mathematical layer** — a renderer may show fewer and report `display_truncated`, but the maths must
always carry the complete set plus its own `count` and `truncated` flag.

**The symmetric cut-set result**, and the sharpest thing the engine has found:

- 6 minimal cut sets, `SAFE01=harm` in **6/6**
- 7 minimal success sets, `SAFE01=preserved` in **7/7**

`SAFE01` is the pivot in both directions *within size-2 sets*. Keep that scope in the wording: a
member common to every cut set of size two is **not** thereby necessary to every failure of every
size, and `common_cut_members` carries that scope in its own field.

**Action space:** 4 declared campaigns, 33 undeclared resolvers, 12 unavailable. Only **6 of 56**
branches have a declared campaign. An `UNDECLARED_RESOLVER` is not a claim that a runnable
experiment exists — a recommendation resting on one is a recommendation to go and design an
experiment, and it must keep reading that way.

**Benchmark** (`--check` verifies in seconds): 12 sources, **195 episodes, 0 refused**. Arm E:
`robust_reachability_accuracy` 1.000 (196 rows), `route_completeness` 1.000 (196),
`outcome_coverage` 1.000 (60), `safety_error` 0.000 (60), `optimality_regret` 0.000 (132),
`policy_validity` 1.000 (86), 0 malformed. Arm E scoring perfectly is the self-test, not a result.

On the agreement between the engine's maximin pick and the route map's own appendix (both `FLUX01`):
that is **convergent internal validation** — two methods over one formal model — not a benchmark
result. It says the model and the computation are coherent, and nothing about beating a language
model.

---

## Outstanding decisions (with the PM, not blocked on code)

**`discriminated_by` for `LV1`–`LV4`.** The schema and the engine's consumption are live, so Δ's
`hypotheses_eliminated` begins computing the moment those four latent-variable hypotheses declare
which branches would settle them. Their discriminating experiments are currently prose. Note the
deliberate split: `related_branches` records what a hypothesis is *about* (may be `DERIVED`),
`discriminated_by` records what would *settle* it (`DECLARED` only, and the only one Δ consumes).
Conflating them would have Δ report a hypothesis eliminated by experiments that cannot speak to it.
A hypothesis declaring that nothing would promote it may not declare discriminators at all.

**`family_membership`.** Set-valued, with a `DECLARED`/`DERIVED` basis, on a node's `analysis`
block. Nothing populates it: there are no family entry nodes and the only remaining signal is
identifier spelling, which this repository has already been wrong about once. Δ's
`families_resolved` stays `null` until declared — `null` rather than `0` is correct while metadata
is absent, because zero is a measurement and absence is not.

**The CI horizon choice.** The committed `MVA_ROBUST_POLICY.md` is generated at **horizon 2**, which
re-derives in ~20 s so CI can verify it on every push. Horizon 3 gives the stronger claim but takes
minutes. The committed artifact therefore says "2 campaigns or fewer"; the horizon-3 result is
reproduced on demand with `rarepipe reason --horizon 3`. If you move the committed horizon, move the
CI step's `--horizon` with it — checking at a different horizon compares two different questions and
reports spurious staleness.

---

## Pre-existing red CI, unrelated to this work

`uv run pytest -q -m "not integration"` fails **10 tests on a clean checkout**, verified pre-existing
by stashing this work and re-running. Four share one root cause: a subprocess `cwd` hard-coded to
`/Users/venus/Desktop/rarepipe`, which exists on one developer's machine and nowhere else.

```
tests/test_realization_gates.py:322      tests/test_discovery_gates.py:433
tests/test_synthesis_invariants.py:284   tests/test_synthesis_mva.py:194
```

Fix: derive the root from the test file's own location (`Path(__file__).resolve().parents[1]`). These
tests prove a digest is stable across processes with different `PYTHONHASHSEED`, so verify they
*pass* once the path is right rather than only that the `FileNotFoundError` is gone. The other 6
failures are in `tests/test_track2.py` with a different cause (`approval_verified` false, an expected
report file not produced).

Worth landing before any locked competitive benchmark — a comparison should not be run against red
infrastructure. A task card for it was queued separately.

---

## Recommended next work: ENIGMA-003, the symbolic solver

Target horizon 6, with a hard acceptance criterion:

> **`symbolic == exact` on every episode the exhaustive solver certifies as exact.**

The harness already defines that set concretely: the 195 committed episodes across 12 sources, each
carrying `exactness: EXACT`. A symbolic solver is not accepted for running further — it must
reproduce the exhaustive solver everywhere the exhaustive solver can be checked. `solvers/exact.py`
is the reference and should stay deliberately slow and obvious; if it gets faster by getting
cleverer it stops being a check on the clever one.

Then ENIGMA-002B/004: the locked deep A/B/C/D comparison. `arms.from_callable(name, fn)` is the
interface; an arm that raises becomes a malformed response rather than a crash, and malformed is
counted separately from wrong.

---

## One practical note

Every substantive defect found while building this surfaced from **generating an artifact and
reading it**, not from the tests: the truncated tied routes, a renderer iterating a dict's keys
after a field changed shape, two `describe()` payloads colliding on a shared `note` key, a metric
fix that was only half applied, and prose written into a digest field. The 146 tests caught none of
them. For this layer, regenerating the reports and diffing them deserves equal standing with running
the suite.
