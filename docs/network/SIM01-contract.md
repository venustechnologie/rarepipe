# SIM01 — contract for the MVA causal-chain simulator

Read before writing any code in `src/rarepipe/stages/simulate/`.

## What is already built, and must not be re-created

`simulate/chain.py` and `simulate/mva.py` exist and are tested (`tests/test_simulate_chain.py`).
They are the core design decision; build on them, do not reimplement.

- `Support` — what kind of evidence stands behind an edge: `human_experimental`,
  `model_experimental`, `different_agent`, `different_compartment`, `class_level`,
  `computational`, `asserted_only`, `contradicted`.
- `Strength` / `STRENGTH` — how far a prediction may lean on each kind. Lower binds the path.
- `Parameter` — a quantity *or* an explicit unknown. A parameter with no value **must** carry a
  `prior` interval; the constructor refuses otherwise. Never substitute a midpoint for an unknown.
- `CausalEdge` — one causal claim, with `sign`, `support`, `evidence_ref`, `scope_note`, `caveat`.
- `CausalChain.predict(source, target)` → `PredictionClaim`, capped by the weakest link on the
  best route, and reporting `contradicted_alternatives` so a null result on a shorter route stays
  visible.
- `CausalChain.seed_for(label, master_seed)` — `zlib.crc32`, stable across processes. Use it.

`mva_chain()` is the case's chain. Its six unmeasured rate constants are
`k_niacin_to_blood_nad`, `f_blood_to_intracellular`, `k_nad_to_sirt2`, `k_sirt2_deacetylation`,
`k_acetylation_to_stability`, `residual_function_fraction`.

## The invariant that decides every design question here

**A simulated result can never become evidence about this child.** Every output carries
`origin="synthetic"`. Nothing written here may enter a campaign store, a plan version, or reward
feedback. If a design seems to need that, stop and say so instead of coding around it.

Related, and equally firm:

1. **A prediction may not outrun its weakest link.** If your module produces a number, it reports
   the verdict and the limiting edge alongside it. A number without its cap is not a result.
2. **An unknown is stated, never defaulted.** Six of this chain's rates are unmeasured. A sampler
   draws from the interval; no code treats the midpoint as an estimate, and no report prints a
   point value for an unvalued parameter.
3. **No accuracy claim.** EXP01 and EXP02 have never run. There are no outcomes for this case to
   validate against. Do not write a metric that implies otherwise — no AUPRC against case data, no
   "80% concordance", no held-out-outcome score. The only legitimate benchmark is *published*
   checkpoint behaviour, and it is qualitative.
4. **Generate every number from a record.** No transcribed rates, no hand-written digests. A rate
   carries numerator, denominator and an interval, or states why no interval applies.
5. **Deterministic seeding** via `seed_for`. Never Python's `hash()`.
6. **Tests propagate the real exit status.** Do not pipe pytest into `tail` and read the pipe's.

## File ownership

| Task | Owns these files, and only these |
|---|---|
| SIM02 | `simulate/engine.py`, `tests/test_simulate_engine.py` |
| SIM03 | `simulate/sensitivity.py`, `tests/test_simulate_sensitivity.py` |
| SIM04 | `simulate/negatives.py`, `tests/test_simulate_negatives.py` |
| SIM05 | `simulate/contradict.py`, `tests/test_simulate_contradict.py` |

Do not edit `chain.py`, `mva.py`, or another task's files. `numpy` and `scipy` are available;
**do not add dependencies** — no SALib, no tellurium, no libsbml. Implement what you need.

## A note on what this is for

The question this simulator answers is not *what will the cells do*. Nobody answers that without
the experiment. It is *which measurement would change what we do*, and *where does the reasoning
break*. The chain already says the decisive gap for this case is
`bubr1_abundance -> bubr1_residual_function` — whether the child's altered protein works at
restored abundance. Work that sharpens that answer is valuable. Work that produces a confident
prediction about a drug effect is not, and will be rejected.
