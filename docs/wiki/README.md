# The rarepipe wiki

**Start here.** This wiki is written so that anyone — of any discipline — can understand what this
project is for, what it can do, and where the work is, and then contribute to it.

It is deliberately multi-audience. A clinician, a developer, a strategist and a biobank each need
different pages, and each of those pages is written for that reader rather than being a technical
document with a summary bolted on.

---

## Read this first, whoever you are

[**01 — What this is**](./01-what-this-is.md) · *~15 min*

The problem, what rarepipe does differently, what it produces, and the project's governing line —
*"Reason with agents. Prove with code."*

If you only read one page, read that one. If you read two, read
[**12 — Current state**](./12-current-state.md) second, because it is the honest status page and it
will stop you overclaiming.

---

## Then, by what you came here for

### If you are a clinician, geneticist or bench scientist

| | |
|---|---|
| [**08 — For clinicians and researchers**](./08-for-clinicians-and-researchers.md) | The science with the software skipped: how a claim earns its status, why class-level and exact-allele evidence are not interchangeable, and the three questions frozen for a bench |
| [**14 — Glossary**](./14-glossary.md) | Every project-specific term defined, marked separately from standard biology |
| [**05 — Evidence discipline**](./05-evidence-discipline.md) | Why you can trust the evidence base — including the self-audit that made the project's own answer *weaker* |

### If you are a developer or architect

| | |
|---|---|
| [**02 — Architecture overview**](./02-architecture.md) | The system in one picture, then in layers, then as a repository you can navigate |
| [**07 — For developers**](./07-for-developers.md) | Setup, the test suite, the CI gate, the conventions that are actually enforced, and your first contribution |
| [**03 — The pipeline, stage by stage**](./03-the-pipeline.md) | What runs in what order: per stage, what it consumes, what it produces, and the invariant that matters most |
| [**architecture/module-reference.md**](./architecture/module-reference.md) | The detailed per-subsystem reference. The **Gotchas** sections are the most valuable part |

### If you want the reasoning engine

| | |
|---|---|
| [**04 — The control compiler**](./04-control-compiler.md) | The conceptual heart: the inverse formulation, and why *mathematically synthesizable* and *physically buildable* are kept rigidly apart |
| [**06 — The contingent route map**](./06-route-map.md) | Every state the case can be in, every experiment between them, every admissible outcome, and where reasoning runs out |

### If you are in sales, marketing, strategy or leadership

| | |
|---|---|
| [**10 — For commercial and strategy**](./10-for-commercial-and-strategy.md) | The category, the real differentiators, the honest limitations, **what must never be claimed**, and language you can safely reuse |
| [**12 — Current state**](./12-current-state.md) | Read this before any external conversation |

### If you hold data, or might share it

| | |
|---|---|
| [**09 — For data holders and collaborators**](./09-for-data-collaborators.md) | What happens to your data, drawn from the code rather than from intention — with a table separating what is **enforced** from what is only **asserted** |
| [**11 — Governance and safety**](./11-governance-and-safety.md) | Every rule, where each is enforced, and which are tested versus policy |

### If you want to help

| | |
|---|---|
| [**13 — Next steps and open frontiers**](./13-next-steps.md) | Three kinds of work kept rigidly apart — **data** needs a laboratory, **knowledge** needs a named missing component, **engineering** needs developer time |

---

## All pages

| Page | Audience | What it covers |
|---|---|---|
| [01 — What this is](./01-what-this-is.md) | Everyone | The problem, the approach, what it produces |
| [02 — Architecture overview](./02-architecture.md) | Developers, architects | Layers, rules, repository layout |
| [03 — The pipeline, stage by stage](./03-the-pipeline.md) | Developers, researchers | Ten stages, artifacts, invariants, CLI |
| [04 — The control compiler](./04-control-compiler.md) | Architects, scientific stakeholders | The inverse problem and its five layers |
| [05 — Evidence discipline](./05-evidence-discipline.md) | Researchers, clinicians, developers | The epistemic ladder, grounding, the backward audit |
| [06 — The contingent route map](./06-route-map.md) | Strategists, scientific stakeholders | The city: states, experiments, outcomes, frontiers |
| [07 — For developers](./07-for-developers.md) | A developer joining tomorrow | Setup, tests, CI, conventions, mutation testing |
| [08 — For clinicians and researchers](./08-for-clinicians-and-researchers.md) | Doctors, geneticists, bench scientists | The case science and the three bench questions |
| [09 — For data holders and collaborators](./09-for-data-collaborators.md) | Biobanks, registries, families, labs | What happens to your data |
| [10 — For commercial and strategy](./10-for-commercial-and-strategy.md) | Sales, marketing, strategy, leadership | Category, differentiators, limits, safe language |
| [11 — Governance and safety](./11-governance-and-safety.md) | Everyone; reviewers and ethics boards | Every rule and where it is enforced |
| [12 — Current state](./12-current-state.md) | Everyone | The honest status page |
| [13 — Next steps and open frontiers](./13-next-steps.md) | Contributors of any discipline | Where the work is, by discipline |
| [14 — Glossary](./14-glossary.md) | Everyone, especially cross-discipline | Every term defined |
| [architecture/module-reference.md](./architecture/module-reference.md) | Developers, architects | Per-subsystem detail reference |

---

## Five ideas that explain most of the design

If you internalise these, the rest of the project reads as obvious rather than idiosyncratic.

**1. Reason with agents. Prove with code.**
A language model may propose a state, a mechanism, a route or an experiment. **Only deterministic
code decides** reachability, safety, robustness, feasibility or a result class. **The gate assigns
the epistemic type, never the proposer.**

**2. Retrieval is not grounding.**
Finding a source and a source supporting your claim are different questions, tracked in different
fields with different verdicts. Every quote is re-found **verbatim** in the stored source before a
statement is accepted.

**3. A bounded negative is a statement about the corpus, never about biology.**
"We searched this named corpus and found nothing" is a complete, reportable result — and it is **not**
"it cannot be done". The system keeps those as separate terminal states, and the strong one has to
earn it.

**4. Logical synthesizability never implies physical feasibility.**
A composition that reaches the target in the mathematics is a legitimate output. *"We cannot build
this yet, and here is exactly what is missing"* is a **successful** answer, not a failure.

**5. Unknowns are branch points, not dead ends.**
Every unknown enumerates its admissible outcomes and continues from each. A leaf must say **why** it
is a leaf, from a closed vocabulary — never *"we stopped reasoning."*

And the sixth, which is not a design principle but is the most credible thing in the repository:

**The project audited its own evidence base, found two load-bearing citations that did not support
the claims built on them, corrected them, recompiled every dependent conclusion — and the answer got
weaker.** It stopped knowing something it never had grounds for, and published the delta. See
[05 — Evidence discipline](./05-evidence-discipline.md) §5.

---

## How to keep this wiki honest

The same discipline the project applies to its science applies here.

- **Every factual claim should name the file that supports it.** If you cannot point at the code, do
  not write the sentence.
- **Numbers go stale.** Where a count appears, prefer the command that produces it. The pages state
  when a figure was measured.
- **Say what is asserted versus what is enforced.** A governance document that presents aspirations
  and mechanisms in the same voice teaches the reader to trust the wrong things.
- **Generated documents under `docs/control/` are build outputs**, never prose. Six CI steps fail if a
  committed one drifts from its compiler. Do not quote one as though someone wrote it — and do not
  edit one.
- **If you find something stale here, that is a defect worth fixing**, not a rounding error.

---

## Beyond the wiki

| | |
|---|---|
| [`README.md`](../../README.md) | The repository readme. Note it documents stages 01–03 only |
| `docs/*.md` | Per-stage operator guides: [intake](../intake.md), [normalize](../normalize.md), [baseline](../baseline.md), [mechanism](../mechanism.md), [track1](../track1.md), [intervention](../intervention.md), [discovery](../discovery.md), [track2](../track2.md), [prospective](../prospective.md) |
| `docs/control/` | The control compiler's design documents **and its generated maps**. The generated maps are the source of truth; three of the design documents are partly stale relative to the evidence repair |
| `docs/network/` | The outreach subsystem's PRD and runbook. The other files there are successive drafts kept as history |
| [`docs/POTENTIAL_IMPROVEMENTS.md`](../POTENTIAL_IMPROVEMENTS.md) | What is known to be imperfect, with costs attached |
| `docs/adr/` | Architecture decision records |

---

> This project produces evidence states and experiments. It does not produce therapies, and no
> statement anywhere in it is clinical advice.
