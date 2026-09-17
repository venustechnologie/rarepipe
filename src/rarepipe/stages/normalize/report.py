"""Human-readable normalization report — rendered only from the sanitized NormalizedCase.

Aggregates only: no HPO identifiers or labels, no genotype values, no records.
"""

from __future__ import annotations

from rarepipe.core.issues import Severity
from rarepipe.stages.normalize.model import NormalizedCase, Status

_STATUS = {
    Status.NORMALIZATION_COMPLETE: "NORMALIZATION_COMPLETE",
    Status.NORMALIZATION_COMPLETE_WITH_WARNINGS: "NORMALIZATION_COMPLETE_WITH_WARNINGS",
    Status.NORMALIZATION_BLOCKED: "NORMALIZATION_BLOCKED",
}
_MARK = {"yes": "✓", "partial": "◐", "no": "✗"}


def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x)


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.2f}%" if whole else "n/a"


def render(c: NormalizedCase) -> str:
    assert c.visibility == "sanitized", "report must be rendered from the sanitized NormalizedCase"
    out: list[str] = []
    w = out.append
    w(f"# CASE NORMALIZATION — {c.case_id}\n")
    w(f"**Status:** {_STATUS[c.status]}  ")
    w(f"**Unresolved:** {c.issue_counts['BLOCKER']} blocker(s) · {c.issue_counts['ACTION_REQUIRED']} action(s) · {c.issue_counts['WARNING']} warning(s) · "
      f"{c.issue_counts['INFO']} info\n")

    w("## Readiness by capability\n")
    w("| capability | ready | blocking reasons | conditions |")
    w("|---|---|---|---|")
    for cap in c.readiness:
        w(f"| {cap.capability} | {_MARK[cap.ready]} {cap.ready} | {', '.join(cap.blocking_reasons) or '—'} | {', '.join(cap.conditions) or '—'} |")
    w("")

    w("## Technical quality vs biological sufficiency\n")
    w("- **Technical quality** (this stage): whether the data parse and can be represented consistently — see Genome and Phenotype below.")
    w("- **Biological sufficiency** (not judged here): e.g. absent pedigree means some inheritance questions may remain unresolvable; it does not make the dataset defective.\n")

    g = c.genome
    w("## Genome\n")
    if g.reference:
        r = g.reference
        s = r.contig_summary
        w(f"- ✓ assembly: **{r.assembly}** (confidence {r.assembly_confidence}, from Stage 01 contig-length evidence)")
        w(f"- source contig scheme: `{s.source_scheme}` — source names preserved; canonical identities via contig map")
        w(f"- contigs declared: {_n(s.declared)}; with records: {_n(s.with_records)}; length conflicts: {s.length_conflicts}")
        w("- contig classes: " + ", ".join(f"{k} {_n(v)}" for k, v in s.by_class.items()))
        w("- records by contig class: " + (", ".join(f"{k} {_n(v)}" for k, v in s.records_by_class.items()) or "n/a"))
        w("- binding basis: " + ", ".join(f"{k} {_n(v)}" for k, v in s.by_basis.items())
          + (f" (resource: {r.assembly_resource.name} {r.assembly_resource.version})" if r.assembly_resource else " (no assembly resource)"))
        if r.declared_references:
            w("- reference declared in the VCF header: " + ", ".join(f"`{d.basename}`" for d in r.declared_references))
        w(f"- analysis reference FASTA: **{r.analysis_reference.status}** — {r.analysis_reference.reason}")
    w(f"- samples: " + ", ".join(f"{s.sample_id} (role: {s.role}{', ' + s.role_source if s.role_source != 'unknown' else ''})" for s in g.samples))
    w("")

    v = g.variant_source
    w("## Variant records (complete stream)\n")
    if v is None:
        w("- ✗ no verified primary VCF was streamed\n")
    else:
        w(f"- {'✓' if v.streamed_completely else '✗'} streamed completely: {_n(v.data_lines)} data lines in {v.elapsed_seconds}s")
        w(f"- {'✓' if not v.records_malformed else '✗'} malformed records: {_n(v.records_malformed)}")
        w(f"- {'✓' if v.parsers_agree else '✗'} htslib independently read {_n(v.htslib_records)} records ({'agrees' if v.parsers_agree else 'DISAGREES'})")
        w(f"- {'✓' if v.sorted else '✗'} coordinate-sorted; contig order follows header: {v.contig_order_follows_header}")
        w(f"- exact duplicates: {_n(v.exact_duplicate_records)}; records sharing a position: {_n(v.records_sharing_position)}; records on undeclared contigs: {_n(v.records_on_undeclared_contigs)}")
        w(f"- invalid REF / ALT allele syntax: {_n(v.invalid_ref_alleles)} / {_n(v.invalid_alt_alleles)}; QUAL missing: {_n(v.qual_missing_records)}\n")
        f = v.filters
        total = v.records_parsed
        w("### FILTER distribution\n")
        w(f"| state | records | share |\n|---|---|---|")
        w(f"| PASS | {_n(f.pass_records)} | {_pct(f.pass_records, total)} |")
        w(f"| non-PASS | {_n(f.non_pass_records)} | {_pct(f.non_pass_records, total)} |")
        w(f"| `.` (no filter recorded) | {_n(f.missing_filter_records)} | {_pct(f.missing_filter_records, total)} |")
        w("")
        if f.records_by_filter:
            w("| filter label | records carrying it | header definition |\n|---|---|---|")
            defs = {d.id: d.description for d in f.definitions}
            for label, n in f.records_by_filter.items():
                w(f"| `{label}` | {_n(n)} | {defs.get(label, '**undeclared**')} |")
            w("")
        unused = [d for d in f.definitions if d.id != "PASS" and d.id not in f.records_by_filter]
        if unused:
            w("Declared but never used: " + ", ".join(f"`{d.id}`" for d in unused) + "\n")
        w(f"Records carrying multiple filters: {_n(f.records_with_multiple_filters)}. {f.note}\n")

        w("### Variant classes\n")
        w("| record class | records |\n|---|---|")
        for k, n in v.record_classes.items():
            w(f"| {k} | {_n(n)} |")
        w("")
        w("Allele-level classes: " + ", ".join(f"{k} {_n(n)}" for k, n in v.allele_classes.items())
          + f". Max ALT alleles in a record: {v.max_alt_alleles}; records with a `*` spanning-deletion allele: {_n(v.records_with_spanning_deletion_allele)}.\n")

        w("### Genotype data (aggregate)\n")
        w("| FORMAT field | in header | records declaring | records populated | populated |\n|---|---|---|---|---|")
        for s in v.format_fields:
            w(f"| {s.field} | {'✓' if s.present_in_header else '✗'} | {_n(s.records_declaring)} | {_n(s.records_populated)} | {100 * s.populated_fraction:.2f}% |")
        gs = v.genotype_states
        w("")
        w(f"GT states: hom-ref {_n(gs.hom_ref)} · het {_n(gs.het)} · hom-alt {_n(gs.hom_alt)} · het (two ALT alleles) {_n(gs.het_non_ref)} · "
          f"haploid {_n(gs.haploid_called)} · missing {_n(gs.missing)} · partially missing {_n(gs.partially_missing)}; "
          f"ploidy {gs.ploidy_counts}; malformed GT {_n(v.genotype_malformed)}.\n")
        p = v.phase
        w(f"**Phase information: {p.status}**" + (f" ({', '.join(p.kinds)})" if p.kinds else "")
          + f" — heterozygous records {_n(p.het_records)}, GT-phased {_n(p.het_records_gt_phased)}; PS populated {_n(p.ps_populated_records)}; "
          f"PGT {_n(p.pgt_populated_records)}; PID {_n(p.pid_populated_records)}. {p.note}\n")
        if p.interpretation_note:
            w(f"> {p.interpretation_note}\n")

        w("### Upstream processing declared in the VCF header\n")
        if not v.upstream_processing:
            w("- none declared\n")
        for step in v.upstream_processing:
            w(f"- {step.tool}" + (f" {step.version}" if step.version else "") + (f" ({step.date})" if step.date else "")
              + f" — parameters {step.parameters}; source `{step.source}`")
        w("\n_Declared history only; its presence is not evidence that the upstream pipeline was correct or complete._\n")

    ph = c.phenotype
    w("## Phenotype\n")
    w(f"- status: **{ph.status}**" + (f" against HPO release {ph.ontology_release} (sha256 {ph.ontology.sha256[:12]}…)" if ph.ontology else ""))
    w(f"- supplied terms: {ph.source_term_count}; distinct canonical concepts: {ph.canonical_term_count}")
    w("- identity status: " + (", ".join(f"{k} {n}" for k, n in ph.status_counts.items()) or "none"))
    w("- HPO branches of resolved terms: " + (", ".join(f"{k} {n}" for k, n in ph.branch_counts.items()) or "none"))
    w("- polarity: " + (", ".join(f"{k} {n}" for k, n in ph.polarity_counts.items()) or "none") + " — listing a term is not treated as observed")
    w(f"- {ph.note}\n")

    w("## Pedigree\n")
    w(f"- {c.pedigree.status}: {c.pedigree.note}\n")

    rr = c.raw_reads
    w("## Raw reads\n")
    if not rr.available:
        w("- not supplied\n")
    else:
        w(f"- available: {len(rr.asset_ids)} FASTQ file(s), {rr.total_size_bytes / 1e9:.2f} GB, {len(rr.lane_pairs)} lane pair(s) — **not opened by this stage**")
        w(f"- sample linkage: **{rr.sample_linkage.status}** — {rr.sample_linkage.reason}\n")

    if c.assertions:
        w("## Case assertions\n")
        for a in c.assertions:
            w(f"- {a.assertion_id}: {a.subject_type} {a.subject_id} {a.predicate} = {a.value} [{a.evidence_type}] — "
              + ("applied" if a.applied else f"NOT applied ({a.rejection_reason})"))
        w("")

    w("## Issues\n")
    for origin in ("case_intake", "case_normalization"):
        group = [i for i in c.issues if i.origin_stage == origin]
        w(f"### Origin: {origin} ({len(group)})\n")
        for sev in Severity:
            for i in (x for x in group if x.severity == sev):
                scope = ", ".join(i.asset_ids[:4] + i.sample_ids) + (" …" if len(i.asset_ids) > 4 else "")
                w(f"- **{sev.value}** `{i.code}` [{i.resolution}]" + (f" [{scope}]" if scope else "") + f" — {i.message}")
                if i.suggested_action:
                    w(f"  - next action: {i.suggested_action}")
        w("")

    w("## Retention\n")
    rt = c.retention
    w(f"- classification: `{rt.classification}` (review required: {rt.review_required}); inherited from {', '.join(rt.inherited_from_assets) or '—'} "
      f"with classes {', '.join(rt.source_retention_classes) or '—'}")
    w(f"- {rt.note}\n")

    pv = c.provenance
    w("## Provenance\n")
    sm = pv.source_manifest
    w(f"- source CaseManifest {sm.schema_version} (stage {sm.stage_version}), run {sm.run_id}, sha256 {sm.manifest_sha256[:16]}…, seal verified: {sm.seal_verified}")
    w(f"- input fingerprint: `{sm.input_fingerprint}`")
    for r in pv.resources:
        w(f"- resource: {r.name} {r.version} — {r.status}, sha256 {r.sha256[:16]}…")
    w(f"- source assets verified: " + ", ".join(f"{a.asset_id} {a.status}" for a in pv.verified_assets))
    w("- operations: " + "; ".join(f"{o.operation} (transforms source: {o.transforms_source_data})" for o in pv.operations))
    w(f"- rarepipe {pv.software.rarepipe} (commit `{pv.software.source_control.commit}`, dirty={pv.software.source_control.dirty}); "
      f"htslib {pv.software.libraries.get('htslib')}; Python {pv.software.python}")
    w(f"- schema {c.schema_['name']} {c.schema_['version']}; stage {c.pipeline['stage']} {c.pipeline['stage_version']}; run {c.execution.run_id}")
    w("")
    return "\n".join(out)
