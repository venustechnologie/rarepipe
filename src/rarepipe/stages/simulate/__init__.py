"""Causal-chain simulation for the MVA case.

Stage 2 of the simulator plan: express the causal chain explicitly, separately from any solver,
so it is inspectable and diffable before anything is numerically integrated.

The design decision that shapes everything here: **a prediction inherits the weakest link on its
path.** Our actual finding about this case is not that niacin fails, it is that the chain
niacin -> NAD -> SIRT2 -> BubR1 breaks at specific links — the supporting SIRT2 experiment used a
different NAD precursor, and the human NAD evidence is whole-blood rather than intracellular. A
simulator that multiplies plausible rate constants together would produce a confident number and
lose that. This one carries it: every edge records what kind of evidence supports it, and a
predicted path cannot claim more support than its weakest edge allows.
"""

from rarepipe.stages.simulate.chain import (  # noqa: F401
    CausalChain,
    CausalEdge,
    ChainPath,
    Parameter,
    PredictionClaim,
    PropagatedEffect,
    Support,
)
