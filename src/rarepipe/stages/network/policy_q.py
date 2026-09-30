"""Tabular Q-learning over versioned observation states (PRD §13).

This is an inspectable engineering MVP — a bounded observation-state policy. It is NOT a
validated clinical decision model. No convergence or global-optimality claim is made.

Q values estimate simulator utility under the configured reward. They must never be rendered
as drug efficacy probabilities, confidence in a biological claim, or the chance an institution
will help. Algorithm defaults (alpha, gamma, epsilon) are adjustable simulator settings, not
scientific quantities.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from rarepipe.stages.network.model import ImmutableModel
from rarepipe.stages.network.sim.world import PolicyObservation
from rarepipe.stages.prospective.store import content_digest
POLICY_DIGEST_COVERAGE = (
    "policy version, feature contract version, simulator hyperparameter labels, Q-table "
    "keys/values, eligible-action keys, logged selection probabilities; excludes "
    "content_digest itself, latent/scorer fields, and any probability-of-biology framing"
)

FEATURE_CONTRACT_VERSION = "obs-features-v1"
POLICY_ALGORITHM = "tabular_q_observation_state_v1"
SIMULATOR_SETTING_LABEL = "adjustable_simulator_setting_not_scientific_quantity"

# ---------------------------------------------------------------------------
# Shared episode-action contract (owned here; baselines re-export JointAction)
# ---------------------------------------------------------------------------

# Laboratory execution and patient actions are structurally unrepresentable.
_UNREPRESENTABLE_ACTION_TOKENS: frozenset[str] = frozenset({
    "lab_execution",
    "laboratory_execution",
    "execute_lab",
    "run_assay",
    "run_laboratory",
    "patient_action",
    "patient_treatment",
    "treat_patient",
    "prescribe",
    "enroll_patient",
    "clinical_intervention",
    "patient_enrollment",
    "dose_patient",
})


class UnrepresentableActionError(ValueError):
    """Raised when a laboratory or patient action is offered to the action space."""


class ActionKind(StrEnum):
    """Micro/macro joint kinds that ONE learner optimizes. Lab/patient kinds do not exist here."""

    REQUEST_EXISTING_FINDING = "request_existing_finding"
    ASK_CLARIFICATION = "ask_clarification"
    VERIFY_CAPABILITY = "verify_capability"
    VERIFY_REFERRAL = "verify_referral"
    REQUEST_METHOD_FEASIBILITY = "request_method_feasibility"
    REQUEST_LOCAL_ANALYSIS_PROPOSAL = "request_local_analysis_proposal"
    FOLLOW_UP = "follow_up"
    WAIT = "wait"
    PREPARE_SCIENTIFIC_REVIEW = "prepare_scientific_review"
    STOP_ROUTE = "stop_route"
    PAUSE = "pause"


class MacroChoice(StrEnum):
    """Macro half of the joint action (node / route / follow-up / wait)."""

    NODE = "node"
    ROUTE = "route"
    FOLLOW_UP = "follow_up"
    WAIT = "wait"


def _normalize_action_token(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def is_unrepresentable_action_token(value: str) -> bool:
    token = _normalize_action_token(value)
    if token in _UNREPRESENTABLE_ACTION_TOKENS:
        return True
    if "patient" in token:
        return True
    if token.startswith("lab_") or token.startswith("laboratory_"):
        return True
    return False


def require_representable_kind(kind: str) -> ActionKind:
    """Parse an action kind. Patient/lab tokens raise; unknown tokens raise ValueError."""
    if is_unrepresentable_action_token(kind):
        raise UnrepresentableActionError(
            f"action {kind!r} is unrepresentable: laboratory execution and patient actions "
            "are not in the action space"
        )
    try:
        return ActionKind(kind)
    except ValueError as exc:
        # Also catch normalized aliases that are not enum members but look clinical.
        raise ValueError(f"unknown action kind {kind!r}") from exc


def macro_for_kind(kind: ActionKind) -> MacroChoice:
    if kind is ActionKind.WAIT or kind is ActionKind.PAUSE:
        return MacroChoice.WAIT
    if kind is ActionKind.FOLLOW_UP:
        return MacroChoice.FOLLOW_UP
    if kind is ActionKind.STOP_ROUTE or kind is ActionKind.VERIFY_REFERRAL:
        return MacroChoice.ROUTE
    return MacroChoice.NODE


class JointAction(ImmutableModel):
    """Shared episode action: micro (question/clarification/feasibility) + macro (node/route/…).

    Baselines and the learner select from this type so A19 can prove one action space.
    """

    kind: str
    question_id: str
    node_id: str
    rationale: str = ""
    cost_units: float = 0.0
    macro: str | None = None
    content_digest: str | None = None

    @model_validator(mode="after")
    def _representable_and_macro(self):
        parsed = require_representable_kind(self.kind)
        expected_macro = macro_for_kind(parsed).value
        if self.macro is None:
            object.__setattr__(self, "macro", expected_macro)
        elif self.macro != expected_macro:
            raise ValueError(
                f"macro {self.macro!r} inconsistent with kind {self.kind!r} "
                f"(expected {expected_macro!r})"
            )
        return self

    @property
    def action_kind(self) -> ActionKind:
        return ActionKind(self.kind)

    def action_key(self) -> str:
        return f"{self.kind}|{self.question_id}|{self.node_id}|{self.macro}"

    def with_digest(self) -> JointAction:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return JointAction(**data)


# ---------------------------------------------------------------------------
# Simulator hyperparameters (labelled — not scientific quantities)
# ---------------------------------------------------------------------------


class SimulatorHyperparameters(ImmutableModel):
    """Adjustable simulator settings for the tabular learner. Not scientific quantities."""

    alpha: float = 0.1
    gamma: float = 0.95
    epsilon_start: float = 0.2
    epsilon_end: float = 0.05
    label: str = SIMULATOR_SETTING_LABEL

    @model_validator(mode="after")
    def _must_be_labelled(self):
        if self.label != SIMULATOR_SETTING_LABEL:
            raise ValueError(
                "alpha/gamma/epsilon must carry the adjustable_simulator_setting label; "
                "they are not scientific quantities"
            )
        if not (0.0 <= self.alpha <= 1.0):
            raise ValueError("alpha must be in [0, 1]")
        if not (0.0 <= self.gamma <= 1.0):
            raise ValueError("gamma must be in [0, 1]")
        if not (0.0 <= self.epsilon_end <= self.epsilon_start <= 1.0):
            raise ValueError("epsilon must satisfy 0 <= end <= start <= 1")
        return self

    def epsilon_at(self, *, step: int, total_steps: int) -> float:
        """Linear schedule start → end over training. Held-out evaluation uses 0 separately."""
        if total_steps <= 1:
            return self.epsilon_end
        t = min(max(step, 0), total_steps - 1) / (total_steps - 1)
        return self.epsilon_start + t * (self.epsilon_end - self.epsilon_start)


DEFAULT_HYPERPARAMETERS = SimulatorHyperparameters()


# ---------------------------------------------------------------------------
# Versioned observation-state encoder
# ---------------------------------------------------------------------------

# Every bin and feature carries an explicit version string.
_BIN_VERSIONS: dict[str, str] = {
    "question_status": "question_status-v1",
    "missing_prerequisites": "missing_prerequisites-v1",
    "evidence_overlap": "evidence_overlap-v1",
    "node_capability_confirmation": "node_capability_confirmation-v1",
    "permissions": "permissions-v1",
    "requests_in_flight": "requests_in_flight-v1",
    "elapsed_time_bucket": "elapsed_time_bucket-v1",
    "budget_remaining": "budget_remaining-v1",
    "context_compatibility": "context_compatibility-v1",
}


class AuditEvent(ImmutableModel):
    """Full event retained for audit even when the learner uses compressed features."""

    kind: str
    detail: str
    observation_digest: str | None = None


class ObservationState(ImmutableModel):
    """Compressed, versioned observation state. No hidden result labels."""

    feature_contract_version: str = FEATURE_CONTRACT_VERSION
    state_key: str
    features: tuple[tuple[str, str], ...]
    bin_versions: tuple[tuple[str, str], ...]
    event_history: tuple[AuditEvent, ...] = ()
    content_digest: str | None = None

    def with_digest(self) -> ObservationState:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return ObservationState(**data)


def _bucket_elapsed(ticks: int) -> str:
    # Versioned elapsed-time buckets — engineering compression, not scientific exposure.
    if ticks <= 0:
        return "t0"
    if ticks <= 5:
        return "t1_5"
    if ticks <= 20:
        return "t6_20"
    if ticks <= 50:
        return "t21_50"
    return "t51_plus"


def _bucket_remaining(used: float, maximum: float) -> str:
    if maximum <= 0:
        return "max0"
    frac = max(0.0, min(1.0, 1.0 - (used / maximum)))
    if frac >= 0.75:
        return "rem_hi"
    if frac >= 0.25:
        return "rem_mid"
    if frac > 0.0:
        return "rem_lo"
    return "rem_zero"


def encode_observation_state(
    observation: PolicyObservation,
    *,
    ticks_used: int = 0,
    cost_used: float = 0.0,
    max_cost_units: float = 50.0,
    max_ticks: int = 100,
    max_requests: int = 12,
    requests_used: int = 0,
    permission_blocked_nodes: tuple[str, ...] = (),
    prior_history: tuple[AuditEvent, ...] = (),
) -> ObservationState:
    """Encode policy-visible fields into a versioned finite state. Latent labels stay out."""
    answered = sorted({ev.question_id for ev in observation.revealed})
    families = sorted({ev.evidence_family_id for ev in observation.revealed if ev.evidence_family_id})
    overlap = "multi" if len(families) != len(observation.revealed) and len(observation.revealed) > 1 else "none"
    if len(families) > 1 and len(observation.revealed) > len(families):
        overlap = "shared_family"

    in_flight = sorted({
        f"{r.question_id}@{r.node_id}"
        for r in observation.request_states
        if r.state in ("WAITING", "DISPATCHING", "SENT")
    })
    capability = sorted({
        f"{p.node_id}:{p.resource_available}"
        for p in observation.public_profiles
    })
    missing = "none" if answered else "all_open"
    if answered and set(answered) < {"Q01", "Q02", "Q04", "Q05"}:
        missing = "partial"

    permissions = "blocked:" + ",".join(sorted(permission_blocked_nodes)) if permission_blocked_nodes else "open"
    # Context compatibility from public prompts / profiles only — never latent endpoints.
    context = "compatible" if observation.public_profiles else "unknown_context"
    if any("mismatch" in lim for ev in observation.revealed for lim in ev.limitations):
        context = "context_flagged"

    features = (
        (f"{_BIN_VERSIONS['question_status']}|answered", ",".join(answered) or "none"),
        (f"{_BIN_VERSIONS['missing_prerequisites']}|missing", missing),
        (f"{_BIN_VERSIONS['evidence_overlap']}|overlap", overlap),
        (f"{_BIN_VERSIONS['node_capability_confirmation']}|caps", ";".join(capability) or "none"),
        (f"{_BIN_VERSIONS['permissions']}|perm", permissions),
        (f"{_BIN_VERSIONS['requests_in_flight']}|inflight", ",".join(in_flight) or "none"),
        (f"{_BIN_VERSIONS['elapsed_time_bucket']}|elapsed", _bucket_elapsed(ticks_used)),
        (
            f"{_BIN_VERSIONS['budget_remaining']}|budget",
            f"{_bucket_remaining(ticks_used, max_ticks)}|"
            f"{_bucket_remaining(cost_used, max_cost_units)}|"
            f"{_bucket_remaining(requests_used, max_requests)}",
        ),
        (f"{_BIN_VERSIONS['context_compatibility']}|ctx", context),
    )
    material = json.dumps(features, sort_keys=True, separators=(",", ":")).encode()
    state_key = "s:" + hashlib.sha256(material).hexdigest()[:24]
    history = prior_history + (
        AuditEvent(
            kind="encode",
            detail=f"features={len(features)}",
            observation_digest=observation.content_digest,
        ),
    )
    return ObservationState(
        feature_contract_version=FEATURE_CONTRACT_VERSION,
        state_key=state_key,
        features=features,
        bin_versions=tuple(sorted(_BIN_VERSIONS.items())),
        event_history=history,
    ).with_digest()


# ---------------------------------------------------------------------------
# Eligibility masks (permission + scientific gate) — apply BEFORE explore/exploit
# ---------------------------------------------------------------------------


class ScientificGate(ImmutableModel):
    """Hard scientific/operational gate. Ineligible actions are unreachable, not merely costly."""

    blocked_kinds: tuple[str, ...] = ()
    require_evidence_for_review: bool = True
    require_inflight_for_follow_up: bool = True
    require_inflight_for_stop_route: bool = True


DEFAULT_SCIENTIFIC_GATE = ScientificGate()


def enumerate_candidate_actions(
    *,
    eligible_node_ids: tuple[str, ...],
    eligible_question_ids: tuple[str, ...],
    node_costs: dict[str, float] | None = None,
) -> tuple[JointAction, ...]:
    """Cartesian candidates before masks. Costs are synthetic benchmark conventions."""
    costs = node_costs or {}
    out: list[JointAction] = []
    contact_kinds = (
        ActionKind.REQUEST_EXISTING_FINDING,
        ActionKind.ASK_CLARIFICATION,
        ActionKind.VERIFY_CAPABILITY,
        ActionKind.VERIFY_REFERRAL,
        ActionKind.REQUEST_METHOD_FEASIBILITY,
        ActionKind.REQUEST_LOCAL_ANALYSIS_PROPOSAL,
        ActionKind.FOLLOW_UP,
        ActionKind.STOP_ROUTE,
        ActionKind.PREPARE_SCIENTIFIC_REVIEW,
    )
    for node_id in eligible_node_ids:
        for question_id in eligible_question_ids:
            if question_id == "Q00":
                continue
            for kind in contact_kinds:
                out.append(JointAction(
                    kind=kind.value, question_id=question_id, node_id=node_id,
                    rationale="candidate", cost_units=float(costs.get(node_id, 1.0)),
                ).with_digest())
    # Wait / pause are always candidate macros (still subject to budget/permission masks).
    wait_node = eligible_node_ids[0] if eligible_node_ids else "fn-silent-harbour"
    out.append(JointAction(
        kind=ActionKind.WAIT.value, question_id="Q00", node_id=wait_node,
        rationale="candidate_wait", cost_units=0.0,
    ).with_digest())
    out.append(JointAction(
        kind=ActionKind.PAUSE.value, question_id="Q00", node_id=wait_node,
        rationale="candidate_pause", cost_units=0.0,
    ).with_digest())
    return tuple(out)


def apply_eligibility_masks(
    candidates: tuple[JointAction, ...],
    observation: PolicyObservation,
    *,
    allows: Any,
    can_afford: Any,
    gate: ScientificGate = DEFAULT_SCIENTIFIC_GATE,
) -> tuple[JointAction, ...]:
    """Permission and scientific-gate masks. Result is the ONLY set exploration may draw from.

    ``allows(node_id, question_id)`` and ``can_afford(action)`` are callables so this module
    does not depend on baselines types at import time for the mask itself.
    """
    answered = {ev.question_id for ev in observation.revealed}
    in_flight = {
        (r.question_id, r.node_id)
        for r in observation.request_states
        if r.state in ("WAITING", "DISPATCHING", "SENT")
    }
    blocked = set(gate.blocked_kinds)
    eligible: list[JointAction] = []
    for action in candidates:
        if action.kind in blocked:
            continue
        if not allows(action.node_id, action.question_id):
            continue
        kind = ActionKind(action.kind)
        contacts = 0 if kind in (ActionKind.WAIT, ActionKind.PAUSE) else 1
        requests = 0 if kind in (ActionKind.WAIT, ActionKind.PAUSE) else 1
        if not can_afford(action, contacts=contacts, requests=requests):
            continue
        if gate.require_evidence_for_review and kind is ActionKind.PREPARE_SCIENTIFIC_REVIEW:
            if not observation.revealed:
                continue
        if gate.require_inflight_for_follow_up and kind is ActionKind.FOLLOW_UP:
            if (action.question_id, action.node_id) not in in_flight and action.question_id not in answered:
                continue
        if gate.require_inflight_for_stop_route and kind is ActionKind.STOP_ROUTE:
            if (action.question_id, action.node_id) not in in_flight:
                continue
        eligible.append(action)
    return tuple(eligible)


# ---------------------------------------------------------------------------
# Q-table persistence and decision logging
# ---------------------------------------------------------------------------


class QEntry(ImmutableModel):
    state_key: str
    action_key: str
    value: float


class PersistedQParameters(ImmutableModel):
    """Persisted tabular parameters. Digest covers keys/values; excludes the digest field."""

    algorithm: str = POLICY_ALGORITHM
    feature_contract_version: str = FEATURE_CONTRACT_VERSION
    hyperparameters: SimulatorHyperparameters = Field(default_factory=SimulatorHyperparameters)
    entries: tuple[QEntry, ...] = ()
    update_count: int = 0
    training_events: int = 0
    content_digest: str | None = None
    digest_coverage: str = POLICY_DIGEST_COVERAGE

    def with_digest(self) -> PersistedQParameters:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return PersistedQParameters(**data)

    def as_table(self) -> dict[tuple[str, str], float]:
        return {(e.state_key, e.action_key): e.value for e in self.entries}


class PolicyDecision(ImmutableModel):
    """Decision record with propensity logged at selection time (never reconstructed later)."""

    policy_id: str
    state_key: str
    observation_digest: str | None
    selected: JointAction | None
    eligible_action_keys: tuple[str, ...]
    selection_probability: float | None = None
    randomized: bool = False
    epsilon: float
    mode: Literal["train", "development", "held_out", "shadow"] = "train"
    q_value: float | None = None
    stopped: bool = False
    stop_reason: str | None = None
    content_digest: str | None = None

    @model_validator(mode="after")
    def _propensity_logged(self):
        if self.selected is not None:
            if self.selection_probability is None:
                raise ValueError("selection_probability must be logged at decision time")
            if not (0.0 < self.selection_probability <= 1.0):
                raise ValueError("selection_probability must be in (0, 1]")
            if self.selected.action_key() not in self.eligible_action_keys:
                raise ValueError("selected action must be among eligible keys")
        return self

    def with_digest(self) -> PolicyDecision:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return PolicyDecision(**data)


class ShadowRecommendation(ImmutableModel):
    """Authentic-campaign shadow: recommendation stored alongside actual action; never dispatched."""

    campaign_id: str
    recommendation: JointAction
    actual_authorized_action: JointAction | None = None
    decision: PolicyDecision
    dispatched: Literal[False] = False
    content_digest: str | None = None

    @field_validator("dispatched")
    @classmethod
    def _never_dispatch(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError("shadow mode must not dispatch")
        return False

    def with_digest(self) -> ShadowRecommendation:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return ShadowRecommendation(**data)


class TrainingEvent(ImmutableModel):
    """Explicit training event. Data ingestion alone is not an RL update."""

    event_id: str
    reward: float
    state_key: str
    action_key: str
    next_state_key: str
    terminal: bool
    split_role: Literal["train", "development"]
    content_digest: str | None = None

    @model_validator(mode="after")
    def _no_held_out(self):
        # Held-out families are evaluation-only; fitting on them is rejected here.
        return self

    def with_digest(self) -> TrainingEvent:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return TrainingEvent(**data)


class IngestionOnlyFeedback(ImmutableModel):
    """Feedback received from ingestion. Does not update Q parameters by itself."""

    campaign_id: str
    payload_digest: str
    applied_rl_update: Literal[False] = False


# ---------------------------------------------------------------------------
# Reporting boundary — Q is simulator utility, never a biological/institutional probability
# ---------------------------------------------------------------------------

_FORBIDDEN_Q_FRAMES: frozenset[str] = frozenset({
    "drug_efficacy",
    "efficacy_probability",
    "biological_confidence",
    "confidence_in_biological_claim",
    "institution_will_help",
    "chance_institution_helps",
    "probability_of_help",
    "clinical_probability",
    "patient_benefit_probability",
})


class QReportingError(ValueError):
    """Raised when a caller tries to frame a Q value as a biological/institutional probability."""


def format_q_as_simulator_utility(q_value: float) -> str:
    """Reporting boundary: Q is simulator utility under the configured reward only."""
    if not math.isfinite(q_value):
        raise QReportingError("Q value must be finite simulator utility")
    return (
        f"simulator_utility_estimate={q_value:.6f} "
        f"(bounded observation-state policy under configured synthetic reward; "
        f"not a probability of biological or institutional outcome)"
    )


def render_q_value(q_value: float, *, frame: str = "simulator_utility") -> str:
    """Only the simulator-utility frame is permitted at the reporting boundary."""
    token = _normalize_action_token(frame)
    if token in _FORBIDDEN_Q_FRAMES or "probability" in token or "efficacy" in token:
        raise QReportingError(
            f"refusing to render Q value as {frame!r}: Q estimates simulator utility only, "
            "never drug efficacy, biological confidence, or institutional help probability"
        )
    if token not in {"simulator_utility", "simulator_utility_estimate", "q_simulator_utility"}:
        raise QReportingError(
            f"unknown Q reporting frame {frame!r}; use simulator_utility"
        )
    return format_q_as_simulator_utility(q_value)


# ---------------------------------------------------------------------------
# Tabular Q-learner (single joint learner)
# ---------------------------------------------------------------------------


class TabularQPolicy:
    """One tabular learner over joint micro+macro actions. Shadow by default on authentic campaigns.

    Report as a bounded observation-state policy. No convergence or optimality claim.
    """

    policy_id: str = "tabular_q_observation_state_v1"

    def __init__(
        self,
        *,
        hyperparameters: SimulatorHyperparameters | None = None,
        scientific_gate: ScientificGate | None = None,
        master_seed: int = 0,
        world_id: str = "policy-world",
    ):
        self.hyperparameters = hyperparameters or DEFAULT_HYPERPARAMETERS
        self.scientific_gate = scientific_gate or DEFAULT_SCIENTIFIC_GATE
        self.master_seed = master_seed
        self.world_id = world_id
        self._q: dict[tuple[str, str], float] = {}
        self._update_count = 0
        self._training_events = 0
        self._decision_count = 0
        self._shadow_log: list[ShadowRecommendation] = []
        self._audit: list[AuditEvent] = []
        # Import here to break the baselines ↔ policy_q import cycle at module load.
        from rarepipe.stages.network.sim.splits import KeyedExogenousRNG
        self._rng = KeyedExogenousRNG(master_seed, world_id=world_id)

    def q_get(self, state_key: str, action_key: str) -> float:
        return self._q.get((state_key, action_key), 0.0)

    def parameter_snapshot(self) -> PersistedQParameters:
        entries = tuple(
            QEntry(state_key=s, action_key=a, value=v)
            for (s, a), v in sorted(self._q.items())
        )
        return PersistedQParameters(
            hyperparameters=self.hyperparameters,
            entries=entries,
            update_count=self._update_count,
            training_events=self._training_events,
        ).with_digest()

    def load_parameters(self, params: PersistedQParameters) -> None:
        self._q = params.as_table()
        self._update_count = params.update_count
        self._training_events = params.training_events
        self.hyperparameters = params.hyperparameters

    def persist(self) -> PersistedQParameters:
        return self.parameter_snapshot()

    def epsilon_for(
        self,
        *,
        mode: Literal["train", "development", "held_out", "shadow"],
        step: int = 0,
        total_steps: int = 1,
    ) -> float:
        if mode in ("held_out", "shadow"):
            return 0.0
        return self.hyperparameters.epsilon_at(step=step, total_steps=total_steps)

    def eligible_joint_actions(
        self,
        observation: PolicyObservation,
        budget: Any,
        constraints: Any,
        *,
        node_costs: dict[str, float] | None = None,
    ) -> tuple[JointAction, ...]:
        candidates = enumerate_candidate_actions(
            eligible_node_ids=tuple(constraints.eligible_node_ids),
            eligible_question_ids=tuple(constraints.eligible_question_ids),
            node_costs=node_costs,
        )

        def allows(node_id: str, question_id: str) -> bool:
            return constraints.allows(node_id, question_id)

        def can_afford(action: JointAction, *, contacts: int, requests: int) -> bool:
            return budget.can_afford(
                cost=action.cost_units, contacts=contacts, requests=requests,
            )

        return apply_eligibility_masks(
            candidates, observation, allows=allows, can_afford=can_afford,
            gate=self.scientific_gate,
        )

    def select(
        self,
        observation: PolicyObservation,
        budget: Any,
        constraints: Any,
        *,
        mode: Literal["train", "development", "held_out", "shadow"] = "train",
        step: int = 0,
        total_steps: int = 2000,
        node_costs: dict[str, float] | None = None,
        ticks_used: int | None = None,
    ) -> PolicyDecision:
        """Epsilon-greedy over the eligibility-masked set only. Propensity logged now."""
        eligible = self.eligible_joint_actions(
            observation, budget, constraints, node_costs=node_costs,
        )
        state = encode_observation_state(
            observation,
            ticks_used=budget.ticks_used if ticks_used is None else ticks_used,
            cost_used=budget.cost_used,
            max_cost_units=budget.max_cost_units,
            max_ticks=budget.max_ticks,
            max_requests=budget.max_requests,
            requests_used=budget.requests_used,
            permission_blocked_nodes=tuple(constraints.permission_blocked_nodes),
            prior_history=tuple(self._audit),
        )
        self._audit = list(state.event_history)
        keys = tuple(a.action_key() for a in eligible)
        if not eligible:
            return PolicyDecision(
                policy_id=self.policy_id, state_key=state.state_key,
                observation_digest=observation.content_digest, selected=None,
                eligible_action_keys=(), selection_probability=None, randomized=False,
                epsilon=self.epsilon_for(mode=mode, step=step, total_steps=total_steps),
                mode=mode, stopped=True, stop_reason="no_eligible_action",
            ).with_digest()

        epsilon = self.epsilon_for(mode=mode, step=step, total_steps=total_steps)
        self._decision_count += 1
        # Deterministic draw keyed by world + decision index — not process hash() / wall clock.
        u = self._rng.draw_u01(
            node_id="policy", question_id="select",
            event=f"decision|{self._decision_count}|{state.state_key}",
        )
        n = len(eligible)
        scored = [(self.q_get(state.state_key, a.action_key()), a) for a in eligible]
        best_q = max(s for s, _ in scored)
        tied = [a for s, a in scored if s == best_q]
        tied_keys = {a.action_key() for a in tied}

        explore = epsilon > 0.0 and u < epsilon
        if explore:
            u2 = self._rng.draw_u01(
                node_id="policy", question_id="explore",
                event=f"explore|{self._decision_count}|{state.state_key}",
            )
            idx = min(int(u2 * n), n - 1)
            chosen = eligible[idx]
            randomized = True
        else:
            if len(tied) == 1:
                chosen = tied[0]
            else:
                u3 = self._rng.draw_u01(
                    node_id="policy", question_id="tiebreak",
                    event=f"tie|{self._decision_count}|{state.state_key}",
                )
                idx = min(int(u3 * len(tied)), len(tied) - 1)
                chosen = tied[idx]
            randomized = epsilon > 0.0 or len(tied) > 1

        # True mixture propensity at decision time — never reconstructed afterwards.
        propensity = epsilon / n
        if chosen.action_key() in tied_keys:
            propensity += (1.0 - epsilon) / len(tied)
        if epsilon == 0.0 and len(tied) == 1:
            randomized = False
            propensity = 1.0

        return PolicyDecision(
            policy_id=self.policy_id,
            state_key=state.state_key,
            observation_digest=observation.content_digest,
            selected=chosen,
            eligible_action_keys=keys,
            selection_probability=propensity,
            randomized=randomized,
            epsilon=epsilon,
            mode=mode,
            q_value=self.q_get(state.state_key, chosen.action_key()),
        ).with_digest()

    def max_eligible_q(self, state_key: str, eligible: tuple[JointAction, ...]) -> float:
        if not eligible:
            return 0.0
        return max(self.q_get(state_key, a.action_key()) for a in eligible)

    def apply_training_update(
        self,
        event: TrainingEvent,
        *,
        eligible_next: tuple[JointAction, ...],
    ) -> float:
        """Explicit training event + eligible feedback. Ingestion alone must not call this."""
        if event.split_role not in ("train", "development"):
            raise ValueError("Q updates are forbidden on held-out splits")
        s, a = event.state_key, event.action_key
        q_sa = self.q_get(s, a)
        future = 0.0 if event.terminal else self.max_eligible_q(event.next_state_key, eligible_next)
        alpha = self.hyperparameters.alpha
        gamma = self.hyperparameters.gamma
        target = event.reward + gamma * future
        new_q = q_sa + alpha * (target - q_sa)
        self._q[(s, a)] = new_q
        self._update_count += 1
        self._training_events += 1
        return new_q

    def ingest_feedback_without_update(self, *, campaign_id: str, payload: dict[str, Any]) -> IngestionOnlyFeedback:
        """Data ingestion alone is not an RL update."""
        digest = content_digest(payload)
        return IngestionOnlyFeedback(
            campaign_id=campaign_id, payload_digest=digest, applied_rl_update=False,
        )

    def shadow_recommend(
        self,
        observation: PolicyObservation,
        budget: Any,
        constraints: Any,
        *,
        campaign_id: str,
        actual_authorized_action: JointAction | None = None,
        node_costs: dict[str, float] | None = None,
    ) -> ShadowRecommendation:
        """Store a recommendation alongside the actual authorized action; never dispatch."""
        decision = self.select(
            observation, budget, constraints, mode="shadow",
            step=0, total_steps=1, node_costs=node_costs,
        )
        if decision.selected is None:
            # Shadow still records a sentinel wait recommendation when nothing is eligible.
            wait = JointAction(
                kind=ActionKind.WAIT.value, question_id="Q00",
                node_id=constraints.eligible_node_ids[0] if constraints.eligible_node_ids else "fn-silent-harbour",
                rationale="shadow_no_eligible", cost_units=0.0,
            ).with_digest()
            recommendation = wait
        else:
            recommendation = decision.selected
        rec = ShadowRecommendation(
            campaign_id=campaign_id,
            recommendation=recommendation,
            actual_authorized_action=actual_authorized_action,
            decision=decision,
            dispatched=False,
        ).with_digest()
        self._shadow_log.append(rec)
        return rec

    @property
    def shadow_log(self) -> tuple[ShadowRecommendation, ...]:
        return tuple(self._shadow_log)


def make_training_event(
    *,
    reward: float,
    state_key: str,
    action_key: str,
    next_state_key: str,
    terminal: bool,
    split_role: Literal["train", "development"] = "train",
    master_seed: int,
    serial: int,
) -> TrainingEvent:
    """Generate a training-event id in code (never hand-typed digests)."""
    material = f"{master_seed}|train-event|{serial}|{state_key}|{action_key}".encode()
    event_id = "te-" + hashlib.sha256(material).hexdigest()[:16]
    return TrainingEvent(
        event_id=event_id, reward=reward, state_key=state_key, action_key=action_key,
        next_state_key=next_state_key, terminal=terminal, split_role=split_role,
    ).with_digest()


def run_declared_reward_training(
    policy: TabularQPolicy,
    *,
    transitions: list[tuple[PolicyObservation, Any, Any, float, bool]],
    total_steps: int | None = None,
    split_role: Literal["train", "development"] = "train",
    node_costs: dict[str, float] | None = None,
) -> PersistedQParameters:
    """Train from declared reward scalars produced by ``RewardScorer.reward_step``.

    Each transition is ``(observation, budget, constraints, reward, terminal)``. The scorer
    owns the verdict; this loop only consumes the declared reward. Held-out fitting is refused.
    """
    if split_role not in ("train", "development"):
        raise ValueError("cannot train on held-out families")
    n = total_steps or max(len(transitions), 1)
    mode: Literal["train", "development"] = "train" if split_role == "train" else "development"
    for i, (obs, budget, constraints, reward, terminal) in enumerate(transitions):
        decision = policy.select(
            obs, budget, constraints, mode=mode, step=i, total_steps=n, node_costs=node_costs,
        )
        if decision.selected is None:
            continue
        # Next-state encoding without a second select (avoids burning RNG / epsilon schedule).
        next_state = encode_observation_state(
            obs,
            ticks_used=budget.ticks_used + (0 if terminal else 1),
            cost_used=budget.cost_used + (decision.selected.cost_units if not terminal else 0.0),
            max_cost_units=budget.max_cost_units,
            max_ticks=budget.max_ticks,
            max_requests=budget.max_requests,
            requests_used=budget.requests_used + (0 if decision.selected.kind in (
                ActionKind.WAIT.value, ActionKind.PAUSE.value,
            ) else 1),
            permission_blocked_nodes=tuple(constraints.permission_blocked_nodes),
        )
        eligible_next = () if terminal else policy.eligible_joint_actions(
            obs, budget, constraints, node_costs=node_costs,
        )
        event = make_training_event(
            reward=reward, state_key=decision.state_key,
            action_key=decision.selected.action_key(),
            next_state_key=next_state.state_key, terminal=terminal,
            split_role=split_role, master_seed=policy.master_seed, serial=i,
        )
        policy.apply_training_update(event, eligible_next=eligible_next)
    return policy.persist()

class PairedPolicyRunner:
    """A19: learner and both baselines receive the same observation and budget snapshots."""

    def __init__(
        self,
        *,
        policy: TabularQPolicy | None = None,
        budget: Any = None,
        constraints: Any = None,
    ):
        from rarepipe.stages.network.sim.baselines import (
            EligibleNodeHeuristicBaseline, FixedExpertSequenceBaseline,
            default_constraints, default_shared_budget,
        )
        self.policy = policy or TabularQPolicy(master_seed=20260930, world_id="paired")
        self.expert = FixedExpertSequenceBaseline()
        self.heuristic = EligibleNodeHeuristicBaseline()
        self.budget_template = budget or default_shared_budget()
        self.constraints = constraints or default_constraints()

    def shared_inputs(self) -> dict[str, object]:
        return {
            "budget": self.budget_template.model_dump(mode="json"),
            "constraints": self.constraints.model_dump(mode="json"),
        }

    def decide_all(self, observation: PolicyObservation) -> tuple[PolicyDecision, Any, Any]:
        budget_l = self.budget_template.remaining()
        budget_e = self.budget_template.remaining()
        budget_h = self.budget_template.remaining()
        assert budget_l.model_dump() == budget_e.model_dump() == budget_h.model_dump()
        learner_d = self.policy.select(observation, budget_l, self.constraints, mode="held_out")
        expert_d = self.expert.select(observation, budget_e, self.constraints)
        heur_d = self.heuristic.select(observation, budget_h, self.constraints)
        assert expert_d.observation_digest == heur_d.observation_digest == observation.content_digest
        assert learner_d.observation_digest == observation.content_digest
        assert expert_d.budget.model_dump() == heur_d.budget.model_dump() == budget_l.model_dump()
        assert expert_d.constraints == heur_d.constraints == self.constraints
        # Shared action space: baseline actions are JointAction instances.
        if expert_d.action is not None:
            assert isinstance(expert_d.action, JointAction)
        if heur_d.action is not None:
            assert isinstance(heur_d.action, JointAction)
        return learner_d, expert_d, heur_d

    def reset(self) -> None:
        self.expert.reset()
        self.heuristic.reset()
