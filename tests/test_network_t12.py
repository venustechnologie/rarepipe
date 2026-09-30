"""T12: evaluation runner, generated reports, exports, claim index (A19–A24, A28, A29, A22)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rarepipe.stages.network.adapter import NativePlanAdapter, ProposalStatus
from rarepipe.stages.network.evaluate import (
    PROVENANCE_FIELDS_THAT_MAY_DIFFER,
    EvaluationConfig,
    make_family_world,
    run_evaluation,
    science_digests_match,
)
from rarepipe.stages.network.model import (
    Assessment,
    Campaign,
    CampaignMode,
    CampaignScope,
    ClaimDirection,
    ClaimRelation,
    Compartment,
    Contribution,
    EvidenceCriteria,
    Intervention,
    NetworkEnvelope,
    Origin,
    Question,
    Restrictions,
    ScientificFinding,
    UsePurpose,
    new_id,
)
from rarepipe.stages.network.report import (
    ClaimClassification,
    ExportRejected,
    build_public_export_payload,
    build_report,
    build_submission_claim_index,
    contribution_may_export,
    contribution_may_route_other_case,
    contribution_may_select_for_training,
    format_reported_rate,
    generate_report_markdown,
    invalidate_report_after_correction,
    restricted,
    write_public_export,
)
from rarepipe.stages.network.sim.reward import (
    ResolutionAttempt,
    RewardScorer,
    default_mva_declaration,
)
from rarepipe.stages.network.sim.splits import catalogue_world_families, default_world_split
from rarepipe.stages.prospective import fixtures as FX
from rarepipe.stages.prospective.model import Actor, ActorType, Role
from rarepipe.stages.prospective.nodes import ResponseState
from rarepipe.stages.prospective.store import PlanStore

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
LEAD = Actor(actor_type=ActorType.HUMAN, identity="lead-scientist", roles=[Role.SCIENTIFIC_LEAD])
OPS = Actor(actor_type=ActorType.HUMAN, identity="research-ops", roles=[Role.RESEARCH_OPERATIONS])
AGENT = Actor(actor_type=ActorType.AGENT, identity="t12-extractor", roles=[Role.RESEARCH_OPERATIONS])

REPO = Path(__file__).resolve().parents[1]
SMALL = EvaluationConfig(
    master_seed=20260930,
    train_episodes_per_family=1,
    development_episodes_per_family=1,
    held_out_episodes_per_family=1,
    max_steps_per_episode=3,
)


def _question(campaign_id: str) -> Question:
    return Question(
        campaign_id=campaign_id,
        scope=CampaignScope.MVA_SCIENTIFIC,
        decision="Is intracellular NAD changed?",
        evidence_criteria=EvidenceCriteria(
            intervention=Intervention.NICOTINIC_ACID,
            compartment=Compartment.INTRACELLULAR,
            endpoint="NAD",
        ),
        required_reviewer=Role.SCIENTIFIC_LEAD,
    )


def _contribution(
    *,
    case_ref: str = "PP_MVA_001_RH_001",
    public_export: bool = False,
    other_case: bool = False,
    policy_training: bool = False,
    permitted: str = "synthetic permitted content",
) -> Contribution:
    campaign_id = new_id()
    q = _question(campaign_id)
    restrictions = Restrictions(
        case_ref=case_ref,
        case_use=True,
        public_export=public_export,
        other_case=other_case,
        policy_training=policy_training,
    )
    finding = ScientificFinding(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(
            question_id=q.id,
            node_identity="fn-northbridge-cell",
            response_state=ResponseState.MEASURED_EFFECT,
        ),
        context=q.evidence_criteria,
        quality="VALID",
        restrictions=restrictions,
    )
    return Contribution(
        origin=Origin.AUTHENTIC_INSTITUTIONAL,
        derived_from=(finding.lineage(),),
        restrictions=restrictions,
        campaign_id=campaign_id,
        scope=q.scope,
        request_id=new_id(),
        responder="private.recipient@example.org",
        source="SRC_T12",
        received_at=NOW,
        event=finding,
        permitted_content=permitted,
        extractor=AGENT,
        evidence_family_id="fam-t12-restricted",
        relations=(
            ClaimRelation(
                claim_id=new_id(),
                question=q,
                direction=ClaimDirection.SUPPORTS,
                rationale="source-grounded",
            ),
        ),
    )


@pytest.fixture(scope="module")
def small_run() -> dict:
    return run_evaluation(SMALL)


def test_a19_learner_and_baselines_share_observation_and_budget_held_out_never_fit(small_run):
    """A19: same observation contract and budget; held-out families were never fit on."""
    a19 = small_run["a19_equivalence"]
    assert a19["same_observation_contract"] is True
    assert a19["same_budget"] is True
    assert (
        a19["learner_observation_digest"]
        == a19["expert_observation_digest"]
        == a19["heuristic_observation_digest"]
        == a19["observation_digest"]
    )
    assert a19["learner_epsilon_held_out"] == 0.0
    assert a19["learner_mode"] == "held_out"
    assert a19["held_out_families_fit"] is False
    fit = set(a19["families_fit"])
    held = set(a19["held_out_families"])
    assert fit.isdisjoint(held)
    split = default_world_split()
    assert held == set(split.held_out_families)
    assert fit <= set(split.train_families) | set(split.development_families)
    for ep in small_run["held_out_episodes"]["learner"]:
        for step in ep["steps"]:
            if step.get("epsilon") is not None:
                assert step["epsilon"] == 0.0


def test_a20_science_digest_byte_identical_across_fresh_processes(tmp_path):
    """A20: two fresh processes, PYTHONHASHSEED left random, science_digest identical."""
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    env1 = {**os.environ, "PYTHONHASHSEED": "1"}
    env2 = {**os.environ, "PYTHONHASHSEED": "2"}
    base = [
        sys.executable,
        "-m",
        "rarepipe.stages.network.evaluate",
        "--seed",
        "20260930",
        "--train-episodes",
        "1",
        "--held-out-episodes",
        "1",
    ]
    r1 = subprocess.run([*base, "--out", str(out1)], env=env1, cwd=str(REPO), capture_output=True, text=True)
    r2 = subprocess.run([*base, "--out", str(out2)], env=env2, cwd=str(REPO), capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    a = json.loads(out1.read_text())
    b = json.loads(out2.read_text())
    assert science_digests_match(a, b)
    assert a["science_digest"]["sha256"] == b["science_digest"]["sha256"]
    named = set(PROVENANCE_FIELDS_THAT_MAY_DIFFER)
    assert "code_revision" in named and "dirty" in named and "results_digest" in named
    assert "covers" in a["science_digest"] and "covers" in a["results_digest"]
    assert len(a["science_digest"]["sha256"]) == 64


def test_a21_report_renders_rates_from_record_not_hand_typed(small_run):
    md = generate_report_markdown(small_run)
    for key in ("learner_held_out", "expert_held_out", "heuristic_held_out"):
        rendered = format_reported_rate(small_run["rates"][key])
        assert rendered in md
        rate = small_run["rates"][key]
        assert f"{rate['numerator']}/{rate['denominator']}" in md
    assert small_run["science_digest"]["sha256"] in md
    assert "clinical benefit" in md.casefold()
    assert "T14" in md
    assert "What is implemented" in md
    assert "What was observed" in md
    assert "What is simulated" in md
    assert "What remains proposed" in md
    assert "What is unresolved" in md


def test_a24_restrictions_survive_export():
    """A24 (1/3): restrictions survive the export path."""
    contrib = _contribution(public_export=False)
    assert not contribution_may_export(contrib)
    payload = build_public_export_payload(contributions=(contrib,))
    exported = payload["contributions"][0]
    assert exported["export_status"] == "omitted_no_public_export_permission"
    assert exported["restrictions_survived"]["public_export"] is False
    assert exported["restrictions_survived"]["case_use"] is True
    assert contrib.restrictions.public_export is False
    assert "recipient" not in exported
    assert "responder" not in exported


def test_a24_restrictions_survive_other_case_routing():
    """A24 (2/3): restrictions survive routing to another case."""
    contrib = _contribution(other_case=False, case_ref="case-A")
    assert not contribution_may_route_other_case(contrib, other_case_ref="case-B")
    assert contrib.may_use(UsePurpose.CASE_USE, case_ref="case-A")
    assert not contrib.may_use(UsePurpose.CASE_USE, case_ref="case-B")
    granted = _contribution(other_case=True, case_ref="case-A")
    assert contribution_may_route_other_case(granted, other_case_ref="case-B")


def test_a24_restrictions_survive_training_selection():
    """A24 (3/3): restrictions survive training selection."""
    blocked = _contribution(policy_training=False)
    assert not contribution_may_select_for_training(blocked)
    assert not blocked.may_use(UsePurpose.POLICY_TRAINING)
    allowed = _contribution(policy_training=True)
    assert contribution_may_select_for_training(allowed)


def test_a28_export_scan_fails_on_private_terms(tmp_path):
    """A28: scan produced export for case-private terms; fail rather than warn."""
    contrib = _contribution(
        public_export=True,
        permitted="Finding mentions SECRET-CASE-TOKEN-ZX91 and variant detail.",
    )
    target = tmp_path / "should_not_exist.json"
    with pytest.raises(ExportRejected) as exc:
        write_public_export(
            target,
            contributions=(contrib,),
            private_terms=["SECRET-CASE-TOKEN-ZX91"],
        )
    assert not target.exists()
    assert exc.value.findings
    assert restricted("recipient")
    assert restricted("exact_variant")
    ok = _contribution(public_export=True, permitted="safe public abstract only")
    payload = build_public_export_payload(contributions=(ok,))
    body = payload["contributions"][0]
    assert "recipient" not in body
    assert "responder" not in body


def test_a29_claim_index_classifications_and_pending_t14(small_run):
    """A29: claims classified; missing artifact => unresolved; T14 stays pending."""
    index = build_submission_claim_index(small_run)
    by_id = {e.claim_id: e for e in index.entries}
    assert by_id["eval-runner-implemented"].classification is ClaimClassification.IMPLEMENTED
    assert by_id["held-out-rates-observed"].classification is ClaimClassification.OBSERVED
    assert by_id["world-families-simulated"].classification is ClaimClassification.SIMULATED
    assert by_id["live-transport-proposed"].classification is ClaimClassification.PROPOSED
    missing = by_id["claim-without-artifact"]
    assert missing.classification is ClaimClassification.UNRESOLVED
    assert missing.artifact and not (REPO / missing.artifact).is_file()
    pilot = by_id["authentic-institutional-pilot"]
    assert pilot.classification is ClaimClassification.UNRESOLVED
    assert pilot.pending_external_milestone == "T14 authentic institutional pilot"
    assert pilot.next_authorized_action
    assert "synthetic" in pilot.next_authorized_action.casefold()


def test_a22_correction_invalidates_report_claims(tmp_path, small_run):
    """A22: correction after report generation marks affected claims invalid."""
    report = build_report(small_run)
    assert report.invalid is False
    assert all(not e.invalid for e in report.claim_index.entries)

    plan = FX.complete_plan()
    store = PlanStore(tmp_path / "ws", plan.plan_id)
    store.commit(plan, expected_parent=None, reason="fixture", kind="initial", actor="test")
    campaign = Campaign(
        id=new_id(),
        purpose="t12-a22",
        scope=CampaignScope.MVA_SCIENTIFIC,
        mode=CampaignMode.SYNTHETIC,
    )
    adapter = NativePlanAdapter(store, campaign=campaign)
    obs = FX.observation("EXP02", FX.exp02())
    proposal = adapter.propose_evidence(obs, actor=OPS, source_id="SRC_T12")
    assert proposal.status is ProposalStatus.PENDING

    q = _question(campaign.id)
    finding = ScientificFinding(
        origin=Origin.SYNTHETIC,
        state=ResponseState.MEASURED_EFFECT,
        envelope=NetworkEnvelope(
            question_id=q.id,
            node_identity="fn-northbridge-cell",
            response_state=ResponseState.MEASURED_EFFECT,
        ),
        context=q.evidence_criteria,
        quality="VALID",
    )
    contrib = Contribution(
        id="SRC_T12",
        origin=Origin.SYNTHETIC,
        derived_from=(finding.lineage(),),
        campaign_id=campaign.id,
        scope=campaign.scope,
        request_id=new_id(),
        responder="sim",
        source="SRC_T12",
        received_at=NOW,
        event=finding,
        permitted_content="synthetic",
        extractor=AGENT,
        evidence_family_id="fam-t12-a22",
    )
    assessment = Assessment(
        id="asm-t12",
        origin=Origin.SYNTHETIC,
        derived_from=(contrib.lineage(),),
        contribution=contrib,
        question=q,
        relations=(),
        reviewer=OPS,
        decision="PROPOSED",
    )
    adapter.register_assessment(assessment)

    family = next(f for f in catalogue_world_families() if f.family_id == "family-favourable")
    world = make_family_world(family, replicate=0)
    scorer = RewardScorer(world, default_mva_declaration())
    scorer.score_attempt(
        ResolutionAttempt(
            question_id="Q01",
            evidence_family_id="fam-t12-a22",
            claimed_direction=ClaimDirection.SUPPORTS,
            contribution_ids=("c1",),
        )
    )
    assert scorer.value_state.total_V == 1.0

    updated, inv = invalidate_report_after_correction(
        report,
        adapter=adapter,
        source_id="SRC_T12",
        reason="Errata: permission revoked after report",
        actor=LEAD,
        scorer=scorer,
        evidence_family_id="fam-t12-a22",
        permission_restricted=True,
        now=NOW,
    )
    assert inv is not None
    assert proposal.id in inv.affected_proposals
    assert assessment.id in inv.affected_assessments
    assert updated.invalid is True
    assert scorer.value_state.total_V == 0.0
    assert any(e.invalid for e in updated.claim_index.entries)
    assert any(e.claim_id == "held-out-rates-observed" and e.invalid for e in updated.claim_index.entries)
    pilot = next(e for e in updated.claim_index.entries if e.claim_id == "authentic-institutional-pilot")
    assert pilot.pending_external_milestone
    assert "Suspend dependent pilot" in (pilot.next_authorized_action or "")


def test_reward_breakdowns_come_from_scorer_not_recomputed(small_run):
    for bucket in small_run["held_out_episodes"].values():
        assert bucket
        for ep in bucket:
            assert ep["steps"]
            for step in ep["steps"]:
                rb = step["reward_breakdown"]
                assert "reward" in rb and "delta_V" in rb
                assert rb.get("convention_label") == "synthetic_benchmark_convention"
                assert rb.get("content_digest")


# ── A28: a private value in an ordinary field ────────────────────────────────


@pytest.mark.parametrize(("label", "run"), [
    ("case identifier", {"caveat": "Simulated only. Derived from the MVA_001 campaign baseline."}),
    ("coding variant", {"caveat": "The BUB1B c.2211-1G>A allele was central to the question."}),
    ("protein variant", {"rates": {"note": "the p.Arg814His substitution in the kinase domain"}}),
    ("frameshift", {"caveat": "c.2441_2442delAG produced a frameshift"}),
    ("coordinate", {"rates": {"note": "cohort context: chr15:40,000,000"}}),
    ("local path", {"caveat": "see /Volumes/Lexar/rarepipe_work for the sealed run"}),
])
def test_a28_a_private_value_in_an_ordinary_field_is_refused(label: str, run: dict):
    """A28: dropping restricted field NAMES does not protect a value written in ordinary prose.

    `caveat` and `rates` are not restricted field names, so a case identifier, an exact variant
    and a genomic coordinate all exported cleanly. The caller can pass `private_terms`, but an
    export that is only safe when the caller remembers is not safe.
    """
    with pytest.raises(ExportRejected):
        build_public_export_payload(run=run)


def test_a28_the_rejection_names_which_rule_fired():
    """An operator has to know what to redact, so the hit names the rule and the path."""
    with pytest.raises(ExportRejected) as excinfo:
        build_public_export_payload(run={"caveat": "BUB1B c.2211-1G>A"})
    message = str(excinfo.value)
    assert "run_summary.caveat" in message
    assert "exact variant notation" in message


def test_a28_an_ordinary_simulated_summary_still_exports():
    """The scan must not refuse the report it exists to publish."""
    payload = build_public_export_payload(run={
        "caveat": "Simulated only; a simulated improvement is not a clinical benefit.",
        "rates": {"held_out_mean_reward": {"numerator": 3, "denominator": 8}},
    })
    assert payload["run_summary"]["caveat"].startswith("Simulated only")


def test_a28_patterns_match_notation_not_a_word_list():
    """Structural patterns generalise to variants nobody listed, which a word list cannot."""
    for unlisted in ("c.1234G>T", "p.Gly12Asp", "chr7:55,249,071", "NEWCASE_042"):
        with pytest.raises(ExportRejected):
            build_public_export_payload(run={"caveat": f"context: {unlisted}"})
