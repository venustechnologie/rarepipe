# Context on the simulator PRD — what already exists, and what I'd change

For the incoming PM. You inherited this mid-flight, so this is the context the PRD reads as not
having, followed by one concrete reframe. Nothing here is an objection to simulation as a direction —
it is about what can be measured in this case, with this data, in the time we have.

---

## 1. What is already built and scored

There were two tracks, both complete.

**Track 1 — which variants cause the disease.** Scored by the hackathon organisers' own evaluator
on 18 Sep: **rank-1 full match**, F-max 1.000, 100/100 rank points. This is the only result in the
project validated by anyone other than us. It is finished and does not need the simulator.

**Track 2 — what to do about it.** This is where the PRD's "existing rare-disease discovery MVP"
actually sits, and it is further along and narrower than the PRD assumes. It is 14 work items,
T01–T13 complete, 610 tests passing. Concretely it contains:

- A **Stage 10 prospective plan** for this one case: three experiment specs (EXP01 nine endpoints,
  EXP02 twelve, EXP03 nine), hypotheses H01–H07, and a sealed immutable version store.
- A **three-valued decision engine** (17 branches, `stage10-rules-1.1.0`) that states, before any
  experiment runs, what each possible result would mean.
- A **research network**: nine institutions identified from public work only, with the exact
  question for each and a drafted, unsent message.
- A **scenario simulator** with 16 synthetic worlds and a tabular Q-learning policy over them.

The PRD says our pilot shows "true gains lie in model-based extrapolation, not in further
literature search alone." That is not quite what we found. We found that the drug hypothesis
**breaks at one specific, measurable link** — the experiment supporting the SIRT2→BubR1 step used a
different NAD precursor, and whether this child's allele leaves the protein functional is
unresolved. The gain available is not extrapolating past that gap. It is knowing which single
measurement closes it.

---

## 2. The validation plan cannot execute as written

This is the part I would resolve before Sprint 1, because four of the eight success metrics depend
on it.

The PRD validates the simulator against **EXP01/EXP02 outcomes** (§139, M2 exit criteria, MVE).
**EXP01 and EXP02 have never been run.** They are specifications inside a plan whose lifecycle is
`DRAFT` and whose native validator reports:

| | |
|---|---:|
| Scientific-readiness gaps | **112** |
| Gaps accepted by a human | **0** |
| Fields carrying a complete, unblocked value | **3** |
| Fields waiting on a named unresolved input | 70 |
| Fields waiting on a human decision or attestation | 24 |

Blocked work by owner: 21 assay-scientist decisions, 7 statistical, 3 operational, 1 scientific
lead. **None of those people are appointed.** There is no clinical lead on this case.

Two consequences:

- **"≥50% reduction in required confirmatory wet-lab experiments"** has a denominator of zero. No
  wet-lab experiment has been run for this child. There is nothing to reduce by half yet.
- **"R ≥ 0.7 against actual outcomes on held-out biological assays"** — for this case, those assays
  do not exist and will not for a long time. The benchmark in §140 (published checkpoint
  perturbations) is a legitimate and different test: it measures the simulator against *other
  people's* experiments. It must not be reported as validating a prediction about this child, and
  our existing claim index would classify it as `simulated`, not `observed`.

There is also a narrower blocker. EXP02's **exposure concentration and duration are not specified
by any field in the plan** — that is an open reviewer question, verbatim: *"Who owns the exposure
concentration and duration, which no field here proposes?"* A pharmacokinetic simulation of niacin
cannot be parameterised until a human answers that. It is a decision, not a parameter we can fit.

---

## 3. Five places the PRD would undo a safety property we built deliberately

Each of these was built because the alternative failed in review.

1. **"Mark hypotheses as 'supported' or 'refuted'"** (§77). The engine is deliberately
   *three-valued* and has no "refuted". It has holds: improvement accompanied by more cell death
   **holds** the rescue conclusion rather than recording a success; an adverse direction **holds**
   progression; conflicting endpoints **show the disagreement** and demand explicit interpretation;
   an uninterpretable result stays uninterpretable. A binary supported/refuted field is exactly the
   collapse those branches exist to prevent.

2. **Agents writing to the knowledge graph** (§75–78, §152). No agent in this system can sign a
   required human review or release a scientific freeze — it is enforced in the domain layer, and
   an agent persona *wearing* the reviewer's role is still refused. Simulation results may propose;
   they cannot update case state.

3. **Watch-state auto-re-simulation on new literature** (§82, §240). Re-running a case because a
   new paper appeared is acting on instructions found in external content. Everything external in
   this system is treated as untrusted data — an instruction inside a reply changes no permission
   and triggers no export. A watchlist that *notifies a human* is fine; one that re-runs and
   updates the graph is not.

4. **Beacon federated queries on this patient's phenotype and variants** (§117, §155). Standing
   constraint on this case: exact variants, variant pairs and HPO combinations must not be
   transmitted externally by default. A Beacon query keyed on this child's HPO terms is precisely
   that. If we want it, it needs an explicit human approval gate, not a default data path.

5. **Simulation as a capability with cost = 0** (§154). The planner would then always prefer it.
   The point of the decision rules is that a simulated result and a measured result are different
   kinds of thing; making simulation free in the planner erases that distinction at exactly the
   moment it matters.

---

## 4. The constraint that is not in the PRD

**The controlled genomic data must be deleted by 24 October 2026**, with notification to the
organisers — three weeks from today. The PRD's timeline is twelve months, with the MVA validation
in M2 (months 4–6). By then the patient data this case is built on will be gone from our
environment by rule.

Also: the repository becomes public after the hackathon, and there is no recontact permitted with
the child, the family, or the MVA Society contacts.

So a twelve-month roadmap whose first validation milestone needs this case's controlled data cannot
run on this case. Either the simulator is built against public data and published benchmarks only,
or the case work has to happen inside the next three weeks. That is a real fork and it is yours to
call.

---

## 5. What I would build instead — and it is already in your PRD

§205 of the PRD, in the MVE section, asks for:

> "Recommended Reduced Assays: Based on the simulation, list which subset of the nine original
> assays would have sufficed to differentiate the hypotheses."

**That is the valuable deliverable, and it is achievable now.** It also does not need ODE solvers,
80% variance explained, Kubernetes, or a 24-hour latency target.

Reframe the objective from **"predict what the experiment will show"** to **"work out which
measurements could change the decision."** The difference matters:

- Prediction accuracy requires ground truth we do not have and cannot get in time.
- Decision sensitivity requires only the decision rules, which already exist and are tested.

The method, concretely: we already have a pre-committed mapping from result → interpretation for
all 17 branches. Sweep the plausible space of EXP01/EXP02 outcomes, push each through the real
engine, and record **which branch fires**. Then ask: across that space, which endpoints actually
change the branch, and which never do? An endpoint whose value never alters the decision is an
endpoint the lab does not need to run first.

That gives the practitioners something they can act on in a fortnight:

- A ranked shortlist of the EXP01 endpoints that discriminate H01 from H02, and the ones that do not.
- The outcome regions where the engine holds rather than concludes — so the team knows in advance
  which results will *not* settle anything, before spending the assay.
- Honest labelling throughout: this is a sensitivity analysis over our own decision rules. It
  predicts nothing about biology, and the report generator already enforces that wording.

This is a strictly smaller build than the PRD describes, it uses what is already tested, it does
not need the controlled data, and it answers the question a clinician would actually ask: *given
limited money and sample, which measurement should we buy first?*

The mechanistic simulator in the PRD is a reasonable thing to want **after** there is one real
experimental result to calibrate against. Before that, its accuracy claims are unfalsifiable.

---

## 6. Decisions I need from you

1. **Case-specific or general?** A one-case MVA prototype in three weeks, or a general platform
   built on public benchmarks with no patient data. The PRD is written as the second but validated
   as the first, which is why it cannot close.
2. **Is the reframe in §5 acceptable** as the simulation deliverable — decision sensitivity rather
   than outcome prediction? If yes, I can scope it this week.
3. **Who answers the assay and statistical questions?** 21 and 7 fields respectively are blocked on
   people who do not exist in this project. Without them the plan stays `DRAFT` whatever the
   simulator does.
4. **Do we want the Beacon path at all?** If yes, it needs a human approval gate designed in, not a
   default query route.
5. **Two citations need verification before anything builds on them.** `PMID:42628241` and
   `PMID:42543917` appear only in the hypothesis seed code, with no retrieval record and no stored
   document. They are the entire evidence base for H03 and part of H04 — including the "closest
   nicotinic-acid experiment was null" claim. The project's own rule is that a citation must be
   retrieved into a bundle with the passage found verbatim; these bypassed it. They may be real. I
   will not assert them until they pass that check.
