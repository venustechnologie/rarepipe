"""The EPCR schedule, fixed before generation and never tuned against a score.

The evaluator sweeps F-max across the unique EPCR values present in the file, so what
matters is the ordering and that the values are distinct — not that they are calibrated.
We do not possess a calibration model, so we do not pretend to: this is a documented
linear, strictly decreasing schedule, and the artifact says so in as many words.
"""

from __future__ import annotations

TOP = 0.90
STEP = 0.08
DESCRIPTION = (f"Rank 1 receives EPCR {TOP:.2f}; each subsequent rank receives {STEP:.2f} less "
               f"(rank 10 receives {TOP - 9 * STEP:.2f}). Strictly decreasing and distinct, so the "
               "evaluator's F-max threshold sweep can separate every rank; fixed before generation.")


def schedule(n: int) -> list[float]:
    values = [round(TOP - STEP * i, 2) for i in range(n)]
    assert all(0 < v <= 1 for v in values), "EPCR must lie in (0, 1]"
    assert len(set(values)) == len(values), "EPCR values must be distinct for the F-max sweep"
    assert values == sorted(values, reverse=True), "EPCR must decrease with rank"
    return values
