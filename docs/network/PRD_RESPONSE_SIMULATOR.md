# Response to the simulation-layer PRD — context, and a narrower proposal

For the incoming PM. You inherited this mid-flight, so most of this is context you could not have
had. Nothing below is a criticism of the PRD as a piece of thinking; the issue is that it is
written for a platform serving many patients, and what exists is one child, one gene, and a
deadline.

---

## 1. What already exists

**Track 1 is finished and externally scored.** Submitted 18 Sep. The organisers' evaluator
returned rank-1 full match on the causal variant pair, F-max 1.000, 100/100 rank points. The
causal gene is **BUB1B**, compound heterozygous. That result is not a claim of ours — it is their
scoring of our frozen prediction.

**Track 2 is built.** Thirteen tasks, 610 passing tests. In outline:

- A **decision engine** (17 branches, B00–B16) that states what each possible experimental result
  means, written down before any experiment runs.
- A **prospective plan** for the case: 3 experiments, ~30 endpoints, 7 competing hypotheses the
  system refuses to collapse.
- A **scenario simulator** — but read §3, because this is the thing most likely to be
  misunderstood.
- A **capability registry**: nine research groups identified from public work, with the exact
  question for each and a drafted message.
- Reproducibility machinery: two-digest provenance, cross-process determinism, generated reports,
  and a static invariant scan.

**The scientific finding is a negative one, and it is the honest part.** The candidate is nicotinic
acid, via NAD → SIRT2 → BubR1 stability. The chain does not hold up: the supporting SIRT2
experiment used a different NAD precursor, the human NAD evidence is whole-blood rather than
intracellular, and whether this child's variant leaves BubR1 *functional* is unresolved. The
system's job was to make that visible rather than let a plausible chain read as a lead.

**The plan is not ready to run.** 112 scientific-readiness gaps. **Zero** accepted by a human.
Three fields complete. It is a DRAFT and the validator refuses to freeze it.

## 2. Constraints you will not find in the repo

- **Data deletion by 24 Oct 2026.** Hackathon rules: genomic material deleted within 30 days of
  close, with notification to the organisers. Any roadmap past that date cannot assume access to
  the controlled data.
- **No recontact** of the child, the family, or the MVA Society. This is absolute.
- **Nothing has been sent to any institution.** External send is disabled in policy; dispatch
  produces a prepared, unsent artifact. This is deliberate, not unfinished.
- **No clinician, no statistician, no assay scientist is attached to this project.** The blocked
  fields break down as 21 assay-scientist decisions, 7 statistical, 3 operational, 1 scientific
  lead. The PRD's personas describe roles that do not currently exist here.
- **The repo goes public after the hackathon.** Exact variants, positions and private paths stay
  in a controlled layer and are scanned out of every export.

## 3. Four places the PRD rests on something that is not the case

**a) EXP01 and EXP02 have never been run.** The validation plan treats them as the primary
benchmark — "compare its predictions against the actual experimental outcomes." There are no
actual outcomes. There is no wet lab, no sample, no institution engaged. This is not a scheduling
problem; it is the single external milestone that no amount of engineering closes.

**b) "≥50% reduction in required confirmatory wet-lab experiments."** We have run zero. The
baseline is zero, so the metric cannot be computed, and if it could it would be a reduction from
nothing.

**c) "R > 0.7, AUC > 0.8 on held-out assays."** Against which labels? For this case there are no
measured outcomes to hold out. A benchmark of published checkpoint experiments is possible, but
that measures a general cell-biology simulator against other people's systems — a different
project, with a different deadline, and no bearing on this child.

**d) We already have a simulator, and it is not the one the PRD assumes.** Ours simulates
**institutional behaviour** — whether a group replies, refuses, has no resource, or sends
something uninterpretable — in order to exercise the outreach loop. It deliberately contains no
biology. The PRD describes a **mechanistic cell** simulator. Those are different systems; the
second is not an extension of the first.

**One architectural conflict worth flagging early.** The PRD proposes feeding simulation outputs
back into the knowledge graph as evidence, marking hypotheses "supported" or "refuted". Our origin
model makes that structurally impossible on purpose: a synthetic record cannot enter a live
campaign store or become real feedback, and the constructor raises if you try. That invariant is
load-bearing — it is the thing stopping a model's output from becoming a finding about a child.
If the simulation layer needs to write into the evidence graph, that is a decision to make
explicitly and in the open, not a schema detail.

## 4. What is right in the PRD, and worth keeping

Three ideas, and one of them is the whole MVP:

- **Sensitivity analysis — which parameter actually drives the outcome.**
- **"Recommended Reduced Assays" — which subset of the nine EXP01 endpoints would have sufficed.**
  This is the best idea in the document and it is buried in the MVE section.
- **Uncertainty as distributions rather than point estimates.**

## 5. The narrower proposal: analyse the decision, not the cell

You do not need a mechanistic model of a cell to answer the question that actually blocks this
case. The question is not *what will the cells do* — nobody can answer that without the
experiment. The question is **which measurements would change what we do**, and that is a property
of the decision rules we already have. It is exactly computable, today, with no biology, no ODEs,
no parameters, and no wet-lab data.

I built a throwaway version this afternoon to check the idea was sound. It took about twenty
minutes, and it immediately found something.

### What it computes

Enumerate the possible outcomes across EXP01's endpoints, run each through the real decision
engine, and ask which endpoints change the answer.

```
outcome vectors enumerated : 128
distinct decisions reached : 3
```

128 possible result patterns collapse into **three** distinct decisions. That alone is worth
knowing before anyone books instrument time.

### What it found

Checking every branch that declares it applies to an experiment against the inputs that experiment
actually measures:

> **EXP01 does not measure `cell_death`.** Four branches that declare they apply to EXP01 —
> **B08** (hold the rescue conclusion), **B09** (adverse hold), **B10**, and **B16** (record a
> population change) — require `cell_death` and therefore **cannot fire on EXP01 at all.**

Concretely, feed EXP01 this result:

| endpoint | value |
|---|---|
| expression_comparability | matched |
| checkpoint_activation | normal |
| checkpoint_silencing | normal |
| chromosome_alignment | normal |
| missegregation | normal |
| **viability** | **decreased** |
| **division_rate** | **decreased** |

and the engine returns:

```
PROPOSED | PERMIT_DRUG_MECHANISM_PLANNING, STRENGTHEN_H01_FOR_MEASURED_ENDPOINTS
```

The cell population is shrinking and dying, and the system reads it as a success that unlocks
drug-mechanism planning. The same shape of result on **EXP02**, which does measure `cell_death`,
correctly fires `RECORD_POPULATION_CHANGE` and `HOLD_PROGRESSION`.

So the safety hold I would have described in the submission video as "fires even when the result
looks good" is **inert on the first experiment** — the one that gates whether drug-mechanism
planning is permitted at all. The branch is present, declares it applies, and cannot reach.

EXP03 has a smaller version of the same problem: it omits `sirt2_activity` and `k668_acetylation`,
so B06 and B11 — the two branches that test whether the mechanism explains a replicated signal —
cannot fire on the replication experiment.

*Honest caveat on my own check:* it also flagged B01, B15, B12 and B13. Those are false positives
— B01 and B15 list prose placeholders rather than endpoint keys, and B12/B13 need `context.*`
fields supplied separately. Real finding: **four inert branches on EXP01, two on EXP03.**

### Why this is the right MVP

- It needs no wet-lab data, so it is not blocked on the thing that blocks everything else.
- It is exact rather than predictive. There is nothing to calibrate and no accuracy claim to
  defend.
- It is falsifiable in the only way that matters here: it either finds a gap or it does not, and
  it found one in twenty minutes.
- It directly serves the clinician. "These five endpoints change the decision; these two do not,
  and this one is missing" is actionable. "Our model predicts BubR1 rises 1.4-fold" is not, and
  invites a trust we have not earned.
- It strengthens the plan we are actually handing over, rather than building a second system
  beside it.

### Scope I would propose for Sprint 1

1. **Branch reachability check.** For every experiment, every branch declaring it applies, report
   whether the experiment's endpoints can supply its required inputs. Ship it as a validator gate
   so an experiment that silences its own safety holds cannot pass review. *This is the fix for
   what I found above.*
2. **Endpoint discrimination report.** Per experiment: how many distinct decisions are reachable,
   which endpoints change the answer, which are redundant *for the rule set* — stated that way,
   because an endpoint can be scientifically essential and still not move this decision.
3. **Minimal discriminating set.** The smallest endpoint subsets that preserve every distinction,
   handed to the assay scientist as a costing question, not as a recommendation.
4. **Add `cell_death` to EXP01** — or record, in the plan, an explicit decision not to, with the
   consequence stated. This is a plan change and needs the scientific lead, not an engineer.

Four to six weeks, one engineer, no new infrastructure, no new dependencies, and it extends code
that already exists and is tested.

### What I would defer, and why

Phenopackets, Beacon, EHDS enclaves, DUO codes, Kubernetes, 99.5% uptime, M≈100 patients, the
module catalogue, PK/PD, delivery and trafficking, the public benchmark and the Arc comparison —
all reasonable for a platform. We have one case and a data-deletion date three weeks out. Every
one of these can be added later by a team that has a second patient; none of them helps this
child, and several would not survive the deletion deadline.

I would also drop the **PubMed/bioRxiv RSS watch-state** for now. Auto-ingesting literature into a
live case is the exact path our intake layer is hardened against: external content is untrusted
data, an instruction inside it is never an instruction, and every extracted field must be grounded
in a verified span of a retrieved document. A keyword feed that enqueues re-simulation bypasses
all of it. The idea is good; it needs the grounded path, not an RSS reader.

## 6. One open item you should know about

Two citations in the hypothesis seed — **PMID 42628241** and **PMID 42543917** — appear only in
source code. No retrieval record, no stored document. They are load-bearing: together they are the
evidence base for H03, and 42543917 carries the "closest nicotinic-acid experiment was null"
claim. Stage 06 was built so a citation must be retrieved into a bundle with the quoted passage
found verbatim in the stored document; these bypassed that path by being seeded directly in code.

They may well be real. I cannot verify them offline and I will not assert them. Worth resolving
before anything cites them externally.
