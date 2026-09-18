# Stage 05 — prospective Track 1 validation

One query against a hidden clinical answer key, made after everything upstream is frozen.
The stage generates a submission; a person submits it.

```
rarepipe export track1 \
  --candidate-run    <baseline run>/raw_candidate_set.private.json \
  --adjudication-run <adjudication run>/adjudicated_hypothesis.private.json \
  --official-scorer  <path>/evaluation.py \
  --output           <work>/track1
```

Outputs, in a sealed run directory:

| file | visibility | what it is |
|---|---|---|
| `track1_submission.csv` | **controlled** | the predictions. The only artifact with exact variant identity; goes to the evaluator only. |
| `track1_methods.md` | shareable | the methods report, generated from provenance. No coordinates. |
| `submission_manifest.json` | shareable | the sanitized `Track1SubmissionPackage`: rows, rule, EPCR schedule, checks, digests. |
| `validation_snapshot.json` | shareable | the frozen upstream state, hashed. |

## What the stage guarantees

* **Row 1 is the adjudicated hypothesis**, as one compound-heterozygous row with its alleles in genomic
  coordinate order. Submitting a pair proposes a configuration; it does not assert established trans phase.
* **Rows 2–10 come from a rule fixed before generation** — cross-profile robustness from Stage 03,
  configurations keyed by variant set, subsets of already-emitted rows dropped. No hand reranking.
* **EPCR is a documented, strictly decreasing schedule**, distinct per rank so the evaluator's F-max sweep
  can separate every row. The artifact states in as many words that these are rank-preserving surrogates,
  not calibrated probabilities.
* **The file is validated twice** before it can be uploaded: against the documented schema, and by the
  challenge's own public `evaluation.py` run locally, which never sees the answer key. An invalid package
  exits non-zero and prints `NOT_VALID_DO_NOT_SUBMIT`.
* **The snapshot pins what was known beforehand** — upstream run ids, their semantic digests, the source
  commit and whether the tree was dirty — and asserts `created_before_ground_truth_query`.

## After submitting

```
rarepipe record-validation --package-run <run> --match FULL|PARTIAL|NONE \
  --response <captured response>.txt --rank-points ... --f-max ... --output <work>/validation
```

This writes an `ExternalValidationResult` and names the branch the case moves into: a full match ends
causal-variant discovery and moves the work to mechanism; a partial match localises the error to one
allele; no match triggers error attribution, not parameter tuning. The result is recorded as evidence
about the case. Nothing upstream is modified by it, and a further submission requires an independently
justified pipeline change.
