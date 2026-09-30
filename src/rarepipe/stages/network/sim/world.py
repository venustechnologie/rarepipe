"""Bounded research world: latent science, observation adapter, virtual-time events.

Policies receive only :class:`PolicyObservation`. Latent truth lives on the world object under a
scorer-only accessor and is structurally excluded from the policy view type.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import zlib
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, runtime_checkable

from pydantic import ConfigDict, Field, ValidationError, model_validator

from rarepipe.stages.network.model import (
    AdditionalResponseState, Campaign, CampaignMode, CampaignScope, ClaimDirection, ClaimRelation,
    Compartment, Contribution, EvidenceCriteria, ImmutableModel, Intervention, LearningFeedback,
    NetworkEnvelope, OperationalResponse, Origin, Question, Restrictions, ScientificFinding, new_id,
)
from rarepipe.stages.network.sim.institution import (
    AssumptionLabel, FictionalNode, InstitutionalOutcome, InstitutionalProcessGenerator,
    LabeledParam, PublicCatalogueEntry, ReplyDisposition, assert_no_real_institution_in_synthetic_text,
    fictional_network, public_capability_catalogue,
)
from rarepipe.stages.prospective import rules
from rarepipe.stages.prospective.model import Actor, ActorType, Knowledge, Quantity, Role
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.store import content_digest

# Keys / substrings that must never appear on a policy-facing object graph.
LATENT_KEY_MARKERS: frozenset[str] = frozenset({
    "latent", "latent_truth", "hidden", "hidden_truth", "ground_truth", "oracle",
    "sim_truth", "true_effect", "true_availability", "true_permission", "residual_function",
    "compartment_truth", "selection_effect", "downstream_truth", "scorer_only",
})

POLICY_VIEW_DIGEST_COVERAGE = (
    "policy-visible fields only: campaign_id, revealed intake events, public profiles, "
    "request states, prompts, feature pairs, ui payload, reward explanation text; "
    "excludes content_digest itself and any latent/scorer fields"
)

WORLD_CONTENT_DIGEST_COVERAGE = (
    "scenario-facing synthetic content: configuration, assumption params, fictional node ids, "
    "revealed intake event digests, scheduled event kinds/ticks; excludes content_digest, "
    "process paths, wall-clock timestamps, and latent truth values"
)


def derive_stream_seed(master: int, *parts: str) -> int:
    """Stable across processes. Do not use Python's randomized ``hash()``."""
    material = "|".join((str(master), *parts)).encode()
    return zlib.crc32(material) & 0xFFFFFFFF


def deterministic_id(master: int, *parts: str) -> str:
    """Stable synthetic identifier. Never hand-typed; derived from the master seed."""
    material = "|".join((str(master), *parts)).encode()
    return "syn-" + hashlib.sha256(material).hexdigest()[:16]


class SeedBank:
    """Named RNG streams from one master seed, with collision detection."""

    def __init__(self, master_seed: int):
        self.master_seed = master_seed
        self._by_name: dict[str, int] = {}
        self._by_value: dict[int, str] = {}
        self._id_seq = 0

    def stream(self, name: str) -> int:
        if name in self._by_name:
            return self._by_name[name]
        seed = derive_stream_seed(self.master_seed, name)
        owner = self._by_value.get(seed)
        if owner is not None and owner != name:
            raise ValueError(f"stream collision between {owner!r} and {name!r} (seed={seed})")
        self._by_name[name] = seed
        self._by_value[seed] = name
        return seed

    def new_id(self, *parts: str) -> str:
        self._id_seq += 1
        return deterministic_id(self.master_seed, "id", str(self._id_seq), *parts)

    def registered(self) -> dict[str, int]:
        return dict(self._by_name)


class ResidualFunction(StrEnum):
    RETAINED = "retained"
    DEFECTIVE = "defective"
    UNKNOWN = "unknown"


class EffectDirection(StrEnum):
    INCREASED = "increased"
    DECREASED = "decreased"
    UNCHANGED = "unchanged"
    UNRESOLVED = "unresolved"
    NOT_MEASURED = "not_measured"


class LatentScientificTruth(ImmutableModel):
    """Scorer-only scientific conditions. Never serialize into a policy observation."""

    residual_function: ResidualFunction
    abundance_normalized: bool
    nad_blood: EffectDirection = EffectDirection.NOT_MEASURED
    nad_intracellular: EffectDirection = EffectDirection.NOT_MEASURED
    bubr1_stability: EffectDirection = EffectDirection.UNRESOLVED
    functional_outcome: EffectDirection = EffectDirection.UNRESOLVED
    division_rate: EffectDirection = EffectDirection.UNCHANGED
    cell_death: EffectDirection = EffectDirection.UNCHANGED
    viability: EffectDirection = EffectDirection.UNCHANGED
    selection_effect: bool = False
    assay_valid: bool = True
    intervention_actually_tested: Intervention | Knowledge = Knowledge.UNKNOWN
    evidence_family_overlap: str | None = None
    params: tuple[LabeledParam, ...] = ()


class GeneratedFinding(ImmutableModel):
    """Internal generator output before the observation adapter."""

    node_id: str
    question_id: str
    kind: Literal["scientific", "operational"]
    scientific_state: ResponseState | AdditionalResponseState | None = None
    operational_state: ResponseState | AdditionalResponseState | None = None
    context: EvidenceCriteria = Field(default_factory=EvidenceCriteria)
    quality: Knowledge | Literal["VALID"] = Knowledge.UNKNOWN
    limitations: tuple[str, ...] = ()
    not_measured: tuple[str, ...] = ()
    free_text: str = ""
    resource_available: bool | Knowledge = Knowledge.UNKNOWN
    analysis_permission: bool | Knowledge = Knowledge.UNKNOWN
    evidence_family_id: str | None = None
    next_action_hint: str = ""


class ScientificResponseGenerator:
    """Latent compartment changes, residual function, outcomes, selection and uncertainty."""

    def __init__(self, truth: LatentScientificTruth, seeds: SeedBank):
        self.truth = truth
        self.seeds = seeds

    def generate(self, *, node_id: str, question_id: str, event_key: str) -> GeneratedFinding:
        # Stream registration keeps keyed exogenous randomness collision-checked.
        self.seeds.stream(f"science|{node_id}|{question_id}|{event_key}")
        truth = self.truth
        if not truth.assay_valid:
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=AdditionalResponseState.INVALID_MEASUREMENT,
                quality=Knowledge.INCONCLUSIVE,
                limitations=("measurement failed QC",),
                free_text="Assay quality checks failed; method repair is required before any efficacy interpretation.",
                next_action_hint="prepare_method_repair_without_drug_failure_claim",
            )
        if event_key == "blood_nad_only":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID,
                                         compartment=Compartment.BLOOD, endpoint="NAD"),
                quality="VALID",
                not_measured=("intracellular_NAD", "cellular_function"),
                limitations=("blood compartment only",),
                free_text="Blood NAD changed; relevant-cell NAD and function remain unmeasured.",
                next_action_hint="leave_relevant_cell_nad_and_function_unknown",
            )
        if event_key == "nmn_mismatch":
            tested = (truth.intervention_actually_tested
                      if isinstance(truth.intervention_actually_tested, Intervention)
                      else Intervention.NMN)
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=tested, compartment=Compartment.INTRACELLULAR,
                                         endpoint="NAD"),
                quality="VALID",
                limitations=("intervention identity differs from the asked compound",),
                free_text="Result concerns NMN, not nicotinic acid.",
                next_action_hint="preserve_intervention_mismatch",
            )
        if event_key == "residual_retained":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=Knowledge.NOT_APPLICABLE,
                                         compartment=Compartment.INTRACELLULAR,
                                         endpoint="residual_BubR1_function"),
                quality="VALID",
                limitations=("abundance-normalized residual function; no drug-rescue claim",),
                free_text="Residual function retained after abundance normalization.",
                next_action_hint="retain_abundance_premise_without_claiming_drug_rescue",
            )
        if event_key == "functional_defect":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_NO_EFFECT,
                context=EvidenceCriteria(intervention=Knowledge.NOT_APPLICABLE,
                                         compartment=Compartment.INTRACELLULAR,
                                         endpoint="residual_BubR1_function"),
                quality="VALID",
                limitations=("adequate abundance with persistent functional defect",),
                free_text="Functional defect persists at adequate abundance.",
                next_action_hint="weaken_model_scoped_premise_and_prepare_review",
            )
        if event_key == "intracellular_nad_up":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID,
                                         compartment=Compartment.INTRACELLULAR, endpoint="NAD"),
                quality="VALID",
                not_measured=("cellular_function", "SIRT2_BubR1_bridge"),
                free_text="Intracellular NAD increased; downstream function unresolved.",
                next_action_hint="retain_upstream_finding_and_identify_missing_link",
            )
        if event_key == "division_decreased":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID,
                                         compartment=Compartment.INTRACELLULAR,
                                         endpoint="division_rate"),
                quality="VALID",
                limitations=("division decreased; benefit unknown — native B16 review route",),
                not_measured=("functional_benefit",),
                free_text="Division rate decreased; benefit remains unknown.",
                next_action_hint="preserve_native_b16_review_route",
            )
        if event_key == "cell_death_increased":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID,
                                         compartment=Compartment.INTRACELLULAR,
                                         endpoint="cell_death"),
                quality="VALID",
                limitations=("cell death increased — native adverse review route",),
                free_text="Cell death increased under the tested conditions.",
                next_action_hint="preserve_native_adverse_review_route",
            )
        if event_key == "coherent_benefit":
            return GeneratedFinding(
                node_id=node_id, question_id=question_id, kind="scientific",
                scientific_state=ResponseState.MEASURED_EFFECT,
                context=EvidenceCriteria(intervention=Intervention.NICOTINIC_ACID,
                                         compartment=Compartment.INTRACELLULAR,
                                         endpoint="cellular_function"),
                quality="VALID",
                limitations=("coherent functional benefit in model; no patient action",),
                free_text="Coherent functional benefit observed in the tested model.",
                next_action_hint="propose_confirmation_or_translational_review_without_patient_action",
            )
        raise ValueError(f"unknown scientific event_key {event_key!r}")


class PublicNodeView(ImmutableModel):
    node_id: str
    institution: str
    group: str | None = None
    official_source: str
    resource_available: Knowledge = Knowledge.UNKNOWN
    analysis_permission: Knowledge = Knowledge.UNKNOWN


class RequestView(ImmutableModel):
    request_id: str
    question_id: str
    node_id: str
    state: str
    next_trigger_tick: int | None = None
    unscheduled_reason: str | None = None


class IntakeEventView(ImmutableModel):
    """Policy-visible intake shape shared with authentic replies (origin is the only tell)."""

    contribution_id: str
    origin: Origin
    kind: Literal["scientific", "operational"]
    state: str
    node_id: str
    question_id: str
    permitted_content: str
    evidence_family_id: str
    intervention: str | None = None
    compartment: str | None = None
    endpoint: str | None = None
    quality: str | None = None
    not_measured: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    next_action_hint: str = ""
    resource_available: str | None = None
    analysis_permission: str | None = None


class PolicyObservation(ImmutableModel):
    """Observation a policy may receive. Extra/latent keys are rejected at construction."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    campaign_id: str
    mode: Literal["synthetic"] = "synthetic"
    revealed: tuple[IntakeEventView, ...] = ()
    public_profiles: tuple[PublicNodeView, ...] = ()
    request_states: tuple[RequestView, ...] = ()
    prompts: tuple[str, ...] = ()
    feature_tensor: tuple[tuple[str, float], ...] = ()
    ui_payload: dict[str, Any] = Field(default_factory=dict)
    reward_explanation_for_selection: str | None = None
    content_digest: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_latent_keys(cls, data: Any):
        if isinstance(data, dict):
            _assert_no_latent_keys(data, path="PolicyObservation")
        return data

    def with_digest(self) -> PolicyObservation:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        # model_copy(update=) is blocked on ImmutableModel — rebuild.
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return PolicyObservation(**data)


def _normalize_marker(key: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in key.casefold())


def _is_latent_key(key: str) -> bool:
    norm = _normalize_marker(key)
    if norm in LATENT_KEY_MARKERS:
        return True
    return any(marker in norm for marker in LATENT_KEY_MARKERS)


def _assert_no_latent_keys(obj: Any, *, path: str) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string key at {path}")
            if _is_latent_key(key):
                raise ValueError(f"latent/hidden key {key!r} at {path}")
            _assert_no_latent_keys(value, path=f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _assert_no_latent_keys(item, path=f"{path}[{i}]")
    elif isinstance(obj, ImmutableModel):
        _assert_no_latent_keys(obj.model_dump(mode="json"), path=path)


def walk_for_latent_keys(obj: Any) -> list[str]:
    """Introspect an object graph; return paths of any latent/hidden keys found."""
    found: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, ImmutableModel):
            visit(node.model_dump(mode="json"), path)
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_s = str(key)
                child = f"{path}.{key_s}" if path else key_s
                if _is_latent_key(key_s):
                    found.append(child)
                visit(value, child)
            return
        if isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                visit(item, f"{path}[{i}]")
            return
        if hasattr(node, "__dict__") and not isinstance(node, (str, bytes, int, float, bool, type(None))):
            raw = {k: v for k, v in vars(node).items() if not k.startswith("__")}
            visit(raw, path)

    visit(obj, "")
    return found


class VirtualEvent(ImmutableModel):
    at_tick: int
    kind: str
    request_id: str
    node_id: str
    ref: str


@runtime_checkable
class SchedulerLike(Protocol):
    """T04 surface used by the sim: read due waiting tasks at a virtual instant."""

    def due(self, now: datetime) -> Any: ...


def _try_import_scheduler() -> type | None:
    try:
        from rarepipe.stages.network.scheduler import Scheduler
    except ImportError:
        return None
    return Scheduler


class VirtualTimeline:
    """Deterministic parallel request / virtual-time queue for the sim world.

    Durable waiting-task construction and outbox transitions stay with T04. When a T04
    ``Scheduler`` is supplied, advancing virtual time also queries ``due(now=...)`` so
    sim and durable timers share the same instant. This queue does not invent a second
    durable store.
    """

    def __init__(self, seeds: SeedBank, *, external: SchedulerLike | None = None):
        self.seeds = seeds
        self.tick = 0
        self._queue: list[VirtualEvent] = []
        self._external = external
        self.scheduler_type = _try_import_scheduler()
        self.seeds.stream("timeline")
        self.last_external_due: tuple[str, ...] = ()

    def schedule(self, *, delay_ticks: int, kind: str, request_id: str, node_id: str, ref: str) -> VirtualEvent:
        event = VirtualEvent(at_tick=self.tick + max(0, delay_ticks), kind=kind,
                             request_id=request_id, node_id=node_id, ref=ref)
        self._queue.append(event)
        self._queue.sort(key=lambda e: (e.at_tick, e.request_id, e.kind))
        return event

    def advance(self, ticks: int = 1) -> list[VirtualEvent]:
        if ticks < 0:
            raise ValueError("ticks must be non-negative")
        self.tick += ticks
        due = [e for e in self._queue if e.at_tick <= self.tick]
        self._queue = [e for e in self._queue if e.at_tick > self.tick]
        if self._external is not None:
            as_of = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=self.tick)
            external_due = self._external.due(as_of)
            self.last_external_due = tuple(getattr(task, "id", str(task)) for task in external_due)
        return due

    def pending(self) -> tuple[VirtualEvent, ...]:
        return tuple(self._queue)


class ObservationAdapter:
    """Map generated findings into the same intake contract authentic replies use."""

    def __init__(self, *, extractor: Actor | None = None, id_factory: Any | None = None):
        self.extractor = extractor or Actor(
            actor_type=ActorType.AGENT, identity="sim-observation-adapter",
            roles=[Role.RESEARCH_OPERATIONS])
        # Optional deterministic id source: callable(name) -> str
        self.id_factory = id_factory or (lambda _name: new_id())

    def _id(self, name: str) -> str:
        return self.id_factory(name)

    def to_contribution(
        self,
        finding: GeneratedFinding,
        *,
        campaign_id: str,
        scope: CampaignScope,
        request_id: str,
        question_decision: str,
        received_at: datetime | None = None,
        restrictions: Restrictions | None = None,
    ) -> Contribution:
        assert_no_real_institution_in_synthetic_text(finding.free_text)
        restrictions = restrictions or Restrictions()
        received_at = received_at or datetime(2026, 9, 30, tzinfo=timezone.utc)
        event_id = self._id(f"event|{request_id}|{finding.node_id}|{finding.kind}")
        if finding.kind == "operational":
            state = finding.operational_state
            if state is None:
                raise ValueError("operational finding requires operational_state")
            event: OperationalResponse | ScientificFinding = OperationalResponse(
                id=event_id, origin=Origin.SYNTHETIC, state=state,  # type: ignore[arg-type]
                resource_available=finding.resource_available,
                analysis_permission=finding.analysis_permission,
                envelope=NetworkEnvelope(
                    question_id=finding.question_id, node_identity=finding.node_id,
                    response_state=state, free_text=finding.free_text),
                restrictions=restrictions,
            )
        else:
            state = finding.scientific_state
            if state is None:
                raise ValueError("scientific finding requires scientific_state")
            event = ScientificFinding(
                id=event_id, origin=Origin.SYNTHETIC, state=state,  # type: ignore[arg-type]
                envelope=NetworkEnvelope(
                    question_id=finding.question_id, node_identity=finding.node_id,
                    response_state=state, free_text=finding.free_text),
                context=finding.context, quality=finding.quality,
                limitations=finding.limitations, not_measured=finding.not_measured,
                restrictions=restrictions,
            )
        family = finding.evidence_family_id or self._id(
            f"family|{finding.node_id}|{finding.question_id}|{finding.kind}")
        claim_id = self._id(f"claim|{request_id}|{finding.question_id}")
        contrib_id = self._id(f"contribution|{request_id}|{finding.node_id}")
        return Contribution(
            id=contrib_id, origin=Origin.SYNTHETIC, derived_from=(event.lineage(),),
            campaign_id=campaign_id, scope=scope, request_id=request_id,
            responder=finding.node_id, source="synthetic-sim",
            received_at=received_at, event=event, extractor=self.extractor,
            permitted_content=finding.free_text, evidence_family_id=family,
            restrictions=restrictions,
            relations=(ClaimRelation(
                claim_id=claim_id,
                question=Question(
                    id=finding.question_id, campaign_id=campaign_id, scope=scope,
                    decision=question_decision,
                    evidence_criteria=finding.context if finding.kind == "scientific"
                    else EvidenceCriteria()),
                direction=ClaimDirection.UNRESOLVED,
                rationale="synthetic intake; direction awaits configured review",
            ),),
        )

    def to_intake_view(self, contribution: Contribution, *, next_action_hint: str = "") -> IntakeEventView:
        event = contribution.event
        intervention = compartment = endpoint = quality = None
        not_measured: tuple[str, ...] = ()
        limitations: tuple[str, ...] = ()
        resource = permission = None
        if isinstance(event, ScientificFinding):
            intervention = str(event.context.intervention)
            compartment = str(event.context.compartment)
            endpoint = event.context.endpoint
            quality = str(event.quality)
            not_measured = event.not_measured
            limitations = event.limitations
        else:
            resource = str(event.resource_available)
            permission = str(event.analysis_permission)
        return IntakeEventView(
            contribution_id=contribution.id, origin=contribution.origin, kind=event.kind,
            state=str(event.state), node_id=event.envelope.node_identity,
            question_id=event.envelope.question_id, permitted_content=contribution.permitted_content,
            evidence_family_id=contribution.evidence_family_id, intervention=intervention,
            compartment=compartment, endpoint=endpoint, quality=quality,
            not_measured=not_measured, limitations=limitations, next_action_hint=next_action_hint,
            resource_available=resource, analysis_permission=permission,
        )


def code_revision() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[5], check=False)
        return (proc.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


class WorldManifest(ImmutableModel):
    master_seed: int
    code_revision: str
    rules_version: str
    python_version: str
    configuration: tuple[tuple[str, str], ...]
    stream_seeds: tuple[tuple[str, int], ...]
    content_digest: str | None = None
    content_digest_coverage: str = WORLD_CONTENT_DIGEST_COVERAGE

    def with_digest(self) -> WorldManifest:
        payload = self.model_dump(mode="json")
        digest = content_digest(payload, exclude={"content_digest"})
        data = {k: v for k, v in payload.items() if k != "content_digest"}
        data["content_digest"] = digest
        return WorldManifest(**data)


class ResearchWorld:
    """Bounded synthetic research world with a hard hidden-truth boundary."""

    def __init__(
        self,
        *,
        master_seed: int,
        campaign_id: str,
        scope: CampaignScope,
        latent: LatentScientificTruth,
        nodes: tuple[FictionalNode, ...] | None = None,
        public_catalogue: tuple[PublicCatalogueEntry, ...] | None = None,
        configuration: dict[str, str] | None = None,
        external_scheduler: SchedulerLike | None = None,
    ):
        self.master_seed = master_seed
        self.campaign_id = campaign_id
        self.scope = scope
        self._latent = latent
        self.seeds = SeedBank(master_seed)
        self.nodes = nodes or fictional_network()
        self.public_catalogue = public_catalogue if public_catalogue is not None else public_capability_catalogue()
        self.institution = InstitutionalProcessGenerator(self.nodes)
        self.science = ScientificResponseGenerator(latent, self.seeds)
        self.adapter = ObservationAdapter(
            id_factory=lambda name: self.seeds.new_id("adapter", name))
        self.timeline = VirtualTimeline(self.seeds, external=external_scheduler)
        self.configuration = configuration or {"world": "synthetic-research", "favourable_bias": "false"}
        self._revealed: list[IntakeEventView] = []
        self._contributions: list[Contribution] = []
        self._requests: list[RequestView] = []
        self._hints: dict[str, str] = {}

    @property
    def latent_for_scorer(self) -> LatentScientificTruth:
        """Scorer/evaluator access only. Do not pass into policy action selection."""
        return self._latent

    def institutional_outcome(self, node_id: str, **kwargs) -> InstitutionalOutcome:
        return self.institution.outcome_for(node_id, now_tick=self.timeline.tick, **kwargs)

    def reveal_scientific(self, *, node_id: str, question_id: str, event_key: str,
                          request_id: str | None = None, question_decision: str = "",
                          evidence_family_id: str | None = None) -> Contribution:
        finding = self.science.generate(node_id=node_id, question_id=question_id, event_key=event_key)
        if evidence_family_id:
            finding = GeneratedFinding(**(finding.model_dump(mode="python") | {
                "evidence_family_id": evidence_family_id}))
        return self._ingest(
            finding,
            request_id=request_id or self.seeds.new_id("request", node_id, question_id, event_key),
            question_decision=question_decision)

    def reveal_operational(
        self,
        *,
        node_id: str,
        question_id: str,
        disposition: ReplyDisposition | None = None,
        request_id: str | None = None,
        question_decision: str = "",
        free_text: str | None = None,
        next_action_hint: str = "",
    ) -> Contribution | None:
        outcome = self.institutional_outcome(
            node_id, disposition_override=disposition, free_text_override=free_text)
        request_id = request_id or self.seeds.new_id(
            "request", node_id, question_id, (disposition or outcome.disposition).value)
        if outcome.disposition is ReplyDisposition.NONRESPONSE:
            self.timeline.schedule(
                delay_ticks=outcome.arrives_at_tick - self.timeline.tick,
                kind="nonresponse_timeout", request_id=request_id, node_id=node_id, ref=question_id)
            self._requests.append(RequestView(
                request_id=request_id, question_id=question_id, node_id=node_id,
                state="WAITING", next_trigger_tick=outcome.arrives_at_tick,
                unscheduled_reason=None))
            return None
        state, finding = _operational_finding(outcome, question_id=question_id)
        finding = GeneratedFinding(**(finding.model_dump(mode="python") | {
            "next_action_hint": next_action_hint or finding.next_action_hint}))
        contrib = self._ingest(finding, request_id=request_id, question_decision=question_decision)
        self.timeline.schedule(
            delay_ticks=max(0, outcome.arrives_at_tick - self.timeline.tick),
            kind="reply_ready", request_id=contrib.request_id, node_id=node_id, ref=contrib.id)
        return contrib

    def _ingest(self, finding: GeneratedFinding, *, request_id: str, question_decision: str) -> Contribution:
        assert_no_real_institution_in_synthetic_text(finding.free_text)
        contrib = self.adapter.to_contribution(
            finding, campaign_id=self.campaign_id, scope=self.scope, request_id=request_id,
            question_decision=question_decision or "synthetic scenario question")
        view = self.adapter.to_intake_view(contrib, next_action_hint=finding.next_action_hint)
        self._contributions.append(contrib)
        self._revealed.append(view)
        self._hints[contrib.id] = finding.next_action_hint
        self._requests.append(RequestView(
            request_id=request_id, question_id=finding.question_id, node_id=finding.node_id,
            state="RECEIVED", next_trigger_tick=self.timeline.tick))
        return contrib

    def policy_observation(
        self,
        *,
        prompts: tuple[str, ...] = (),
        feature_tensor: tuple[tuple[str, float], ...] = (),
        ui_payload: dict[str, Any] | None = None,
        reward_explanation_for_selection: str | None = None,
    ) -> PolicyObservation:
        profiles = tuple(
            PublicNodeView(node_id=e.node_id, institution=e.institution, group=e.group,
                           official_source=e.official_source,
                           resource_available=e.resource_available,
                           analysis_permission=e.analysis_permission)
            for e in self.public_catalogue
        )
        obs = PolicyObservation(
            campaign_id=self.campaign_id, revealed=tuple(self._revealed),
            public_profiles=profiles, request_states=tuple(self._requests),
            prompts=prompts, feature_tensor=feature_tensor,
            ui_payload=ui_payload or {},
            reward_explanation_for_selection=reward_explanation_for_selection,
        )
        return obs.with_digest()

    def try_enter_live_campaign(self, purpose: str = "live store guard") -> Campaign:
        """A15: synthetic contributions cannot enter a live campaign store."""
        return Campaign(
            id=self.campaign_id, purpose=purpose, scope=self.scope,
            mode=CampaignMode.LIVE, contributions=tuple(self._contributions),
        )

    def try_enter_live_feedback(self, feedback: LearningFeedback) -> Campaign:
        return Campaign(
            id=self.campaign_id, purpose="live feedback guard", scope=self.scope,
            mode=CampaignMode.LIVE, feedback=(feedback,),
        )

    def manifest(self) -> WorldManifest:
        for node in self.nodes:
            self.seeds.stream(f"node|{node.id}")
        streams = tuple(sorted(self.seeds.registered().items()))
        config = tuple(sorted(self.configuration.items()))
        revealed_digests = tuple(
            content_digest(v.model_dump(mode="json")) for v in self._revealed)
        body = {
            "master_seed": self.master_seed,
            "code_revision": code_revision(),
            "rules_version": rules.RULES_VERSION,
            "python_version": platform.python_version(),
            "configuration": list(config),
            "stream_seeds": list(streams),
            "fictional_nodes": [n.id for n in self.nodes],
            "revealed_intake_digests": list(revealed_digests),
            "pending_events": [e.model_dump(mode="json") for e in self.timeline.pending()],
            "tick": self.timeline.tick,
        }
        digest = content_digest(body)
        return WorldManifest(
            master_seed=self.master_seed, code_revision=body["code_revision"],
            rules_version=rules.RULES_VERSION, python_version=body["python_version"],
            configuration=config, stream_seeds=streams, content_digest=digest,
        ).with_digest()


def _operational_finding(outcome: InstitutionalOutcome, *, question_id: str) -> tuple[
        ResponseState | AdditionalResponseState, GeneratedFinding]:
    disposition = outcome.disposition
    if disposition is ReplyDisposition.REFUSAL:
        state: ResponseState | AdditionalResponseState = AdditionalResponseState.DECLINED
        hint = "managed_wait_or_reroute_without_biological_negative"
    elif disposition is ReplyDisposition.REFERRAL:
        state = AdditionalResponseState.NO_RELEVANT_RESOURCE
        hint = "verify_referral_and_preserve_scientific_uncertainty"
    elif disposition is ReplyDisposition.PERMISSION_UNRESOLVED:
        state = AdditionalResponseState.CAPABILITY_REPORTED
        hint = "create_access_task_without_analysis_or_biology_update"
    elif disposition is ReplyDisposition.NO_MEASUREMENT:
        state = ResponseState.NO_RELEVANT_DATA
        hint = "leave_relevant_cell_nad_and_function_unknown"
    elif disposition is ReplyDisposition.PARTNER_AVAILABILITY:
        state = AdditionalResponseState.CAPABILITY_REPORTED
        hint = "update_partnership_state_without_mva_evidence"
    elif disposition is ReplyDisposition.QC_FAILURE:
        finding = GeneratedFinding(
            node_id=outcome.node_id, question_id=question_id, kind="scientific",
            scientific_state=AdditionalResponseState.INVALID_MEASUREMENT,
            quality=Knowledge.INCONCLUSIVE, limitations=("measurement QC failure",),
            free_text=outcome.free_text,
            next_action_hint="prepare_method_repair_without_drug_failure_claim",
        )
        return AdditionalResponseState.INVALID_MEASUREMENT, finding
    else:
        state = AdditionalResponseState.CAPABILITY_REPORTED
        hint = "create_access_task_without_analysis_or_biology_update"
    finding = GeneratedFinding(
        node_id=outcome.node_id, question_id=question_id, kind="operational",
        operational_state=state, free_text=outcome.free_text,
        resource_available=outcome.resource_reported,
        analysis_permission=outcome.analysis_permission_reported,
        next_action_hint=hint,
    )
    return state, finding


def synthetic_learning_feedback(campaign_id: str, action_id: str) -> LearningFeedback:
    return LearningFeedback(
        origin=Origin.SYNTHETIC, campaign_id=campaign_id, action_id=action_id,
        assessor=Actor(actor_type=ActorType.AGENT, identity="sim-scorer",
                       roles=[Role.ENGINEER]),
        method="synthetic-benchmark", status="synthetic", version="sim-1",
    )


# Re-export ValidationError for callers that guard live-store insertion.
CampaignStoreRejection = ValidationError
