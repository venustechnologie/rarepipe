# For developers

This page is for someone joining tomorrow. It covers getting the suite green locally, what CI
actually checks, the conventions that are enforced rather than merely encouraged, and how to add
something without breaking the discipline the rest of the project depends on.

Read [`02-architecture.md`](./02-architecture.md) first if you have not — this page assumes you
know roughly where things live.

---

## 1. Setup

Dependencies are locked with [uv](https://docs.astral.sh/uv/). Python is pinned to **3.12** by
`.python-version`; `pyproject.toml` requires `>=3.12`.

```bash
uv sync --all-extras --dev
```

That is the whole setup. There is no database, no service to start, no credentials to configure.
The CLI entry point is [`src/rarepipe/cli.py`](../../src/rarepipe/cli.py):

```bash
uv run rarepipe --help
```

Runtime dependencies are deliberately few: `typer`, `pydantic` v2, `pysam`, `pyyaml`, `pypdf`,
`alphagenome`. The dev group is one package — `pytest`.

### What you cannot run from a fresh clone

Be aware of this before you go looking for a bug that is not there:

| Not in the repo | Consequence |
|---|---|
| `research/` (gitignored — full texts, verbatim quotes, imported sessions) | Stage 08 and Stage 09 runs are **not reproducible** from this checkout alone |
| `*.private.json`, every genomic extension, Track 1 prediction CSVs | No case run can be replayed |
| Exomiser distribution and its multi-gigabyte data bundles | Stage 03 needs `RAREPIPE_EXOMISER_HOME`; the offline suite uses a fake solver instead |
| The challenge's own `evaluation.py` | One Stage 05 test skips unless `RAREPIPE_TRACK1_SCORER` is set |

Those are the 8 skipped tests. Everything else runs offline with no case data.

---

## 2. Running the tests the way CI runs them

```bash
uv run pytest -q -m "not integration"
```

As of this writing that is **1024 passed, 8 skipped** — 1032 collected across 61 test files, about
four minutes on a laptop.

One honest note about that command: **no test in the repository currently carries the `integration`
marker**, so the filter is a no-op today. It is kept because CI's comment explains the intent
("integration-marked tests need an environment this runner does not have") and because the marker
is the right place to put anything that needs the controlled drive. Plain `pytest` gives the same
1032 today — do not assume it always will.

To run one subsystem while iterating:

```bash
uv run pytest -q tests/test_synthesis_gates.py tests/test_synthesis_invariants.py
```

Note that `tests/test_evidence_repair.py` takes around 30 seconds on its own. That is deliberate:
`recompile.observe()` imports roughly fifteen modules and runs five full compilations plus the causal
chain, reading **nothing** cached. A cached value would make the exercise meaningless.

---

## 3. The CI gate

[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs 14 steps on every push and pull
request. Three install, then:

| Step | What it does |
|---|---|
| Test suite | `uv run pytest -q -m "not integration"` |
| Network invariant scan | `tools/network/check_invariants.py` |
| Control compiler invariant scan | the same scanner, `--package src/rarepipe/stages/control` |
| Architecture map is not stale | regenerate + `git diff --exit-code` |
| Realization maps are not stale | same, two documents |
| Capability gap report is not stale | same |
| External capability reports are not stale | same, two documents |
| Evidence repair deltas are not stale | same, two documents |
| Decision branch reachability | advisory — runs with `\|\| true` |
| Endpoint discrimination | advisory report |
| Contingent route map is valid and not stale | `compile_route_map.py --check` |

Two rules are stated in the workflow's own header, and both exist because the failure happened:

1. **pytest's exit status is the job's status.** It is never piped into `tail`, `head` or `grep` — a
   pipe once hid a real failure. The static scanner checks for this too.
2. **The controlled drive is never required.** Every check runs offline, with no case data.

### The six staleness checks are the interesting part

Everything under `docs/control/` is **compiler output, not prose.** Six CI steps regenerate a
committed document and diff it against the checkout. Editing a generated Markdown file by hand
passes human review and then fails CI — which is the intended behaviour, because it means a verdict
cannot be changed by editing the document that reports it.

To regenerate after a legitimate change:

```bash
uv run python tools/control/compile_mva_synthesis.py
uv run python tools/control/compile_mva_realization.py
uv run python tools/control/compile_mva_gaps.py
uv run python tools/control/compile_mva_external_gaps.py
uv run python tools/control/compile_evidence_repair.py
uv run python tools/control/compile_route_map.py
```

`compile_route_map.py --check` validates and compares **without writing**, which is what CI uses.

### The static scans, and why they are not tests

[`tools/network/check_invariants.py`](../../tools/network/check_invariants.py) reads source rather
than behaviour. The reason is pointed: **the author of a task writes both the code and its tests**,
so a test suite cannot be the only check on a convention. Five checks, each tied to a defect that
actually occurred here:

| Check | The defect it caught |
|---|---|
| No `hash()` as a seed source | Process-randomised, so two runs disagreed while both claimed a fixed seed |
| No hand-written `sha256:` literal | One plausible-looking fake digest reached a reviewer |
| Hidden world-truth names confined to the simulation files | Latent truth leaking into a learner |
| No `pytest \| tail` | A pipe hid a real test failure |
| No `model_copy(update=)` on lineage-enforcing records | Would bypass validators that enforce record lineage |

The scanner prints its own `not_checked` list — including "whether the science is right" and
"anything requiring the code to run". A scanner that publishes its limits is more useful than one
that implies it has none. Note that it defaults to `src/rarepipe/stages/network`; CI invokes it
twice, so **other stage packages are not covered by that scan.**

---

## 4. Conventions that are actually enforced

Not a style guide. Each of these will fail something if you break it.

**Artifacts are immutable.** A run writes into `<output>/.incomplete-<run_id>/`, creates each file
with exclusive-create (`mode='x'`), chmods everything to `0444`, writes `SHA256SUMS`, and only then
atomically renames the directory into place. `RunDirectory.open()` raises `FileExistsError` if the
final path exists. A crashed run never looks finished, and **re-running produces a sibling, never
an edit.**

**Data problems are facts, not exceptions.** Nothing raises past a stage boundary for a problem with
the data. A stage collects `Issue` records with one of four severities — `BLOCKER`,
`ACTION_REQUIRED`, `WARNING`, `INFO` — and the stage's status is *derived* from the worst severity
present. Only invalid invocation raises. The exit contract is `0` ok, `2` usage error, `3` blocked,
so an operator script can tell "I called this wrong" from "the case cannot proceed".

**Tool functions return friendly errors.** Corollary of the above: a stage function that raises into
the pipeline on bad data is a bug.

**The private/sanitized split is schema-driven.** A field declared `restricted()` carries
`json_schema_extra={"restricted": True}` and exists only in the `*.private.json`.
`clear_restricted()` walks the model recursively and resets every tagged field. **Adding a sensitive
field means tagging it** — there is no second list to keep in sync, and that is the entire design.
Every report renderer asserts `visibility == "sanitized"` before it writes a line.

**Nothing run-specific inside a semantic digest.** `semantic_digest()` hashes what an artifact
*says*, excluding how long it took to say it. `volatile_fields()` is the shared guard. Its docstring
records that this broke twice — Stage 02 digested VCF stream time, Stage 03 digested wall-clock and
peak RSS. Exactly two upstream-pointer paths may legitimately contain a run id.

**Sorting is load-bearing, not cosmetic.** Iterating a set of string tuples gives a different order
per process under hash randomisation, which silently breaks content digests and the cross-process
reproducibility invariant. **Any new collection that reaches an output must be sorted.** Seeds come
from CRC32, never Python's `hash()`.

**Enumeration caps fail loudly.** `CANDIDATE_LIMIT = 64`, `STATE_LIMIT = 2**18`, `max_depth <= 6`,
`COMPOSITION_LIMIT = 25_000`. All of them **raise** rather than truncate — because a silently
truncated search reports "no architecture found" in exactly the same words as an exhaustive one.

**Closed vocabularies.** Enums are `StrEnum` and closed on purpose, so a proposer cannot invent a
category and smuggle a claim in with it. Models are frozen pydantic with `extra="forbid"`.

**English only**, in identifiers, strings and comments.

---

## 5. Mutation testing: the discipline that matters most

**A gate that passes on its first run proves nothing.** It might be checking the thing you meant,
or it might be inert. The only way to tell is to break it deliberately and require it to go red.

This has caught real defects in this repository. Three worth knowing:

- **A dependency check that looked sufficient.** A branch-level `dependency_tested` check in the
  route map seemed right. The mutation **survived** — an efficacy-named outcome rode in on the flag.
  The fix was a per-outcome `dependency_outcomes` list.
- **A provenance test that gave a false pass.** Two cases asserted as "allowed" had never been
  blocked in the first place, because bare residue positions matched no pattern at all. Breaking the
  guard exposed *two* pre-existing bugs: bare positions were ungated, and the private cross-check
  ran *after* the pattern scan instead of first.
- **The mutation that was itself inert.** The causal chain has two identical evidence-required
  guards, on `Parameter` and on `CausalEdge`. The first attempt broke the wrong one and the test
  still passed. The control was never inert — the mutation was. Check *which* guard you broke.

One practical warning, learned expensively: **restore from a copy, not `git checkout`.** A
`git checkout` during mutation testing clobbers uncommitted edits elsewhere in the tree and leaves
untracked files behind. Copy the file aside, mutate, verify red, copy back, and verify the diff is
clean before committing.

### Test properties, not conclusions

During the evidence repair, five tests had to be rewritten, and **two of them had asserted the
historical conclusion directly** — that the case's direct route *is* contradicted. Those tests would
have made the correct answer unreachable. They now assert the property on *constructed* chains, so
the invariant holds while the conclusion stays free to move.

Three others asserted counts that legitimately changed. **A count is not a property.** If your test
breaks because the science moved, the test was wrong.

---

## 6. Adding a capability

Which path you take depends on what you are adding.

### A new stage

Follow the shape every existing stage shares, because it is uniform and the uniformity is what
makes the gate work:

1. `model.py` first — the contract, as frozen pydantic with closed enums. Mark private-only fields
   `restricted()`. **This is the file a reviewer reads to learn what your subsystem believes**, so
   write it as that statement.
2. `schema.py` — export the JSON Schema with a versioned `$id`, and commit it under `schemas/`. A
   drift test fails if code and committed schema diverge, with the regeneration command in the
   failure message.
3. `stage.py` — orchestration. Consume **only** a sealed upstream artifact, never the case
   directory. Collect issues; derive status; never raise on data.
4. `report.py` — render from the sanitized artifact, and assert that.
5. Wire a command into [`cli.py`](../../src/rarepipe/cli.py), importing your stage **lazily inside
   the command body** so startup stays fast and an import failure stays local to one command.
6. `tests/test_<name>.py` — TDD. Write it first, watch it fail, then implement until green.

### A control-compiler layer

Do not add reachability semantics of your own.
[`src/rarepipe/stages/control/reachability.py`](../../src/rarepipe/stages/control/reachability.py)
owns safety filtering, all-interleaving exploration and unknowns-fixed-per-trajectory. Read it
before you change what a verdict means. Add your layer's own vocabulary in a `kinds.py`, and make
the report's model validator **refuse any headline its own contents do not support** — that pattern
is used in every existing layer and it is what stops "no result by prose".

### A generated document

Write a compiler under `tools/control/`, render Markdown into `docs/control/`, and **add a staleness
step to CI.** A generated document without a staleness check is just prose that looks authoritative.

---

## 7. Private case data, day to day

The rule is simple and it is not negotiable: **controlled data stays in its approved environment,
and only sanitized artifacts come back.**

In practice:

- Real controlled data runs locally under
  `sandbox-exec -p '(version 1)(allow default)(deny network*)'`.
- Only sanitized artifacts are read back — **never `*.private.json`.**
- No genomic rows, sequences, sample identifiers or case-specific raw data go to any LLM API,
  annotation API, analytics endpoint, telemetry service, error reporter or external log.
- Never paste genome-scale case content into an agent conversation.
- `.gitignore` is part of the safety story rather than housekeeping: `/secure/`, `/work/`, `/out/`,
  `*.private.json`, every genomic file extension, Track 1 prediction CSVs and the whole `research/`
  directory are excluded — **specifically because this repository is expected to become public.**

A subtlety that catches people: **"sanitized" is not "anonymous".** The sanitizer's own note says
so. Internal aliases remain and the artifact still describes one real individual's case structure.
Both private artifacts additionally carry source sample labels and HPO identifiers, so they are
controlled material and belong in the deletion plan — along with `<output>/.cache/checksums.json`.

And one thing to hold carefully: the *domain* the case's missense allele sits in is public biology.
The **residue is not**, and it must never appear in a sanitized field. Directness grades live only
in restricted fields for a specific reason — a nearby published variant plus a position would
localise the child's residue.

---

## 8. Where the governance guards live in code

| Guard | File | What it does |
|---|---|---|
| Disclosure boundary | [`stages/adjudicate/disclosure.py`](../../src/rarepipe/stages/adjudicate/disclosure.py) | `check_query` refuses outbound queries carrying case identity. The **private-residue cross-check runs first**, on every residue-shaped token, before any pattern scan |
| Public-residue exception | same file | `PublicResidueProvenance` — the only licence for a residue token to leave, attested **per token, per source**, verbatim in committed snapshot text under `data/literature` |
| Approval gate | same file | `approval_gate()` has **no success path.** Exact-variant external querying is unimplemented by design |
| Therapeutic-intent filter | [`stages/mechanism/retrieve.py`](../../src/rarepipe/stages/mechanism/retrieve.py) | Second, independent gate on retrieval. Perturbation vocabulary is deliberately *allowed*; words of intent to treat are refused |
| Therapy-filter lift | [`stages/discovery/lanes.py`](../../src/rarepipe/stages/discovery/lanes.py) | `check_intervention_query` — the one place the therapy filter is lifted, and **only** that filter. The case-identity guard still applies |
| Proposals gate | [`stages/control/proposals.py`](../../src/rarepipe/stages/control/proposals.py) | Assigns the epistemic type; strips agent-claimed feasibility; rejects any payload carrying a result-class word |
| Role policy | [`stages/prospective/policy.py`](../../src/rarepipe/stages/prospective/policy.py) | Agents get read + draft only, and can never sign a review or freeze |

Two rules about these guards:

**A refusal is a bug to fix or a decision to escalate — never something to work around.** If
`check_query` refuses a query you believe is legitimate, the question is whether the guard is wrong
(fix the guard, with a test) or whether the query really does carry case identity (change the
query). Loosening a pattern to get past it is the one move that is not available.

**The guards fail closed and are deliberately broad.** The bare-residue pattern also matches
ordinary strings like a `C57` mouse strain, so legitimate gene-level queries sometimes get refused.
Tightening in that direction was a deliberate choice **after a bare residue slipped through
ungated.** Treat a false refusal as cheaper than a false release.

---

## 9. Your first contribution

A walkthrough that exercises the real discipline without needing case data. Suppose you want the
route-map validator to enforce a new structural rule.

**1. Write the failing test first.**

```bash
# tests/test_control_skills.py — add a test asserting your rule
uv run pytest -q tests/test_control_skills.py -k your_new_rule
```

Watch it fail. If it passes before you have written any implementation, the test is not testing
what you think.

**2. Implement it** in [`tools/control/compile_route_map.py`](../../tools/control/compile_route_map.py),
inside `validate()`. Keep it a property of the structure, not an assertion about this case's answer.

**3. Mutation-test your own gate.** Copy the file aside. Break the check deliberately — invert the
condition, or weaken it the way a hurried author would. Re-run:

```bash
uv run pytest -q tests/test_control_skills.py -k your_new_rule   # must be RED
```

If it stays green, your gate is inert. Fix it, then restore from your copy and confirm
`git diff` is clean.

**4. Regenerate and check the document.**

```bash
uv run python tools/control/compile_route_map.py --check
```

**5. Run the whole suite and both scans** the way CI will:

```bash
uv run pytest -q -m "not integration"
uv run python tools/network/check_invariants.py
uv run python tools/network/check_invariants.py --package src/rarepipe/stages/control
```

**6. Commit.** Commit finished work directly to `main` and push — shipping is the point. Never
`git add -A` while an agent may be writing files; stage the paths you actually changed.

If your change moved a generated document, the regenerated file is part of the commit. If it moved a
scientific conclusion, say so in the commit message — that is the one thing a reviewer cannot
reconstruct from the diff.

---

## Where to go next

- **The detailed per-subsystem map** —
  [`architecture/module-reference.md`](./architecture/module-reference.md): inputs, outputs, key
  modules, invariants, gotchas and status for every subsystem.
- **The rules you are working inside** —
  [`05-evidence-discipline.md`](./05-evidence-discipline.md) and
  [`11-governance-and-safety.md`](./11-governance-and-safety.md).
- **What is already known to be imperfect** —
  [`docs/POTENTIAL_IMPROVEMENTS.md`](../POTENTIAL_IMPROVEMENTS.md). It states what is true today,
  what would be better, and what it would cost, so you can decide rather than rediscover.
- **Where the open work is** — [`13-next-steps.md`](./13-next-steps.md).
- **Per-stage operator guides** — [`docs/intake.md`](../intake.md),
  [`docs/normalize.md`](../normalize.md), [`docs/baseline.md`](../baseline.md),
  [`docs/mechanism.md`](../mechanism.md), [`docs/track1.md`](../track1.md),
  [`docs/intervention.md`](../intervention.md), [`docs/discovery.md`](../discovery.md),
  [`docs/track2.md`](../track2.md), [`docs/prospective.md`](../prospective.md).

---

> A gate that passes on its first run proves nothing. A refusal is a bug to fix or a decision to
> escalate, never something to work around. Test properties, not conclusions.
