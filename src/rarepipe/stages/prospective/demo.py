"""The completion demonstration (PRD §19.1), offline and end to end.

1. import the current candidate and seed the real MVA plan;
2. explain why the real plan cannot yet freeze;
3. preview the scenario library against it (hypothetical, no mutation);
4. freeze a separately labelled, complete synthetic fixture;
5. ingest a synthetic outcome into that fixture;
6. record a human reviewer decision and the successor version;
7. export a sanitized artifact;
8. replay the interpretation and get the same result.

The real MVA plan is never frozen, never given an observation and never marked validated.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from rarepipe.stages.prospective import fixtures as FX
from rarepipe.stages.prospective import workflow as W
from rarepipe.stages.prospective.baseline import import_baseline
from rarepipe.stages.prospective.export import export
from rarepipe.stages.prospective.model import Actor, ActorType, OutcomeAvailability, ReviewDecision, Role
from rarepipe.stages.prospective.seed import PLAN_ID, seed_plan
from rarepipe.stages.prospective.store import PlanStore
from rarepipe.stages.prospective.views import write_views

DEMO_REVIEWERS = [(Actor(actor_type=ActorType.HUMAN, identity=f"demo {r.value} (synthetic fixture review)",
                         roles=[r]), r) for r in (Role.SCIENTIFIC_LEAD, Role.ASSAY_SCIENTIST, Role.STATISTICIAN)]
OPS = Actor(actor_type=ActorType.HUMAN, identity="demo research operations", roles=[Role.RESEARCH_OPERATIONS])


def run(baseline_package: Path, workspace: Path, say=print) -> dict:
    out: dict = {}
    # 1-2. the real plan
    ref, _ = import_baseline(baseline_package, status="CANDIDATE")
    real = PlanStore(workspace, PLAN_ID)
    plan = real.commit(seed_plan(ref), expected_parent=real.head(), reason="demo: initial draft", kind="initial",
                       actor="demo", idempotency_key=f"init:{ref.package_sha256}")
    say(f"[1] imported the candidate: {ref.manifest_entries} manifest entries verified; status {ref.status}")
    report = W.validate(plan)
    owners = Counter(u.owner.value for u in report.scientific_readiness)
    say(f"[2] the real plan cannot freeze: {len(report.scientific_readiness)} named gap(s) "
        f"({', '.join(f'{k} {v}' for k, v in owners.most_common())}); provenance: {'; '.join(report.provenance)}")
    out["real_plan_gaps"] = len(report.scientific_readiness)
    # 3. previews
    previews = [W.preview(plan, s) for s in FX.SCENARIOS.values()]
    for name, p in zip(FX.SCENARIOS, previews, strict=True):
        say(f"[3] preview {name:32} → {', '.join(p.matches)}{' (DECISION_REVIEW_REQUIRED)' if p.conflicting_actions else ''}")
    assert real.load().version_id == plan.version_id, "a preview must not change the plan"
    # 4. synthetic fixture: complete, reviewed, frozen
    fx = PlanStore(workspace, "PP_SYNTHETIC_DEMO")
    fixture = FX.complete_plan()
    fx.commit(fixture, expected_parent=fx.head(), reason="synthetic fixture", kind="initial", actor="demo",
              idempotency_key="fixture:v1")
    if fx.load().lifecycle.value != "FROZEN":
        for actor, role in DEMO_REVIEWERS:
            W.record_plan_review(fx, actor, role, ReviewDecision.APPROVE_FOR_FREEZE, "synthetic fixture is complete")
        frozen = W.freeze(fx, DEMO_REVIEWERS[0][0], OutcomeAvailability(planned_start="2026-10-01"))
    else:
        frozen = fx.load()
    say(f"[4] froze the synthetic fixture {frozen.version_id} (temporal status {frozen.temporal_status.value}); "
        "this preregisters nothing")
    # 5-6. ingest a synthetic outcome and review it
    result = W.ingest(fx, FX.observation("EXP02", FX.SCENARIOS["exp02_unexpected_mechanism"]["values"]), OPS)
    d = result.decision
    say(f"[5] ingested {result.observation.observation_id}: {', '.join(d.matches)} → {', '.join(d.proposed_actions)}")
    if d.review_version == 0:
        record, successor = W.review_decision(fx, d.decision_id, DEMO_REVIEWERS[0][0], Role.SCIENTIFIC_LEAD,
                                              ReviewDecision.ACCEPT_INTERPRETATION,
                                              "signal preserved; mechanism outside the chain to be investigated", 0)
        say(f"[6] reviewer accepted {record.decision_id}; successor {successor.version_id} (parent "
            f"{successor.parent_version})")
    # 7. export
    exported = export(fx, workspace / "exports", "public")
    say(f"[7] sanitized export sealed at {exported.name}")
    # 8. replay
    ok, diffs = W.replay(fx, d.decision_id)
    say(f"[8] replay of {d.decision_id}: {'REPRODUCED' if ok else 'DIFFERS ' + ', '.join(diffs)}")
    write_views(real, workspace / "views" / "real_plan", previews)
    write_views(fx, workspace / "views" / "synthetic_fixture")
    say(f"views written under {workspace / 'views'}")
    assert real.load().lifecycle.value == "DRAFT" and not real.observations(), "the real plan stays unvalidated"
    say("the real MVA plan remains DRAFT, with no observation and no validation claim")
    out.update(replayed=ok, fixture_version=frozen.version_id, decision=d.decision_id)
    return out
