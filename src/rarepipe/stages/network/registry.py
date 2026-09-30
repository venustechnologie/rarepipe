"""Seed capability registry and match exploration (PRD §7, Tasks T01/T03).

Provides public-evidence capability profiles for candidate institutions, question routing,
and transparent match explanations. Operational parameters (resource availability, analysis
permission, capacity, cost, turnaround) default to UNKNOWN until confirmed by an authentic
institutional operational response.

Helsinki and Oulu share an evidence-family ID to reflect their common underlying human
study (PMID 32386566). Centre Léon Bérard is isolated in a separate PARTNERSHIP_ONCOLOGY
campaign seed with listing-reported governance states and supplies no MVA scientific evidence.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from rarepipe.stages.network.model import (
    Campaign, CampaignMode, CampaignScope, Capability, ContactRoute,
    EvidenceCriteria, ImmutableModel, Intervention, Knowledge, Match,
    Node, NodeType, OperationalResponse, Origin, PublicSource, Quantity,
    Question, unknown_quantity,
)
from rarepipe.stages.prospective.model import Role
from rarepipe.stages.prospective.store import canonical_bytes, content_digest


NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
RANKING_BASIS = (
    "ordinal: public evidence specificity (direct target literature > "
    "methods/reconstitution > discovery/referral network); not a reply probability"
)
RANKING_VERSION = "1.0.0"


class NodeSeedEntry(ImmutableModel):
    node: Node
    campaign_scope: CampaignScope
    questions: tuple[str, ...]
    candidate_rationale: str
    sourced_evidence: tuple[str, ...]
    inferred: tuple[str, ...]
    confirmation_remains: tuple[str, ...]
    evidence_family_id: str | None = None
    ranking_tier: int = 1
    supplies_mva_evidence: bool = True


class MatchExplanation(ImmutableModel):
    question_id: str
    node_id: str
    match_id: str
    institution: str
    group: str | None = None
    node_type: NodeType
    candidate_rationale: str
    supporting_evidence: tuple[str, ...]
    inferred: tuple[str, ...]
    confirmation_remains: tuple[str, ...]
    evidence_family_id: str | None = None
    ranking_basis: str
    ranking_version: str
    ranking_tier: int = 1
    resource_available: Knowledge | bool = Knowledge.UNKNOWN
    analysis_permission: Knowledge | bool = Knowledge.UNKNOWN
    contact_verified: bool = False
    supplies_mva_evidence: bool = True
    match: Match
    node: Node

    def confirm_resource(self, event: OperationalResponse) -> Node:
        """Confirm resource availability using an authentic institutional operational response."""
        data = self.node.model_dump()
        updates: dict[str, Any] = {
            "confirmation_events": (*self.node.confirmation_events, event),
        }
        if event.resource_available is not Knowledge.UNKNOWN:
            updates["resource_available"] = event.resource_available
        if event.analysis_permission is not Knowledge.UNKNOWN:
            updates["analysis_permission"] = event.analysis_permission
        return Node(**(data | updates))


class SeedData(ImmutableModel):
    schema_id: str = Field(alias="schema", default="rarepipe.research-network.seed-nodes.v0.1")
    version: str = "1.0.0"
    generated_at: datetime
    ranking_basis: str
    ranking_version: str
    campaigns: tuple[Campaign, ...]
    leads: tuple[NodeSeedEntry, ...]


def _build_mva_campaign() -> Campaign:
    q01 = Question(
        id="Q01",
        campaign_id="cmp-mva-001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Whether an abundance-restoration premise remains plausible; which functional endpoints remain necessary",
        evidence_criteria=EvidenceCriteria(
            endpoint="BubR1 residual function",
        ),
        required_reviewer=Role.SCIENTIFIC_LEAD,
        state=Knowledge.UNKNOWN,
    )
    q02 = Question(
        id="Q02",
        campaign_id="cmp-mva-001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Whether the first drug-to-cell connection is supported for that model",
        dependencies=("Q01",),
        evidence_criteria=EvidenceCriteria(
            intervention=Intervention.NICOTINIC_ACID,
            compartment=Knowledge.UNKNOWN,
            endpoint="NAD",
        ),
        required_reviewer=Role.SCIENTIFIC_LEAD,
        state=Knowledge.UNKNOWN,
    )
    q03 = Question(
        id="Q03",
        campaign_id="cmp-mva-001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Which mechanistic connection is supported or challenged",
        dependencies=("Q02",),
        evidence_criteria=EvidenceCriteria(
            intervention=Intervention.NICOTINIC_ACID,
            endpoint="BubR1 stability / SIRT2 activity",
        ),
        required_reviewer=Role.SCIENTIFIC_LEAD,
        state=Knowledge.UNKNOWN,
    )
    q04 = Question(
        id="Q04",
        campaign_id="cmp-mva-001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Whether independent confirmation or translational review is justified",
        dependencies=("Q01", "Q03"),
        evidence_criteria=EvidenceCriteria(
            intervention=Intervention.NICOTINIC_ACID,
            endpoint="chromosome segregation / cell division",
        ),
        required_reviewer=Role.SCIENTIFIC_LEAD,
        state=Knowledge.UNKNOWN,
    )
    q05 = Question(
        id="Q05",
        campaign_id="cmp-mva-001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Where and how to obtain the next contribution",
        required_reviewer=Role.RESEARCH_OPERATIONS,
        state=Knowledge.UNKNOWN,
    )
    q06 = Question(
        id="Q06",
        campaign_id="cmp-mva-001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Which scientific design decisions can be prepared for review",
        required_reviewer=Role.SCIENTIFIC_LEAD,
        state=Knowledge.UNKNOWN,
    )
    return Campaign(
        id="cmp-mva-001",
        purpose="Investigation of nicotinic acid for BUB1B-associated mosaic variegated aneuploidy",
        case_ref="PP_MVA_001_RH_001",
        scope=CampaignScope.MVA_SCIENTIFIC,
        mode=CampaignMode.LIVE,
        exclusions=("MVA Society", "child", "family"),
        status="DRAFT",
        questions=(q01, q02, q03, q04, q05, q06),
    )


def _build_partnership_campaign() -> Campaign:
    q_onc_01 = Question(
        id="Q_ONC_01",
        campaign_id="cmp-partnership-oncology",
        scope=CampaignScope.PARTNERSHIP_ONCOLOGY,
        decision="Whether Centre Léon Bérard is still considering an AI partner for Recoding Medicine",
        required_reviewer=Role.RESEARCH_OPERATIONS,
        state=Knowledge.UNKNOWN,
    )
    return Campaign(
        id="cmp-partnership-oncology",
        purpose="Explore AI research partnership with Centre Léon Bérard for virtual tumour board note extraction",
        case_ref="CHALLENGE_RECODING_MEDICINE",
        scope=CampaignScope.PARTNERSHIP_ONCOLOGY,
        mode=CampaignMode.LIVE,
        status="DRAFT",
        questions=(q_onc_01,),
    )


def _build_leads() -> tuple[NodeSeedEntry, ...]:
    leads: list[NodeSeedEntry] = []

    # 1. Hubrecht Institute (Kops group)
    src_hubrecht = PublicSource(
        reference="https://www.hubrecht.eu/research-groups/kops-group/",
        accessed_at=NOW,
    )
    node_hubrecht = Node(
        id="node-hubrecht-kops",
        institution="Hubrecht Institute",
        group="Kops group",
        node_type=NodeType.EVIDENCE_PRODUCING_LAB,
        source=src_hubrecht,
        capabilities=(
            Capability(
                description="Chromosome segregation fidelity, SAC signaling, and aneuploidy mechanisms research",
                source=src_hubrecht,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Cellular and organoid model systems for kinetochore and spindle checkpoint dynamics",
                source=src_hubrecht,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Live-cell microscopy for mitotic timing and chromosome alignment",
                source=src_hubrecht,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_hubrecht,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q01", "Q04", "Q06"),
        candidate_rationale="Current MVA and chromosome-segregation research; potential existing restored-abundance findings, endpoint limits, model/method referral",
        sourced_evidence=(
            "Active peer-reviewed research on BUB1B/BubR1 chromosome segregation mechanisms",
            "Published expertise in live-cell mitotic imaging assays at Hubrecht Institute",
        ),
        inferred=(
            "Laboratory may hold cellular models with altered BubR1 abundance or relevant SAC assay systems",
            "Protocols could be adapted to evaluate residual function in variant alleles",
        ),
        confirmation_remains=(
            "Whether specific BUB1B variant models are currently available in the lab",
            "Functional assay bandwidth and willingness to test variant alleles",
            "Institutional material transfer and analysis permission",
        ),
        evidence_family_id="ef-hubrecht-kops",
        ranking_tier=1,
        supplies_mva_evidence=True,
    ))

    # 2. University of Helsinki (ASWLab)
    src_helsinki = PublicSource(
        reference="https://www.helsinki.fi/en/researchgroups/mitochondrial-medicine/research",
        accessed_at=NOW,
        published_at=datetime(2020, 5, 7, tzinfo=timezone.utc),
    )
    node_helsinki = Node(
        id="node-helsinki-aswlab",
        institution="University of Helsinki",
        group="ASWLab",
        node_type=NodeType.EVIDENCE_PRODUCING_LAB,
        source=src_helsinki,
        capabilities=(
            Capability(
                description="Mitochondrial medicine and systemic/tissue NAD metabolomics research",
                source=src_helsinki,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Clinical trial execution and metabolomic profiling of nicotinic acid supplementation in humans",
                source=src_helsinki,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Targeted mass spectrometry protocols for NAD+ metabolome quantification",
                source=src_helsinki,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_helsinki,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q02", "Q06"),
        candidate_rationale="Tissue/systemic metabolism; human nicotinic-acid research; blood-versus-cell measurement interpretation and existing methods",
        sourced_evidence=(
            "Co-led clinical study demonstrating systemic and tissue NAD+ elevation by nicotinic acid in humans (PMID 32386566)",
            "Established institutional protocols for NAD metabolite quantification",
        ),
        inferred=(
            "Metabolomic expertise applies to distinguishing intracellular vs blood NAD compartmental concentrations",
            "Could advise on dose-response and exposure conditions for nicotinic acid",
        ),
        confirmation_remains=(
            "Whether cellular/intracellular compartmental assays are routinely supported",
            "Availability of experimental capacity for non-mitochondrial disease models",
            "Institutional collaboration and data sharing permission",
        ),
        evidence_family_id="ef-niacin-trial-pmid32386566",
        ranking_tier=1,
        supplies_mva_evidence=True,
    ))

    # 3. University of Oulu (Pirinen Lab)
    src_oulu = PublicSource(
        reference="https://www.oulu.fi/en/research-groups/mitochondria-and-nutrient-signaling",
        accessed_at=NOW,
        published_at=datetime(2020, 5, 7, tzinfo=timezone.utc),
    )
    node_oulu = Node(
        id="node-oulu-pirinen",
        institution="University of Oulu",
        group="Pirinen Lab",
        node_type=NodeType.EVIDENCE_PRODUCING_LAB,
        source=src_oulu,
        capabilities=(
            Capability(
                description="Mitochondria and nutrient signaling with focus on NAD+ boosting therapies",
                source=src_oulu,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Cell-type-specific nicotinic acid response and NAD synthesis pathway analyses",
                source=src_oulu,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Preclinical pharmacology and metabolic flux analysis of NAD precursors",
                source=src_oulu,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_oulu,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q02", "Q06"),
        candidate_rationale="NAD metabolism and the same human niacin study; nicotinic-acid-specific response conditions and feasible analyses",
        sourced_evidence=(
            "Co-led landmark trial of niacin in humans (PMID 32386566)",
            "Documented expertise in cellular NAD precursor utilization and nutrient signaling",
        ),
        inferred=(
            "Laboratory can define interpretable cell culture exposure conditions for nicotinic acid",
            "Experience with NAD quantification methods in cell models",
        ),
        confirmation_remains=(
            "Cell model availability and feasibility of testing BUB1B/MVA cell contexts",
            "Current laboratory testing capacity and service availability",
            "Formal institutional research collaboration agreement",
        ),
        evidence_family_id="ef-niacin-trial-pmid32386566",
        ranking_tier=1,
        supplies_mva_evidence=True,
    ))

    # 4. Harvard Medical School (Sinclair Lab)
    src_harvard = PublicSource(
        reference="https://agingresearch.hms.harvard.edu/faculty/sinclair/",
        accessed_at=NOW,
        published_at=datetime(2014, 5, 8, tzinfo=timezone.utc),
    )
    node_harvard = Node(
        id="node-harvard-sinclair",
        institution="Harvard Medical School",
        group="Sinclair Lab",
        node_type=NodeType.EVIDENCE_PRODUCING_LAB,
        source=src_harvard,
        capabilities=(
            Capability(
                description="Sirtuin biochemistry, NAD+ biology, and deacetylation target identification",
                source=src_harvard,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Original SIRT2/BubR1 deacetylation and protein stabilization assays",
                source=src_harvard,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Small molecule sirtuin modulators and NAD biology expertise",
                source=src_harvard,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_harvard,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q03", "Q04"),
        candidate_rationale="Original SIRT2/BubR1 work; current NAD/sirtuin expertise; existing mechanistic findings and distinction between abundance and function",
        sourced_evidence=(
            "North et al. (2014) demonstrated SIRT2-mediated deacetylation of BubR1 and its role in stability (PMID 24825348)",
            "World-renowned expertise in NAD biology and sirtuin regulation",
        ),
        inferred=(
            "May possess historical constructs, antibodies, or assay protocols specific to BubR1 deacetylation",
            "Could advise on whether SIRT2 activation increases mutant BubR1 functional activity vs abundance alone",
        ),
        confirmation_remains=(
            "Whether BubR1/mitotic research remains active in the laboratory vs general aging pathways",
            "Reagent availability and willingness to evaluate MVA-specific variant alleles",
            "Institutional MTA and IP requirements",
        ),
        evidence_family_id="ef-sirt2-bubr1-pmid24825348",
        ranking_tier=1,
        supplies_mva_evidence=True,
    ))

    # 5. BBMRI-ERIC
    src_bbmri = PublicSource(
        reference="https://www.bbmri-eric.eu/bbmri-sample-and-data-portal/",
        accessed_at=NOW,
    )
    node_bbmri = Node(
        id="node-bbmri-eric",
        institution="BBMRI-ERIC",
        node_type=NodeType.DISCOVERY_NETWORK,
        source=src_bbmri,
        capabilities=(
            Capability(
                description="Pan-European biobank discovery portal with federated sample and dataset search",
                source=src_bbmri,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Negotiator service for sample access and data transfer governance across European biobanks",
                source=src_bbmri,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Quality management and compliance frameworks for biological sample acquisition",
                source=src_bbmri,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_bbmri,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q05",),
        candidate_rationale="Collection discovery and negotiation infrastructure; identify a holder and a permitted feasibility/local-analysis route",
        sourced_evidence=(
            "Official European research infrastructure linking hundreds of biobanks across Europe",
            "Standardized negotiator system for requesting samples from biobank holders",
        ),
        inferred=(
            "Network queries can identify whether any participating European biobank holds BUB1B/MVA patient specimens or relevant cell models",
            "Could identify permitted local-analysis routes avoiding biological specimen transport",
        ),
        confirmation_remains=(
            "Whether any annotated BUB1B/MVA specimens currently exist in indexed biobanks",
            "Specific biobank custodians' willingness to participate in rare disease access requests",
            "Cross-border data/sample transfer regulations and ethics approval",
        ),
        evidence_family_id="ef-bbmri-portal",
        ranking_tier=3,
        supplies_mva_evidence=True,
    ))

    # 6. Euro-BioImaging
    src_eurobio = PublicSource(
        reference="https://www.eurobioimaging.eu/image-data-services/image-analysis-services/",
        accessed_at=NOW,
    )
    node_eurobio = Node(
        id="node-euro-bioimaging",
        institution="Euro-BioImaging",
        node_type=NodeType.ANALYSIS_SERVICE,
        source=src_eurobio,
        capabilities=(
            Capability(
                description="Quantitative biological image analysis, machine learning pipelines, and cellular tracking",
                source=src_eurobio,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Standardized image quality control, open workflow execution, and computational infrastructure",
                source=src_eurobio,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Distributed access to European advanced microscopy and image analysis facilities",
                source=src_eurobio,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_eurobio,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q04", "Q06"),
        candidate_rationale="Image analysis, tracking and workflow services; endpoint feasibility, image QC and execution arrangement",
        sourced_evidence=(
            "European research infrastructure offering coordinated image analysis services and expert workflows",
            "Published catalog of specialized image data services and QC protocols",
        ),
        inferred=(
            "Can execute or adapt automated mitotic tracking, micronucleus counts, or segregation defect quantification on microscopy datasets",
            "Can advise on imaging standards necessary to make functional division endpoints interpretable",
        ),
        confirmation_remains=(
            "Node assignment and facility capacity for specific mitotic analysis tasks",
            "Service costs, pricing tier, and expected analysis turnaround times",
            "Data access agreement terms for external case data",
        ),
        evidence_family_id="ef-euro-bioimaging-services",
        ranking_tier=2,
        supplies_mva_evidence=True,
    ))

    # 7. MPI Molecular Physiology (Musacchio group)
    src_musacchio = PublicSource(
        reference="https://www.mpi-dortmund.mpg.de/research-groups/musacchio",
        accessed_at=NOW,
    )
    node_musacchio = Node(
        id="node-mpi-musacchio",
        institution="MPI Molecular Physiology",
        group="Musacchio group",
        node_type=NodeType.EVIDENCE_PRODUCING_LAB,
        source=src_musacchio,
        capabilities=(
            Capability(
                description="Biochemical reconstitution of kinetochore complexes and spindle assembly checkpoint machinery",
                source=src_musacchio,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Cryo-EM and structural analysis of BubR1/BUB1/Bub3 protein assemblies",
                source=src_musacchio,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="In vitro phosphorylation and functional reconstitution assays for checkpoint proteins",
                source=src_musacchio,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_musacchio,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q01", "Q03", "Q06"),
        candidate_rationale="Biochemical reconstitution and cell-division methods; orthogonal assay interpretation when cellular results are ambiguous",
        sourced_evidence=(
            "World-leading publication record in reconstituting human SAC complexes containing BubR1",
            "Definitive biochemical and structural methodologies for analyzing BubR1 interactions and activities",
        ),
        inferred=(
            "Reconstitution system can test whether residual activity or interaction partners of mutant BubR1 change upon SIRT2 deacetylation",
            "Provides decisive orthogonal evidence when cellular assays are ambiguous or confounded by cell death",
        ),
        confirmation_remains=(
            "Feasibility and interest in testing specific patient BUB1B variants in reconstitution assays",
            "Capacity for academic collaboration or scientific advisory consultation",
            "Formal institutional collaboration agreement",
        ),
        evidence_family_id="ef-musacchio-kinetochore",
        ranking_tier=1,
        supplies_mva_evidence=True,
    ))

    # 8. CHU de Québec–Université Laval (Elowe lab)
    src_elowe = PublicSource(
        reference="https://www.projets-recherche.ulaval.ca/projet?id=479868",
        accessed_at=NOW,
    )
    node_elowe = Node(
        id="node-chu-quebec-elowe",
        institution="CHU de Québec–Université Laval",
        group="Elowe lab",
        node_type=NodeType.EVIDENCE_PRODUCING_LAB,
        source=src_elowe,
        capabilities=(
            Capability(
                description="Mitotic kinase signaling, BubR1 phosphorylation, and checkpoint silencing research",
                source=src_elowe,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Cell-based functional assays for chromosome alignment and spindle checkpoint timing",
                source=src_elowe,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Structure-function analysis of BubR1 pseudokinase domain and functional motifs",
                source=src_elowe,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_elowe,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q01", "Q04", "Q06"),
        candidate_rationale="Mitotic signaling and domain/silencing research; activation versus silencing/alignment limitations",
        sourced_evidence=(
            "Funded research project and publications on BubR1 phosphorylation dynamics and SAC signaling (Project ID 479868)",
            "Extensive methodology for evaluating mitotic checkpoint arrest versus slippage",
        ),
        inferred=(
            "Expertise can distinguish whether restoring BubR1 abundance restores functional checkpoint silencing or merely checkpoint activation",
            "Assay platforms can evaluate functional division endpoints in variant-expressing lines",
        ),
        confirmation_remains=(
            "Current model availability and willingness to evaluate specific BUB1B alleles",
            "Turnaround and experimental capacity within the academic laboratory",
            "Institutional research agreement and MTA",
        ),
        evidence_family_id="ef-elowe-mitotic-signaling",
        ranking_tier=1,
        supplies_mva_evidence=True,
    ))

    # 9. Institute of Cancer Research (London, UK)
    src_icr = PublicSource(
        reference="https://www.icr.ac.uk/about-us/icr-news/detail/children-with-rare-disorder-lead-scientists-to-cancer-related-gene",
        accessed_at=NOW,
        published_at=datetime(2004, 11, 21, tzinfo=timezone.utc),
    )
    node_icr = Node(
        id="node-icr-london",
        institution="Institute of Cancer Research",
        node_type=NodeType.HISTORICAL_CUSTODIAL_LEAD,
        source=src_icr,
        capabilities=(
            Capability(
                description="Historical identification and characterization of BUB1B mutations in mosaic variegated aneuploidy",
                source=src_icr,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Cancer genetics archive and historical rare disease cohort documentation",
                source=src_icr,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Referral pathway to historical clinical and genetic research networks",
                source=src_icr,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_icr,
        campaign_scope=CampaignScope.MVA_SCIENTIFIC,
        questions=("Q05",),
        candidate_rationale="Historical BUB1B/MVA research involvement; current custodial or scientific referral, not an assumed resource",
        sourced_evidence=(
            "Led the original 2004 discovery connecting biallelic BUB1B mutations to MVA (Hanks et al., Nat Genet 2004)",
            "Maintains institutional scientific archives regarding the discovery",
        ),
        inferred=(
            "Archival records or emeritus investigators might identify where original specimens or patient-derived cell lines were archived or transferred",
            "Could provide referral to active European or UK curators of rare chromosome instability cohorts",
        ),
        confirmation_remains=(
            "Whether any physical samples or cell lines remain in custody or storage",
            "Whether historical investigators or curators are contactable and permitted to respond",
            "Referral to current custodian (ICR is NOT an assumed resource holder)",
        ),
        evidence_family_id="ef-icr-mva-discovery-2004",
        ranking_tier=3,
        supplies_mva_evidence=True,
    ))

    # 10. Centre Léon Bérard (Separate Partnership Lead)
    src_clb = PublicSource(
        reference="https://www.sprind.org/en/actions/challenges/recoding-medicine",
        accessed_at=NOW,
    )
    node_clb = Node(
        id="node-centre-leon-berard",
        institution="Centre Léon Bérard",
        node_type=NodeType.HISTORICAL_CUSTODIAL_LEAD,
        source=src_clb,
        capabilities=(
            Capability(
                description="Listing-reported material: multidisciplinary virtual tumour board meeting notes (2017–2026), raw, not longitudinal, no annotation or linkage listed",
                source=src_clb,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Listing-reported access status: consent basis unclear, access model undecided, departure from institution unsure, ethics approval not started",
                source=src_clb,
                evidence_status="PUBLICLY_REPORTED",
            ),
            Capability(
                description="Listing-reported partnership opportunity: oncology data holder seeking AI partner for Recoding Medicine",
                source=src_clb,
                evidence_status="PUBLICLY_REPORTED",
            ),
        ),
        contact_route=ContactRoute(
            recipient="info@schmitt-t.com",
            source=PublicSource(
                reference="Directory listing / screenshot for Recoding Medicine challenge",
                accessed_at=NOW,
            ),
            verification=None,
        ),
    )
    leads.append(NodeSeedEntry(
        node=node_clb,
        campaign_scope=CampaignScope.PARTNERSHIP_ONCOLOGY,
        questions=("Q_ONC_01",),
        candidate_rationale="Listing-reported oncology data holder seeking AI partner for Recoding Medicine challenge; multidisciplinary virtual tumour board notes 2017–2026",
        sourced_evidence=(
            "Directory listing screenshot for Recoding Medicine challenge",
            "Contact email info@schmitt-t.com provided in directory listing",
        ),
        inferred=(
            "Centre Léon Bérard may still be seeking an AI research partner to extract research questions, clinical reasoning, and evidence needs from tumour board notes",
        ),
        confirmation_remains=(
            "Whether Centre Léon Bérard is still considering an AI partner",
            "Clarification of consent basis, access model, data departure permission, and ethics approval",
            "Verification of authentic institutional contact and governance",
        ),
        evidence_family_id="ef-clb-recoding-medicine",
        ranking_tier=1,
        supplies_mva_evidence=False,
    ))

    return tuple(leads)


def build_seed_data() -> SeedData:
    """Construct the canonical seed data containing both campaigns and all candidate leads."""
    campaigns = (_build_mva_campaign(), _build_partnership_campaign())
    leads = _build_leads()
    return SeedData(
        generated_at=NOW,
        ranking_basis=RANKING_BASIS,
        ranking_version=RANKING_VERSION,
        campaigns=campaigns,
        leads=leads,
    )


def get_default_seed_path() -> Path:
    """Resolve the default file path to data/network/seed_nodes.json."""
    if "RAREPIPE_SEED_NODES_PATH" in os.environ:
        return Path(os.environ["RAREPIPE_SEED_NODES_PATH"]).resolve()
    # 5 levels up: src/rarepipe/stages/network/registry.py -> workspace_root
    workspace_root = Path(__file__).resolve().parents[4]
    candidate = workspace_root / "data" / "network" / "seed_nodes.json"
    if candidate.exists():
        return candidate
    cwd_candidate = Path("data/network/seed_nodes.json").resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return candidate


class CapabilityRegistry:
    """In-memory capability registry providing search, explanation, and confirmation."""

    def __init__(self, data: SeedData):
        self._data = data
        self._nodes_by_id: dict[str, Node] = {lead.node.id: lead.node for lead in data.leads}
        self._leads_by_node_id: dict[str, NodeSeedEntry] = {lead.node.id: lead for lead in data.leads}
        self._campaigns_by_id: dict[str, Campaign] = {c.id: c for c in data.campaigns}
        self._questions_by_id: dict[str, Question] = {}
        for campaign in data.campaigns:
            for q in campaign.questions:
                self._questions_by_id[q.id] = q

        self._matches_by_question: dict[str, list[Match]] = {}
        self._matches_by_node_and_q: dict[tuple[str, str], Match] = {}
        for lead in data.leads:
            for q_id in lead.questions:
                match_id = f"match-{lead.node.id}-{q_id.lower()}"
                match = Match(
                    id=match_id,
                    question_id=q_id,
                    node_id=lead.node.id,
                    reasons=(lead.candidate_rationale,),
                    sources=(lead.node.source,),
                    gaps=lead.confirmation_remains,
                    eligibility=Knowledge.UNKNOWN,
                    ranking_basis=data.ranking_basis,
                    ranking_version=data.ranking_version,
                    inferred=lead.inferred,
                )
                self._matches_by_question.setdefault(q_id, []).append(match)
                self._matches_by_node_and_q[(lead.node.id, q_id)] = match

    @classmethod
    def load(cls, path: str | Path | None = None) -> CapabilityRegistry:
        """Load capability registry from JSON file (or construct default if file not yet written)."""
        file_path = Path(path).resolve() if path else get_default_seed_path()
        if not file_path.exists():
            data = build_seed_data()
            return cls(data)
        raw_text = file_path.read_text(encoding="utf-8")
        data = SeedData.model_validate_json(raw_text)
        return cls(data)

    def get_node(self, node_id: str) -> Node:
        if node_id not in self._nodes_by_id:
            raise KeyError(f"Node not found: {node_id}")
        return self._nodes_by_id[node_id]

    def get_lead(self, node_id: str) -> NodeSeedEntry:
        if node_id not in self._leads_by_node_id:
            raise KeyError(f"Lead not found: {node_id}")
        return self._leads_by_node_id[node_id]

    def get_question(self, question_id: str) -> Question:
        if question_id not in self._questions_by_id:
            raise KeyError(f"Question not found: {question_id}")
        return self._questions_by_id[question_id]

    def get_campaign(self, campaign_id: str) -> Campaign:
        if campaign_id not in self._campaigns_by_id:
            raise KeyError(f"Campaign not found: {campaign_id}")
        return self._campaigns_by_id[campaign_id]

    def query_nodes_by_question(self, question_id: str) -> list[Node]:
        """Query nodes that are candidates for answering the given question.
        
        Ordered by explained ordinal ranking tier (direct target literature > methods > network),
        not by any fabricated response probability.
        """
        matching_leads = [
            lead for lead in self._data.leads
            if question_id in lead.questions
        ]
        matching_leads.sort(key=lambda lead: (lead.ranking_tier, lead.node.institution))
        return [lead.node for lead in matching_leads]

    def get_matches_for_question(self, question_id: str) -> list[Match]:
        """Return Match instances for the given question."""
        nodes = self.query_nodes_by_question(question_id)
        return [self._matches_by_node_and_q[(n.id, question_id)] for n in nodes]

    def explain_match(self, node_id: str, question_id: str) -> MatchExplanation:
        """Explain why a node matches a question, what is inferred, and what confirmation remains."""
        key = (node_id, question_id)
        if key not in self._matches_by_node_and_q:
            raise KeyError(f"No match registered between node '{node_id}' and question '{question_id}'")
        match = self._matches_by_node_and_q[key]
        lead = self._leads_by_node_id[node_id]
        node = lead.node
        contact_verified = node.contact_route is not None and node.contact_route.verification is not None
        return MatchExplanation(
            question_id=question_id,
            node_id=node_id,
            match_id=match.id,
            institution=node.institution,
            group=node.group,
            node_type=node.node_type,
            candidate_rationale=lead.candidate_rationale,
            supporting_evidence=lead.sourced_evidence,
            inferred=lead.inferred,
            confirmation_remains=lead.confirmation_remains,
            evidence_family_id=lead.evidence_family_id,
            ranking_basis=match.ranking_basis,
            ranking_version=match.ranking_version,
            ranking_tier=lead.ranking_tier,
            resource_available=node.resource_available,
            analysis_permission=node.analysis_permission,
            contact_verified=contact_verified,
            supplies_mva_evidence=lead.supplies_mva_evidence,
            match=match,
            node=node,
        )

    def confirm_node(self, node_id: str, event: OperationalResponse) -> Node:
        """Confirm node resource or permission using an authentic institutional operational response."""
        node = self.get_node(node_id)
        data = node.model_dump()
        updates: dict[str, Any] = {
            "confirmation_events": (*node.confirmation_events, event),
        }
        if event.resource_available is not Knowledge.UNKNOWN:
            updates["resource_available"] = event.resource_available
        if event.analysis_permission is not Knowledge.UNKNOWN:
            updates["analysis_permission"] = event.analysis_permission
        # Node validator raises if event is not authentic institutional or node_identity mismatches
        return Node(**(data | updates))

    def get_evidence_family_id(self, node_id: str) -> str | None:
        """Return the shared or individual evidence-family ID for the node."""
        return self._leads_by_node_id[node_id].evidence_family_id

    def all_nodes(self, scope: CampaignScope | None = None) -> list[Node]:
        leads = self._data.leads
        if scope is not None:
            leads = tuple(lead for lead in leads if lead.campaign_scope == scope)
        return [lead.node for lead in leads]

    def all_questions(self, scope: CampaignScope | None = None) -> list[Question]:
        questions = list(self._questions_by_id.values())
        if scope is not None:
            questions = [q for q in questions if q.scope == scope]
        return questions

    def all_campaigns(self) -> list[Campaign]:
        return list(self._campaigns_by_id.values())

    def content_digest(self) -> str:
        """Compute the content digest over the canonical seed data."""
        return content_digest(self._data)


_DEFAULT_REGISTRY: CapabilityRegistry | None = None


def get_registry(path: str | Path | None = None) -> CapabilityRegistry:
    """Return a shared or loaded CapabilityRegistry instance."""
    global _DEFAULT_REGISTRY
    if path is not None:
        return CapabilityRegistry.load(path)
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = CapabilityRegistry.load()
    return _DEFAULT_REGISTRY


def load_seed(path: str | Path | None = None) -> CapabilityRegistry:
    """Load capability registry from seed nodes JSON."""
    return CapabilityRegistry.load(path)


def query_nodes_by_question(question_id: str, registry: CapabilityRegistry | None = None) -> list[Node]:
    """Query nodes for a question using the active or default registry."""
    reg = registry or get_registry()
    return reg.query_nodes_by_question(question_id)


def explain_match(node_id: str, question_id: str, registry: CapabilityRegistry | None = None) -> MatchExplanation:
    """Explain match between a node and question using the active or default registry."""
    reg = registry or get_registry()
    return reg.explain_match(node_id, question_id)


def confirm_node(node_id: str, event: OperationalResponse, registry: CapabilityRegistry | None = None) -> Node:
    """Confirm node resource using the active or default registry."""
    reg = registry or get_registry()
    return reg.confirm_node(node_id, event)
