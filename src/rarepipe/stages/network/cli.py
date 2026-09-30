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


# --- T13: operator verification, environment check, and acceptance map (append only) ---

verify_app = typer.Typer(
    no_args_is_help=True,
    help="Verify network implementation, environment, and acceptance criteria.",
)
app.add_typer(verify_app, name="verify")

PRD_ACCEPTANCE_DESCRIPTIONS: dict[str, str] = {
    "A01": "Each seeded node has a source, node type and explicit unknown availability/permission fields.",
    "A02": "A public profile match cannot become a confirmed resource or collaboration without a new evidence event.",
    "A03": "Exact intervention mismatches survive ingestion; NMN findings cannot become nicotinic-acid observations.",
    "A04": "Blood-only NAD evidence cannot close the relevant-cell or functional question.",
    "A05": "Unknown endpoints and missing interpretive fields stay unknown.",
    "A06": "Two replies about one original study do not become independent replication or duplicate reward.",
    "A07": "Refusal, no response, no resource, QC failure and informative negative remain distinct.",
    "A08": "Native B16 behavior is preserved on the current reduced-division/unknown-benefit fixture; native death and other review routes regress unchanged.",
    "A09": "Conflicting scientific findings create context comparison/review, not a majority-vote conclusion.",
    "A10": "Frozen native plans cannot be mutated; stale edits fail with a conflict.",
    "A11": "No persona/agent can sign a required human review or release a scientific freeze.",
    "A12": "Every live waiting task has an owner and next trigger or a visible unscheduled reason.",
    "A13": "Send/reply retries deduplicate correctly; an ambiguous send enters reconciliation before another transmission.",
    "A14": "Revocation, opt-out, exclusion or unset required authorization blocks dispatch, including pending retries.",
    "A15": "Synthetic contributions and synthetic learning feedback cannot cross into real campaign stores.",
    "A16": "Hidden world truth is absent from policy inputs, prompts and UI payloads supplied during decisions.",
    "A17": "The learner updates persisted parameters from the declared reward; static routing alone fails this test.",
    "A18": "Eligible-action constraints apply to exploration as well as exploitation.",
    "A19": "Fixed and heuristic baselines receive equivalent observations and budgets; held-out splits are checked for leakage.",
    "A20": "Repeated fresh-process runs reproduce scoped semantic results with generated digests and honest provenance differences.",
    "A21": "Metrics and narrative are generated from records; each reported rate has its actual count/denominator.",
    "A22": "A later correction or permission change invalidates affected derivatives and pending dependent actions.",
    "A23": "A malicious instruction in an external reply cannot change permissions, execute code or export records.",
    "A24": "A contribution's restrictions survive exports, other-case routing, and training selection.",
    "A25": "An authentic institutional reply is imported with provenance and produces an assessed next action; synthetic inputs cannot pass this milestone.",
    "A26": "A partnership reply cannot satisfy an MVA scientific question or imply dataset access.",
    "A27": "A coherent positive scientific branch ends at confirmation/review tasks, with no patient action.",
    "A28": "Public exports omit private identifiers, case-local paths, recipient details and restricted text unless expressly permitted.",
    "A29": "The submission index distinguishes implemented, observed, simulated, proposed and unresolved claims.",
    "A30": "The user can pause/cancel a campaign and obtain a permitted handoff without losing its recorded history.",
}


def collect_acceptance_map(repo_root: Path | None = None) -> dict[str, dict]:
    """Index acceptance IDs to the tests that name them, by AST inspection of the suite.

    This measures naming, not behaviour: a test is indexed when its function name or docstring
    mentions the acceptance ID. That makes every row runnable by a reviewer, which is the point —
    but a test that names A08 and asserts nothing would be indexed just the same. The status is
    therefore NAMED_BY_TEST, never "covered", and nothing here is evidence that an acceptance
    criterion is actually exercised. Only reading the cited tests establishes that.
    """
    import ast
    import re

    root = repo_root or Path(__file__).resolve().parents[4]
    tests_dir = root / "tests"
    aid_pattern = re.compile(r"(?i)(?:^|_|\b)a(0[1-9]|1[0-9]|2[0-9]|30)(?:_|\b)")

    raw_matches: dict[str, set[str]] = {}
    if tests_dir.exists():
        for test_file in sorted(tests_dir.glob("test_*.py")):
            try:
                tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=str(test_file))
            except Exception:
                continue
            rel_path = f"tests/{test_file.name}"
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    docstring = ast.get_docstring(node) or ""
                    matched = set()
                    for m in aid_pattern.finditer(node.name):
                        matched.add("A" + m.group(1).upper())
                    for m in aid_pattern.finditer(docstring):
                        matched.add("A" + m.group(1).upper())
                    for aid in matched:
                        raw_matches.setdefault(aid, set()).add(f"{rel_path}::{node.name}")

    result: dict[str, dict] = {}
    for i in range(1, 31):
        aid = f"A{i:02d}"
        desc = PRD_ACCEPTANCE_DESCRIPTIONS.get(aid, "")
        if aid == "A25":
            result[aid] = {
                "id": aid,
                "description": desc,
                "status": "EXTERNAL_MILESTONE",
                "test_nodes": [],
            }
        elif aid in raw_matches and raw_matches[aid]:
            result[aid] = {
                "id": aid,
                "description": desc,
                "status": "NAMED_BY_TEST",
                "test_nodes": sorted(raw_matches[aid]),
            }
        else:
            result[aid] = {
                "id": aid,
                "description": desc,
                "status": "NOT_NAMED_BY_ANY_TEST",
                "test_nodes": [],
            }
    return result


def render_acceptance_table_markdown(map_data: dict[str, dict]) -> str:
    """Render the acceptance map as a markdown table."""
    lines = [
        "This table is an **index built from test names and docstrings**, so a reviewer can run "
        "any row with `uv run pytest -q <node_id>`. `NAMED_BY_TEST` means a test names the ID; it "
        "is not evidence that the criterion is exercised, and only reading the cited tests "
        "establishes that. `NOT_NAMED_BY_ANY_TEST` is a definite gap.",
        "",
        "| ID | Status | PRD Requirement | Test Node ID(s) naming this ID |",
        "|---|---|---|---|",
    ]
    for aid, row in sorted(map_data.items()):
        status = row["status"]
        desc = row["description"]
        if status == "EXTERNAL_MILESTONE":
            node_str = "*None (external milestone: cannot be satisfied by synthetic fixtures)*"
        elif status == "NAMED_BY_TEST":
            node_str = "<br>".join(f"`{t}`" for t in row["test_nodes"])
        else:
            node_str = "*None — no test names this ID*"
        lines.append(f"| {aid} | **{status}** | {desc} | {node_str} |")
    return "\n".join(lines)


@verify_app.command("acceptance-map")
def verify_acceptance_map(
    as_json: JsonOpt = False,
    uncovered_only: Annotated[bool, typer.Option("--uncovered-only", help="Report only IDs that no test names.")] = False,
) -> None:
    """Generate the acceptance map from the test suite (PRD §18, T13)."""
    mapping = collect_acceptance_map()
    if uncovered_only:
        mapping = {k: v for k, v in mapping.items()
                   if v["status"] == "NOT_NAMED_BY_ANY_TEST"}

    if as_json:
        typer.echo(json.dumps(mapping, indent=2))
    else:
        typer.echo(render_acceptance_table_markdown(mapping))


@verify_app.command("runbook-revision")
def verify_runbook_revision(as_json: JsonOpt = False) -> None:
    """Report whether RUNBOOK.md's recorded verification still describes the current code.

    A runbook records the revision its verification actually ran at. That revision does not become
    wrong when work continues — it becomes *stale*, which a reader must be able to see. This
    reports it; it does not fail, because a historical record is not a defect.
    """
    import re
    import subprocess

    root = Path(__file__).resolve().parents[4]
    runbook = root / "docs/network/RUNBOOK.md"
    text = runbook.read_text(encoding="utf-8") if runbook.exists() else ""
    recorded = sorted(set(re.findall(r"\b[0-9a-f]{40}\b", text)))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                          capture_output=True, text=True).stdout.strip()
    commits_since = 0
    if recorded and head:
        newest = max(
            recorded,
            key=lambda sha: int(subprocess.run(
                ["git", "rev-list", "--count", f"{sha}..HEAD"], cwd=str(root),
                capture_output=True, text=True).stdout.strip() or 0) * -1,
        )
        commits_since = int(subprocess.run(
            ["git", "rev-list", "--count", f"{newest}..HEAD"], cwd=str(root),
            capture_output=True, text=True).stdout.strip() or 0)
    status = "CURRENT" if commits_since == 0 and recorded else "STALE"
    payload = {
        "runbook": "docs/network/RUNBOOK.md",
        "recorded_revisions": recorded,
        "head": head,
        "commits_since": commits_since,
        "status": status,
        "means": ("the recorded verification describes the current code"
                  if status == "CURRENT" else
                  f"the recorded verification ran {commits_since} commit(s) ago; re-run it before "
                  "citing its results as current"),
    }
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"{status}: {payload['means']}")
        typer.echo(f"  recorded: {', '.join(recorded) or 'none'}")
        typer.echo(f"  HEAD    : {head}")


@verify_app.command("environment")
def verify_environment(
    as_json: JsonOpt = False,
) -> None:
    """Check the pinned baseline plan, controlled drive mount, git state, and runtime."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[4]
    controlled_drive = Path("/Volumes/Lexar/rarepipe_work/MVA_001/prospective")
    controlled_mounted = controlled_drive.is_dir()
    baseline_plan = "PP_MVA_001_RH_001@0002-455419f1"
    rules_version = "stage10-rules-1.1.0"
    scientific_readiness_gaps = 112

    git_head = "unknown"
    git_dirty = False
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            git_head = proc.stdout.strip()
        diff_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        git_dirty = bool(diff_proc.stdout.strip())
    except Exception:
        pass

    plan_head_matches = None
    if controlled_mounted:
        head_file = controlled_drive / "PP_MVA_001_RH_001" / "HEAD"
        if head_file.exists():
            plan_head_matches = head_file.read_text().strip() == baseline_plan

    env_report = {
        "python_version": sys.version.split()[0],
        "git_head": git_head,
        "git_dirty": git_dirty,
        "controlled_drive_path": str(controlled_drive),
        "controlled_drive_mounted": controlled_mounted,
        "baseline_plan_id": baseline_plan,
        "baseline_plan_head_matches": plan_head_matches,
        "rules_version": rules_version,
        "scientific_readiness_gaps": scientific_readiness_gaps,
    }

    if as_json:
        typer.echo(json.dumps(env_report, indent=2))
    else:
        typer.echo("Network Runtime & Baseline Verification Environment:")
        for k, v in env_report.items():
            typer.echo(f"  {k:28}: {v}")


@verify_app.command("suite")
def verify_suite(
    collect_only: Annotated[bool, typer.Option("--collect-only", help="Collect tests without running them.")] = False,
) -> None:
    """Run non-integration pytest suite and report real exit status without piping."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[4]
    cmd = [sys.executable, "-m", "pytest", "-q", "-m", "not integration"]
    if collect_only:
        cmd.append("--collect-only")

    typer.echo(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, check=False)
    typer.echo(proc.stdout)
    if proc.stderr:
        typer.echo(proc.stderr, err=True)
    typer.echo(f"Real process exit status: {proc.returncode}")
    raise typer.Exit(proc.returncode)


if __name__ == "__main__":
    app()

