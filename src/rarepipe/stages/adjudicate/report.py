"""Human-readable evidence dossier — rendered only from the sanitized AdjudicatedHypothesis.

Claims stay separate, supporting and contradicting evidence stay separate, and gaps are
stated as gaps. No overall score, no classification, no recommendation.
"""

from __future__ import annotations

from rarepipe.stages.adjudicate.model import AdjudicatedHypothesis, Direction, EvidenceClass

CLASS_ORDER = sorted(EvidenceClass, key=lambda c: c.rank)


def render(h: AdjudicatedHypothesis) -> str:
    assert h.visibility == "sanitized", "report must be rendered from the sanitized artifact"
    out: list[str] = []
    w = out.append
    by_id = {a.assertion_id: a for a in h.assertions}

    w(f"# EVIDENCE ADJUDICATION — {h.case_id}\n")
    w(f"**Hypothesis:** {h.gene_symbol}, {h.inheritance_model} (candidate compound heterozygous)  ")
    w(f"**Status:** {h.status.value}  ")
    w(f"**Overall:** {h.evidence_summary.overall} — {h.evidence_summary.overall_basis}\n")
    w(f"> {h.interpretation_note}\n")

    w("## Claims, kept separate\n")
    w("| claim | subject | assessment | basis |")
    w("|---|---|---|---|")
    for c in h.claims:
        w(f"| {c.statement} | {c.subject} | **{c.assessment}** | {c.assessment_basis} |")
    w("")

    w("## Evidence by class\n")
    s = h.evidence_summary
    w("| class | state |")
    w("|---|---|")
    for label, value in (("human observation", s.human_observation), ("functional", s.functional), ("population", s.population),
                         ("molecular/mechanistic", s.molecular_mechanistic), ("computational", s.computational),
                         ("technical call", s.technical_call), ("phase", s.phase)):
        w(f"| {label} | {value} |")
    w("")
    w("_Ordered by the evidence hierarchy: a predictor does not outrank an assay or a human observation._\n")

    for direction, title in ((Direction.SUPPORTS, "Supporting evidence"), (Direction.CONTRADICTS, "Contradicting evidence"),
                             (Direction.UNCERTAIN, "Indeterminate evidence")):
        items = sorted([a for a in h.assertions if a.direction == direction], key=lambda a: (a.evidence_class.rank, a.assertion_id))
        w(f"## {title} ({len(items)})\n")
        if not items:
            w("_None._\n")
            continue
        for a in items:
            claim = next((c for c in h.claims if c.claim_id == a.claim_id), None)
            w(f"- **{a.assertion_id}** · `{a.evidence_class.value}` · strength **{a.strength.value}** — {a.statement}")
            if a.result:
                w(f"  - result: {a.result}")
            w(f"  - bears on: {claim.statement if claim else a.claim_id}")
            w(f"  - strength basis: {a.strength_basis}")
            p = a.provenance
            w(f"  - source: {p.source}" + (f" {p.source_version}" if p.source_version else "")
              + (f", id {p.identifier}" if p.identifier else "") + f", retrieval `{p.retrieval.value}`")
            for lim in a.limitations:
                w(f"  - limitation: {lim}")
        w("")

    w("## Phase\n")
    p = h.phase
    w(f"- status: **{p.status}**")
    w(f"- read-backed phase in the supplied VCF: {p.existing_vcf_readbacked_phase}")
    w(f"- genomic distance between the two loci: {p.genomic_distance_bp:,} bp" if p.genomic_distance_bp else "- genomic distance: unknown")
    w(f"- parental data: {p.parental_data}; long-range phasing: {p.long_range_phase}")
    w(f"- {p.note}\n")

    w("## What is missing\n")
    for gap in h.evidence_gaps:
        w(f"- {gap}")
    w("")
    w("## Unresolved questions\n")
    for q in h.unresolved_questions:
        w(f"- {q}")
    w("")

    w("## What would change our mind\n")
    for d, title in (("would_strengthen", "Would strengthen the hypothesis"), ("would_weaken", "Would weaken the hypothesis")):
        w(f"**{title}**\n")
        for m in [x for x in h.what_would_change_our_mind if x.direction == d]:
            w(f"- {m.evidence}")
            w(f"  - why: {m.why}")
        w("")

    w("## Evidence requests\n")
    for r in h.evidence_requests:
        w(f"### {r.request_id}\n")
        w(f"- **question:** {r.question}")
        w(f"- **why it matters:** {r.why_it_matters}")
        w(f"- **evidence needed:** {r.evidence_needed}")
        w(f"- **minimum information:** {r.minimum_information} (raw data required: {r.raw_data_required})")
        w(f"- **route:** {r.preferred_route}; blocks this stage: {r.blocks_this_stage}")
        w(f"\n> {r.draft_message}\n")

    w("## Next actions, by expected information value\n")
    w("| action | expected gain | cost | rationale |")
    w("|---|---|---|---|")
    for a in h.next_actions:
        w(f"| {a.action} | {a.expected_information_gain} | {a.cost} | {a.rationale} |")
    w("")

    if h.provisional_classifications:
        w("## Research-only provisional interpretation\n")
        for pc in h.provisional_classifications:
            w(f"- {pc.variant_role}: {pc.provisional_result} via {', '.join(pc.criteria_applied) or 'no criteria'} ({pc.criteria_source})")
            w(f"  - {pc.caveat}")
        w("")

    pv = h.provenance
    w("## Provenance\n")
    sh = pv.source_hypothesis
    w(f"- hypothesis from RawCandidateSet run {sh.raw_candidate_set_run_id} (rank {sh.solver_rank}, supported in {len(sh.profiles_supporting)} profile(s))")
    w(f"- NormalizedCase run {sh.normalized_case_run_id}")
    w("- evidence sources: " + "; ".join(f"{p.source}{' ' + p.source_version if p.source_version else ''} (`{p.retrieval.value}`)" for p in pv.evidence_sources))
    w(f"- disclosure policy: {pv.disclosure_policy}")
    w("- controls: " + "; ".join(pv.environment_controls))
    w(f"- rarepipe {pv.software.rarepipe} (commit `{pv.software.source_control.commit}`)")
    w(f"- schema {h.schema_['name']} {h.schema_['version']}; run {h.execution.run_id}")
    w("")
    w("## Not done here\n")
    w("- No diagnosis, and no clinical variant classification.")
    w("- No therapy, drug or treatment reasoning.")
    w("- No leaderboard submission.")
    w("- No candidate reranking, and no alternative candidates displaced.")
    w("- No case-specific variant identity transmitted to any external service.\n")
    return "\n".join(out)
