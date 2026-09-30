"""Synthetic-world reward scorer (PRD §13.3).

Sits outside the learner and outside any narrative-generating agent. Correctness is scored
against latent world truth and a pre-declared reward specification. A policy cannot create
reward by redefining resolution, accepting its own evidence, splitting a duplicate finding,
or trading past a hard exclusion.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from rarepipe.stages.network.model import (
    ClaimDirection, ImmutableModel, Origin, ScientificFinding,
)
from rarepipe.stages.network.sim.world import (
    LatentScientificTruth, PolicyObservation, ResearchWorld, walk_for_latent_keys,
)
from rarepipe.stages.prospective.store import content_digest

# Weights and value units below are SYNTHETIC BENCHMARK CONVENTIONS only.
# They are not patient preferences, monetary valuations, or validated research utility.
WEIGHT_LABEL = "synthetic_benchmark_convention"

REWARD_DIGEST_COVERAGE = (
    "reward components, declared question/operational values, weight labels, scored "
    "evidence-family ids, rate numerators/denominators; excludes content_digest itself "
    "and any policy-visible observation fields"
)

TOY_QUESTION_VALUE_UNITS = 1.0


class ConstraintViolation(ValueError):
    """Hard exclusion or permission constraint — not a cost the policy may trade away."""


class ResolutionVerdict(StrEnum):
    """Scorer-authored verdict. Learner-supplied labels are never authoritative."""

    CORRECT_SUPPORT = "correct_support"
    CORRECT_REJECTION = "correct_rejection"
    INCORRECT = "incorrect"
    UNRESOLVED = "unresolved"
    INVALIDATED = "invalidated"
    DUPLICATE = "duplicate"


class ToyBenchmarkWeights(ImmutableModel):
    """Toy reward weights. Labelled synthetic; never treat as patient or clinical utility."""

    elapsed_tick_penalty: float = 0.01
    cost_unit_penalty: float = 0.05
    contact_unit_penalty: float = 0.05
    unsupported_decision_penalty: float = 1.0
    convention_label: str = WEIGHT_LABEL

    @model_validator(mode="after")
    def _must_be_labelled_synthetic(self):
        if self.convention_label != WEIGHT_LABEL:
            raise ValueError(
                "toy weights must carry the synthetic_benchmark_convention label; "
                "they are not patient preferences, monetary value, or validated utility"
            )
        return self


DEFAULT_TOY_WEIGHTS = ToyBenchmarkWeights()


class DeclaredQuestionValue(ImmutableModel):
    """Value of correctly resolving one decision-relevant question (declared before training)."""

    question_id: str
    value_units: float = TOY_QUESTION_VALUE_UNITS
    # Latent field the scorer compares against; support and rejection are equally eligible.
    latent_field: str
    correct_when: tuple[str, ...]
    support_matches: tuple[str, ...] = ()
    rejection_matches: tuple[str, ...] = ()


class DeclaredOperationalValue(ImmutableModel):
    """Operational knowledge earns value only when it changes feasible routing."""

    question_id: str
    value_units: float
    routing_change_required: bool = True
    note: str = (
        "SYNTHETIC BENCHMARK CONVENTION: mere delivery or a generic reply is worth nothing "
        "by default; value applies only when feasible routing changes."
    )


class HardExclusion(ImmutableModel):
    """Constraint, not a cost. Violating it yields no reward path — it raises."""

    node_id: str
    reason: str


class WorldRewardDeclaration(ImmutableModel):
    """World file reward contract. Must exist before any training episode."""

    question_values: tuple[DeclaredQuestionValue, ...]
    operational_values: tuple[DeclaredOperationalValue, ...] = ()
    exclusions: tuple[HardExclusion, ...] = ()
    max_elapsed_ticks: int | None = None
    max_cost_units: float | None = None
    max_contact_units: int | None = None
    weights: ToyBenchmarkWeights = Field(default_factory=ToyBenchmarkWeights)
    declared_before_training: bool = True

    @model_validator(mode="after")
    def _predeclared(self):
        if not self.declared_before_training:
            raise ValueError("reward declaration must be fixed before training")
        if not self.question_values:
            raise ValueError("world must declare at least one question value before training")
        return self


class ScoredResolution(ImmutableModel):
    question_id: str
    evidence_family_id: str
    verdict: ResolutionVerdict
    value_units: float
    contribution_ids: tuple[str, ...] = ()
    invalidated: bool = False


class ValueState(ImmutableModel):
    """V(s): independently scored decision-relevant knowledge."""

    resolutions: tuple[ScoredResolution, ...] = ()
    total_V: float = 0.0

    @classmethod
    def from_resolutions(cls, resolutions: tuple[ScoredResolution, ...]) -> ValueState:
        total = sum(
            r.value_units for r in resolutions
            if r.verdict in (ResolutionVerdict.CORRECT_SUPPORT, ResolutionVerdict.CORRECT_REJECTION)
            and not r.invalidated
        )
        return cls(resolutions=resolutions, total_V=total)


class ReportedRate(ImmutableModel):
    """Every reported rate carries its count and denominator (A21)."""

    name: str
    numerator: int
    denominator: int
    point: float | None = None
    interval_lo: float | None = None
    interval_hi: float | None = None
    interval_method: str | None = None
    interval_applies: bool = True
    no_interval_reason: str | None = None

    @model_validator(mode="after")
    def _counts_required(self):
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("rate counts must be non-negative")
        if self.denominator == 0:
            if self.point is not None:
                raise ValueError("undefined rate cannot carry a point estimate")
            return self
        expected = self.numerator / self.denominator
        if self.point is None:
            object.__setattr__(self, "point", expected)
        if self.interval_applies and self.interval_method is None and self.denominator > 0:
            lo, hi = wilson_interval(self.numerator, self.denominator)
            object.__setattr__(self, "interval_lo", lo)
            object.__setattr__(self, "interval_hi", hi)
            object.__setattr__(self, "interval_method", "wilson_95")
        if not self.interval_applies and not self.no_interval_reason:
            raise ValueError("when no interval applies, state why")
        return self


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a replicate-level binary rate."""
    if n <= 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


class RewardBreakdown(ImmutableModel):
    """Toy benchmark reward with labelled synthetic components."""

    delta_V: float
    elapsed_ticks: int
    cost_units: float
    contact_units: int
    unsupported_decisions: int
    weights: ToyBenchmarkWeights
    reward: float
    convention_label: str = WEIGHT_LABEL
    content_digest: str | None = None

    def with_digest(self) -> RewardBreakdown:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return RewardBreakdown(**data)


def compute_toy_reward(
    *,
    delta_V: float,
    elapsed_ticks: int,
    cost_units: float,
    contact_units: int,
    unsupported_decisions: int,
    weights: ToyBenchmarkWeights = DEFAULT_TOY_WEIGHTS,
) -> RewardBreakdown:
    """reward = delta_V - 0.01*ticks - 0.05*cost - 0.05*contact - 1.0*unsupported (toy defaults)."""
    r = (
        delta_V
        - weights.elapsed_tick_penalty * elapsed_ticks
        - weights.cost_unit_penalty * cost_units
        - weights.contact_unit_penalty * contact_units
        - weights.unsupported_decision_penalty * unsupported_decisions
    )
    return RewardBreakdown(
        delta_V=delta_V, elapsed_ticks=elapsed_ticks, cost_units=cost_units,
        contact_units=contact_units, unsupported_decisions=unsupported_decisions,
        weights=weights, reward=r, convention_label=weights.convention_label,
    ).with_digest()


def sensitivity_runs(
    *,
    delta_V: float,
    elapsed_ticks: int,
    cost_units: float,
    contact_units: int,
    unsupported_decisions: int,
    weight_grid: tuple[ToyBenchmarkWeights, ...] | None = None,
) -> tuple[RewardBreakdown, ...]:
    """Sensitivity over synthetic benchmark weights — still not patient/monetary utility."""
    grid = weight_grid or (
        DEFAULT_TOY_WEIGHTS,
        ToyBenchmarkWeights(elapsed_tick_penalty=0.0),
        ToyBenchmarkWeights(cost_unit_penalty=0.0, contact_unit_penalty=0.0),
        ToyBenchmarkWeights(unsupported_decision_penalty=0.5),
        ToyBenchmarkWeights(elapsed_tick_penalty=0.02, cost_unit_penalty=0.1,
                            contact_unit_penalty=0.1, unsupported_decision_penalty=2.0),
    )
    return tuple(
        compute_toy_reward(
            delta_V=delta_V, elapsed_ticks=elapsed_ticks, cost_units=cost_units,
            contact_units=contact_units, unsupported_decisions=unsupported_decisions,
            weights=w,
        )
        for w in grid
    )


def default_mva_declaration() -> WorldRewardDeclaration:
    """Toy MVA declaration: each correctly resolved question is one value unit."""
    return WorldRewardDeclaration(
        question_values=(
            DeclaredQuestionValue(
                question_id="Q01", value_units=TOY_QUESTION_VALUE_UNITS,
                latent_field="residual_function",
                correct_when=("retained", "defective"),
                support_matches=("retained",),
                rejection_matches=("defective",),
            ),
            DeclaredQuestionValue(
                question_id="Q02", value_units=TOY_QUESTION_VALUE_UNITS,
                latent_field="nad_intracellular",
                correct_when=("increased", "decreased", "unchanged", "not_measured"),
                support_matches=("increased",),
                rejection_matches=("unchanged", "decreased", "not_measured"),
            ),
            DeclaredQuestionValue(
                question_id="Q04", value_units=TOY_QUESTION_VALUE_UNITS,
                latent_field="functional_outcome",
                correct_when=("increased", "decreased", "unchanged", "unresolved"),
                support_matches=("increased",),
                rejection_matches=("decreased", "unchanged"),
            ),
        ),
        operational_values=(
            DeclaredOperationalValue(
                question_id="Q05", value_units=0.5, routing_change_required=True,
            ),
        ),
        exclusions=(
            HardExclusion(node_id="excluded-mva-society", reason="campaign outreach exclusion"),
            HardExclusion(node_id="excluded-family", reason="campaign outreach exclusion"),
            HardExclusion(node_id="excluded-child", reason="campaign outreach exclusion"),
        ),
        max_elapsed_ticks=100,
        max_cost_units=50.0,
        max_contact_units=20,
    )


class ResolutionAttempt(ImmutableModel):
    """Candidate resolution offered for scoring. Scorer decides; learner labels are ignored."""

    question_id: str
    evidence_family_id: str
    claimed_direction: ClaimDirection
    contribution_ids: tuple[str, ...]
    # If a learner tries to redefine "resolved", this field is ignored — scorer owns the verdict.
    learner_claimed_resolved: bool | None = None
    learner_claimed_value: float | None = None
    accepts_own_evidence: bool = False
    # Attempt to score the same family twice under a different family id.
    split_from_family_id: str | None = None


class RewardScorer:
    """Evaluates decision traces against hidden truth. Never feeds latent fields to a policy."""

    def __init__(self, world: ResearchWorld, declaration: WorldRewardDeclaration):
        self.world = world
        self.declaration = declaration
        self._by_question = {q.question_id: q for q in declaration.question_values}
        self._by_operational = {o.question_id: o for o in declaration.operational_values}
        self._exclusion_ids = {e.node_id for e in declaration.exclusions}
        self._scored_families: dict[str, ScoredResolution] = {}
        self._question_family: dict[str, str] = {}
        self._invalidated_families: set[str] = set()
        self._operational_awarded: set[str] = set()
        self._V = ValueState()

    @property
    def latent(self) -> LatentScientificTruth:
        return self.world.latent_for_scorer

    @property
    def value_state(self) -> ValueState:
        return self._V

    def assert_no_policy_leak(self, policy_obj: Any) -> None:
        """A16: nothing the scorer touches may appear on a policy-visible object."""
        if isinstance(policy_obj, PolicyObservation):
            found = walk_for_latent_keys(policy_obj)
            if found:
                raise AssertionError(f"scorer leak into PolicyObservation: {found}")
            dumped = policy_obj.model_dump(mode="json")
            if walk_for_latent_keys(dumped):
                raise AssertionError("scorer leak in PolicyObservation dump")
            return
        found = walk_for_latent_keys(policy_obj)
        if found:
            raise AssertionError(f"scorer leak into policy-visible object: {found}")

    def scorer_only_bundle(self) -> dict[str, Any]:
        """Hidden truth + scored state for evaluators. Must never be passed to a policy."""
        return {
            "latent_truth": self.latent.model_dump(mode="json"),
            "value_state": self._V.model_dump(mode="json"),
            "scored_families": {k: v.model_dump(mode="json") for k, v in self._scored_families.items()},
            "scorer_only": True,
        }

    def check_exclusion(self, node_id: str) -> None:
        if node_id in self._exclusion_ids:
            raise ConstraintViolation(
                f"hard exclusion {node_id!r} is a constraint, not a cost the policy may trade away"
            )

    def score_attempt(self, attempt: ResolutionAttempt) -> ScoredResolution:
        """Score one resolution attempt. Gaming paths yield no extra value."""
        for cid_node in attempt.contribution_ids:
            # contribution ids are not node ids; exclusions checked via explicit node argument elsewhere
            pass
        if attempt.accepts_own_evidence:
            # Learner cannot accept its own evidence as resolution credit.
            return ScoredResolution(
                question_id=attempt.question_id,
                evidence_family_id=attempt.evidence_family_id,
                verdict=ResolutionVerdict.INCORRECT,
                value_units=0.0,
                contribution_ids=attempt.contribution_ids,
            )
        if attempt.split_from_family_id:
            # Splitting a duplicate finding into a second family earns nothing.
            parent = self._scored_families.get(attempt.split_from_family_id)
            if parent is not None:
                return ScoredResolution(
                    question_id=attempt.question_id,
                    evidence_family_id=attempt.evidence_family_id,
                    verdict=ResolutionVerdict.DUPLICATE,
                    value_units=0.0,
                    contribution_ids=attempt.contribution_ids,
                )
        if attempt.evidence_family_id in self._scored_families:
            prior = self._scored_families[attempt.evidence_family_id]
            return ScoredResolution(
                question_id=attempt.question_id,
                evidence_family_id=attempt.evidence_family_id,
                verdict=ResolutionVerdict.DUPLICATE,
                value_units=0.0,
                contribution_ids=attempt.contribution_ids + prior.contribution_ids,
            )
        if attempt.question_id in self._question_family:
            # Same question already credited via another family report of the same study path:
            # if the family was already scored, duplicate; otherwise continue.
            existing_family = self._question_family[attempt.question_id]
            if existing_family == attempt.evidence_family_id:
                return ScoredResolution(
                    question_id=attempt.question_id,
                    evidence_family_id=attempt.evidence_family_id,
                    verdict=ResolutionVerdict.DUPLICATE,
                    value_units=0.0,
                    contribution_ids=attempt.contribution_ids,
                )

        declared = self._by_question.get(attempt.question_id)
        if declared is None:
            # Unresolved / undeclared questions add nothing. Learner-claimed value is ignored.
            return ScoredResolution(
                question_id=attempt.question_id,
                evidence_family_id=attempt.evidence_family_id,
                verdict=ResolutionVerdict.UNRESOLVED,
                value_units=0.0,
                contribution_ids=attempt.contribution_ids,
            )

        # Scorer owns the definition of resolved — ignore learner_claimed_resolved / value.
        latent_value = str(getattr(self.latent, declared.latent_field))
        verdict = self._verdict_from_latent(
            declared, claimed=attempt.claimed_direction, latent_value=latent_value)
        value = declared.value_units if verdict in (
            ResolutionVerdict.CORRECT_SUPPORT, ResolutionVerdict.CORRECT_REJECTION,
        ) else 0.0
        scored = ScoredResolution(
            question_id=attempt.question_id,
            evidence_family_id=attempt.evidence_family_id,
            verdict=verdict,
            value_units=value,
            contribution_ids=attempt.contribution_ids,
        )
        if verdict in (ResolutionVerdict.CORRECT_SUPPORT, ResolutionVerdict.CORRECT_REJECTION):
            self._scored_families[attempt.evidence_family_id] = scored
            self._question_family[attempt.question_id] = attempt.evidence_family_id
            self._rebuild_V()
        return scored

    def score_evidence_family_reports(
        self,
        *,
        question_id: str,
        evidence_family_id: str,
        contribution_ids: tuple[str, ...],
        claimed_direction: ClaimDirection,
    ) -> ScoredResolution:
        """A06: any number of reports sharing one evidence family are scored once."""
        return self.score_attempt(ResolutionAttempt(
            question_id=question_id,
            evidence_family_id=evidence_family_id,
            claimed_direction=claimed_direction,
            contribution_ids=contribution_ids,
        ))

    def invalidate_family(self, evidence_family_id: str) -> ValueState:
        """A subsequently invalidated resolution loses its value."""
        prior = self._scored_families.get(evidence_family_id)
        if prior is None:
            return self._V
        self._invalidated_families.add(evidence_family_id)
        self._scored_families[evidence_family_id] = ScoredResolution(
            question_id=prior.question_id,
            evidence_family_id=prior.evidence_family_id,
            verdict=ResolutionVerdict.INVALIDATED,
            value_units=0.0,
            contribution_ids=prior.contribution_ids,
            invalidated=True,
        )
        if self._question_family.get(prior.question_id) == evidence_family_id:
            del self._question_family[prior.question_id]
        self._rebuild_V()
        return self._V

    def score_operational(
        self,
        *,
        question_id: str,
        changed_feasible_routing: bool,
        is_mere_delivery: bool = False,
        is_generic_reply: bool = False,
    ) -> float:
        """Operational value only when routing changes; delivery/generic reply worth nothing."""
        if is_mere_delivery or is_generic_reply or not changed_feasible_routing:
            return 0.0
        declared = self._by_operational.get(question_id)
        if declared is None or not declared.routing_change_required:
            return 0.0
        if question_id in self._operational_awarded:
            return 0.0
        self._operational_awarded.add(question_id)
        # Operational value is tracked separately from scientific V for clarity in breakdowns.
        return declared.value_units

    def reward_step(
        self,
        *,
        previous_V: float,
        elapsed_ticks: int,
        cost_units: float,
        contact_units: int,
        unsupported_decisions: int,
        operational_delta: float = 0.0,
        contacted_nodes: tuple[str, ...] = (),
    ) -> RewardBreakdown:
        for node_id in contacted_nodes:
            self.check_exclusion(node_id)
        delta_V = (self._V.total_V - previous_V) + operational_delta
        return compute_toy_reward(
            delta_V=delta_V,
            elapsed_ticks=elapsed_ticks,
            cost_units=cost_units,
            contact_units=contact_units,
            unsupported_decisions=unsupported_decisions,
            weights=self.declaration.weights,
        )

    def resolution_rate(self) -> ReportedRate:
        """Rate of correctly resolved declared questions, with numerator and denominator."""
        total = len(self.declaration.question_values)
        correct = sum(
            1 for q in self.declaration.question_values
            if (fam := self._question_family.get(q.question_id)) is not None
            and fam not in self._invalidated_families
            and self._scored_families[fam].verdict in (
                ResolutionVerdict.CORRECT_SUPPORT, ResolutionVerdict.CORRECT_REJECTION,
            )
        )
        return ReportedRate(
            name="correctly_resolved_questions",
            numerator=correct,
            denominator=total,
        )

    def _rebuild_V(self) -> None:
        self._V = ValueState.from_resolutions(tuple(self._scored_families.values()))

    @staticmethod
    def _verdict_from_latent(
        declared: DeclaredQuestionValue,
        *,
        claimed: ClaimDirection,
        latent_value: str,
    ) -> ResolutionVerdict:
        if claimed is ClaimDirection.UNRESOLVED or claimed is ClaimDirection.NOT_APPLICABLE:
            return ResolutionVerdict.UNRESOLVED
        if latent_value not in declared.correct_when:
            return ResolutionVerdict.UNRESOLVED
        if claimed is ClaimDirection.SUPPORTS:
            if latent_value in declared.support_matches:
                return ResolutionVerdict.CORRECT_SUPPORT
            return ResolutionVerdict.INCORRECT
        if claimed is ClaimDirection.AGAINST:
            if latent_value in declared.rejection_matches:
                return ResolutionVerdict.CORRECT_REJECTION
            return ResolutionVerdict.INCORRECT
        return ResolutionVerdict.UNRESOLVED


def policy_cannot_buy_exclusion(
    scorer: RewardScorer,
    *,
    excluded_node_id: str,
    offered_cost_units: float,
) -> None:
    """Assert exclusions are constraints: paying cost cannot purchase a contact."""
    try:
        scorer.check_exclusion(excluded_node_id)
    except ConstraintViolation:
        # Offering more cost does not open a path — still a constraint.
        if offered_cost_units < 0:
            raise AssertionError("negative cost is not a valid bypass")
        raise
    raise AssertionError("expected ConstraintViolation for excluded node")


def latent_matches_finding(latent: LatentScientificTruth, finding: ScientificFinding) -> bool:
    """Helper for tests: scorers compare scientific findings to latent fields, not policy labels."""
    endpoint = finding.context.endpoint
    if endpoint == "residual_BubR1_function":
        return latent.residual_function.value in ("retained", "defective")
    if endpoint == "NAD" and finding.context.compartment is not None:
        return True
    return finding.origin is Origin.SYNTHETIC
