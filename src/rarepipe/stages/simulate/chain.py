"""A causal chain whose predictions cannot outrun their evidence."""
from __future__ import annotations

import zlib
from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Support(StrEnum):
    """What kind of evidence stands behind an edge or a parameter.

    Ordered by how much a prediction may lean on it (see `Strength`). The three middle members
    exist because this case needs them: the SIRT2/BubR1 result used NMN rather than nicotinic
    acid, and the human NAD result is whole blood rather than the relevant intracellular
    compartment. Collapsing those into "supported" is exactly the error this module exists to
    prevent.
    """

    HUMAN_EXPERIMENTAL = "human_experimental"
    MODEL_EXPERIMENTAL = "model_experimental"
    DIFFERENT_AGENT = "different_agent"
    DIFFERENT_COMPARTMENT = "different_compartment"
    CLASS_LEVEL = "class_level"
    COMPUTATIONAL = "computational"
    ASSERTED_ONLY = "asserted_only"
    CONTRADICTED = "contradicted"


class Strength(IntEnum):
    """How far a prediction may lean on each support kind. Lower binds the whole path."""

    CONTRADICTED = 0
    ASSERTED_ONLY = 1
    COMPUTATIONAL = 2
    CLASS_LEVEL = 3
    DIFFERENT_COMPARTMENT = 4
    DIFFERENT_AGENT = 4
    MODEL_EXPERIMENTAL = 5
    HUMAN_EXPERIMENTAL = 6


STRENGTH: dict[Support, Strength] = {
    Support.CONTRADICTED: Strength.CONTRADICTED,
    Support.ASSERTED_ONLY: Strength.ASSERTED_ONLY,
    Support.COMPUTATIONAL: Strength.COMPUTATIONAL,
    Support.CLASS_LEVEL: Strength.CLASS_LEVEL,
    Support.DIFFERENT_COMPARTMENT: Strength.DIFFERENT_COMPARTMENT,
    Support.DIFFERENT_AGENT: Strength.DIFFERENT_AGENT,
    Support.MODEL_EXPERIMENTAL: Strength.MODEL_EXPERIMENTAL,
    Support.HUMAN_EXPERIMENTAL: Strength.HUMAN_EXPERIMENTAL,
}

# What a path may be reported as, given its weakest link. Never "established": no path through a
# simulated chain establishes anything about a patient.
VERDICT_FOR_STRENGTH: dict[int, str] = {
    0: "CONTRADICTED_ON_PATH",
    1: "ASSERTION_ONLY",
    2: "COMPUTATIONAL_ONLY",
    3: "CLASS_LEVEL_ONLY",
    4: "CONDITIONAL_ON_UNVERIFIED_SUBSTITUTION",
    5: "SUPPORTED_IN_MODEL_SYSTEMS",
    6: "SUPPORTED_IN_HUMANS",
}


class Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Parameter(Immutable):
    """A quantity with its evidence, or an explicit unknown with a stated interval.

    A parameter with no measured value does not get a plausible default. It gets `value=None`, a
    wide interval, and a support kind that a path inherits. `prior` is the interval a sampler may
    draw from; it is required whenever the value is unknown, so "we do not know this" can never be
    silently replaced by a point estimate.
    """

    name: str
    unit: str
    value: float | None = None
    prior: tuple[float, float] | None = None
    support: Support = Support.ASSERTED_ONLY
    evidence_ref: str | None = None
    note: str = ""

    @model_validator(mode="after")
    def _unknown_needs_an_interval(self):
        if self.value is None and self.prior is None:
            raise ValueError(
                f"parameter {self.name!r} has no value and no interval: an unknown quantity must "
                "state the range it could take, never fall back on a default"
            )
        if self.prior is not None and self.prior[0] > self.prior[1]:
            raise ValueError(f"parameter {self.name!r} has an inverted interval")
        if self.support is not Support.ASSERTED_ONLY and not self.evidence_ref:
            raise ValueError(
                f"parameter {self.name!r} claims {self.support.value} support with no evidence "
                "reference"
            )
        return self

    def interval(self) -> tuple[float, float]:
        if self.prior is not None:
            return self.prior
        return (float(self.value), float(self.value))  # type: ignore[arg-type]


class CausalEdge(Immutable):
    """One causal claim: source changes target, in a stated direction, on stated evidence."""

    source: str
    target: str
    sign: Literal[1, -1]
    mechanism: str
    support: Support
    evidence_ref: str | None = None
    scope_note: str = Field("", description="What the cited evidence actually covered.")
    caveat: str = ""
    parameter: Parameter | None = None

    @model_validator(mode="after")
    def _evidence_required_unless_asserted(self):
        if self.support is not Support.ASSERTED_ONLY and not self.evidence_ref:
            raise ValueError(
                f"edge {self.source}->{self.target} claims {self.support.value} support with no "
                "evidence reference"
            )
        if self.support in {Support.DIFFERENT_AGENT, Support.DIFFERENT_COMPARTMENT} \
                and not self.scope_note:
            raise ValueError(
                f"edge {self.source}->{self.target} is {self.support.value}: say in scope_note "
                "what the cited evidence actually covered, or the substitution is invisible"
            )
        return self

    @property
    def key(self) -> str:
        return f"{self.source}->{self.target}"


class ChainPath(Immutable):
    """An ordered route through the chain."""

    edges: tuple[CausalEdge, ...]

    @property
    def nodes(self) -> tuple[str, ...]:
        if not self.edges:
            return ()
        return (self.edges[0].source, *(e.target for e in self.edges))

    @property
    def sign(self) -> int:
        total = 1
        for edge in self.edges:
            total *= edge.sign
        return total

    def weakest(self) -> CausalEdge:
        return min(self.edges, key=lambda e: int(STRENGTH[e.support]))


class PredictionClaim(Immutable):
    """What a path may be reported as. Never evidence about a patient."""

    origin: Literal["synthetic"] = "synthetic"
    source: str
    target: str
    direction: Literal["increase", "decrease"]
    verdict: str
    weakest_link: str
    weakest_support: Support
    limiting_scope_note: str
    path: tuple[str, ...]
    unsupported_links: tuple[str, ...] = ()
    contradicted_alternatives: tuple[str, ...] = Field(
        (),
        description="Routes to the same target that the evidence contradicts. Reported even "
                    "though a better-supported route exists: a null result on a shorter route is "
                    "evidence about the hypothesis, not noise the strongest path gets to hide.",
    )
    caveats: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _never_claims_establishment(self):
        if "ESTABLISH" in self.verdict.upper() or "PROVEN" in self.verdict.upper():
            raise ValueError("a simulated path establishes nothing; verdicts may not say so")
        return self


class CausalChain(Immutable):
    """A named set of causal claims over biological states."""

    chain_id: str
    case_ref: str
    nodes: tuple[str, ...]
    edges: tuple[CausalEdge, ...]

    @model_validator(mode="after")
    def _edges_connect_declared_nodes(self):
        declared = set(self.nodes)
        for edge in self.edges:
            missing = {edge.source, edge.target} - declared
            if missing:
                raise ValueError(f"edge {edge.key} uses undeclared node(s) {sorted(missing)}")
        return self

    def out_edges(self, node: str) -> tuple[CausalEdge, ...]:
        return tuple(e for e in self.edges if e.source == node)

    def paths(self, source: str, target: str) -> tuple[ChainPath, ...]:
        """Every acyclic route from source to target."""
        found: list[ChainPath] = []

        def walk(node: str, trail: list[CausalEdge], seen: set[str]) -> None:
            if node == target and trail:
                found.append(ChainPath(edges=tuple(trail)))
                return
            for edge in self.out_edges(node):
                if edge.target in seen:
                    continue
                walk(edge.target, [*trail, edge], seen | {edge.target})

        walk(source, [], {source})
        return tuple(found)

    def predict(self, source: str, target: str) -> PredictionClaim | None:
        """The best claim available from source to target, limited by its weakest link.

        Where several routes exist, the strongest route is reported — and it is still capped by
        its own weakest edge, so adding a chain of assertions can never raise a verdict.
        """
        routes = self.paths(source, target)
        if not routes:
            return None
        best = max(routes, key=lambda p: int(STRENGTH[p.weakest().support]))
        weak = best.weakest()
        contradicted = tuple(
            " -> ".join(route.nodes)
            for route in routes
            if route is not best
            and any(e.support is Support.CONTRADICTED for e in route.edges)
        )
        return PredictionClaim(
            source=source, target=target,
            direction="increase" if best.sign > 0 else "decrease",
            verdict=VERDICT_FOR_STRENGTH[int(STRENGTH[weak.support])],
            weakest_link=weak.key,
            weakest_support=weak.support,
            limiting_scope_note=weak.scope_note or weak.caveat or "no scope recorded",
            path=best.nodes,
            unsupported_links=tuple(
                e.key for e in best.edges
                if STRENGTH[e.support] <= Strength.ASSERTED_ONLY
            ),
            contradicted_alternatives=contradicted,
            caveats=tuple(e.caveat for e in best.edges if e.caveat),
        )

    def unknown_parameters(self) -> tuple[Parameter, ...]:
        return tuple(e.parameter for e in self.edges
                     if e.parameter is not None and e.parameter.value is None)

    def seed_for(self, label: str, master_seed: int) -> int:
        """Deterministic across processes. Never Python's per-process hash()."""
        payload = f"{master_seed}|{self.chain_id}|{label}".encode()
        return zlib.crc32(payload) & 0xFFFFFFFF
