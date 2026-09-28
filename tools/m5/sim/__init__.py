"""A5 — operating characteristics of the proposed M5 decision system, by simulation.

EVERYTHING IN THIS PACKAGE IS SYNTHETIC. Every number produced here is a property of an
explicitly stated generative model, not a measurement, not an MVA parameter and not a
probability about any person. No output of this package may enter a plan, a gap register, a
review record or an evidence table. The package reads the real decision engine
(`rarepipe.stages.prospective.rules.evaluate`) but writes nothing back.

What is being tested is the *whole* decision system: data generating process -> candidate
statistical analysis -> decision framing -> observation-vector category -> branch. A statistical
test that behaves correctly can still feed a branch engine that draws the wrong conclusion, so
each run ends at a branch, not at a p-value.
"""

from __future__ import annotations

SYNTHETIC_LABEL = (
    "SIMULATION_OUTPUT (synthetic): conditional on the stated generative model only; "
    "not a measurement, not an MVA parameter, not a probability about this child"
)

__all__ = ["SYNTHETIC_LABEL"]
