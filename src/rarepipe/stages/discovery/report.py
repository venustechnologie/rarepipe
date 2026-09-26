"""The discovery dossier. Rendered from the sanitized artifact.

Two sections carry most of the value and neither is the candidate list: what was found moving the
biology the wrong way, and what nobody has tried. A stage that reports only candidates would hide
both.
"""

from __future__ import annotations

from rarepipe.stages.discovery.model import CandidateState, InterventionDiscovery, Lane, Outcome

MARK = {CandidateState.MECHANISM_MATCH: "✓", CandidateState.INSUFFICIENT_EVIDENCE: "?",
        CandidateState.CONTRADICTED: "✗", CandidateState.NOT_APPROVED: "—",
        CandidateState.DISCOVERED: "·"}


def render(d: InterventionDiscovery) -> str:
    assert d.visibility == "sanitized", "the report must be rendered from the sanitized artifact"
    out: list[str] = []
    w = out.append

    w(f"# APPROVED INTERVENTION DISCOVERY — {d.case_id}\n")
    w(f"**Gene:** {d.gene_symbol} · **Status:** `{d.status.value}`\n")
    w(f"> {d.interpretation_note}\n")
    w(f"{d.status_basis}\n")

    w("## What was searched\n")
    w("| lane | task | documents | question |")
    w("|---|---|---|---|")
    for s in d.searches:
        w(f"| `{s.lane.value}` | {s.knowledge_task} | {s.documents} | {s.note} |")
    w("")

    w("## Experiences found\n")
    w("_Something that was actually tried, and what happened. An intervention nobody tried appears nowhere in "
      "this table — that is the difference between untested and failed._\n")
    if not d.experiences:
        w("_None._\n")
    else:
        w("| id | intervention | outcome | system | endpoint | source |")
        w("|---|---|---|---|---|---|")
        for e in d.experiences:
            endpoint = "; ".join(f"{m.endpoint} ({m.direction})" for m in e.measured_endpoints) or "—"
            w(f"| {e.id} | {e.intervention_ingredient} | **{e.outcome.value}** | {e.subject_scope.value} | "
              f"{endpoint} | `{e.evidence_source.source_id}` |")
        w("")
        for e in d.experiences:
            w(f"**{e.id}** — {e.intervention_ingredient} · lane `{e.lane.value}`  ")
            w(f'> "{e.evidence_source.quote[:280]}"')
            w(f"- system: {e.model or e.subject_scope.value}; intent: {e.intervention_intent or '—'}")
            for limit in e.limitations:
                w(f"- limitation: {limit}")
            w("")

    w("## Candidates\n")
    if not d.candidates:
        w("_None discovered._\n")
    else:
        w("| id | ingredient | approved | state | match | direction | directness |")
        w("|---|---|---|---|---|---|---|")
        for c in d.candidates:
            m = c.mechanism_match
            w(f"| {c.id} | {c.ingredient} | {'**yes** — ' + (c.approval.authority_source or '') if c.approval.verified else 'not verified'} "
              f"| {MARK[c.state]} {c.state.value} | {m.status.value if m else '—'} | {m.direction if m else '—'} "
              f"| {m.evidence_directness.value if m else '—'} |")
        w("")
        for c in d.candidates:
            w(f"### {c.id} — {c.ingredient}\n")
            a = c.approval
            w(f"- approval: **{'verified' if a.verified else 'not verified'}**"
              + (f" · {a.authority_source} · jurisdictions {', '.join(a.jurisdictions)}" if a.verified else "")
              + (f" · ids {a.identifiers}" if a.identifiers else ""))
            w(f"  - {a.note}")
            if c.forbidden_direction_conflict:
                w(f"- **forbidden-direction conflict:** {c.forbidden_direction_conflict}")
            if c.mechanism_match:
                m = c.mechanism_match
                w(f"- required: `{m.required_effect}` · reported: {m.observed_or_reported_effect[:140]}")
                w(f"- direction **{m.direction}** → `{m.status.value}` ({m.basis})")
            w(f"- experiences: improved {len(c.experiences_positive)}, no effect {len(c.experiences_negative)}, "
              f"worsened {len(c.experiences_harmful)}, mixed {len(c.experiences_mixed)}, "
              f"considered but unmeasured {len(c.experiences_unknown)}")
            if c.independence_groups:
                w(f"- independence groups: {', '.join(c.independence_groups)}")
            w(f"- adversarial search: {'performed' if c.adversarial_search_performed else '**not performed**'}"
              + (f" — {c.adversarial_search_note}" if c.adversarial_search_note else ""))
            w(f"- pediatric metadata: {c.pediatric_metadata.note}")
            for limit in c.limitations:
                w(f"- limitation: {limit}")
            w("")

    w("## Directions to avoid\n")
    avoid = [c for c in d.candidates if c.state is CandidateState.CONTRADICTED]
    if not avoid:
        w("_None found._\n")
    else:
        w("_Interventions with evidence of pushing this biology the wrong way. Not a candidate list; the opposite "
          "of one, and arguably the most directly useful output of this stage. Approval status is shown per entry, "
          "because an unverified name must not be presented as an approved medicine._\n")
        for c in avoid:
            w(f"- **{c.ingredient}** — approval {'verified (' + ', '.join(c.approval.jurisdictions) + ')' if c.approval.verified else '**not verified**'}")
            w(f"  - {c.forbidden_direction_conflict}")
            w(f"  - observed-harm evidence: {', '.join(c.experiences_harmful) or 'none'}")
            for limit in c.limitations:
                w(f"  - {limit}")
        w("")

    w("## Reference compounds (not approved, not Track 2 eligible)\n")
    if not d.reference_compounds:
        w("_None._\n")
    for r in d.reference_compounds:
        w(f"- **{r.ingredient}** — {r.what_it_showed[:200]}")
        w(f"  - proves the biology is pharmacologically movable: {str(r.proves_pharmacologic_modifiability).lower()}")
        w(f"  - {r.follow_up_question}")
    w("")

    w("## Rejected, and why\n")
    w("| intervention | rejected because | detail |")
    w("|---|---|---|")
    for r in d.rejected:
        w(f"| {r.intervention} | `{r.rejected_because.value}` | {r.detail[:110]} |")
    w("")

    w("## What nobody has tried\n")
    w(f"_{d.untested_note}_\n")
    for need in d.unresolved_evidence_needs:
        w(f"- {need}")
    w("")

    w("## Questions for a future clinical node\n")
    w("_Generated here, deliberately not sent._\n")
    for spec in d.node_query_specs:
        w(f"**{spec.id}** — {spec.question}  ")
        w(f"- desired evidence: {', '.join(spec.desired_evidence)}")
        w(f"- a negative answer is useful: {str(spec.useful_negative_result).lower()}; "
          f"patient identity required: {str(spec.patient_identity_required).lower()}")
        w(f"- acceptable output: {', '.join(spec.acceptable_output)}; disclosure level: {spec.disclosure_level}")
        w(f"- arises from: {spec.arises_from}")
        w("")

    p = d.provenance
    w("## Provenance\n")
    w(f"- built from intervention map {p.intervention_map_run_id} ({p.intervention_map_digest})")
    w(f"- specifications consumed: {', '.join(p.specifications_consumed)}")
    w(f"- approval sources: {', '.join(p.approval_sources) or 'none verified'}")
    w(f"- research sessions: {', '.join(p.research_sessions) or 'none'}")
    w(f"- disclosure: {p.disclosure_policy}")
    for control in p.environment_controls:
        w(f"- control: {control}")
    w(f"- schema {d.schema_['name']} {d.schema_['version']}; run {d.execution.run_id}")
    w("")
    w("## Not done here\n")
    w("- No ranking: a list of states is not an order of preference.")
    w("- No dose, no regimen, no prescription.")
    w("- No claim that any medicine should or should not be given to this child. That is a clinician's judgement, "
      "on evidence this stage only gathers.")
    w("- No exact patient variant left the machine.\n")
    return "\n".join(out)
