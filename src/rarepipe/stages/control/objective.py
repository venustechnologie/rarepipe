"""Ranking candidate strategies without a weighted sum.

The general form J(u) = αD + βR + γC + δU needs four weights, and none of them is grounded for this
case; choosing them would be inventing constants. Ranking is lexicographic instead, and safety is
the first key — not a term. A strategy that is unsafe under any evidence-consistent variant ranks
below every strategy that is safe under all of them, however many variants it works in. No amount
of benefit can buy back a safety violation, because the two are never added together.
"""
from __future__ import annotations

from rarepipe.stages.control.controllability import StrategyAssessment


def rank_key(a: StrategyAssessment) -> tuple:
    return (
        bool(a.unsafe_in),                                  # hard: safe everywhere first
        -len(a.works_in),                                   # then works under more variants
        len(a.blocking_relationships) + len(a.feasibility_blockers),
        len(a.unresolved_relied_on),                        # then leans on fewer unresolved links
        len(a.strategy),                                    # then fewer steps
        len(a.controls),                                    # then fewer controls
        a.strategy,                                         # then deterministic tie-break
    )


def rank(assessments: list[StrategyAssessment]) -> list[StrategyAssessment]:
    return sorted(assessments, key=rank_key)
