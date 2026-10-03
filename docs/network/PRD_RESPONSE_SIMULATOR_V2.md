# Response to the simulator PRD, second version

Addendum to `PRD_RESPONSE_SIMULATOR.md`. The fundamentals in that document still apply and I will
not repeat them: EXP01 and EXP02 have never run, so there are no held-out outcomes to validate
predictions against and no wet-lab baseline to reduce by 50%; our existing simulator models
institutional behaviour rather than biology; and feeding simulation output back as evidence
contradicts an origin invariant that exists on purpose.

This version is more concrete and the ticket breakdown is genuinely usable. Three things in it
are new, and the first one decides the rest.

---

## 1. Ten of the twelve weeks fall after the data is destroyed

The hackathon requires genomic material to be deleted within 30 days of close. **That deadline is
24 October 2026 — 21 days from today.** Organisers must be notified when it is done.

Against the PRD's own Gantt:

| Milestone | Date | Relative to deletion |
|---|---|---|
| Sprint 1–2, dev environment + ingestion | ends 2026-10-15 | before |
| Sprint 3–4, causal graph + model compiler | ends 2026-10-30 | **6 days after** |
| Simulation core | 2026-11-13 | **20 days after** |
| UI / dashboard | 2026-12-11 | **48 days after** |
| Final testing | 2027-01-01 | **69 days after** |

The first virtual experiment is scheduled for weeks 5–6. By then the case data will have been
gone for roughly three weeks. The plan spends its first two sprints building ingestion for data
that must be destroyed before anything consumes it.

This is not a scheduling slip to absorb. Either the plan targets something that does not need the
controlled data, or it needs a different data agreement that does not exist yet and will not
exist in 21 days.

## 2. Statements in the document that are not true of this case

These matter more than the architecture, because each would be read as established fact.

**"Centros genéticos europeos … ya interesados" (already interested).** No institution has been
contacted. Nothing has been sent — external send is disabled in software and every contact route
in our registry is marked unverified. We have nine candidates identified from public work and
zero relationships. A roadmap that assumes willing partners at T0 is assuming the single thing
that is actually blocking the project.

**"Proveer muestras biológicas" (supply biological samples).** Out of bounds. The hackathon rules
prohibit recontacting the child, the family, or the MVA Society, and our plan says in its own text
that it "authorizes no acquisition or contact". Sample acquisition is a different governance
regime with ethics approval, consent and an MTA — not a collaboration bullet.

**EXP02 hypothesis written as "Niacina *in vivo* produce ↑SIRT2 → ↑BubR1".** Two problems. Our
EXP02 is explicitly *in cellulo*: "does nicotinic acid improve the required cellular functions in
a defined BUB1B-deficient **model**". And EXP03's recorded interpretation is that a positive
result "may unlock a translational-review task; **no patient intervention is unlocked**". Writing
*in vivo* into the experiment table is precisely the drift the decision engine exists to catch.
Stating it as the hypothesis to confirm also inverts our actual finding, which is that this chain
is unsupported at its decisive link.

**EXP01 described as "introducción de un gen BUB1B funcional".** That is gene therapy. EXP01 is an
allele-function experiment asking whether *the child's altered protein* works once its abundance
is normalised — the plan says in as many words that it is "an allele-function experiment, not a
recreation of the child's genotype". Reframing it as introducing a functional gene changes the
question being asked.

**"Modelar p53"** — p53 is not in this case's mechanism graph. **"mito_corr (milieu)"** does not
correspond to anything in our endpoint set. **CPTAC** is cancer proteomics; it holds no BUB1B
allele-function data and cannot validate EXP01/EXP02.

## 3. Two metrics that point the wrong way

**"≥10× hypothesis increase."** We maintain seven hypotheses and the system's value is that it
*refuses to collapse them* — including H05 and H06, which are kept specifically because they are
inconvenient for the favoured explanation. Rewarding hypothesis volume rewards the opposite
behaviour.

**"Tasa de acierto inicial > 30%" (hypotheses confirmed in phase 1).** Nothing can be confirmed
without a wet lab. A system measured on confirmation rate, with no way to confirm, will learn to
report confirmations.

## 4. Which tickets survive, and which do not

| # | Ticket | Verdict |
|---|---|---|
| 1 | API contract for `/simulate` | Defer — contract for a service whose inputs are undecided |
| 2 | Secure case ingestion (VCF/FHIR) | **Drop** — builds intake for data deleted in 21 days |
| 3 | Causal subgraph generation | Defer |
| 4 | Model compiler (ODE/SBML) | Defer |
| 5 | VCell/COPASI integration | Defer |
| 6 | **Sensitivity analysis** | **Keep — reshaped (see below)** |
| 7 | **Experiment prioritiser** | **Keep — reshaped** |
| 8 | Federated Beacon queries | Defer — no agreement, no partner, no time |
| 9 | Watch-state scheduler on PubMed webhooks | **Drop for now** — bypasses the grounded-extraction path intake is hardened around |
| 10 | Dashboard with dummy metrics | Drop — a dashboard of invented numbers is the failure mode this project is built against |

Tickets 6 and 7 are the real product. The rest is a platform.

## 5. What I would do with the 21 days instead

Analyse the decision rather than the cell. The question that blocks this case is not *what will
the cells do* — nobody answers that without the experiment. It is **which measurements would
change what we do**, which is a property of decision rules we already have, computable today with
no biology, no ODEs, no parameters, no VCell, and no patient data. Critically: **it survives the
deletion deadline**, because it operates on the plan, not on the genome.

I built it. It is committed as `tools/network/check_branch_reachability.py`, and it found a real
defect on the first run.

> **EXP01 does not measure `cell_death`.** Four branches that declare they apply to EXP01 — B08
> (hold the rescue conclusion), B09 (adverse hold), B10, and B16 (record a population change) —
> all require `cell_death` and therefore **cannot fire on EXP01 at all**.

EXP01 is the experiment that gates `PERMIT_DRUG_MECHANISM_PLANNING`. Give it a result where
expression is matched, all four functional readouts are normal, and viability and division rate
are both *decreased*, and the engine returns:

```
PROPOSED | PERMIT_DRUG_MECHANISM_PLANNING, STRENGTHEN_H01_FOR_MEASURED_ENDPOINTS
```

The population is dying and the system reads a success that unlocks drug-mechanism planning. The
identical result shape on EXP02, which does measure cell death, correctly fires
`RECORD_POPULATION_CHANGE` and `HOLD_PROGRESSION`. EXP03 has a smaller version of the same
problem: it omits `sirt2_activity` and `k668_acetylation`, so the two branches that ask whether
the mechanism explains a replicated signal cannot fire on the replication experiment.

That is the kind of result this approach produces: exact, checkable, no accuracy claim to defend,
and immediately actionable by a scientific lead. It took an afternoon. It needs no partner, no
sample, no consent, and no data that is about to be deleted.

### Proposed scope for the time that actually remains

1. **Branch reachability as a validator gate** — an experiment that silences its own safety holds
   cannot pass review. *Done as a tool; needs wiring into the gate.*
2. **Endpoint discrimination report** — per experiment, how many distinct decisions are reachable
   and which endpoints change the answer. (For EXP01: 128 outcome vectors, 3 distinct decisions.)
3. **Minimal discriminating sets** — handed to an assay scientist as a costing question, not a
   recommendation.
4. **Add `cell_death` to EXP01**, or record an explicit decision not to with the consequence
   stated. A plan change for the scientific lead, not an engineer.

Four items, no new infrastructure, no new dependencies, and all four outlive 24 October.

## 6. The honest framing for whoever decides

The simulator described here is a reasonable product for an organisation with several patients, a
data agreement, and a year. We have one child, no partner, and three weeks of data access left.

The binding constraint on this case has never been compute or modelling sophistication. It is
that **no laboratory has agreed to run anything**, and no clinician is attached. A mechanistic
simulator does not move that, and twelve weeks spent building one ends with a more elaborate
system and the same unresolved external milestone.
