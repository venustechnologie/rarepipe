"""Episode generation: valid partial knowledge states, each with an exact oracle answer.

An episode is a situation the engine could really be in — a set of results already in hand — and
the exact answer to what should happen next. The specification's procedure, followed literally:
start at the real root, take only admissible actions, apply only admissible outcomes, update the
state, stop at varying depths, and record the state.

Two things make an episode trustworthy, and both are enforced rather than assumed.

**Only reachable work is ever done.** Actions come from the engine's own action space, so a
generated state is one the solver could actually have arrived at. Hand-rolling the walk would let
an episode decide a branch nothing could have run, and every answer about it would then be about a
situation that cannot occur.

**The oracle must be exact.** An episode whose answer could not be computed exactly is rejected,
with the reason recorded. That is what keeps the harness honest while the exhaustive solver is the
only solver: the admissible region is small, and it is better to have few episodes that mean
something than many whose ground truth is a guess.

Determinism is by explicit seed, through ``random.Random``. Nothing here uses the builtin ``hash``,
which is randomised per process — a "fixed seed" resting on it is not fixed, and this repository
has already been bitten by exactly that.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from random import Random

from rarepipe.stages.control.benchmark.oracle import OracleAnswer, OracleError, oracle_answer
from rarepipe.stages.control.policy import Constraints, KnowledgeState, PolicyGraph, update
from rarepipe.stages.control.policy.actions import (Action, admissible, admissible_outcomes,
                                                    build_action_space)


@dataclass(frozen=True)
class Episode:
    """One situation, and the exact answer to it."""
    id: str
    graph_ref: str
    target: str
    horizon: int
    depth: int
    decided: tuple[tuple[str, str], ...]
    actions_taken: tuple[str, ...]
    oracle: OracleAnswer

    def state(self) -> KnowledgeState:
        return KnowledgeState(decided=self.decided)

    def describe(self) -> dict:
        return {
            "id": self.id,
            "graph_ref": self.graph_ref,
            "target": self.target,
            "horizon": self.horizon,
            "depth": self.depth,
            "decided": {branch: outcome for branch, outcome in self.decided},
            "actions_taken": list(self.actions_taken),
            "oracle": self.oracle.describe(),
        }


@dataclass(frozen=True)
class Rejected:
    """An episode that was generated and then refused, with the reason."""
    depth: int
    decided: tuple[tuple[str, str], ...]
    reason: str

    def describe(self) -> dict:
        return {
            "depth": self.depth,
            "decided": {branch: outcome for branch, outcome in self.decided},
            "reason": self.reason,
        }


def episode_id(graph_ref: str, target: str, decided: tuple[tuple[str, str], ...]) -> str:
    """A stable id from the content, so the same situation is the same episode in every process.

    Built with sha256 rather than ``hash``, which is per-process randomised: ids derived from it
    would reshuffle every run and silently move episodes between splits.
    """
    payload = json.dumps(
        {"graph": graph_ref, "target": target, "decided": sorted(decided)}, sort_keys=True)
    return "ep_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def walk(graph: PolicyGraph, *, campaigns: tuple[Action, ...] = (), rng: Random,
         max_depth: int, constraints: Constraints | None = None
         ) -> list[tuple[int, KnowledgeState, tuple[str, ...]]]:
    """One random descent, yielding the state after each step. Every step is legal by construction."""
    constraints = constraints or Constraints()
    relevant = frozenset(graph.target_relevant_branches(graph.goal))
    space = build_action_space(graph, campaigns, restrict_to=relevant)

    state = KnowledgeState.initial()
    taken: tuple[str, ...] = ()
    trail: list[tuple[int, KnowledgeState, tuple[str, ...]]] = []
    for depth in range(1, max_depth + 1):
        options = admissible(space, state)
        if not options:
            break
        action = options[rng.randrange(len(options))]
        outcomes = admissible_outcomes(
            graph, action, state,
            include_non_informative=constraints.include_non_informative)
        if not outcomes:
            break
        observation = outcomes[rng.randrange(len(outcomes))]
        state = update(graph, state, action, observation)
        taken = taken + (action.id,)
        trail.append((depth, state, taken))
    return trail


def generate(graph: PolicyGraph, *, graph_ref: str, campaigns: tuple[Action, ...] = (),
             seed: int, count: int, max_depth: int = 3, horizon: int = 3,
             constraints: Constraints | None = None,
             include_root: bool = True) -> tuple[tuple[Episode, ...], tuple[Rejected, ...]]:
    """Generate up to ``count`` distinct admissible episodes, plus the ones that were refused.

    Duplicates are collapsed by content id: two descents that learn the same things are the same
    episode, and scoring the same situation twice would weight it twice for no reason.

    The returned rejections are not noise. They are the measurement of how much of the space the
    exhaustive solver can actually certify, which is the number that decides when the symbolic
    solver becomes necessary.
    """
    constraints = constraints or Constraints()
    rng = Random(seed)
    found: dict[str, Episode] = {}
    refused: list[Rejected] = []

    def consider(depth: int, state: KnowledgeState, taken: tuple[str, ...]) -> None:
        identifier = episode_id(graph_ref, graph.goal, state.decided)
        if identifier in found:
            return
        try:
            answer = oracle_answer(graph, state, horizon=horizon, campaigns=campaigns,
                                   constraints=constraints)
        except OracleError as exc:
            refused.append(Rejected(depth=depth, decided=state.decided, reason=str(exc)))
            return
        found[identifier] = Episode(
            id=identifier, graph_ref=graph_ref, target=graph.goal, horizon=horizon,
            depth=depth, decided=state.decided, actions_taken=taken, oracle=answer)

    if include_root:
        consider(0, KnowledgeState.initial(), ())

    # Bounded attempts rather than a while-true: a graph can run out of distinct shallow states,
    # and a generator that spins looking for a count it cannot reach is worse than one that returns
    # fewer and says so.
    attempts = 0
    while len(found) < count and attempts < count * 12:
        attempts += 1
        for depth, state, taken in walk(graph, campaigns=campaigns, rng=rng,
                                        max_depth=max_depth, constraints=constraints):
            if len(found) >= count:
                break
            consider(depth, state, taken)

    episodes = tuple(sorted(found.values(), key=lambda e: (e.depth, e.id)))
    return episodes, tuple(refused)


def coverage(episodes: tuple[Episode, ...], refused: tuple[Rejected, ...]) -> dict:
    """How much of the attempted space the exhaustive oracle could certify, and at what depths."""
    by_depth: dict[int, int] = {}
    for episode in episodes:
        by_depth[episode.depth] = by_depth.get(episode.depth, 0) + 1
    refused_by_depth: dict[int, int] = {}
    for entry in refused:
        refused_by_depth[entry.depth] = refused_by_depth.get(entry.depth, 0) + 1
    attempted = len(episodes) + len(refused)
    return {
        "admitted": len(episodes),
        "refused": len(refused),
        "attempted": attempted,
        "admitted_fraction": (len(episodes) / attempted) if attempted else 0.0,
        "admitted_by_depth": dict(sorted(by_depth.items())),
        "refused_by_depth": dict(sorted(refused_by_depth.items())),
        "note": ("Refusals are episodes whose oracle could not be computed exactly. They measure "
                 "how far the exhaustive solver certifies, which is what decides when a symbolic "
                 "solver stops being optional."),
    }
