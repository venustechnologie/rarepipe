"""Drive arms over a split, score every response, and report with the provenance of the run.

The run records what it was measured on, not just what the numbers were. A benchmark result
without the episode set's seal, the split salt and the horizon is a number nobody can reproduce or
contest, and the whole purpose of freezing a split is to make a published figure traceable.

Two guards the runner enforces rather than trusting:

**The locked split is verified before it is used.** If its seal no longer matches, the run stops.
Measuring against a locked set that has changed since it was sealed produces a number about some
other set.

**Running on the locked split is explicit.** ``allow_locked`` must be passed. The default is the
development split, because the locked one is meant to be touched once, at the end, and a default
that quietly used it is how a test set gets tuned against by accident.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from rarepipe.stages.control.benchmark import metrics
from rarepipe.stages.control.benchmark.arms import Arm, ArmContext
from rarepipe.stages.control.benchmark.contracts import Response
from rarepipe.stages.control.benchmark.episodes import Episode
from rarepipe.stages.control.benchmark.metrics import Score
from rarepipe.stages.control.benchmark.splits import DEVELOPMENT, LOCKED, SplitSet
from rarepipe.stages.control.policy import Constraints, PolicyGraph
from rarepipe.stages.control.policy.actions import Action, build_action_space


class RunnerError(ValueError):
    pass


@dataclass(frozen=True)
class RunResult:
    split: str
    arms: tuple[str, ...]
    episodes: int
    repeats: int
    horizon: int
    locked_seal: str
    split_salt: str
    graph_ref: str
    responses: tuple[Response, ...]
    scores: tuple[Score, ...]

    def describe(self, *, include_responses: bool = False) -> dict:
        out = {
            "provenance": {
                "split": self.split,
                "split_salt": self.split_salt,
                "locked_seal": self.locked_seal,
                "graph_ref": self.graph_ref,
                "horizon": self.horizon,
                "episodes": self.episodes,
                "repeats": self.repeats,
                "arms": list(self.arms),
                "note": ("A result is reproducible only with the set it was measured on. The seal "
                         "identifies that set; the salt identifies the split that produced it."),
            },
            "per_arm": metrics.aggregate(self.scores),
            "reproducibility": metrics.reproducibility(self.scores),
            "secondary": _secondary(self.responses),
        }
        if include_responses:
            out["responses"] = [r.describe() for r in self.responses]
            out["scores"] = [s.describe() for s in self.scores]
        return out


def _secondary(responses: tuple[Response, ...]) -> dict:
    """Latency, tokens and engine calls — the cost side of any advantage."""
    by_arm: dict[str, list[Response]] = {}
    for response in responses:
        by_arm.setdefault(response.arm, []).append(response)

    def average(rows, field):
        values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        return {"mean": mean(values) if values else None, "reported_by": len(values)}

    return {
        arm: {field: average(rows, field)
              for field in ("latency_seconds", "tokens", "engine_calls")}
        for arm, rows in sorted(by_arm.items())
    }


def run(graph: PolicyGraph, splits: SplitSet, arms: tuple[Arm, ...], *,
        campaigns: tuple[Action, ...] = (), split: str = DEVELOPMENT, horizon: int = 3,
        repeats: int = 1, constraints: Constraints | None = None,
        allow_locked: bool = False, graph_ref: str = "") -> RunResult:
    """Run every arm over every episode of a split, ``repeats`` times each."""
    if split == LOCKED and not allow_locked:
        raise RunnerError(
            "refusing to run on the locked split without allow_locked=True. It is meant to be "
            "measured once, at the end; a default that used it quietly is how a test set gets "
            "tuned against by accident.")
    if repeats < 1:
        raise RunnerError("repeats must be at least one")
    splits.verify()

    constraints = constraints or Constraints()
    context = ArmContext(graph=graph, campaigns=campaigns, horizon=horizon,
                         constraints=constraints)
    chosen: tuple[Episode, ...] = splits.by_name(split).episodes
    available = frozenset(
        action.id for action in build_action_space(
            graph, campaigns,
            restrict_to=frozenset(graph.target_relevant_branches(graph.goal))).actions)

    responses: list[Response] = []
    scores: list[Score] = []
    for episode in chosen:
        for arm in arms:
            for _ in range(repeats):
                response = arm(episode, context)
                responses.append(response)
                scores.append(metrics.score(graph, response, episode.oracle,
                                            available_actions=available))

    return RunResult(
        split=split,
        arms=tuple(arm.name for arm in arms),
        episodes=len(chosen),
        repeats=repeats,
        horizon=horizon,
        locked_seal=splits.locked_seal,
        split_salt=splits.salt,
        graph_ref=graph_ref,
        responses=tuple(responses),
        scores=tuple(scores),
    )
