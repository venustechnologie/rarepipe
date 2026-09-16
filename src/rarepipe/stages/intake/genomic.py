"""Header-level inspection of genomic formats via pysam/htslib.

What is read: headers, sequence dictionaries, index structures, the BGZF EOF
marker, and — for VCF/BCF only — whether the *first* record parses (its content
is discarded immediately). What is never done: iterating variants, reading
alignments, computing coverage, fetching loci, or decoding CRAM slices.
"""

from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pysam

from rarepipe.core.issues import Issue, IssueCode, Severity
from rarepipe.stages.intake.manifest import (
    AlignmentMetadata,
    Compression,
    Contig,
    FastaMetadata,
    Format,
    HeaderDeclarations,
    IndexStatus,
    Program,
    ReadGroup,
    SequenceDictionaryMetadata,
    VcfMetadata,
)
from rarepipe.stages.intake.reference import determine_build

pysam.set_verbosity(0)  # htslib diagnostics go to stderr unfiltered; we record structured issues instead

ANNOTATION_INFO_KEYS = {"CSQ": "VEP", "ANN": "SnpEff", "BCSQ": "bcftools csq", "LOF": "SnpEff LOF", "NMD": "SnpEff NMD"}


@dataclass
class Inspection:
    metadata: object | None = None
    issues: list[Issue] = field(default_factory=list)
    # Restricted, pre-alias sample labels in header order; the stage maps them to SAMPLE_nnn.
    sample_labels: list[str] = field(default_factory=list)
    # Restricted: @SQ UR values (often absolute paths) for CRAM reference resolution.
    reference_uris: list[str] = field(default_factory=list)


def _issue(code, severity, message, asset_id, action=None, evidence=()):
    return Issue(code=code, severity=severity, message=message, asset_ids=[asset_id], suggested_action=action, evidence=list(evidence))


# ── VCF / BCF ────────────────────────────────────────────────────────────────


def inspect_vcf(path: Path, asset_id: str, fmt: Format, compression: Compression, eof_present: bool | None,
                index: IndexStatus, index_path: Path | None) -> Inspection:
    out = Inspection()
    unknown_build = determine_build([])
    try:
        vf = pysam.VariantFile(str(path), "r", index_filename=str(index_path) if index_path else None)
    except (OSError, ValueError) as exc:
        out.issues.append(_issue(IssueCode.VCF_PARSE_FAILED, Severity.BLOCKER, f"{fmt.value} header could not be parsed ({type(exc).__name__}).",
                                 asset_id, "Verify compression and file integrity (e.g. re-download and compare checksums)."))
        out.metadata = VcfMetadata(format=fmt, compression=compression, header_valid=False, genome_build=unknown_build, index=index)
        return out

    with vf:
        h = vf.header
        contigs = [Contig(name=c.name, length=c.length, md5=(dict(c.header_record.items()).get("md5") if c.header_record else None))
                   for c in h.contigs.values()]
        claims, source_tools, hints = [], set(), set()
        reference_claim = None
        is_gvcf = False
        for rec in h.records:
            key = rec.key or ""
            if rec.type == "GENERIC":
                value = rec.value or ""
                if key == "reference":
                    reference_claim = value
                    claims.append(("##reference", value))
                elif key.lower() in ("assembly", "genome_build", "genomebuild"):
                    claims.append((f"##{key}", value))
                elif key == "source":
                    source_tools.add(Path(value.split()[0]).name[:80] if value.strip() else "unspecified")  # basename: values can be paths
                elif key.startswith("GVCFBlock"):
                    is_gvcf = True
                if key.lower().endswith(("command", "commandline", "cmdline")):
                    source_tools.add(key[:80])
            elif rec.type == "STRUCTURED":
                items = dict(rec.items())
                if key.lower().endswith(("command", "commandline")) or key == "DRAGENCommandLine":
                    source_tools.add((items.get("ID") or key)[:80])
                if key == "ALT" and items.get("ID") in ("NON_REF", "*"):
                    is_gvcf = True
            elif rec.type == "CONTIG":
                items = dict(rec.items())
                if items.get("assembly"):
                    claims.append(("##contig assembly", items["assembly"]))
        for info_key, tool in ANNOTATION_INFO_KEYS.items():
            if info_key in h.info:
                hints.add(f"INFO/{info_key} declared (typical of {tool} annotation)")
        filters = list(h.filters.keys())
        if [f for f in filters if f != "PASS"]:
            hints.add(f"{len([f for f in filters if f != 'PASS'])} non-PASS FILTER(s) declared")

        build = determine_build(contigs, claims)
        labels = list(h.samples)
        out.sample_labels = labels

        has_records = None
        try:
            next(iter(vf))  # parsed and discarded — content is never retained or logged
            has_records = True
        except StopIteration:
            has_records = False
        except (OSError, ValueError) as exc:
            out.issues.append(_issue(IssueCode.VCF_PARSE_FAILED, Severity.BLOCKER,
                                     f"Header parsed but the first record could not be read ({type(exc).__name__}).",
                                     asset_id, "Verify file integrity; the body may be corrupt or truncated."))

        contigs_with_records = None
        if index.present:
            try:
                idx = vf.index
                contigs_with_records = sorted(idx.keys()) if idx is not None else None
                index.usable = idx is not None
            except (OSError, ValueError, AttributeError):
                index.usable = False
            if not index.usable:
                out.issues.append(_issue(IssueCode.INDEX_UNUSABLE, Severity.ACTION_REQUIRED, "Index file is present but htslib could not load it for this file.",
                                         asset_id, "Regenerate the index in a preparation stage (not in intake)."))

    out.metadata = VcfMetadata(
        format=fmt, compression=compression, header_valid=True, vcf_version=h.version, is_gvcf=is_gvcf, has_records=has_records,
        sample_count=len(labels), source_sample_labels=labels, contigs=contigs, contigs_with_records_per_index=contigs_with_records,
        reference_claim=reference_claim, genome_build=build, index=index,
        declarations=HeaderDeclarations(info=sorted(h.info.keys()), format=sorted(h.formats.keys()), filter=sorted(filters)),
        source_tools=sorted(source_tools), processing_hints=sorted(hints),
    )

    if compression == Compression.GZIP:
        out.issues.append(_issue(IssueCode.VCF_NOT_BGZF, Severity.ACTION_REQUIRED, "VCF is plain-gzip compressed, not BGZF; it cannot be indexed or randomly accessed.",
                                 asset_id, "Recompress with bgzip in a preparation stage."))
    if compression == Compression.BGZF or fmt == Format.BCF:
        if eof_present is False:
            out.issues.append(_issue(IssueCode.BGZF_EOF_MISSING, Severity.BLOCKER, "BGZF end-of-file marker is absent; the file is likely truncated.",
                                     asset_id, "Re-transfer the file and verify its checksum against the source."))
    if not index.present and compression != Compression.GZIP:
        sev = Severity.ACTION_REQUIRED if compression in (Compression.BGZF, Compression.FORMAT_NATIVE) else Severity.WARNING
        out.issues.append(_issue(IssueCode.INDEX_MISSING, sev, f"No {'TBI/CSI' if fmt == Format.VCF else 'CSI'} index found for this {fmt.value}.",
                                 asset_id, "Create the index in a preparation stage; intake does not create derived files."))
    if has_records is False:
        out.issues.append(_issue(IssueCode.VCF_NO_RECORDS, Severity.ACTION_REQUIRED, "Variant file contains a header but no records.", asset_id,
                                 "Confirm this is the intended variant file."))
    if not labels:
        out.issues.append(_issue(IssueCode.VCF_NO_SAMPLES, Severity.ACTION_REQUIRED, "Variant file has no sample columns (sites-only); no genotypes are available.",
                                 asset_id, "Confirm whether a genotyped VCF exists for this case."))
    if not contigs:
        out.issues.append(_issue(IssueCode.VCF_NO_CONTIG_HEADER, Severity.WARNING, "No ##contig header lines; reference cannot be fingerprinted from this file.", asset_id))
    if is_gvcf:
        out.issues.append(_issue(IssueCode.GVCF_DETECTED, Severity.INFO, "Header indicates a gVCF (reference blocks present); it is not equivalent to a called VCF.", asset_id))
    return out


# ── BAM / CRAM ───────────────────────────────────────────────────────────────


def inspect_alignments(path: Path, asset_id: str, fmt: Format, eof_present: bool | None,
                       index: IndexStatus, index_path: Path | None) -> Inspection:
    out = Inspection()
    unknown_build = determine_build([])
    mode = "rc" if fmt == Format.CRAM else "rb"
    try:
        af = pysam.AlignmentFile(str(path), mode, check_sq=False, require_index=False,
                                 index_filename=str(index_path) if index_path else None)
    except (OSError, ValueError) as exc:
        truncated = " The BGZF end-of-file marker is also absent — the file is likely truncated." if eof_present is False else ""
        out.issues.append(_issue(IssueCode.ALIGNMENT_PARSE_FAILED, Severity.BLOCKER, f"{fmt.value} could not be opened by htslib ({type(exc).__name__}).{truncated}",
                                 asset_id, "Re-transfer the file and verify its checksum against the source."))
        out.metadata = AlignmentMetadata(format=fmt, header_valid=False, bgzf_eof_present=eof_present, genome_build=unknown_build, index=index)
        return out

    with af:
        hdr = af.header.to_dict()
        if index.present:
            try:
                index.usable = bool(af.check_index())
            except (ValueError, OSError):
                index.usable = False

    quickcheck = True
    try:
        pysam.samtools.quickcheck(str(path))
    except pysam.utils.SamtoolsError:
        quickcheck = False  # stderr includes the absolute path; do not propagate it

    sq = hdr.get("SQ", [])
    contigs = [Contig(name=s["SN"], length=s.get("LN"), md5=s.get("M5")) for s in sq]
    out.reference_uris = sorted({s["UR"] for s in sq if s.get("UR")})
    claims = [("@SQ AS", s["AS"]) for s in sq if s.get("AS")][:1] + [("@SQ UR", s["UR"]) for s in sq if s.get("UR")][:1]
    build = determine_build(contigs, claims)

    read_groups = []
    labels: list[str] = []
    for rg in hdr.get("RG", []):
        sm = rg.get("SM")
        read_groups.append(ReadGroup(platform=rg.get("PL"), source_id=rg.get("ID"), source_sample_label=sm, library=rg.get("LB")))
        if sm is not None and sm not in labels:
            labels.append(sm)
    out.sample_labels = labels

    sort_order = hdr.get("HD", {}).get("SO")
    programs = [Program(name=p.get("PN") or p.get("ID"), version=p.get("VN")) for p in hdr.get("PG", [])]
    meta = AlignmentMetadata(
        format=fmt, header_valid=True, quickcheck_passed=quickcheck, bgzf_eof_present=eof_present, sort_order=sort_order,
        contigs=contigs, read_group_count=len(read_groups), read_groups=read_groups, programs=programs, genome_build=build, index=index,
    )
    out.metadata = meta

    if eof_present is False or not quickcheck:
        out.issues.append(_issue(IssueCode.ALIGNMENT_QUICKCHECK_FAILED, Severity.BLOCKER,
                                 f"{fmt.value} failed integrity quick-check" + (" (end-of-file marker missing — likely truncated)." if eof_present is False else "."),
                                 asset_id, "Re-transfer the file and verify its checksum against the source."))
    if sort_order != "coordinate":
        out.issues.append(_issue(IssueCode.ALIGNMENT_NOT_COORDINATE_SORTED, Severity.WARNING,
                                 f"Header sort order is '{sort_order or 'undeclared'}', not 'coordinate'; random access requires coordinate sorting.", asset_id))
    if not index.present:
        out.issues.append(_issue(IssueCode.INDEX_MISSING, Severity.ACTION_REQUIRED, f"No {'CRAI' if fmt == Format.CRAM else 'BAI/CSI'} index found for this {fmt.value}.",
                                 asset_id, "Create the index in a preparation stage; intake does not create derived files."))
    elif index.usable is False:
        out.issues.append(_issue(IssueCode.INDEX_UNUSABLE, Severity.ACTION_REQUIRED, "Index file is present but htslib could not load it for this file.", asset_id,
                                 "Regenerate the index in a preparation stage."))
    if not read_groups:
        out.issues.append(_issue(IssueCode.READ_GROUPS_ABSENT, Severity.ACTION_REQUIRED, "No @RG read groups; the sample this file belongs to cannot be established from metadata.",
                                 asset_id, "Obtain sample identity from the data provider."))
    elif any(rg.source_sample_label is None for rg in read_groups):
        out.issues.append(_issue(IssueCode.READ_GROUP_SAMPLE_MISSING, Severity.ACTION_REQUIRED, "One or more read groups lack an SM (sample) tag.", asset_id,
                                 "Obtain sample identity from the data provider."))
    if len(labels) > 1:
        out.issues.append(_issue(IssueCode.READ_GROUP_SAMPLE_CONFLICT, Severity.ACTION_REQUIRED,
                                 f"Read groups name {len(labels)} different samples within one alignment file.", asset_id,
                                 "Confirm whether this file intentionally merges multiple samples."))
    return out


# ── FASTA / dictionaries ─────────────────────────────────────────────────────


def parse_fai(path: Path) -> list[Contig]:
    contigs = []
    with path.open() as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 2 and cols[1].isdigit():
                contigs.append(Contig(name=cols[0], length=int(cols[1])))
    return contigs


def parse_sequence_dictionary(path: Path) -> list[Contig]:
    contigs = []
    with path.open() as fh:
        for line in fh:
            if not line.startswith("@SQ"):
                continue
            fields = dict(f.split(":", 1) for f in line.rstrip("\n").split("\t")[1:] if ":" in f)
            if "SN" in fields:
                ln = fields.get("LN")
                contigs.append(Contig(name=fields["SN"], length=int(ln) if ln and ln.isdigit() else None, md5=fields.get("M5")))
    return contigs


def dictionary_claims(path: Path) -> list[tuple[str, str]]:
    claims = []
    with path.open() as fh:
        for line in fh:
            if line.startswith("@SQ"):
                for f in line.rstrip("\n").split("\t")[1:]:
                    if f.startswith(("AS:", "UR:")):
                        claims.append((f"@SQ {f[:2]}", f[3:]))
                if claims:
                    break
    return claims


def scan_fasta(path: Path, compression: Compression, want_md5: bool) -> list[Contig]:
    """Single streaming pass. MD5 follows the SAM spec: uppercase, no whitespace."""
    opener = gzip.open if compression in (Compression.BGZF, Compression.GZIP) else open
    contigs: list[Contig] = []
    name, length, md5 = None, 0, None

    def flush():
        if name is not None:
            contigs.append(Contig(name=name, length=length, md5=md5.hexdigest() if md5 else None))

    with opener(path, "rb") as fh:
        for line in fh:
            if line.startswith(b">"):
                flush()
                name = line[1:].split()[0].decode() if line[1:].split() else ""
                length = 0
                md5 = hashlib.md5(usedforsecurity=False) if want_md5 else None
            else:
                seq = line.strip()
                length += len(seq)
                if md5 is not None:
                    md5.update(seq.upper())
        flush()
    return contigs


def inspect_fasta(path: Path, asset_id: str, compression: Compression, index: IndexStatus, fai_path: Path | None,
                  dict_path: Path | None, want_md5: bool) -> Inspection:
    out = Inspection()
    source = "none"
    contigs: list[Contig] = []
    claims: list[tuple[str, str]] = []
    try:
        if want_md5:
            contigs, source = scan_fasta(path, compression, want_md5=True), "streamed_scan"
        elif fai_path:
            contigs, source = parse_fai(fai_path), "fai"
        elif dict_path:
            contigs, source = parse_sequence_dictionary(dict_path), "sequence_dictionary"
        else:
            contigs, source = scan_fasta(path, compression, want_md5=False), "streamed_scan"
        if dict_path:
            claims = dictionary_claims(dict_path)
    except (OSError, ValueError, EOFError) as exc:
        out.issues.append(_issue(IssueCode.FASTA_PARSE_FAILED, Severity.ACTION_REQUIRED, f"FASTA could not be scanned ({type(exc).__name__}).", asset_id,
                                 "Verify file integrity."))
    if fai_path and source == "streamed_scan":
        fai = {c.name: c.length for c in parse_fai(fai_path)}
        scanned = {c.name: c.length for c in contigs}
        index.usable = fai == scanned
        if not index.usable:
            out.issues.append(_issue(IssueCode.INDEX_UNUSABLE, Severity.ACTION_REQUIRED, "FASTA index (.fai) disagrees with the FASTA's actual contigs/lengths.",
                                     asset_id, "Regenerate the .fai in a preparation stage."))
    elif fai_path:
        index.usable = True
    if not index.present:
        out.issues.append(_issue(IssueCode.INDEX_MISSING, Severity.WARNING, "Reference FASTA has no .fai index.", asset_id,
                                 "Create the index in a preparation stage if random access is needed."))
    out.metadata = FastaMetadata(compression=compression, contig_source=source, contigs=contigs, md5_computed=want_md5 and source == "streamed_scan",
                                 genome_build=determine_build(contigs, claims), index=index)
    return out


def inspect_sequence_dictionary(path: Path, asset_id: str) -> Inspection:
    contigs = parse_sequence_dictionary(path)
    return Inspection(metadata=SequenceDictionaryMetadata(contigs=contigs, genome_build=determine_build(contigs, dictionary_claims(path))))
