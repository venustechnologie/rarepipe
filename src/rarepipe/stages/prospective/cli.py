"""`rarepipe prospective ...` (PRD §17). Thin: every command calls the domain layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from rarepipe.stages.prospective import seed as seed_mod
from rarepipe.stages.prospective import workflow as W
from rarepipe.stages.prospective.baseline import BaselineError, import_baseline
from rarepipe.stages.prospective.model import Actor, ActorType, OutcomeAvailability, ReviewDecision, Role
from rarepipe.stages.prospective.policy import PolicyError
from rarepipe.stages.prospective.store import PlanStore, VersionConflict

app = typer.Typer(no_args_is_help=True, help="Stage 10 — prospective experiment and decision plans. Sends nothing.")
EXIT_USAGE, EXIT_BLOCKED, EXIT_CONFLICT = 2, 3, 4

WorkspaceOpt = Annotated[Path, typer.Option(help="Directory holding plan stores.")]
PlanOpt = Annotated[str, typer.Option(help="Plan id.")]
ActorOpt = Annotated[str, typer.Option(help="Who is acting (recorded in the audit log).")]
RoleOpt = Annotated[Role, typer.Option(help="The capacity in which the actor acts.")]
ActorTypeOpt = Annotated[ActorType, typer.Option(help="HUMAN, AGENT or SYSTEM. Agents cannot review or freeze.")]


def _actor(name: str, role: Role, actor_type: ActorType) -> Actor:
    return Actor(actor_type=actor_type, identity=name, roles=[role])


def _fail(exc: Exception, code: int = EXIT_BLOCKED) -> None:
    typer.echo(f"error: {exc}", err=True)
    for extra in getattr(exc, "problems", []) or getattr(exc, "diff", []):
        typer.echo(f"  - {extra}", err=True)
    raise typer.Exit(code)


@app.command("init")
def init(baseline: Annotated[Path, typer.Option(help="Verified Stage 09 package (zip or folder).")],
         workspace: WorkspaceOpt, actor: ActorOpt = "engineer", role: RoleOpt = Role.ENGINEER,
         actor_type: ActorTypeOpt = ActorType.HUMAN,
         status: Annotated[str, typer.Option(help="CANDIDATE or FROZEN, as the release says.")] = "CANDIDATE") -> None:
    """Verify and pin the baseline; create the MVA seed plan as a DRAFT."""
    try:
        ref, _ = import_baseline(baseline, status=status)
    except BaselineError as exc:
        _fail(exc)
    store = PlanStore(workspace, seed_mod.PLAN_ID)
    try:
        plan = store.commit(seed_mod.seed_plan(ref), expected_parent=store.head(), reason="initial draft from "
                            f"baseline {ref.stage_runs.get('stage09')}", kind="initial", actor=actor,
                            idempotency_key=f"init:{ref.package_sha256}")
    except VersionConflict as exc:
        _fail(exc, EXIT_CONFLICT)
    typer.echo(f"{plan.version_id}  {plan.lifecycle.value}  baseline {ref.status}, {ref.manifest_entries} manifest "
               "entries verified")
    for lim in ref.known_limitations:
        typer.echo(f"  limitation: {lim}")


@app.command("validate")
def validate(workspace: WorkspaceOpt, plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Structural, scientific-readiness, provenance and policy errors, reported separately."""
    report = W.validate(PlanStore(workspace, plan_id).load())
    typer.echo(report.render())


@app.command("preview")
def preview(scenario: Annotated[Path, typer.Option(help="Hypothetical scenario JSON.")], workspace: WorkspaceOpt,
            plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Evaluate hypothetical inputs. Writes nothing to the plan, sends nothing."""
    record = W.preview(PlanStore(workspace, plan_id).load(), json.loads(scenario.read_text()))
    typer.echo(json.dumps(record.model_dump(mode="json"), indent=2))


@app.command("review-plan")
def review_plan(workspace: WorkspaceOpt, decision: Annotated[ReviewDecision, typer.Option()],
                rationale: Annotated[str, typer.Option()], actor: ActorOpt, role: RoleOpt,
                actor_type: ActorTypeOpt = ActorType.HUMAN, plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Record a human review of the plan's current content."""
    try:
        plan = W.record_plan_review(PlanStore(workspace, plan_id), _actor(actor, role, actor_type), role, decision,
                                    rationale)
    except (PolicyError, W.WorkflowError) as exc:
        _fail(exc)
    typer.echo(plan.version_id)


@app.command("freeze")
def freeze(workspace: WorkspaceOpt, actor: ActorOpt, role: RoleOpt = Role.SCIENTIFIC_LEAD,
           actor_type: ActorTypeOpt = ActorType.HUMAN,
           availability: Annotated[Path | None, typer.Option(help="Outcome-availability declaration JSON.")] = None,
           plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Enforce the real-plan gates and produce an immutable version."""
    decl = OutcomeAvailability(**json.loads(availability.read_text())) if availability else None
    try:
        plan = W.freeze(PlanStore(workspace, plan_id), _actor(actor, role, actor_type), decl)
    except (PolicyError, W.WorkflowError) as exc:
        _fail(exc)
    typer.echo(f"{plan.version_id} FROZEN · temporal status {plan.temporal_status.value}")


@app.command("ingest")
def ingest(observation: Annotated[Path, typer.Option(help="Observation JSON.")], workspace: WorkspaceOpt,
           actor: ActorOpt = "research_operations", role: RoleOpt = Role.RESEARCH_OPERATIONS,
           actor_type: ActorTypeOpt = ActorType.HUMAN,
           raw: Annotated[Path | None, typer.Option(help="Original result file, re-hashed on ingest.")] = None,
           plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Store the immutable result, validate it, and produce a review proposal."""
    try:
        result = W.ingest(PlanStore(workspace, plan_id), json.loads(observation.read_text()),
                          _actor(actor, role, actor_type), raw)
    except (PolicyError, W.WorkflowError) as exc:
        _fail(exc)
    d = result.decision
    typer.echo(f"{result.observation.observation_id}{' (already ingested: same identity, no new replication)' if result.duplicate else ''}")
    typer.echo(f"{d.decision_id} {d.status}: {', '.join(d.matches)}")


@app.command("review")
def review(decision_id: Annotated[str, typer.Option("--decision")], outcome: Annotated[ReviewDecision, typer.Option()],
           rationale: Annotated[str, typer.Option()], expected_review_version: Annotated[int, typer.Option()],
           workspace: WorkspaceOpt, actor: ActorOpt, role: RoleOpt = Role.SCIENTIFIC_LEAD,
           actor_type: ActorTypeOpt = ActorType.HUMAN,
           select: Annotated[list[str] | None, typer.Option(help="Selected actions (default: non-conflicting).")] = None,
           plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Record an authorized human interpretation and its task proposals."""
    try:
        record, successor = W.review_decision(PlanStore(workspace, plan_id), decision_id,
                                              _actor(actor, role, actor_type), role, outcome, rationale,
                                              expected_review_version, select)
    except VersionConflict as exc:
        _fail(exc, EXIT_CONFLICT)
    except (PolicyError, W.WorkflowError) as exc:
        _fail(exc)
    typer.echo(f"{record.decision_id} {record.status}" + (f" → successor {successor.version_id}" if successor else ""))


@app.command("diff")
def diff(old: str, new: str, workspace: WorkspaceOpt, plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Explain scientific, editorial and operational changes between two versions."""
    from rarepipe.stages.prospective.diff import diff_plans

    store = PlanStore(workspace, plan_id)
    for change in diff_plans(store.load(old), store.load(new)):
        typer.echo(change.render())


@app.command("replay")
def replay(decision_id: Annotated[str, typer.Option("--decision")], workspace: WorkspaceOpt,
           plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Re-evaluate the pinned inputs; exit non-zero if the evaluation does not reproduce."""
    ok, diffs = W.replay(PlanStore(workspace, plan_id), decision_id)
    typer.echo("REPRODUCED" if ok else f"DIFFERS: {', '.join(diffs)}")
    if not ok:
        raise typer.Exit(EXIT_BLOCKED)


@app.command("export")
def export(workspace: WorkspaceOpt, output: Annotated[Path, typer.Option()],
           visibility: Annotated[str, typer.Option(help="public or private")] = "public",
           private_terms: Annotated[Path | None, typer.Option(help="Local file of terms that must never leave; "
                                                                   "read only here.")] = None,
           mode: Annotated[str, typer.Option(help="remove or reject")] = "remove",
           plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Apply the output policy and write a sealed export with a manifest."""
    from rarepipe.stages.prospective.export import ExportRejected
    from rarepipe.stages.prospective.export import export as do_export

    terms = [t.strip() for t in private_terms.read_text().splitlines() if t.strip()] if private_terms else []
    try:
        path = do_export(PlanStore(workspace, plan_id), output, visibility, terms, mode)
    except ExportRejected as exc:
        _fail(exc)
    typer.echo(str(path))


@app.command("views")
def views(workspace: WorkspaceOpt, output: Annotated[Path, typer.Option()],
          scenario: Annotated[list[Path] | None, typer.Option(help="Scenario JSON(s) to render as previews.")] = None,
          plan_id: PlanOpt = seed_mod.PLAN_ID) -> None:
    """Write the doctor, editor, result-review, scenario and audit views (static HTML)."""
    from rarepipe.stages.prospective.views import write_views

    store = PlanStore(workspace, plan_id)
    previews = [W.preview(store.load(), json.loads(p.read_text())) for p in scenario or []]
    for path in write_views(store, output, previews):
        typer.echo(str(path))


@app.command("demo")
def demo(baseline: Annotated[Path, typer.Option(help="The current candidate package.")], workspace: WorkspaceOpt) -> None:
    """The §19.1 completion demonstration, offline. The real MVA plan is never frozen or validated."""
    from rarepipe.stages.prospective.demo import run

    result = run(baseline, workspace, say=typer.echo)
    if not result.get("replayed"):
        raise typer.Exit(EXIT_BLOCKED)
