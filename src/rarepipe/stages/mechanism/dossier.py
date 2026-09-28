"""The human-readable mechanism dossier, rendered only from the sanitized artifact.

Structure follows PRD 006 §45. Every section names its evidence ids, unknown links are
printed as unknown, and contradictions get their own section rather than a softening clause.
"""

from __future__ import annotations

from rarepipe.stages.mechanism.model import ClaimStatus, Direction, EvidenceLevel, MechanismDossier, Scope

MARK = {ClaimStatus.SUPPORTED: "✓", ClaimStatus.PARTIALLY_SUPPORTED: "~", ClaimStatus.CONTRADICTED: "✗",
        ClaimStatus.UNRESOLVED: "?"}


def render(d: MechanismDossier) -> str:
    assert d.visibility == "sanitized", "the dossier must be rendered from the sanitized artifact"
    out: list[str] = []
    w = out.append
    by_id = {c.id: c for c in d.claims}
    ev = {e.evidence_id: e for e in d.evidence}

    w(f"# MOLECULAR MECHANISM — {d.case_id}\n")
    w(f"**Gene:** {d.gene_symbol}  ")
    w(f"**Status:** `{d.status.value}`  ")
    w(f"**Causal genotype:** {'externally validated (Track 1 full match)' if d.state.causal_genotype_externally_validated else 'not externally validated'}\n")
    w(f"> {d.interpretation_note}\n")
    w(f"{d.status_basis}\n")
    r = d.readiness
    w("## Readiness, in two dimensions\n")
    w("| dimension | state | basis |")
    w("|---|---|---|")
    w(f"| disease mechanism | {'**ready for intervention search**' if r.disease_mechanism_ready_for_intervention_search else 'not ready'} "
      f"| {r.disease_mechanism_basis[:150]} |")
    w(f"| exact-allele mechanism | {'complete' if r.exact_allele_mechanism_complete else '**incomplete**'} "
      f"| blocker: `{r.exact_allele_blocker or 'none'}` |")
    w("")
    w(f"_Semantic review coverage: {r.semantic_review_coverage}._\n")

    w("## The chain, arrow by arrow\n")
    w("| link | status | scope | evidence | note |")
    w("|---|---|---|---|---|")
    for e in d.graph.edges:
        w(f"| {e.from_node} → {e.to_node} · _{e.relation}_ | {MARK[e.status]} {e.status.value} | {e.scope.value} | "
          f"{len(e.evidence)} | {e.note[:90]} |")
    w("")
    if d.graph.unknown_edges:
        w("**Unknown links, left unknown:** " + "; ".join(d.graph.unknown_edges) + "\n")
    if d.graph.qualifications:
        w("**The chain as drawn is not the whole story.** Accepted evidence says these matter, without placing "
          "an arrow we could source:\n")
        for q in d.graph.qualifications:
            w(f"- {q}")
        w("")

    w("## Claims\n")
    for c in d.claims:
        w(f"**{c.id}** {MARK[c.status]} `{c.status.value}` · scope `{c.scope.value}` · "
          f"{c.epistemic_class.value}{f' · confidence {c.confidence.value}' if c.confidence else ''}  ")
        w(f"{c.statement}  ")
        if c.evidence:
            w(f"- supporting ({len(c.evidence)}): {', '.join(c.evidence[:8])}{' …' if len(c.evidence) > 8 else ''}")
        if c.indirect_evidence:
            groups = sorted({ev[i].independence_group for i in c.indirect_evidence
                             if i in ev and ev[i].independence_group})
            w(f"- consistent but not establishing ({len(c.indirect_evidence)}): {', '.join(c.indirect_evidence[:8])}")
            if groups:
                w(f"  - independent sources among them: {len(groups)} ({', '.join(groups)}) — records sharing a "
                  f"group are not independent witnesses")
        if c.contradicting_evidence:
            w(f"- contradicting: {', '.join(c.contradicting_evidence[:8])}")
        if c.unknown_reason:
            w(f"- unresolved because: {c.unknown_reason}")
        for limit in c.limitations:
            w(f"- limitation: {limit}")
        w("")

    w("## Allele A — the truncating allele\n")
    a = d.state.allele_a
    w(f"- consequence: {a.molecular_consequence}")
    w(f"- transcript effect: {a.transcript_effect} ({a.transcript_effect_status.value})")
    w(f"- protein effect: {a.protein_effect} ({a.protein_effect_status.value})")
    w(f"- exact-allele functional evidence: {a.exact_functional_evidence}")
    for u in a.unresolved:
        w(f"- unresolved: {u}")
    w("")
    w("## Allele B — the missense allele\n")
    b = d.state.allele_b
    w(f"- consequence: {b.molecular_consequence}")
    w(f"- protein effect: {b.protein_effect} ({b.protein_effect_status.value})")
    w(f"- exact-allele functional evidence: {b.exact_functional_evidence}")
    for u in b.unresolved:
        w(f"- unresolved: {u}")
    w("")
    w("## Combined genotype\n")
    w(f"- {d.state.combined_genotype_state}")
    w(f"- status: {d.state.combined_genotype_status.value}\n")

    w("## Cellular mechanism\n")
    for label, status in (("spindle checkpoint", d.state.spindle_checkpoint),
                          ("chromosome segregation", d.state.chromosome_segregation),
                          ("mosaic aneuploidy", d.state.aneuploidy),
                          ("disease bridge", d.state.disease_bridge)):
        w(f"- {label}: **{status.value}**")
    w("")
    if d.state.mechanistic_classes:
        w("**Mechanistic classes the literature reports — kept separate, not averaged:**\n")
        for klass in d.state.mechanistic_classes:
            w(f"- {klass}")
        w("")

    w("## Evidence by scope\n")
    w("_The distinction the whole stage exists to preserve._\n")
    w("| scope | records | sources | strongest level |")
    w("|---|---|---|---|")
    for scope in Scope:
        items = [e for e in d.evidence if e.scope is scope]
        if not items:
            continue
        best = min((e.evidence_level for e in items), key=lambda lv: lv.rank)
        w(f"| {scope.value} | {len(items)} | {len({e.source_id for e in items})} | {best.value} |")
    w("")
    human = [e for e in d.evidence if e.evidence_level is EvidenceLevel.HUMAN_EXPERIMENTAL]
    w(f"Human experimental records: {len(human)} from {len({e.source_id for e in human})} source(s). "
      f"Rescue/complementation records: {sum(1 for e in d.evidence if e.rescue_experiment)}.\n")

    w("## Assays the field actually uses\n")
    w("| assay | question | models | sources |")
    w("|---|---|---|---|")
    for a_ in d.assays[:12]:
        w(f"| {a_.assay} | {a_.biological_question} | {', '.join(a_.models_used[:3])} | {a_.source_count} |")
    w("")

    w("## Contradictions\n")
    if not d.contradictions:
        w("_None found in the corpus. That is a statement about this corpus, not about the literature._\n")
    else:
        for c in d.contradictions[:12]:
            w(f"- {c}")
        w("")

    w("## Evidence strongest at\n")
    for s in d.evidence_strongest_at:
        w(f"- {s}")
    w("")
    w("## Evidence weakest at\n")
    for s in d.evidence_weakest_at:
        w(f"- {s}")
    w("")
    w("## What is unknown\n")
    for u in d.unknowns:
        w(f"- {u}")
    w("")
    w("## What would change our mind\n")
    for m in d.what_would_change_our_mind:
        w(f"- **{m.evidence}**")
        w(f"  - why: {m.why}")
        w(f"  - would change: {m.would_change}")
    w("")
    if d.residual_function:
        out.extend(residual_section(d))
    if d.corpus_refresh:
        out.extend(refresh_section(d))
    if d.direction_corrections:
        w("## Extractor directions corrected on semantic review\n")
        w("A sentence's polarity is not its relationship to every claim it lands in, so each passage is judged per "
          "claim. Claims a reviewer did not name keep the extractor's reading. The full record, per evidence id, is "
          "in `direction_corrections.json`.\n")
        w("| source | passage | per claim | reason | evidence → claim (extractor → reviewed) |")
        w("|---|---|---|---|---|")
        for c in d.direction_corrections:
            per_claim = ", ".join(f"{k}: {v}" for k, v in c.claims.items()) or (c.direction.value if c.direction else "")
            applied = "; ".join(f"{a['evidence_id']} → {a['claim_id']} ({a['old']} → {a['new']})" for a in c.applied)
            unused = f" — named but not reached: {', '.join(c.unused_claims)}" if c.unused_claims else ""
            w(f"| {c.source_id} | {c.quote_contains[:90]}… | {per_claim} | {c.reason} | {applied or 'none'}{unused} |")
        w("")
    w(f"## Highest-value unresolved question\n\n{d.highest_value_unresolved_question}\n")

    w("## Next actions\n")
    w("| # | action | gain | cost | time | friction | matters for intervention search |")
    w("|---|---|---|---|---|---|---|")
    for a_ in d.next_actions:
        w(f"| {a_.rank} | {a_.action} | {a_.expected_information_gain} | {a_.cost} | {a_.time} | {a_.friction} | "
          f"{a_.importance_for_intervention_search} |")
    w("")

    w("## How this was researched\n")
    w(f"- {len(d.knowledge_tasks)} knowledge task(s), {len(d.query_log)} query(ies) against public literature")
    w(f"- {len(d.documents)} document(s) stored; {sum(1 for x in d.documents if x.full_text)} with legitimately "
      f"accessible full text, {sum(1 for x in d.documents if not x.full_text)} as metadata and abstract only")
    w(f"- {len(d.evidence)} evidence record(s), every quote re-found in its stored source before acceptance")
    w(f"- {len(d.invalid_inferences)} claim(s) rejected for failing provenance validation")
    w(f"- automation: {d.automation_status.current_mode}; the pipeline does not call a model and runs without one")
    w("")
    w("| task | state | retrieval | extraction | semantic review | documents | reviewed by |")
    w("|---|---|---|---|---|---|---|")
    for task in d.knowledge_tasks:
        p_ = task.progress
        w(f"| `{task.id}` | {task.state.value} | {p_.retrieval} | {p_.deterministic_extraction} | "
          f"{p_.semantic_review} | {len(task.documents_found)} | {', '.join(task.reviewed_by) or '—'} |")
    w("")
    for task in d.knowledge_tasks:
        w(f"- `{task.id}` {task.question} — stop rule: {task.stop_reason}")
    w("")
    pv = d.provenance
    w("## Provenance\n")
    w(f"- adjudication run {pv.adjudication_run_id}; corpus run {pv.corpus_run_id} ({pv.corpus_digest})")
    if pv.causal_pair_validated_by:
        w(f"- causal pair: {pv.causal_pair_validated_by}")
    w(f"- disclosure: {pv.disclosure_policy}")
    for control in pv.environment_controls:
        w(f"- control: {control}")
    a = d.automation_status
    w(f"- automation: orchestration **{a.automated_llm_orchestration}**, mode **{a.current_mode}**, "
      f"pipeline depends on an LLM: **{str(a.pipeline_depends_on_an_llm).lower()}** ({a.reason})")
    for session in pv.research_sessions:
        w(f"- research session `{session.session_id}` ({session.mode}): {session.provider} {session.model} via "
          f"{session.interface}, task {session.knowledge_task}, template {session.prompt_template}, "
          f"{len(session.accepted)} claim(s) accepted, {len(session.rejected)} rejected, "
          f"case genomic data supplied: {str(session.case_specific_genomic_data_supplied).lower()}, "
          f"human reviewed: {str(session.human_reviewed).lower()}")
    for b in pv.evidence_bundles:
        w(f"- evidence bundle `{b.bundle_id}`: {len(b.documents)} document(s), {b.characters} characters, {b.digest}")
    w(f"- schema {d.schema_['name']} {d.schema_['version']}; run {d.execution.run_id}")
    w("")
    w("## Not done here\n")
    w("- No drug, treatment, repurposing or intervention reasoning of any kind.")
    w("- No gene-therapy or editing speculation; rescue experiments are recorded as mechanistic evidence only.")
    w("- No claim that class-level evidence describes this child's allele.")
    w("- No numeric mechanism score: we have nothing calibrated to produce one.\n")
    return "\n".join(out)


RESULT_MARK = {"restored": "restored", "not_restored": "not restored", "normal": "normal", "reduced": "reduced",
               "increased": "increased", "not_reported": "not reported"}


def residual_section(d: MechanismDossier) -> list[str]:
    rf = d.residual_function
    out = ["## Residual function — does the altered protein work when abundance is restored?\n",
           f"**Decision: `{rf.decision}`** — {rf.decision_meaning}.\n",
           "| level | finding | basis |", "|---|---|---|",
           f"| class (same region, other substitutions) | {rf.class_level} | {rf.class_level_basis} |",
           f"| this child's allele | {rf.exact_allele} | {rf.exact_allele_basis} |", "",
           f"Numbering: {rf.numbering_check}. How directly each experiment applies to this child was graded "
           "locally (exact / same position / nearby / same region / different region) and is kept in the private "
           "artifact only: a nearby published variant would localise the child's residue.\n",
           "| id | variant | protein tested | abundance | readouts | function at restored abundance | source |",
           "|---|---|---|---|---|---|---|"]
    for e in d.variant_experiments:
        readouts = "; ".join(f"{r.kind.replace('_', ' ')}: {RESULT_MARK[r.result]}" for r in e.readouts)
        out.append(f"| {e.experiment_id} | {e.variant_label} | {e.protein_tested.replace('_', ' ')} | "
                   f"{e.abundance_condition.replace('_', ' ')} | {readouts} | "
                   f"{e.function_at_restored_abundance.replace('_', ' ')} | {e.source_id} "
                   f"{', '.join(sorted({r.figure for r in e.readouts if r.figure}))} |")
    out.append("")
    out.append("Normal-protein replacement (WT rows) shows the assays respond to BUBR1; it is not evidence that any "
               "altered protein works.\n")
    if rf.supporting_observations:
        out.append("Bearing on the strategy, not on the decision:\n")
        out += [f"- {x}" for x in rf.supporting_observations]
        out.append("")
    out.append(f"**Distinguishing experiment.** {rf.distinguishing_experiment}\n")
    if rf.what_remains_open:
        out.append("Still open:\n")
        out += [f"- {x}" for x in rf.what_remains_open]
        out.append("")
    return out


def refresh_section(d: MechanismDossier) -> list[str]:
    out = ["## Corpus refresh — what became available\n",
           "| document | before | after | why | retrieved | supplements |", "|---|---|---|---|---|---|"]
    for r in d.corpus_refresh:
        supps = ", ".join(f"{s['href']}: {s['state'].replace('_', ' ')}" for s in r.get("supplements", [])) or "—"
        out.append(f"| {r['source_id']} {r.get('pmcid') or ''} | {r['before'].replace('_', ' ')} | "
                   f"{r['after'].replace('_', ' ')} | {r['reason']} | {r['retrieved_at'][:10]} | {supps} |")
    out.append("")
    if any(s["state"] == "inaccessible_bot_challenge" for r in d.corpus_refresh for s in r.get("supplements", [])):
        out.append("Supplements behind a bot-detection challenge were not solved or bypassed. A person can download "
                   "them and pass them to `rarepipe mechanism refresh-corpus --supplement SOURCE_ID=file.pdf`, which builds a new corpus run.\n")
    return out


def render_comparison(d: MechanismDossier) -> str:
    """The short note the reviewer asked for: what moved relative to the frozen result."""
    c = d.baseline_comparison
    out = [f"# Stage 06 reopened — comparison with {c.baseline_label or c.baseline_mechanism_run}\n",
           f"Frozen mechanism run `{c.baseline_mechanism_run}` ({c.baseline_mechanism_digest})"
           + (f"; frozen Track 2 run `{c.baseline_track2_run}` ({c.baseline_track2_digest})" if c.baseline_track2_run else "")
           + f". New run `{d.execution.run_id}` ({d.semantic_digest}).\n",
           "| | frozen | now | changed |", "|---|---|---|---|"]
    out += [f"| {r.topic} | {r.frozen} | {r.now} | {'**yes**' if r.changed else 'no'} |" for r in c.rows]
    out.append("")
    if d.residual_function:
        rf = d.residual_function
        out.append(f"**Decision: `{rf.decision}`.** {rf.decision_meaning[0].upper()}{rf.decision_meaning[1:]}.\n")
        out.append(f"**Distinguishing experiment.** {rf.distinguishing_experiment}\n")
    if c.regenerate:
        out.append("**Regenerated because of this:**\n")
        out += [f"- {x}" for x in c.regenerate]
        out.append("")
    out.append("Evidence for every row is in the run's sanitized dossier; quotes were re-found verbatim in the "
               "stored sources.\n")
    return "\n".join(out)
