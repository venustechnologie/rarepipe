
# SIM04 — first-class store for negative results

You own **`src/rarepipe/stages/simulate/negatives.py`** and **`tests/test_simulate_negatives.py`**.

A negative result is evidence. This project already distinguishes refusal, no-resource, QC
failure, measured-null and informative-negative in `network/model.py`
(`AdditionalResponseState`); reuse that vocabulary, do not invent a parallel one.

## Requirements

- A record type for "this did not work", carrying: what was tried, what was measured, the
  distinction between **a measured null** and **a failure to measure**, the evidence reference,
  and `origin` (`public_evidence` / `authentic_institutional` / `synthetic`).
- `NegativeStore` with append-only semantics and content-addressed ids. A stored negative is never
  edited; a correction is a successor record referencing its predecessor.
- **A measured null must not be representable as a non-result, and vice versa.** Enforce it in the
  type, and attack it in a test.
- An `informative_negative` additionally claims validated controls and adequate power. The
  constructor must refuse that classification unless both are recorded.
- Seed the chain's contradicted edge into the store: the closest nicotinic-acid experiment was
  null and reported no measurement of the chain (`mva.EV_NIACIN_NULL`, which is marked UNVERIFIED
  — carry that marker, do not drop it).
- A query interface: "what has already been tried against this target, and what was the result?"

## Tests

At minimum: append-only enforcement; a measured null cannot be stored as a non-response;
`informative_negative` refused without controls and power; the UNVERIFIED marker survives storage
and retrieval; and a synthetic negative cannot be returned as authentic evidence.

Run `uv run pytest -q tests/test_simulate_negatives.py` and report the real exit status.
