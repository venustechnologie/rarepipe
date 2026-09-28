"""Track 2 research-hypothesis adjudication.

Stage 08 asked whether an approved medication has already been shown to produce the change the
mechanism needs. The answer was no. Stage 09 asks a different and strictly weaker question:

    is there an approved medication for which the evidence justifies *testing* the hypothesis?

That is not "the drug works". It is "the experiment is scientifically justified", and the schema
keeps the two apart so a polished submission cannot quietly become more confident than its evidence.

`MedicationCandidate` (Stage 08) means demonstrated mechanism match. `ResearchRepurposingHypothesis`
(here) means justified experiment. Nothing is promoted between them silently.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from rarepipe.core.provenance import SoftwareProvenance
from rarepipe.core.redaction import restricted

SCHEMA_NAME = "Track2HypothesisSet"
SCHEMA_VERSION = "1.0.0"
STAGE_NAME = "track2_adjudication"
STAGE_VERSION = "0.1.0"


class Status(StrEnum):
    READY = "TRACK2_RESEARCH_HYPOTHESIS_READY"
    BLOCKED = "TRACK2_SUBMISSION_BLOCKED_NO_DEFENSIBLE_HYPOTHESIS"


class EvidenceGrade(StrEnum):
    """How far the evidence actually reaches. Never a probability of working."""

    DIRECT = "DIRECT"                              # tested in BUB1B-deficient or MVA biology
    STRONG_INDIRECT = "STRONG_INDIRECT"            # drug → required BUBR1 change, shown; untested in MVA
    MECHANISTIC_INDIRECT = "MECHANISTIC_INDIRECT"  # drug → target → evidenced chain → required state


class HypothesisState(StrEnum):
    TRACK2_ELIGIBLE_DIRECT = "TRACK2_ELIGIBLE_DIRECT"
    TRACK2_ELIGIBLE_STRONG_INDIRECT = "TRACK2_ELIGIBLE_STRONG_INDIRECT"
    TRACK2_ELIGIBLE_MECHANISTIC_INDIRECT = "TRACK2_ELIGIBLE_MECHANISTIC_INDIRECT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    WRONG_DIRECTION = "WRONG_DIRECTION"
    APPROVAL_UNVERIFIED = "APPROVAL_UNVERIFIED"
    NOT_APPROVED = "NOT_APPROVED"
    CONTRADICTED = "CONTRADICTED"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"


class SearchResult(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE_EXPERIENCE_FOUND = "NEGATIVE_EXPERIENCE_FOUND"
    NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"
    CONTRADICTORY = "CONTRADICTORY"
    INACCESSIBLE = "INACCESSIBLE"
    EXHAUSTED_TO_THRESHOLD = "EXHAUSTED_TO_THRESHOLD"


class SearchOutcome(BaseModel):
    """What a search actually established, and — said out loud — what it did not.

    Formalised because the pipeline has needed it at every stage, and because a node network will
    eventually return exactly this shape.
    """

    question: str
    corpus: str
    result: SearchResult
    interpretation: str
    does_not_mean: str
    queries: list[str] = Field(default_factory=list)
    documents_examined: int = 0
    evidence: list[str] = Field(default_factory=list)


class ChainLink(BaseModel):
    """One arrow of the proposed drug → rescue chain. Evidenced or explicitly inferred, never blurred."""

    step: str
    kind: Literal["evidenced", "inference"] = "inference"
    evidence: list[str] = Field(default_factory=list)
    note: str = ""


class PediatricContext(BaseModel):
    status: str = "not collected"
    sources: list[str] = Field(default_factory=list)
    clinical_suitability: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class ValidationPlan(BaseModel):
    """What experiment would settle it. The point is worth testing, not worth administering."""

    system: str
    intervention: str
    readouts: list[str] = Field(default_factory=list)
    hypothesis: str
    falsification: str
    model_requirements: list[str] = Field(
        default_factory=list, description="What the experimental model must satisfy before a result is interpretable, "
                                          "e.g. genotype verified locally and its applicability labelled.")
    not_authorized: list[str] = Field(
        default_factory=list, description="What this plan explicitly does not establish or authorize.")


class MindChanger(BaseModel):
    would_strengthen: list[str] = Field(default_factory=list)
    would_weaken: list[str] = Field(default_factory=list)
    would_falsify: list[str] = Field(default_factory=list)


class EfficacyDependency(BaseModel):
    """Something the hypothesis needs to be true in order to work, stated so it cannot be forgotten.

    Generating a hypothesis without knowing the exact allele is not the same as expecting it to work
    regardless of the allele. A strategy that raises protein abundance helps only if the protein that
    accumulates can do its job.
    """

    dependency: str
    status: Literal["unresolved", "supported", "contradicted"] = "unresolved"
    why_it_matters: str = ""
    what_would_resolve_it: str = ""
    basis: str | None = Field(None, description="Where the current status comes from, when a stage derived it.")


class GateCheck(BaseModel):
    check: str
    passed: bool
    detail: str = ""


class ResearchRepurposingHypothesis(BaseModel):
    id: str
    active_ingredient: str
    canonical_ids: dict[str, str] = Field(default_factory=dict)
    approval_verified: bool = False
    approval_jurisdictions: list[str] = Field(default_factory=list)
    approval_authority: str | None = None
    approval_note: str = ""
    intervention_spec: str = "SPEC_001"
    statement: str
    proposed_chain: list[ChainLink] = Field(default_factory=list)
    required_direction: str = "restore_toward_normal"
    predicted_direction: Literal["concordant", "discordant", "unknown"] = Field(
        "unknown", description="The direction the mechanism predicts the medication would move the required state.")
    observed_direction: Literal["concordant", "discordant", "unknown"] = Field(
        "unknown", description="The direction actually observed on the REQUIRED state (BUBR1 function, checkpoint, "
                               "segregation). Upstream effects such as a rise in blood NAD+ do not count here.")
    observed_upstream_effects: list[str] = Field(
        default_factory=list, description="Effects of the medication that were observed, short of the required state.")
    evidence_grade: EvidenceGrade | None = None
    establishing_evidence: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    negative_experiences: list[str] = Field(default_factory=list)
    unknown_experiences: list[str] = Field(default_factory=list)
    not_tested_note: str = ""
    independence_groups: list[str] = Field(default_factory=list)
    exact_allele_dependency: bool = Field(
        False, description="Whether GENERATING the hypothesis required the exact allele's mechanism. It says "
                           "nothing about whether the medication would work regardless of the allele — see "
                           "efficacy_dependencies for that.")
    efficacy_dependencies: list[EfficacyDependency] = Field(default_factory=list)
    tested_in_bub1b_deficiency: bool = False
    tested_in_mva: bool = False
    pediatric_context: PediatricContext = Field(default_factory=PediatricContext)
    validation_plan: ValidationPlan | None = None
    what_would_change_our_mind: MindChanger = Field(default_factory=MindChanger)
    gate: list[GateCheck] = Field(default_factory=list)
    state: HypothesisState = HypothesisState.DISCOVERY_ONLY
    limitations: list[str] = Field(default_factory=list)
    clinical_actionability: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    treatment_recommendation: Literal[False] = False


class RejectedHypothesis(BaseModel):
    intervention: str
    discovered_because: str
    rejected_because: HypothesisState
    failed_checks: list[str] = Field(default_factory=list)
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)


class SubmissionClaim(BaseModel):
    """Every substantive sentence intended for the report, tied to what it rests on."""

    id: str
    statement: str
    evidence_ids: list[str] = Field(default_factory=list)
    type: Literal["observation", "external_evidence", "derived_inference"]
    scope: str = "disease_level"
    allowed_in_submission: bool = True
    basis_note: str = ""


class BaselineSnapshot(BaseModel):
    """The sealed pre-network baseline. Frozen whichever branch the stage takes."""

    created_at: str
    created_before_network_search: bool = True
    public_evidence_only: bool = True
    validation_run_id: str | None = None
    mechanism_run_id: str | None = None
    mechanism_digest: str | None = None
    intervention_map_run_id: str | None = None
    intervention_map_digest: str | None = None
    discovery_run_id: str | None = None
    discovery_digest: str | None = None
    git_commit: str | None = None
    git_describe: str | None = None
    hypotheses_found: int = 0
    note: str = ("Established from public evidence alone, before any institutional or node outreach. A later rerun "
                 "with node evidence can be compared against this to measure what the network added.")


class Action(BaseModel):
    rank: int
    action: str
    expected_information_gain: Literal["high", "moderate", "low"]
    cost: Literal["very_low", "low", "moderate", "high", "very_high"]
    rationale: str
    blocked_by: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    software: SoftwareProvenance
    discovery_run_id: str
    discovery_digest: str | None = None
    intervention_map_run_id: str | None = None
    mechanism_run_id: str | None = None
    validation_run_id: str | None = None
    research_sessions: list[str] = Field(default_factory=list)
    approval_sources: list[str] = Field(default_factory=list)
    disclosure_policy: str = ("Public evidence only. Gene, protein, disease, mechanism and medication names may be "
                              "queried; exact variants, HGVS, coordinates, the variant pair and the phenotype "
                              "fingerprint never leave local compute.")
    environment_controls: list[str] = Field(default_factory=list)


class Execution(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    discovery_path: str | None = restricted(None)
    argv: list[str] = restricted(list)


class Track2HypothesisSet(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}, alias="schema")
    pipeline: dict = Field(default_factory=lambda: {"stage": STAGE_NAME, "stage_version": STAGE_VERSION})
    visibility: Literal["private", "sanitized"]
    case_id: str
    gene_symbol: str
    status: Status
    status_basis: str
    interpretation_note: str = ("Research hypotheses, not treatment. An entry here means the evidence justifies "
                                "testing whether an approved medication produces the required biological effect — "
                                "not that it does, and not a recommendation to administer anything to anyone.")
    hypotheses: list[ResearchRepurposingHypothesis] = Field(default_factory=list)
    rejected: list[RejectedHypothesis] = Field(default_factory=list)
    search_outcomes: list[SearchOutcome] = Field(default_factory=list)
    submission_claims: list[SubmissionClaim] = Field(default_factory=list)
    residual_function: dict | None = Field(None, description="Stage 06F assessment, as the mechanism run stated it.")
    node_query_specs: list[dict] = Field(default_factory=list)
    baseline: BaselineSnapshot
    next_actions: list[Action] = Field(default_factory=list)
    provenance: Provenance
    semantic_digest: str | None = None
    execution: Execution

    model_config = {"populate_by_name": True, "serialize_by_alias": True}
