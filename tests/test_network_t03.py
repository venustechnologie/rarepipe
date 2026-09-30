"""Acceptance tests for seed capability registry (PRD §7, Tasks T01/T03).

Asserts:
- A01: every seeded node has a source URL, a node type, and unknown availability and permission.
- A02: a match built from a public profile carries no confirmed resource or collaboration, and a
  method that would confirm it requires a new evidence event to be supplied.
- A03: question routes preserve intervention identity — a node routed to Q02 (nicotinic acid) is not
  thereby a source about NMN.
- Helsinki and Oulu share an evidence-family id; ICR is typed as a historical/custodial lead; no node
  has a verified contact route.
- Centre Léon Bérard is isolated in a separate PARTNERSHIP_ONCOLOGY campaign with listing-reported
  states and supplies no MVA scientific evidence.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from rarepipe.stages.network.model import (
    AdditionalResponseState, CampaignScope, ClaimDirection, ClaimRelation,
    Compartment, Contribution, EvidenceCriteria, Intervention, Knowledge,
    NetworkEnvelope, Node, NodeType, OperationalResponse, Origin,
    PublicSource, Quantity, ScientificFinding, new_id,
)
from rarepipe.stages.network.registry import (
    CapabilityRegistry, MatchExplanation, NodeSeedEntry, explain_match,
    load_seed, query_nodes_by_question,
)
from rarepipe.stages.prospective.model import Actor, ActorType, Role
from rarepipe.stages.prospective.nodes import ResponseState


NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def registry() -> CapabilityRegistry:
    return load_seed()


def test_a01_every_seeded_node_has_source_url_type_and_unknown_fields(registry: CapabilityRegistry):
    """A01: Each seeded node has a source URL, a node type, and unknown availability/permission."""
    nodes = registry.all_nodes()
    # 9 MVA leads + 1 partnership lead
    assert len(nodes) == 10

    for node in nodes:
        # Source must be present, with a valid HTTP/HTTPS URL
        assert isinstance(node.source, PublicSource)
        assert node.source.reference.startswith(("http://", "https://"))
        assert node.source.accessed_at is not None

        # Node type must be one of the four defined NodeType members
        assert isinstance(node.node_type, NodeType)
        assert node.node_type in (
            NodeType.EVIDENCE_PRODUCING_LAB,
            NodeType.ANALYSIS_SERVICE,
            NodeType.DISCOVERY_NETWORK,
            NodeType.HISTORICAL_CUSTODIAL_LEAD,
        )

        # Operational availability and permission MUST default to UNKNOWN
        assert node.resource_available is Knowledge.UNKNOWN
        assert node.analysis_permission is Knowledge.UNKNOWN

        # Capacity, cost, and turnaround MUST be unknown Quantity objects
        for field_name in ("capacity", "cost", "turnaround"):
            qty = getattr(node, field_name)
            assert isinstance(qty, Quantity)
            assert qty.value is None
            assert qty.null_reason is Knowledge.UNKNOWN

        # No confirmation events may be present in seed state
        assert node.confirmation_events == ()


def test_a02_match_carries_no_confirmed_resource_and_requires_new_evidence_event(registry: CapabilityRegistry):
    """A02: Public profile match carries no confirmed resource; confirmation requires new institutional event."""
    # Explain match for Hubrecht on Q01
    explanation = registry.explain_match("node-hubrecht-kops", "Q01")
    assert isinstance(explanation, MatchExplanation)

    # Match carries unknown eligibility, and node availability/permission are UNKNOWN
    assert explanation.match.eligibility is Knowledge.UNKNOWN
    assert explanation.resource_available is Knowledge.UNKNOWN
    assert explanation.analysis_permission is Knowledge.UNKNOWN

    # Attempting to confirm with public evidence MUST fail
    public_event = OperationalResponse(
        origin=Origin.PUBLIC_EVIDENCE,
        state=AdditionalResponseState.CAPABILITY_REPORTED,
        resource_available=True,
        envelope=NetworkEnvelope(
            question_id="Q01",
            node_identity=explanation.node.id,
            response_state=AdditionalResponseState.CAPABILITY_REPORTED,
        ),
    )
    with pytest.raises(ValidationError, match="new institutional evidence"):
        explanation.confirm_resource(public_event)

    # Attempting to confirm with wrong node identity MUST fail
    wrong_node_event = OperationalResponse(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=AdditionalResponseState.CAPABILITY_REPORTED,
        resource_available=True,
        envelope=NetworkEnvelope(
            question_id="Q01",
            node_identity="some-other-node",
            response_state=AdditionalResponseState.CAPABILITY_REPORTED,
        ),
    )
    with pytest.raises(ValidationError, match="new institutional evidence"):
        explanation.confirm_resource(wrong_node_event)

    # Supplying an authentic institutional event for this node succeeds
    authentic_event = OperationalResponse(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=AdditionalResponseState.CAPABILITY_REPORTED,
        resource_available=True,
        analysis_permission=True,
        envelope=NetworkEnvelope(
            question_id="Q01",
            node_identity=explanation.node.id,
            response_state=AdditionalResponseState.CAPABILITY_REPORTED,
        ),
    )
    confirmed_node = explanation.confirm_resource(authentic_event)
    assert confirmed_node.resource_available is True
    assert confirmed_node.analysis_permission is True
    assert authentic_event in confirmed_node.confirmation_events


def test_a03_question_routes_preserve_intervention_identity(registry: CapabilityRegistry):
    """A03: Question routes preserve intervention identity — Q02 (nicotinic acid) is not about NMN."""
    q02 = registry.get_question("Q02")
    assert q02.evidence_criteria.intervention is Intervention.NICOTINIC_ACID

    # Only Helsinki and Oulu are routed to Q02
    q02_nodes = registry.query_nodes_by_question("Q02")
    q02_ids = {n.id for n in q02_nodes}
    assert q02_ids == {"node-helsinki-aswlab", "node-oulu-pirinen"}

    # An NMN scientific finding cannot match Q02's criteria
    nmn_criteria = EvidenceCriteria(
        intervention=Intervention.NMN,
        compartment=Compartment.INTRACELLULAR,
        endpoint="NAD",
    )
    nmn_finding = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(
            question_id="Q02",
            node_identity="node-helsinki-aswlab",
            response_state=ResponseState.MEASURED_EFFECT,
        ),
        context=nmn_criteria,
        quality="VALID",
    )
    assert not nmn_finding.matches(q02.evidence_criteria)

    # Attempting to attach an NMN finding as supporting Q02 in a Contribution MUST raise ValidationError
    actor = Actor(actor_type=ActorType.AGENT, identity="test-agent", roles=[Role.RESEARCH_OPERATIONS])
    with pytest.raises(ValidationError, match="matching intervention"):
        Contribution(
            origin=Origin.AUTHENTIC_INSTITUTIONAL,
            derived_from=(nmn_finding.lineage(),),
            campaign_id=q02.campaign_id,
            scope=q02.scope,
            request_id=new_id(),
            responder="Helsinki ASWLab",
            source="test-source",
            received_at=NOW,
            event=nmn_finding,
            extractor=actor,
            evidence_family_id="ef-test",
            relations=(
                ClaimRelation(
                    claim_id=new_id(),
                    question=q02,
                    direction=ClaimDirection.SUPPORTS,
                    rationale="NMN finding cannot support nicotinic acid question",
                ),
            ),
        )


def test_helsinki_and_oulu_share_evidence_family_id(registry: CapabilityRegistry):
    """Helsinki (ASWLab) and Oulu (Pirinen Lab) share an evidence-family ID for the human niacin study."""
    helsinki_family = registry.get_evidence_family_id("node-helsinki-aswlab")
    oulu_family = registry.get_evidence_family_id("node-oulu-pirinen")

    assert helsinki_family is not None
    assert helsinki_family == oulu_family
    assert helsinki_family == "ef-niacin-trial-pmid32386566"

    # Verify that two contributions using this shared family ID cannot be claimed as independent
    q02 = registry.get_question("Q02")
    finding_helsinki = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(
            question_id="Q02",
            node_identity="node-helsinki-aswlab",
            response_state=ResponseState.MEASURED_EFFECT,
        ),
        context=q02.evidence_criteria,
        quality="VALID",
    )
    finding_oulu = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(
            question_id="Q02",
            node_identity="node-oulu-pirinen",
            response_state=ResponseState.MEASURED_EFFECT,
        ),
        context=q02.evidence_criteria,
        quality="VALID",
    )
    actor = Actor(actor_type=ActorType.AGENT, identity="test-agent", roles=[Role.RESEARCH_OPERATIONS])
    c_helsinki = Contribution(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(finding_helsinki.lineage(),),
        campaign_id=q02.campaign_id,
        scope=q02.scope,
        request_id=new_id(),
        responder="Helsinki ASWLab",
        source="PMID 32386566",
        received_at=NOW,
        event=finding_helsinki,
        extractor=actor,
        evidence_family_id=helsinki_family,
        relations=(),
    )
    c_oulu = Contribution(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(finding_oulu.lineage(),),
        campaign_id=q02.campaign_id,
        scope=q02.scope,
        request_id=new_id(),
        responder="Oulu Pirinen Lab",
        source="PMID 32386566",
        received_at=NOW,
        event=finding_oulu,
        extractor=actor,
        evidence_family_id=oulu_family,
        relations=(),
    )
    assert not c_helsinki.independent_of(c_oulu)
    assert not c_oulu.independent_of(c_helsinki)


def test_icr_is_typed_as_historical_custodial_lead(registry: CapabilityRegistry):
    """ICR is typed as a historical/custodial lead, NOT an assumed resource holder."""
    icr = registry.get_node("node-icr-london")
    assert icr.node_type is NodeType.HISTORICAL_CUSTODIAL_LEAD
    assert icr.resource_available is Knowledge.UNKNOWN

    explanation = registry.explain_match("node-icr-london", "Q05")
    assert "referral" in explanation.candidate_rationale.lower()
    assert any("not an assumed resource holder" in gap.lower() for gap in explanation.confirmation_remains)


def test_no_node_has_verified_contact_route(registry: CapabilityRegistry):
    """The contact route for every seeded node is unverified."""
    nodes = registry.all_nodes()
    for node in nodes:
        if node.id == "node-centre-leon-berard":
            # Centre Léon Bérard stores the directory-listed contact info@schmitt-t.com
            assert node.contact_route is not None
            assert node.contact_route.recipient == "info@schmitt-t.com"
            # Explicitly NOT verified
            assert node.contact_route.verification is None
        else:
            # 9 MVA leads have no invented contact route
            assert node.contact_route is None

    # Overall assertion: no node has a verified contact route
    assert all(node.contact_route is None or node.contact_route.verification is None for node in nodes)


def test_separate_partnership_oncology_campaign_seed(registry: CapabilityRegistry):
    """Centre Léon Bérard is seeded in a separate PARTNERSHIP_ONCOLOGY campaign and supplies no MVA evidence."""
    # Verify campaign exists with correct scope
    camp = registry.get_campaign("cmp-partnership-oncology")
    assert camp.scope is CampaignScope.PARTNERSHIP_ONCOLOGY

    # Verify initial question asks only whether they are still considering an AI partner
    assert len(camp.questions) == 1
    q_onc = camp.questions[0]
    assert q_onc.id == "Q_ONC_01"
    assert q_onc.scope is CampaignScope.PARTNERSHIP_ONCOLOGY
    assert "considering an AI partner" in q_onc.decision

    # CLB node properties
    clb = registry.get_node("node-centre-leon-berard")
    assert clb.institution == "Centre Léon Bérard"
    assert clb.node_type is NodeType.HISTORICAL_CUSTODIAL_LEAD

    # Capabilities must store listing-reported states (PUBLICLY_REPORTED), never verified facts
    assert len(clb.capabilities) == 3
    for cap in clb.capabilities:
        assert cap.evidence_status == "PUBLICLY_REPORTED"
        assert "listing-reported" in cap.description.lower()

    # CLB lead does NOT supply MVA scientific evidence and is not routed to Q01-Q06
    lead = registry.get_lead("node-centre-leon-berard")
    assert not lead.supplies_mva_evidence
    assert lead.questions == ("Q_ONC_01",)

    for q_id in ("Q01", "Q02", "Q03", "Q04", "Q05", "Q06"):
        assert "node-centre-leon-berard" not in [n.id for n in registry.query_nodes_by_question(q_id)]


def test_four_node_types_distinguished(registry: CapabilityRegistry):
    """The four node types from PRD §7 are represented and properly assigned."""
    node_types = {n.node_type for n in registry.all_nodes()}
    assert node_types == {
        NodeType.EVIDENCE_PRODUCING_LAB,
        NodeType.ANALYSIS_SERVICE,
        NodeType.DISCOVERY_NETWORK,
        NodeType.HISTORICAL_CUSTODIAL_LEAD,
    }

    # Verify specific nodes match PRD §7 classifications
    assert registry.get_node("node-hubrecht-kops").node_type is NodeType.EVIDENCE_PRODUCING_LAB
    assert registry.get_node("node-euro-bioimaging").node_type is NodeType.ANALYSIS_SERVICE
    assert registry.get_node("node-bbmri-eric").node_type is NodeType.DISCOVERY_NETWORK
    assert registry.get_node("node-icr-london").node_type is NodeType.HISTORICAL_CUSTODIAL_LEAD


def test_ranking_basis_explained_ordinal_without_fabricated_probability(registry: CapabilityRegistry):
    """Matches provide an explained ordinal ranking basis and never imply reply probability."""
    for q in registry.all_questions():
        matches = registry.get_matches_for_question(q.id)
        for match in matches:
            assert "ordinal" in match.ranking_basis.lower()
            assert "not a reply probability" in match.ranking_basis.lower()
            assert match.ranking_version == "1.0.0"
            assert match.eligibility is Knowledge.UNKNOWN


def test_publication_date_distinct_from_confirmation_date(registry: CapabilityRegistry):
    """Source publication date is stored separately from availability confirmation."""
    icr = registry.get_node("node-icr-london")
    sinclair = registry.get_node("node-harvard-sinclair")
    helsinki = registry.get_node("node-helsinki-aswlab")

    assert icr.source.published_at == datetime(2004, 11, 21, tzinfo=timezone.utc)
    assert sinclair.source.published_at == datetime(2014, 5, 8, tzinfo=timezone.utc)
    assert helsinki.source.published_at == datetime(2020, 5, 7, tzinfo=timezone.utc)

    # For all, resource availability remains UNKNOWN, with no confirmation events
    for n in (icr, sinclair, helsinki):
        assert n.resource_available is Knowledge.UNKNOWN
        assert n.analysis_permission is Knowledge.UNKNOWN
        assert n.confirmation_events == ()


def test_query_and_explain_api(registry: CapabilityRegistry):
    """Registry offers query_nodes_by_question and explain_match with complete breakdown."""
    # Test query routing
    assert len(query_nodes_by_question("Q01", registry)) == 3
    assert len(query_nodes_by_question("Q02", registry)) == 2
    assert len(query_nodes_by_question("Q03", registry)) == 2
    assert len(query_nodes_by_question("Q04", registry)) == 4
    assert len(query_nodes_by_question("Q05", registry)) == 2
    assert len(query_nodes_by_question("Q06", registry)) == 6
    assert len(query_nodes_by_question("Q_ONC_01", registry)) == 1

    # Test explain match breakdown
    exp = explain_match("node-harvard-sinclair", "Q03", registry)
    assert exp.question_id == "Q03"
    assert exp.node_id == "node-harvard-sinclair"
    assert exp.institution == "Harvard Medical School"
    assert len(exp.supporting_evidence) > 0
    assert len(exp.inferred) > 0
    assert len(exp.confirmation_remains) > 0
    assert not exp.contact_verified
