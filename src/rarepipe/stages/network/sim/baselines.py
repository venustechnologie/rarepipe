"""Fixed expert and eligible-node heuristic baselines (PRD §13.4).

Both baselines are defined before evaluation and receive the SAME observable information,
constraints and resource budget as the learner. Do not weaken them: the sequence and the
heuristic scoring rule are explicit named constants so a weakening change is visible in a diff.

The shared episode-action type lives in ``network.policy_q`` (T10). Baselines re-export it so
the learner and both baselines are provably selecting from one action space (A19).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rarepipe.stages.network.model import ImmutableModel
from rarepipe.stages.network.policy_q import ActionKind, JointAction
from rarepipe.stages.network.sim.world import PolicyObservation
from rarepipe.stages.prospective.store import content_digest

# Shared episode-action contract — owned by policy_q; aliased here for baseline call sites.
BaselineAction = JointAction

BASELINE_DIGEST_COVERAGE = (
    "baseline id, action kinds, question/node ids, shared budget remaining, observation "
    "content_digest, constraint tokens; excludes content_digest itself and any latent fields"
)

# --- Explicit baseline contracts. Weakening these constants is a visible diff. ---

# Fixed expert-designed sequence for the toy MVA synthetic campaign.
# Order is intentional: residual-function before NAD compartment before functional outcomes,
# operational capability check before costly assay nodes. Do not shorten or shuffle to
# make a learner look better.
EXPERT_SEQUENCE: tuple[tuple[str, str, str], ...] = (
    ("request_existing_finding", "Q01", "fn-northbridge-cell"),
    ("request_existing_finding", "Q02", "fn-cedar-nad"),
    ("verify_capability", "Q05", "fn-redrock-access"),
    ("request_existing_finding", "Q04", "fn-northbridge-cell"),
    ("verify_referral", "Q05", "fn-holloway-mitotic"),
    ("wait", "Q00", "fn-silent-harbour"),
)

# Eligible-node heuristic: prefer confirmed-capable, low-cost, unanswered questions.
# Scores are SYNTHETIC BENCHMARK CONVENTION ranks, not clinical priorities.
HEURISTIC_ACTION_PRIORITY: tuple[str, ...] = (
    "request_existing_finding",
    "verify_capability",
    "verify_referral",
    "ask_clarification",
    "follow_up",
    "wait",
    "pause",
)

HEURISTIC_NODE_COST_UNITS: dict[str, float] = {
    "fn-northbridge-cell": 1.0,
    "fn-cedar-nad": 1.5,
    "fn-holloway-mitotic": 1.0,
    "fn-redrock-access": 0.5,
    "fn-silent-harbour": 1.0,
    "fn-glassford-refuse": 0.5,
    "fn-willow-partner": 0.5,
    "fn-lowland-qc": 2.0,
}


class SharedResourceBudget(ImmutableModel):
    """Identical budget envelope for learner and both baselines (A19)."""

    max_ticks: int
    max_cost_units: float
    max_contact_units: int
    max_requests: int
    ticks_used: int = 0
    cost_used: float = 0.0
    contacts_used: int = 0
    requests_used: int = 0

    def remaining(self) -> SharedResourceBudget:
        return SharedResourceBudget(
            max_ticks=self.max_ticks, max_cost_units=self.max_cost_units,
            max_contact_units=self.max_contact_units, max_requests=self.max_requests,
            ticks_used=self.ticks_used, cost_used=self.cost_used,
            contacts_used=self.contacts_used, requests_used=self.requests_used,
        )

    def can_afford(self, *, cost: float = 0.0, contacts: int = 1, requests: int = 1) -> bool:
        if self.requests_used + requests > self.max_requests:
            return False
        if self.contacts_used + contacts > self.max_contact_units:
            return False
        if self.cost_used + cost > self.max_cost_units:
            return False
        if self.ticks_used >= self.max_ticks:
            return False
        return True

    def consume(self, *, ticks: int = 0, cost: float = 0.0, contacts: int = 0, requests: int = 0) -> SharedResourceBudget:
        return SharedResourceBudget(
            max_ticks=self.max_ticks, max_cost_units=self.max_cost_units,
            max_contact_units=self.max_contact_units, max_requests=self.max_requests,
            ticks_used=self.ticks_used + ticks,
            cost_used=self.cost_used + cost,
            contacts_used=self.contacts_used + contacts,
            requests_used=self.requests_used + requests,
        )


class EpisodeConstraints(ImmutableModel):
    """Hard exclusions and permission masks shared with the learner."""

    excluded_node_ids: tuple[str, ...] = ()
    eligible_node_ids: tuple[str, ...] = ()
    eligible_question_ids: tuple[str, ...] = ()
    permission_blocked_nodes: tuple[str, ...] = ()

    def allows(self, node_id: str, question_id: str) -> bool:
        if node_id in self.excluded_node_ids:
            return False
        if node_id in self.permission_blocked_nodes:
            return False
        if self.eligible_node_ids and node_id not in self.eligible_node_ids:
            return False
        if self.eligible_question_ids and question_id not in self.eligible_question_ids:
            return False
        return True


class BaselineDecision(ImmutableModel):
    baseline_id: str
    action: JointAction | None
    observation_digest: str | None
    budget: SharedResourceBudget
    constraints: EpisodeConstraints
    stopped: bool = False
    stop_reason: str | None = None
    content_digest: str | None = None

    def with_digest(self) -> BaselineDecision:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return BaselineDecision(**data)


@runtime_checkable
class BaselinePolicy(Protocol):
    baseline_id: str

    def select(
        self,
        observation: PolicyObservation,
        budget: SharedResourceBudget,
        constraints: EpisodeConstraints,
    ) -> BaselineDecision: ...


def default_shared_budget() -> SharedResourceBudget:
    """Engineering toy budget — identical for all compared policies."""
    return SharedResourceBudget(
        max_ticks=100, max_cost_units=50.0, max_contact_units=20, max_requests=12,
    )


def default_constraints() -> EpisodeConstraints:
    return EpisodeConstraints(
        excluded_node_ids=("excluded-mva-society", "excluded-family", "excluded-child"),
        eligible_node_ids=(
            "fn-northbridge-cell", "fn-cedar-nad", "fn-holloway-mitotic",
            "fn-redrock-access", "fn-silent-harbour", "fn-glassford-refuse",
            "fn-willow-partner", "fn-lowland-qc",
        ),
        eligible_question_ids=("Q01", "Q02", "Q04", "Q05", "Q06", "Q00"),
        permission_blocked_nodes=(),
    )


class FixedExpertSequenceBaseline:
    """(1) Fixed expert-designed sequence. Defined before any evaluation."""

    baseline_id: str = "fixed_expert_sequence_v1"

    def __init__(self, sequence: tuple[tuple[str, str, str], ...] = EXPERT_SEQUENCE):
        # Sequence is a required constructor argument defaulting to the named constant.
        # Replacing EXPERT_SEQUENCE with a weaker list is a visible source change.
        self.sequence = sequence
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    def select(
        self,
        observation: PolicyObservation,
        budget: SharedResourceBudget,
        constraints: EpisodeConstraints,
    ) -> BaselineDecision:
        obs_digest = observation.content_digest
        while self._cursor < len(self.sequence):
            kind, question_id, node_id = self.sequence[self._cursor]
            self._cursor += 1
            if not constraints.allows(node_id, question_id):
                continue
            cost = HEURISTIC_NODE_COST_UNITS.get(node_id, 1.0)
            if kind == ActionKind.WAIT.value:
                cost = 0.0
                contacts = 0
            else:
                contacts = 1
            if not budget.can_afford(cost=cost, contacts=contacts, requests=0 if kind == "wait" else 1):
                return BaselineDecision(
                    baseline_id=self.baseline_id, action=None, observation_digest=obs_digest,
                    budget=budget, constraints=constraints, stopped=True,
                    stop_reason="shared_budget_exhausted",
                ).with_digest()
            action = JointAction(
                kind=kind, question_id=question_id, node_id=node_id,
                rationale="expert_sequence_step", cost_units=cost,
            ).with_digest()
            return BaselineDecision(
                baseline_id=self.baseline_id, action=action, observation_digest=obs_digest,
                budget=budget, constraints=constraints,
            ).with_digest()
        return BaselineDecision(
            baseline_id=self.baseline_id, action=None, observation_digest=obs_digest,
            budget=budget, constraints=constraints, stopped=True,
            stop_reason="expert_sequence_complete",
        ).with_digest()


class EligibleNodeHeuristicBaseline:
    """(2) Simple eligible-node routing heuristic. Same observations/budget as the expert."""

    baseline_id: str = "eligible_node_heuristic_v1"

    def __init__(
        self,
        *,
        action_priority: tuple[str, ...] = HEURISTIC_ACTION_PRIORITY,
        node_costs: dict[str, float] | None = None,
    ):
        self.action_priority = action_priority
        self.node_costs = dict(node_costs or HEURISTIC_NODE_COST_UNITS)
        self._issued: set[tuple[str, str]] = set()

    def reset(self) -> None:
        self._issued.clear()

    def select(
        self,
        observation: PolicyObservation,
        budget: SharedResourceBudget,
        constraints: EpisodeConstraints,
    ) -> BaselineDecision:
        obs_digest = observation.content_digest
        answered = {ev.question_id for ev in observation.revealed}
        in_flight = {
            (r.question_id, r.node_id) for r in observation.request_states
            if r.state in ("WAITING", "DISPATCHING", "SENT")
        }
        candidates: list[tuple[float, JointAction]] = []
        for node_id in constraints.eligible_node_ids:
            for question_id in constraints.eligible_question_ids:
                if question_id == "Q00":
                    continue
                if not constraints.allows(node_id, question_id):
                    continue
                if (question_id, node_id) in self._issued or (question_id, node_id) in in_flight:
                    continue
                if question_id in answered and not _needs_follow_up(observation, question_id, node_id):
                    continue
                kind = self._choose_kind(observation, question_id, node_id, answered)
                cost = self.node_costs.get(node_id, 1.0)
                if not budget.can_afford(cost=cost, contacts=1, requests=1):
                    continue
                score = self._score(kind, node_id, question_id, answered)
                action = JointAction(
                    kind=kind, question_id=question_id, node_id=node_id,
                    rationale=f"heuristic_score={score}", cost_units=cost,
                ).with_digest()
                candidates.append((score, action))
        if not candidates:
            if budget.can_afford(cost=0.0, contacts=0, requests=0) and budget.ticks_used < budget.max_ticks:
                wait = JointAction(
                    kind=ActionKind.WAIT.value, question_id="Q00", node_id="fn-silent-harbour",
                    rationale="heuristic_wait_no_eligible", cost_units=0.0,
                ).with_digest()
                return BaselineDecision(
                    baseline_id=self.baseline_id, action=wait, observation_digest=obs_digest,
                    budget=budget, constraints=constraints,
                ).with_digest()
            return BaselineDecision(
                baseline_id=self.baseline_id, action=None, observation_digest=obs_digest,
                budget=budget, constraints=constraints, stopped=True,
                stop_reason="no_eligible_action",
            ).with_digest()
        candidates.sort(key=lambda item: (-item[0], item[1].question_id, item[1].node_id))
        best = candidates[0][1]
        self._issued.add((best.question_id, best.node_id))
        return BaselineDecision(
            baseline_id=self.baseline_id, action=best, observation_digest=obs_digest,
            budget=budget, constraints=constraints,
        ).with_digest()

    def _choose_kind(
        self,
        observation: PolicyObservation,
        question_id: str,
        node_id: str,
        answered: set[str],
    ) -> str:
        if question_id == "Q05":
            return ActionKind.VERIFY_CAPABILITY.value
        if node_id == "fn-holloway-mitotic":
            return ActionKind.VERIFY_REFERRAL.value
        if question_id in answered:
            return ActionKind.FOLLOW_UP.value
        return ActionKind.REQUEST_EXISTING_FINDING.value

    def _score(self, kind: str, node_id: str, question_id: str, answered: set[str]) -> float:
        # Higher is better. Explicit formula — weakening (e.g. dropping cost term) is a visible diff.
        try:
            action_rank = len(self.action_priority) - self.action_priority.index(kind)
        except ValueError:
            action_rank = 0
        cost = self.node_costs.get(node_id, 1.0)
        unanswered_bonus = 2.0 if question_id not in answered else 0.0
        return float(action_rank) + unanswered_bonus - 0.1 * cost


def _needs_follow_up(observation: PolicyObservation, question_id: str, node_id: str) -> bool:
    for req in observation.request_states:
        if req.question_id == question_id and req.node_id == node_id and req.state == "WAITING":
            return True
    return False


class PairedBaselineRunner:
    """Run both baselines on identical observations, constraints and budgets (A19)."""

    def __init__(
        self,
        *,
        expert: FixedExpertSequenceBaseline | None = None,
        heuristic: EligibleNodeHeuristicBaseline | None = None,
        budget: SharedResourceBudget | None = None,
        constraints: EpisodeConstraints | None = None,
    ):
        self.expert = expert or FixedExpertSequenceBaseline()
        self.heuristic = heuristic or EligibleNodeHeuristicBaseline()
        self.budget_template = budget or default_shared_budget()
        self.constraints = constraints or default_constraints()

    def shared_inputs(self) -> dict[str, object]:
        """Inputs both baselines must receive. Equality is part of the A19 contract."""
        return {
            "budget": self.budget_template.model_dump(mode="json"),
            "constraints": self.constraints.model_dump(mode="json"),
        }

    def decide_both(self, observation: PolicyObservation) -> tuple[BaselineDecision, BaselineDecision]:
        budget_a = self.budget_template.remaining()
        budget_b = self.budget_template.remaining()
        # Same observation object, same constraint record, equal budget snapshots.
        assert budget_a.model_dump() == budget_b.model_dump()
        expert_decision = self.expert.select(observation, budget_a, self.constraints)
        heuristic_decision = self.heuristic.select(observation, budget_b, self.constraints)
        assert expert_decision.observation_digest == heuristic_decision.observation_digest
        assert expert_decision.constraints == heuristic_decision.constraints
        assert expert_decision.budget.model_dump() == heuristic_decision.budget.model_dump()
        return expert_decision, heuristic_decision

    def reset(self) -> None:
        self.expert.reset()
        self.heuristic.reset()
