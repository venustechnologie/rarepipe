
# SIM03 — global sensitivity over the causal chain

You own **`src/rarepipe/stages/simulate/sensitivity.py`** and
**`tests/test_simulate_sensitivity.py`**.

Answer: which unmeasured parameter most determines whether the target moves — i.e. which
measurement would most reduce our uncertainty.

## Requirements

- Implement variance-based global sensitivity yourself with `numpy` (Sobol first-order and total
  indices via a Saltelli-style design, or Morris elementary effects). **Do not add SALib.**
- `rank(chain, *, target, master_seed, draws)` → ordered list of
  `(parameter_name, first_order, total, support_kind)`, highest influence first.
- Seed via `chain.seed_for`. Deterministic across processes.
- Report indices with the sample size they were computed from, and a convergence note: an index
  from too few draws is not an index. State the draw count beside every number.
- **Carry each parameter's `support` into the ranking.** A parameter that is both the most
  influential and `asserted_only` is the single most valuable measurement in the chain, and the
  report should say that in words, not leave the reader to join it up.
- Do not recommend measuring less. Output is a ranked uncertainty list for an assay scientist to
  cost, never a recommendation to drop an endpoint.

## Tests

At minimum: a synthetic chain with one dominant parameter ranks it first; indices are
reproducible across processes; the support kind travels with the ranking; and a chain where every
parameter is measured yields an explicitly empty ranking rather than noise.

Run `uv run pytest -q tests/test_simulate_sensitivity.py` and report the real exit status.
