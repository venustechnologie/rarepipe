# Current state

The honest status page. What exists, what is partial, what is deliberately not built, and what the
project currently says about the case.

Everything here was measured against this checkout rather than recalled. Where a number could not be
verified offline, it says so instead of guessing. **The value of this page is that you can trust
it** — so if you find something stale, that is a defect worth fixing rather than a rounding error.

---

## 1. The project in numbers

| | |
|---|---|
| Package | `rarepipe` 0.1.0, Python ≥ 3.12 |
| Source | **221 Python files, ~49,600 lines** across 13 stage subsystems plus `core/` |
| Tests | **1024 passed, 8 skipped** — 1032 collected, across 54 `test_*.py` files (61 Python files in `tests/` including fixtures and helpers) |
| Suite runtime | ~4 minutes |
| CI | **14 steps**, including 6 generated-document staleness checks. Entirely offline, no case data |
| Static scans | 2, over `stages/network` and `stages/control` |
| Tracked documentation | 56 Markdown files under `docs/` |
| Commits | 128 |
| JSON Schemas | 11 artifact contracts, committed and drift-tested |

The 8 skipped tests need things a clean checkout does not have: the Exomiser distribution and its
data bundles, and the external challenge's own evaluator script.

One correction to a plausible assumption: **no test currently carries the `integration` marker**, so
CI's `-m "not integration"` filter is a no-op today. Plain `pytest` collects the same 1032. The
marker is kept because it is the right place for anything needing the controlled drive.

### Relative size, which is not where a newcomer expects

| Subsystem | Files | Lines | Position |
|---|---|---|---|
| `network` | 24 | 12,660 | Stage-adjacent — outreach and coordination |
| `control` | 70 | 11,575 | The control compiler and all its layers |
| `mechanism` | 15 | 4,011 | Stage 06 |
| `intake` | 13 | 3,176 | Stage 01 |
| `prospective` | 15 | 3,133 | Stage 10 |
| `simulate` | 9 | 2,592 | Causal chain and propagation |
| `normalize` | 11 | 1,919 | Stage 02 |
| `adjudicate` | 8 | 1,745 | Stage 04 |
| `track2` | 6 | 1,429 | Stage 09 |
| `baseline` | 9 | 1,413 | Stage 03 |
| `discovery` | 7 | 1,220 | Stage 08 |
| `intervention` | 4 | 1,097 | Stage 07 |
| `track1` | 8 | 1,007 | Stage 05 |

**The two largest subsystems are not pipeline stages.** `control` is the reasoning engine and
`network` is the coordination layer — together nearly half the codebase. The linear pipeline that
the stage numbering implies is the smaller part of the system.

---

## 2. Stage coverage

Git tags record which stages were frozen at a version. Absence of a tag is not absence of
implementation — it means that stage was never cut as a release.

| Stage | Subsystem | Status | Tag |
|---|---|---|---|
| 01 Case intake | `intake` | **Frozen** — schema frozen against the tag | `stage01-case_intake-v0.1.0` |
| 02 Normalization | `normalize` | **Built**, schema v1.1.0, drift-tested | — |
| 03 Baseline candidates | `baseline` | **Built**; needs the external solver to run for real | — |
| 04 Evidence adjudication | `adjudicate` | **Frozen** | `stage04-evidence_adjudication-v0.1.0` |
| 05 Track 1 submission | `track1` | **Frozen** | `stage05-track1_export-v0.1.0` |
| 06 Mechanism resolution | `mechanism` | **Frozen at v0.2.0**; one CLI command broken (below) | `stage06-mechanism-v0.1.0`, `v0.2.0` |
| 07 Intervention logic | `intervention` | **Frozen** | `stage07-intervention-v0.1.0` |
| 08 Approved-intervention discovery | `discovery` | **Built**; not reproducible from a public clone | — |
| 09 Track 2 adjudication | `track2` | **Frozen at v0.1.2** | `stage09-track2-v0.1.0`, `v0.1.1`, `v0.1.2` |
| 10 Prospective plans | `prospective` | **Built**; the one real plan is a `DRAFT` and cannot freeze (below) | — |

Two naming traps that cost newcomers time:

**Stage numbers do not match directory names.** `stages/track1/` is Stage 05, `stages/intervention/`
is Stage 07, `stages/discovery/` is Stage 08, `stages/track2/` is Stage 09. "Track 1" and "Track 2"
are the external challenge's track names, not pipeline positions.

**`stages/discovery/` and `stages/control/discovery/` are completely different subsystems.** The
first is approved-intervention discovery (Stage 08); the second is capability-gap discovery for the
control compiler. `tests/test_discovery_gates.py` tests the **second** one.

---

## 3. The control compiler and its layers

All five layers are built, and each produces a generated, staleness-checked report.

| Layer | Status | Committed headline for the live case |
|---|---|---|
| Control core | Built | A control map with one of seven explicit result classes |
| Synthesis | Built | **`SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`** |
| Physical realization | Built | Per-function verdicts; the abundance route is `EVIDENCE_INSUFFICIENT` |
| Capability-gap discovery | Built | **Zero grounded capabilities** |
| Evidence repair | Built | 4 repairs; **10 of 11 dependent layers moved** |
| Contingent route map | Built and valid | 240 nodes, 154 edges, 56 branches, no unavoidable branch |

`SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN` is a **successful** output, and it is the one most likely to be
misread. It means: the route works under every evidence-compatible model, and what is missing is a
way to build it — named per component. A reader expecting a ranked list of interventions will find
the opposite, and that is the designed result.

**Zero grounded capabilities** is likewise a real result, not a gap in the run. The external search
ran against a named corpus and nothing survived validation. The report's headline metric is
deliberately *previously-open interfaces whose epistemic state changed*, not papers found.

---

## 4. Where the case science stands

The full statement is [`docs/control/MVA_CASE_DECISION.md`](../control/MVA_CASE_DECISION.md). In
brief:

**Known.** The child's missense allele sits in the **protein kinase domain** — from the case's own
protein-feature evidence. (The domain name is public biology; the residue appears in no published
document from this project.) For that region, function at restored abundance is demonstrated **for
one endpoint** — two kinase-domain substitutions forced to wild-type-comparable levels fully restored
the nocodazole response. The mechanism of low abundance is **protein turnover, not transcription**.
The kinase domain is **dispensable** for both mitotic functions, so a kinase-domain substitution
matters because it destabilises the protein rather than because it removes catalysis.

**Not known, and this is the whole case.** Only **one of four** functional endpoints was measured at
restored abundance; checkpoint silencing, chromosome segregation and chromosome alignment were not.
And **no experiment anywhere has expressed this child's exact substitution at matched abundance.**

| Claim | Status | Establishing records |
|---|---|---|
| Variant-class (kinase-domain missense) | `PARTIALLY_SUPPORTED` | **103** |
| Exact-variant (this child's substitution) | `UNRESOLVED` | **0** |

**The decision, recorded at two levels at once:**

| Level | Verdict |
|---|---|
| Variant class, kinase domain | `function_persists` |
| This child's allele | `insufficient` |
| **Decision** | **`INSUFFICIENT`** |

`ABUNDANCE_LIMITED_MECHANISM_SUPPORTED` at class level and `CASE_REMAINS_UNRESOLVED` for this allele
— both at once, and they must not be merged.

**The result that makes the decision trustworthy:** knowing the domain moved the class-level reading
a long way and moved the decision **not at all**. That was verified *before* the real annotation
arrived by probing all three domains; the decision came back `INSUFFICIENT` in every one. The
invariance is the result.

No probability is attached to any of this, and none should be.

### The three bench-ready questions

Frozen in [`docs/control/MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md):

| | Question |
|---|---|
| **CHAR01** | Does this child's exact missense allele destabilise the protein at all? |
| **FLUX01** | Does manipulating microtubule poleward flux reduce missegregation in a BubR1-limiting human-cell state, while preserving viability, division and cell death? |
| **BR1** | At matched BubR1 abundance, does K668 state alter kinetochore PP2A-B56 recruitment? |

`NO_CROSS_PREREQUISITE` — each can be run and read without the others' outcomes. **That is a
scheduling property, explicitly not biological independence.** They are unranked, and none is
conditional on another. **None requires patient material.**

**None has been run.** There is no wet-lab result anywhere in this project.

### A unifying finding worth recording

Across five full texts: **every relevant published experiment ran at BubR1-present or BubR1-absent,
never BubR1-limiting** — which is the case's actual regime. That is why FLUX01 specifies a measured
gradient rather than a single depletion level, and it is the kind of finding that only appears when
you read the experiments rather than the conclusions.

### What the external validation layer does and does not show

The Stage 05 machinery is built and frozen: a hashed snapshot of the pipeline's prior state is sealed
*before* the evaluator is queried, so feedback is auditable rather than retroactively absorbable as
tuning. The branch table maps the evaluator's verdict to the next investigative question — a full
match ends causal-variant discovery and moves the case to mechanism; a partial or absent match opens
different questions.

**The case's own validation artifacts are controlled and are not in this repository.** This page
therefore describes the mechanism and does not assert the outcome. Read the controlled run
artifacts for that.

---

## 5. What is built, what is partial, what is deferred

### Built and working

| | |
|---|---|
| The ten pipeline stages | Each with immutable sealed run directories, paired private/sanitized artifacts, reports and logs |
| The control compiler, all five layers | With generated reports and staleness checks |
| The contingent route map | 240 nodes, validated against seven closed vocabularies |
| The evidence-repair and recompile machinery | Exercised for real, with the delta published |
| The disclosure boundary | Nine refused pattern classes, fails closed, with the provenance exception |
| Schema-driven redaction | 11 committed schemas, drift-tested |
| The CLI | 30 commands plus a 12-command `prospective` sub-app |
| CI | 14 steps, fully offline |
| Reproducible packaging | Self-verifying zips that are unpacked and checksum-verified before being returned |

### Partial, with the specific limitation

| | The limitation |
|---|---|
| **`mechanism fetch-corpus`** | **Broken** — a missing module import. `--help` works because the import is lazy, so the breakage only surfaces on a real run. `refresh-corpus` and `resolve` work from an existing frozen corpus, so a corpus cannot currently be acquired from scratch through the CLI |
| **Stage 10's one real plan** | A `DRAFT`. It cannot freeze while scientific-readiness gaps remain, and the seed deliberately leaves every assay method, threshold, analysis field and model availability null **so they surface as owned gaps** rather than as invisible assumptions |
| **Stage 10 branch evaluation** | The descriptors advertise five branches for every experiment kind, but the evaluator computes them only on the non-allele-function path. The adverse-event hold does fire everywhere; the population-change review does not |
| **Branch reachability** | Two branches cannot fire because the replication experiment's endpoint set omits the two readouts it would need — **the replication experiment cannot test the mechanism it is replicating.** CI runs this check advisory (`\|\| true`) with a comment saying to make it blocking once resolved |
| **Stage 08 search specs** | Every ingredient is matched against only the **first** spec; additional specs are recorded in provenance but not independently matched |
| **Stage 09 gate** | 15 checks, and **one is vacuous as written** — it tests a non-optional boolean for `None`, which can never fail. The docs say "thirteen"; the code defines 15 |
| **The control renderer** | **Not case-generic.** It hard-codes case-specific prose into the generated map. A second case needs the renderer changed, not just new input data |
| **One rescue classifier** | Hardcodes this gene's symbols. Correct here, useless for the next case |
| **Static scan coverage** | Covers `stages/network` and `stages/control` only. Other stage packages are **not** scanned |
| **Corpus snapshots (control layers)** | Abstracts and metadata only, never full text. A claim whose support lives in a figure or methods section cannot be grounded there. 10 of 64 corpus documents are abstract-only, including a priority study that is not open access |
| **Three knowledge tasks** | `DETERMINISTICALLY_EXTRACTED` — retrieved and pattern-matched, **never read by a reasoning process.** The task-state model makes this visible rather than letting it pass as done |
| **Sensitivity ranking** | Rank order does **not** survive a doubling of the sample size for this chain, so **no rank is reported.** A priority order that moves with sample size reads as a finding and is not one |
| **One unmeasured parameter** | The chain has seven unknowns; the priority report has a specification for six and silently skips the seventh |

### Not reproducible from a public clone

`research/` is gitignored — full texts, verbatim quotes, imported sessions. **Stage 08 and Stage 09
runs cannot be reproduced from this checkout alone.** Likewise no case run can be replayed, because
every private artifact and every genomic file extension is excluded.

### Deliberately not built

Each of these is an explicit decision, not a backlog item.

| Not built | Why |
|---|---|
| Any therapy, dose, regimen or recommendation output | A recommendation is **unrepresentable** — the field is typed `Literal[False]` |
| Exact-variant external querying | The authorising function **has no success path** |
| External sending | Dispatch returns a stored unsent draft. Nothing has ever been sent |
| Any probability, efficacy score or model confidence in the reasoning layers | None would be grounded |
| Expected information gain for experiment selection | It would require inventing a probability. The criterion is `deterministic_elimination` |
| A weighted safety/benefit objective | Explicitly refused — none of the weights is grounded, and safety is lexicographically first |
| A provider that asks a model what it remembers about the literature | **A model's recollection is not a source** |
| An LLM anywhere in the mechanism path | A test asserts the module does not exist and that five named modules contain no API endpoint, key name or client call. The artifact records `pipeline_depends_on_an_llm: false` |
| Interval-valued state variables, ODE and stochastic formalisms | Named in the registry and refused by the engine. Interval variables **raise at construction** rather than being silently discretised |
| Automatic deletion of controlled material | Retention classes are recorded; a human must act |
| Multi-case infrastructure, tenancy, or a UI beyond the CLI and static HTML views | Out of scope at one case |

---

## 6. Known scale limits

Stated because they are real and cheap to hit, not because they are urgent.

| Limit | Where |
|---|---|
| Strategy search is **exponential in the control set** — every non-empty subset of remaining controls at every depth, re-run per variant | Control core. Caps raise rather than degrade: `max_depth ≤ 6`, 64 candidates per unknown, 2¹⁸ states |
| Composition search raises past **25,000** compositions | Synthesis. It raises rather than truncating, because a silently truncated search reports "no architecture found" in the same words as an exhaustive one |
| The causal chain re-walks the graph per draw | Fine at 14 nodes and 16 edges; will not scale unchanged |
| Only 7 of 16 chain edges carry a parameter | The other 9 propagate as a bare sign, so the magnitude is a product over a sparse subset — **not a kinetic model** |
| `recompile.observe()` runs five full compilations with nothing cached | ~30 seconds. Deliberate — a cached value would make the exercise meaningless |
| Route-map Pareto frontier capped at 8 sets per node | Bounds the cross-product at `all_of` nodes |

---

## 7. Known staleness in the repository's own documents

The project tracks this rather than tidying it away, and the direction of each drift is recorded.

| Stale thing | Reality |
|---|---|
| Three control design documents | Partly stale relative to the evidence repair. One says a route is `CONTRADICTED`; it is now `EVIDENCE_INSUFFICIENT` — unsupported rather than refuted, **a weaker and different claim.** Trust the generated reports and the code |
| `docs/track2.md` and a gate docstring | Both say "thirteen" checks; the code defines **15** |
| A simulator contract document | Lists six unmeasured parameters; the chain has **seven** |
| A validation module docstring | Says two references keep an unverified marker; the live run reports **zero** |
| Hard-coded counts in several docstrings | A provider advertises "five citations across fifteen claims"; the inventory now returns **16 edges, 13 cited, across 5 references.** The computed corpus size is correct — only the prose is wrong |
| Concrete figures in one module's docstring | Claims about **past runs**, not values computed at call time |
| A skill document's gap count | Dated. Read `prospective validate --json` as the live source |
| The repository README | Documents **stages 01–03 only** |

The pattern is consistent and worth internalising: **generated documents and code are the source of
truth; hand-written design prose and docstring counts drift.** That is why six CI steps guard the
generated documents and nothing guards the prose.

---

## 8. What the project does not claim

- **No wet-lab validation of anything.** The output is experiments; none has been run.
- **No clinical validation, no diagnostic performance, no patient outcome.** Absent and out of scope.
- **No therapy, compound, dose or treatment recommendation**, anywhere, by construction.
- **No probabilities.** Not withheld — not computed.
- **No preregistration claim** without independent timestamp evidence. A hash proves which bytes you
  have, not when you saw a result, so a freeze without timestamp evidence is marked
  `TEMPORAL_STATUS_UNVERIFIED`.
- **No capability discovered** by the external search. Zero.
- **No institutional reply exists.** Nothing has been sent, and the learning component trains against
  a **synthetic** world.
- **No robust reachability.** Reported as `NOT_ESTABLISHED`, and never inferred from
  single-outcome resilience.
- **Biological independence of the three bench questions** is not claimed. Only that no result is a
  prerequisite for running or reading another.
- **n = 1.** One case, worked deeply, with the engine built generically and the case data separated
  from it.

---

## Where to go next

- **Where the open work is, sorted by discipline** — [`13-next-steps.md`](./13-next-steps.md).
- **The backlog with costs attached** —
  [`docs/POTENTIAL_IMPROVEMENTS.md`](../POTENTIAL_IMPROVEMENTS.md). It states what is true today,
  what would be better, and what it would cost, so a future reader can decide rather than
  rediscover.
- **The case science in full** —
  [`docs/control/MVA_CASE_DECISION.md`](../control/MVA_CASE_DECISION.md) and
  [`MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md).
- **The self-audit** —
  [`MVA_EVIDENCE_REPAIR_DELTA.md`](../control/MVA_EVIDENCE_REPAIR_DELTA.md) and
  [`MVA_FULL_RECOMPILE_DELTA.md`](../control/MVA_FULL_RECOMPILE_DELTA.md).
- **The whole reachable space** — [`06-route-map.md`](./06-route-map.md).
- **What may never be claimed externally** —
  [`10-for-commercial-and-strategy.md`](./10-for-commercial-and-strategy.md) §6.

---

> The decision for this case is `INSUFFICIENT`. That is the correct answer, and the system reaching
> it rather than overclaiming is the result.
