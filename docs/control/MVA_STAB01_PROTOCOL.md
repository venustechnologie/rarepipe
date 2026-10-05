# STAB01 — execution-ready protocol: can this substrate class be stabilised?

**Question.** Can the steady-state abundance of a misfolding, kinase-domain-destabilised BubR1 missense
protein be increased in a human cell by perturbing its folding or degradation machinery?

**What this experiment does not answer.** Whether a stabilised protein works. EXP01 answers function;
STAB01 answers physical controllability. A result here is never reported as functional rescue, and the
`MVA_BUBR1_STABILITY_REALIZATION.md` M5 entry is the reason the separation matters: the KEN degron would
stabilise BubR1 and destroy the checkpoint, so "more protein" and "working protein" are genuinely
different claims.

**Why the reference mutants come first.** I909T and L1012P are the characterised substrates: normal
transcript, ~2-fold elevated turnover, HSP90-dependent, proteasome-cleared. The mechanism is already
established there, so a perturbation that does nothing to them tells us the perturbation is inert, not
that the case allele is special. The exact case allele is only tested after a perturbation moves the
reference class — stated as a stop rule in §6.

**Perturbations are research control variables.** Every agent below is a tool for setting a state
variable in a dish. Nothing here is a treatment recommendation, and no result licenses one — including
the opened search vocabulary: a compound used to perturb a cell is not a candidate for anybody.

---

## 1. Substrates

| arm | construct | role |
|---|---|---|
| R1 | LAP-BubR1 **I909T** | reference destabilised substrate |
| R2 | LAP-BubR1 **L1012P** | second reference destabilised substrate |
| W | LAP-BubR1 **wild-type** | the abundance ceiling and the specificity control |
| N | LAP-BubR1 **Y155C** or **R550Q** | a *stable* substitution — a perturbation that raises this too is acting on BubR1 generally, not on misfolding |
| X | **this case's exact substitution** | **held back**; entered only under the §6 stop rule |

Human cells, stable or inducible expression, as in PMID:20516114 Fig. 2D/3C (U2OS used there for exactly
this purpose). Arm X's identity stays in the private layer and never appears in an external order.

Arm N is the control that makes the result mean something. The hypothesis is specifically about
*misfolding* clearance; without a stable substitution in the panel, a general increase in BubR1 would be
misread as correction of misfolding.

## 2. Mechanisms to interrogate

**Grounded mechanism and proposed rescue direction are not the same claim, and this protocol keeps them
apart.** What is grounded is that a mechanism *governs* this protein's abundance. What is proposed is
that running it backwards raises abundance. The second does not follow from the first, and every
reverse-direction arm below is an experimental hypothesis with no supporting evidence yet.

### Grounded — the mechanism governs this substrate class

| id | mechanism | what is demonstrated | source |
|---|---|---|---|
| P1 | HSP90-dependent folding | HSP90 inhibition collapses mutant BubR1 levels while wild-type barely moves; the mutant depends on chaperone capacity | PMID:20516114 |
| P2 | proteasomal clearance | MG132 prevents the enhanced turnover HSP90 inhibition causes; the mutant is proteasome-cleared | PMID:20516114 |

Both are grounded **on the reference substrates themselves** (I909T, L1012P), which is what makes them
the right place to start. Both are demonstrated only in the destabilising direction.

### Grounded relation, untested on this substrate

| id | mechanism | what is demonstrated | where it stops |
|---|---|---|---|
| P3 | SIRT2 ↔ BubR1 K668 acetylation | SIRT2 overexpression and NMN raise BubR1 abundance in mouse tissue (PMID:24825348); selective Sirt2 inhibition destabilises BubR1 in human HeLa cells (PMID:25672491) | both directions established, neither on a misfolding mutant; the raising direction only in mouse |
| P4 | FBXW7 / Thr620 phosphodegron | FBXW7 depletion increases BubR1 stabilisation at kinetochores; T620 is a phosphodegron (PMID:38008853) | human cells, but a kinetochore pool rather than steady-state abundance, and on normally folded protein |

### Proposed rescue directions — hypotheses, not grounded

| id | manipulation | status |
|---|---|---|
| P1-R | raise chaperone capacity: HSF1 activation, or HSP70/HSP40 co-expression | **no supporting evidence.** That the mutant depends on HSP90 does not establish that more chaperone raises its level. Run as a hypothesis and report as one |
| P2-R | reduce degradative flux below baseline | **no supporting evidence**, and confounded: proteasome inhibition is broadly toxic, so S6 governs whether any S1 change is readable at all |
| P3-R | raise SIRT2 activity on a misfolding substrate | **extrapolated** from mouse wild-type protein |
| P4-R | deplete FBXW7 to raise steady-state (not pool) abundance | **extrapolated**, and the published effect was pool-confined |

Reproducing P1 and P2 in the destabilising direction is the **positive control that the assay can detect
a change at all**. It is not the experiment. The experiment is every `-R` row, and each is labelled a
hypothesis in the result record regardless of outcome.

### What the closed literature search adds

The search for a grounded reverse direction is **closed**: 50 queries over four rounds, the last bounded
round aimed directly at this gap with CRISPR, small-molecule, compound-screen, modifier-screen and
proteostasis-screen vocabulary. No genetic modifier screen, proteostasis screen or perturbation study
raises the steady-state abundance or slows the turnover of a destabilised BubR1 missense protein. The
`-R` rows are therefore not merely unsupported in this document; they are unsupported in the retrieved
literature, which is why this has to be run rather than read.

One finding from that round changes how P1-R should be *measured*, without grounding it. Work on global
suppressors of protein folding defects across four unrelated proteins reports that suppressors act by
increasing **refolding rate**, and that "thermodynamic stabilisation is neither necessary nor sufficient
for suppressor action" (PMID:36037221). If that generalises, a chaperone-capacity arm could raise the
foldable fraction without changing thermodynamic stability — so P1-R is judged on S1 and S2, abundance
and turnover, and not on any stability proxy. The paper is not about BubR1 and grounds nothing here.

## 3. Readouts

**S1 — steady-state abundance (primary).** Quantitative immunoblot, all arms on one membrane, loading
control, arm W as the ceiling. This is the endpoint the outcome states are defined on.

**S2 — turnover / stability.** Cycloheximide chase (the source used 5 h), ± the perturbation, with the
decay of each arm quantified. This separates "more protein" from "slower loss of protein": a
perturbation can slow turnover measurably without moving steady state, which is its own outcome state
below.

**S3 — transcript abundance.** RT-qPCR for the construct and for endogenous *BUB1B*, in every condition.
**This readout is what makes the result a protein-stability claim.** Several perturbations above act on
transcription or translation as a side effect; without S3, a transcriptional increase would be reported
as stabilisation. The case's own transcript is normal, so a transcript-mediated increase would not even
address the right mechanism.

**S4 — localisation and pool distribution.** BubR1/ACA kinetochore quantification plus whole-cell signal,
after brief nocodazole with MG132. Required because M2's published stabilisation was measured **at
kinetochores**: a change confined to that pool is not whole-cell stabilisation, and conflating them is
the specific error this readout exists to prevent.

**S5 — perturbation validity.** Each perturbation is confirmed to have engaged its target in the same
experiment: HSP90 client behaviour for P1, ubiquitin-conjugate accumulation for P2, a SIRT2-dependent
acetylation readout for P3, FBXW7 protein level for P4. A null result from an unengaged perturbation is
not a null result about the mechanism.

**S6 — cell state.** Viability, cell death and division rate with denominators. Several of these
perturbations are broadly cytotoxic at the doses that engage their targets, and an abundance change read
out of a dying population is an artefact. This is a validity readout, not a safety claim about anything
outside the dish.

## 4. Outcome states

Precommitted. Assigned from S1–S3 with S4 resolving the pool question, and gated on S5 and S6.

They apply to the **proposed rescue arms** (the `-R` rows). A grounded-direction arm reproducing destabilisation is control validity, not an outcome: it says the assay can see a change, and nothing more. Each assignment records which arm produced it and whether that arm was grounded or hypothesised, so a positive result cannot later be cited as though it had been predicted.

| state | condition |
|---|---|
| `STEADY_STATE_ABUNDANCE_INCREASED` | S1 rises for R1 and/or R2 toward arm W, with S3 showing no corresponding transcript increase, S4 showing the rise is whole-cell rather than pool-confined, and S5/S6 valid |
| `TURNOVER_REDUCED_WITHOUT_ABUNDANCE_RESCUE` | S2 shows measurably slower decay but S1 does not move |
| `LOCAL_POOL_ONLY` | S4 shows the change confined to the kinetochore pool while whole-cell S1 is unchanged |
| `NO_STABILISATION` | S5 confirms the perturbation engaged its target and neither S1 nor S2 moved |
| `CONTEXT_OR_MEASUREMENT_INSUFFICIENT` | S5 shows the perturbation did not engage; or S6 shows the population is compromised; or S3 shows a transcript change that confounds S1; or a required readout is missing |

A transcript-mediated increase is `CONTEXT_OR_MEASUREMENT_INSUFFICIENT` for this question, not
`STEADY_STATE_ABUNDANCE_INCREASED` — it may be a real effect on BubR1 levels, and it is not an answer
about stabilising a misfolding protein.

These five states are STAB01's own vocabulary and deliberately do not reuse EXP01's `B` rules: those
encode hypothesis updates about allele function, which this experiment is not entitled to make.

## 5. What each outcome means for the project

| state | consequence |
|---|---|
| `STEADY_STATE_ABUNDANCE_INCREASED` | the first instance of `mechanism -> physical perturbation -> measured rescue of a broken state variable` for this case. The abundance route stops being a black box and acquires a component. Function is still EXP01's question |
| `TURNOVER_REDUCED_WITHOUT_ABUNDANCE_RESCUE` | the degradation arm is reachable but another process is rate-limiting — most likely synthesis or folding capacity. Points at P1's untested direction |
| `LOCAL_POOL_ONLY` | explains M2's published result and closes it as a route to whole-cell abundance |
| `NO_STABILISATION` | this substrate class is not controllable through the interrogated machinery. The missing capability stated in `MVA_BUBR1_STABILITY_REALIZATION.md` §9 stands, and the search moves to machinery not covered by P1–P4 |
| `CONTEXT_OR_MEASUREMENT_INSUFFICIENT` | nothing moves; the failed validity readout is named and the condition repeated |

## 6. Stop rule on the exact case allele

Arm X is not run in the first pass. It enters only when a perturbation reaches
`STEADY_STATE_ABUNDANCE_INCREASED` on R1 and/or R2 — and then the question asked of it is narrow: does
the same perturbation, at the same engagement level, raise arm X's steady-state abundance toward arm W?

Reason: the reference substrates are characterised and the case allele is not, so a null on arm X in a
system that has not been shown to work on anything is uninterpretable, and it would spend the case
construct on a question the panel cannot yet answer. A positive on R1/R2 followed by a null on X is a
real and interpretable finding — this allele is not stabilisable by that mechanism — and only reachable
in that order.

## 7. What this experiment cannot conclude

That a stabilised protein is functional. That a perturbation used here is suitable for administration to
anyone — these are control variables in a dish, and no result licenses an intervention claim. That an
effect in a cancer line transfers to the child's cells. And nothing about the exact case allele at all,
until §6 is satisfied.
