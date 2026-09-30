"""Institutional process generator and fictional node identities.

Real institution names may appear in the public capability catalogue. Synthetic replies,
availability, refusals, delays and findings use fictional identities only — never shaped as
correspondence from a named real institution.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from rarepipe.stages.network.model import ImmutableModel, NodeType
from rarepipe.stages.prospective.model import Knowledge, Quantity


# Public catalogue may cite these (PRD §7). Synthetic reply text must never contain them.
REAL_PUBLIC_INSTITUTION_NAMES: frozenset[str] = frozenset({
    "Hubrecht Institute",
    "University of Helsinki",
    "ASWLab",
    "University of Oulu",
    "Pirinen Lab",
    "Harvard Medical School",
    "Sinclair Lab",
    "BBMRI-ERIC",
    "Euro-BioImaging",
    "MPI Molecular Physiology",
    "Musacchio",
    "CHU de Québec",
    "Université Laval",
    "Elowe",
    "Institute of Cancer Research",
    "Centre Léon Bérard",
})


class AssumptionLabel(StrEnum):
    """Every simulation parameter is an explicit assumption, never a real-institution estimate."""

    ASSUME = "ASSUME"
    STRESS = "STRESS"
    UNFAVOURABLE = "UNFAVOURABLE"
    CATALOGUE = "CATALOGUE"


class LabeledParam(ImmutableModel):
    name: str
    value: str | float | int | bool
    label: AssumptionLabel
    note: str = ""


class ReplyDisposition(StrEnum):
    EXISTING_FINDING = "existing_finding"
    NO_MEASUREMENT = "no_measurement"
    REFERRAL = "referral"
    PERMISSION_UNRESOLVED = "permission_unresolved"
    REFUSAL = "refusal"
    NONRESPONSE = "nonresponse"
    DELAYED = "delayed"
    WORKLOAD_DEFER = "workload_defer"
    QC_FAILURE = "qc_failure"
    PARTNER_AVAILABILITY = "partner_availability"


class FictionalNode(ImmutableModel):
    """Synthetic-world node. Identity strings are fiction; they are not registry leads."""

    id: str
    display_name: str
    group: str | None = None
    node_type: NodeType = NodeType.EVIDENCE_PRODUCING_LAB
    public_relevance: str = ""
    disposition: ReplyDisposition
    # ASSUME/STRESS/UNFAVOURABLE — never estimates of a real lab's behaviour.
    latency_ticks: int = Field(ge=0, description="ASSUME virtual-time delay before a reply may arrive.")
    response_probability: float = Field(
        ge=0, le=1, description="ASSUME reply probability in this synthetic world only.")
    workload_backlog: int = Field(ge=0, description="ASSUME queued synthetic requests ahead of this one.")
    cost_units: float = Field(ge=0, description="ASSUME synthetic contact/cost units.")
    referral_target_id: str | None = None
    params: tuple[LabeledParam, ...] = ()

    @model_validator(mode="after")
    def _fictional_only(self):
        blob = " ".join(filter(None, (self.id, self.display_name, self.group, self.public_relevance)))
        for real in REAL_PUBLIC_INSTITUTION_NAMES:
            if real.casefold() in blob.casefold():
                raise ValueError(f"fictional node must not embed real institution name {real!r}")
        return self


class PublicCatalogueEntry(ImmutableModel):
    """Authorized public profile. May name a real institution; is not a synthetic reply."""

    node_id: str
    institution: str
    group: str | None = None
    official_source: str
    initial_questions: tuple[str, ...] = ()
    resource_available: Knowledge = Knowledge.UNKNOWN
    analysis_permission: Knowledge = Knowledge.UNKNOWN
    capacity: Quantity = Field(default_factory=lambda: Quantity(null_reason=Knowledge.UNKNOWN))
    cost: Quantity = Field(default_factory=lambda: Quantity(null_reason=Knowledge.UNKNOWN))
    turnaround: Quantity = Field(default_factory=lambda: Quantity(null_reason=Knowledge.UNKNOWN))


class InstitutionalOutcome(ImmutableModel):
    """Process outcome before scientific content is attached."""

    node_id: str
    disposition: ReplyDisposition
    arrives_at_tick: int
    free_text: str
    referral_target_id: str | None = None
    resource_reported: bool | Knowledge = Knowledge.UNKNOWN
    analysis_permission_reported: bool | Knowledge = Knowledge.UNKNOWN
    attachment_authorized: bool = True
    reuse_permission: Literal["case_use", "revoked", "changed", "unset"] = "unset"
    opted_out: bool = False
    params_used: tuple[LabeledParam, ...] = ()


def assert_no_real_institution_in_synthetic_text(text: str) -> None:
    for real in REAL_PUBLIC_INSTITUTION_NAMES:
        if real.casefold() in text.casefold():
            raise ValueError(f"synthetic reply must not look like correspondence from {real!r}")


def fictional_network() -> tuple[FictionalNode, ...]:
    """Bounded synthetic network with favourable, delayed and unfavourable dispositions."""
    return (
        FictionalNode(
            id="fn-northbridge-cell", display_name="Northbridge Cell Dynamics Lab",
            group="Residual-function unit", disposition=ReplyDisposition.EXISTING_FINDING,
            latency_ticks=2, response_probability=0.85, workload_backlog=0, cost_units=1.0,
            params=(LabeledParam(name="response_probability", value=0.85, label=AssumptionLabel.ASSUME,
                                 note="synthetic reply rate; not an estimate of any real lab"),
                    LabeledParam(name="latency_ticks", value=2, label=AssumptionLabel.ASSUME))),
        FictionalNode(
            id="fn-cedar-nad", display_name="Cedar Ridge NAD Methods Unit",
            disposition=ReplyDisposition.EXISTING_FINDING,
            latency_ticks=3, response_probability=0.7, workload_backlog=1, cost_units=1.5,
            params=(LabeledParam(name="response_probability", value=0.7, label=AssumptionLabel.ASSUME),)),
        FictionalNode(
            id="fn-holloway-mitotic", display_name="Holloway Mitotic Signaling Group",
            disposition=ReplyDisposition.REFERRAL, referral_target_id="fn-northbridge-cell",
            latency_ticks=4, response_probability=0.6, workload_backlog=0, cost_units=1.0,
            params=(LabeledParam(name="response_probability", value=0.6, label=AssumptionLabel.ASSUME),)),
        FictionalNode(
            id="fn-redrock-access", display_name="Redrock Access Coordination Desk",
            node_type=NodeType.DISCOVERY_NETWORK, disposition=ReplyDisposition.PERMISSION_UNRESOLVED,
            latency_ticks=5, response_probability=0.9, workload_backlog=2, cost_units=0.5,
            params=(LabeledParam(name="latency_ticks", value=5, label=AssumptionLabel.STRESS,
                                 note="slow permission path in an unfavourable world"),)),
        FictionalNode(
            id="fn-silent-harbour", display_name="Silent Harbour Custodial Archive",
            node_type=NodeType.HISTORICAL_CUSTODIAL_LEAD, disposition=ReplyDisposition.NONRESPONSE,
            latency_ticks=20, response_probability=0.05, workload_backlog=0, cost_units=1.0,
            params=(LabeledParam(name="response_probability", value=0.05, label=AssumptionLabel.UNFAVOURABLE,
                                 note="near-nonresponse world; not a real institution estimate"),)),
        FictionalNode(
            id="fn-glassford-refuse", display_name="Glassford Biospecimen Desk",
            disposition=ReplyDisposition.REFUSAL,
            latency_ticks=1, response_probability=1.0, workload_backlog=0, cost_units=0.5,
            params=(LabeledParam(name="response_probability", value=1.0, label=AssumptionLabel.ASSUME,
                                 note="deterministic refusal fixture"),)),
        FictionalNode(
            id="fn-willow-partner", display_name="Willow Oncology Partnership Desk",
            node_type=NodeType.DISCOVERY_NETWORK, disposition=ReplyDisposition.PARTNER_AVAILABILITY,
            latency_ticks=2, response_probability=0.8, workload_backlog=0, cost_units=0.5,
            params=(LabeledParam(name="response_probability", value=0.8, label=AssumptionLabel.ASSUME),)),
        FictionalNode(
            id="fn-lowland-qc", display_name="Lowland Assay QC Cooperative",
            node_type=NodeType.ANALYSIS_SERVICE, disposition=ReplyDisposition.QC_FAILURE,
            latency_ticks=3, response_probability=0.75, workload_backlog=1, cost_units=2.0,
            params=(LabeledParam(name="cost_units", value=2.0, label=AssumptionLabel.STRESS),)),
    )


def public_capability_catalogue() -> tuple[PublicCatalogueEntry, ...]:
    """Seeded public profiles (PRD §7). Availability stays unknown until confirmed."""
    return (
        PublicCatalogueEntry(
            node_id="pub-hubrecht-kops", institution="Hubrecht Institute", group="Kops group",
            official_source="https://www.hubrecht.eu/research-groups/kops-group/",
            initial_questions=("Q01", "Q04", "Q06")),
        PublicCatalogueEntry(
            node_id="pub-helsinki-asw", institution="University of Helsinki", group="ASWLab",
            official_source="https://www.helsinki.fi/en/researchgroups/mitochondrial-medicine/research",
            initial_questions=("Q02", "Q06")),
        PublicCatalogueEntry(
            node_id="pub-oulu-pirinen", institution="University of Oulu", group="Pirinen Lab",
            official_source="https://www.oulu.fi/en/research-groups/mitochondria-and-nutrient-signaling",
            initial_questions=("Q02", "Q06")),
        PublicCatalogueEntry(
            node_id="pub-harvard-sinclair", institution="Harvard Medical School", group="Sinclair Lab",
            official_source="https://agingresearch.hms.harvard.edu/faculty/sinclair/",
            initial_questions=("Q03", "Q04")),
        PublicCatalogueEntry(
            node_id="pub-bbmri", institution="BBMRI-ERIC",
            official_source="https://www.bbmri-eric.eu/bbmri-sample-and-data-portal/",
            initial_questions=("Q05",)),
        PublicCatalogueEntry(
            node_id="pub-euro-bioimaging", institution="Euro-BioImaging",
            official_source="https://www.eurobioimaging.eu/image-data-services/image-analysis-services/",
            initial_questions=("Q04", "Q06")),
        PublicCatalogueEntry(
            node_id="pub-mpi-musacchio", institution="MPI Molecular Physiology", group="Musacchio group",
            official_source="https://www.mpi-dortmund.mpg.de/research-groups/musacchio",
            initial_questions=("Q01", "Q03", "Q06")),
        PublicCatalogueEntry(
            node_id="pub-laval-elowe", institution="CHU de Québec–Université Laval", group="Elowe lab",
            official_source="https://www.projets-recherche.ulaval.ca/projet?id=479868",
            initial_questions=("Q01", "Q04", "Q06")),
        PublicCatalogueEntry(
            node_id="pub-icr-london", institution="Institute of Cancer Research",
            official_source=("https://www.icr.ac.uk/about-us/icr-news/detail/"
                             "children-with-rare-disorder-lead-scientists-to-cancer-related-gene"),
            initial_questions=("Q05",)),
        PublicCatalogueEntry(
            node_id="pub-clb-partnership", institution="Centre Léon Bérard",
            official_source="directory listing (partnership lead; not MVA evidence)",
            initial_questions=()),
    )


class InstitutionalProcessGenerator:
    """Maps dispositions to process outcomes. Parameters stay labeled assumptions."""

    def __init__(self, nodes: tuple[FictionalNode, ...] | None = None):
        self.nodes = {n.id: n for n in (nodes or fictional_network())}

    def outcome_for(
        self,
        node_id: str,
        *,
        now_tick: int = 0,
        free_text_override: str | None = None,
        disposition_override: ReplyDisposition | None = None,
    ) -> InstitutionalOutcome:
        node = self.nodes[node_id]
        disposition = disposition_override or node.disposition
        text = free_text_override or _default_text(node, disposition)
        assert_no_real_institution_in_synthetic_text(text)
        resource: bool | Knowledge = Knowledge.UNKNOWN
        permission: bool | Knowledge = Knowledge.UNKNOWN
        if disposition is ReplyDisposition.PERMISSION_UNRESOLVED:
            resource, permission = True, Knowledge.UNKNOWN
        elif disposition is ReplyDisposition.REFUSAL:
            # DECLINED cannot assert boolean resource/permission (network model invariant).
            resource, permission = Knowledge.UNKNOWN, Knowledge.UNKNOWN
        elif disposition is ReplyDisposition.REFERRAL:
            resource = False
        elif disposition is ReplyDisposition.PARTNER_AVAILABILITY:
            resource = True
        delay = node.latency_ticks + node.workload_backlog
        if disposition is ReplyDisposition.NONRESPONSE:
            delay = max(delay, 10_000)
        return InstitutionalOutcome(
            node_id=node.id, disposition=disposition, arrives_at_tick=now_tick + delay,
            free_text=text, referral_target_id=node.referral_target_id,
            resource_reported=resource, analysis_permission_reported=permission,
            params_used=node.params,
        )


def _default_text(node: FictionalNode, disposition: ReplyDisposition) -> str:
    templates = {
        ReplyDisposition.EXISTING_FINDING: (
            f"{node.display_name} returns a permitted existing finding summary for the asked question."),
        ReplyDisposition.NO_MEASUREMENT: (
            f"{node.display_name} reports that the requested endpoint was not measured locally."),
        ReplyDisposition.REFERRAL: (
            f"{node.display_name} has no relevant local finding and refers to another fictional holder."),
        ReplyDisposition.PERMISSION_UNRESOLVED: (
            f"{node.display_name} confirms a resource may exist but analysis permission is unresolved."),
        ReplyDisposition.REFUSAL: (
            f"{node.display_name} declines further contact for this request."),
        ReplyDisposition.NONRESPONSE: "",
        ReplyDisposition.DELAYED: (
            f"{node.display_name} acknowledges the request; a substantive reply is still pending."),
        ReplyDisposition.WORKLOAD_DEFER: (
            f"{node.display_name} defers because of current synthetic workload."),
        ReplyDisposition.QC_FAILURE: (
            f"{node.display_name} reports the measurement failed quality checks."),
        ReplyDisposition.PARTNER_AVAILABILITY: (
            f"{node.display_name} indicates interest in discussing partnership availability only."),
    }
    return templates[disposition]
