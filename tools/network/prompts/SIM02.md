
# SIM02 — Monte Carlo engine over the causal chain

You own **`src/rarepipe/stages/simulate/engine.py`** and **`tests/test_simulate_engine.py`**.

Build a sampler that propagates parameter uncertainty through `mva_chain()` and reports a
distribution rather than a point estimate.

## Requirements

- `run(chain, *, target, master_seed, draws)` → an immutable result record holding: the sampled
  parameter draws' summary (per parameter: interval drawn from, support kind), the output
  distribution for the target, and the `PredictionClaim` from `chain.predict()` attached verbatim.
- Seed every stream through `chain.seed_for(label, master_seed)`. Two runs in **separate
  processes** with the same seed must produce byte-identical numeric output; write a test that
  spawns `subprocess` with differing `PYTHONHASHSEED` and compares.
- Propagate the sign of each edge. A path with an odd number of negative edges decreases its
  target.
- **The result record carries the verdict and the limiting edge.** A distribution whose path is
  capped at `ASSERTION_ONLY` must say so in the record, and your renderer must print it adjacent
  to any number. A number without its cap is not a result.
- Any rate with `value=None` is drawn from its `prior`. Never use the midpoint as an estimate, and
  assert that in a test.
- Report the fraction of draws in which the target moved in the predicted direction, **with its
  numerator and denominator**, and a Wilson interval. That fraction is a property of the assumed
  intervals, not a probability about the child — say so in the record's own text.

## Tests

At minimum: cross-process determinism; an unvalued parameter is never collapsed to a midpoint;
sign propagation; the verdict travels with the distribution; and a run against a chain whose path
is `CONTRADICTED` refuses to report a direction as favourable.

Run `uv run pytest -q tests/test_simulate_engine.py` and report the real exit status.
