"""Contract tests for origin, scientific scope and independent permission grants."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from rarepipe.stages.network.model import (
    ActionEvent, AdditionalResponseState, Assessment, Authorization, Campaign, CampaignMode,
    CampaignScope, ClaimDirection, ClaimRelation, Compartment, Contribution, EvidenceCriteria,
    HumanConfirmation, IndependenceAssertion, Intervention, LearningFeedback, Lineage, Match,
    NetworkEnvelope, Node, NodeType, OperationalResponse, Origin, PolicyArtifact, PublicSource,
    Question, Request, Restrictions, ScientificFinding, UsePurpose, new_id,
)
from rarepipe.stages.prospective.model import Actor, ActorType, Knowledge, Quantity, Role
from rarepipe.stages.prospective.nodes import EvidenceEnvelope, ResponseState


NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def actor(kind=ActorType.AGENT):
    return Actor(actor_type=kind, identity="test-extractor", roles=[Role.SCIENTIFIC_LEAD])


def criteria(**updates):
    return EvidenceCriteria(**dict(intervention=Intervention.NICOTINIC_ACID,
                                   compartment=Compartment.INTRACELLULAR,
                                   endpoint="NAD", **updates))


def question(campaign_id, **updates):
    data = dict(campaign_id=campaign_id, scope=CampaignScope.MVA_SCIENTIFIC,
                decision="Is intracellular NAD changed?", evidence_criteria=criteria(),
                required_reviewer=Role.SCIENTIFIC_LEAD)
    return Question(**(data | updates))


def finding(q, *, origin=Origin.AUTHENTIC_INSTITUTIONAL, context=None, restrictions=None):
    return ScientificFinding(
        origin=origin, state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(question_id=q.id, node_identity="fictional-node",
                                 response_state=ResponseState.MEASURED_EFFECT),
        context=context or q.evidence_criteria, quality="VALID",
        restrictions=restrictions or Restrictions(),
    )


def contribution(q, *, event=None, direction=ClaimDirection.UNRESOLVED, family=None, **updates):
    event = event or finding(q)
    data = dict(origin=event.origin, derived_from=(event.lineage(),), campaign_id=q.campaign_id,
                scope=q.scope, request_id=new_id(), responder="fictional responder", source="test-source",
                received_at=NOW, event=event, extractor=actor(), evidence_family_id=family or new_id(),
                relations=(ClaimRelation(claim_id=new_id(), question=q, direction=direction,
                                         rationale="source-grounded extraction"),))
    return Contribution(**(data | updates))


def test_a01_node_unknown_defaults_and_native_types():
    node = Node(institution="Fictional lab", node_type=NodeType.EVIDENCE_PRODUCING_LAB,
                source=PublicSource(reference="https://example.org/profile"))
    assert node.resource_available is Knowledge.UNKNOWN
    assert node.analysis_permission is Knowledge.UNKNOWN
    for quantity in (node.capacity, node.cost, node.turnaround):
        assert isinstance(quantity, Quantity)
        assert quantity.value is None
        assert quantity.null_reason is Knowledge.UNKNOWN


def test_a02_public_match_needs_new_institutional_event():
    node = Node(institution="Fictional lab", node_type=NodeType.ANALYSIS_SERVICE,
                source=PublicSource(reference="https://example.org/profile"))
    match = Match(question_id=new_id(), node_id=node.id, reasons=("public methods",),
                  sources=(node.source,), ranking_basis="capability", ranking_version="1")
    assert match.eligibility is Knowledge.UNKNOWN
    data = node.model_dump()
    with pytest.raises(ValidationError, match="new institutional evidence"):
        Node(**(data | {"resource_available": True}))
    event = OperationalResponse(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=AdditionalResponseState.CAPABILITY_REPORTED, resource_available=True,
        envelope=NetworkEnvelope(question_id=match.question_id, node_identity=node.id,
                                 response_state=AdditionalResponseState.CAPABILITY_REPORTED))
    confirmed = Node(**(data | {"resource_available": True, "confirmation_events": (event,)}))
    assert confirmed.resource_available is True
    assert confirmed.analysis_permission is Knowledge.UNKNOWN
    public_event = OperationalResponse(**(event.model_dump() | {"origin": Origin.PUBLIC_EVIDENCE}))
    with pytest.raises(ValidationError):
        Node(**(data | {"resource_available": True, "confirmation_events": (public_event,)}))


@pytest.mark.parametrize("intervention", [Intervention.NAM, Intervention.NR, Intervention.NMN])
def test_a03_intervention_mismatch_survives(intervention):
    q = question(new_id())
    context = EvidenceCriteria(**(q.evidence_criteria.model_dump() | {"intervention": intervention}))
    event = finding(q, context=context)
    stored = Contribution.model_validate_json(contribution(q, event=event).model_dump_json())
    assert stored.event.context.intervention is intervention
    assert not stored.event.matches(q.evidence_criteria)
    with pytest.raises(ValidationError, match="matching intervention"):
        contribution(q, event=event, direction=ClaimDirection.SUPPORTS)
    assert len(set(Intervention)) == 4


def test_a04_blood_cannot_satisfy_intracellular_question():
    q = question(new_id())
    event = finding(q, context=EvidenceCriteria(**(q.evidence_criteria.model_dump() |
                                                  {"compartment": Compartment.BLOOD})))
    assert not event.matches(q.evidence_criteria)
    with pytest.raises(ValidationError, match="compartment"):
        contribution(q, event=event, direction=ClaimDirection.SUPPORTS)
    assert contribution(q, event=event).relations[0].direction is ClaimDirection.UNRESOLVED


def test_a05_missing_interpretation_stays_unknown_after_roundtrip():
    q = question(new_id(), evidence_criteria=EvidenceCriteria())
    stored = Contribution.model_validate_json(contribution(q).model_dump_json())
    assert stored.event.context.endpoint is None
    assert stored.event.context.intervention is Knowledge.UNKNOWN
    assert stored.event.context.compartment is Knowledge.UNKNOWN
    assert stored.event.context.experimental_unit is None
    assert stored.event.context.denominator is None
    assert stored.event.value.value is None
    assert stored.event.value.null_reason is Knowledge.UNKNOWN
    assert not stored.event.matches(q.evidence_criteria)


def confirmation(ref):
    return HumanConfirmation(actor=actor(ActorType.HUMAN), role=Role.SCIENTIFIC_LEAD,
                             timestamp=NOW, statement_ref=ref, rationale="Reviewed source")


def test_a06_shared_family_is_not_replication_and_independence_needs_reason():
    q = question(new_id())
    family = new_id()
    first = contribution(q, family=family)
    second = contribution(q, family=family, responder="another sender")
    assert not first.independent_of(second)
    different = contribution(q)
    assert not first.independent_of(different)
    assertion = IndependenceAssertion(other_family_id=different.evidence_family_id,
                                      reason="Separate experimental execution", confirmation=confirmation(first.id))
    established = contribution(q, family=family, independence=(assertion,))
    assert established.independent_of(different)
    with pytest.raises(ValidationError):
        IndependenceAssertion(other_family_id=new_id(), reason="", confirmation=confirmation(first.id))
    with pytest.raises(ValidationError, match="cannot be independent"):
        contribution(q, family=different.evidence_family_id, independence=(assertion,))


def test_a07_response_distinctions_and_separate_event_types():
    states = {AdditionalResponseState.DECLINED, ResponseState.NO_RESPONSE,
              AdditionalResponseState.NO_RELEVANT_RESOURCE, AdditionalResponseState.INVALID_MEASUREMENT,
              AdditionalResponseState.INFORMATIVE_NEGATIVE}
    assert len(states) == 5
    assert not states.intersection(Knowledge)
    q = question(new_id())
    for state in states:
        envelope = NetworkEnvelope(question_id=q.id, node_identity="fixture", response_state=state)
        assert isinstance(envelope, EvidenceEnvelope)
        cls = ScientificFinding if state in {AdditionalResponseState.INVALID_MEASUREMENT,
                                            AdditionalResponseState.INFORMATIVE_NEGATIVE} else OperationalResponse
        event = cls(origin=Origin.SYNTHETIC, state=state, envelope=envelope)
        assert type(event).model_validate_json(event.model_dump_json()).state == state
        wrong = OperationalResponse if cls is ScientificFinding else ScientificFinding
        with pytest.raises(ValidationError):
            wrong(origin=Origin.SYNTHETIC, state=state, envelope=envelope)


def test_a15_live_campaign_rejects_synthetic_contribution_and_feedback():
    campaign_id = new_id()
    q = question(campaign_id)
    item = contribution(q, event=finding(q, origin=Origin.SYNTHETIC))
    data = dict(id=campaign_id, purpose="Test campaign", scope=q.scope, questions=(q,))
    with pytest.raises(ValidationError, match="synthetic contributions"):
        Campaign(**data, mode=CampaignMode.LIVE, contributions=(item,))
    assert Campaign(**data, mode=CampaignMode.SYNTHETIC, contributions=(item,)).contributions == (item,)
    feedback = LearningFeedback(origin=Origin.SYNTHETIC, campaign_id=campaign_id,
                                action_id=new_id(), assessor=actor(), method="fixture", version="1",
                                status="synthetic")
    with pytest.raises(ValidationError, match="synthetic contributions"):
        Campaign(**data, mode=CampaignMode.LIVE, feedback=(feedback,))
    with pytest.raises(ValidationError, match="observed feedback"):
        LearningFeedback(**(feedback.model_dump() | {"status": "observed"}))
    with pytest.raises(ValidationError, match="inherit"):
        contribution(q, event=item.event, origin=Origin.AUTHENTIC_INSTITUTIONAL)
    with pytest.raises(ValidationError):
        item.origin = Origin.AUTHENTIC_INSTITUTIONAL
    with pytest.raises(ValueError, match="successor"):
        item.model_copy(update={"origin": Origin.AUTHENTIC_INSTITUTIONAL})
    with pytest.raises(ValidationError, match="inherit"):
        Lineage(record_id=new_id(), origin=Origin.PUBLIC_EVIDENCE, parents=(item.lineage(),))


def test_a24_restrictions_roundtrip_and_inherited_use_query():
    q = question(new_id())
    grant = Restrictions(case_ref="case-local", case_use=True)
    item = contribution(q, event=finding(q, restrictions=grant), restrictions=grant)
    stored = Contribution.model_validate_json(item.model_dump_json())
    assert stored.may_use(UsePurpose.CASE_USE, case_ref="case-local")
    assert not stored.may_use(UsePurpose.CASE_USE, case_ref="another-case")
    for purpose in (UsePurpose.PUBLIC_EXPORT, UsePurpose.OTHER_CASE, UsePurpose.POLICY_TRAINING):
        assert not stored.may_use(purpose)
    broadened = contribution(q, event=item.event, restrictions=Restrictions(public_export=True))
    assert not broadened.may_use(UsePurpose.PUBLIC_EXPORT)
    feedback = LearningFeedback(origin=item.origin, derived_from=(item.lineage(),),
                                restrictions=Restrictions(policy_training=True), campaign_id=q.campaign_id,
                                action_id=new_id(), assessor=actor(), method="assessment", version="1")
    assert not feedback.may_use(UsePurpose.POLICY_TRAINING)


def test_a26_partnership_cannot_attach_to_mva_question():
    q = question(new_id())
    with pytest.raises(ValidationError, match="another campaign or scope"):
        contribution(q, scope=CampaignScope.PARTNERSHIP_ONCOLOGY)
    with pytest.raises(ValidationError, match="another campaign or scope"):
        contribution(q, campaign_id=new_id())


def test_extraction_is_not_human_review_and_relations_are_per_claim():
    q = question(new_id())
    event = finding(q)
    relations = (ClaimRelation(claim_id=new_id(), question=q, direction=ClaimDirection.SUPPORTS,
                               rationale="Matching NAD observation"),
                 ClaimRelation(claim_id=new_id(), question=q, direction=ClaimDirection.UNRESOLVED,
                               rationale="Functional consequence not measured"))
    item = contribution(q, event=event, relations=relations)
    assert item.human_confirmation is None
    assert {r.direction for r in item.relations} == {ClaimDirection.SUPPORTS, ClaimDirection.UNRESOLVED}
    with pytest.raises(ValidationError, match="only a human"):
        HumanConfirmation(actor=actor(), role=Role.SCIENTIFIC_LEAD, timestamp=NOW,
                          statement_ref=item.id, rationale="Agent cannot sign")
    assessment_id = new_id()
    data = dict(id=assessment_id, origin=item.origin, derived_from=(item.lineage(),), contribution=item,
                question=q, relations=relations, reviewer=actor(), decision="ACCEPTED")
    with pytest.raises(ValidationError, match="human review"):
        Assessment(**data)
    confirmed = confirmation(assessment_id)
    assessed = Assessment(**(data | {"reviewer": confirmed.actor, "confirmation": confirmed}))
    assert assessed.decision == "ACCEPTED"


def test_remaining_records_roundtrip_and_action_mask():
    q = question(new_id())
    request = Request(origin=Origin.SYNTHETIC, campaign_id=q.campaign_id, question_id=q.id,
                      node_id=new_id(), content="Bounded question", sender=actor(),
                      recipient="fixture@example.org", disclosure_scope="public")
    assert Request.model_validate_json(request.model_dump_json()) == request
    assert request.authorization_ref is None
    action_data = dict(origin=Origin.SYNTHETIC, campaign_id=q.campaign_id, previous_state="DRAFT",
                       eligible_options=("wait",), selected_action="wait", randomized=True,
                       policy_version="1", config_version="1", occurred_at=NOW)
    with pytest.raises(ValidationError, match="selection probability"):
        ActionEvent(**action_data)
    action = ActionEvent(**action_data, selection_probability=1)
    assert ActionEvent.model_validate_json(action.model_dump_json()) == action
    with pytest.raises(ValidationError, match="must be eligible"):
        ActionEvent(**(action_data | {"selected_action": "send"}), selection_probability=1)
    policy = PolicyArtifact(origin=Origin.SYNTHETIC, algorithm="fixture", feature_contract=("state",),
                            training_config=(), seed=123)
    assert PolicyArtifact.model_validate_json(policy.model_dump_json()) == policy
    auth_id = new_id()
    signed = confirmation(auth_id)
    authorization = Authorization(id=auth_id, issuer=signed.actor, authority="test-only",
                                  confirmation=signed, sender="fixture", recipients=("fixture",),
                                  purpose="test", content_refs=(request.id,), valid_from=NOW,
                                  valid_until=NOW.replace(year=2027))
    assert Authorization.model_validate_json(authorization.model_dump_json()) == authorization
    assert authorization.limits.max_requests is None
    assert authorization.limits.spend_limit.null_reason is Knowledge.UNKNOWN


def test_nonresponse_cannot_assert_absence_and_qc_failure_cannot_support_claim():
    q = question(new_id())
    for state in (ResponseState.NO_RESPONSE, ResponseState.NOT_SEARCHED,
                  AdditionalResponseState.DECLINED, AdditionalResponseState.CANNOT_DISCLOSE):
        with pytest.raises(ValidationError, match="cannot confirm"):
            OperationalResponse(origin=Origin.AUTHENTIC_INSTITUTIONAL, state=state,
                                resource_available=False,
                                envelope=NetworkEnvelope(question_id=q.id, node_identity="fixture",
                                                         response_state=state))
    for state in (ResponseState.INCONCLUSIVE_RESULT, AdditionalResponseState.INVALID_MEASUREMENT):
        event = ScientificFinding(origin=Origin.AUTHENTIC_INSTITUTIONAL, state=state,
                                  envelope=NetworkEnvelope(question_id=q.id, node_identity="fixture",
                                                           response_state=state),
                                  context=q.evidence_criteria, quality="VALID")
        with pytest.raises(ValidationError, match="scientific relation"):
            contribution(q, event=event, direction=ClaimDirection.SUPPORTS)


def test_immutable_collections_and_event_lineage_cannot_be_dropped():
    q = question(new_id())
    event = finding(q, origin=Origin.SYNTHETIC)
    with pytest.raises(ValidationError, match="source event's lineage"):
        contribution(q, event=event, derived_from=())
    item = contribution(q, event=event)
    campaign = Campaign(id=q.campaign_id, purpose="fixture", scope=q.scope,
                        mode=CampaignMode.SYNTHETIC, contributions=(item,))
    assert isinstance(campaign.contributions, tuple)
    with pytest.raises(ValidationError):
        campaign.mode = CampaignMode.LIVE
    with pytest.raises(ValidationError):
        item.restrictions.policy_training = True
    with pytest.raises(ValidationError, match="identify this contribution"):
        contribution(q, human_confirmation=confirmation(new_id()))
