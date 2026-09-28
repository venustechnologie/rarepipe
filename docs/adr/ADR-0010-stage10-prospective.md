# ADR-0010: Stage 10 as a local domain layer on the existing artifact pipeline

Status: accepted for P0 · 2026-09-28

## Context

PRD v1.0 asks for a versioned prospective planning layer on top of Rarepipe's evidence artifacts. It
has to work without model API access, replay deterministically, keep private data local, and never
let a synthetic or hypothetical result reach the real case. The repository already has these parts:
- immutable sealed run directories (`core.artifacts`);
- semantic digests (`core.digest`);
- restricted-field redaction;
- verified packages with an archive-path manifest (`core.package`);
- a pitch claim check;
- the NodeQuerySpec drafts from Stage 08.

## Decision

1. **One package, `rarepipe.stages.prospective`, owns the domain.** It holds the schemas
   (`model`), canonical digests and the version store (`store`), baseline import (`baseline`),
   `policy`, the rules engine (`rules`), the operations (`workflow`), `diff`/impact, `nodes`,
   `export`, `views`, the MVA `seed`, synthetic `fixtures` and the `demo`. The CLI (`cli`) is thin,
   and the same workflow functions serve as the internal service interface. A future HTTP layer
   calls them with the same idempotency keys and version preconditions.
2. **Storage is plain files, not a database.** Versions use exclusive create and are then made
   read-only. HEAD is replaced atomically. Observations are addressed by their content digest, so
   re-ingesting identical evidence returns the same identity. Execution state and the audit log sit
   beside the plan. The audit log records ids, kinds and reasons, never observation values.
3. **Canonicalization is `rarepipe-canonical-json-v1`.** It uses sorted keys, compact separators and
   UTF-8, with units and full numeric values kept in the content. There are two digests:
   - **Plan content digest.** It excludes lineage fields and reviews. A review approves exactly this
     digest, so any scientific edit invalidates the review.
   - **Review digest.** It also excludes the timing declaration recorded at freeze.

   Raw-byte hashes (package, raw result) are separate fields.
4. **Rules are code with pinned descriptors.** `rules.py` implements B00–B15 in Kleene logic.
   Each plan version pins `rules_version` and a serialized descriptor per branch. `replay`
   re-evaluates the pinned inputs and checks the result is identical.
5. **Views are static HTML generated from the same records as exports.** P0 needs no web server,
   works offline, and a download is exactly what is shown.
6. **Policy is enforced in the domain layer.** Separate permissions cover read, draft, scientific
   review, freeze, private export and external send. Agents may read and draft only. External send
   is disabled in this deployment, so `nodes.send` always refuses.

## Reused infrastructure and interface changes

- `core.artifacts.RunDirectory` seals exports. `core.package` builds the Stage 09 baseline
  packages.
- `track2.check-pitch` covers AT28.
- `mechanism.experiments.notation_aliases` covers AT20: frameshift labels are never expanded to
  stop aliases.
- New command group: `rarepipe prospective …`.
- `ValidationPlan` gained `model_requirements` and `not_authorized`, both additive.
- Hypothesis and analysis sessions gained `supersedes`, which lets a new session replace an older
  one without editing it.

## Consequences

- The real MVA plan cannot freeze until the owners in `docs/prospective.md` supply their inputs and
  the baseline is frozen. This is intended: the system does not manufacture answers.
- P1 work plugs into this package as adapters: `SimulationRun` adapters, node transports and
  quantitative forecasting. The contracts for all three exist now, so their outputs can never be
  typed as observations.
- The PRD's companion JSON fixtures were not supplied with the PRD. `fixtures.py` provides equivalent
  synthetic scenarios, every one labelled as a software test input.
