# Next steps and open frontiers

Where the work is, organised so someone can pick something up.

The three sections below are kept rigidly apart, because conflating them was a real mistake this
project made and fixed. **"We need more research" is three completely different requests**, and they
need different people, different budgets and different timescales:

| Kind | The limiting resource | Who |
|---|---|---|
| **Data** | A laboratory. More software changes nothing | Bench scientists, core facilities, model platforms |
| **Knowledge** | A named missing component, or access to text we cannot reach | Researchers, data holders, publishers |
| **Engineering** | Developer time | Developers, architects |

Each item below states the question, why it matters, what a contribution looks like, and what
discipline it needs.

---

## The structural finding to read first

Before the item list, the non-obvious result that should shape how anyone prioritises here.

**Nine separate open questions in the route map share one prerequisite: an organism model.**

| What a branch needs | Branches |
|---|---|
| A human cell line and nothing else | **39** |
| **An organism model** | **9** |
| A tissue model | **7** |
| Blocked by governance — no experiment resolves it | **1** |

That changes what "expensive" means. The costly object is **not any single experiment** — it is the
platform that nine of them depend on. A route-by-route reading hides this completely: each of the
nine looks like a separate line item, and they are one.

Two consequences worth acting on:

- **A partner with an existing organism-model platform unlocks nine questions at once.** That is a
  far better conversation than nine separate asks, and it is the highest-leverage single
  relationship available to the project.
- **39 branches need nothing but a human cell line.** That is where progress is cheapest, and it is
  where the three frozen bench questions sit.

And one more property of the map worth knowing before you plan around it: **no branch is unavoidable.**
There is no single chokepoint experiment, so a closed route always leaves an alternative
neighbourhood. That is what building the whole space bought.

---

## 1. Data — where progress now needs a laboratory

**These are not software problems. No amount of further analysis moves any of them.**

Three questions are frozen and bench-ready in
[`docs/control/MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md), with
execution packets for two. They are `NO_CROSS_PREREQUISITE` — runnable in any order or all at once —
which is a scheduling property and **explicitly not** a claim of biological independence. They are
unranked, and **none requires patient material.**

### CHAR01 — is the destabilisation premise even true for this allele?

**The question.** Does this child's exact missense allele destabilise the BubR1 protein at all?

**Why it matters.** The entire abundance-focused strategy family rests on this premise, and the
premise has never been tested for *this* allele. The project holds 103 establishing records at
variant-class level and **zero** at exact-allele level. If the premise is false, a whole family is
mis-framed.

**What a contribution looks like.** A human cell line with established expression of tagged BubR1
constructs. A construct panel including published reference substitutions, a cycloheximide chase,
HSP90 inhibition and proteasome inhibition. Quantitative immunoblot with all arms on one membrane.
Specified in full in
[`CHAR01_EXECUTION_PACKET.md`](../control/CHAR01_EXECUTION_PACKET.md), including the validity gates
your hands must pass first and what each of the four admissible outcomes licenses.

**Discipline.** Cell biology / biochemistry. **The exact substitution stays local** — it is supplied
to a synthesis provider as a sequence through a private channel and appears in no external order.

### FLUX01 — can chromosome fidelity be corrected by other physics?

**The question.** Does physical manipulation of microtubule poleward flux reduce missegregation in a
**BubR1-limiting** human-cell state, while preserving viability, division and cell death?

**Why it matters.** This tests a route that does not repair the broken protein at all. It is the
clearest available test of whether the functional target can be reached by a non-canonical
mechanism — which is the project's central architectural bet.

**The finding that shaped the design.** Across five full texts, **every relevant published experiment
ran at BubR1-present or BubR1-absent, never BubR1-limiting** — and limiting is the case's actual
regime. That is why the packet specifies a *measured gradient* spanning known reference regimes
rather than a single depletion level. It is also a good illustration of why reading experiments beats
reading conclusions.

**What a contribution looks like.** Human cells with titratable depletion (non-transformed preferred,
because the flux work was done there). Three mechanistically independent flux perturbations. Live
imaging for lagging chromosomes, micronuclei in the following interphase. Viability, cell death and
division rate **required, not optional** — with denominators. Full specification in
[`FLUX01_EXECUTION_PACKET.md`](../control/FLUX01_EXECUTION_PACKET.md).

**Discipline.** Mitosis / cell biology, with live-imaging capability.

### BR1 — does the abundance axis touch the phosphatase axis?

**The question.** At experimentally matched BubR1 abundance, does K668 state alter kinetochore
PP2A-B56 recruitment?

**Why it matters.** A positive result would create a mechanism linking two parts of the map that are
currently separate districts. **And the project's own prior leans against it** — the published residue
sits at the relevant interface but outside the three positions that carry binding. It is worth asking
precisely because one experiment can kill it without touching anything else.

**What a contribution looks like.** Acetylation-mimetic and non-acetylatable constructs **with
abundance matched across comparison conditions in the same experiment** — that matching *is* the
design, since the established stability effect would otherwise confound the readout. Primary readout
is kinetochore PP2A-B56 per kinetochore.

**Two strictnesses to respect.** An unmatched comparison licenses **nothing** and is never negative
evidence. And four substitutions are **refused**: changes in alignment, cohesion, checkpoint
silencing or missegregation may not stand in for the recruitment measurement, because those are
exactly the readouts the parent hypothesis predicts will co-move — accepting one would confirm the
bridge from the observations that motivated it.

**Discipline.** Kinetochore biology, quantitative immunofluorescence.

### The two platform asks

**An organism model** — unlocks nine branches at once. See the structural finding above. This is the
single most valuable thing a partner could bring.

**Cytogenetic data for this child** — would connect the case to the disease-level aneuploidy bridge
by **observation** rather than by inference. Outstanding.

---

## 2. Knowledge — where a named component is still missing

These are not "read more papers". Each is a specific missing thing, and the map says which.

### The frontier audit, as it stands today

Of the route map's 72 true leaves:

| Terminal state | Leaves | Meaning |
|---|---|---|
| `BOUNDED_FRONTIER` | 49 | A stated condition bounds it — mostly "repeat under a valid condition" |
| `GOVERNANCE_BLOCKED` | 6 | Not permitted. **No experiment resolves these** |
| `UNSAFE` | 6 | Closed on safety grounds |
| `SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED` | 5 | We searched a named universe and it was empty |
| `PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE` | 3 | Evidence rules it out |
| `ORGANISM_TARGET_REACHED_IN_MODEL` | 1 | Success, in a model |
| `CONTEXT_TRANSFER_REQUIRED` | 1 | Known elsewhere; moving it here is the open step |
| `DECLARED_SCIENTIFIC_FRONTIER` | **1** | **Nobody knows this** |
| `UNEXPANDED_FRONTIER` | **0** | — |

**Zero unexpanded frontiers.** That is the audited result, and it is the one number on this page
worth dwelling on: every leaf has earned its status. An earlier version of the map had thirteen
leaves that looked like frontiers and were simply unexpanded branches — expanding them produced an
entire strategy family nobody had noticed was missing.

### The one genuine scientific frontier

> Clonal dynamics do not explain it and fidelity does dominate, **yet the fraction does not move** —
> a contradiction between two measurements with no identified next experiment.

That is the project's single declared scientific frontier after three separate audits. It is not a
gap in our reading; it is two measurements that should agree and do not, with nobody — us included —
able to name the experiment that resolves it.

**What a contribution looks like:** a mitosis or cancer-biology researcher proposing a measurement
that discriminates. This is a genuinely open question and the most interesting thing on this page.

**Discipline.** Mitosis, aneuploidy, clonal population dynamics.

### Access to text we cannot legitimately reach

**Full text for ten corpus documents** that are currently abstract-and-metadata only — including a
priority study that is not open access. This is the most likely reason a local residue search found
nothing: **a residue appears in figures, tables and methods, and rarely in an abstract.**

The control-layer snapshots store abstracts only by design, which bounds the whole phase: a claim
whose support lives in a figure cannot be grounded there.

**What a contribution looks like.** Legitimate access only — publisher, institutional, author
manuscript, or organizer-provided. **No paywall circumvention.** *"Potentially relevant evidence
exists but is presently inaccessible"* is a valid recorded state and will stay recorded as that.
Ingest, re-run the local residue search, and reopen the exact-variant claim if anything matches.

**Discipline.** Anyone with legitimate institutional access.

### Three knowledge tasks retrieved but never read

Three public knowledge tasks sit at `DETERMINISTICALLY_EXTRACTED`: retrieved and pattern-matched,
**never read by a reasoning process.** The task-state model makes the distinction visible rather than
letting fetching pass as reading.

Topics: truncating alleles; assay outputs that distinguish mutation classes; the downstream defect
most linked to the disease.

**What a contribution looks like.** Three reading sessions, roughly an hour each, following the
import gate — every cited source must already be in the bundle and every quote must be re-found in
the stored document.

**Discipline.** Anyone who can read a genetics paper carefully. **This is the lowest-barrier
scientific contribution available.**

### Outstanding external requests

Two have been asked and not answered: a request to the challenge organizers for a private channel for
the controlled loci, and submitter-level records for the truncating allele from a variant database
whose bundled snapshot and current release disagree about which condition an assertion was made for.

---

### What the project is **not** looking for

Stated plainly, because it is the most likely form of unhelpful help:

**Not more literature review on the closed searches.** Five frontiers are
`SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED` — searched against a named corpus, with the queries and counts
recorded. Another three are `PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE`. Re-searching those is work that
has already been done and whose record exists.

If you believe a closed search was closed wrongly, **the useful contribution is not another search —
it is naming the specific document the search should have found.** That is checkable; a general
impression is not.

**Not more variant interpretation.** The causal variants are known. That stage is finished.

---

## 3. Engineering — platform work that would help

Drawn from [`docs/POTENTIAL_IMPROVEMENTS.md`](../POTENTIAL_IMPROVEMENTS.md), which states what is
true today, what would be better and what it would cost, plus the repository's own deferred items.

**Nothing here changes a scientific conclusion already reached.** This is a backlog, not a plan.

### Worth doing, in rough order of value

**Fix `mechanism fetch-corpus`.** It is broken — a missing module import. `--help` works because the
import is lazy, so the breakage only surfaces on a real run, which makes it worse than an obvious
failure. Today a corpus cannot be acquired from scratch through the CLI. *Small, well-scoped, good
first contribution.*

**Attach sources to the interpretation layer.** The deepest item in the backlog, and the one with the
best argument behind it. Evidence and claims are fully sourced — 1,194 evidence records, every one
with a source id and a quote verified in the stored text. **Interpretation is not:** of 43 prose
statements, 4 have a machine-readable basis and 39 have none.

The concrete example the backlog gives: a claim carries 43 evidence ids, each resolving to a PMID and
a verbatim quote. The limitation sitting beside it — *"a molecular rescue is not a clinical rescue"* —
is true, load-bearing, and **points at nothing.** A reader cannot tell whether it came from a paper,
from the claim statuses, or from an agent reasoning at 2am.

The proposed fix is a `Sourced` wrapper: the same words, plus a `basis` of ids that must resolve
inside the artifact, a `derived_by`, and a `kind` — with `definitional` as an explicit escape hatch
for genuinely editorial sentences, *allowed without a basis but required to declare itself.*

And the reasoning that makes it worth the schema churn: **the point is to make insight cheaper, not
scarcer.** Today a bare assertion feels unsafe to write, so conclusions get under-written. With a
basis field the incentive flips — write the conclusion, name what it rests on, and let the validator
surface the ones resting on nothing, which are exactly the ones worth arguing about.

*Cost: schema change to two artifacts; two stages need a re-run and re-freeze at new schema versions.
Claims, evidence and statuses come out identical; the digests change.*

**Make the control renderer case-generic.** It hard-codes case-specific prose into the generated map
and assumes every constraint has a predicate. **A second case needs the renderer changed, not just
new input data** — so this is the single biggest blocker to a second case, and the most valuable
structural contribution available.

**Generalise the gene-specific rescue classifier**, which hardcodes this gene's symbols to decide
whether a rescue record establishes a point or merely sits near it. Correct here, useless next time.
It wants the case's gene symbols read from the dossier instead.

**Resolve the Stage 10 branch-evaluation gap.** The descriptors advertise five branches for every
experiment kind; the evaluator computes them only on one path. The adverse-event hold fires
everywhere, but **the population-change review does not** — which matters, because population change
is exactly the confounder the safety discipline exists to catch. The reachability checker cannot see
this, because it only checks whether endpoints can supply a branch's inputs.

**Fix the replication experiment's endpoint set.** Two branches cannot fire because the endpoint set
omits the two readouts they need: **the replication experiment cannot test the mechanism it is
replicating.** CI runs this check advisory with a comment saying to make it blocking once resolved —
so fixing it also tightens the gate.

**Fix the vacuous gate check.** One of Stage 09's 15 checks tests a non-optional boolean for `None`,
so it can never fail. Either make it test something or remove it; a check that cannot fail is worse
than no check, because it inflates the count. (While there: the docs say "thirteen" and the code
defines 15.)

**Match Stage 08 against every search spec.** It currently matches every ingredient against only the
first spec, and hardcodes one intervention point. Additional specs are recorded in provenance but
never independently matched.

**Extend the static scan to the other stage packages.** It covers `stages/network` and
`stages/control` only. The remaining stage packages are unscanned.

**Deduplicate noisy extractor output.** 1,194 records from 67 sources via sentence-pattern matching.
Claim statuses use distinct *sources* rather than sentence counts, so the noise does not inflate
confidence — but it does inflate the artifact and makes per-claim evidence lists hard to read.

**Improve bundle carving.** A bundle is carved by matching a task's own queries, so a narrowly-worded
task gets a narrow bundle — one task received 5 documents while the corpus held 64. Honest but blunt.
A second pass offering documents from sibling tasks, with the reason recorded per document, would
help.

**Add a specification for the seventh unmeasured parameter.** The chain has seven unknowns; the
priority report has a specification for six and silently skips the seventh, with no note that one is
missing.

### Known and deliberately left

| | Why |
|---|---|
| Reproducibility from queries rather than from the corpus | The corpus *is* the record. Query-level reproducibility needs a pinned snapshot service — a much larger commitment |
| Additional dense AlphaGenome scorers | Combined responses exceed the API's size cap at the needed granularity; they would need separate per-scorer runs. Worth it only if a specific question needs them, and the questions that earned the adapter are answered |
| Scale work on the search engines | Caps raise rather than degrade, which is the correct failure mode. Not urgent at one case |

### Housekeeping with dates attached

- The repository must be **made public** after the hackathon closes.
- Genomic material must be **deleted within 30 days** of close, with notification. The submission
  period runs to **24 October 2026**.
- An API key pasted into a transcript should be **rotated**. A test already fails the build if
  key-shaped material reaches a tracked file.

---

## How to pick something up

| If you are | Start here |
|---|---|
| A bench scientist | [`MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md), then the execution packet for whichever question fits your hands |
| A researcher with a mechanism idea | The one declared scientific frontier, above. Then [`06-route-map.md`](./06-route-map.md) |
| Someone with institutional journal access | The ten abstract-only documents |
| A careful reader of genetics papers | The three unread knowledge tasks — the lowest-barrier scientific contribution here |
| A developer | [`07-for-developers.md`](./07-for-developers.md), then `mechanism fetch-corpus` as a first fix |
| An architect | The case-generic renderer, and the `Sourced` wrapper proposal |
| A platform or core facility | The organism-model prerequisite — nine branches at once |
| A data holder | [`09-for-data-collaborators.md`](./09-for-data-collaborators.md) |

Two things to carry into any of it:

**Write the test first, then break it.** A gate that passes on its first run proves nothing. See
[`07-for-developers.md`](./07-for-developers.md) §5.

**If the answer gets weaker, that may be the correct result.** The project's own evidence repair made
its conclusion weaker, and that was the point. Do not optimise for a stronger answer.

---

## Where to go next

- **What exists today** — [`12-current-state.md`](./12-current-state.md).
- **The full backlog with costs** — [`docs/POTENTIAL_IMPROVEMENTS.md`](../POTENTIAL_IMPROVEMENTS.md).
- **The whole reachable space** — [`06-route-map.md`](./06-route-map.md) and the generated
  [`MVA_CONTINGENT_ROUTE_MAP.md`](../control/MVA_CONTINGENT_ROUTE_MAP.md).
- **The rules any contribution has to respect** —
  [`05-evidence-discipline.md`](./05-evidence-discipline.md) and
  [`11-governance-and-safety.md`](./11-governance-and-safety.md).
- **Terms defined** — [`14-glossary.md`](./14-glossary.md).

---

> Nine branches share one prerequisite. The expensive object is the platform, not the experiment. If
> you think a closed search was closed wrongly, name the document it should have found.
