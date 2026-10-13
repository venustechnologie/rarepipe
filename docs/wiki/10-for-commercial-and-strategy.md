# For commercial and strategy

This page is for sales, marketing, partnerships, strategy and non-technical leadership. It says what
rarepipe is in business terms, what genuinely differentiates it, who would plausibly use it, and —
at equal length, deliberately — what it cannot do and what must never be claimed about it.

The reason the limitations section is as long as the differentiators section is that this audience
gets asked hard questions by people who are qualified to ask them. A claim you cannot defend in a
room with a clinical geneticist costs more than the deal it wins.

**Rule of thumb for everything below: if you cannot point at the file that does it, do not say it.**
Every claim on this page names one.

---

## 1. The category

### What it is

**A decision-and-evidence system for cases where the genetics are solved and nothing follows from
that.**

Its output is a statement of which biological world you are in given what you observe next, plus the
specific experiment that would tell you — with the interpretation of every possible result fixed
before the result exists.

The useful one-liner: *most tools tell you what a variant probably is. This one tells you what you
would have to measure next, and what each answer would and would not license.*

### What it is not

Be precise about this, because every one of these is a category someone will try to put us in, and
each comes with expectations we would fail:

| Not this | Why the distinction matters |
|---|---|
| A variant-interpretation or diagnostic tool | It **starts** after the causal variant is known. It does not classify variants and has no diagnostic performance. |
| A drug-discovery or repurposing screen | It produces no therapy, no compound recommendation and no dose. The code cannot represent a treatment recommendation — the field is typed `Literal[False]`. |
| A target-identification platform | It produces *control variables and required functions*, which are upstream of a target and deliberately modality-agnostic. |
| An AI/LLM analysis product | Language models propose. They never decide. A test asserts that no module in the mechanism path calls a model, and the artifact records `pipeline_depends_on_an_llm: false`. |
| A clinical decision-support system | Nothing in it is clinical advice, and every decision record carries that sentence unconditionally. |
| A literature-mining tool | Retrieval is one bounded step inside it, and the system is explicit that **retrieval is not grounding.** |

### The honest framing of maturity

One live case, worked deeply, with the engine built generically and the case data separated from it.
Not a product; a working system with a demonstrable method and one real result. Saying so is more
persuasive to a serious counterparty than implying a platform with ten customers.

---

## 2. What actually differentiates it

Five things. Each is real, each is checkable, and each names its file.

### 1. Deterministic gates instead of model confidence

Agents may propose. Only code decides. The gate assigns the epistemic type of every statement —
never the thing that proposed it
([`stages/control/proposals.py`](../../src/rarepipe/stages/control/proposals.py)). An
agent-proposed relationship enters as a hypothesis at most; agent-claimed feasibility is stripped;
no proposal may carry a result class at all.

There are **no confidence numbers anywhere** in the physical reasoning layers. No probability of
success, no efficacy score, no model-generated confidence. Verdicts come from closed vocabularies.
That is a design decision: a number nobody can ground is worse than a word everybody can check.

**The commercial point:** every output is attributable to a rule, which means it is auditable,
reproducible and defensible in review. "The model was confident" is not a defence. "This gate, in
this file, returned this verdict from this evidence" is.

### 2. Grounding separated from retrieval

Finding a source and a source supporting your claim are tracked as different questions with
different verdicts. Three levels — the paper exists and says this; it really is about this entity,
input, output and direction; and it transfers to the system you care about — are **never merged**,
and only the third licenses a grounded verdict.

Every quote is re-found verbatim in the stored source before a statement is accepted. A paraphrase
fails.

**The commercial point:** this is the failure mode that destroys credibility in evidence-driven work
— a confident chain of reasoning resting on a citation that does not say what it was taken to say.
It is also the one a buyer cannot audit for themselves. Here it is structurally prevented and the
prevention is visible.

### 3. Reproducible frozen corpora

Retrieval is a deliberate, separately-run, networked step that writes a versioned snapshot.
Compilation reads **only** the snapshot. Consequences: verdicts are reproducible months later,
continuous integration needs no network, and every query that was ever sent is in the log.

A test asserts the compiler never touches the network. Another asserts no committed query was
case-specific.

**The commercial point:** "we can regenerate this exact conclusion from this exact evidence" is a
sentence very few systems in this space can say. It matters for regulated counterparties,
publication, and any partner who will eventually ask how a conclusion was reached.

### 4. A contingent map instead of a single recommendation

The system does not output a plan. It outputs the space: every biological state the case could be
in, every experiment that moves between them, every admissible outcome, and every place where
reasoning genuinely runs out — as one validated graph with no probabilities in it.

For the live case: **240 nodes, 154 edges, 56 open questions, 202 enumerated outcomes.** Branches
are sorted by what kind of work would answer them — 39 need nothing but a human cell line, 9 need an
organism model, 7 a tissue model, 1 is blocked by governance and no experiment resolves it.

**The commercial point — and this is the most under-sold capability:** it prices ignorance in a
budgetable unit. "39 open questions need only a human cell line; nine share one platform
prerequisite" is a procurement conversation. "We need more research" is not. And the structure
surfaces findings a route-by-route analysis hides — the expensive object here is not any single
experiment, it is the organism-model platform that nine separate questions depend on.

### 5. Governance enforced in code, not in policy

The case-identity boundary is nine refused pattern classes in a guard that fails closed. Exact-variant
external querying is not configurable-off; **the function that would authorise it has no success
path.** Redaction is schema-driven, so adding a sensitive field means tagging it rather than
remembering a list. Reports assert they were handed the redacted artifact before writing a line.

**The commercial point:** with a data holder, "we have a policy" and "the code cannot do it" are
different conversations. This is the second one. See
[`09-for-data-collaborators.md`](./09-for-data-collaborators.md), which is written for exactly that
audience and includes a table separating what is *enforced* from what is only *asserted*.

### The sixth thing, which is harder to sell and more convincing

The system audited its own evidence base, found two load-bearing citations that did not support the
claims built on them, corrected them, recompiled every dependent layer — and **the answer got
weaker.** The project stopped knowing something it never had grounds for, and it published the
delta.

That is not a feature anyone asks for. It is the single most credible thing in the repository, and
with a sophisticated counterparty it is worth more than any capability claim. Lead with it when the
room is technical.

---

## 3. Who would plausibly use this

Stated as hypotheses, because none is a signed relationship.

| Who | What they would get |
|---|---|
| **Rare-disease foundations and patient organisations** | A structured statement of what is actually unknown for a specific case, and which experiment would resolve it — rather than a list of papers |
| **Academic labs working on a specific mechanism** | Bench-ready questions with precommitted interpretation matrices, validity gates and the published results their hands must reproduce first |
| **Biobanks, registries and consortia** | A collaborator whose data handling is verifiable in code, which asks cohort-level questions that never require patient identity |
| **Clinical genetics groups** | The layer that begins where variant interpretation ends |
| **Translational research organisations** | A reusable method for turning "mechanism known, nothing actionable" into a costed experimental programme |
| **Core facilities and model-organism platforms** | Nine open questions in the live case share one organism-model prerequisite |

Who this is **not** for, today: anyone needing a diagnostic, a therapeutic, a regulatory submission,
or throughput across many cases.

---

## 4. What a demonstration looks like today

### What you can show right now

- **The route map** — the full space for a real case, generated, with every open question classified
  by the work that would answer it.
- **The bench matrix** — three questions frozen for a laboratory, each with its system, manipulation,
  validity gates, primary readout, and a table of what every admissible outcome licenses and does not
  license.
- **The evidence repair delta** — the self-audit described above, with every layer recomputed and a
  stated reason even for the one that did not move.
- **The case decision** — including the result that the conclusion was *unchanged* by learning which
  protein domain the allele sits in, verified by probing all three domains before the real annotation
  arrived.
- **The gates failing** — a query carrying case identity being refused; a generated document failing
  CI because it was edited by hand. Showing a system refuse something is a better demo than showing
  it produce something.
- **The suite and the gate** — 1032 tests, two static source scans, six staleness checks, all
  offline with no case data.

### What would need building for a second case

Say this plainly, because it is the first question a serious partner asks.

| Gap | What it is |
|---|---|
| **The renderer is case-specific** | `render.py` in the control layer hard-codes case-specific prose into the generated control map. A second case needs the renderer generalised, not just new input data. |
| **Case data is hand-authored** | The control problem and the route map are written by hand under validation, not derived automatically. Building a second city is expert work measured in weeks. |
| **One gene-specific classifier** | A rescue-evidence classifier hardcodes this gene's symbols. Correct here, useless next time. |
| **Scale limits are real** | Strategy search is exponential in the control set and the caps raise rather than degrade; the causal-chain code is fine at 14 nodes and will not scale unchanged. |
| **No multi-case infrastructure** | No tenancy, no case isolation beyond directories, no UI beyond a CLI and static HTML views. |

The honest version of the pitch: **the method transfers, the engine mostly transfers, the case
encoding is expert work.** That is a services-and-method story today, not a software-licence story.

---

## 5. Limitations, stated so you are never caught out

Each of these is a question someone will ask. These are the real answers.

**One case.** Everything is demonstrated on a single case. The engine is generic and the case data is
separated from it, but n=1.

**Nothing has been tested at a bench.** The system's output is experiments. **None has been run.**
There is no wet-lab validation of any prediction, and the project does not claim one.

**No clinical validation, no diagnostic performance, no patient outcome.** Not weak — absent, and
out of scope by design.

**The decision for the live case is `INSUFFICIENT`.** That is the current scientific answer: the
evidence does not settle the question for this child's specific allele. It is the correct answer and
it is also, honestly, not a triumphant one. Frame it as what it is — **the system refusing to
overclaim where 103 pieces of class-level evidence and 0 pieces of exact-allele evidence disagree.**

**Nothing has been sent to anyone.** The outreach layer drafts and stores; external sending is off
and the dispatch path returns an unsent draft. Zero institutional replies exist, and the reinforcement
learning component trains against a **synthetic** world.

**Zero grounded capabilities were found.** The external capability search ran, inspected a named
corpus, and found nothing that grounds the missing functions. That is a legitimate and informative
result — it is *not* a discovery. The headline metric is deliberately "previously-open interfaces
whose epistemic state changed", not "papers found".

**Two stages are not reproducible from a public clone**, because the material they consume is
gitignored.

**Corpus snapshots for the control layers hold abstracts only**, never full text. A claim whose
support lives in a figure or a methods section cannot be grounded there. Ten corpus documents are
abstract-only, including a priority study that is not open access.

**Retention is asserted, not enforced.** Deletion classes are recorded; the code does not delete.

**Some design documents are stale** relative to the code, and the repository says which ones and in
which direction. The generated reports and the code are the source of truth.

**There is no commercial traction**: no customers, no revenue, no signed partnerships, no regulatory
engagement.

---

## 6. What must never be claimed

Not guidance. A hard list. These are not matters of emphasis, and several would be false statements
about a child.

**Never claim any of the following:**

- That the system produces, recommends, suggests or identifies a **treatment, therapy, drug,
  compound, dose or intervention for a patient.**
- That anything in it constitutes **medical, clinical or diagnostic advice.**
- That it has **diagnostic performance, accuracy, sensitivity or specificity** of any kind.
- That it is **clinically validated, regulatory-cleared, or in clinical use.**
- That any result establishes **patient benefit, treatment readiness or likely outcome.**
- That a **cellular result transfers to a patient.** Every decision record in the system carries the
  line *"a cellular result does not establish patient benefit or treatment readiness"* —
  unconditionally, appended by code.
- That the system **knows, predicts or estimates the probability** that something will work. There
  are no probabilities. Saying "high confidence" about any output is a false statement about the
  software.
- That a bounded negative means **impossibility.** "We searched a named corpus and found nothing" is
  never "it cannot be done", and the system keeps three distinct terminal states precisely so these
  cannot be confused.
- That finding no evidence against something means it is **safe**.
- That the three bench questions are **biologically independent.** They are
  `NO_CROSS_PREREQUISITE` — a scheduling property. The project explicitly says they may share
  mechanism.
- That "inhibiting X raised Y in a cell" implies **"administer an inhibitor of X"**. This is the
  specific prohibition the governance layer enforces over generated documents, and it is the single
  easiest sentence to slip into in a deck.
- Anything about the **child's specific residue, coordinate or substitution.** The domain is public.
  The position is not, and it appears in no published document from this project.
- That any data holder, institution, laboratory or clinician is a **partner, collaborator or user**
  unless they have agreed in writing. Nothing has been sent; a drafted request is not a relationship.

---

## 7. Language you can safely reuse

Checked against the code. Use these as written.

**On what it does**

> "rarepipe works on cases where the causal variant is already known and nothing clinically
> actionable follows from knowing it. It asks what biological state you would need, what would have
> to be true to reach it, and which experiment would tell you — and it refuses to answer from
> anything but evidence it holds and can re-check."

**On the method**

> "Agents propose. Code decides. The system is built so that a language model can suggest where to
> look, and only deterministic code can decide what has been established."

> "Reason with agents. Prove with code."

**On evidence**

> "Every quote is re-found verbatim in the stored source before a statement is accepted. Retrieval
> and grounding are tracked as separate questions, because finding a source and a source supporting
> your claim are not the same thing."

**On negative results**

> "When the system finds nothing, it says which corpus it searched and how large it was. A bounded
> negative is a statement about what was inspected, never a statement about biology."

**On the output**

> "The output is not a recommendation. It is the space of reachable biological states, the experiment
> that moves between each pair, every admissible outcome, and an explicit account of where reasoning
> runs out."

**On governance**

> "The case-identity boundary is enforced in code and fails closed. Exact-variant external querying
> is not switched off — it is unimplemented, and the function that would authorise it has no success
> path."

**On maturity**

> "One case, worked deeply, with the engine built generically and the case data separated from it.
> The method transfers; encoding a new case is expert work."

**On the self-audit — the strongest line available, and it is true**

> "The project audited its own evidence base, found two load-bearing citations that did not support
> the claims built on them, corrected them, and recompiled every dependent conclusion. The answer
> got weaker. The system stopped knowing something it never had grounds for, and published the
> delta."

**On what it is not**

> "It produces evidence states and falsifiable experiments. It does not produce therapies, and
> nothing in it is clinical advice."

That last sentence appears at the bottom of these wiki pages for a reason. It is the correct close
to any external description of this project.

---

## Where to go next

- **What the system says today, honestly** — [`12-current-state.md`](./12-current-state.md). Read
  this before any external conversation.
- **The science, if your counterparty is technical** —
  [`08-for-clinicians-and-researchers.md`](./08-for-clinicians-and-researchers.md).
- **The data-holder conversation** —
  [`09-for-data-collaborators.md`](./09-for-data-collaborators.md), which includes the
  enforced-versus-asserted table.
- **The governance rules, consolidated** —
  [`11-governance-and-safety.md`](./11-governance-and-safety.md).
- **The self-audit, in full** —
  [`docs/control/MVA_EVIDENCE_REPAIR_DELTA.md`](../control/MVA_EVIDENCE_REPAIR_DELTA.md) and
  [`MVA_FULL_RECOMPILE_DELTA.md`](../control/MVA_FULL_RECOMPILE_DELTA.md).
- **Where help is needed** — [`13-next-steps.md`](./13-next-steps.md).

---

> This project produces evidence states and experiments. It does not produce therapies, and no
> statement anywhere in it is clinical advice.
