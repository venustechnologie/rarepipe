"""The arms, and the interface the rest of them will implement.

An arm is a callable that sees an episode and returns a response in the contract. That is the whole
interface, and it is deliberately narrow: an arm gets the situation and the graph, and gives back
the fields that are scored. Nothing about how it arrives at them is visible to the scorer, which is
what lets a deterministic solver and a language model be compared on the same footing.

Only **Arm E — engine only** exists today. It is the specification's diagnostic: no language
generation at all, isolating the mathematical quality from any question of phrasing. It is also the
harness's own self-test, because scoring it against the oracle it came from must come out perfect,
and a metric that cannot award full marks to a known-correct answer is broken.

Arms A–D (a model alone, a model with the map, a model with generic tools, a model with the engine)
are not here on purpose. They need a model choice, a budget, and a locked split that exists before
any prompt is tuned. Building them now would mean tuning against episodes that are supposed to be
frozen.

A note on what Arm E is *not*. It cannot be the subject of a competitive claim: it is the engine
answering with the engine's own answer, so it measures the harness and the solver, never an
advantage over anything. The comparison needs the other arms.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol

from rarepipe.stages.control.benchmark.contracts import Response, from_oracle
from rarepipe.stages.control.benchmark.episodes import Episode
from rarepipe.stages.control.benchmark.oracle import oracle_answer
from rarepipe.stages.control.policy import Constraints, PolicyGraph
from rarepipe.stages.control.policy.actions import Action

ENGINE_ONLY = "E_engine_only"


@dataclass(frozen=True)
class ArmContext:
    """Everything an arm is given. The same for every arm, which is the point."""
    graph: PolicyGraph
    campaigns: tuple[Action, ...]
    horizon: int
    constraints: Constraints


class Arm(Protocol):
    """An arm answers one episode. Implementations may be deterministic or not."""

    name: str

    def __call__(self, episode: Episode, context: ArmContext) -> Response:
        ...


@dataclass(frozen=True)
class EngineOnlyArm:
    """Arm E: the engine's own answer, with no language model anywhere in the path.

    Recomputed from the episode's state rather than copied from the stored oracle. Reading the
    answer back out of the episode would make this arm a tautology that passes even if the solver
    broke; recomputing means it re-derives the same answer or the harness notices.
    """
    name: str = ENGINE_ONLY

    def __call__(self, episode: Episode, context: ArmContext) -> Response:
        started = time.perf_counter()
        answer = oracle_answer(
            context.graph, episode.state(), target=episode.target,
            horizon=context.horizon, campaigns=context.campaigns,
            constraints=context.constraints, require_exact=False)
        response = from_oracle(answer, episode_id=episode.id, arm=self.name)
        return _with_latency(response, time.perf_counter() - started)


def _with_latency(response: Response, elapsed: float) -> Response:
    from dataclasses import replace
    return replace(response, latency_seconds=round(elapsed, 4))


def engine_only() -> EngineOnlyArm:
    return EngineOnlyArm()


def from_callable(name: str, answer: Callable[[Episode, ArmContext], dict]) -> Arm:
    """Wrap a function returning raw response JSON as an arm, parsing through the contract.

    How the other arms will be added: whatever produces the JSON — a model call, a tool loop — is
    the caller's business, and the contract is what the harness sees. A malformed answer becomes a
    malformed response rather than an exception, because an arm that cannot produce the schema is a
    finding to record and not a crash.
    """

    @dataclass(frozen=True)
    class _Wrapped:
        name: str

        def __call__(self, episode: Episode, context: ArmContext) -> Response:
            from rarepipe.stages.control.benchmark.contracts import parse
            started = time.perf_counter()
            try:
                raw = answer(episode, context)
            except Exception as exc:                        # noqa: BLE001 — recorded, not raised
                return Response(episode_id=episode.id, arm=self.name,
                                malformed_reason=f"arm raised {type(exc).__name__}: {exc}",
                                latency_seconds=round(time.perf_counter() - started, 4))
            parsed = parse(raw, episode_id=episode.id, arm=self.name)
            return _with_latency(parsed, time.perf_counter() - started)

    return _Wrapped(name=name)
