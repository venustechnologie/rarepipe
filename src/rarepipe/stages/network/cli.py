"""`rarepipe network ...` — research-network operator commands.

Append command groups only; do not rewrite another task's group.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from rarepipe.stages.network.model import Campaign
from rarepipe.stages.network.outbox import Outbox
from rarepipe.stages.network.registry import load_seed
from rarepipe.stages.network.sim.scenarios import SCENARIO_BUILDERS
from rarepipe.stages.network import views as V

app = typer.Typer(
    no_args_is_help=True,
    help="Research-network operator tools. Views project stored records; they do not decide or send.",
)

views_app = typer.Typer(no_args_is_help=True, help="Operator views over stored campaign records (PRD §15).")
app.add_typer(views_app, name="views")

WorkspaceOpt = Annotated[Path, typer.Option(help="Campaign workspace directory.")]
CampaignOpt = Annotated[str, typer.Option(help="Campaign id.")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Emit the typed payload as JSON.")]


def _outbox(workspace: Path, campaign_id: str) -> Outbox:
    """Open an existing campaign journal; never create one from a view command."""
    from rarepipe.stages.network.eventlog import EventLog, opaque

    root = Path(workspace) / opaque(campaign_id)
    log = EventLog(root)
    try:
        events = log.events()
    except Exception as exc:  # noqa: BLE001 — surface journal problems to the operator
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    campaign_events = [event for event in events if event.kind == "campaign"]
    if not campaign_events:
        typer.echo(f"error: no campaign journal for {campaign_id!r}", err=True)
        raise typer.Exit(2)
    stored = Campaign.model_validate(log.snapshot(campaign_events[-1]))
    return Outbox(workspace, stored)


def _emit(payload, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload.model_dump(mode="json"), indent=2))
    else:
        typer.echo(V.render_view_text(payload))


@views_app.command("case")
def views_case(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    as_json: JsonOpt = False,
) -> None:
    """Current question, premises, latest change, next task, owner and trigger."""
    _emit(V.case_view(_outbox(workspace, campaign_id)), as_json)


@views_app.command("network")
def views_network(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    question_id: Annotated[Optional[str], typer.Option(help="Limit to one question id.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Explained candidates; public evidence held apart from confirmed availability."""
    box = _outbox(workspace, campaign_id)
    _emit(V.network_view(box.campaign(), registry=load_seed(), question_id=question_id), as_json)


@views_app.command("requests")
def views_requests(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    as_json: JsonOpt = False,
) -> None:
    """Draft/sent content, authorization, task state, follow-up, stop/pause controls."""
    _emit(V.requests_view(_outbox(workspace, campaign_id)), as_json)


@views_app.command("contribution")
def views_contribution(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    contribution_id: Annotated[str, typer.Option(help="Contribution id on the campaign.")],
    as_json: JsonOpt = False,
) -> None:
    """Permitted content, proposal, missing fields, applicability, evidence family, reviewer action."""
    box = _outbox(workspace, campaign_id)
    campaign = box.campaign()
    contribution = next((c for c in campaign.contributions if c.id == contribution_id), None)
    if contribution is None:
        typer.echo(f"error: contribution {contribution_id!r} not recorded on campaign", err=True)
        raise typer.Exit(2)
    _emit(V.contribution_review_view(campaign, contribution=contribution), as_json)


@views_app.command("scenarios")
def views_scenarios(
    scenario_id: Annotated[str, typer.Option(help="Catalogue scenario id, e.g. S01.")],
    master_seed: Annotated[int, typer.Option(help="Deterministic catalogue seed.")] = 20260930,
    as_json: JsonOpt = False,
) -> None:
    """Selected world assumptions, action trace and decisions — always synthetic-labelled."""
    builders = dict(SCENARIO_BUILDERS)
    if scenario_id not in builders:
        typer.echo(f"error: unknown scenario {scenario_id!r}", err=True)
        raise typer.Exit(2)
    _emit(V.scenarios_view(builders[scenario_id](master_seed)), as_json)


@views_app.command("learning")
def views_learning(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    as_json: JsonOpt = False,
) -> None:
    """Baseline comparisons, reward components, policy version, updates and limitations."""
    box = _outbox(workspace, campaign_id)
    _emit(V.learning_view(box.campaign()), as_json)


@views_app.command("audit")
def views_audit(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    as_json: JsonOpt = False,
) -> None:
    """Provenance, supersessions, scoped sharing and plain-language account of actual work."""
    box = _outbox(workspace, campaign_id)
    handoff = None
    if box.campaign().status in {"PAUSED", "CANCELLED"}:
        handoff = box.handoff()
    _emit(V.audit_export_view(box, contributions=box.campaign().contributions, handoff=handoff), as_json)


@views_app.command("family")
def views_family(
    workspace: WorkspaceOpt,
    campaign_id: CampaignOpt,
    as_json: JsonOpt = False,
) -> None:
    """What changed, what it means, what remains unresolved, who owns the next step."""
    _emit(V.family_summary_view(_outbox(workspace, campaign_id)), as_json)


# --- T12: evaluation runner, reports, exports, claim index (append only) ---

evaluate_app = typer.Typer(
    no_args_is_help=True,
    help="Run network evaluation, generate reports/exports and the submission claim index.",
)
app.add_typer(evaluate_app, name="evaluate")


@evaluate_app.command("run")
def evaluate_run(
    out: Annotated[Path, typer.Option(help="Write the run record JSON here.")],
    seed: Annotated[int, typer.Option(help="Master seed.")] = 20260930,
    train_episodes: Annotated[int, typer.Option(help="Train episodes per family.")] = 2,
    held_out_episodes: Annotated[int, typer.Option(help="Held-out episodes per family.")] = 1,
) -> None:
    """Train/tune/evaluate learner + baselines; write digests and provenance."""
    from rarepipe.stages.network.evaluate import EvaluationConfig, run_evaluation, write_run_record

    cfg = EvaluationConfig(
        master_seed=seed,
        train_episodes_per_family=train_episodes,
        development_episodes_per_family=1 if train_episodes > 0 else 0,
        held_out_episodes_per_family=held_out_episodes,
    )
    path = write_run_record(out, run_evaluation(cfg))
    typer.echo(f"wrote {path}")


@evaluate_app.command("report")
def evaluate_report(
    results: Annotated[Path, typer.Argument(help="Evaluation run record JSON.")],
    out: Annotated[Optional[Path], typer.Option(help="Write markdown report here.")] = None,
) -> None:
    """Generate the evaluation narrative from a stored run record (A21)."""
    from rarepipe.stages.network.report import build_report, render_claim_index_markdown

    run = json.loads(Path(results).read_text())
    report = build_report(run)
    text = report.markdown + "\n" + render_claim_index_markdown(report.claim_index)
    if out is not None:
        out.write_text(text)
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text)


@evaluate_app.command("export")
def evaluate_export(
    out: Annotated[Path, typer.Option(help="Public export JSON path.")],
    results: Annotated[Optional[Path], typer.Option(help="Optional run record to summarise.")] = None,
    private_terms: Annotated[
        Optional[Path], typer.Option(help="Newline-separated case-private terms; a hit fails the export."),
    ] = None,
) -> None:
    """Public export with restriction drop + private-term scan (A24, A28)."""
    from rarepipe.stages.network.report import ExportRejected, write_public_export

    run = json.loads(results.read_text()) if results is not None else None
    terms = [
        line.strip() for line in private_terms.read_text().splitlines() if line.strip()
    ] if private_terms is not None else []
    try:
        path = write_public_export(out, run=run, contributions=(), private_terms=terms)
    except ExportRejected as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"wrote {path}")
