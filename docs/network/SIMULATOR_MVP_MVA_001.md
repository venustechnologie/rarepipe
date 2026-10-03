# Scoped MVP — in-silico design exploration for MVA_001 only

Scopes down `deep-research-report.md` to this one case. Written 2026-10-03 against commit
`8e4b0ef`. Nothing here needs a new service, a new ontology stack, or a 12-month programme.

## 1. The finding that drives the scope

The incoming PRD proposes a predictive patient-specific simulator, validated against held-out
assays, whose output includes a **recommended reduced assay set** (§225, example: *"measuring only
BubR1 abundance and viability"*).

I ran that example against our own decision engine. Of the 13 branches that apply to EXP02:

| | Full 11-endpoint set | PRD's reduced set |
|---|---|---|
| Evaluable branches | 13 | 4 |
| **B08** improvement accompanied by death/less division → hold rescue | evaluable | **blocked** |
| **B09** adverse direction → hold progression | evaluable | **blocked** |
| **B16** established population change, whatever the benefit verdict | evaluable | **blocked** |
| **B14** endpoints conflict → show disagreement | evaluable | **blocked** |
| B05–B07, B10, B11 (every branch that could record a positive result) | evaluable | **blocked** |

The surviving four are B00 (bad provenance → quarantine), B01 (failed QC), B12 (translational
hold) and B15 (unmodelled observation). In other words: that reduced set can report that the data
is valid and that we cannot interpret it. It cannot reach a conclusion, and it removes **every
guard that catches a false positive**.

B16 needs `cell_death` **and** `division_rate`. Viability alone does not substitute — which is
exactly what EXP02's own recorded interpretation already says: *"Viability alone does not exclude
selection: death and division are recorded with their denominators."*

So **"reduce wet-lab experiments by ≥50%" is out of scope**, and would be out of scope even with a
validated simulator. It is not a cost saving on this case; it is the removal of the specific
readouts that stop an apparent rescue being believed.

## 2. What else cannot be done for this case, and why

| PRD item | Why not here |
|---|---|
| ≥0.7 Pearson / ≥0.8 AUC vs held-out assays; 80% of variance | **MVA_001 has zero experimental outcomes.** There is nothing to correlate against. The metric is unmeasurable, not merely unmet. |
| "Held-out test set: formalize expected outcomes for EXP01/EXP02" (§222) | EXP01 and EXP02 have not run. Expected outcomes would be written by us and then scored against — a synthetic fixture standing in for a real result. This project already rejects that for T14/A25; the same rule applies here. |
| Quantitative kinetics (NAD→SIRT2 rate, BubR1 degradation) | The single most consequential parameter is whether this child's variant leaves BubR1 functional. That is **unresolved** — it is the H01-vs-H02 question the whole plan is blocked on. A simulator would have to assume it, then return it as a result. |
| Beacon/Phenopackets/DUO/EHDS registration, Kubernetes, 99.5% uptime, 10–100 concurrent patients | Governance and scale for a platform. One case, one operator, offline, on a controlled drive. |
| Watch-state RSS monitoring, €1.05M, 8 FTE, 12 months | Not what one case needs to move. |

None of this says the platform PRD is wrong as a product vision. It says **it cannot be validated
on a case with no outcomes**, and validating it against invented outcomes would be worse than not
building it.

## 3. What is worth building, and it is already nearly here

The one idea in that PRD that transfers cleanly is **sensitivity analysis** (§71) — but inverted.

Not *"predict what the experiment will show."*
Instead: **"across everything we do not know, can this experiment answer the question at all?"**

That needs no rate constants, no held-out outcomes, and no claim of accuracy. It runs on the
decision engine we already have: `workflow.preview(plan, scenario)` takes hypothetical inputs,
cannot write or send, and returns the same `DecisionRecord` a real observation would. The forecast
mode is already `QUALITATIVE_CONDITIONAL`.

### Four deliverables

**D1 — Outcome-space map.** Enumerate the coherent combinations of endpoint categories for EXP01
and EXP02, run each through `preview()`, record which branches fire and which actions result.
Output: the complete table from *possible result* → *pre-committed reading*, generated, with a
digest. This is exhaustive coverage of the decision table, not prediction.

**D2 — Endpoint necessity, not reduction.** For every candidate endpoint subset, report which
branches become unevaluable — the table in §1, generalised. It answers "can we run fewer assays?"
with "here is precisely what you stop being able to conclude." It never recommends a reduction.
Dropping an endpoint that disables B08, B09 or B16 is reported as a **safety loss**, not a saving.

**D3 — Discrimination check.** For each outcome in D1, does it separate H01 from H02? And from
H03, H04, H06? Report which outcomes are diagnostic and which leave everything unresolved. This
is the real open question: *as designed, can EXP01/EXP02 settle residual function?* If a large
share of the outcome space is non-diagnostic, that is a design finding worth having before anyone
is asked to run it.

**D4 — Robustness over the named unknowns.** We do not have numeric parameters, but we do have 112
named unresolved fields, 70 of which carry a value waiting on a named input. Sweep those
**categorically**, and report which design decisions hold across all of them versus which flip.
Feed the result to the work packages that are already waiting — in particular **M5_W001**
(`NEEDS_DESIGN_DECISION`: which expression-linkage option to develop first).

### Explicitly out of scope

ODE/PDE solvers · predicted effect sizes · confidence intervals on biology · any accuracy claim ·
any recommendation to drop an assay · patient-level prediction · a second case.

## 4. Acceptance criteria

1. D1 enumerates the outcome space and **every** branch in the engine's vocabulary appears at least
   once, or the uncovered branches are named as a finding.
2. D2 reproduces §1's table from code, and a test asserts that any subset disabling B08, B09 or
   B16 is reported as a safety loss.
3. D3 reports the diagnostic share of the outcome space with its numerator and denominator.
4. D4's output maps to real work-package ids; no new gap is closed by it. **Preparation does not
   close a gap** — only a human accepting an edit through the native workflow does, and the
   validator keeps reporting 112 until then.
5. Two fresh-process runs agree on the science digest, as the existing evaluation runner already
   requires.
6. Nothing writes to the plan store. `preview()` takes no store by design; keep it that way.
7. No output states or implies a predicted biological result, an effect size, or a treatment.

## 5. Cost

Days, one person, no new service. It reuses `rules`, `workflow.preview`, the scenario harness, the
seeded plan, and the report generator — all of which exist and are tested. There is no cloud spend
and no new dependency.

## 6. The honest summary

The platform PRD describes a product. This describes what can be learned about **this child's
experiment** with what is actually known, which is: not what the result will be, but whether the
experiment as designed is capable of producing an answer — and which readouts cannot be removed
without losing the ability to disbelieve a good-looking one.
