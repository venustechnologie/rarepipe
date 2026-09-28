# Stage 10 integration

Use the current repository and `docs/prospective.md` as the interface authority. The attached guide describes `rarepipe prospective init | validate | preview | review-plan | freeze | ingest | review | diff | replay | export | views | demo`. It is documentation, not proof that the implementation has been inspected or its tests rerun.

## Discover before writing

Read applicable project instructions. Inspect `rarepipe prospective --help` and the relevant subcommand's help before composing commands. The supplied guide says commands accept `--workspace DIR`; follow the actual parser's placement and arguments. Do not invent `--json`, `--patch`, `--approve-as-agent` or an amendment command.

Read the actual plan schema, serializers, validators and storage functions under `src/rarepipe/stages/prospective/` if accessible. Capture the current plan ID, version, digest, baseline status and gap output. Keep a nonzero scientific-readiness result distinct from a command execution failure. If code is missing, prepare the proposed mapping and mark integration UNVERIFIED.

## Prepare work without altering gates

Write proposed scientific content to a new draft-output directory outside the immutable plan store. Use the user's/project's approved data location. Keep private proposals out of a public repository or export.

Link proposed edits to the existing field paths and expected version. The handoff proposal format is deliberately separate from native Rarepipe objects. Do not feed it to `ingest`, which is for observations, or assume there is a native proposal-import command.

If a supported draft-update API exists, describe the intended changes and validation steps. Applying approved edits must use the project's versioned process and expected-version checks. Never replace a frozen file, mutate its permissions, write directly into an exclusive-create store or use a synthetic demonstration to satisfy real-plan gates.

Run available validation and preview operations on the appropriate draft/demo context. Do not run `review-plan`, `freeze` or `review` as a human actor on the strength of these role documents. Do not generate a human signature or an authentic-looking review record for a real person.

## Preserve the operational model

Keep DRAFT/REVIEW_REQUIRED state when scientific requirements are incomplete. Keep baseline CANDIDATE status until a genuine reviewed release exists. A candidate may be used for drafting without being relabelled as frozen.

Treat the static HTML views as reports unless an actual interactive interface is implemented. Do not claim that an agent edited a plan by changing its generated HTML. Keep hypothetical scenarios out of the real observation store and preserve all old predictions.

## Reconcile and report

Report the original gap count, reviewed grouping, proposed edits, still-required evidence and actual validator output. Do not subtract drafted fields from the real unresolved count before accepted edits pass the real validator. Report source-specific test evidence: a captured test log, a developer message and a locally executed suite are different provenance.

Taskmaster is optional for recording this scientific work. Use bounded timeouts for provider-driven parsing; an expired CLI login is an authentication issue, not a scientific blocker. Do not read credentials or pretend to repair the developer's login. The documented manual-task route remains usable. Never relabel M5 complete to make the task list green.
