"""MechanismDossier and MechanismGraph — the output contracts of mechanism resolution.

Track 1 answered *which* variants are causal. This stage asks what they do, and the whole
design exists to stop that question being answered by fluent narration.

Three rules are enforced by the schema rather than by good intentions:

1. Every scientific statement carries an `EpistemicClass`. There is no "model knowledge"
   class: anything an LLM produces is a DERIVED_INFERENCE and must cite the evidence it
   used, or it is recorded as an invalid inference and discarded.
2. Every piece of evidence carries a `Scope`. "Other BUB1B kinase-domain variants reduce
   BUBR1 abundance" and "this child's allele reduces BUBR1 abundance" are different claims,
   and the schema refuses to let one stand in for the other.
3. Unknown links stay in the graph as unknown. A mechanism graph with no gaps is a story,
   not a result.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted
from rarepipe.stages.mechanism.compare import BaselineComparison
from rarepipe.stages.mechanism.experiments import ResidualFunctionAssessment, VariantExperiment

SCHEMA_NAME = "MechanismDossier"
SCHEMA_VERSION = "1.1.0"
STAGE_NAME = "mechanism_resolution"
STAGE_VERSION = "0.3.0"


class Status(StrEnum):
    READY_FOR_INTERVENTION_SEARCH = "MECHANISM_READY_FOR_INTERVENTION_SEARCH"
    BLOCKED = "MECHANISM_BLOCKED"


class EpistemicClass(StrEnum):
    """The four classes. Deliberately no LLM_KNOWLEDGE."""

    OBSERVATION = "observation"                  # measured from this case
    EXTERNAL_EVIDENCE = "external_evidence"      # stated/demonstrated in an identifiable source
    DERIVED_INFERENCE = "derived_inference"      # reasoned from observations + external evidence
    UNKNOWN = "unknown"


class EvidenceLevel(StrEnum):
    """The source hierarchy from PRD 006 §2. Weighting is contextual, not arithmetic."""

    THIS_CASE = "this_case"
    HUMAN_EXPERIMENTAL = "human_experimental"
    EXPERT_CURATED = "expert_curated"
    PRIMARY_LITERATURE = "primary_literature"
    MODEL_SYSTEM = "model_system"
    COMPUTATIONAL = "computational"
    REVIEW = "review_or_secondary"
    LLM_SYNTHESIS = "llm_synthesis"

    @property
    def rank(self) -> int:
        return _LEVEL_RANK[self]

    @property
    def is_evidence(self) -> bool:
        return self is not EvidenceLevel.LLM_SYNTHESIS


_LEVEL_RANK = {
    EvidenceLevel.THIS_CASE: 1, EvidenceLevel.HUMAN_EXPERIMENTAL: 2, EvidenceLevel.EXPERT_CURATED: 3,
    EvidenceLevel.PRIMARY_LITERATURE: 4, EvidenceLevel.MODEL_SYSTEM: 5, EvidenceLevel.COMPUTATIONAL: 6,
    EvidenceLevel.REVIEW: 7, EvidenceLevel.LLM_SYNTHESIS: 8,
}


class ExperimentalLevel(StrEnum):
    PATIENT_DERIVED_CELLS = "patient_derived_cells"
    HUMAN_UNRELATED_CELLS = "human_unrelated_cells"
    ENGINEERED_HUMAN_CELL_LINE = "engineered_human_cell_line"
    ANIMAL_MODEL = "animal_model"
    BIOCHEMICAL_ASSAY = "biochemical_assay"
    IN_SILICO = "in_silico"
    NOT_APPLICABLE = "not_applicable"


class Scope(StrEnum):
    """What the evidence is actually about. Never widened, never narrowed."""

    EXACT_VARIANT = "exact_variant"
    SAME_RESIDUE = "same_residue"
    NEARBY_VARIANT = "nearby_variant"
    VARIANT_CLASS = "variant_class"
    GENE_LEVEL = "gene_level"
    DISEASE_LEVEL = "disease_level"


class Applicability(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    BACKGROUND = "background"


class Direction(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    UNCERTAIN = "uncertain"


class ClaimStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class ClaimType(StrEnum):
    GENE_DISEASE = "gene_disease"
    TRANSCRIPT_EFFECT = "transcript_effect"
    PROTEIN_EFFECT = "protein_effect"
    CHECKPOINT_EFFECT = "checkpoint_effect"
    SEGREGATION_EFFECT = "segregation_effect"
    ANEUPLOIDY = "aneuploidy"
    DISEASE_BRIDGE = "disease_bridge"
    COMBINED_GENOTYPE = "combined_genotype"


class Confidence(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class DisclosureLevel(StrEnum):
    PUBLIC_GENE_LEVEL = "public_gene_level"
    PUBLIC_DISEASE_LEVEL = "public_disease_level"
    LOCAL_ONLY = "local_only"


# ── retrieval ───────────────────────────────────────────────────────────────

class RetrievedDocument(BaseModel):
    source_id: str
    source_type: Literal["journal_article", "preprint", "curated_database", "ontology", "other"]
    title: str
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    journal: str | None = None
    pub_year: int | None = None
    url: str | None = None
    retrieved_at: str
    query: str = Field(description="The exact query that surfaced this document. Never case-specific.")
    content_hash: str
    full_text: bool = Field(False, description="True only when legitimately accessible full text was stored.")
    access_note: str = ""
    characters_stored: int = 0
    is_review: bool = False
    local_path: str | None = restricted(None)


class QueryRecord(BaseModel):
    """The research process is pipeline data: which strategies actually find evidence."""

    query: str
    generated_by: str = Field(description="Planner identity and version, or the LLM model that proposed it.")
    executed_on: str
    timestamp: str
    results: int
    selected: int
    knowledge_task: str | None = None
    rejected: int = 0
    rejection_reason: str | None = None


class TaskState(StrEnum):
    """"We searched this" must not mean the same thing as "a reasoning process examined it"."""

    PLANNED = "PLANNED"
    RETRIEVED = "RETRIEVED"
    DETERMINISTICALLY_EXTRACTED = "DETERMINISTICALLY_EXTRACTED"
    SEMANTICALLY_REVIEWED = "SEMANTICALLY_REVIEWED"
    ADJUDICATED = "ADJUDICATED"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


Step = Literal["not_started", "complete", "blocked", "not_applicable"]


class TaskProgress(BaseModel):
    """Each stage of work on a question, separately. Fetching documents is not reading them."""

    retrieval: Step = "not_started"
    deterministic_extraction: Step = "not_started"
    semantic_review: Step = "not_started"
    adjudication: Step = "not_started"

    def state(self) -> TaskState:
        if self.retrieval == "blocked":
            return TaskState.BLOCKED
        if self.adjudication == "complete":
            return TaskState.ADJUDICATED
        if self.semantic_review == "complete":
            return TaskState.SEMANTICALLY_REVIEWED
        if self.deterministic_extraction == "complete":
            return TaskState.DETERMINISTICALLY_EXTRACTED
        if self.retrieval == "complete":
            return TaskState.RETRIEVED
        return TaskState.PLANNED


class KnowledgeTask(BaseModel):
    """A question the pipeline asked itself, kept alongside the answer it produced."""

    id: str
    question: str
    reason: str
    disclosure_level: DisclosureLevel
    retrieval_plan: list[str]
    progress: TaskProgress = Field(default_factory=TaskProgress)
    state: TaskState = TaskState.PLANNED
    status: Literal["planned", "completed", "blocked", "abandoned"] = Field(
        "planned", description="Legacy coarse status. `state` and `progress` are what to read.")
    queries: list[str] = Field(default_factory=list)
    documents_found: list[str] = Field(default_factory=list)
    evidence_found: list[str] = Field(default_factory=list)
    resolved_claims: list[str] = Field(default_factory=list)
    information_gain: Literal["high", "moderate", "low", "none"] | None = None
    stop_reason: str | None = Field(None, description="Which stopping rule ended the search (PRD 006 §36).")
    reviewed_by: list[str] = Field(default_factory=list, description="Research sessions that actually read this bundle.")


# ── evidence ────────────────────────────────────────────────────────────────

CLAIM_DIRECTIONS = ("supports", "contradicts", "uncertain", "not_applicable")


class ClaimDirection(BaseModel):
    """How one passage bears on one claim, as a reviewer judged it."""

    direction: Literal[CLAIM_DIRECTIONS]  # type: ignore[valid-type]
    reason: str
    reviewed_by: str


class DirectionOverride(BaseModel):
    """Recorded on the claim it changed, so the export shows exactly what moved and why."""

    evidence_id: str
    extractor_direction: str
    direction_for_this_claim: str
    reason: str
    reviewed_by: str


class DirectionCorrection(BaseModel):
    """A semantic reviewer overruling the deterministic extractor's direction for one passage.

    The extractor reads cue words ("no significant effect", "unchanged"). A sentence introducing a
    different variant class can trip them without contradicting anything. The correction is keyed by
    source and passage, not by evidence id, because ids are renumbered whenever the corpus grows.
    """

    source_id: str
    quote_contains: str
    direction: Direction | None = Field(None, description="Record-level override for every claim; prefer `claims`.")
    claims: dict[str, Literal[CLAIM_DIRECTIONS]] = Field(  # type: ignore[valid-type]
        default_factory=dict, description="Per-claim relationship: a sentence's polarity is not its relationship "
                                          "to every claim it lands in. not_applicable removes it from that claim.")
    reason: str
    reviewed_by: str = Field(description="Who reviewed it, e.g. a research session id or a person.")
    applied_to: int = Field(0, description="How many evidence records it matched in this run.")
    applied: list[dict] = Field(default_factory=list,
                                description="Per evidence record and claim: extractor direction → reviewed direction.")
    unused_claims: list[str] = Field(default_factory=list,
                                     description="Claims named here that none of the matched records landed in.")


class EvidenceRecord(BaseModel):
    """One extracted finding, anchored to text that provably exists in a stored source."""

    evidence_id: str
    source_id: str
    statement: str
    quote: str = Field(description="Verbatim span from the stored source. Short by design.")
    quote_offsets: tuple[int, int] | None = None
    epistemic_class: EpistemicClass
    evidence_level: EvidenceLevel
    experimental_level: ExperimentalLevel = ExperimentalLevel.NOT_APPLICABLE
    scope: Scope
    applicability_to_case: Applicability
    direction: Direction
    assay: str | None = None
    model_system: str | None = None
    result: str | None = None
    rescue_experiment: bool = False
    variant_tested: str | None = Field(None, description="What the source tested, in the source's own terms.")
    limitations: list[str] = Field(default_factory=list)
    independence_group: str | None = Field(
        None, description="Evidence sharing a source model shares a group. Two scores from models that embed one "
                          "another are not two independent witnesses, and counting them as such is how a single "
                          "predictor comes to look like a consensus.")
    embeds: list[str] = Field(default_factory=list, description="Other independence groups this record's source "
                                                                "incorporates (e.g. a composite score embedding a predictor).")
    extracted_by: str = Field(description="Extractor identity and version, or provider:model:prompt_version.")
    verified_from_source: bool = Field(False, description="The quote was found verbatim in the stored document.")
    pub_year: int | None = None
    case_specific_detail: str | None = restricted(None)
    claim_directions: dict[str, ClaimDirection] = Field(
        default_factory=dict, description="Reviewed per-claim relationships that replace `direction` for that claim.")


class InvalidInference(BaseModel):
    """An agent claim that failed provenance validation. Kept, not silently dropped."""

    produced_by: str
    statement: str
    reason: Literal["no_citation", "source_not_in_corpus", "quote_not_found_in_source", "scope_overreach"]
    detail: str = ""


# ── claims and graph ────────────────────────────────────────────────────────

class Inference(BaseModel):
    derived_by: str
    reasoning: str
    inputs: list[str] = Field(default_factory=list, description="Evidence ids the inference rests on.")


class MechanismClaim(BaseModel):
    id: str
    type: ClaimType
    statement: str
    status: ClaimStatus
    scope: Scope
    epistemic_class: EpistemicClass
    evidence: list[str] = Field(default_factory=list, description="Evidence that can establish this claim.")
    indirect_evidence: list[str] = Field(default_factory=list,
                                         description="Consistent with the claim but unable to establish it — "
                                                     "domain location, predictors, evidence at a wider scope.")
    contradicting_evidence: list[str] = Field(default_factory=list)
    inference: Inference | None = None
    limitations: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None
    unknown_reason: str | None = None
    direction_overrides: list[DirectionOverride] = Field(default_factory=list)


class MechanismNode(BaseModel):
    id: str
    label: str
    kind: Literal["allele", "transcript", "protein", "cellular_process", "cellular_state", "clinical"]
    note: str = ""


class MechanismEdge(BaseModel):
    """An arrow nobody is allowed to draw for free."""

    from_node: str
    to_node: str
    relation: str
    status: ClaimStatus
    scope: Scope
    claim_id: str | None = None
    evidence: list[str] = Field(default_factory=list)
    best_evidence_level: EvidenceLevel | None = None
    note: str = ""


class MechanismGraph(BaseModel):
    nodes: list[MechanismNode]
    edges: list[MechanismEdge]
    unknown_edges: list[str] = Field(default_factory=list, description="Edges whose status is UNRESOLVED, named for visibility.")
    qualifications: list[str] = Field(
        default_factory=list,
        description="Accepted evidence that the chain as drawn is incomplete — parallel functions, effects beyond "
                    "the modelled variables, non-specific causes. Kept as qualifications rather than invented arrows: "
                    "we have evidence these matter, not evidence of where they attach.")


class AlleleMechanism(BaseModel):
    role: Literal["variant_a", "variant_b"]
    molecular_consequence: str | None = None
    transcript_effect: str = "unresolved"
    transcript_effect_status: ClaimStatus = ClaimStatus.UNRESOLVED
    protein_effect: str = "unresolved"
    protein_effect_status: ClaimStatus = ClaimStatus.UNRESOLVED
    exact_functional_evidence: str = "none found"
    evidence: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class AssayRecord(BaseModel):
    """What the field actually measures — the menu for any future external experiment."""

    assay: str
    biological_question: str
    models_used: list[str] = Field(default_factory=list)
    readout: str = ""
    source_count: int = Field(0, description="How many distinct sources use this assay; `sources` lists a sample.")
    sources: list[str] = Field(default_factory=list)
    case_applicability: Applicability = Applicability.INDIRECT


class MechanismState(BaseModel):
    causal_genotype_externally_validated: bool
    gene_disease_status: ClaimStatus
    allele_a: AlleleMechanism
    allele_b: AlleleMechanism
    combined_genotype_state: str
    combined_genotype_status: ClaimStatus
    spindle_checkpoint: ClaimStatus
    chromosome_segregation: ClaimStatus
    aneuploidy: ClaimStatus
    disease_bridge: ClaimStatus
    mechanistic_classes: list[str] = Field(default_factory=list,
                                           description="Distinct mechanisms the literature reports; never averaged into one.")


class MindChanger(BaseModel):
    evidence: str
    why: str
    would_change: str


class NextAction(BaseModel):
    """Ordinal, never decimal. We have no calibrated cost model."""

    rank: int
    action: str
    expected_information_gain: Literal["high", "moderate", "low"]
    cost: Literal["very_low", "low", "moderate", "high", "very_high"]
    time: Literal["hours", "days", "weeks", "months"]
    friction: Literal["none", "low", "moderate", "high"]
    importance_for_intervention_search: Literal["blocking", "high", "moderate", "low"]
    rationale: str


class EvidenceBundle(BaseModel):
    """The documents a research question was answered from. What the assistant is allowed to see."""

    bundle_id: str
    knowledge_task: str
    created_at: str
    documents: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    characters: int = 0
    digest: str = ""
    contains_case_specific_data: bool = Field(
        False, description="Always false. A bundle is public literature; the case is matched locally.")


class LLMResearchSession(BaseModel):
    """A human-operated research interaction, recorded so the reasoning step has provenance.

    The whole conversation is not captured — only enough to answer 'which model helped with which
    scientific reasoning step, and what was it allowed to see'.
    """

    session_id: str
    provider: str
    interface: str
    model: str
    mode: Literal["human_operated"] = "human_operated"
    knowledge_task: str
    permitted_inputs: list[str] = Field(default_factory=list, description="Source ids the assistant was given.")
    case_specific_genomic_data_supplied: bool = False
    prompt_template: str | None = None
    produced: list[str] = Field(default_factory=list)
    accepted: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    human_reviewed: bool = False
    performed_at: str | None = None
    note: str = ""
    supersedes: str | None = Field(None, description="An earlier session this one replaces. The earlier record "
                                                     "stays on disk; it is no longer loaded.")


class Readiness(BaseModel):
    """Two questions, not one. The disease mechanism can be actionable while the allele is unknown."""

    disease_mechanism_ready_for_intervention_search: bool
    disease_mechanism_basis: str
    exact_allele_mechanism_complete: bool
    exact_allele_blocker: str | None = None
    semantic_review_coverage: str = Field("", description="How many public tasks a reasoning process actually read.")


class AutomationStatus(BaseModel):
    """Stated in the artifact, so nobody mistakes this for an autonomous research agent."""

    automated_llm_orchestration: Literal["deferred", "enabled"] = "deferred"
    current_mode: Literal["human_operated_llm_assistance", "deterministic_only", "automated"] = "deterministic_only"
    reason: str = "first discover the research workflow before automating it"
    pipeline_depends_on_an_llm: bool = False


class Provenance(BaseModel):
    software: SoftwareProvenance
    adjudication_run_id: str
    validation_run_id: str | None = None
    causal_pair_validated_by: str | None = None
    corpus_run_id: str | None = None
    corpus_digest: str | None = None
    research_sessions: list[LLMResearchSession] = Field(default_factory=list)
    evidence_bundles: list[EvidenceBundle] = Field(default_factory=list)
    disclosure_policy: str = ("Retrieval is gene-, protein- and disease-level only. The child's coordinates, alleles, "
                              "HGVS and residue are never transmitted: exact-variant matching runs locally against the "
                              "downloaded corpus.")
    environment_controls: list[str] = Field(default_factory=list)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    corpus_path: str | None = restricted(None)
    adjudication_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class MechanismDossier(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    gene_symbol: str
    status: Status
    status_basis: str
    readiness: Readiness
    interpretation_note: str = ("A mechanism dossier, not a mechanism story. Claims are separated by scope: what is "
                                "known about the gene and the disease is not evidence about this child's alleles. "
                                "No diagnosis, no treatment reasoning, no intervention search.")
    state: MechanismState
    claims: list[MechanismClaim]
    graph: MechanismGraph
    evidence: list[EvidenceRecord]
    documents: list[RetrievedDocument]
    knowledge_tasks: list[KnowledgeTask]
    query_log: list[QueryRecord]
    assays: list[AssayRecord]
    automation_status: AutomationStatus = Field(default_factory=AutomationStatus)
    invalid_inferences: list[InvalidInference] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    evidence_strongest_at: list[str] = Field(default_factory=list)
    evidence_weakest_at: list[str] = Field(default_factory=list)
    what_would_change_our_mind: list[MindChanger] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)
    highest_value_unresolved_question: str = ""
    direction_corrections: list[DirectionCorrection] = Field(default_factory=list)
    corpus_refresh: list[dict] = Field(default_factory=list,
                                       description="Per-document outcome of reopening the corpus, if it was reopened.")
    variant_experiments: list[VariantExperiment] = Field(default_factory=list)
    residual_function: ResidualFunctionAssessment | None = None
    baseline_comparison: BaselineComparison | None = None
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
