"""case_normalization stage: CaseManifest (+ optional CaseAssertions, pinned resources) → NormalizedCase.

Contract
    input:   a *private* CaseManifest (the only description of the case this stage trusts),
             the assets it declares, a pinned resources directory, optional CaseAssertions
    output:  <output>/<run_id>/{normalized_case.private.json, normalized_case.sanitized.json,
                                normalization_report.md, normalization.log, SHA256SUMS}
    states:  NORMALIZATION_COMPLETE | NORMALIZATION_COMPLETE_WITH_WARNINGS | NORMALIZATION_BLOCKED

Never: walks the case directory, opens FASTQs, fetches resources, rewrites/filters the VCF,
aligns, calls, phases, annotates or prioritizes.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.issues import Severity
from rarepipe.core.provenance import software_provenance
from rarepipe.core.redaction import clear_restricted
from rarepipe.resources import lock as reslock
from rarepipe.resources.assembly import load_assembly_report
from rarepipe.resources.hpo import load_obo, release_date
from rarepipe.stages.intake.manifest import CaseManifest, FastqMetadata, PhenotypeMetadata, VcfMetadata
from rarepipe.stages.intake.stage import network_safe_htslib
from rarepipe.stages.normalize import contigs as contig_layer
from rarepipe.stages.normalize import readiness, report, upstream, vcf_scan
from rarepipe.stages.normalize.assertions import CaseAssertions
from rarepipe.stages.normalize.model import (
    SUPPORTED_MANIFEST_MAJOR,
    AnalysisReference,
    AppliedAssertion,
    CarriedIssue,
    Execution,
    FilterCharacterization,
    FormatFieldStat,
    GenomeSection,
    GenotypeStates,
    LanePair,
    NormalizedCase,
    NormIssueCode,
    Operation,
    PedigreeSection,
    PhaseInformation,
    PhenotypeSection,
    Provenance,
    RawReadsSection,
    ReferenceBinding,
    ResourceRef,
    Retention,
    SampleIdentity,
    SampleLinkage,
    SourceManifest,
    Status,
    VcfCharacterization,
    VerifiedAsset,
)
from rarepipe.stages.normalize.phenotype import normalize_term

TOTAL_STEPS = 7
PRIVATE = "normalized_case.private.json"
SANITIZED = "normalized_case.sanitized.json"
REPORT = "normalization_report.md"
LOG = "normalization.log"


class NormalizeUsageError(ValueError):
    """Invalid invocation or unusable input artifact (data problems become issues)."""


@dataclass
class NormalizeRequest:
    manifest: Path
    output: Path
    resources: Path | None = None
    assertions: Path | None = None
    case_root: Path | None = None
    argv: list[str] = field(default_factory=list)


@dataclass
class NormalizeResult:
    case: NormalizedCase
    sanitized: NormalizedCase
    run_dir: Path


def _issue(code: NormIssueCode, severity: Severity, message: str, **kw) -> CarriedIssue:
    return CarriedIssue(code=code.value, severity=severity, origin_stage="case_normalization",
                        resolution="informational" if severity == Severity.INFO else "unresolved", message=message, **kw)


def _semantic_digest(case: NormalizedCase) -> str:
    data = case.model_dump(mode="json", by_alias=True, exclude={"execution", "semantic_digest"})
    return "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _load_manifest(req: NormalizeRequest) -> tuple[CaseManifest, bytes]:
    if not req.manifest.is_file():
        raise NormalizeUsageError("manifest file does not exist.")
    raw = req.manifest.read_bytes()
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise NormalizeUsageError("manifest is not valid JSON.") from exc
    schema = data.get("schema", {})
    if schema.get("name") != "CaseManifest" or str(schema.get("version", "")).split(".")[0] != SUPPORTED_MANIFEST_MAJOR:
        raise NormalizeUsageError(f"unsupported artifact: expected CaseManifest {SUPPORTED_MANIFEST_MAJOR}.x.")
    try:
        manifest = CaseManifest.model_validate(data)
    except ValidationError as exc:
        raise NormalizeUsageError(f"manifest does not validate against CaseManifest ({exc.error_count()} error(s)).") from exc
    if manifest.redaction.visibility != "private":
        raise NormalizeUsageError("a sanitized manifest cannot be normalized (it has no asset locations); pass case_manifest.private.json.")
    return manifest, raw


def run_normalize(req: NormalizeRequest, console: Console | None = None) -> NormalizeResult:
    console = console or Console()
    manifest, raw = _load_manifest(req)
    case_root = (req.case_root or Path(manifest.provenance.configuration.case_root or "")).resolve()
    out = req.output.resolve()
    if out.is_relative_to(case_root) or out.is_relative_to(req.manifest.resolve().parent):
        raise NormalizeUsageError("output must be outside the case root and outside the Stage 01 run directory.")
    if req.resources and not req.resources.is_dir():
        raise NormalizeUsageError("--resources is not a directory.")
    assertions = None
    assertions_sha = None
    if req.assertions:
        try:
            araw = req.assertions.read_bytes()
            assertions = CaseAssertions.model_validate_json(araw)
            assertions_sha = hashlib.sha256(araw).hexdigest()
        except (OSError, ValidationError) as exc:
            raise NormalizeUsageError(f"assertions file is not a valid CaseAssertions artifact ({type(exc).__name__}).") from exc

    started = utc_now()
    t0 = time.monotonic()
    run_id = new_run_id(started)
    with network_safe_htslib() as env_controls:
        case = _run(req, console, manifest, raw, case_root, assertions, assertions_sha, run_id, started, t0, env_controls)
    sanitized = case.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = _semantic_digest(sanitized)

    console.step(7, TOTAL_STEPS, "Writing NormalizedCase...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(PRIVATE, canonical_json(case))
    run.write_text(SANITIZED, canonical_json(sanitized))
    run.write_text(REPORT, report.render(sanitized))
    console.ok(f"run {run_id}: private + sanitized NormalizedCase, report, log")
    console.line()
    console.line(case.status.value)
    ready = [c.capability for c in case.readiness if c.ready in ("yes", "partial")]
    console.line("\nCapabilities ready: " + (", ".join(ready) if ready else "none"))
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return NormalizeResult(case=case, sanitized=sanitized, run_dir=run.seal())


def _run(req, console, manifest: CaseManifest, raw: bytes, case_root: Path, assertions: CaseAssertions | None, assertions_sha,
         run_id, started, t0, env_controls) -> NormalizedCase:
    issues: list[CarriedIssue] = []
    ops: list[Operation] = []
    assets = {a.asset_id: a for a in manifest.assets}

    # ── 1. upstream manifest ────────────────────────────────────────────────
    console.step(1, TOTAL_STEPS, "Loading CaseManifest...")
    seal = upstream.seal_status(req.manifest)
    source = SourceManifest(schema_version=manifest.schema_.version, stage_version=manifest.pipeline.stage_version, run_id=manifest.execution.run_id,
                            intake_status=manifest.status.value, manifest_sha256=hashlib.sha256(raw).hexdigest(),
                            semantic_digest=manifest.semantic_digest, input_fingerprint=manifest.provenance.fingerprints.input_fingerprint,
                            seal_verified=seal, path=str(req.manifest.resolve()))
    if seal is False:
        issues.append(_issue(NormIssueCode.UPSTREAM_SEAL_MISMATCH, Severity.BLOCKER, "CaseManifest bytes do not match the Stage 01 run seal (SHA256SUMS); it was modified after intake.",
                             suggested_action="Re-run Stage 01; never edit pipeline artifacts."))
    elif seal is None:
        issues.append(_issue(NormIssueCode.UPSTREAM_SEAL_UNAVAILABLE, Severity.WARNING, "No Stage 01 run seal found next to the manifest; its integrity cannot be confirmed."))
    upstream_blocked = manifest.status.value == "INTAKE_BLOCKED"
    if upstream_blocked:
        issues.append(_issue(NormIssueCode.UPSTREAM_INTAKE_BLOCKED, Severity.BLOCKER, "Stage 01 ended INTAKE_BLOCKED; its blockers must be resolved and intake re-run first."))
    for i in manifest.issues:
        issues.append(CarriedIssue(code=i.code.value, severity=i.severity, origin_stage="case_intake",
                                   resolution="informational" if i.severity == Severity.INFO else "unresolved",
                                   message=i.message, asset_ids=i.asset_ids, sample_ids=i.sample_ids, evidence=i.evidence, suggested_action=i.suggested_action))
    console.ok(f"CaseManifest {source.schema_version} from run {source.run_id}: {source.intake_status}; seal "
               + {True: "verified", False: "MISMATCH", None: "unavailable"}[seal])
    console.info(f"{len(manifest.issues)} Stage 01 issue(s) carried forward")

    # ── 2. resources ────────────────────────────────────────────────────────
    console.step(2, TOTAL_STEPS, "Verifying pinned resources (no network)...")
    resources: list[ResourceRef] = []
    hpo_ref = asm_ref = None
    lock = reslock.load_lock(req.resources) if req.resources else None
    if req.resources and lock is None:
        issues.append(_issue(NormIssueCode.RESOURCE_LOCK_MISSING, Severity.ACTION_REQUIRED, "Resources directory has no resources.lock.json; no resource can be trusted."))
    for entry in (lock.resources if lock else []):
        status = reslock.verify(req.resources, entry)
        ref = ResourceRef(kind=entry.kind.value, name=entry.name, version=entry.version, sha256=entry.sha256, size_bytes=entry.size_bytes,
                          source_url=entry.source_url, retrieved_at=entry.retrieved_at, status=status, path=str((req.resources / entry.path).resolve()))
        resources.append(ref)
        if status == "missing":
            issues.append(_issue(NormIssueCode.RESOURCE_MISSING, Severity.ACTION_REQUIRED, f"Pinned resource '{entry.name}' {entry.version} is missing from the resources directory."))
        elif status == "checksum_mismatch":
            issues.append(_issue(NormIssueCode.RESOURCE_CHECKSUM_MISMATCH, Severity.BLOCKER,
                                 f"Pinned resource '{entry.name}' {entry.version} does not match its locked SHA-256; refusing to use it.",
                                 suggested_action="Restore the exact pinned file or re-provision and re-lock deliberately."))
        elif entry.kind.value == "hpo_ontology" and hpo_ref is None:
            hpo_ref = ref
        elif entry.kind.value == "assembly_report" and asm_ref is None:
            asm_ref = ref
        (console.ok if status == "verified" else console.fail)(f"{entry.kind.value}: {entry.version} ({status})")
    if not resources:
        console.warn("no pinned resources supplied")

    # ── 3. assertions ───────────────────────────────────────────────────────
    console.step(3, TOTAL_STEPS, "Loading case assertions...")
    applied: list[AppliedAssertion] = []
    active_assertions = []
    if assertions is None:
        console.info("none supplied (unknown remains a legitimate state)")
    elif assertions.case_id != manifest.case.case_id:
        issues.append(_issue(NormIssueCode.ASSERTIONS_CASE_MISMATCH, Severity.BLOCKER, "CaseAssertions belong to a different case_id; none were applied."))
    else:
        active_assertions = assertions.assertions
        console.info(f"{len(active_assertions)} assertion(s) supplied")

    # ── 4. verify declared source assets ────────────────────────────────────
    console.step(4, TOTAL_STEPS, "Verifying declared source assets against Stage 01 digests...")
    pi = manifest.primary_inputs
    vcf_id = pi.primary_variant_asset_id
    if vcf_id is None and pi.variant_asset_ids:
        issues.append(_issue(NormIssueCode.PRIMARY_VARIANT_ASSET_UNRESOLVED, Severity.BLOCKER, "Stage 01 found several variant files and none was designated primary.",
                             asset_ids=pi.variant_asset_ids, suggested_action="Re-run intake with --primary-variant."))
    to_verify: list[tuple[str, str]] = []
    if vcf_id:
        to_verify.append((vcf_id, "primary_variants"))
        vmeta = assets[vcf_id].metadata
        if isinstance(vmeta, VcfMetadata) and vmeta.index.asset_id:
            to_verify.append((vmeta.index.asset_id, "variant_index"))
    to_verify += [(aid, "phenotype") for aid in pi.phenotype_asset_ids]
    verified: list[VerifiedAsset] = []
    ok_ids: set[str] = set()
    for aid, role in to_verify:
        a = assets[aid]
        path = case_root / (a.relative_path or "")
        if not path.is_file():
            status = "missing"
            issues.append(_issue(NormIssueCode.SOURCE_ASSET_MISSING, Severity.BLOCKER, f"Declared {role} asset is not at its manifest location.", asset_ids=[aid],
                                 suggested_action="Mount the case at its original location or pass --case-root."))
        elif path.stat().st_size != a.size_bytes or reslock.sha256_file(path) != a.checksum_sha256:
            status = "changed"
            issues.append(_issue(NormIssueCode.SOURCE_ASSET_CHANGED, Severity.BLOCKER, f"Declared {role} asset no longer matches its Stage 01 SHA-256.", asset_ids=[aid],
                                 suggested_action="Inputs changed since intake: re-run Stage 01, then Stage 02."))
        else:
            status = "verified"
            ok_ids.add(aid)
        verified.append(VerifiedAsset(asset_id=aid, role=role, expected_sha256=a.checksum_sha256 or "", status=status))
        (console.ok if status == "verified" else console.fail)(f"{aid} ({role}): {status}")
    ops.append(Operation(operation="verify_source_assets", inputs=[a for a, _ in to_verify], parameters={"method": "sha256 vs CaseManifest"},
                         output="provenance.verified_assets"))
    integrity_blocked = any(v.status != "verified" for v in verified)

    # ── 5. full VCF stream ──────────────────────────────────────────────────
    console.step(5, TOTAL_STEPS, "Streaming the complete VCF (aggregates only)...")
    vchar = None
    per_contig = None
    vmeta = assets[vcf_id].metadata if vcf_id else None
    if vcf_id and vcf_id in ok_ids and isinstance(vmeta, VcfMetadata):
        path = case_root / assets[vcf_id].relative_path
        steps, filter_defs, info_ids, formats = upstream.header_description(path)
        scan = vcf_scan.scan(path, [c.name for c in vmeta.contigs], {f.id for f in filter_defs},
                             progress=lambda d, t: console.progress(vcf_id, d, t))
        per_contig = {k.decode(): v for k, v in scan.per_contig.items()}
        vchar = _characterize(vcf_id, vmeta, scan, steps, filter_defs, info_ids, formats, issues)
        ops.append(Operation(operation="stream_vcf_characterization", inputs=[vcf_id],
                             parameters={"parser": "rarepipe strict VCF text parser", "cross_check": "htslib full read", "records_dropped": "0"},
                             output="genome.variant_source"))
        (console.ok if not vchar.records_malformed and vchar.parsers_agree else console.fail)(
            f"{vchar.data_lines:,} data lines; {vchar.records_malformed} malformed; htslib read {vchar.htslib_records:,} ({'agrees' if vchar.parsers_agree else 'DISAGREES'})")
        console.info(f"  PASS {vchar.filters.pass_records:,} · non-PASS {vchar.filters.non_pass_records:,} · FILTER '.' {vchar.filters.missing_filter_records:,}; "
                     f"multiallelic {vchar.multiallelic_records:,}; sorted {vchar.sorted}; phase info: {vchar.phase.status}; {vchar.elapsed_seconds}s")
    else:
        console.warn("no verified primary VCF to stream")

    # ── 6. semantic normalization ───────────────────────────────────────────
    console.step(6, TOTAL_STEPS, "Normalizing reference, contigs, samples, phenotype, reads, pedigree...")
    reference = None
    assembly = manifest.reference.genome_build.value.value
    if vmeta is not None and isinstance(vmeta, VcfMetadata):
        asm_report = None
        if asm_ref is None:
            issues.append(_issue(NormIssueCode.ASSEMBLY_RESOURCE_UNAVAILABLE, Severity.WARNING,
                                 "No pinned assembly report; contigs are classified by labelled name heuristics only."))
        else:
            asm_report = load_assembly_report(Path(asm_ref.path))
            if not contig_layer.report_matches_assembly(asm_report, assembly):
                issues.append(_issue(NormIssueCode.ASSEMBLY_RESOURCE_MISMATCH, Severity.ACTION_REQUIRED,
                                     f"Pinned assembly report is not for the case assembly ({assembly}); it was not used."))
                asm_report = None
        bindings, summary = contig_layer.bind_contigs([(c.name, c.length) for c in vmeta.contigs], asm_report, assembly.split("+")[0], per_contig)
        if summary.length_conflicts:
            issues.append(_issue(NormIssueCode.CONTIG_LENGTH_CONFLICT, Severity.BLOCKER,
                                 f"{summary.length_conflicts} contig(s) match an assembly-report name but not its length.", asset_ids=[vcf_id],
                                 evidence=[b.source_name for b in bindings if b.length_conflict][:10]))
        if summary.by_basis.get("name_heuristic"):
            issues.append(_issue(NormIssueCode.CONTIGS_BOUND_BY_HEURISTIC, Severity.INFO,
                                 f"{summary.by_basis['name_heuristic']} contig(s) classified by name heuristic (not by the assembly report).", asset_ids=[vcf_id]))
        if summary.by_basis.get("unbound"):
            issues.append(_issue(NormIssueCode.CONTIGS_UNBOUND, Severity.WARNING,
                                 f"{summary.by_basis['unbound']} contig(s) could not be bound or classified; they are preserved as 'unknown'.", asset_ids=[vcf_id]))
        issues.append(_issue(NormIssueCode.ANALYSIS_REFERENCE_NOT_BOUND, Severity.INFO,
                             "The assembly is identified, but no exact reference FASTA is bound; left-alignment and read alignment are not yet possible."))
        reference = ReferenceBinding(
            assembly=assembly, assembly_confidence=manifest.reference.genome_build.confidence.value,
            assembly_evidence=[f"CaseManifest {source.run_id}: {e}" for e in manifest.reference.genome_build.evidence],
            source_contig_scheme=summary.source_scheme, assembly_resource=asm_ref if asm_report else None,
            contig_summary=summary, contigs=bindings,
            analysis_reference=AnalysisReference(status="not_yet_bound", reason="no exact, checksum-pinned reference FASTA compatible with the VCF contig dictionary has been provisioned"),
        )
        ops.append(Operation(operation="bind_contig_identities", inputs=[vcf_id], resources=[f"{asm_ref.name} {asm_ref.version}"] if asm_report else [],
                             parameters={"match": "name AND length"}, output="genome.reference.contigs"))
        console.ok(f"{summary.declared} contigs ({summary.source_scheme}): " + ", ".join(f"{n} {k}" for k, n in summary.by_class.items()))

    # samples
    samples = [SampleIdentity(sample_id=s.sample_id, source_labels=s.source_labels) for s in manifest.samples]
    by_sample = {s.sample_id: s for s in samples}

    # phenotype
    onto = load_obo(Path(hpo_ref.path)) if hpo_ref else None
    terms = []
    for aid in pi.phenotype_asset_ids:
        pmeta = assets[aid].metadata
        if isinstance(pmeta, PhenotypeMetadata):
            terms += [normalize_term(t.id, t.polarity, aid, onto) for t in pmeta.terms]
    if not manifest.phenotype.available:
        pheno_status = "unavailable"
    elif onto is None:
        pheno_status = "not_validated_resource_unavailable"
        issues.append(_issue(NormIssueCode.HPO_RESOURCE_UNAVAILABLE, Severity.ACTION_REQUIRED,
                             "No verified pinned HPO release; supplied terms were not validated.", suggested_action="Provision and lock an HPO release: rarepipe resources fetch-hpo."))
    else:
        pheno_status = "normalized"

    # raw reads
    raw_ids = pi.raw_read_asset_ids
    lanes: dict[tuple, LanePair] = {}
    for aid in raw_ids:
        fm = assets[aid].metadata
        if not isinstance(fm, FastqMetadata):
            continue
        key = tuple(sorted([aid, fm.mate_asset_id])) if fm.mate_asset_id else (aid,)
        pair = lanes.setdefault(key, LanePair(lane=fm.lane_from_header or fm.lane_from_filename, r1_asset_id=None, r2_asset_id=None))
        if (fm.read_number_from_header or fm.read_number_from_filename) == 2:
            pair.r2_asset_id = aid
        else:
            pair.r1_asset_id = aid
    linkage = SampleLinkage(status="unverified", reason="FASTQ files carry no sample metadata and no identity check has been performed") if raw_ids else None

    # assertions
    for a in active_assertions:
        rec = AppliedAssertion(assertion_id=a.assertion_id, subject_type=a.subject.type, subject_id=a.subject.id, predicate=a.predicate, value=a.value,
                               evidence_type=a.evidence.type, evidence_reference=a.evidence.reference, asserted_by=a.asserted_by, asserted_at=a.asserted_at, applied=False)
        reason = None
        if a.predicate == "role":
            if a.subject.id in by_sample:
                by_sample[a.subject.id].role, by_sample[a.subject.id].role_source, by_sample[a.subject.id].role_assertion_id = a.value, "externally_asserted", a.assertion_id
            else:
                reason = "subject sample not in CaseManifest"
        elif a.predicate == "phenotype_polarity":
            targets = [t for t in terms if (a.subject.type == "phenotype_set" and a.subject.id in ("ALL", t.source_asset_id))
                       or (a.subject.type == "hpo_term" and t.source_id == a.subject.id)]
            if not targets:
                reason = "no supplied phenotype term matches the subject"
            conflicts = [t for t in targets if t.polarity_basis == "source_document" and t.polarity != a.value]
            for t in targets:
                if t.polarity_basis != "source_document":
                    t.polarity, t.polarity_basis = a.value, f"assertion:{a.assertion_id}"
            if conflicts:
                issues.append(_issue(NormIssueCode.ASSERTION_REJECTED, Severity.WARNING,
                                     f"Assertion {a.assertion_id} did not override {len(conflicts)} polarity value(s) stated in the source document."))
        elif a.predicate == "sample_linkage":
            if not raw_ids:
                reason = "case has no raw reads"
            elif a.subject.id != "ALL":
                reason = "only subject id 'ALL' is supported for raw_read_set"
            elif a.value not in by_sample:
                reason = "asserted sample not in CaseManifest"
            else:
                linkage = SampleLinkage(status="externally_asserted", sample_id=a.value, assertion_id=a.assertion_id,
                                        reason="asserted by an operator with evidence; not computationally verified")
                for ci in issues:
                    if ci.code == "FASTQ_SAMPLE_UNDECLARED":
                        ci.resolution, ci.assertion_ids = "addressed_by_assertion", [a.assertion_id]
        rec.applied, rec.rejection_reason = reason is None, reason
        applied.append(rec)
        if reason:
            issues.append(_issue(NormIssueCode.ASSERTION_REJECTED, Severity.ACTION_REQUIRED, f"Assertion {a.assertion_id} was not applied: {reason}."))
        else:
            issues.append(_issue(NormIssueCode.ASSERTION_APPLIED, Severity.INFO, f"Assertion {a.assertion_id} applied ({a.predicate})."))
    if applied:
        ops.append(Operation(operation="apply_case_assertions", inputs=[f"CaseAssertions sha256:{assertions_sha}"], output="samples/phenotype/raw_reads"))

    # phenotype issues + section (after polarity assertions)
    status_counts = Counter(t.status for t in terms)
    resolved = [t for t in terms if t.status in ("active", "secondary_id", "obsolete_replaced")]
    if status_counts.get("unknown"):
        issues.append(_issue(NormIssueCode.HPO_TERM_UNKNOWN, Severity.ACTION_REQUIRED, f"{status_counts['unknown']} supplied identifier(s) do not exist in the pinned HPO release.",
                             asset_ids=pi.phenotype_asset_ids))
    if status_counts.get("obsolete_replaced"):
        issues.append(_issue(NormIssueCode.HPO_TERM_OBSOLETE_REPLACED, Severity.WARNING,
                             f"{status_counts['obsolete_replaced']} obsolete identifier(s) mapped to their ontology replacement (original ids preserved).", asset_ids=pi.phenotype_asset_ids))
    if status_counts.get("obsolete_no_replacement"):
        issues.append(_issue(NormIssueCode.HPO_TERM_OBSOLETE_NO_REPLACEMENT, Severity.ACTION_REQUIRED,
                             f"{status_counts['obsolete_no_replacement']} obsolete identifier(s) have no unambiguous replacement; none was chosen.", asset_ids=pi.phenotype_asset_ids))
    if status_counts.get("secondary_id"):
        issues.append(_issue(NormIssueCode.HPO_TERM_SECONDARY_ID, Severity.INFO, f"{status_counts['secondary_id']} identifier(s) are secondary (alt_id) ids of a current concept."))
    outside = [t for t in resolved if "phenotypic_abnormality" not in t.branches]
    if outside:
        issues.append(_issue(NormIssueCode.HPO_TERM_OUTSIDE_PHENOTYPIC_ABNORMALITY, Severity.WARNING,
                             f"{len(outside)} supplied term(s) are not under 'Phenotypic abnormality' (e.g. inheritance or modifier terms).", asset_ids=pi.phenotype_asset_ids))
    polarity_counts = Counter(t.polarity for t in terms)
    if polarity_counts.get("unspecified"):
        issues.append(_issue(NormIssueCode.HPO_POLARITY_UNSPECIFIED, Severity.WARNING,
                             f"{polarity_counts['unspecified']} term(s) have unspecified polarity; listing a term is not treated as 'observed'.",
                             asset_ids=pi.phenotype_asset_ids, suggested_action="Supply a CaseAssertions record citing documentation, if such evidence exists."))
    phenotype = PhenotypeSection(
        status=pheno_status, ontology=hpo_ref, ontology_release=release_date(onto) if onto else None, source_term_count=len(terms),
        canonical_term_count=len({t.canonical_id for t in resolved}), status_counts=dict(sorted(status_counts.items())),
        polarity_counts=dict(sorted(polarity_counts.items())), branch_counts=dict(sorted(Counter(b for t in resolved for b in t.branches).items())), terms=terms,
    )
    if terms:
        ops.append(Operation(operation="normalize_hpo_identities", inputs=pi.phenotype_asset_ids,
                             resources=[f"HPO {phenotype.ontology_release} sha256:{hpo_ref.sha256}"] if hpo_ref else [],
                             parameters={"graph_expansion": "none", "polarity_default": "unspecified"}, output="phenotype.terms"))
    console.ok(f"phenotype: {len(terms)} term(s) — " + (", ".join(f"{n} {k}" for k, n in sorted(status_counts.items())) or "none")
               + f"; polarity {dict(polarity_counts)}")

    raw_reads = RawReadsSection(available=bool(raw_ids), asset_ids=raw_ids, lane_pairs=sorted(lanes.values(), key=lambda p: (p.lane or 0, p.r1_asset_id or "")),
                                total_size_bytes=sum(assets[a].size_bytes for a in raw_ids), sample_linkage=linkage)
    console.info(f"raw reads: {len(raw_ids)} file(s), {len(lanes)} lane pair(s); linkage {linkage.status if linkage else 'n/a'} (not opened)")
    pedigree = PedigreeSection(status=manifest.pedigree.status,
                               note="Not supplied. This is not evidence of absent family; no singleton pedigree is fabricated." if manifest.pedigree.status == "unavailable"
                               else "Relationships exactly as asserted in Stage 01 pedigree sources.",
                               relationships=[r.model_dump(mode="json") for r in manifest.pedigree.relationships])

    genome = GenomeSection(reference=reference, variant_source=vchar, samples=samples)
    caps = readiness.assess(genome, phenotype, pedigree, raw_reads, upstream_blocked,
                            integrity_blocked or any(i.code in ("VCF_RECORDS_MALFORMED", "CONTIG_LENGTH_CONFLICT", "UPSTREAM_SEAL_MISMATCH", "RESOURCE_CHECKSUM_MISMATCH") for i in issues))

    issues = sorted({i.model_dump_json(): i for i in issues}.values(), key=CarriedIssue.sort_key)
    live = [i for i in issues if i.resolution == "unresolved"]
    counts = {s.value: sum(1 for i in live if i.severity == s) for s in Severity}
    counts["INFO"] = sum(1 for i in issues if i.severity == Severity.INFO)
    if counts["BLOCKER"]:
        status = Status.NORMALIZATION_BLOCKED
    elif counts["ACTION_REQUIRED"] or counts["WARNING"]:
        status = Status.NORMALIZATION_COMPLETE_WITH_WARNINGS
    else:
        status = Status.NORMALIZATION_COMPLETE

    opened = [v.asset_id for v in verified]
    case = NormalizedCase(
        visibility="private", case_id=manifest.case.case_id, status=status, readiness=caps, genome=genome, phenotype=phenotype, pedigree=pedigree,
        raw_reads=raw_reads, assertions=applied, issues=issues, issue_counts=counts,
        retention=Retention(inherited_from_assets=sorted(set(opened)), source_retention_classes=sorted({assets[a].retention_class.value for a in opened})),
        provenance=Provenance(software=software_provenance(), source_manifest=source, verified_assets=verified, resources=resources,
                              assertions_sha256=assertions_sha, operations=ops,
                              environment_controls=env_controls + ["no network access performed by normalization", "source assets opened read-only",
                                                                   "no derived genomic files written", "FASTQ assets not opened"],
                              case_root_override=str(req.case_root.resolve()) if req.case_root else None),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3), argv=req.argv),
    )
    case.semantic_digest = _semantic_digest(case)
    return case


def _characterize(vcf_id, vmeta: VcfMetadata, scan: vcf_scan.ScanResult, steps, filter_defs, info_ids, formats, issues) -> VcfCharacterization:
    n = scan.records_parsed
    denom = max(1, n * max(1, scan.sample_count))
    fields = sorted(set(formats) | {k.decode() for k in scan.fmt_declaring})
    fmt_stats = [FormatFieldStat(field=f, present_in_header=f in formats, header_number=formats.get(f, (None, None))[0],
                                 header_type=formats.get(f, (None, None))[1], records_declaring=scan.fmt_declaring[f.encode()],
                                 records_populated=scan.fmt_populated[f.encode()], populated_fraction=round(scan.fmt_populated[f.encode()] / denom, 6))
                 for f in fields]
    pop = {s.field: s.records_populated for s in fmt_stats}
    het = scan.gt["het"] + scan.gt["het_non_ref"]
    kinds = [k for k, present in (("gt_phased_separator", scan.het_phased > 0), ("phase_set_PS", pop.get("PS", 0) > 0),
                                  ("read_backed_PGT_PID", pop.get("PGT", 0) > 0 or pop.get("PID", 0) > 0)) if present]
    header_filter_ids = {f.id for f in filter_defs}
    undeclared = sorted(f for f in scan.by_filter if f not in header_filter_ids)
    agree = None if scan.htslib_records is None else (not scan.htslib_error and scan.htslib_records == scan.data_lines)
    sorted_ok = scan.out_of_order == 0 and scan.noncontiguous == 0

    vc = VcfCharacterization(
        asset_id=vcf_id, sample_id=vmeta.sample_ids[0] if len(vmeta.sample_ids) == 1 else None, streamed_completely=scan.streamed_completely,
        data_lines=scan.data_lines, records_parsed=n, records_malformed=scan.malformed, malformed_line_numbers=scan.malformed_lines,
        htslib_records=scan.htslib_records, htslib_error=scan.htslib_error, parsers_agree=agree, sorted=sorted_ok,
        out_of_order_records=scan.out_of_order, noncontiguous_contig_blocks=scan.noncontiguous, contig_order_follows_header=scan.order_follows_header,
        records_on_undeclared_contigs=scan.undeclared_contig_records, exact_duplicate_records=scan.exact_duplicates,
        records_sharing_position=scan.sharing_position, invalid_ref_alleles=scan.invalid_ref, invalid_alt_alleles=scan.invalid_alt,
        filters=FilterCharacterization(definitions=filter_defs, pass_records=scan.pass_records, missing_filter_records=scan.missing_filter,
                                       non_pass_records=scan.non_pass, records_by_filter=dict(sorted(scan.by_filter.items())),
                                       records_with_multiple_filters=scan.multi_filter, undeclared_filters_used=undeclared),
        record_classes=dict(sorted(scan.record_classes.items())), allele_classes=dict(sorted(scan.allele_classes.items())),
        multiallelic_records=scan.multiallelic, max_alt_alleles=scan.max_alts, records_with_spanning_deletion_allele=scan.spanning_deletion_records,
        qual_missing_records=scan.qual_missing, info_fields_declared=info_ids, format_fields=fmt_stats,
        genotype_states=GenotypeStates(**{k: scan.gt[k] for k in ("hom_ref", "het", "hom_alt", "het_non_ref", "haploid_called", "missing", "partially_missing")},
                                       ploidy_counts=dict(sorted(scan.ploidy.items()))),
        genotype_malformed=scan.genotype_malformed,
        phase=PhaseInformation(status="present" if kinds else "none", kinds=kinds, het_records=het, het_records_gt_phased=scan.het_phased,
                               ps_populated_records=pop.get("PS", 0), pgt_populated_records=pop.get("PGT", 0), pid_populated_records=pop.get("PID", 0)),
        upstream_processing=steps, elapsed_seconds=scan.elapsed,
    )
    ids = [vcf_id]
    if scan.malformed:
        issues.append(_issue(NormIssueCode.VCF_RECORDS_MALFORMED, Severity.BLOCKER, f"{scan.malformed} VCF data line(s) are malformed (wrong column count, invalid POS/QUAL).",
                             asset_ids=ids, evidence=[f"first line numbers: {', '.join(map(str, scan.malformed_lines))}"],
                             suggested_action="Obtain a corrected VCF from the provider; normalization never repairs or drops records."))
    if scan.htslib_error:
        issues.append(_issue(NormIssueCode.VCF_HTSLIB_READ_FAILED, Severity.BLOCKER, f"htslib stopped reading after {scan.htslib_records} record(s); downstream tools will fail on this file.", asset_ids=ids))
    elif agree is False:
        issues.append(_issue(NormIssueCode.VCF_PARSER_DISAGREEMENT, Severity.BLOCKER,
                             f"htslib read {scan.htslib_records} record(s) but the file has {scan.data_lines} data line(s).", asset_ids=ids))
    if not sorted_ok:
        issues.append(_issue(NormIssueCode.VCF_NOT_SORTED, Severity.ACTION_REQUIRED,
                             f"VCF is not coordinate-sorted ({scan.out_of_order} out-of-order record(s), {scan.noncontiguous} non-contiguous contig block(s)).", asset_ids=ids))
    if not scan.order_follows_header:
        issues.append(_issue(NormIssueCode.VCF_CONTIG_ORDER_DIFFERS_FROM_HEADER, Severity.WARNING, "Contig blocks do not follow the header's contig order.", asset_ids=ids))
    if scan.undeclared_contig_records:
        issues.append(_issue(NormIssueCode.VCF_RECORDS_ON_UNDECLARED_CONTIGS, Severity.WARNING, f"{scan.undeclared_contig_records} record(s) lie on contigs not declared in the header.", asset_ids=ids))
    if scan.invalid_ref or scan.invalid_alt:
        issues.append(_issue(NormIssueCode.VCF_INVALID_ALLELE_SYNTAX, Severity.ACTION_REQUIRED,
                             f"{scan.invalid_ref} REF and {scan.invalid_alt} ALT allele(s) violate VCF allele syntax.", asset_ids=ids))
    if scan.exact_duplicates:
        issues.append(_issue(NormIssueCode.VCF_DUPLICATE_RECORDS, Severity.WARNING, f"{scan.exact_duplicates} record(s) duplicate another record's position and alleles.", asset_ids=ids))
    if undeclared:
        issues.append(_issue(NormIssueCode.VCF_UNDECLARED_FILTERS, Severity.WARNING, f"{len(undeclared)} FILTER label(s) are used but not declared in the header.", asset_ids=ids))
    if scan.genotype_malformed:
        issues.append(_issue(NormIssueCode.VCF_GENOTYPE_MALFORMED, Severity.ACTION_REQUIRED, f"{scan.genotype_malformed} GT value(s) are malformed or reference undefined alleles.", asset_ids=ids))
    if scan.non_pass:
        issues.append(_issue(NormIssueCode.VCF_NON_PASS_RECORDS_PRESERVED, Severity.INFO,
                             f"{scan.non_pass} non-PASS record(s) are present and preserved. Whether upstream processing removed other records cannot be determined from the file.", asset_ids=ids))
    if scan.multiallelic:
        issues.append(_issue(NormIssueCode.VCF_MULTIALLELIC_RECORDS_PRESENT, Severity.INFO, f"{scan.multiallelic} multiallelic record(s) present (not decomposed).", asset_ids=ids))
    if not kinds:
        issues.append(_issue(NormIssueCode.PHASE_INFORMATION_ABSENT, Severity.INFO, "The VCF contains no phase information (no '|' heterozygous GT, PS, PGT or PID).", asset_ids=ids))
    return vc
