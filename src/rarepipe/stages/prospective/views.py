"""Offline HTML views generated from the same records the CLI and exports use (PRD §16).

Every view answers: what do we expect, under which assumptions, what observation would change our
view, and what happens next? Views are static files; they read records and never mutate them.
"""

from __future__ import annotations

import html
from pathlib import Path

from rarepipe.stages.prospective.diff import diff_plans
from rarepipe.stages.prospective.model import DecisionRecord, ProspectivePlan
from rarepipe.stages.prospective.store import PlanStore
from rarepipe.stages.prospective.workflow import validate

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#5d5a52;--line:#dedad0;--accent:#2f5d8a;--warn:#9a3b1c;--ok:#2e6b3f;
--chip:#efece4}
@media (prefers-color-scheme: dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a8a598;--line:#34322c;
--accent:#8db4dc;--warn:#e39a7a;--ok:#8fcf9e;--chip:#26241f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,
sans-serif}main{max-width:1040px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.5rem;margin:.2rem 0 1rem}
h2{font-size:1.1rem;margin:2rem 0 .5rem;border-bottom:1px solid var(--line);padding-bottom:.25rem}
.muted{color:var(--muted)}.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:0 .6rem;
font-size:.8rem;margin-right:.3rem}.warn{color:var(--warn)}.ok{color:var(--ok)}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{border-bottom:1px solid var(--line);
padding:.4rem .5rem;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
.banner{background:var(--warn);color:#fff;padding:.6rem 1rem;font-weight:700;letter-spacing:.02em;
position:sticky;top:0}@media print{.banner{position:static}}.card{border:1px solid var(--line);border-radius:8px;
padding:1rem;margin:.75rem 0}.wrap{overflow-x:auto}details summary{cursor:pointer;color:var(--accent)}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _page(title: str, body: str, banner: str | None = None) -> str:
    top = f'<div class="banner" role="alert">{_e(banner)}</div>' if banner else ""
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{_e(title)}</title><style>{CSS}</style></head>"
            f"<body>{top}<main>{body}</main></body></html>")


def _table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<div class='wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def doctor_view(plan: ProspectivePlan, previous: ProspectivePlan | None, decisions: list[DecisionRecord]) -> str:
    """The clinician's view: no run ids, no implementation details by default (§16.1)."""
    open_tasks = [t for t in plan.tasks if t.status in ("PROPOSED", "OPEN", "BLOCKED")]
    next_step = open_tasks[0] if open_tasks else None
    changes = [c for c in diff_plans(previous, plan) if c.kind == "scientific"] if previous else []
    unresolved = [h for h in plan.hypotheses if h.assessment in ("UNRESOLVED", "UNDER_INVESTIGATION")]
    reviewed = [d for d in decisions if d.status == "REVIEWED"]
    body = [f"<h1>{_e(plan.case_ref)}: where things stand</h1>",
            f"<p class='muted'>Plan state: <span class='chip'>{_e(plan.lifecycle.value)}</span> "
            f"Nothing here is a treatment, a prescription or a validated prediction for this child.</p>",
            "<h2>The current question</h2>", f"<p>{_e(plan.decision_question)}</p>",
            "<h2>Present evidence level</h2>",
            "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in plan.baseline.known_limitations[:6]) + "</ul>",
            "<h2>Unresolved decision</h2>",
            "<ul>" + "".join(f"<li><b>{_e(h.id)}</b> {_e(h.statement)} — <span class='muted'>"
                             f"{_e(h.assessment.lower().replace('_', ' '))}; decided by {_e(h.distinguished_by)}"
                             f"</span></li>" for h in unresolved) + "</ul>",
            "<h2>Next proposed step</h2>",
            (f"<div class='card'><p>{_e(next_step.description)}</p><p class='muted'>Owner: "
             f"{_e(next_step.owner.value.replace('_', ' '))}. Status: {_e(next_step.status.lower())}.</p></div>"
             if next_step else "<p>No open step.</p>"),
            "<h2>Blockers</h2>", "<ul>" + "".join(f"<li>{_e(b)}</li>" for b in plan.blockers) + "</ul>",
            "<h2>What changed since the last review</h2>",
            ("<ul>" + "".join(f"<li>{_e(c.path)}</li>" for c in changes[:12]) + "</ul>") if changes
            else "<p>No scientific change since the previous version.</p>",
            f"<p class='muted'>{len(reviewed)} reviewed interpretation(s) on record.</p>",
            "<details><summary>Evidence, assumptions and competing interpretations</summary>",
            _table(["hypothesis", "evidence", "alternatives"],
                   [[_e(h.id + " " + h.statement), _e("; ".join(f"{e.ref} ({e.scope_note})" for e in h.evidence) or
                                                      "none cited"), _e(", ".join(h.alternatives) or "—")]
                    for h in plan.hypotheses]),
            "<p>Assumptions:</p><ul>" + "".join(f"<li>{_e(a.id)}: {_e(a.statement)}</li>" for a in plan.assumptions)
            + "</ul></details>"]
    return _page(f"{plan.case_ref} overview", "".join(body))


def editor_view(plan: ProspectivePlan) -> str:
    report = validate(plan)
    gaps = report.scientific_readiness
    by_obj: dict[str, int] = {}
    for g in gaps:
        by_obj[g.object_ref] = by_obj.get(g.object_ref, 0) + 1
    body = [f"<h1>Plan editor — {_e(plan.plan_id)}</h1>",
            f"<p><span class='chip'>{_e(plan.lifecycle.value)}</span><span class='chip'>version "
            f"{_e(plan.version_id)}</span><span class='chip'>{'FREEZABLE' if report.freezable else 'NOT FREEZABLE'}"
            f"</span></p>",
            "<h2>Experiment completeness</h2>",
            _table(["experiment", "decision", "open fields"],
                   [[_e(e.id), _e(e.decision_question),
                     _e(by_obj.get(e.id, 0) + sum(by_obj.get(ep, 0) for ep in e.endpoints))]
                    for e in plan.experiments]),
            "<h2>Missing fields — what, why, who</h2>",
            _table(["object", "field", "why it matters", "owner", "blocks"],
                   [[_e(g.object_ref), _e(g.field), _e(g.reason), _e(g.owner.value), _e(g.blocks)] for g in gaps]),
            "<h2>Endpoints</h2>",
            _table(["id", "meaning", "desired", "denominator", "required", "threshold"],
                   [[_e(e.id), _e(e.biological_meaning), _e(e.desired), _e(e.denominator or "—"),
                     "yes" if e.required else "optional",
                     _e(e.effect_criterion.value if e.effect_criterion.value is not None
                        else f"null ({e.effect_criterion.null_reason})")] for e in plan.endpoints]),
            "<h2>Forecasts</h2>",
            _table(["id", "prediction", "disconfirming", "mode", "probability", "applicability"],
                   [[_e(f.id), _e(f.prediction), _e(f.disconfirming_pattern), _e(f.mode.value),
                     _e(f.probability if f.probability is not None else f"null — {f.probability_null_reason}"),
                     _e(f.model_applicability.value)] for f in plan.forecasts]),
            "<h2>Rule coverage</h2>",
            _table(["branch", "applies to", "actions"],
                   [[_e(r.branch), _e(", ".join(k.value for k in r.applies_to)), _e(", ".join(r.actions))]
                    for r in plan.rules]),
            "<h2>Dependencies (table view of the graph)</h2>",
            _table(["from", "depends on"], [[_e(h.id), _e(", ".join(h.dependencies) or "—")] for h in plan.hypotheses]
                   + [[_e(f.id), _e(", ".join([f.hypothesis, f.experiment, f.endpoint, *f.assumptions]))]
                      for f in plan.forecasts]),
            "<h2>Tasks</h2>",
            _table(["id", "task", "owner", "status", "external action"],
                   [[_e(t.id), _e(t.description), _e(t.owner.value), _e(t.status),
                     "authorized" if t.external_action_authorized else "not authorized"] for t in plan.tasks]),
            "<h2>Unsent capability requests</h2>",
            _table(["id", "type", "decision it could change", "status"],
                   [[_e(c.id), _e(c.type.value), _e(c.decision_it_could_change), _e(c.status)]
                    for c in plan.capability_requests]),
            "<h2>Reviews</h2>",
            _table(["role", "actor", "decision", "content reviewed"],
                   [[_e(r.role.value), _e(f"{r.actor.identity} ({r.actor.actor_type.value})"), _e(r.decision.value),
                     _e(r.object_version[:19])] for r in plan.reviews]) if plan.reviews else "<p>None.</p>"]
    return _page(f"{plan.plan_id} editor", "".join(body))


def decision_view(plan: ProspectivePlan, record: DecisionRecord, observation_values: dict | None = None) -> str:
    """Scenario explorer (hypothetical) or result review (real), from one record shape."""
    banner = "HYPOTHETICAL SCENARIO — not evidence, not a decision, nothing was sent" if record.scenario else None
    forecasts = [f for f in plan.forecasts if f.experiment in {e.id for e in plan.experiments}]
    by_ep = {e.id: e for e in plan.endpoints}
    rows = []
    for f in forecasts:
        ep = by_ep.get(f.endpoint)
        observed = (observation_values or {}).get(ep.key) if ep else None
        rows.append([_e(f.id), _e(ep.key if ep else f.endpoint), _e(f.expected_direction), _e(observed or "—")])
    gates = {k: v for k, v in record.predicates.items() if k in ("identity_and_provenance_verified",
                                                                 "required_readouts_present", "precision_adequate",
                                                                 "controls_valid")}
    body = [f"<h1>{'Scenario explorer' if record.scenario else 'Result review'} — {_e(record.decision_id)}</h1>",
            f"<p><span class='chip'>{_e(record.status)}</span> rules {_e(record.rules_version)}</p>",
            "<h2>Quality gates first</h2>",
            _table(["gate", "value"], [[_e(k), _e(v)] for k, v in gates.items()]),
            "<h2>Frozen expectation vs observation, endpoint by endpoint</h2>",
            _table(["forecast", "endpoint", "expected", "observed"], rows),
            "<h2>Matched branches</h2>",
            "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in record.interpretation) + "</ul>",
            ("<p class='warn'>Matched but not admissible: " + _e(", ".join(record.inadmissible_matches)) + "</p>")
            if record.inadmissible_matches else "",
            "<h2>Unknown inputs and information requests</h2>",
            "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in record.unknown_inputs + record.information_requests) + "</ul>",
            "<h2>Proposed next steps</h2>",
            "<ul>" + "".join(f"<li>{_e(a)}</li>" for a in record.proposed_actions) + "</ul>",
            ("<p class='warn'>Contradictory actions: " + _e("; ".join(" vs ".join(p) for p in
                                                                   record.conflicting_actions))
             + " — DECISION_REVIEW_REQUIRED</p>") if record.conflicting_actions else "",
            "<h2>What cannot be concluded</h2>",
            "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in record.cannot_conclude) + "</ul>",
            "<h2>Review options</h2>" + ("<p>None — a scenario is never reviewed into the case.</p>" if record.scenario
                                         else "<p>accept interpretation · amend with reason · request clarification "
                                              "· defer decision (<code>rarepipe prospective review</code>)</p>")]
    if record.review:
        body.append(f"<h2>Human review</h2><p>{_e(record.review.decision.value)} by {_e(record.review.actor.identity)} "
                    f"as {_e(record.review.role.value)}: {_e(record.review.rationale)}</p>")
    return _page(record.decision_id, "".join(body), banner)


def audit_view(store: PlanStore) -> str:
    versions = store.versions()
    rows = []
    for older, newer in zip(versions, versions[1:], strict=False):
        a, b = store.load(older), store.load(newer)
        for c in diff_plans(a, b):
            rows.append([_e(newer), _e(c.kind), _e(c.path), _e(str(c.old)[:120]), _e(str(c.new)[:120])])
    lineage = [[_e(v), _e(store.load(v).parent_version or "—"), _e(store.load(v).change_kind),
                _e(store.load(v).change_reason)] for v in versions]
    body = ["<h1>Change and audit</h1>", "<h2>Lineage</h2>",
            _table(["version", "parent", "kind", "reason"], lineage),
            "<h2>Changes (scientific, editorial, operational)</h2>",
            _table(["version", "kind", "path", "old", "new"], rows),
            "<h2>Audit events</h2>",
            _table(["at", "event", "detail"], [[_e(e.get("at")), _e(e.get("event")),
                                                _e({k: v for k, v in e.items() if k not in ('at', 'event')})]
                                               for e in store.audit_events()])]
    return _page(f"{store.plan_id} audit", "".join(body))


def write_views(store: PlanStore, out: Path, scenarios: list[DecisionRecord] = ()) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    plan = store.load()
    versions = store.versions()
    previous = store.load(versions[-2]) if len(versions) > 1 else None
    decisions = store.decisions()
    files = {"doctor.html": doctor_view(plan, previous, decisions), "editor.html": editor_view(plan),
             "audit.html": audit_view(store)}
    obs = {o.observation_id: {v.endpoint_key: (v.category or "") for v in o.values} for o in store.observations()}
    for d in decisions:
        files[f"review_{d.decision_id}.html"] = decision_view(plan, d, obs.get(d.observation_id))
    for s in scenarios:
        files[f"scenario_{s.decision_id}.html"] = decision_view(plan, s)
    written = []
    for name, text in files.items():
        (out / name).write_text(text)
        written.append(out / name)
    return written
