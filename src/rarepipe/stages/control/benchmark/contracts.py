"""The response contract: the structured answer every arm must return, and its validator.

The specification fixes this shape so that four arms producing prose of wildly different quality are
still compared on the same fields. Everything scored is a field here; nothing is scored by reading
an explanation.

The validator is deliberately strict about *shape* and silent about *correctness*. A response that
is well-formed and wrong is a data point; a response that is malformed cannot be scored at all, and
the difference has to be visible, because "the model could not produce the schema" and "the model
produced the schema and got it wrong" are different findings about different problems.

Two fields exist to catch specific failures the engine is supposed to prevent:

``all_tied_optimal_routes``
    Returning one of several tied optima as though it were unique. An arm that answers with a
    single route when four are tied is wrong *even if the route it names is one of the four*.

``unsupported_claims``
    Self-reported assertions that nothing in the graph backs. Scored, not trusted: an arm that
    leaves it empty while asserting unsupported things is caught by the other fields, and one that
    fills it honestly is not penalised for candour.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The verdict vocabulary an arm may use. Deliberately the engine's own three-valued one: an arm
# that cannot say "not established" would be forced to guess, and we would be measuring the
# forcing rather than the reasoning.
VERDICTS = ("TRUE", "FALSE", "NOT_ESTABLISHED")

REQUIRED_FIELDS = (
    "conditional_reachable",
    "robust_reachable",
    "next_best_action",
    "all_tied_optimal_routes",
    "contingent_policy_tree",
    "closed_routes",
    "unsafe_routes",
    "remaining_frontiers",
    "supporting_node_ids",
    "unsupported_claims",
)


class ContractError(ValueError):
    """The response cannot be scored because its shape is wrong, not because it is incorrect."""


@dataclass(frozen=True)
class Response:
    """One arm's answer to one episode."""
    episode_id: str
    arm: str
    conditional_reachable: bool | None = None
    robust_reachable: str | None = None
    next_best_action: str | None = None
    all_tied_optimal_routes: tuple[tuple[str, ...], ...] = ()
    contingent_policy_tree: dict = field(default_factory=dict)
    closed_routes: tuple[str, ...] = ()
    unsafe_routes: tuple[tuple[str, str], ...] = ()
    remaining_frontiers: tuple[str, ...] = ()
    supporting_node_ids: tuple[str, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    # Secondary, recorded for every arm because they are the cost side of any advantage.
    latency_seconds: float | None = None
    tokens: int | None = None
    engine_calls: int | None = None
    malformed_reason: str | None = None

    @property
    def scorable(self) -> bool:
        return self.malformed_reason is None

    def describe(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "arm": self.arm,
            "conditional_reachable": self.conditional_reachable,
            "robust_reachable": self.robust_reachable,
            "next_best_action": self.next_best_action,
            "all_tied_optimal_routes": [list(r) for r in self.all_tied_optimal_routes],
            "contingent_policy_tree": self.contingent_policy_tree,
            "closed_routes": list(self.closed_routes),
            "unsafe_routes": [{"branch": b, "outcome": o} for b, o in self.unsafe_routes],
            "remaining_frontiers": list(self.remaining_frontiers),
            "supporting_node_ids": list(self.supporting_node_ids),
            "unsupported_claims": list(self.unsupported_claims),
            "latency_seconds": self.latency_seconds,
            "tokens": self.tokens,
            "engine_calls": self.engine_calls,
            "malformed_reason": self.malformed_reason,
        }


def response_schema() -> dict:
    """The JSON Schema an arm's raw output must satisfy, for publication alongside results."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "PolicyBenchmarkResponse",
        "type": "object",
        "additionalProperties": True,
        "required": list(REQUIRED_FIELDS),
        "properties": {
            "conditional_reachable": {"type": "boolean"},
            "robust_reachable": {"enum": list(VERDICTS)},
            "next_best_action": {"type": ["string", "null"]},
            "all_tied_optimal_routes": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "Every tied optimal route. One of several returned alone is wrong.",
            },
            "contingent_policy_tree": {"type": "object"},
            "closed_routes": {"type": "array", "items": {"type": "string"}},
            "unsafe_routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["branch", "outcome"],
                    "properties": {"branch": {"type": "string"}, "outcome": {"type": "string"}},
                },
            },
            "remaining_frontiers": {"type": "array", "items": {"type": "string"}},
            "supporting_node_ids": {"type": "array", "items": {"type": "string"}},
            "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        },
    }


def parse(raw: dict, *, episode_id: str, arm: str) -> Response:
    """Build a ``Response``, recording a malformed reason instead of raising.

    A malformed answer is data about the arm, so it is kept and counted rather than thrown away —
    an arm that cannot produce the schema half the time has told us something important, and
    dropping those rows would flatter it.
    """
    missing = [name for name in REQUIRED_FIELDS if name not in raw]
    if missing:
        return Response(episode_id=episode_id, arm=arm,
                        malformed_reason=f"missing fields: {', '.join(missing)}")
    verdict = raw.get("robust_reachable")
    if verdict not in VERDICTS:
        return Response(episode_id=episode_id, arm=arm,
                        malformed_reason=f"robust_reachable {verdict!r} is not one of {VERDICTS}")
    if not isinstance(raw.get("conditional_reachable"), bool):
        return Response(episode_id=episode_id, arm=arm,
                        malformed_reason="conditional_reachable must be a boolean")

    def routes(value) -> tuple[tuple[str, ...], ...]:
        if not isinstance(value, list):
            raise ContractError("all_tied_optimal_routes must be a list of lists")
        return tuple(tuple(sorted(str(x) for x in item)) for item in value)

    def pairs(value) -> tuple[tuple[str, str], ...]:
        out = []
        for item in value or []:
            if isinstance(item, dict) and "branch" in item and "outcome" in item:
                out.append((str(item["branch"]), str(item["outcome"])))
        return tuple(sorted(out))

    try:
        return Response(
            episode_id=episode_id,
            arm=arm,
            conditional_reachable=bool(raw["conditional_reachable"]),
            robust_reachable=verdict,
            next_best_action=(None if raw.get("next_best_action") is None
                              else str(raw["next_best_action"])),
            all_tied_optimal_routes=routes(raw.get("all_tied_optimal_routes") or []),
            contingent_policy_tree=raw.get("contingent_policy_tree") or {},
            closed_routes=tuple(sorted(str(x) for x in raw.get("closed_routes") or [])),
            unsafe_routes=pairs(raw.get("unsafe_routes")),
            remaining_frontiers=tuple(sorted(str(x) for x in raw.get("remaining_frontiers") or [])),
            supporting_node_ids=tuple(sorted(str(x) for x in raw.get("supporting_node_ids") or [])),
            unsupported_claims=tuple(str(x) for x in raw.get("unsupported_claims") or []),
            latency_seconds=raw.get("latency_seconds"),
            tokens=raw.get("tokens"),
            engine_calls=raw.get("engine_calls"),
        )
    except (ContractError, TypeError, ValueError) as exc:
        return Response(episode_id=episode_id, arm=arm,
                        malformed_reason=f"{type(exc).__name__}: {exc}")


def from_oracle(answer, *, episode_id: str, arm: str = "engine") -> Response:
    """The engine's own answer in the response contract — the Arm E / oracle-shaped baseline.

    Useful as a self-check: scoring this against the oracle it came from must give a perfect score,
    and a metric that cannot award one to a known-correct answer is a broken metric.
    """
    return Response(
        episode_id=episode_id,
        arm=arm,
        conditional_reachable=answer.conditional_reachable,
        robust_reachable=answer.verdict,
        next_best_action=(answer.recommended_actions[0] if answer.recommended_actions else None),
        all_tied_optimal_routes=tuple(tuple(sorted(s)) for s in answer.tied_minimal_branch_sets),
        contingent_policy_tree=answer.policy,
        closed_routes=(),
        unsafe_routes=tuple(sorted((b, o) for b, o, _ in answer.unsafe_routes)),
        remaining_frontiers=tuple(answer.remaining_frontiers),
        supporting_node_ids=(),
        unsupported_claims=(),
        engine_calls=1,
    )
