# Stage 03 — Baseline Causal-Hypothesis Generation

> The first stage permitted to produce biological hypotheses — and it produces none of
> its own. It asks a mature solver (Exomiser) what it considers the strongest causal
> hypotheses under four explicitly declared assumptions, and records exactly why.

```bash
uv run rarepipe baseline \
  --normalized-case /secure/work/MVA_001/normalization/RUN_.../normalized_case.private.json \
  --exomiser-home /resources/exomiser/exomiser-cli-15.1.0 \
  --exomiser-data /resources/exomiser/data \
  --output /secure/work/MVA_001/baseline \
  --max-heap 7g
```

| option | purpose |
|---|---|
| `--profile PROFILE_A` (repeatable) | Run a subset of the matrix. Default: all four. |
| `--max-heap 7g` | Java heap for the solver. Exomiser documents ~8 GB for a ~4.4M-variant genome. |
| `--timeout-hours 6` | Per-profile timeout. |
| `--dry-run` | Write each profile's job configuration without running the solver. |
| `--case-root DIR` | Case mounted elsewhere; the VCF is still SHA-256 verified against upstream. |

Exit codes: `0` complete (with or without warnings) · `3` blocked · `2` usage error.

## The profile matrix

Exactly two things vary. Everything else is identical across the four runs.

| profile | HPO set | VCF FILTER treatment |
|---|---|---|
| A — standard | phenotypic-abnormality terms only | `failedVariantFilter` (non-PASS dropped) |
| B — filter-sensitive | phenotypic-abnormality terms only | no `failedVariantFilter` (non-PASS permitted) |
| C — phenotype-sensitive | all supplied terms | `failedVariantFilter` |
| D — inclusive | all supplied terms | no `failedVariantFilter` |

**`analysisMode: PASS_ONLY` is constant in all four.** It is Exomiser's memory strategy
(retain only variants passing Exomiser's own filter chain); `failedVariantFilter` is the
step that reads the VCF's FILTER column. Conflating them would silently change the
experiment, so a test asserts the only difference between A and B's analysis config is
the presence of that one step.

Non-PASS variants that are permitted keep their labels — `MQ40` stays `MQ40`. Nothing is
rewritten to PASS, and no variant is dropped from the source file.

## Declared assumptions

Assumptions live in the *analysis*, never written back into the case record:

| id | statement |
|---|---|
| `ASSUME_HPO_DESCRIBE_PROBAND` | The supplied HPO terms are used as features describing the child. The NormalizedCase still says `polarity: unspecified`. |
| `ASSUME_ANALYSIS_ROLE_PROBAND` | The single sample is designated proband for this analysis. Not evidence about family structure; no pedigree is fabricated. |
| `ASSUME_NO_REMM_NONCODING_SCORING` | REMM is omitted (its tabix file is not provisioned) and non-coding effects are filtered, making this a coding-sequence baseline. |

## What the solver is given — and never given

Given: the source VCF unmodified, the selected HPO terms, the genome assembly, and the
analysis configuration above. **Never given:** a disease name, a gene panel, seed genes,
or any candidate list. A test greps the generated job files to keep it that way.

The step order follows Exomiser's shipped `preset-genome-analysis` (phenotype prioritiser
first, then `priorityScoreFilter`), whose own comments state this "dramatically reduce[s]
the time and memory required to analyse a genome".

## RawCandidateSet

`RawCandidateSet` v1.0.0 records **what the solver said**, not what this system believes.
Ranks and scores are the solver's, unaltered; rarepipe reranks nothing and promotes nothing.

- **Compound-heterozygous candidates are pairs**: `is_variant_pair`, two
  `contributing_variants`, and `phase.status: unresolved` with the note that two
  heterozygous variants in one gene are a *candidate configuration*, not proof of trans.
- `contributing_variants[].source_filter_status` carries the VCF label verbatim.
- `variant_ref` is a stable per-run reference (`sha256(contig:pos:ref:alt)[:12]`) so a later
  stage can ask about specific variants — e.g. whether a pair shares PGT/PID — without
  coordinates leaving the private artifact.
- Variant coordinates, HGVS, genotypes, rsIDs and sample labels are **private-only**.

## Stability across profiles

The point is not a single ranking but whether it survives the two unresolved decisions:
top-1/5/10/20 gene overlap per profile pair, compound-het gene overlap, rank movement,
genes appearing **only** when non-PASS records are permitted, genes appearing **only** with
the wider HPO set, and a verdict (`stable` / `partially_stable` / `unstable` / `insufficient`).
Disagreement is a finding, not a failure.

## Failure is a result

A blocked stage is a scientific outcome, and each blocker names the smallest missing
capability rather than working around it:

| code | meaning |
|---|---|
| `SOLVER_OUT_OF_MEMORY` | The host cannot analyse this case as supplied at this heap size. |
| `SOLVER_REJECTED_INPUT` | The solver cannot consume the case — the message names contig renaming / multiallelic decomposition / reference binding as the candidate missing capability. **The VCF is never rewritten here.** |
| `SOLVER_UNAVAILABLE` / `SOLVER_DATA_UNAVAILABLE` | Nothing was run; no results are invented. |
| `UPSTREAM_NOT_READY` | Stage 02 reported a required capability as not ready. |
| `SOURCE_ASSET_CHANGED` | The VCF no longer matches the digest recorded upstream. |

If the solver rejects the input, that is what would justify an input-adaptation stage —
discovered, not assumed.

## Provisioning (once, networked; analysis runs offline)

```bash
brew install openjdk@21
curl -LO https://github.com/exomiser/Exomiser/releases/download/15.1.0/exomiser-cli-15.1.0-distribution.zip
curl -LO https://g-879a9f.f5dc97.75bc.dn.glob.us/data/2602_phenotype.zip   # 13.5 GB
curl -LO https://g-879a9f.f5dc97.75bc.dn.glob.us/data/2602_hg38.zip        # 23.6 GB
unzip 2602_*.zip -d exomiser-cli-15.1.0/data
```

The case run performs no network access; the solver is a child process inheriting the
caller's sandbox (`sandbox-exec ... (deny network*)` on macOS).

Pinned in every artifact: Exomiser version and jar SHA-256, hg38 and phenotype data
versions, Java version and max heap, the analysis/properties config digests (computed over
a canonicalised job so they describe the *analysis*, not the run's paths), the
NormalizedCase digest, and the source VCF SHA-256.

## What the real solver actually does (measured, Exomiser 15.1.0 / data 2602)

Verified by `tests/test_baseline_solver.py` against a provisioned installation, not assumed:

| question | observed behaviour | consequence |
|---|---|---|
| multiallelic records | split into separate allele rows | no decomposition stage needed |
| numeric contig names (`15`) | accepted; output contigs normalised to numeric | this case's `chr`-stripped naming needs no adaptation |
| decoy contigs | variants silently dropped from output | MVA_001's ~43k decoy records never reach analysis |
| `analysisMode: PASS_ONLY` | does **not** exclude non-PASS VCF records | the B/D profiles genuinely test filter sensitivity |
| solver's TSV `FILTER` column | reports Exomiser's own status (`PASS` for survivors) | source labels must be read back from the VCF — otherwise an `MQ40` variant is recorded as PASS |
| mode of inheritance in TSV | abbreviated `AD`/`AR`/`XD`/`XR` | a recessive candidate with two heterozygous contributing variants *is* the compound-het configuration; searching for `COMP_HET` finds nothing |
| CLI shape | `--sample` + `--analysis` (flat script) + `--vcf/--assembly`; Spring config via `-Dspring.config.location` | the v13/14 combined job file is rejected; `--assembly` wants `GRCh38`, not `hg38` |

Measured cost on a 9 GB laptop, 5,012,204-record WGS VCF: **~7–16 minutes per profile, peak ~1.9 GB RSS**.
The phenotype-first step order prunes genes before variant work, so genome-scale analysis is far
cheaper here than Exomiser's 8 GB genome guidance suggests.

## Retention

| artifact | class |
|---|---|
| native solver outputs (annotated tables, JSON, logs) | `delete_required` |
| RawCandidateSet (full ranked output) | `delete_required_review` |
| small top-N candidate findings | `retainable_after_review` |

Native outputs live outside the sealed run directory under `<output>/native/<run_id>/` and
are recorded by relative path + SHA-256. Do not assume any of it may be published.

## Deliberately not done

- No reranking, no manual promotion, no "this gene sounds relevant".
- No disease name or gene panel supplied to the solver.
- **PGT/PID read-backed phase is not consulted.** Until candidate pairs exist there is no
  reason to analyse 770k local phase assignments; phase adjudication for specific pairs is
  a later stage.
- No leaderboard submission. Hidden-label feedback is a scarce resource and is not spent
  on a first baseline.
- No variant decomposition, left-alignment, contig renaming or reference binding.

## Testing

Offline tests use a fake solver that reacts to the two varied decisions, so profile
construction, ingest, pair representation, FILTER-label preservation, sensitivity
comparison, failure classification, privacy and idempotence are all covered without the
37 GB bundle. Tests that genuinely need the solver — multiallelic handling, `chr`-stripped
contig names, decoy contigs, real PASS vs non-PASS behaviour — live in
`tests/test_baseline_solver.py` and run when provisioned:

```bash
export RAREPIPE_EXOMISER_HOME=/resources/exomiser/exomiser-cli-15.1.0
export RAREPIPE_EXOMISER_DATA=/resources/exomiser/data
uv run pytest -q tests/test_baseline_solver.py
```
