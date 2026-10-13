# For clinicians and researchers

This page skips the software. It explains what the system does *scientifically*, what it would hand
you, and what the three questions currently frozen for a bench actually ask. It assumes you know
cell biology and genetics, and nothing about this codebase. Every term specific to the project is
defined where it first appears.

If you want one sentence: **the system decides which biological world the case is in, given what
you measure next — and it refuses to answer from anything except evidence it holds and can
re-check.**

It produces evidence states and falsifiable experiments. It does not produce therapies, and nothing
in it is clinical advice.

---

## 1. The case, stated honestly

A child with mosaic variegated aneuploidy — cells carrying varying, randomly distributed
chromosome-number abnormalities — with biallelic *BUB1B* variants: one truncating allele, one
missense allele. *BUB1B* encodes BubR1, a core component of the mitotic checkpoint, the surveillance
mechanism that holds a dividing cell at metaphase until every chromosome is correctly attached to
the spindle.

The causal variants are known. **Nothing clinically actionable follows from knowing them**, and that
gap is the problem the project exists to work on.

So the question moved from *what is the variant* to *what is the biological state, and what would
have to be true to change it.*

### What the primary functional evidence establishes

Computed from the controlled case artifacts — 16 variant experiments, 49 claims, 1410 evidence
records, every quote re-found in the stored corpus, nothing typed by hand:

**The child's missense allele sits in the protein kinase domain.** That is from the case's own
protein-feature evidence. (The domain name is public biology. The residue is not, and appears in no
published document from this project — see §6.)

**For that region, function at restored abundance is demonstrated — for one endpoint.** Two
kinase-domain substitutions, I909T and L1012P, forced to wild-type-comparable levels, fully restored
the nocodazole response. The assessment returns class-level `function_persists` on exactly those two.

**The mechanism of low abundance is protein turnover, not transcription.** mRNA is normal; turnover
roughly doubles under cycloheximide; levels collapse under HSP90 inhibition while wild-type barely
moves. The authors read this as misfolding.

**The kinase domain is dispensable for both mitotic functions.** The 731X truncation has no kinase
domain and still restores checkpoint, segregation and alignment. So a kinase-domain substitution
matters because it *destabilises the protein*, not because it removes catalysis.

**Abundance is not a general explanation for MVA *BUB1B* alleles.** The same assays demonstrate the
opposite regime: Y155C, in the N-terminal TPR domain, is expressed normally, localises normally,
restores chromosome alignment — and fails to restore checkpoint activity. 483X is its mirror image:
checkpoint-competent, alignment-incompetent, with significantly extended mitosis. **Function is
separable by domain, and a protein at full abundance can still be half broken.**

### What is still unknown, and why it is the whole case

**Only one of four functional endpoints was measured at restored abundance.** The measured endpoint
is checkpoint activation (nocodazole response). Three were not reported at restored abundance:
checkpoint silencing, chromosome segregation, chromosome alignment. Alignment was tested for these
alleles only at a low ectopic level, where failure is uninterpretable because the abundance was
insufficient. The published generalisation that these mutations constrain nothing but abundance
**rests on the nocodazole response alone.**

**No experiment anywhere has expressed this child's exact substitution at matched abundance.**

Those two sentences produce the project's central number pair:

| Claim | Status | Establishing records |
|---|---|---|
| Variant-class claim (kinase-domain missense behaves this way) | `PARTIALLY_SUPPORTED` | **103** |
| Exact-variant claim (this child's substitution behaves this way) | `UNRESOLVED` | **0** |

**The gap between 103 and 0 is the case.**

So the decision is recorded at two levels at once, and they must not be merged:

| Level | Verdict | Basis |
|---|---|---|
| Variant class, kinase domain | `function_persists` | I909T and L1012P restored the measured function at wild-type-comparable level |
| This child's allele | `insufficient` | No experiment expressed this exact substitution; **sharing a domain does not settle residual function** |
| **Decision** | **`INSUFFICIENT`** | The residual-function dependency stays open |

No probability is attached to any of this, and none should be.

### The result that makes the decision trustworthy

Knowing which domain the allele sits in moved the class-level reading a long way and moved the
decision **not at all.** That was checked *before* the real annotation was available, by running the
assessment with a probe residue in each of the three domains: class level came back
`function_persists` in the kinase domain and the central region, `mixed` in the TPR domain — and the
decision stayed `INSUFFICIENT` in **every** one. The real annotation then landed in the kinase
domain and returned the same decision.

**The invariance is the result, not a coincidence.** A system whose conclusion is unchanged by the
fact you were most excited to learn is a system whose conclusion was not resting on hope.

### H01 versus H02

Two competing hypotheses were on the table:

- **H01** — adequate abundance permits useful function.
- **H02** — a functional defect remains even when abundance is restored.

The experiments discriminate, but not by making one win. They make the two **asymmetric in
endpoint**, which is sharper.

H01 now rests on a direct matched-abundance experiment in the child's own domain rather than on
inference — **for checkpoint activation only**, which is a hard limit and not a caveat. H02 was
previously carried on a single abstract-level citation at gene scope; it is now an experimentally
demonstrated phenotype for a *BUB1B* missense allele at normal abundance and normal localisation
(Y155C). H02 stopped being a bare alternative.

The two are **not mutually exclusive.** The published model is two patient groups — one explained by
abundance, one combining reduced abundance with direct functional impairment. `MIXED` is a live
outcome, not a hedge.

**For this child's allele the discrimination now collapses to three observables: chromosome
alignment, checkpoint silencing and chromosome segregation, at matched abundance.** Checkpoint
activation can no longer separate H01 from H02, because the class-level evidence says it returns.
That is the smallest remaining biological uncertainty, and it is what the experiments below are
designed around.

---

## 2. How a claim earns its status

Every scientific statement in the system carries three things: a **class** (what kind of knowledge
it is), a **scope** (what it is about), and a **source** that can be re-checked.

Three rules govern how a statement gets a status, and all three are enforced mechanically.

**A quote must be re-found in the stored source.** Not reported, not summarised — found again,
verbatim, in the document the system holds. A paraphrase fails. In one of the loaders a single
failed quote rejects the entire input file.

**Only certain evidence levels may *establish* a claim.** A computational predictor score or a
protein-domain annotation is *visible* on a claim but **cannot change its status**. It lands in
`indirect_evidence`. Among the predictors, only REVEL has calibrated ACMG bands available, so
AlphaMissense, MVP, CADD, PolyPhen, SIFT and MutationTaster are recorded as `indeterminate` with a
note that no calibrated mapping exists — rather than being given a strength they have not earned.

**Scope cannot be borrowed.** Evidence about *other* variants in the same domain is recorded at
`variant_class` scope and may not stand in for an `exact_variant` claim. A claim at exact-variant
scope is rejected unless at least one cited document actually mentions the case's own residue —
checked locally, with nothing leaving the machine.

### "Nobody has measured this" is a legitimate output

This matters more than it sounds. The system is built so that **"no accessible source reports a
functional experiment on this residue"** is a complete, reportable scientific result — not a failure
to find something.

Three claims that are routinely confused are kept structurally apart:

| The claim | What it means |
|---|---|
| We searched a named corpus and found nothing | A statement about **that corpus**, with its size and queries printed |
| It is not in our local case material | Much weaker — our material is small |
| Evidence establishes this cannot be so | The strong claim, and it has to be earned |

Every negative result names the universe inspected. A refusal from a data holder — *no relevant
data*, *not searched*, *access denied*, *cannot disclose* — **can never become "measured, no
effect"**; those are classified as operational outcomes that are ineligible to become observations.
And a search that found nothing produces no evidence record at all. It produces an unresolved
evidence need.

### The backward audit, and the result that should earn your trust

Rules about what enters do nothing about what is already believed. So the grounding rule was run
**in reverse** over every citation the project's causal chain rested on. Fourteen attributions were
graded; **two were disqualified.** One was already suspected. The other was found only because the
audit ran over everything rather than over the one that had already failed.

Concretely: a citation the chain rested on, carrying the verdict *contradicted*, turned out to be a
study of white adipocytes adapting to cooler temperatures. Its stored text contains neither the
compound's name nor any spelling of the protein, so it cannot report a null effect of one on the
other.

Before anything was retired the system searched for the reference that was *meant* — the plan seed,
the curated corpus, the simulator's reference constants, the commit that introduced the citation,
and targeted external queries. Outcome: not found. Inventing a replacement is **not representable**
in the data model.

Then every dependent layer was recomputed. **The answer got weaker.** Withdrawing the refutation
meant a route stopped being excluded as falsified — it is now an assertion with no evidence either
way. The system stopped knowing something it never had grounds for.

That is the single best reason to trust the rest of this page.

---

## 3. Experiments with the interpretation fixed in advance

Every experiment the system specifies carries a **precommitted interpretation matrix**: for each
admissible outcome, written down *before the result exists*, what that outcome licenses and —
separately and explicitly — **what it does not license.**

This is not a formality. It closes the gap that normally swallows a result: deciding after the fact
what a number meant.

The machinery behind it, in plain terms:

- Each experiment declares its endpoints, its validity gates, and its admissible outcomes.
- Outcomes are evaluated in **three-valued logic**: true, false, or **unknown**. Unknown is not
  zero, and a missing measurement produces an explicit information request rather than a default.
- Seven distinct ways a value can be absent are kept apart — *unknown*, *not measured*, *not
  reported*, *unavailable*, *inconclusive*, *evidence against*, *not applicable*. **None of them
  means zero.**
- Two **admissibility gates** run first: is the identity and provenance of the sample verified, and
  are precision, controls and required readouts present. If either fails, no scientific conclusion
  is permitted — and the conclusions that *would* have matched are listed as `inadmissible_matches`
  rather than quietly dropped, so you can see what was almost concluded.
- No branch takes precedence. **Every** matching branch is kept, and when two proposed actions
  contradict each other the record requires a human to choose.
- Editing a forecast after results exist is marked a post-result amendment, and the original scoring
  stands.

One thing the system will not claim: a hash proves which bytes you have, not when you saw a result.
Without independent timestamp evidence, a frozen plan is marked
`TEMPORAL_STATUS_UNVERIFIED` and **no preregistration is claimed.**

### Safety and confounder readouts are required, not optional

This is the rule most likely to matter to you at the bench, and the system treats it as
load-bearing rather than courteous.

**Fewer errors in a dying population is selective loss, not rescue.** If an intervention kills
aneuploid cells preferentially, the aneuploid fraction falls and every chromosome-fidelity readout
improves — while nothing has been corrected in any cell.

So:

- Viability, cell death and division rate are **required** readouts with their denominators, not
  optional additions. A result missing one of them is not a weaker result; it is inadmissible.
- A reading is only treated as a clean discriminator **if no uncontrolled process could fake it.**
  The code names the confounders explicitly and only credits an experiment that measures them too.
  A falling aneuploid fraction separates rescue from failure *only if cell death is measured beside
  it.*
- A population-scale improvement states, in the same breath as the result, that it **corrected no
  cell.**
- A mechanism that moves a population must say what makes the movement selective. "Selection" is not
  an answer.
- The cell-level functional target is a **conjunction of four** things — low missegregation,
  preserved viability, preserved division, no increase in cell death — so "fewer errors" alone
  cannot satisfy it.
- And because a result in a cancer or immortalised line is not a result in the lineages that carry
  this child's burden, that transfer is held as a **separate named question** with its own unknowns.

---

## 4. The three questions frozen for a bench

These are the concrete ask. Full specifications are in
[`docs/control/MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md), with
execution packets for two of them.

**They are `NO_CROSS_PREREQUISITE`: each can be executed and interpreted without knowing either of
the others' outcomes.** They can go to a bench in any order, or all at once.

> **That is a scheduling property, not biological independence.** They may well share mechanism —
> one of the project's own latent-variable hypotheses proposes that some of them do, and BR1 exists
> precisely because a connection between two of them is plausible. Nothing claims they are
> mechanistically unrelated. The claim is narrower: **no result is a prerequisite for running or
> reading another.**

They are **not ranked** and none is conditional on another. A matrix for handoff, not a route.

### CHAR01 — is the destabilisation premise true for this allele?

| | |
|---|---|
| **Question** | Does this child's exact missense allele destabilise the BubR1 protein at all? |
| **System** | Human cell line with LAP-tagged BubR1 constructs (U2OS or HeLa). **No patient material required or used.** |
| **Manipulation** | Construct panel — the exact case substitution; wild-type; I909T and L1012P as reference destabilised; Y155C or R550Q as stable controls away from the kinase domain; Q921H as a kinase-domain substitution normal in both level and function. Then cycloheximide chase, HSP90 inhibition, MG132, and MG132 plus HSP90 inhibition. |
| **Validity gates** | I909T and L1012P reproduce their published reduction; Q921H returns normal; transcript level normal in the test arm; construct identity verified locally first. |
| **Primary readout** | Steady-state abundance by quantitative immunoblot — all arms on one membrane, loading control, wild-type as reference. |

Q921H is in the panel for a precise reason: a kinase-domain substitution that is normal in both
level and function shows that **domain location alone does not establish instability.**

The outcome that is most often misread is `not_destabilised`. It licenses exactly one thing: simple
abundance-limited instability is not demonstrated *in this construct*, and exact functional
characterisation remains required. It does **not** license a direct functional defect, nor
assignment to the Y155C regime, nor any statement about the child's endogenous protein.

A transcript difference in the test arm makes the condition **uninterpretable** — protein stability
cannot be read off an arm whose transcript differs — and routes to expression-validity work rather
than to any outcome.

### FLUX01 — can chromosome fidelity be corrected by other physics?

| | |
|---|---|
| **Question** | Does physical manipulation of microtubule poleward flux reduce chromosome missegregation in a **BubR1-limiting** human-cell state, while preserving viability, division and cell death? |
| **System** | Human cells with titratable BubR1 depletion — a doxycycline-inducible shRNA line; hTERT-RPE-1 preferred because the flux work was done there and it is non-transformed, HeLa as fallback. Chromatin marker for live imaging. |
| **Manipulation** | A measured BubR1-limiting **gradient** spanning known reference regimes, crossed with three mechanistically independent flux perturbations: low-dose paclitaxel, HAUS8 codepletion, NuMA codepletion. |
| **Validity gates** | BubR1 level measured by quantitative immunoblot in **every replicate** — not assumed from a pilot; flux engagement validated per arm; the KIF18A-depleted arm reproduces the published rescue in these hands. |
| **Primary readout** | Missegregation — lagging chromosomes in anaphase by live imaging, and micronuclei in the following interphase, **per assessable division**. |

The gradient is the design. The reason it matters: **every relevant published experiment ran at
BubR1-present or BubR1-absent, never BubR1-limiting** — which is the case's actual regime. That
finding came out of five full texts and is why a gradient, rather than a single depletion level, is
specified.

Note what `lower_missegregation_benefit_needs_residual_bubr1` licenses: a **compensatory** route,
exploiting residual function while altering another physical process. That is a *result*, not a
failure — and it does not weaken the route, because the functional target never required avoiding
the protein.

**A null without validated engagement is not a null.**

The published ~6% and ~13% abundance figures are cited as the reason a quantitative match is needed,
**never as a cutoff.** No abundance level is claimed to reproduce this child — whose own BubR1 level
has never been measured.

### BR1 — does the abundance axis touch the phosphatase axis?

| | |
|---|---|
| **Question** | At experimentally matched BubR1 abundance, does K668 state alter kinetochore PP2A-B56 recruitment? |
| **System** | Human cells expressing acetylation-mimetic and non-acetylatable K668 constructs, abundance matched across comparison conditions. |
| **Validity gate** | **Abundance matched across comparison conditions, in the same experiment.** This is the whole design — the established K668 stability effect would otherwise confound the recruitment readout. |
| **Primary readout** | Kinetochore PP2A-B56 per kinetochore. |

K668 is a **published** residue in the central region. It is **not** this child's position, which is
in the kinase domain — so neither document discloses the other.

Two things about this one are unusually strict:

**An unmatched comparison is never negative evidence.** `abundance_not_matched` licenses *nothing*
and is recorded as non-informative.

**Four specific substitutions are refused.** Changes in chromosome alignment, cohesion, checkpoint
silencing or missegregation **may not stand in for the recruitment measurement** — because those
four are exactly the readouts the parent latent-variable hypothesis predicts will co-move. Accepting
one as evidence for BR1 would confirm the bridge using the very observations that motivated it. A
change in any of them with recruitment unmeasured leaves BR1 **unresolved.**

And the project states its own prior against itself: the structural facts lean *against* this
bridge, because K668 sits at the B56 interface but **outside** the three positions that carry
binding. It is worth asking because a positive result would create a cross-district mechanism, and
because one experiment can kill it without touching anything else.

### What none of the three licenses

Patient benefit. Treatment readiness. Any statement about this child's endogenous protein. Any
inference that a result in a cancer or immortalised line transfers to the lineages that carry this
child's burden.

---

## 5. What you would actually receive

For any experiment the system specifies, the handoff is:

- The **scientific question**, in one sentence.
- The **biological system** required, with named cell lines and the reason for each.
- The **manipulation**, including the control panel and why each control is in it.
- **Validity gates** — the conditions under which the run is interpretable at all, including which
  published results your hands must reproduce first.
- The **primary readout**, and the supporting and safety readouts, each with its denominator.
- The **admissible outcomes**, each with what it licenses and what it does not.
- The **invalid / non-informative conditions**, named in advance.

What you will not receive: a compound to administer, a dose, a predicted effect size, a probability
of success, or a ranking of which experiment to do first. Those are either not grounded or not the
system's to decide.

---

## 6. The privacy boundary, in terms that affect your work

Three things worth knowing if you collaborate on this:

**The exact substitution stays local.** It is supplied to a synthesis provider as a sequence through
a private channel and appears in no external order, report or query. It is in none of the published
documents — including the bench matrix a lab works from.

**Domain-level is public, residue-level is not.** The project states that the allele is in the
protein kinase domain, because a domain name is public biology. It never states the position. The
gradings that compare a published residue to the child's are computed locally and held in restricted
fields that the publishable artifacts strip — because a nearby published variant plus a position
would localise the child's residue.

**A published residue may leave only when it is attested.** A residue token is released only if it
is found verbatim in a committed public source snapshot, checked per token and per source. And a
residue derived from the private case is **refused however well attested it is elsewhere.**

No case variant has been sent to any external provider. Exact-variant external querying is not
merely disabled — it is unimplemented, and the function that would authorise it has no success path.

---

## Where to go next

- **The case decision in full** —
  [`docs/control/MVA_CASE_DECISION.md`](../control/MVA_CASE_DECISION.md), with
  [`MVA_FUNCTIONAL_EVIDENCE_MAP.md`](../control/MVA_FUNCTIONAL_EVIDENCE_MAP.md) holding the
  experiments it rests on.
- **The three bench questions** —
  [`docs/control/MVA_BENCH_EXECUTION_MATRIX.md`](../control/MVA_BENCH_EXECUTION_MATRIX.md), then
  [`CHAR01_EXECUTION_PACKET.md`](../control/CHAR01_EXECUTION_PACKET.md) and
  [`FLUX01_EXECUTION_PACKET.md`](../control/FLUX01_EXECUTION_PACKET.md).
- **The discriminating experiment for H01 versus H02** —
  [`MVA_EXP01_DECISION_PACKET.md`](../control/MVA_EXP01_DECISION_PACKET.md) and the protocol in
  [`MVA_EXP01_PROTOCOL.md`](../control/MVA_EXP01_PROTOCOL.md). The separate question of whether this
  protein can be stabilised at all is [`MVA_STAB01_PROTOCOL.md`](../control/MVA_STAB01_PROTOCOL.md),
  which answers physical controllability and never function.
- **Everything that is reachable, and where reasoning runs out** —
  [`06-route-map.md`](./06-route-map.md).
- **Why the evidence can be trusted** — [`05-evidence-discipline.md`](./05-evidence-discipline.md).
- **Terms defined** — [`14-glossary.md`](./14-glossary.md).

---

> Sharing a domain does not settle residual function. Fewer errors in a dying population is
> selective loss, not rescue. A null without validated engagement is not a null.
