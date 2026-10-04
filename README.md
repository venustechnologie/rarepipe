# rarepipe

> **Reason with agents. Prove with code.**
>
> Agents may propose biological states, mechanisms, alternative routes, models, controls,
> actuators and experiments. Deterministic mathematical code must evaluate constraints,
> reachability, consistency, observability, provenance and safety wherever those concepts have
> formal semantics. Missing biological knowledge must remain an explicit unknown. The system must
> never manufacture quantitative semantics merely to complete a computation.
>
> **We do not ask only what an intervention will do. We specify what biology must do, then solve
> for how to make it happen.** — see [the control compiler design](docs/control/DESIGN.md)

A reproducible, stage-by-stage pipeline for working toward resolving difficult rare-disease cases.
It is being discovered bottom-up: stages are added only when a real case shows they are needed.

```
CASE → INTAKE → NORMALIZATION → BASELINE ANALYSIS → (…)
        ▲ stage 01 (frozen)  ▲ stage 02      ▲ stage 03
```

Every stage consumes versioned artifacts and produces immutable, versioned artifacts with provenance.
No stage re-inspects raw directories behind the previous stage's back.

## Stage 01 — Case Intake

```bash
uv sync
uv run rarepipe intake --case-root /secure/mva_case --case-id MVA_001 --output /secure/work/MVA_001/intake
```

Produces `CaseManifest` (private + sanitized JSON), an intake report, a run log, and a checksum seal.
No interpretation, no transformation, no network. See **[docs/intake.md](docs/intake.md)** for outputs,
the schema contract, the issue taxonomy, security assumptions, and limitations.

## Stage 02 — Case Input Normalization

```bash
uv run rarepipe resources fetch-hpo --resources /resources/rarepipe          # once, networked
uv run rarepipe resources fetch-assembly-report --resources /resources/rarepipe
uv run rarepipe normalize --manifest <intake run>/case_manifest.private.json \
  --resources /resources/rarepipe --output /secure/work/MVA_001/normalization
```

Consumes the CaseManifest (never the case directory) and produces `NormalizedCase`: canonical contig
identities, a complete-stream VCF characterization (FILTER distribution, variant classes, genotype
fields, phase availability), HPO identity normalization against a pinned ontology release, and
readiness per capability. No transformation, no interpretation, no network.
See **[docs/normalize.md](docs/normalize.md)**.

## Stage 03 — Baseline Causal-Hypothesis Generation

```bash
uv run rarepipe baseline --normalized-case <norm run>/normalized_case.private.json \
  --exomiser-home /resources/exomiser/exomiser-cli-15.1.0 --exomiser-data /resources/exomiser/data \
  --output /secure/work/MVA_001/baseline
```

Asks Exomiser for candidate causal hypotheses under four declared profiles (HPO set ×
VCF FILTER treatment) and produces `RawCandidateSet` plus a stability comparison across
those profiles. Compound-heterozygous candidates are variant pairs with unresolved phase.
rarepipe reranks nothing and supplies no disease name or gene panel to the solver.
See **[docs/baseline.md](docs/baseline.md)**.

## Development

```bash
uv run pytest -q                                              # synthetic fixtures only
uv run rarepipe fixtures --output /tmp/rarepipe-fixtures      # inspect them by hand
uv run rarepipe schema --output schemas/case_manifest.schema.json
```

Environment: Python 3.12 (`.python-version`), dependencies pinned in `uv.lock`, htslib via pysam wheels.

**Never develop or test against real controlled data. Never commit real manifests or reports.**
