# Stage 10 — prospective experiment and decision plans (operator guide)

Stage 10 turns an unresolved hypothesis into explicit conditional forecasts, proposed experiments,
interpretable outcome branches and accountable next actions. Each new observation updates a
reviewable case state, and nothing ever rewrites what was predicted beforehand.

It does not establish a treatment, run an experiment, prescribe anything or simulate the child. No
state or action in it reaches a patient: the furthest the engine goes is a translational-review task.

Every screen answers one question: **what do we expect, under which assumptions, what observation
would change our view, and what happens next?**

## Commands

All commands take `--workspace DIR` (plan stores live under it) and default to the MVA plan
`PP_MVA_001_RH_001`. Nothing is sent anywhere, and every command works without network access.

| Command | What it does |
|---|---|
| `prospective init --baseline PKG` | Verifies every manifest entry of a Stage 09 package, pins a `BaselineRef` and seeds the MVA plan as `DRAFT`. It is idempotent: the same package gives the same version. |
| `prospective validate` | Reports structural, scientific-readiness, provenance and policy errors separately. Each gap names the field, why it matters and its owner. |
| `prospective preview --scenario JSON` | Evaluates hypothetical inputs. It writes nothing, sends nothing, and labels every output as a hypothetical scenario. |
| `prospective review-plan --decision APPROVE_FOR_FREEZE --role ...` | Records a human review of the plan's exact current content. |
| `prospective freeze --actor ... [--availability JSON]` | Checks the freeze gates (FR-040), then writes an immutable version. It refuses while gaps remain. |
| `prospective ingest --observation JSON [--raw FILE]` | Stores the immutable result and checks units, denominators, model identity and synthetic separation. It then evaluates the rules and writes a review proposal. |
| `prospective review --decision DR_… --outcome … --expected-review-version N` | Records a human interpretation. If the decision was reviewed since you opened it, you get a conflict. An accepted interpretation creates a successor plan version. |
| `prospective diff OLD NEW` | Lists scientific, editorial and operational changes. |
| `prospective replay --decision DR_…` | Re-evaluates the pinned inputs and exits non-zero unless the result is identical. |
| `prospective export --output DIR [--visibility public] [--private-terms FILE] [--mode remove\|reject]` | Applies the allowlist and a free-text scan, then writes a sealed export with its manifest. |
| `prospective views --output DIR [--scenario JSON…]` | Writes the doctor, editor, result-review, scenario and audit views as static HTML. |
| `prospective demo --baseline PKG` | Runs the §19.1 completion demonstration from start to finish. |

## States

- **Plan:** `DRAFT → REVIEW_REQUIRED → READY_TO_FREEZE → FROZEN`, then `SUPERSEDED` or `WITHDRAWN`.
- **Frozen versions:** read-only files. Any change creates a successor that names its parent and the
  reason for the change. If results were already available when an edited forecast or threshold
  changed, the successor is labelled `POST_RESULT_AMENDMENT` for the affected forecasts. The original
  scoring stands.
- **Execution:** `NOT_STARTED`, `RESULTS_PENDING`, `RESULT_REVIEW_REQUIRED` and so on. Execution
  state lives in `execution.json` beside the plan, never inside a frozen version.
- **Timing:** a hash proves which bytes you have, not when you saw a result. Unless timestamp
  evidence is recorded, a freeze is `TEMPORAL_STATUS_UNVERIFIED`, and no preregistration is claimed.

## The rules engine

The engine evaluates branches B00–B15 over an observation vector, using TRUE, FALSE and UNKNOWN.
Missing required data is UNKNOWN, never zero.

- **Integrity and quality gates:** B00 (identity or provenance unverified) and B01 (precision,
  controls or a required readout) decide whether a scientific conclusion is admissible at all.
- **Inadmissible results:** conclusions that would have matched are listed as inadmissible, not
  dropped. The exception is B02, which only keeps matched-abundance function unresolved; it
  still applies.
- **Adverse flags:** a critical adverse flag (B09) always creates a hold-and-review task, even on an
  unverified result.
- **Conflicts:** every match is kept. When the proposed actions contradict each other (for example,
  "propose replication" alongside "hold progression"), the record becomes
  `DECISION_REVIEW_REQUIRED`. No branch wins by precedence.
- **Endpoints stay separate:** checkpoint activation, checkpoint silencing, alignment and
  missegregation are distinct endpoints. More protein alone is an intermediate finding. Fewer errors
  alongside more death or slower division is held as possible selection (B08).

## What the real MVA plan needs before it can freeze

Run `validate` to see the current list. It is owned work, not a software problem:

| Owner | Blocks |
|---|---|
| Research operations and scientific lead | Real experiment readiness: whether an exact-allele or complete-genotype model is available and permitted |
| Assay scientist | Scientific freeze: assay methods, comparators, validity criteria and effect thresholds |
| Statistician and assay scientist | Scientific freeze: the §8.4 analysis fields (experimental unit, replication, effect, uncertainty and the rest) |
| Research operations | Scientific freeze: a result-availability declaration |
| Scientific lead, assay scientist and statistician | Scientific freeze: human reviews of the exact content |
| Engineering | Scientific freeze: rebasing onto the intended frozen baseline, because a `CANDIDATE` baseline cannot be frozen |

The system allows planning while these are unresolved. It never fills them in to make a view look
complete.

## Data boundaries

- The public plan carries only sanitized baseline fields. Model requirements refer to private
  constructs through opaque `private:` references, which resolve only inside the authorized
  environment and are removed from every public export.
- Pass exact-variant terms to `export --private-terms` from a local file. Tests use synthetic secrets
  only.
- Node queries are `DRAFT_UNSENT`. "No relevant data", "access denied", "not searched" and "no
  response" are operational outcomes. None of them can become an observation or `MEASURED_NO_EFFECT`.
