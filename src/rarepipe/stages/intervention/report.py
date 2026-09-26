"""The intervention-logic report. Rendered from the sanitized map only.

The section that matters most is the last one: what is *not* currently justified. A stage that only
lists what it likes teaches nobody where the edge of the evidence is.
"""

from __future__ import annotations

from rarepipe.stages.intervention.model import InterventionMap, PointStatus

MARK = {PointStatus.SUPPORTED: "✓", PointStatus.UNRESOLVED: "?", PointStatus.DEPRIORITIZED: "↓",
        PointStatus.NOT_JUSTIFIED: "✗"}


def render(m: InterventionMap) -> str:
    assert m.visibility == "sanitized", "the report must be rendered from the sanitized artifact"
    out: list[str] = []
    w = out.append

    w(f"# INTERVENTION LOGIC — {m.case_id}\n")
    w(f"**Gene:** {m.gene_symbol} · **Status:** `{m.status.value}`\n")
    w(f"> {m.interpretation_note}\n")
    w(f"{m.status_basis}\n")

    w("## Where the case stands\n")
    readiness = m.readiness
    w(f"- causal genotype: externally validated (Track 1 full match)")
    w(f"- disease mechanism: {'ready' if readiness.get('approved_drug_search', {}).get('ready') else 'not ready'} "
      f"for approved-drug search")
    allele = readiness.get("exact_allele_mechanism", {})
    w(f"- exact missense mechanism: {'complete' if allele.get('complete') else '**unresolved**'}"
      + (f" (blocker: `{allele.get('blocker')}`)" if allele.get("blocker") else ""))
    w("")

    w("## Mechanistic axes\n")
    for axis in m.axes:
        s = axis.support
        w(f"**{axis.id}** · {axis.biological_level} · confidence {axis.confidence}  ")
        w(f"{axis.state}  ")
        w(f"- support: human experimental `{str(s.human_experimental).lower()}`, curated human "
          f"`{str(s.curated_human_evidence).lower()}`, class-level human `{str(s.human_class_level).lower()}`, "
          f"**exact-variant experimental `{str(s.exact_variant_experimental).lower()}`**, "
          f"computational exact-variant `{str(s.computational_exact_variant).lower()}`")
        for limit in axis.limitations:
            w(f"- limitation: {limit}")
        w("")

    if m.negative_predictions:
        w("## Predictions that did not light up\n")
        w("_A model that finds nothing is a reason to deprioritize, never a refutation._\n")
        for n in m.negative_predictions:
            w(f"- **{n.hypothesis}** — {n.result} from {n.source} ({n.scope.value}, {n.strength})")
            w(f"  - {n.detail}")
            w(f"  - does not establish: {n.does_not_establish}")
        w("")
    if m.deprioritized_axes:
        w("| deprioritized axis | reason | reopen if |")
        w("|---|---|---|")
        for a in m.deprioritized_axes:
            w(f"| {a.axis} | {a.reason[:110]} | {'; '.join(a.reopen_if[:2])} |")
        w("")

    for point in m.intervention_points:
        w("─" * 60 + "\n")
        w(f"## {point.id} — {point.biological_state}\n")
        w(f"**Status:** {MARK[point.status]} `{point.status.value}` · **priority** {point.priority.value} · "
          f"**role** {point.role.value} · **scope** {point.evidence_scope.value}\n")
        d = point.desired_effect
        w(f"- **desired change:** {d.current_state} → {d.desired_state} (`{d.direction.value}`), "
          f"confidence {d.confidence}")
        w(f"- **why:** {point.rationale}")
        w(f"- **expected downstream effect:** {point.expected_downstream_effect}")
        w(f"- **establishing rescue evidence:** {len(point.establishing_rescue_evidence)} record(s)"
          + (f" — {', '.join(point.establishing_rescue_evidence[:6])}"
             if point.establishing_rescue_evidence else " — **none**"))
        if point.rescue_criterion:
            w(f"  - counts as establishing only if: {point.rescue_criterion}")
        for related in point.related_rescue_evidence:
            w(f"- **related rescue evidence** (does not establish this point): {related.what_it_shows}")
            w(f"  - why not establishing: {related.why_not_establishing}")
            w(f"  - records: {', '.join(related.evidence)}")
        w(f"- **mechanism claims:** {', '.join(point.mechanism_claims) or 'none'}")
        e = point.validation_endpoints
        if e.proximal or e.cellular or e.disease_related:
            w(f"- **expected readouts:** proximal {', '.join(e.proximal) or '—'}; cellular "
              f"{', '.join(e.cellular) or '—'}; disease-related {', '.join(e.disease_related) or '—'}")
        if point.reversibility:
            r = point.reversibility
            w(f"- **reversibility:** {r.reversible} (timing: {r.timing}){' — ' + r.note if r.note else ''}")
        w(f"- **depends on the exact-allele mechanism:** "
          f"{'**yes**' if point.requires_exact_allele_mechanism else 'no'}")
        if point.contraindicated_direction:
            w(f"- **contra-direction:** {point.contraindicated_direction}")
        for limit in point.limitations:
            w(f"- limitation: {limit}")
        c = point.what_would_change_our_mind
        w(f"- would strengthen: {c.would_strengthen}")
        w(f"- would weaken: {c.would_weaken}")
        w(f"- would falsify: {c.would_falsify}")
        w("")

    w("─" * 60 + "\n")
    w("## Forbidden directions\n")
    w("_Mechanistic contradiction detection, not clinical safety advice. Derived from the mechanism graph and "
      "functional evidence — never from a computational prediction._\n")
    w("| biological state | prohibited direction | why | derived from |")
    w("|---|---|---|---|")
    for f in m.forbidden_effects:
        w(f"| {f.biological_state} | **{f.prohibited_direction.value}** | {f.reason[:110]} | {f.derived_from} |")
    w("")

    w("## Search specifications for the next stage\n")
    if not m.search_specs:
        w("_None: no point is supported enough to search on._\n")
    for spec in m.search_specs:
        w(f"**{spec.spec_id}** (from {spec.intervention_point})  ")
        w(f"- target: {spec.biological_target}")
        w(f"- desired effect: `{spec.desired_effect.value}`")
        w("- acceptable mechanisms:")
        for mechanism in spec.acceptable_mechanisms:
            w(f"    - {mechanism}")
        for item in spec.insufficient_for_match:
            w(f"- **not sufficient for a mechanism match:** {item}")
        w(f"- **disallowed mechanisms:** {'; '.join(spec.disallowed_mechanisms)}")
        w(f"- expected rescue readout: {', '.join(spec.expected_rescue_readout) or '—'}")
        w(f"- minimum evidence: {spec.minimum_evidence}; specificity: {spec.patient_specificity.value}; "
          f"exact-allele dependency: {str(spec.exact_allele_dependency).lower()}")
        w(f"- constraints: {spec.constraints}")
        for u in spec.uncertainties:
            w(f"- uncertainty: {u}")
        w("")

    w("## Not currently justified\n")
    if not m.not_currently_justified:
        w("_Nothing was set aside._\n")
    for item in m.not_currently_justified:
        w(f"- {item}")
    w("")
    if m.unresolved_points:
        w("## Unresolved\n")
        for item in m.unresolved_points:
            w(f"- {item}")
        w("")

    w("## What the research actions bought\n")
    w("| action | expected | actual | gain | case state change |")
    w("|---|---|---|---|---|")
    for a in m.action_outcomes:
        w(f"| {a.action[:60]} | {a.expected_gain} | {a.actual_result[:80]} | {a.information_gain} | "
          f"{a.case_state_change[:60]} |")
    w("")
    for a in m.action_outcomes:
        if a.lesson:
            w(f"- lesson: {a.lesson}")
    w("")

    p = m.provenance
    w("## Provenance\n")
    w(f"- built from mechanism run {p.mechanism_run_id} ({p.mechanism_status})")
    w(f"- mechanism digest {p.mechanism_digest}")
    w(f"- AlphaGenome evidence present: {str(p.alphagenome_used).lower()}")
    w(f"- evidence precedence: {' > '.join(p.evidence_precedence)}")
    for control in p.environment_controls:
        w(f"- control: {control}")
    w(f"- schema {m.schema_['name']} {m.schema_['version']}; run {m.execution.run_id}")
    w("")
    w("## Not done here\n")
    w("- No medication, compound or drug class is named, ranked or recommended.")
    w("- No drug, chemical or medication database was consulted.")
    w("- No treatment plan, and no medical advice.")
    w("- No modality is pre-decided: what could achieve a direction is the next stage's question.\n")
    return "\n".join(out)
