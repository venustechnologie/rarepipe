# PRD v4: what it fixed, what it broke — and the MVA-specific PRD to build instead

Fourth addendum. The first three are `PRD_RESPONSE_SIMULATOR.md`, `_V2.md`, `_V3.md`.

---

## Part 1 — v4 in brief

**What it fixed, and this matters:** the patient variant is gone from the schema examples, the
fabricated niacin treatment record is gone, the fictional seven-person roster is gone, and the
two invented institutions are gone. Those were the stop items. Thank you.

**What it broke:** it removed the dates. *"Dejen de calcular plazos"* — stop calculating
deadlines — and *"simular todo lo posible."*

In most projects that is a defensible call. Here it is the most dangerous line in any of the four
documents, because this project has exactly one hard constraint and it is a date: **the genomic
material must be deleted by 24 October 2026, which is 20 days away, with notification to the
organisers.** v2 and v3 had wrong dates. v4 has no dates, which in this specific situation is
worse — a wrong date gets corrected, an absent one gets discovered.

"Simulate everything possible" with no deadline, on a case whose data expires in 20 days, will
produce a half-built compiler and no data to point it at.

**Smaller items:**

- **Stage 5, "Piloto con hospital aliado … nuevos casos reales"** — recruiting partner hospitals
  and onboarding new real patients is presented as step 5 of 6. That is a different project with
  its own ethics approvals, not a later sprint of this one.
- **Blockchain for provenance** — we already have content-addressed digests and an immutable
  versioned store with a full audit log. Blockchain adds nothing here and will cost credibility
  in any technical review.
- **"HEAPSGA"** is not a thing. Whatever was meant, it needs naming correctly before it is a
  mitigation.
- **PDS/DES > 0.7** are Virtual Cell Challenge metrics for predicting differential gene expression
  after CRISPR perturbation in cell lines. EXP01 is an allele-function assay with categorical
  endpoints. The metrics do not transfer.
- **EXP01's endpoints are still listed wrong** — "expresión BubR1, aneuploidía, viabilidad". Only
  viability is in EXP01; BubR1 abundance and aneuploidy belong to EXP02. This is now the **third
  of four documents** with the same error, which tells me nobody writing these has opened the
  plan. The fix is one link, below.
- **"Revisar que las predicciones intermedias (BubR1↑, SIRT2 act) coincidan con resultados
  conocidos"** presupposes BubR1↑ as the known result. That is precisely the claim our evidence
  review found unsupported. A validation step that assumes the conclusion is not a validation
  step.

**Three good ideas worth keeping, and two of them we already have:**

- *"Para reacciones sin datos, el sistema genera amplias incertidumbres o sugiere medirlas
  directamente."* This is exactly right, and it already exists: unknowns stay typed as unknown and
  the engine emits `information_requests` naming the missing readout.
- *"Repositorio de resultados negativos."* Also already there — `EVIDENCE_AGAINST` and
  `NOT_MEASURED` are first-class, and the null niacin experiment is retained deliberately.
- *Agents that try to refute the leading hypothesis.* Carried over from v3 and still the best idea
  in any of the four. We approximate it by keeping H05 and H06 alive on purpose; formalising it
  would be real work with real value.

---

## Part 2 — The PRD I think we should build

**Decision-readiness analysis for MVA_001.** Not a virtual cell. Twenty days. One engineer.

### The problem, stated honestly

Nobody can tell you what this child's cells will do without running the experiment. A simulator
that claims to is making a prediction it cannot validate, because EXP01 and EXP02 have never run
and there are no held-out outcomes for them.

But there is a question nobody has answered that **is** answerable right now:

> Of the measurements we plan to take, which ones would actually change what we do?

That is a property of the decision rules, not of the biology. It is exact rather than predictive.
It needs no parameters, no ODEs, no VCell, no partner, no sample — and, critically, **no patient
data**, so it is the only proposed work that outlives 24 October.

### It already found something

I built the first piece to check the idea was sound. It is committed as
`tools/network/check_branch_reachability.py` and it found a real defect:

> **EXP01 does not measure `cell_death`.** Four branches that declare they apply to EXP01 — B08
> (hold the rescue conclusion), B09 (adverse hold), B10, and B16 (record a population change) —
> all require `cell_death` and therefore cannot fire on EXP01 at all.

EXP01 is the experiment that gates `PERMIT_DRUG_MECHANISM_PLANNING`. Give it a result where
expression is matched, all four functional readouts are normal, and viability and division rate
are both decreased, and the engine returns:

```
PROPOSED | PERMIT_DRUG_MECHANISM_PLANNING, STRENGTHEN_H01_FOR_MEASURED_ENDPOINTS
```

The cell population is dying and the system reads it as a success that unlocks drug-mechanism
planning. The identical result on EXP02, which does measure cell death, correctly fires
`RECORD_POPULATION_CHANGE` and `HOLD_PROGRESSION`.

That is one afternoon's work, and it is worth more to the people who would run this experiment
than a twelve-week simulator that cannot be validated.

### Deliverables

| # | Deliverable | State |
|---|---|---|
| D1 | **Branch reachability gate** — an experiment that silences its own safety holds cannot pass validation | tool built; needs wiring into the validator |
| D2 | **Endpoint discrimination report** — per experiment, how many distinct decisions are reachable and which endpoints move the answer | prototype run (EXP01: 128 outcome vectors → 3 decisions) |
| D3 | **Minimal discriminating sets** — smallest endpoint subsets preserving every distinction | not started |
| D4 | **Unresolvable-input report** — for each decision that cannot be reached, the specific missing measurement, routed to the owner who must supply it | not started |
| D5 | **One-page output for the assay scientist** — generated, not written | not started |

### Acceptance criteria

Each is checkable by someone who did not build it, which is the point.

- **D1** — Runs in CI. Reports the four EXP01 branches and the two EXP03 branches currently
  unreachable. A new experiment that omits a required input for a branch declaring `applies_to`
  its kind fails the build. Prose placeholders and `context.*` entries are classified out, not
  counted.
- **D2** — For every experiment, outputs the count of reachable distinct decisions and a per-
  endpoint verdict of discriminating or not-discriminating *for the rule set*, worded so that
  "not discriminating here" is never read as "not scientifically necessary."
- **D3** — Outputs every minimal subset, not one. If several are minimal, the choice between them
  is a cost and feasibility question for an assay scientist, and the tool must not pre-empt it.
- **D4** — Every unreachable decision names its missing input and the role that owns it
  (assay scientist, statistician, scientific lead, research operations).
- **D5** — Generated from the records with no hand-written numbers, consistent with how every
  other report in this repository is produced.
- **Whole** — runs with the controlled drive unmounted. If it needs patient data, it is the wrong
  tool.

### Explicit non-goals

No mechanistic cell model. No ODE compiler. No VCell or COPASI. No parameter estimation. No
Beacon or BBMRI federation. No phenopacket ingestion. No dashboard. No new patients. No partner
hospital. No prediction of any experimental outcome, and therefore **no accuracy claim to
defend**.

Each of these is reasonable for an organisation with several patients, a data agreement and a
year. We have one child, no partner, and 20 days of data access.

### The decision this forces, which is the real deliverable

D4 produces a list of specific missing measurements with named owners. That list is the thing a
scientific lead can act on in an afternoon, and the first entry on it is already known:

> **Add `cell_death` to EXP01, or record an explicit decision not to with the consequence
> stated.** That is a plan change requiring the scientific lead. Not an engineer, and not me.

### Where the plan actually lives

So the fifth document does not repeat the endpoint error: the experiments, endpoints and
hypotheses are defined in `src/rarepipe/stages/prospective/seed.py`. EXP01's nine endpoints are
expression comparability, checkpoint activation, checkpoint silencing, chromosome alignment,
missegregation, viability, division rate, kinetochore localization and PP2A-B56 recruitment.

---

## Part 3 — The question none of the four PRDs asks

Every version proposes to reduce the number of experiments. **The number currently scheduled to
run is zero.** No laboratory has agreed to anything. No clinician is attached. Every contact route
in our registry is unverified and nothing has been sent, because sending is disabled in software
and the decision belongs to the family and their clinician.

A simulator that halves zero is still zero.

Of everything across four documents, the only item that touches the binding constraint is the
outreach list we finished last week: nine groups identified from public work, the exact question
for each, and a drafted message. It is sitting in `docs/network/OUTREACH_HANDOVER.md` waiting for
a human to decide whether to send it.

I would spend the 20 days on D1–D5 and on that decision, and revisit the simulator when there is
a partner, a data agreement, and an experiment that has actually produced a number.
