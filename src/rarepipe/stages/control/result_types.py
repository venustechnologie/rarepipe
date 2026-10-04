"""The legitimate ways a compilation can end. Each is a result, not a failure."""
from __future__ import annotations

from enum import StrEnum


class ResultClass(StrEnum):
    CONTROL_SOLUTION_CANDIDATE = "CONTROL_SOLUTION_CANDIDATE"
    ROBUST_CONTROL_SOLUTION_CANDIDATE = "ROBUST_CONTROL_SOLUTION_CANDIDATE"
    CONTROL_INDETERMINATE = "CONTROL_INDETERMINATE"
    CURRENTLY_UNCONTROLLABLE = "CURRENTLY_UNCONTROLLABLE"
    TARGET_SPECIFICATION_INCOMPLETE = "TARGET_SPECIFICATION_INCOMPLETE"
    OBSERVABILITY_INSUFFICIENT = "OBSERVABILITY_INSUFFICIENT"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"


SOLUTION_CLASSES = {ResultClass.CONTROL_SOLUTION_CANDIDATE,
                    ResultClass.ROBUST_CONTROL_SOLUTION_CANDIDATE}

# What each class means, stated where the report renders it, so "uncontrollable" cannot be read as
# "biologically impossible".
MEANING: dict[ResultClass, str] = {
    ResultClass.CONTROL_SOLUTION_CANDIDATE:
        "a causally defensible strategy reaches the target under the single accepted model",
    ResultClass.ROBUST_CONTROL_SOLUTION_CANDIDATE:
        "a strategy reaches the target under every evidence-compatible model and every candidate "
        "for each unknown relationship",
    ResultClass.CONTROL_INDETERMINATE:
        "whether the target is reachable depends on something not yet known; the blocker is named",
    ResultClass.CURRENTLY_UNCONTROLLABLE:
        "unreachable under the current model and the current control set — not biologically "
        "impossible forever",
    ResultClass.TARGET_SPECIFICATION_INCOMPLETE:
        "success has not been sufficiently defined, so reachability cannot be evaluated",
    ResultClass.OBSERVABILITY_INSUFFICIENT:
        "a route may exist, but the available measurements cannot establish that it was taken or "
        "that it stayed safe",
    ResultClass.MODEL_DISAGREEMENT:
        "evidence-compatible models imply materially different control strategies",
}
