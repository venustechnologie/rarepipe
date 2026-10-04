"""Physical Realization Compiler (Part 1).

The synthesis layer produces architectures that would mathematically produce a desired state. This
layer asks whether anything real could implement them:

    abstract biological transformation -> physical mechanism -> real components

The decomposition is mandatory, because the shortcut is the thing being prevented. Jumping from a
required function to a compound name removes the whole of the interesting reasoning, so a
realization is a chain of steps, each naming the piece it uses and the capability of that piece it
relies on.

**Build authorization: Part 1 only.** The global building-block universe stays closed. No drug
catalogue, no gene catalogue, no molecular simulator, no binding prediction, no pharmacokinetics and
no delivery modelling — the interfaces are shaped for them and none is implemented.

What makes this layer honest is that its evidence inventory is **derived from the repository**, by
walking the case's own causal chain. A capability cites a claim that already exists, with the support
level and scope already recorded, so it cannot invent a reference and cannot grade its own evidence.
"""
from __future__ import annotations

REALIZATION_PRINCIPLE = (
    "A logical solution is not a feasible intervention, and a mechanism that exists somewhere is "
    "not a mechanism that exists here. Both distinctions are computed, never assumed."
)
