"""An architecture is not robust because it works under the model somebody liked.

M is the set of biological models still compatible with the evidence, and each model expands into
one variant per candidate for each of its unknown relationships. Robustness is quantified over all
of it:

    A is robust  <=>  A reaches the target under every M_i and every candidate within each M_i.

The intermediate classes exist so that "works under one model" cannot be stated in the same words
as "works under all of them". MODEL_DISAGREEMENT outranks them: when evidence-compatible models
give different verdicts, the honest output is the disagreement, never the favourable half of it.
"""
from __future__ import annotations

from rarepipe.stages.control.synthesis.kinds import RobustnessClass


def classify(per_model: tuple[tuple[str, str], ...]) -> tuple[RobustnessClass, str]:
    """per_model maps a model id to ALL | SOME | NONE across that model's consistent variants."""
    if not per_model:
        return RobustnessClass.NO_MODEL_SUPPORT, "no evidence-consistent variant was evaluated"
    verdicts = {v for _, v in per_model}
    full = [m for m, v in per_model if v == "ALL"]
    partial = [m for m, v in per_model if v == "SOME"]
    if verdicts == {"NONE"}:
        return RobustnessClass.NO_MODEL_SUPPORT, "no model supports this architecture"
    if len(per_model) > 1 and len(verdicts) > 1:
        return (RobustnessClass.MODEL_DISAGREEMENT,
                "evidence-compatible models give different verdicts: " +
                ", ".join(f"{m}={v}" for m, v in per_model))
    if verdicts == {"ALL"}:
        return (RobustnessClass.ROBUST_CONTROL_CANDIDATE,
                f"reaches the target under every candidate of every model in play ({len(full)} "
                "model(s))")
    if len(full) > 1:
        return (RobustnessClass.MULTI_MODEL_CONTROL,
                f"holds under all candidates of {full}, but not of every model")
    if full:
        return (RobustnessClass.MODEL_SPECIFIC_CONTROL,
                f"holds only under {full[0]}, so the verdict depends on that model being the right one")
    return (RobustnessClass.MODEL_SPECIFIC_CONTROL,
            f"holds only under some candidates of {partial}; the unknown decides the outcome")
