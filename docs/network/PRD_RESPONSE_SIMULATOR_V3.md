# Response to the simulator PRD, third version — two items to resolve before anyone starts

Addendum to `PRD_RESPONSE_SIMULATOR.md` and `..._V2.md`. The shared objections still stand and I
will not repeat them. This version is the most actionable of the three, and it also contains the
first thing I would stop work over.

---

## STOP 1 — A specific patient variant is written into the document, and the plan sends it abroad

**Section 6 carries a concrete BUB1B HGVS coding variant** (the `genotypes` entry in the patient
object, line 112), and **the same variant is repeated in the federated-query example** (line 183)
as a value to send to external biobanks. Section 7 schedules that integration for **week 4,
25 October**.

I have not tried to match it against the case data, and I am not going to. Resolving this by
checking it against the private layer would pull the real variant into a place it must not be.
**Someone with local access should check it, offline, and not report the answer in writing.**

Both possible answers are bad:

- **If it is the child's variant**, it has been written into a planning document and scheduled for
  transmission to external institutions. The standing rule on this project is explicit: exact
  patient variants must never be transmitted externally by default, and if exact-variant external
  querying ever becomes necessary, the correct response is to **stop and build an explicit
  approval gate**, not to put it in a query example.
- **If it is invented**, a fabricated variant is sitting in a document that reads as the case's
  real data, and it would be queried against real biobanks as though it were.

For reference: the string does not appear anywhere in our repository. Our own exports scan for
exactly this shape of content and refuse rather than warn.

**Action:** remove the HGVS from both places. Replace with an obvious placeholder. If
variant-level federated discovery is genuinely wanted later, that is a governance decision with a
human approval gate, not ticket #8.

## STOP 2 — A treatment the child never received is recorded as fact

The same patient object contains:

```json
"treatments": [ {"drug":"Niacin","dose":"500mg","response":"none"} ]
```

That reads as: this child was given 500 mg of niacin and did not respond. Nothing of the kind has
happened. No one has been treated, our plan unlocks no patient intervention, and our own finding
is that the niacin hypothesis is unresolved — not tried and failed.

A fabricated negative treatment response is worse than a fabricated positive one. If it reaches a
clinician, a funder, or a future reader of this repository, it closes a question that is open.

**Action:** delete it, or mark the whole object unmistakably as a schema illustration with
non-clinical dummy values.

---

## 1. The prototype deadline is the data-destruction deadline

The PRD sets 24 October 2026 as the date for a working prototype and calls it *inalterable*. That
is the same day the hackathon requires the genomic material to be deleted, with notification to
the organisers.

So the demo date is the day the data must be gone. And the schedule continues past it: week 4
(25 Oct) federated queries and dashboard, week 5 (1 Nov), week 6 (8 Nov) — all after deletion.
Week 4 specifically proposes querying external biobanks with patient variant criteria on the day
after the data is destroyed.

I do not think this is a deliberate trade-off. I think the date was chosen because it is the date
everyone is saying, without knowing what it is for.

## 2. Institutions and people in this document do not exist

- **"SinatraLab en Moscú"** and **"SinHanover"** are named as collaboration targets for chromosome
  and BubR1 reference data. Neither appears in our capability registry and I can find no trace of
  either. Hubrecht and Musacchio, named alongside them, are real and are in our registry — which
  makes the invented two harder to spot, not easier.
- **The team roster in section 5** — Dr. Ana Pérez, Luis Martínez, María García, Carlos Vega,
  Elena Ruiz, Sofía López, Javier Muñoz, each with years of experience attached — is seven
  fictional people. If this circulates as a staffing plan it will be read as a team that exists.
- **"contactar coautores de estudios"**: no author, lab or institution has been contacted. Every
  contact route in our registry is marked unverified and external sending is disabled in software.

## 3. EXP01's endpoints are wrong in the document

The PRD lists EXP01 as covering *"abundancia de BubR1, p-S6, aneuploidía celular, viabilidad"*.
Actually:

| Listed | Reality |
|---|---|
| BubR1 abundance | belongs to **EXP02**, not EXP01 |
| p-S6 | **not in any experiment** — mTOR signalling, not in this case's graph |
| cellular aneuploidy | `total_aneuploidy` belongs to **EXP02** |
| viability | correct |

EXP01 actually measures: expression comparability, checkpoint activation, checkpoint silencing,
chromosome alignment, missegregation, viability, division rate, kinetochore localization,
PP2A-B56 recruitment. A simulator built against the listed four would be modelling a different
experiment and reporting it as EXP01.

Likewise the recommended next step in the dashboard mock — *"realizar ensayo de función
mitocondrial"* — is not in this plan at all.

## 4. Targets with nothing to measure against

- **">80% concordancia"** between in-silico predictions and real data. EXP01 and EXP02 have never
  run. There is no real data for them.
- **"~1000× virtuales por cada 1 real"** — a ratio against a denominator of zero real experiments.
- **"≥70% concordancia"** on retrospective SAC/BUB1B benchmarks is the one measurable target here,
  and it measures a general cell-biology simulator against published mitosis experiments. That is
  a real project. It is not this child's project, and it would not finish before the data is gone.

## 5. What is genuinely good in this version

More than in the previous two, and worth saying:

- **Contradiction agents** — "for each hypothesis, find evidence that invalidates it." This is the
  right instinct and it is close to what our hypothesis set already does by keeping H05 and H06
  alive on purpose. Formalising it is worth doing.
- **Sensitivity analysis with Sobol/Morris, returning a ranked parameter list.**
- **"Sin mejorar la entrega intracelular, un compuesto X nunca llegaría al sitio activo"** — the
  idea that the system should be able to say *this route is blocked for a reason that is not
  biology* is exactly right, and it is the kind of conclusion that saves real time.
- Acknowledging up front that the Virtual Cell Challenge winners did not consistently beat naive
  baselines. That honesty should propagate into the targets, which it currently does not.

## 6. What I would actually ship by 24 October

Three weeks, no new infrastructure, no partner, no sample, no patient data — and therefore not
affected by the deletion deadline:

1. **Branch reachability as a validator gate.** Already built
   (`tools/network/check_branch_reachability.py`). It found that EXP01 cannot fire four of its own
   safety holds, because it does not measure `cell_death` — including B16 and B09, the two holds
   that are supposed to stop a result that looks good while the cell population dies.
2. **Endpoint discrimination report.** For EXP01: 128 possible outcome patterns reduce to 3
   distinct decisions. Which endpoints move the answer, and which do not.
3. **Minimal discriminating sets**, handed to an assay scientist as a costing question.
4. **A decision on `cell_death` in EXP01** — add it, or record why not. Scientific lead, not
   engineer.

This is a smaller claim than a virtual cell. It is also the only version of the work that can be
true on 24 October.

## 7. The thing none of the three PRDs addresses

All three propose to reduce the number of experiments. None of them changes the fact that **the
number of experiments currently scheduled to run is zero**, because no laboratory has agreed to
run anything and no clinician is attached to this case.

A simulator that halves zero is still zero. The binding constraint is a conversation, not a
compute cluster — and of everything in these three documents, the only item that touches it is
the outreach list we already have, which is waiting on a human to decide whether to send it.
