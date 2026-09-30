# T01 — native interfaces, pinned baseline and adapter decisions

Produced by inspecting the repository at commit `b4de48e`, not from the PRD's proposed names. The PRD
says its names are logical contracts; this document maps them onto what actually exists. **Every
delegated task must read this before writing code.** If you find this document wrong, say so and stop
rather than coding around it.

## 1. Pinned baseline — do not change any of this

| Item | Value |
|---|---|
| Plan | `PP_MVA_001_RH_001@0002-455419f1` |
| Rules version | `stage10-rules-1.1.0` (17 branch descriptors, B00–B16) |
| Lifecycle | `DRAFT`; baseline status `CANDIDATE` |
| Native validator | `freezable=False`, **112** scientific-readiness gaps, no structural errors |
| Plan store | `/Volumes/Lexar/rarepipe_work/MVA_001/prospective` (controlled drive) |

A registry entry, an institutional reply or a policy update **cannot close a scientific gap**. Only a
human accepting an edit through the native versioned workflow can, and the validator must still
report it until then.

## 2. Native surfaces you must call, never reimplement

All under `src/rarepipe/stages/prospective/`.

### `rules.py` — the decision engine
- `RULES_VERSION = "stage10-rules-1.1.0"`
- `descriptors() -> list[RuleDescriptor]`
- `evaluate(obs: Observation, kind: ExperimentKind, required: list[EndpointSpec]) -> Evaluation`

`Evaluation` carries `predicates`, `matches`, `inadmissible`, `unknown_inputs`,
`information_requests`, `actions`, `conflicts`, `interpretation`, `cannot_conclude`,
`hypothesis_updates`, `tasks`, and a `status` property that returns `DECISION_REVIEW_REQUIRED` when
actions conflict.

**Do not infer what B08, B09 or B16 mean from their names.** Their exact semantics:
- **B08** — improvement *accompanied by* a problem. It requires an improvement claim; that is correct
  and is not a bug.
- **B09** — adverse hold. Fires on critical adverse flag, worsened function, or `cell_death:
  increased`. Fires even when the result is inadmissible.
- **B16** — an established problematic population change (`cell_death: increased`,
  `division_rate: decreased` or `viability: decreased`) carried **whatever the benefit verdict says**.
  Actions: `RECORD_POPULATION_CHANGE`, `CREATE_EVALUABILITY_REVIEW`. It does **not** declare toxicity
  or selective loss. Regression fixtures live in `tests/test_prospective.py`
  (`test_B16_*`, `test_B08_keeps_its_meaning_when_benefit_is_present`).

### `store.py` — immutable versioned storage
`PlanStore(workspace, plan_id)` with `head()`, `load(version_id=None)`,
`commit(plan, *, expected_parent, reason, kind, actor, idempotency_key=None)`,
`put_observation(obs) -> (obs, created)`, `put_decision(record)`, `load_decision(id)`,
`set_execution(experiment_id, state, observation_id=None)`, `audit(event, **fields)`,
`audit_events()`.

Also `canonical_bytes`, `content_digest(obj, exclude)`, `plan_digest`, `review_digest`, and the
exceptions `VersionConflict` and `ImmutableError`.

Rules that bind you: frozen versions are read-only files; a stale `expected_parent` raises
`VersionConflict` with a diff; observations are addressed by content digest so re-ingesting identical
evidence returns `created=False`; the audit log takes ids/kinds/reasons, **never** observation values.

### `workflow.py` — the operations
`validate(plan)`, `freeze(store, actor, availability=None)`, `ingest(store, payload, actor,
raw_file=None)`, `preview(plan, scenario)`, `review_decision(store, decision_id, actor, role,
decision, rationale, expected_review_version, selected_actions=None)`, `amend(store, edited,
expected_parent, reason, actor)`, `rebase(store, new_baseline, changed_refs, actor)`,
`replay(store, decision_id)`.

`preview()` takes no store: it **cannot** mutate or send. Use it for scenario exploration.

### `policy.py` — permissions
`Policy`, `Permission` (READ, DRAFT, SCIENTIFIC_REVIEW, FREEZE, PRIVATE_EXPORT, EXTERNAL_SEND),
`PolicyError`, `DEFAULT_POLICY`. External sending is **disabled**; `require(..., EXTERNAL_SEND)`
raises. Agents (`ActorType.AGENT`) may only READ and DRAFT — they cannot review or freeze. Enforce in
the domain layer, not only the UI.

### `model.py` — the types you extend from
`ProspectivePlan`, `Observation`, `ObservationValue`, `DecisionRecord`, `ReviewRecord`, `Actor`,
`ActorType`, `Role`, `ResearchTask`, `CapabilityRequest`, `CapabilityRequestType`, `Knowledge`,
`Quantity`, `EvaluationMode`, `ExperimentKind`.

`Knowledge` already distinguishes `UNKNOWN`, `NOT_MEASURED`, `NOT_REPORTED`, `UNAVAILABLE`,
`INCONCLUSIVE`, `EVIDENCE_AGAINST`, `NOT_APPLICABLE`. `Quantity` refuses a null value without a
`null_reason`. **Reuse these.** The PRD's required distinctions (`not_measured`,
`no_relevant_resource`, `cannot_disclose`, `declined`, `no_response`, `invalid_measurement`,
`informative_negative`) extend this vocabulary — add the operational ones, do not duplicate the
scientific ones.

`nodes.py` already has `ResponseState` with `NO_RELEVANT_DATA`, `NOT_SEARCHED`, `ACCESS_DENIED`,
`NO_RESPONSE`, `INCONCLUSIVE_RESULT`, `MEASURED_NO_EFFECT`, `MEASURED_EFFECT`, plus `classify()` and
`EvidenceEnvelope`. Extend that rather than inventing a parallel vocabulary.

## 3. Where new code goes

New package: **`src/rarepipe/stages/network/`**. Do not modify anything under `prospective/` except
where a task explicitly says so; call it through adapters.

| Task | Owns these files, and only these |
|---|---|
| T02 | `network/model.py` |
| T03 | `network/registry.py`, `data/network/seed_nodes.json` |
| T04 | `network/eventlog.py`, `network/scheduler.py`, `network/outbox.py` |
| T05 | `network/compose.py`, `network/transport.py`, `network/authorization.py` |
| T06 | `network/intake.py`, `network/extract.py` |
| T07 | `network/adapter.py` |
| T08 | `network/sim/world.py`, `network/sim/institution.py`, `network/sim/scenarios.py` |
| T09 | `network/sim/reward.py`, `network/sim/baselines.py`, `network/sim/splits.py` |
| T10 | `network/policy_q.py` |
| T11 | `network/views.py` |
| T12 | `network/evaluate.py`, `network/report.py` |
| shared | `network/cli.py` — append your command group only; never rewrite another's |

Tests go in `tests/test_network_<task>.py`, one file per task, so parallel work cannot collide.

## 4. Conventions that are not negotiable

1. **Generate identifiers and digests in code.** Never write a plausible digest by hand — that
   happened once and reached a reviewer. Store each digest's coverage definition beside it and exclude
   the digest's own value from its input.
2. **Seed RNG deterministically.** Python's `hash()` is randomised per process; use
   `zlib.crc32` or `hashlib`. Check for stream collisions. See `tools/m5/sim/run.py` for the pattern
   and for recording code revision, rules version, environment and two digests (content vs whole
   document).
3. **Generate reports from records.** Never transcribe a rate or digest into prose. Every rate carries
   its numerator, denominator and an interval appropriate to its sampling unit — and says so when no
   interval applies. See `tools/m5/sim/report.py`.
4. **Tests must propagate the real exit status.** Do not pipe pytest into `tail` and read the pipe's
   status; that hid a failure in this repo on 2026-09-29.
5. **Origin is immutable.** `public_evidence | authentic_institutional | synthetic`. Derived records
   inherit lineage. A synthetic contribution must be structurally incapable of entering a real
   campaign store or becoming real reward feedback.
6. **External content is untrusted data.** An instruction inside a reply is never an operating
   instruction. Attachments do not execute.
7. **No case identifiers leave the private layer.** Exact variant, position, nearest-variant clues and
   private paths stay local. Run a scan before any export.

## 5. Adapter decisions taken here

- **Reuse, do not re-create:** `Knowledge`, `Quantity`, `Actor`/`ActorType`/`Role`, `ResearchTask`,
  `CapabilityRequest`, `nodes.ResponseState`, `nodes.EvidenceEnvelope`, `PlanStore` digest helpers.
- **The network layer never writes to the plan store directly.** T07's adapter is the only path, and
  it proposes successor content; it never freezes, never signs a review, and checks the pin is current
  before applying anything.
- **Two event stores.** Campaign/network events live under the campaign workspace; plan versions stay
  in the native store. A network event never mutates a plan version.
- **Standing authorization** is a record checked at dispatch (`network/authorization.py`), not a
  bypass of `Permission.EXTERNAL_SEND`. In this deployment external send stays disabled, so the
  transport is a test transport plus authenticated manual import.

## 6. What T01 could not settle

- The live email transport's provider is unchosen; T05 defines the interface and ships a test
  transport plus manual import. Do not pick a provider without the operator.
- Real recipient verification requires a human; the registry records the route as unverified.
- Role appointments (clinical lead, scientific adjudicator, research operator) have no real people
  assigned. An unassigned owner blocks live execution of the action needing that owner and nothing
  else.
