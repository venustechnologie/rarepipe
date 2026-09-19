# Stage 07 — intervention logic

Between a supported mechanism and a drug search sits a layer most workflows skip: *what would an
intervention actually have to do?* This stage builds it, names no medication, and consults no drug
database.

```
rarepipe intervention --mechanism-run <stage 06 run> --research <workspace> --output <work>/intervention
```

Offline. Refuses to run at all on a `MECHANISM_BLOCKED` dossier.

## What it produces

* **MechanisticAxis** — a level at which the disease could be engaged, with support recorded *per
  level* (human experimental, curated, class-level, exact-variant experimental, computational). A
  prediction can support a working hypothesis without becoming one.
* **InterventionPoint** — a biological state, a role (root cause / proximal / intermediate /
  downstream phenotype / biomarker), an explicit **direction**, the rescue evidence that makes the
  direction causal, measurable endpoints drawn from the dossier's own assay inventory, a
  reversibility claim, and whether it **depends on the unresolved exact-allele mechanism**.
* **ForbiddenEffect** — directions expected to worsen the disease process. Derived from the
  mechanism graph and functional evidence only. A computational prediction says what an allele may
  do; it never establishes which therapeutic direction is dangerous.
* **NegativePredictionEvidence** — a model that did not light up. It deprioritizes an axis and
  states in its own fields that it does not establish absence. Axes move to `DEPRIORITIZED`, never
  `REJECTED`, and each carries the conditions that would reopen it.
* **InterventionSearchSpec** — what Stage 08 may search for: a biological effect with a direction,
  acceptable and **disallowed** mechanisms, expected rescue readouts, exact-allele dependency, and
  the pediatric constraint.
* **ActionOutcome** — what each research action actually bought, including the ones that bought
  nothing. That trace is how we eventually learn which actions are worth taking.

## Rules the gate enforces

`INTERVENTION_LOGIC_READY_FOR_APPROVED_DRUG_SEARCH` requires at least one supported point with an
explicit direction, causal rescue evidence, measurable endpoints, and a search spec built from it.
A supported point missing a direction or an endpoint blocks the stage: a target without a direction
is how a search finds a compound that pushes the wrong way.

## Two general concepts that came out of using the pipeline

* **`independence_group`** on evidence. The AVI score is dominated by AlphaMissense, which the case
  already held — so those are not two independent witnesses. Evidence sharing a source model shares
  a group, and a composite records what it `embeds`.
* **Negative predictions** are first-class. Dumping them into `contradicting_evidence` would have
  let a silent model look like a refuting experiment.
