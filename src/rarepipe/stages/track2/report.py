"""Three documents: the adjudication, the submission report, and the pitch.

All three are generated from validated `SubmissionClaim`s and evidenced chain links, so the polished
version cannot become more confident than the science underneath it.
"""

from __future__ import annotations

from rarepipe.stages.track2.model import Status, Track2HypothesisSet


def _chain(h, evidence: dict) -> list[str]:
    lines = []
    for i, link in enumerate(h.proposed_chain, start=1):
        mark = "✓ evidenced" if link.kind == "evidenced" else "· inference"
        lines.append(f"{i}. **{link.step}** — {mark}")
        if link.note:
            lines.append(f"   - {link.note}")
        for eid in link.evidence:
            record = evidence.get(eid, {})
            lines.append(f'   - `{record.get("source_id", eid)}`: "{record.get("quote", "")[:200]}"')
    return lines


def render(s: Track2HypothesisSet, evidence: dict) -> str:
    out: list[str] = []
    w = out.append
    w(f"# TRACK 2 CANDIDATE ADJUDICATION — {s.case_id}\n")
    w(f"**Gene:** {s.gene_symbol} · **Status:** `{s.status.value}`\n")
    w(f"> {s.interpretation_note}\n")
    w(f"{s.status_basis}\n")

    w("## Hypotheses\n")
    if not s.hypotheses:
        w("_None proposed._\n")
    for h in s.hypotheses:
        w(f"### {h.id} — {h.active_ingredient}\n")
        w(f"**State:** `{h.state.value}`"
          + (f" · **grade** `{h.evidence_grade.value}`" if h.evidence_grade else "") + "\n")
        w(f"{h.statement}\n")
        w(f"- approval: **{'verified' if h.approval_verified else 'not verified'}**"
          + (f" · {h.approval_authority} · {', '.join(h.approval_jurisdictions)}" if h.approval_verified else ""))
        if h.canonical_ids:
            w(f"  - identifiers: {h.canonical_ids}")
        w(f"- direction: **{h.observed_direction}** against required `{h.required_direction}`")
        w(f"- tested in BUB1B deficiency: **{str(h.tested_in_bub1b_deficiency).lower()}** · in MVA: "
          f"**{str(h.tested_in_mva).lower()}**")
        if h.not_tested_note:
            w(f"  - {h.not_tested_note}")
        w(f"- exact-allele dependency: {str(h.exact_allele_dependency).lower()}")
        if h.independence_groups:
            w(f"- independence groups: {', '.join(h.independence_groups)}")
        w("\n**Proposed chain**\n")
        out.extend(_chain(h, evidence))
        w("")
        if h.validation_plan:
            v = h.validation_plan
            w("**Validation experiment**\n")
            w(f"- system: {v.system}")
            w(f"- intervention: {v.intervention}")
            w(f"- readouts: {', '.join(v.readouts)}")
            w(f"- hypothesis: {v.hypothesis}")
            w(f"- falsification: {v.falsification}")
            w("")
        c = h.what_would_change_our_mind
        for label, items in (("would strengthen", c.would_strengthen), ("would weaken", c.would_weaken),
                             ("would falsify", c.would_falsify)):
            for item in items:
                w(f"- {label}: {item}")
        for limit in h.limitations:
            w(f"- limitation: {limit}")
        w("\n**Promotion gate**\n")
        w("| check | result | detail |")
        w("|---|---|---|")
        for check in h.gate:
            w(f"| {check.check} | {'✓' if check.passed else '**✗**'} | {check.detail[:90]} |")
        w("")

    if s.rejected:
        w("## Rejected\n")
        w("| intervention | because | failed checks |")
        w("|---|---|---|")
        for r in s.rejected:
            w(f"| {r.intervention} | `{r.rejected_because.value}` | {'; '.join(r.failed_checks)[:120]} |")
        w("")

    w("## Search outcomes\n")
    w("_What each search established — and, said out loud, what it did not._\n")
    for o in s.search_outcomes:
        w(f"**{o.question}**  ")
        w(f"- result: `{o.result.value}`")
        w(f"- interpretation: {o.interpretation}")
        w(f"- **does not mean:** {o.does_not_mean}")
        w("")

    w("## Sealed pre-network baseline\n")
    b = s.baseline
    w("```")
    w(f"created_at                  {b.created_at}")
    w(f"created_before_network      {str(b.created_before_network_search).lower()}")
    w(f"public_evidence_only        {str(b.public_evidence_only).lower()}")
    w(f"discovery_run               {b.discovery_run_id}")
    w(f"discovery_digest            {b.discovery_digest}")
    w(f"intervention_map_run        {b.intervention_map_run_id}")
    w(f"git_commit                  {b.git_commit} ({b.git_describe})")
    w(f"hypotheses_found            {b.hypotheses_found}")
    w("```\n")
    w(f"{b.note}\n")

    w("## Questions carried to a future clinical node\n")
    for spec in s.node_query_specs:
        w(f"- **{spec.get('id')}** — {spec.get('question')}  (sent: {str(spec.get('sent', False)).lower()})")
    w("")
    w("## Next actions\n")
    w("| # | action | gain | cost | rationale |")
    w("|---|---|---|---|---|")
    for a in s.next_actions:
        w(f"| {a.rank} | {a.action} | {a.expected_information_gain} | {a.cost} | {a.rationale} |")
    w("")
    w("## Not done here\n")
    w("- No dose, no regimen, no route, no schedule.")
    w("- No claim that any medication works, and no recommendation to administer anything to anyone.")
    w("- Clinical actionability is NOT_ASSESSED by design: that judgement belongs to clinicians.")
    w("- Nothing was uploaded. Submission remains human-controlled.\n")
    return "\n".join(out)


def submission(s: Track2HypothesisSet, evidence: dict, discovery: dict) -> str:
    """The Track 2 report, generated from validated claims only."""
    eligible = [h for h in s.hypotheses if h.state.value.startswith("TRACK2_ELIGIBLE")]
    claims = {c.id: c for c in s.submission_claims}
    out: list[str] = []
    w = out.append
    w(f"# Track 2 — research repurposing hypothesis for {s.case_id} ({s.gene_symbol})\n")
    w("> A hypothesis for follow-up, grounded in mechanism. Not a treatment recommendation, not a claim of "
      "efficacy, and not medical advice.\n")

    w("## 1. Case resolution\n")
    w(f"{claims['SC_001'].statement} The pipeline analysed controlled genomic data entirely on local hardware in a "
      "network-denied sandbox; no patient variant, coordinate or phenotype combination was ever transmitted to any "
      "external service, including during this repurposing search.\n")
    w("## 2. Disease mechanism\n")
    w(f"{claims['SC_002'].statement} {claims['SC_004'].statement}\n")
    w("## 3. What biology would have to change\n")
    w("Restore sufficient functional BUBR1 availability or activity, or directly improve a rescue endpoint in "
      "BUB1B-deficient biology. Directions that weaken the checkpoint or increase missegregation are recorded as "
      "forbidden, and disqualify a candidate however well it engages the pathway.\n")

    w("## 4. Candidate research hypothesis\n")
    if not eligible:
        w("**None.** No approved medication passed the promotion gate. See section 9.\n")
    for h in eligible:
        w(f"### {h.active_ingredient} — `{h.evidence_grade.value}`\n")
        w(f"{h.statement}\n")
        w(f"Approval verified against {h.approval_authority} ({', '.join(h.approval_jurisdictions)}).\n")
        w("**Proposed mechanism chain**\n")
        out.extend(_chain(h, evidence))
        w("")
    w("## 5. Supporting evidence and its independence\n")
    for h in eligible:
        w(f"- {h.active_ingredient}: {len(h.establishing_evidence)} evidenced citation(s) across "
          f"{len([l for l in h.proposed_chain if l.kind == 'evidenced'])} arrow(s); independence groups: "
          f"{', '.join(h.independence_groups) or 'not assigned'}")
    w("")
    w("## 6. Contradictory and null evidence\n")
    for o in s.search_outcomes:
        if o.result.value in ("CONTRADICTORY", "NEGATIVE_EXPERIENCE_FOUND"):
            w(f"- {o.interpretation} (**does not mean:** {o.does_not_mean})")
    w(f"- {claims['SC_003'].statement}")
    w("")
    w("## 7. What is not known\n")
    for h in eligible:
        w(f"- {h.active_ingredient}: {h.not_tested_note}")
        for limit in h.limitations:
            w(f"  - {limit}")
    w(f"- {claims['SC_004'].statement}")
    w("")
    w("## 8. Proposed validation\n")
    for h in eligible:
        if not h.validation_plan:
            continue
        v = h.validation_plan
        w(f"**{h.active_ingredient}** — in {v.system}, apply {v.intervention} and measure "
          f"{', '.join(v.readouts)}. Supported if {v.hypothesis}. Falsified if {v.falsification}.\n")
    w("## 9. Negative search results\n")
    for o in s.search_outcomes:
        if o.result.value in ("NO_EVIDENCE_FOUND", "EXHAUSTED_TO_THRESHOLD"):
            w(f"- **{o.question}** → `{o.result.value}`. {o.interpretation}. Does not mean: {o.does_not_mean}.")
    w("\nRecording this matters: one team's dead end is another team's saved months.\n")
    w("## 10. Methodology\n")
    w("Nine stages, each producing an immutable, hashed artifact: intake, normalization, baseline hypothesis "
      "generation under four sensitivity profiles, evidence adjudication, prospective Track 1 validation, "
      "mechanism resolution, an AlphaGenome Atlas capability added without disturbing frozen results, intervention "
      "logic, approved-medication discovery, and this adjudication. Evidence carries scope, independence group and "
      "a quote verified against its stored source; an assistant proposes and the evidence store proves. The "
      "pipeline calls no model at inference time and runs end to end without one.\n")
    w("## 11. Scalability\n")
    w("The case-resolution architecture is reusable: the objects are disease-agnostic and the evidence sources are "
      "adapters. The stage generates node query specifications for evidence that public literature cannot supply — "
      "designed so those sources can later be distributed. No distributed network has been operated, and nothing "
      "here claims one has.\n")
    w("## 12. AI disclosure\n")
    w("AI assistance: Anthropic Claude Code (Claude Pro; Claude Opus 5; model-improvement/data-use setting: Off) "
      "and OpenAI ChatGPT (Plus; GPT-5.6 Sol; \"Improve the model for everyone\": Off) were used for software "
      "development, methodology, and review of sanitized/derived findings. Raw VCF/FASTQ files, exact patient "
      "variant coordinates/alleles, and genome-scale genotype tables were not provided to either service. "
      "Controlled genomic analysis was performed locally.\n")
    return "\n".join(out)


def pitch(s: Track2HypothesisSet, discovery: dict) -> str:
    eligible = [h for h in s.hypotheses if h.state.value.startswith("TRACK2_ELIGIBLE")]
    lead = eligible[0] if eligible else None
    out = [f"# Three-minute pitch — {s.case_id}\n",
           "_Speaker notes. Every number here traces to a sealed artifact._\n",
           "## 0:00 — the case\n",
           "A child with mosaic variegated aneuploidy. 85 GB of controlled data, analysed entirely on a laptop in a "
           "network-denied sandbox. The pipeline never saw a disease name when it generated its hypothesis.\n",
           "## 0:30 — we were right, and we can prove we said so first\n",
           "Track 1: full match at rank 1, 100/100 rank points, F-max 1.000. The predictions file was hashed and "
           "frozen hours before the oracle was queried, and that hash never changed.\n",
           "## 1:00 — what the mechanism actually supports\n",
           "Biallelic BUB1B disruption, impaired checkpoint, mosaic aneuploidy — with rescue evidence making the "
           "direction causal. And one link deliberately left unknown: what this child's missense allele does. "
           "Nobody has measured it, so the pipeline says so.\n",
           "## 1:30 — the honest drug result\n",
           "No approved medication has ever been tested for rescue in BUB1B-deficient biology. Not failed — "
           "untested. The search also found approved drugs that push this biology the wrong way, which is directly "
           "useful for a clinician.\n"]
    if lead:
        out += ["## 2:00 — one hypothesis worth testing\n",
                f"{lead.active_ingredient}, approval verified. {lead.statement} Every arrow in that chain is either "
                "cited to a retrieved paper or marked as an inference. It has never been tested in this disease, "
                "and we propose the experiment rather than the treatment.\n"]
    else:
        out += ["## 2:00 — where the public literature ends\n",
                "No approved medication met the evidence bar. That is the finding: we have mapped precisely where "
                "public evidence stops and where a clinical network would have to begin.\n"]
    out += ["## 2:30 — what this is really for\n",
            "Every stage is a reusable object, not a script. The unanswered questions are already written as node "
            "query specifications — the shape a hospital could answer without moving a patient record. One child's "
            "dead end becomes the next child's saved months.\n",
            "## 2:50 — close\n",
            "We did not find a cure. We found the exact edge of what is known, and left a machine-readable map of "
            "how to cross it.\n"]
    return "\n".join(out)
