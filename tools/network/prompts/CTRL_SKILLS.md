
# CTRL-SKILLS — the seven scientific-reasoning skills for the Biological State Control Compiler

You own exactly these seven files, and nothing else:

```
.claude/skills/control-state-modeler/SKILL.md
.claude/skills/control-causal-dynamics/SKILL.md
.claude/skills/control-strategy-generator/SKILL.md
.claude/skills/control-falsification/SKILL.md
.claude/skills/control-observability-design/SKILL.md
.claude/skills/control-actuator-mapper/SKILL.md
.claude/skills/control-provenance-auditor/SKILL.md
```

Do NOT write or modify any Python. Do NOT commit. Read first, in this order:
`src/rarepipe/stages/control/__init__.py`, `provenance.py`, `state_space.py`, `dynamics.py`,
`controls.py`, `proposals.py`, `compiler.py`, `mva.py`, and `actuator_registry.py`. Every type,
field and value you mention must exist in that code. If you reference something that does not
exist, that is a defect.

## The architecture these skills serve

"Reason with agents. Prove with code." Skills propose; deterministic code gates. A skill can never
produce a result class (`CONTROL_SOLUTION_CANDIDATE` etc.) — `proposals.gate()` rejects any
payload containing one. The gate ASSIGNS the epistemic type; an agent-proposed relationship enters
as INFERRED_HYPOTHESIS with status at most "assumed"; an agent cannot assert a control is feasible;
an agent cannot approve a target. Write every skill so that it never asks the model to do these.

## Required structure of every SKILL.md

YAML frontmatter with `name` (the directory name) and `description` (when to use it, one paragraph).
Then these sections, each with real content — no placeholders:

- `skill_id`, `version` (start at 0.1.0)
- `scope` — what it reasons about, and explicitly what it does not
- `required_inputs` — which compiler objects or report fields it reads
- `reasoning_checklist` — numbered steps the model follows
- `allowed_tools` — read-only repository access and the compiler entry points it may run
  (`uv run python -c "from rarepipe.stages.control.mva import problem; ..."`); never network
  access to case data
- `forbidden_inferences` — concrete things it must never conclude (see below)
- `output_schema` — the exact shape it emits. For RELATIONSHIP, CONTROL and TARGET_CONSTRAINT
  proposals this is a `proposals.Proposal` whose `payload` validates as the corresponding type.
  For other roles it is an advisory finding a human reads; say plainly that advisory findings change
  nothing automatically.
- `uncertainty_language` — the words it uses for unknown, assumed, contradicted; it must keep the
  compiler's distinction between "unknown and blocking" and "unknown but irrelevant"
- `abstention_conditions` — when it must stop and say it cannot proceed
- `validation_hooks` — which deterministic module checks its output (e.g. `proposals.gate`,
  `compiler.compile_problem`, `observability.direct_gaps`)
- `benchmark_cases` — at least two concrete cases drawn from the MVA compilation or the proof gates
  (A–H in the PRD), each with the input, the correct behaviour, and the failure it should catch
- `retention_criterion` — the PRD says keep a specialised skill only if evaluation shows it catches
  failures or finds valid solutions a generic agent misses. State what that evaluation would
  measure for this skill, and state honestly that it has not been run.

## The seven roles

1. **control-state-modeler** — biological understanding → candidate variables, domains, and
   constraints. Must keep qualitative values qualitative (never map impaired/normal to numbers);
   must never put a mechanism (e.g. normal BubR1 abundance) into the target region.
2. **control-causal-dynamics** — proposes state-transition relationships. Must propose
   UNKNOWN_FUNCTION when evidence does not determine a function, rather than a guessed table. Must
   never fill `REL_BUBR1_ABUNDANCE_FUNCTION`.
3. **control-strategy-generator** — proposes alternative routes across repair, stabilization,
   compensation, bypass, suppression, replacement, rewiring (`controls.RouteClass`). Proposes
   biological control variables, never drugs. Benchmark: it is the source of `C_REPLACE_FUNCTION`.
4. **control-falsification** — tries to invalidate a candidate route: missing confounders,
   selective loss (H06), unsafe transients. Benchmark: a route that lowers aneuploidy by killing
   aneuploid cells must be flagged.
5. **control-observability-design** — what measurements distinguish models and verify outcomes.
   Must treat safety variables as needing direct measurement (a model's prediction that cell death
   will not move does not certify safety). Benchmark: the EXP01 `cell_death` gap; EXP03's missing
   `sirt2_activity` and `k668_acetylation` — it must list the three scientific options and choose
   none.
6. **control-actuator-mapper** — maps a biological control to `actuator_registry.ActuatorClass`
   entries, only after a route exists. Must never produce a drug list before a control route
   exists, never recommend, and always carry each actuator's own evidence cap.
7. **control-provenance-auditor** — checks claims do not exceed their evidence. Benchmark: the two
   PMIDs marked UNVERIFIED (no retrieval record) must not support any claim stated as verified;
   relabelling `different_agent` evidence as stronger support must be caught.

## Forbidden inferences that apply to every skill

No treatment recommendation. No dose. No claim of clinical efficacy. No invented threshold,
parameter, rate or probability. No promotion of a simulated prediction to an observation. No
contact with the child, family or patient organisations. No exact patient variant, position or
identifier anywhere in a skill file.

When done, list the seven files and, for each, which of its benchmark cases you checked against the
real compiler output by running it. Report honestly any you could not check.
