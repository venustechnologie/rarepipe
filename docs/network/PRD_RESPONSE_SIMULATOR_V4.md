# Response to the simulator PRD, fourth version

Scheduling is set aside at Xavier's instruction, and so is effort estimation — build capacity is
not the constraint here. This version drops dates itself and says "stop calculating deadlines,
focus on scientific quality", which I agree with. So this is about what to build and how it would
be judged, nothing else.

I built two pieces of it rather than reviewing again. Results below.

---

## 1. The one objection that is not about scheduling

**The proposed success metrics cannot be computed on this case's endpoints.**

Section 6 proposes measuring the simulator with Virtual Cell Challenge metrics — PDS/DES, and
"correct identification of differentially expressed genes", with a target above 0.7. Those metrics
are defined over **transcriptomic perturbation prediction**: given a perturbation, predict an
expression vector across genes, and score it against the measured vector.

This case's endpoints are not expression vectors. Every one of them is a **categorical ordinal
judgement** from a fixed fourteen-value vocabulary:

```
improved | unchanged | worsened | increased | decreased | present | absent
matched  | not_matched | normal  | impaired  | partial   | yes     | no
```

EXP01 measures checkpoint activation, checkpoint silencing, chromosome alignment, missegregation,
expression comparability, viability, division rate, kinetochore localization, PP2A-B56
recruitment. There is no gene list, so there are no differentially expressed genes to get right,
and PDS/DES has no definition over this data. The metric is not hard to hit; it is undefined.

This matters because it hides a real trade. To make VCC metrics applicable you would have to
**redesign the endpoint set into transcriptomics** — and the three-valued decision engine, which
is the actual asset here, operates on exactly these categorical readouts. Swapping them out does
not extend the system; it replaces the part that works. If that trade is wanted, it should be made
deliberately and in the open.

**"Entrenar y validar el simulador con los datos MVA/BUB1B reales"** has the same shape of
problem. The case's controlled data is genotype and phenotype. EXP01 has never been run, so there
are no functional-assay outcomes in it to train or validate against. Nothing in the case data
tells you what BubR1 abundance or missegregation did under an intervention.

**What *is* available as ground truth:** published SAC and BUB1B perturbation experiments. That is
a real, honest benchmark — and it is exactly what stage 2 of the roadmap already proposes
("replicar lógicas conocidas del checkpoint"). That stage is sound as written. It is stages 3 and
6 that attach metrics the data cannot support.

## 2. What I built, and what it found

### Endpoint discrimination

Enumerate the reachable outcome vectors over an experiment's endpoints, run each through the real
rule engine, and report which endpoints change the decision.
`tools/network/endpoint_discrimination.py`.

| Experiment | outcome vectors | distinct decisions | cannot change the decision |
|---|---:|---:|---|
| EXP01 | 512 | **3** | viability, division_rate, kinetochore_localization, PP2A-B56 |
| EXP02 | 20,736 | 36 | **total_aneuploidy** |
| EXP03 | 2,592 | 26 | none |

**EXP01 can reach only three distinct decisions.** Nine endpoints, 512 possible result patterns,
three answers. Worth knowing before anyone books instrument time.

**`total_aneuploidy` is read by no rule at all.** It sits in EXP02's endpoint list and the string
appears zero times in the rule engine. Aneuploidy is what mosaic variegated aneuploidy *is* — the
defining phenotype — and however it reads, the decision does not change. Either a branch should
read it, or the plan should record why measuring it informs something other than this decision.
That is a question for the scientific lead, not an engineer.

### Branch reachability

A branch declares which experiment kinds it applies to and which inputs it needs. Nothing checked
that the experiment measures them. `tools/network/check_branch_reachability.py`.

**EXP01 does not measure `cell_death`**, so four branches that declare they apply to it cannot
fire: **B08** (hold the rescue conclusion), **B09** (adverse hold), **B10**, and **B16** (record a
population change). Give EXP01 a result where expression is matched, all four functional readouts
are normal, and viability and division rate are both decreased, and the engine returns:

```
PROPOSED | PERMIT_DRUG_MECHANISM_PLANNING, STRENGTHEN_H01_FOR_MEASURED_ENDPOINTS
```

The population is dying and it reads as a success that unlocks drug-mechanism planning. The same
result shape on EXP02, which does measure cell death, correctly fires `RECORD_POPULATION_CHANGE`
and `HOLD_PROGRESSION`.

The two findings are the same finding from two sides: viability and division rate are inert on
EXP01 *because* the branches that would read them need an input EXP01 does not carry. Adding
`cell_death` takes EXP01 from 3 reachable decisions to **6**. Viability and division rate stay
inert even then, which is a second question for the scientific lead.

EXP03 has a smaller version: it omits `sirt2_activity` and `k668_acetylation`, so B06 and B11 —
the two branches asking whether the mechanism explains a replicated signal — cannot fire on the
replication experiment.

Both tools have tests that pin the findings as they currently stand, so fixing the plan fails them
loudly and they get updated deliberately rather than silently drifting.

## 3. What I would keep from this PRD, and build next

The roadmap's six stages are the best structure of the four documents. Three parts are
straightforwardly good and I would build them:

- **"Compilador de Simulaciones" as a DSL for the causal chain** — `BUB1B → BubR1 → mitotic
  complex → phenotype`. Expressing the chain explicitly, separately from any solver, is valuable
  on its own: it makes the chain inspectable and diffable, and it is the artefact a scientist can
  argue with. Build the DSL and the chain before any ODE engine.
- **Contradiction agents** — "for each hypothesis, find the evidence that invalidates it." This is
  already the behaviour our hypothesis set encodes by keeping H05 and H06 alive on purpose.
  Formalising it is a real improvement.
- **"Repositorio de resultados negativos"** — a first-class store for what did not work. We
  already distinguish refusal, no-resource, QC failure, measured-null and informative-negative;
  giving negatives their own home is the right instinct and almost free from here.

Stage 2 as written — a POC that reproduces known checkpoint logic — is the right first simulator
goal, because its success condition is checkable against published behaviour rather than against
outcomes that do not exist.

## 4. Three small corrections

- **Blockchain for provenance** (section 5, "opcional") would be a downgrade. We already have
  content-addressed digests over canonical serialisations, an immutable versioned store that
  refuses to rewrite a frozen version, and an append-only audit log. Blockchain adds operational
  cost and removes nothing we currently trust by other means.
- **"HEAPSGA"** (section 9) does not resolve to anything I can identify. If a confidential-compute
  enclave is meant, name the actual technology, because the mitigation depends on which one.
- **Simulation output must not become case evidence.** Stage 4 connects the simulator to the
  knowledge base; our origin model makes a synthetic record structurally unable to enter a live
  campaign store or become real feedback, and the constructor raises if you try. That invariant is
  the thing stopping a model's output from becoming a finding about a child. Keep simulated
  results in their own lineage, clearly labelled, and let a human promote anything.

## 5. Ordering

Stage 5 is the hospital partner. Everything in stages 3 and 6 depends on it — held-out validation
needs real results, federation needs an institution with data — and it is the single item in this
roadmap that no amount of agent capacity can produce. Engineering cannot substitute for it, and it
is the only stage with that property.

I would move it first and run it in parallel with stage 2, because the outreach list for it
already exists: nine groups, the exact question for each, and drafted messages, waiting on a
human to decide whether to send. That is the one action that changes what is possible here.

## 6. What I will start on, unless redirected

1. The causal-chain DSL from stage 2, with the MVA chain expressed in it.
2. A checkpoint-logic POC whose success condition is reproducing published SAC behaviour.
3. The negative-results store.
4. Contradiction checks over the existing hypothesis set.

Items 2 and 3 are the ones I would delegate in parallel. None of them needs a partner, a sample, or
any data we do not already hold — and none of them requires pretending we can validate predictions
against results that do not exist.
