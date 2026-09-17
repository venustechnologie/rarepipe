"""Human-readable baseline report — rendered only from the sanitized RawCandidateSet.

Gene symbols, ranks and scores appear (they are the finding). Variant coordinates,
HGVS, genotypes and sample labels do not — they are private-only. No candidate is
promoted, reordered or editorialised here.
"""

from __future__ import annotations

from rarepipe.core.issues import Severity
from rarepipe.stages.baseline.model import RawCandidateSet

TOP_N = 20


def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else "—" if x is None else str(x)


def render(c: RawCandidateSet) -> str:
    assert c.visibility == "sanitized", "report must be rendered from the sanitized RawCandidateSet"
    out: list[str] = []
    w = out.append
    by_id = {r.profile_id: r for r in c.results}
    runtime = {t.profile_id: t for t in c.execution.profile_runtimes}

    w(f"# BASELINE GENOMIC ANALYSIS — {c.case_id}\n")
    w(f"**Status:** {c.status.value}  ")
    w(f"**Issues:** {c.issue_counts['BLOCKER']} blocker(s) · {c.issue_counts['ACTION_REQUIRED']} action(s) · "
      f"{c.issue_counts['WARNING']} warning(s) · {c.issue_counts['INFO']} info\n")
    w(f"> {c.interpretation_note}\n")

    s = c.provenance.solver
    w("## Solver\n")
    w(f"- {s.name} {s.version}" + (f" (jar sha256 {s.jar_sha256[:12]}…)" if s.jar_sha256 else ""))
    w(f"- data: hg38 {s.hg38_data_version or '—'}, phenotype {s.phenotype_data_version or '—'}")
    w(f"- runtime: {s.java_version or '—'}, max heap {s.java_max_heap or '—'}")
    w(f"- assembly: {c.provenance.source_case.assembly}; source VCF sha256 {c.provenance.source_case.source_vcf_sha256[:12]}…\n")

    w("## Profiles\n")
    w("| profile | HPO terms | rule | failedVariantFilter | non-PASS permitted | analysisMode | status | candidates | runtime | peak RSS |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for p in c.profiles:
        r = by_id.get(p.profile_id)
        w(f"| {p.profile_id} | {p.phenotype.term_count} | {p.phenotype.rule} | {p.filter_policy.failed_variant_filter} | "
          f"{p.filter_policy.non_pass_records_permitted} | {p.filter_policy.analysis_mode} | "
          f"{r.status if r else '—'} | {_n(r.candidate_count) if r else '—'} | "
          f"{f'{runtime[p.profile_id].wall_clock_seconds:.0f}s' if runtime.get(p.profile_id) and runtime[p.profile_id].wall_clock_seconds else '—'} | "
          f"{f'{runtime[p.profile_id].peak_rss_bytes / 1e9:.1f} GB' if runtime.get(p.profile_id) and runtime[p.profile_id].peak_rss_bytes else '—'} |")
    w("")
    w("_`analysisMode: PASS_ONLY` is Exomiser's memory strategy and is constant across profiles; "
      "`failedVariantFilter` is the step that reads the VCF FILTER column. Source FILTER labels are never rewritten._\n")

    w("### Declared analysis assumptions\n")
    for a in (c.profiles[0].assumptions if c.profiles else []):
        w(f"- **{a.id}** ({a.scope}): {a.statement}")
        w(f"  - basis: {a.basis}")
    w("")

    st = c.stability
    w("## Candidate stability across profiles\n")
    if st is None or st.verdict == "insufficient":
        w(f"- insufficient completed profiles to compare{f': {st.verdict_basis}' if st else ''}\n")
    else:
        w(f"**Verdict: {st.verdict}** — {st.verdict_basis}\n")
        cols = st.profiles_compared
        w("| gene | " + " | ".join(cols) + " | profiles |")
        w("|---" * (len(cols) + 2) + "|")
        for row in st.top_gene_table:
            w(f"| {row.gene_symbol} | " + " | ".join(str(row.ranks.get(p) or "—") for p in cols) + f" | {row.appears_in_profiles}/{len(cols)} |")
        w("")
        w("| pair | top-1 same | top-5 | top-10 | top-20 | comp-het genes |")
        w("|---|---|---|---|---|---|")
        for p in st.pairwise:
            w(f"| {p.profile_a} vs {p.profile_b} | {p.top1_same_gene} | {p.top5_gene_overlap}/5 | {p.top10_gene_overlap}/10 | "
              f"{p.top20_gene_overlap}/20 | {p.compound_het_gene_overlap} |")
        w("")
        w(f"- genes in every profile's top {len(st.top_gene_table)}: " + (", ".join(st.genes_in_all_profiles) or "none"))
        w("- **FILTER sensitivity** — appear only when non-PASS records are permitted: "
          + (", ".join(st.genes_only_when_non_pass_permitted) or "none"))
        w("- **Phenotype sensitivity** — appear only with the wider HPO set: "
          + (", ".join(st.genes_only_with_eighth_term) or "none"))
        if st.max_rank_movement:
            worst = sorted(st.max_rank_movement.items(), key=lambda kv: -kv[1])[:5]
            w("- largest rank movement: " + ", ".join(f"{g} ±{d}" for g, d in worst))
        w("")

    w("## Top candidates per profile\n")
    for r in c.results:
        if r.status != "completed":
            w(f"### {r.profile_id} — {r.status}" + (f" ({r.failure_reason})" if r.failure_reason else "") + "\n")
            continue
        w(f"### {r.profile_id} — {_n(r.candidate_count)} ranked gene/inheritance-model candidates\n")
        w("| rank | gene | inheritance model | combined | phenotype | variant | contributing variants | pair | any non-PASS |")
        w("|---|---|---|---|---|---|---|---|---|")
        for cand in r.candidates[:TOP_N]:
            w(f"| {cand.rank} | {cand.gene_symbol} | {cand.inheritance_model} | {cand.score_combined:.4f} | "
              f"{cand.score_phenotype:.4f} | {cand.score_variant:.4f} | {cand.contributing_variant_count} | "
              f"{'✓' if cand.is_variant_pair else ''} | {'!' if cand.any_contributing_variant_non_pass else ''} |"
              if cand.score_combined is not None else
              f"| {cand.rank} | {cand.gene_symbol} | {cand.inheritance_model} | — | — | — | {cand.contributing_variant_count} | "
              f"{'✓' if cand.is_variant_pair else ''} | {'!' if cand.any_contributing_variant_non_pass else ''} |")
        w("")
        pairs = [x for x in r.candidates if x.is_variant_pair][:TOP_N]
        if pairs:
            w(f"**Compound-heterozygous configurations ({len(pairs)} shown):** "
              + ", ".join(f"{p.gene_symbol} (rank {p.rank})" for p in pairs))
            w(f"> {pairs[0].phase.note}\n" if pairs[0].phase else "")
        if r.variants_in_source:
            w(f"_Source records: {_n(r.variants_in_source)}; variant rows in solver output after its filters: "
              f"{_n(r.variants_reported_by_solver)}. The difference is Exomiser's own filtering, not data loss._\n")
        if r.contigs_absent_from_solver_output:
            w(f"_Contigs carrying source records but absent from this profile's variant output: "
              f"{len(r.contigs_absent_from_solver_output)} (expected for filtered analyses; listed in the artifact)._\n")

    w("## Issues\n")
    for sev in Severity:
        group = [i for i in c.issues if i.severity == sev]
        if not group:
            continue
        w(f"### {sev.value} ({len(group)})\n")
        for i in group:
            scope = ", ".join(i.profile_ids)
            w(f"- **{i.code}**" + (f" [{scope}]" if scope else "") + f" — {i.message}")
            for e in i.evidence[:6]:
                w(f"  - evidence: {e}")
            if i.suggested_action:
                w(f"  - next action: {i.suggested_action}")
        w("")

    rt = c.retention
    w("## Retention\n")
    w(f"- native solver outputs (annotated tables, logs): `{rt.native_solver_outputs}`")
    w(f"- this RawCandidateSet: `{rt.raw_candidate_set}`")
    w(f"- small top-N candidate findings: `{rt.top_n_findings}`")
    w(f"- {rt.note}\n")

    pv = c.provenance
    w("## Provenance\n")
    w(f"- NormalizedCase run {pv.source_case.normalized_case_run_id}, digest {(pv.source_case.normalized_case_semantic_digest or '')[:24]}…")
    w(f"- rarepipe {pv.software.rarepipe} (commit `{pv.software.source_control.commit}`, dirty={pv.software.source_control.dirty})")
    w(f"- host: {pv.execution_host.get('platform', '—')}")
    w("- controls: " + "; ".join(pv.environment_controls))
    w(f"- schema {c.schema_['name']} {c.schema_['version']}; stage {c.pipeline['stage']} {c.pipeline['stage_version']}; run {c.execution.run_id}")
    w("")
    w("## Not done here\n")
    w("- No candidate was reranked, promoted or filtered by rarepipe.")
    w("- No disease name, gene panel or candidate list was supplied to the solver.")
    w("- Read-backed phase (PGT/PID) was not consulted; compound-heterozygous phase remains unresolved.")
    w("- Nothing here is a diagnosis, and no result has been submitted anywhere.\n")
    return "\n".join(out)
