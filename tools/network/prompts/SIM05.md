
# SIM05 — contradiction checks over the hypothesis set

You own **`src/rarepipe/stages/simulate/contradict.py`** and
**`tests/test_simulate_contradict.py`**.

For each hypothesis, find the evidence that would invalidate it — and report when none has been
looked for.

## Requirements

- Read the case's hypotheses from `rarepipe.stages.prospective.seed` (H01–H07). Do not restate
  them; read them.
- For each hypothesis report: its stated `falsification` / `distinguished_by` where one exists,
  which chain edges would have to hold or fail for it to survive, and whether any recorded
  evidence currently opposes it.
- **A hypothesis with no falsification criterion is a finding**, not a blank. Report it as
  unfalsifiable-as-stated.
- **H01 and H02 are mutually exclusive and both live.** The report must not pick a winner. Where
  two hypotheses are alternatives, say what single measurement would separate them — for this
  case, the chain already identifies `bubr1_abundance -> bubr1_residual_function`.
- Cross-reference `CausalEdge.support`: a hypothesis resting only on `asserted_only` or
  `different_agent` edges is reported as such, with the edge named.
- Never conclude. The output is "here is what would kill this idea, and whether anyone checked",
  not a ranking of likelihood.

## Tests

At minimum: every seeded hypothesis appears; H01 and H02 are both reported live with the
separating measurement named; a hypothesis with no falsification criterion is flagged rather than
silently passed; and a hypothesis supported only by a `different_agent` edge is reported with that
edge named.

Run `uv run pytest -q tests/test_simulate_contradict.py` and report the real exit status.
