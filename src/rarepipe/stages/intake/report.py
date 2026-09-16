"""Human-readable intake report.

Rendered exclusively from the *sanitized* manifest, so it cannot contain
restricted fields regardless of what this module does.
"""

from __future__ import annotations

from rarepipe.core.issues import Severity
from rarepipe.stages.intake.manifest import (
    AlignmentMetadata,
    CaseManifest,
    FastaMetadata,
    LogicalRole,
    PhenotypeMetadata,
    RetentionClass,
    Status,
    VcfMetadata,
)

_STATUS_LINE = {
    Status.INTAKE_COMPLETE: "INTAKE_COMPLETE — ready for normalization",
    Status.INTAKE_COMPLETE_WITH_WARNINGS: "INTAKE_COMPLETE_WITH_WARNINGS — ready for normalization, with conditions below",
    Status.INTAKE_BLOCKED: "INTAKE_BLOCKED — not ready for normalization",
}


def _gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 1e8 else f"{n / 1e6:.2f} MB" if n >= 1e5 else f"{n} B"


def _mark(ok: bool | None) -> str:
    return "✓" if ok else "✗" if ok is False else "?"


def render(m: CaseManifest) -> str:
    assert m.redaction.visibility == "sanitized", "report must be rendered from the sanitized manifest"
    out: list[str] = []
    w = out.append
    by_id = {a.asset_id: a for a in m.assets}
    issues_for = lambda aid: [i for i in m.issues if aid in i.asset_ids]  # noqa: E731

    w(f"# CASE INTAKE — {m.case.case_id}\n")
    w(f"**Status:** {_STATUS_LINE[m.status]}  ")
    w(f"**Blockers:** {m.issue_counts['BLOCKER']} · **Actions required:** {m.issue_counts['ACTION_REQUIRED']} · "
      f"**Warnings:** {m.issue_counts['WARNING']} · **Info:** {m.issue_counts['INFO']}\n")
    w(f"> {m.readiness.rationale}\n")

    w("## Genomic variant data\n")
    vcfs = [a for a in m.assets if a.logical_role == LogicalRole.GENOMIC_VARIANTS]
    if not vcfs:
        w("- ✗ no variant files detected\n")
    for a in vcfs:
        md = a.metadata
        primary = " (primary)" if a.asset_id == m.primary_inputs.primary_variant_asset_id else ""
        w(f"**{a.asset_id}**{primary} — {a.detected_format.value}, {_gb(a.size_bytes)}, validation `{a.validation.status.value}`\n")
        if isinstance(md, VcfMetadata):
            w(f"- {_mark(md.header_valid)} header readable ({md.vcf_version or 'version undeclared'}, compression: {md.compression.value})")
            w(f"- {_mark(md.has_records)} first record parses" if md.has_records is not None else "- ? record readability not established")
            w(f"- {_mark(md.index.present and md.index.usable is not False)} index: "
              + (f"{md.index.index_type.value} {md.index.asset_id}" if md.index.present else "missing"))
            w(f"- samples: {md.sample_count} ({', '.join(md.sample_ids) or 'none'})")
            w(f"- genome build: **{md.genome_build.value.value}** (confidence {md.genome_build.confidence.value}); contig naming: {md.genome_build.naming_convention.value}")
            w(f"- declared contigs: {len(md.contigs)}" + (f"; contigs with indexed records: {len(md.contigs_with_records_per_index)}" if md.contigs_with_records_per_index is not None else ""))
            if md.is_gvcf:
                w("- ! gVCF (reference blocks present)")
            for hint in md.processing_hints:
                w(f"- header hint: {hint}")
            if md.source_tools:
                w(f"- producing tools declared in header: {', '.join(md.source_tools)}")
        w("")

    w("## Raw sequencing\n")
    alns = [a for a in m.assets if a.logical_role == LogicalRole.ALIGNED_READS]
    if not alns:
        w("- not supplied\n")
    for a in alns:
        md = a.metadata
        w(f"**{a.asset_id}** — {a.detected_format.value}, {_gb(a.size_bytes)}, validation `{a.validation.status.value}`\n")
        if isinstance(md, AlignmentMetadata):
            w(f"- {_mark(md.header_valid)} header readable; {_mark(md.quickcheck_passed)} integrity quick-check")
            w(f"- sort order: {md.sort_order or 'undeclared'}")
            w(f"- {_mark(md.index.present and md.index.usable is not False)} index: " + (f"{md.index.index_type.value} {md.index.asset_id}" if md.index.present else "missing"))
            w(f"- read groups: {md.read_group_count}; samples: {', '.join(md.sample_ids) or 'none declared'}")
            w(f"- genome build: **{md.genome_build.value.value}** (confidence {md.genome_build.confidence.value}); sequences in dictionary: {len(md.contigs)}")
            if md.cram_reference:
                ok = md.cram_reference.status.value == "available_verified_md5"
                w(f"- {'✓' if ok else '!'} CRAM reference: {md.cram_reference.status.value}"
                  + (f" ({', '.join(md.cram_reference.reference_asset_ids)})" if md.cram_reference.reference_asset_ids else ""))
        w("")

    w("## Reference context\n")
    g = m.reference.genome_build
    w(f"- case genome build: **{g.value.value}** (confidence {g.confidence.value})")
    for ev in g.evidence:
        w(f"  - {ev}")
    for act in g.action_required:
        w(f"  - action: {act}")
    refs = [a for a in m.assets if a.logical_role == LogicalRole.REFERENCE_SEQUENCE]
    for a in refs:
        if isinstance(a.metadata, FastaMetadata):
            w(f"- reference FASTA {a.asset_id}: {len(a.metadata.contigs)} sequences, build {a.metadata.genome_build.value.value}"
              f" ({a.metadata.genome_build.confidence.value}), MD5s computed: {a.metadata.md5_computed}")
    w("")

    w("## Samples\n")
    w(f"{len(m.samples)} distinct sample label(s) observed. Roles (proband/parent) are never inferred.\n")
    for s in m.samples:
        vias = ", ".join(f"{o.asset_id} ({o.via})" for o in s.observed_in)
        extras = []
        if s.asserted_sex:
            extras.append("asserted sex: " + ", ".join(f"{v.value} [{v.source_asset_id}]" for v in s.asserted_sex))
        if s.asserted_affected_status:
            extras.append("asserted status: " + ", ".join(f"{v.value} [{v.source_asset_id}]" for v in s.asserted_affected_status))
        w(f"- **{s.sample_id}** — observed in {vias}" + (f"; {'; '.join(extras)}" if extras else ""))
    w("")

    w("## Phenotype\n")
    p = m.phenotype
    if not p.available:
        w("- ✗ no HPO phenotype artifact detected\n")
    else:
        w(f"- ✓ HPO artifact(s): {', '.join(p.asset_ids)}")
        w(f"- {p.hpo_valid_identifier_count} syntactically valid identifiers ({p.hpo_unique_valid_identifier_count} unique)")
        w(f"- {p.hpo_malformed_identifier_count} malformed identifiers")
        w(f"- polarity stated: {p.observed_count} observed, {p.excluded_count} excluded")
        for aid in p.asset_ids:
            md = by_id[aid].metadata
            if isinstance(md, PhenotypeMetadata):
                w(f"- {aid}: parsed as {md.parser}")
        w("- (syntax only — no ontology validation performed)\n")

    w("## Pedigree\n")
    if m.pedigree.status == "unavailable":
        w("- not supplied (a fact about the case, not an error)\n")
    else:
        w(f"- source(s): {', '.join(m.pedigree.asset_ids)}")
        for r in m.pedigree.relationships:
            w(f"- {r.subject} {r.relation} {r.object} [asserted by {r.source_asset_id}]")
        w("")

    w("## Other assets\n")
    others = [a for a in m.assets if a.logical_role not in (LogicalRole.GENOMIC_VARIANTS, LogicalRole.ALIGNED_READS)]
    if not others:
        w("- none\n")
    else:
        w("| asset | role | detected format | size | validation |")
        w("|---|---|---|---|---|")
        for a in others:
            w(f"| {a.asset_id} | {a.logical_role.value} | {a.detected_format.value} | {_gb(a.size_bytes)} | {a.validation.status.value} |")
        w("")
    if m.relationships:
        w("**Relationships:** " + "; ".join(f"{r.source} {r.type.value} {r.target}" for r in m.relationships) + "\n")

    w("## Issues\n")
    if not m.issues:
        w("None.\n")
    for sev in Severity:
        group = [i for i in m.issues if i.severity == sev]
        if not group:
            continue
        w(f"### {sev.value} ({len(group)})\n")
        for i in group:
            scope = ", ".join(i.asset_ids + i.sample_ids)
            w(f"- **{i.code.value}**" + (f" [{scope}]" if scope else "") + f" — {i.message}")
            for ev in i.evidence[:6]:
                w(f"  - evidence: {ev}")
            if i.suggested_action:
                w(f"  - next action: {i.suggested_action}")
        w("")

    w("## Data governance\n")
    delete = [a for a in m.assets if a.retention_class == RetentionClass.CONTROLLED_GENOMIC_DELETE_REQUIRED]
    review = [a for a in m.assets if a.retention_class == RetentionClass.CONTROLLED_CASE_MATERIAL_REVIEW_REQUIRED]
    w(f"- {len(delete)} asset(s), {_gb(sum(a.size_bytes for a in delete))}: `controlled_genomic_delete_required`")
    w(f"- {len(review)} asset(s): `controlled_case_material_review_required`")
    w("- Intake created no copies of input data. Outputs of this run: private manifest (restricted), sanitized manifest, this report, run log.\n")

    w("## Provenance\n")
    pv = m.provenance
    w(f"- input fingerprint: `{pv.fingerprints.input_fingerprint}`")
    w(f"- inventory fingerprint: `{pv.fingerprints.inventory_fingerprint}`")
    w(f"- rarepipe {pv.software.rarepipe} (commit `{pv.software.source_control.commit}`, dirty={pv.software.source_control.dirty}); "
      f"htslib {pv.software.libraries.get('htslib')}; pysam {pv.software.libraries.get('pysam')}; Python {pv.software.python}")
    w(f"- schema {m.schema_.name} {m.schema_.version}; stage {m.pipeline.stage} {m.pipeline.stage_version}")
    w(f"- run {m.execution.run_id}, {m.execution.started_at} → {m.execution.finished_at}")
    w("")
    return "\n".join(out)
