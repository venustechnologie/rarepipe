"""case_intake stage: case directory → CaseManifest.

Contract
    input:   case_root, case_id, optional configuration
    output:  <output>/<run_id>/{case_manifest.private.json, case_manifest.sanitized.json,
                                intake_report.md, intake.log, SHA256SUMS}
    states:  INTAKE_COMPLETE | INTAKE_COMPLETE_WITH_WARNINGS | INTAKE_BLOCKED

Inputs are opened read-only. No network. No derived files are created.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.hashing import DigestCache, Digests, fingerprint, stream_digest
from rarepipe.core.issues import Issue, IssueCode, Severity, count_by_severity, sort_issues
from rarepipe.core.provenance import software_provenance
from rarepipe.stages.intake import discovery, genomic, pedigree, phenotype, redact, report, validation
from rarepipe.stages.intake.discovery import Discovered
from rarepipe.stages.intake.manifest import (
    AlignmentMetadata,
    AssetRecord,
    CaseManifest,
    CaseRef,
    ChecksumSidecarMetadata,
    Execution,
    FastaMetadata,
    Fingerprints,
    Format,
    IndexStatus,
    IntakeConfiguration,
    InventorySummary,
    LogicalRole,
    PhenotypeSection,
    PrimaryInputs,
    Provenance,
    Readiness,
    Redaction,
    ReferenceSection,
    Status,
    Validation,
    ValidationStatus,
    VcfMetadata,
)

TOTAL_STEPS = 7
PROGRESS_MIN_BYTES = 64 * 1024 * 1024
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NOT_INSPECTED_ROLES = {LogicalRole.UNKNOWN, LogicalRole.DOCUMENTATION, LogicalRole.CASE_METADATA, LogicalRole.SYSTEM_FILE}
PRIVATE_MANIFEST = "case_manifest.private.json"
SANITIZED_MANIFEST = "case_manifest.sanitized.json"
REPORT = "intake_report.md"
LOG = "intake.log"


class IntakeUsageError(ValueError):
    """Invalid invocation (not a data problem — data problems become Issues)."""


@dataclass
class IntakeRequest:
    case_root: Path
    case_id: str
    output: Path
    exclude_globs: list[str] = field(default_factory=list)
    primary_variant_asset: str | None = None
    references: list[Path] = field(default_factory=list)
    checksum_cache: bool = True
    argv: list[str] = field(default_factory=list)


@dataclass
class IntakeResult:
    manifest: CaseManifest
    sanitized: CaseManifest
    run_dir: Path


@contextlib.contextmanager
def network_safe_htslib():
    """htslib fetches CRAM references from EBI when REF_PATH is unset. Intake never decodes
    CRAM slices, but the environment is pinned anyway so no code path can reach the network."""
    keys = ("REF_PATH", "REF_CACHE")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["REF_PATH"] = os.environ["REF_CACHE"] = "/nonexistent/rarepipe-no-network-reference-lookup"
    try:
        yield ["REF_PATH/REF_CACHE pinned to a nonexistent local path (disables htslib's EBI CRAM reference download)"]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _validate_request(req: IntakeRequest) -> None:
    if not CASE_ID_RE.match(req.case_id):
        raise IntakeUsageError("case-id must be 1–64 characters of letters, digits, '.', '_' or '-'.")
    if not req.case_root.is_dir():
        raise IntakeUsageError("case-root does not exist or is not a directory.")
    root, out = req.case_root.resolve(), req.output.resolve()
    if out == root or out.is_relative_to(root):
        raise IntakeUsageError("output must be outside case-root (intake never writes into the case).")
    for ref in req.references:
        if not ref.is_file():
            raise IntakeUsageError(f"--reference is not a file: {ref.name}")


def _worst(issues: list[Issue]) -> Severity | None:
    return min((i.severity for i in issues), key=lambda s: s.rank, default=None)


def _semantic_digest(m: CaseManifest) -> str:
    data = m.model_dump(mode="json", by_alias=True, exclude={"execution", "semantic_digest"})
    return "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def run_intake(req: IntakeRequest, console: Console | None = None) -> IntakeResult:
    console = console or Console()
    _validate_request(req)
    started = utc_now()
    t0 = time.monotonic()
    run_id = new_run_id(started)
    with network_safe_htslib() as env_controls:
        manifest = _run(req, console, run_id, started, t0, env_controls)
    sanitized = redact.sanitize(manifest)
    sanitized.semantic_digest = _semantic_digest(sanitized)

    console.step(7, TOTAL_STEPS, "Writing CaseManifest...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(PRIVATE_MANIFEST, canonical_json(manifest))
    run.write_text(SANITIZED_MANIFEST, canonical_json(sanitized))
    run.write_text(REPORT, report.render(sanitized))
    console.ok(f"run {run_id}: private manifest, sanitized manifest, report, log")
    console.line()
    console.line(manifest.status.value)
    if manifest.readiness.normalization_ready:
        console.line("\nNext stage:\nInput Normalization")
    counts = manifest.issue_counts
    if counts["BLOCKER"]:
        console.line(f"\n{counts['BLOCKER']} blocker(s) must be resolved.")
    if counts["ACTION_REQUIRED"]:
        console.line(f"{counts['ACTION_REQUIRED']} action(s) require review.")
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    run_dir = run.seal()
    return IntakeResult(manifest=manifest, sanitized=sanitized, run_dir=run_dir)


def _run(req: IntakeRequest, console: Console, run_id: str, started, t0: float, env_controls: list[str]) -> CaseManifest:
    issues: list[Issue] = []

    # ── 1. discovery ────────────────────────────────────────────────────────
    console.step(1, TOTAL_STEPS, "Discovering assets...")
    assets, disc_issues = discovery.discover(req.case_root, req.exclude_globs, req.references)
    issues += disc_issues
    for a in assets:
        issues += a.issues
        discovery.assign_role(a, phenotype.looks_like_phenotype(a.path, a.fmt))
    by_id: dict[str, Discovered] = {a.asset_id: a for a in assets}
    links, link_issues = discovery.link(assets)
    issues += link_issues
    total_bytes = sum(a.size for a in assets)
    console.info(f"{len(assets)} files found ({total_bytes / 1e9:.2f} GB)")
    for a in assets:
        issues += _format_issues(a)
    roles = {}
    for a in assets:
        roles[a.role.value] = roles.get(a.role.value, 0) + 1
    console.info("roles: " + ", ".join(f"{n} {r}" for r, n in sorted(roles.items())))

    metas: dict[str, object] = {}
    labels_vcf: dict[str, list[str]] = {}
    labels_aln: dict[str, list[str]] = {}
    vcf_ped_pairs: dict[str, list[tuple[str, str]]] = {}

    def index_for(a: Discovered) -> tuple[IndexStatus, Path | None]:
        idx_id = links.index_of.get(a.asset_id)
        if not idx_id:
            return IndexStatus(present=False), None
        idx = by_id[idx_id]
        return IndexStatus(present=True, index_type=idx.fmt, asset_id=idx_id), idx.path

    # ── 2. variants ─────────────────────────────────────────────────────────
    console.step(2, TOTAL_STEPS, "Inspecting variant files...")
    vcfs = [a for a in assets if a.role == LogicalRole.GENOMIC_VARIANTS]
    if not vcfs:
        console.warn("no VCF/BCF detected")
    for a in vcfs:
        idx, idx_path = index_for(a)
        res = genomic.inspect_vcf(a.path, a.asset_id, a.fmt, a.sniff.compression, a.sniff.bgzf_eof_present, idx, idx_path)
        metas[a.asset_id], labels_vcf[a.asset_id] = res.metadata, res.sample_labels
        issues += res.issues
        md: VcfMetadata = res.metadata
        (console.ok if md.header_valid else console.fail)(f"{a.asset_id}: {a.fmt.value} header {'readable' if md.header_valid else 'NOT readable'}")
        if md.header_valid:
            console.info(f"  {md.sample_count} sample(s); build {md.genome_build.value.value} ({md.genome_build.confidence.value}); "
                         f"index {'present' if idx.present else 'MISSING'}")
            vcf_ped_pairs[a.asset_id] = pedigree.vcf_pedigree_pairs(a.path)

    # ── 3. alignments + reference ───────────────────────────────────────────
    console.step(3, TOTAL_STEPS, "Inspecting alignment and reference files...")
    alns = [a for a in assets if a.role == LogicalRole.ALIGNED_READS]
    crams = [a for a in alns if a.fmt == Format.CRAM]
    if not alns:
        console.info("no BAM/CRAM supplied")
    fastas: dict[str, FastaMetadata] = {}
    for a in assets:
        if a.role == LogicalRole.REFERENCE_SEQUENCE:
            idx, _ = index_for(a)
            fai = by_id[links.index_of[a.asset_id]].path if a.asset_id in links.index_of else None
            dct = by_id[links.dict_of[a.asset_id]].path if a.asset_id in links.dict_of else None
            if crams:
                console.info(f"  {a.asset_id}: streaming FASTA to compute per-sequence MD5 (needed to verify CRAM reference)")
            res = genomic.inspect_fasta(a.path, a.asset_id, a.sniff.compression, idx, fai, dct, want_md5=bool(crams))
            metas[a.asset_id] = res.metadata
            fastas[a.asset_id] = res.metadata
            issues += res.issues
            console.ok(f"{a.asset_id}: reference FASTA, {len(res.metadata.contigs)} sequences, build {res.metadata.genome_build.value.value}")
        elif a.role == LogicalRole.SEQUENCE_DICTIONARY:
            res = genomic.inspect_sequence_dictionary(a.path, a.asset_id)
            metas[a.asset_id] = res.metadata
    for a in alns:
        idx, idx_path = index_for(a)
        res = genomic.inspect_alignments(a.path, a.asset_id, a.fmt, a.sniff.bgzf_eof_present, idx, idx_path)
        metas[a.asset_id], labels_aln[a.asset_id] = res.metadata, res.sample_labels
        issues += res.issues
        md: AlignmentMetadata = res.metadata
        if not md.header_valid:
            console.fail(f"{a.asset_id}: {a.fmt.value} header NOT readable")
            continue
        (console.ok if md.quickcheck_passed else console.fail)(f"{a.asset_id}: {a.fmt.value} {'passes' if md.quickcheck_passed else 'FAILS'} integrity quick-check")
        console.info(f"  build {md.genome_build.value.value} ({md.genome_build.confidence.value}); {md.read_group_count} read group(s); index {'present' if idx.present else 'MISSING'}")
        if a.fmt == Format.CRAM:
            cram_ref, rels, ref_issues = validation.resolve_cram_reference(a.asset_id, md, res.reference_uris, fastas)
            md.cram_reference = cram_ref
            links.relationships += rels
            issues += ref_issues
            (console.ok if cram_ref.status.value == "available_verified_md5" else console.warn)(f"  CRAM reference: {cram_ref.status.value}")

    # ── 4. phenotype + pedigree ─────────────────────────────────────────────
    console.step(4, TOTAL_STEPS, "Inspecting phenotype and pedigree data...")
    pheno_ids = []
    for a in assets:
        if a.role == LogicalRole.PHENOTYPE_TERMS:
            md, p_issues = phenotype.inspect_phenotype(a.path, a.asset_id, a.fmt)
            issues += p_issues
            if md:
                metas[a.asset_id] = md
                pheno_ids.append(a.asset_id)
                console.ok(f"{a.asset_id}: HPO artifact; {md.valid_term_count} valid, {md.malformed_identifier_count} malformed identifier(s)")
    if not pheno_ids:
        console.warn("no HPO phenotype artifact detected")
    parsed_peds = {}
    for a in assets:
        if a.role == LogicalRole.PEDIGREE:
            ped = pedigree.parse_ped(a.path, a.asset_id)
            parsed_peds[a.asset_id] = ped
            issues += ped.issues
            console.ok(f"{a.asset_id}: pedigree with {len(ped.rows)} individual(s)")
    if not parsed_peds and not any(vcf_ped_pairs.values()):
        console.info("no pedigree supplied")

    # ── 5. checksums ────────────────────────────────────────────────────────
    console.step(5, TOTAL_STEPS, "Computing SHA-256 content digests (streaming)...")
    cache = DigestCache(req.output / ".cache" / "checksums.json" if req.checksum_cache else None)
    md5_wanted = {t for t, s in links.sidecar_of.items() if by_id[s].fmt == Format.CHECKSUM_MD5}
    digests: dict[str, Digests] = {}
    for a in assets:
        want_md5 = a.asset_id in md5_wanted
        cached = cache.get(a.rel, a.stat, want_md5)
        if cached:
            digests[a.asset_id] = cached
            continue
        progress = (lambda d, t, _id=a.asset_id: console.progress(_id, d, t)) if a.size >= PROGRESS_MIN_BYTES else None
        digests[a.asset_id] = stream_digest(a.path, want_md5=want_md5, progress=progress)
        cache.put(a.rel, a.stat, digests[a.asset_id])
    console.ok(f"{len(digests)} digest(s) ({cache.hits} resumed from cache)")
    for target_id, sidecar_id in sorted(links.sidecar_of.items()):
        sc = by_id[sidecar_id]
        algo = "md5" if sc.fmt == Format.CHECKSUM_MD5 else "sha256"
        expected = discovery.read_sidecar_digest(sc.path, algo)
        actual = digests[target_id].md5 if algo == "md5" else digests[target_id].sha256
        verified = None if expected is None else expected == actual
        metas[sidecar_id] = ChecksumSidecarMetadata(algorithm=algo, target_asset_id=target_id, verified=verified)
        if expected is None:
            issues.append(Issue(code=IssueCode.CHECKSUM_SIDECAR_UNPARSEABLE, severity=Severity.WARNING, asset_ids=[sidecar_id],
                                message=f"{algo.upper()} sidecar does not contain a parseable digest."))
        elif not verified:
            target = by_id[target_id]
            primary = target.role in (LogicalRole.GENOMIC_VARIANTS, LogicalRole.ALIGNED_READS)
            issues.append(Issue(code=IssueCode.CHECKSUM_SIDECAR_MISMATCH, severity=Severity.BLOCKER if primary else Severity.ACTION_REQUIRED,
                                asset_ids=[target_id, sidecar_id], message=f"File content does not match its supplied {algo.upper()} checksum; it may be corrupt or a different file.",
                                suggested_action="Re-transfer the file from the source and re-run intake."))
            console.fail(f"{target_id}: {algo.upper()} sidecar mismatch")
        else:
            console.ok(f"{target_id}: matches supplied {algo.upper()} checksum")

    # ── 6. cross-validation ─────────────────────────────────────────────────
    console.step(6, TOTAL_STEPS, "Cross-validating metadata...")
    registry = validation.SampleRegistry()
    for a in assets:  # sorted discovery order → deterministic SAMPLE_nnn
        for label in labels_vcf.get(a.asset_id, []):
            registry.observe(label, a.asset_id, "vcf_sample_column")
        for label in labels_aln.get(a.asset_id, []):
            registry.observe(label, a.asset_id, "read_group_SM")
    ped_section, ped_metas = validation.pedigree_section(registry, parsed_peds, vcf_ped_pairs)
    metas.update(ped_metas)
    for aid, labels in labels_vcf.items():
        metas[aid].sample_ids = [registry.id_of(l) for l in labels]
    for aid, labels in labels_aln.items():
        md = metas[aid]
        md.sample_ids = [registry.id_of(l) for l in labels]
        for rg in md.read_groups:
            rg.sample_id = registry.id_of(rg.source_sample_label) if rg.source_sample_label is not None else None
    ped_labels = {aid: [r.individual for r in p.rows] for aid, p in parsed_peds.items()}
    issues += validation.sample_consistency(registry, labels_vcf, labels_aln, ped_labels)
    console.info(f"{len(registry.samples)} distinct sample label(s) observed")

    entries = validation.reference_entries(metas)
    for e in entries:
        if e.fmt in (Format.VCF, Format.BCF, Format.BAM, Format.CRAM, Format.SAM, Format.FASTA):
            issues += validation.per_asset_build_issues(e.asset_id, e.fmt, e.call)
    case_build, per_asset_builds, ref_issues = validation.reference_consistency(entries)
    issues += ref_issues
    (console.fail if any(i.severity == Severity.BLOCKER for i in ref_issues) else console.ok)(
        f"case genome build: {case_build.value.value} ({case_build.confidence.value})")

    primary, primary_issues = _primary_inputs(req, assets, pheno_ids, ped_section)
    issues += primary_issues
    if not pheno_ids:
        issues.append(Issue(code=IssueCode.PHENOTYPE_UNAVAILABLE, severity=Severity.WARNING, message="No HPO phenotype artifact was identified in the case.",
                            suggested_action="Confirm whether phenotype data was supplied under an unrecognized format."))
    if ped_section.status == "unavailable":
        issues.append(Issue(code=IssueCode.PEDIGREE_UNAVAILABLE, severity=Severity.INFO, message="No pedigree information supplied; no family relationships are asserted."))

    # ── assemble ────────────────────────────────────────────────────────────
    issues = sort_issues(issues)
    counts = count_by_severity(issues)
    records = []
    for a in assets:
        own = [i for i in issues if a.asset_id in i.asset_ids]
        restricted_, retention = discovery.retention(a)
        worst = _worst(own)
        if a.role in NOT_INSPECTED_ROLES:
            status = ValidationStatus.NOT_INSPECTED
        else:
            status = {Severity.BLOCKER: ValidationStatus.INVALID, Severity.ACTION_REQUIRED: ValidationStatus.REQUIRES_ACTION,
                      Severity.WARNING: ValidationStatus.VALID_WITH_WARNINGS}.get(worst, ValidationStatus.VALID)
        records.append(AssetRecord(
            asset_id=a.asset_id, relative_path=a.rel, filename=a.filename, extension=a.extension, extension_format=a.ext_fmt,
            detected_format=a.fmt, compression=a.sniff.compression, size_bytes=a.size, checksum_sha256=digests[a.asset_id].sha256,
            logical_role=a.role, restricted=restricted_, retention_class=retention, external=a.external, metadata=metas.get(a.asset_id),
            validation=Validation(status=status, issue_codes=sorted({i.code.value for i in own})),
        ))

    blockers = sorted({i.code.value for i in issues if i.severity == Severity.BLOCKER})
    actions = sorted({i.code.value for i in issues if i.severity == Severity.ACTION_REQUIRED})
    if blockers:
        status = Status.INTAKE_BLOCKED
        rationale = f"{len(blockers)} blocking condition(s): the case cannot safely proceed until resolved."
    elif actions or counts["WARNING"]:
        status = Status.INTAKE_COMPLETE_WITH_WARNINGS
        rationale = ("No blockers. Normalization may proceed, but "
                     + (f"{counts['ACTION_REQUIRED']} item(s) require a human decision and " if actions else "")
                     + f"{counts['WARNING']} warning(s) must be carried forward.")
    else:
        status = Status.INTAKE_COMPLETE
        rationale = "No blockers, actions or warnings. The case's technical shape is fully described."

    config = IntakeConfiguration(case_root=str(req.case_root.resolve()), exclude_globs=req.exclude_globs, primary_variant_asset=req.primary_variant_asset,
                                 external_references=[str(r.resolve()) for r in req.references])
    by_role, by_format = {}, {}
    for r in records:
        by_role[r.logical_role.value] = by_role.get(r.logical_role.value, 0) + 1
        by_format[r.detected_format.value] = by_format.get(r.detected_format.value, 0) + 1
    finished = utc_now()
    manifest = CaseManifest(
        redaction=Redaction(visibility="private", note=redact.PRIVATE_NOTE),
        case=CaseRef(case_id=req.case_id),
        status=status,
        readiness=Readiness(normalization_ready=not blockers, blockers=blockers, actions_required=actions, rationale=rationale),
        inventory=InventorySummary(asset_count=len(records), total_size_bytes=total_bytes, by_role=dict(sorted(by_role.items())), by_format=dict(sorted(by_format.items()))),
        primary_inputs=primary,
        assets=records,
        relationships=sorted(links.relationships, key=lambda r: (r.type.value, r.source, r.target)),
        samples=registry.samples,
        phenotype=_phenotype_section(pheno_ids, metas),
        pedigree=ped_section,
        reference=ReferenceSection(genome_build=case_build, per_asset=per_asset_builds),
        issues=issues,
        issue_counts=counts,
        provenance=Provenance(
            software=software_provenance(),
            configuration=config,
            fingerprints=Fingerprints(
                input_fingerprint=fingerprint([d.sha256 for d in digests.values()]),
                inventory_fingerprint=fingerprint([f"{by_id[i].rel}\t{d.sha256}" for i, d in digests.items()]),
                configuration_digest="sha256:" + hashlib.sha256(config.model_dump_json().encode()).hexdigest(),
            ),
            environment_controls=env_controls + ["inputs opened read-only; no derived files created", "no network access performed by intake"],
        ),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=finished.isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3),
                            checksum_cache_enabled=req.checksum_cache, checksum_cache_hits=cache.hits, argv=req.argv),
    )
    manifest.semantic_digest = _semantic_digest(manifest)
    return manifest


def _format_issues(a: Discovered) -> list[Issue]:
    from rarepipe.stages.intake import formats

    issues = []
    if a.fmt == Format.EMPTY:
        issues.append(Issue(code=IssueCode.EMPTY_FILE, severity=Severity.WARNING, asset_ids=[a.asset_id], message="File is empty."))
    if formats.is_mismatch(a.ext_fmt, a.fmt):
        claims_genomic = a.ext_fmt in discovery.GENOMIC
        is_genomic = a.fmt in discovery.GENOMIC
        if claims_genomic and not is_genomic:
            issues.append(Issue(code=IssueCode.FORMAT_EXTENSION_MISMATCH, severity=Severity.BLOCKER, asset_ids=[a.asset_id],
                                message=f"Filename indicates {a.ext_fmt.value} but content is not readable as {a.ext_fmt.value} (detected: {a.fmt.value}).",
                                suggested_action="Verify the file is complete and uncorrupted; intake does not reinterpret it."))
        else:
            issues.append(Issue(code=IssueCode.FORMAT_EXTENSION_MISMATCH, severity=Severity.WARNING, asset_ids=[a.asset_id],
                                message=f"Filename indicates {a.ext_fmt.value} but content is {a.fmt.value}; content-detected format is recorded.",
                                suggested_action="Rename at the source to avoid downstream confusion."))
    if a.role == LogicalRole.UNKNOWN and a.fmt != Format.EMPTY:
        issues.append(Issue(code=IssueCode.UNKNOWN_FILE, severity=Severity.WARNING, asset_ids=[a.asset_id],
                            message=f"File role could not be determined (detected content: {a.fmt.value}). Recorded, not interpreted.",
                            suggested_action="Confirm whether this file belongs to the case."))
    if a.role == LogicalRole.CASE_METADATA:
        issues.append(Issue(code=IssueCode.ADDITIONAL_METADATA_DETECTED, severity=Severity.INFO, asset_ids=[a.asset_id],
                            message=f"Additional {a.fmt.value} metadata file detected; recorded but not interpreted by intake."))
    return issues


def _primary_inputs(req: IntakeRequest, assets: list[Discovered], pheno_ids: list[str], ped) -> tuple[PrimaryInputs, list[Issue]]:
    issues = []
    variants = [a for a in assets if a.role == LogicalRole.GENOMIC_VARIANTS]
    alns = [a for a in assets if a.role == LogicalRole.ALIGNED_READS]
    primary_id, selection = None, "none"
    if req.primary_variant_asset:
        match = [a for a in variants if a.rel == req.primary_variant_asset]
        if match:
            primary_id, selection = match[0].asset_id, "configured"
        else:
            issues.append(Issue(code=IssueCode.CONFIGURED_ASSET_NOT_FOUND, severity=Severity.ACTION_REQUIRED,
                                message="The configured primary variant asset is not a variant file in this case.",
                                suggested_action="Check the --primary-variant relative path."))
    if selection == "none":
        if len(variants) == 1:
            primary_id, selection = variants[0].asset_id, "only_candidate"
        elif len(variants) > 1:
            selection = "ambiguous"
            issues.append(Issue(code=IssueCode.PRIMARY_VARIANT_ASSET_AMBIGUOUS, severity=Severity.ACTION_REQUIRED, asset_ids=[a.asset_id for a in variants],
                                message=f"{len(variants)} variant files are present; which one downstream analysis should use is not established.",
                                suggested_action="Re-run with --primary-variant <relative path> once the intended file is confirmed."))
    if not variants and not alns:
        issues.append(Issue(code=IssueCode.PRIMARY_GENOMIC_INPUT_MISSING, severity=Severity.BLOCKER,
                            message="No readable-format variant (VCF/BCF) or alignment (BAM/CRAM) file was identified.",
                            suggested_action="Confirm the case root and that genomic files were fully transferred."))
    elif not variants:
        issues.append(Issue(code=IssueCode.VARIANT_CALLS_ABSENT, severity=Severity.WARNING, asset_ids=[a.asset_id for a in alns],
                            message="Alignments are present but no variant calls; a variant-calling stage would be required."))
    elif alns:
        issues.append(Issue(code=IssueCode.OPTIONAL_ALIGNMENTS_SUPPLIED, severity=Severity.INFO, asset_ids=[a.asset_id for a in alns],
                            message=f"{len(alns)} alignment file(s) supplied in addition to variant calls."))
    return PrimaryInputs(
        variant_asset_ids=[a.asset_id for a in variants], primary_variant_asset_id=primary_id, primary_variant_selection=selection,
        alignment_asset_ids=[a.asset_id for a in alns],
        reference_sequence_asset_ids=[a.asset_id for a in assets if a.role == LogicalRole.REFERENCE_SEQUENCE],
        phenotype_asset_ids=pheno_ids, pedigree_asset_ids=ped.asset_ids,
    ), issues


def _phenotype_section(pheno_ids: list[str], metas: dict) -> PhenotypeSection:
    ms = [metas[i] for i in pheno_ids]
    unique = set()
    for m in ms:
        unique |= {t.id for t in m.terms}
    return PhenotypeSection(
        available=bool(ms), asset_ids=pheno_ids,
        hpo_valid_identifier_count=sum(m.valid_term_count for m in ms),
        hpo_unique_valid_identifier_count=len(unique),
        hpo_malformed_identifier_count=sum(m.malformed_identifier_count for m in ms),
        observed_count=sum(m.observed_count for m in ms), excluded_count=sum(m.excluded_count for m in ms),
    )
