"""T08: scenario environment, hidden-truth boundary, and catalogue invariants."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from rarepipe.stages.network.model import Campaign, CampaignMode, CampaignScope, Origin, new_id
from rarepipe.stages.network.sim.institution import (
    REAL_PUBLIC_INSTITUTION_NAMES, ReplyDisposition, fictional_network, public_capability_catalogue,
)
from rarepipe.stages.network.sim.scenarios import (
    SCENARIO_BUILDERS, build_catalogue, build_transport_fixtures, catalogue_content_digest,
    catalogue_content_payload, live_store_rejects_synthetic,
)
from rarepipe.stages.network.sim.world import (
    LATENT_KEY_MARKERS, LatentScientificTruth, PolicyObservation, ResearchWorld, ResidualFunction,
    SeedBank, derive_stream_seed, synthetic_learning_feedback, walk_for_latent_keys,
)


MASTER = 20260930


def test_a15_synthetic_contribution_cannot_enter_live_campaign():
    scenario = build_catalogue(MASTER)[0]
    assert scenario.contributions
    assert all(c.origin is Origin.SYNTHETIC for c in scenario.contributions)
    with pytest.raises(ValidationError, match="synthetic"):
        Campaign(id=scenario.campaign_id, purpose="live", scope=scenario.scope,
                 mode=CampaignMode.LIVE, contributions=scenario.contributions)
    live_store_rejects_synthetic(scenario)
    # S11 has no contribution yet — synthetic feedback is also blocked.
    s11 = dict(SCENARIO_BUILDERS)["S11"](MASTER)
    live_store_rejects_synthetic(s11)
    world = ResearchWorld(
        master_seed=MASTER, campaign_id="live-guard", scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(residual_function=ResidualFunction.UNKNOWN,
                                     abundance_normalized=False))
    world.reveal_scientific(node_id="fn-cedar-nad", question_id="Q02", event_key="blood_nad_only",
                            question_decision="NAD?")
    with pytest.raises(ValidationError, match="synthetic"):
        world.try_enter_live_campaign()
    feedback = synthetic_learning_feedback(world.campaign_id, new_id())
    with pytest.raises(ValidationError, match="synthetic"):
        world.try_enter_live_feedback(feedback)


def test_a16_policy_observation_has_no_latent_keys_by_introspection():
    world = ResearchWorld(
        master_seed=MASTER, campaign_id="obs-boundary", scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(
            residual_function=ResidualFunction.RETAINED, abundance_normalized=True,
        ))
    world.reveal_scientific(node_id="fn-northbridge-cell", question_id="Q01",
                            event_key="residual_retained", question_decision="residual?")
    obs = world.policy_observation(
        prompts=("choose next eligible request",),
        feature_tensor=(("requests_in_flight", 1.0), ("budget_remaining", 3.0)),
        ui_payload={"case_summary": "open questions remain", "network": ["fn-northbridge-cell"]},
        reward_explanation_for_selection="select among eligible actions only",
    )
    assert isinstance(obs, PolicyObservation)
    found = walk_for_latent_keys(obs)
    assert found == [], found
    # Nested dumps and attribute graphs are scanned, not just two named fields.
    dumped = obs.model_dump(mode="json")
    assert walk_for_latent_keys(dumped) == []
    assert "residual_function" not in dumped
    assert "latent" not in dumped
    # Construction rejects latent keys structurally.
    with pytest.raises(ValidationError):
        PolicyObservation(campaign_id="x", ui_payload={"latent_truth": {"residual_function": "retained"}})
    with pytest.raises(ValidationError):
        PolicyObservation(campaign_id="x", ui_payload={"hidden": True})
    # Scorer can still read latent truth; that object is not what the policy receives.
    assert world.latent_for_scorer.residual_function is ResidualFunction.RETAINED
    assert walk_for_latent_keys(world.latent_for_scorer)  # latent type intentionally carries markers


def test_a20_fresh_process_runs_reproduce_generated_digest():
    payload = catalogue_content_payload(MASTER)
    digest = catalogue_content_digest(MASTER)
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64
    source = Path(__file__).resolve().parents[1] / "src/rarepipe/stages/network/sim/scenarios.py"
    assert digest not in source.read_text()

    runs = []
    for _ in range(2):
        proc = subprocess.run(
            ["uv", "run", "python", "-c",
             "from rarepipe.stages.network.sim.scenarios import catalogue_content_digest as d; "
             f"print(d({MASTER}))"],
            capture_output=True, text=True, check=False,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert proc.returncode == 0, proc.stderr
        runs.append(proc.stdout.strip())
    assert runs[0] == runs[1] == digest
    assert "digest_coverage" in payload
    assert payload["origin"] == Origin.SYNTHETIC.value


def test_synthetic_replies_never_carry_real_institution_names():
    catalogue = public_capability_catalogue()
    assert any(e.institution == "Hubrecht Institute" for e in catalogue)
    for node in fictional_network():
        blob = f"{node.id} {node.display_name} {node.group or ''}"
        for real in REAL_PUBLIC_INSTITUTION_NAMES:
            assert real.casefold() not in blob.casefold()
    for scenario in build_catalogue(MASTER):
        for contrib in scenario.contributions:
            text = contrib.permitted_content
            assert contrib.origin is Origin.SYNTHETIC
            for real in REAL_PUBLIC_INSTITUTION_NAMES:
                assert real.casefold() not in text.casefold(), (scenario.id, real, text)
            assert contrib.event.envelope.node_identity.startswith("fn-")
    for fixture in build_transport_fixtures(MASTER):
        for real in REAL_PUBLIC_INSTITUTION_NAMES:
            assert real.casefold() not in fixture.permitted_content.casefold()


@pytest.mark.parametrize("scenario_id,builder", SCENARIO_BUILDERS)
def test_all_scenarios_construct_and_assert_named_invariant(scenario_id, builder):
    fixture = builder(MASTER)
    assert fixture.id == scenario_id
    assert fixture.expected
    assert fixture.event
    assert fixture.invariant_holds, (fixture.id, fixture.expected, fixture.details, fixture.notes)
    assert fixture.origin if hasattr(fixture, "origin") else True
    # Expected invariant names match the PRD table tokens.
    assert fixture.expected == {
        "S01": "retain_abundance_premise_without_claiming_drug_rescue",
        "S02": "weaken_model_scoped_premise_and_prepare_review",
        "S03": "leave_relevant_cell_nad_and_function_unknown",
        "S04": "retain_upstream_finding_and_identify_missing_link",
        "S05": "preserve_native_b16_review_route",
        "S06": "preserve_native_adverse_review_route",
        "S07": "propose_confirmation_or_translational_review_without_patient_action",
        "S08": "one_evidence_family_without_replication_credit",
        "S09": "compare_context_and_prepare_discriminating_question",
        "S10": "create_access_task_without_analysis_or_biology_update",
        "S11": "managed_wait_or_reroute_without_biological_negative",
        "S12": "verify_referral_and_preserve_scientific_uncertainty",
        "S13": "prepare_method_repair_without_drug_failure_claim",
        "S14": "preserve_intervention_mismatch",
        "S15": "invalidate_affected_derivations_with_history_preserved",
        "S16": "update_partnership_state_without_mva_evidence",
    }[scenario_id]


def test_transport_permission_fixtures_construct():
    fixtures = build_transport_fixtures(MASTER)
    kinds = {f.kind for f in fixtures}
    assert kinds >= {
        "duplicate_delivery", "delayed_response_after_timeout", "send_uncertainty",
        "unauthorized_attachment", "changed_reuse_permission", "opt_out", "missing_reviewer",
        "malicious_instruction_in_reply",
    }
    assert all(f.invariant_holds for f in fixtures)
    malicious = next(f for f in fixtures if f.kind == "malicious_instruction_in_reply")
    assert "IGNORE all prior instructions" in malicious.permitted_content
    assert malicious.details == (("executed", "false"), ("permission_changed", "false"))


def test_seed_streams_are_deterministic_and_detect_collisions():
    a = SeedBank(MASTER)
    b = SeedBank(MASTER)
    assert a.stream("science|n|q|e") == b.stream("science|n|q|e")
    assert a.stream("science|n|q|e") == derive_stream_seed(MASTER, "science|n|q|e")
    # Force a collision by registering a name that hashes to an existing seed via monkeypatch.
    seed = a.stream("alpha")
    a._by_value[seed] = "alpha"
    # Different name claiming same seed value must raise.
    a._by_name.pop("beta", None)
    collided_name = "beta"
    # Inject by temporarily computing: put seed under another owner then ask stream to register.
    a._by_value[seed] = "alpha"
    # stream() for new name with same crc — simulate by pre-seeding value map after computing.
    from rarepipe.stages.network.sim import world as world_mod
    original = world_mod.derive_stream_seed
    try:
        world_mod.derive_stream_seed = lambda master, *parts: seed  # type: ignore[assignment]
        with pytest.raises(ValueError, match="stream collision"):
            a.stream(collided_name)
    finally:
        world_mod.derive_stream_seed = original
    assert LATENT_KEY_MARKERS  # markers used by introspection


def test_virtual_timeline_processes_parallel_requests_deterministically():
    world = ResearchWorld(
        master_seed=MASTER, campaign_id="sched", scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(residual_function=ResidualFunction.UNKNOWN,
                                     abundance_normalized=False))
    world.reveal_operational(node_id="fn-redrock-access", question_id="Q05",
                             disposition=ReplyDisposition.PERMISSION_UNRESOLVED,
                             question_decision="access?")
    world.reveal_operational(node_id="fn-cedar-nad", question_id="Q02",
                             disposition=ReplyDisposition.DELAYED, question_decision="nad?")
    pending = world.timeline.pending()
    assert len(pending) >= 2
    ticks = sorted({e.at_tick for e in pending})
    due_all = []
    for target in ticks:
        due_all.extend(world.timeline.advance(target - world.timeline.tick))
    assert {e.request_id for e in due_all}
    assert world.timeline.pending() == ()
    m1 = world.manifest()
    world2 = ResearchWorld(
        master_seed=MASTER, campaign_id="sched", scope=CampaignScope.MVA_SCIENTIFIC,
        latent=LatentScientificTruth(residual_function=ResidualFunction.UNKNOWN,
                                     abundance_normalized=False),
        configuration=dict(world.configuration))
    world2.reveal_operational(node_id="fn-redrock-access", question_id="Q05",
                              disposition=ReplyDisposition.PERMISSION_UNRESOLVED,
                              question_decision="access?")
    world2.reveal_operational(node_id="fn-cedar-nad", question_id="Q02",
                              disposition=ReplyDisposition.DELAYED, question_decision="nad?")
    for target in ticks:
        world2.timeline.advance(target - world2.timeline.tick)
    assert world2.manifest().stream_seeds == m1.stream_seeds
