"""Asset discovery, content sniffing, role assignment and asset relationships.

Nothing here opens a file for writing. Directory symlinks are not traversed
(loop- and scope-safety); file symlinks are inspected and flagged if they
resolve outside the case root.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.issues import Issue, IssueCode, Severity
from rarepipe.stages.intake import formats
from rarepipe.stages.intake.manifest import (
    AssetRelationship,
    Compression,
    Format,
    LogicalRole,
    RelationshipType,
    RetentionClass,
)

SYSTEM_FILES = {".ds_store", "thumbs.db", "desktop.ini"}
DOC_NAMES = ("readme", "license", "changelog", "data_use", "terms")

GENOMIC = {Format.VCF, Format.BCF, Format.BAM, Format.CRAM, Format.SAM}
GENOMIC_INDEXES = {Format.TBI, Format.CSI, Format.BAI, Format.CRAI}
OPAQUE = {Format.BINARY_UNKNOWN, Format.GZIP_UNKNOWN}


@dataclass
class Discovered:
    asset_id: str
    rel: str
    path: Path
    filename: str
    extension: str
    ext_fmt: Format | None
    sniff: formats.Sniff
    size: int
    stat: os.stat_result
    external: bool = False
    role: LogicalRole = LogicalRole.UNKNOWN
    issues: list[Issue] = field(default_factory=list)

    @property
    def fmt(self) -> Format:
        return self.sniff.format


def asset_id_for(rel: str) -> str:
    return "ASSET_" + hashlib.sha256(rel.encode()).hexdigest()[:10].upper()


def _excluded(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(Path(rel).name, g) for g in globs)


def _make(path: Path, rel: str, external: bool) -> Discovered:
    st = path.stat()
    ext = formats.split_extension(path.name)
    ext_fmt = formats.extension_format(path.name)
    return Discovered(asset_id=asset_id_for(rel), rel=rel, path=path, filename=path.name, extension=ext, ext_fmt=ext_fmt,
                      sniff=formats.sniff(path, ext_fmt), size=st.st_size, stat=st, external=external)


def discover(case_root: Path, exclude_globs: list[str], external_references: list[Path]) -> tuple[list[Discovered], list[Issue]]:
    assets: list[Discovered] = []
    issues: list[Issue] = []
    root = case_root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        d = Path(dirpath)
        for name in list(dirnames):
            if (d / name).is_symlink():
                issues.append(Issue(code=IssueCode.SYMLINKED_DIRECTORY_NOT_TRAVERSED, severity=Severity.WARNING,
                                    message="A symlinked directory inside the case root was not traversed; its contents are not part of this manifest.",
                                    suggested_action="Replace with a real directory or pass its files explicitly if they belong to the case."))
        for name in sorted(filenames):
            path = d / name
            rel = path.relative_to(root).as_posix()
            if _excluded(rel, exclude_globs):
                continue
            try:
                asset = _make(path, rel, external=False)
            except OSError as exc:
                issues.append(Issue(code=IssueCode.FILE_UNREADABLE, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id_for(rel)],
                                    message=f"A file in the case root could not be read ({type(exc).__name__}).",
                                    suggested_action="Fix permissions or remove the broken link; its role cannot be established."))
                continue
            if path.is_symlink() and not path.resolve().is_relative_to(root):
                asset.issues.append(Issue(code=IssueCode.SYMLINK_OUTSIDE_CASE_ROOT, severity=Severity.WARNING, asset_ids=[asset.asset_id],
                                          message="File is a symlink resolving outside the case root; its content was inspected in place."))
            assets.append(asset)
    for n, ref in enumerate(external_references, start=1):
        p = ref.resolve()
        assets.append(_make(p, f"external:{n}:{p.name}", external=True))
    return assets, issues


def assign_role(a: Discovered, is_phenotype: bool) -> None:
    f = a.fmt
    lower = a.filename.lower()
    if lower in SYSTEM_FILES or lower.startswith("._"):
        a.role = LogicalRole.SYSTEM_FILE
    elif f in (Format.VCF, Format.BCF):
        a.role = LogicalRole.GENOMIC_VARIANTS
    elif f in (Format.BAM, Format.CRAM, Format.SAM):
        a.role = LogicalRole.ALIGNED_READS
    elif f in (Format.TBI, Format.CSI):
        a.role = LogicalRole.VARIANT_INDEX  # re-labelled to ALIGNMENT_INDEX if it indexes a BAM
    elif f in (Format.BAI, Format.CRAI):
        a.role = LogicalRole.ALIGNMENT_INDEX
    elif f == Format.FASTA:
        a.role = LogicalRole.REFERENCE_SEQUENCE
    elif f in (Format.FAI, Format.GZI):
        a.role = LogicalRole.REFERENCE_INDEX
    elif f == Format.SEQUENCE_DICTIONARY:
        a.role = LogicalRole.SEQUENCE_DICTIONARY
    elif f == Format.PED:
        a.role = LogicalRole.PEDIGREE
    elif f in (Format.CHECKSUM_MD5, Format.CHECKSUM_SHA256):
        a.role = LogicalRole.CHECKSUM_SIDECAR
    elif is_phenotype:
        a.role = LogicalRole.PHENOTYPE_TERMS
    elif f == Format.PDF or lower.startswith(DOC_NAMES) or a.extension == ".md":
        a.role = LogicalRole.DOCUMENTATION
    elif f in (Format.JSON, Format.CSV, Format.TSV, Format.TEXT):
        a.role = LogicalRole.CASE_METADATA
    else:
        a.role = LogicalRole.UNKNOWN


def retention(a: Discovered) -> tuple[bool, RetentionClass]:
    if a.external:
        return False, RetentionClass.EXTERNAL_REFERENCE
    if a.fmt in GENOMIC | GENOMIC_INDEXES | OPAQUE:
        # Opaque binaries in a controlled genomic dataset are treated as genomic until shown otherwise.
        return True, RetentionClass.CONTROLLED_GENOMIC_DELETE_REQUIRED
    return True, RetentionClass.CONTROLLED_CASE_MATERIAL_REVIEW_REQUIRED


# ── relationships ────────────────────────────────────────────────────────────

# index format → (suffix rules, acceptable target formats)
_INDEX_RULES: dict[Format, tuple[list[tuple[str, str]], set[Format]]] = {
    Format.TBI: ([(".tbi", "")], {Format.VCF}),
    Format.CSI: ([(".csi", "")], {Format.VCF, Format.BCF, Format.BAM}),
    Format.BAI: ([(".bai", ""), (".bai", ".bam")], {Format.BAM}),
    Format.CRAI: ([(".crai", ""), (".crai", ".cram")], {Format.CRAM}),
    Format.FAI: ([(".fai", "")], {Format.FASTA}),
    Format.GZI: ([(".gzi", "")], {Format.FASTA}),
}
_DICT_TARGET_SUFFIXES = [".fa", ".fasta", ".fna", ".fa.gz", ".fasta.gz", ".fna.gz"]


@dataclass
class Links:
    index_of: dict[str, str] = field(default_factory=dict)  # data asset_id → index asset_id
    gzi_of: dict[str, str] = field(default_factory=dict)
    dict_of: dict[str, str] = field(default_factory=dict)  # fasta asset_id → dict asset_id
    sidecar_of: dict[str, str] = field(default_factory=dict)  # target asset_id → sidecar asset_id
    relationships: list[AssetRelationship] = field(default_factory=list)


def _siblings(rel: str, candidates: list[str], by_rel: dict[str, Discovered]) -> list[Discovered]:
    return [by_rel[c] for c in candidates if c in by_rel]


def link(assets: list[Discovered]) -> tuple[Links, list[Issue]]:
    by_rel = {a.rel: a for a in assets}
    links = Links()
    issues: list[Issue] = []
    for a in assets:
        if a.fmt in _INDEX_RULES:
            rules, targets = _INDEX_RULES[a.fmt]
            cands = []
            for suffix, replacement in rules:
                if a.rel.lower().endswith(suffix):
                    cands.append(a.rel[: -len(suffix)] + replacement)
            matched = [t for t in _siblings(a.rel, cands, by_rel) if t.fmt in targets]
            if not matched:
                issues.append(Issue(code=IssueCode.ORPHAN_INDEX, severity=Severity.WARNING, asset_ids=[a.asset_id],
                                    message=f"{a.fmt.value} index has no matching data file in the case.",
                                    suggested_action="Confirm whether its data file is missing or the index is stray."))
                continue
            target = matched[0]
            if a.fmt == Format.GZI:
                links.gzi_of[target.asset_id] = a.asset_id
                rtype = RelationshipType.BGZF_INDEX_OF
            else:
                if target.asset_id in links.index_of:
                    continue  # first (deterministic, sorted) index wins; others remain recorded assets
                links.index_of[target.asset_id] = a.asset_id
                rtype = RelationshipType.INDEX_OF
                if target.fmt == Format.BAM:
                    a.role = LogicalRole.ALIGNMENT_INDEX
            links.relationships.append(AssetRelationship(type=rtype, source=a.asset_id, target=target.asset_id,
                                                         evidence=["filename pairing", f"content verified as {a.fmt.value} ↔ {target.fmt.value}"]))
        elif a.fmt == Format.SEQUENCE_DICTIONARY and a.rel.endswith(".dict"):
            stem = a.rel[: -len(".dict")]
            cands = [stem + s for s in _DICT_TARGET_SUFFIXES]
            matched = [t for t in _siblings(a.rel, cands, by_rel) if t.fmt == Format.FASTA]
            for t in matched[:1]:
                links.dict_of[t.asset_id] = a.asset_id
                links.relationships.append(AssetRelationship(type=RelationshipType.SEQUENCE_DICTIONARY_OF, source=a.asset_id, target=t.asset_id,
                                                             evidence=["filename pairing"]))
        elif a.fmt in (Format.CHECKSUM_MD5, Format.CHECKSUM_SHA256):
            for suffix in (".md5", ".sha256"):
                if a.rel.lower().endswith(suffix) and a.rel[: -len(suffix)] in by_rel:
                    t = by_rel[a.rel[: -len(suffix)]]
                    links.sidecar_of[t.asset_id] = a.asset_id
                    links.relationships.append(AssetRelationship(type=RelationshipType.CHECKSUM_OF, source=a.asset_id, target=t.asset_id,
                                                                 evidence=["filename pairing"]))
    return links, issues


def read_sidecar_digest(path: Path, algorithm: str) -> str | None:
    try:
        token = path.read_text(encoding="utf-8").split()[0].lower()
    except (OSError, UnicodeDecodeError, IndexError):
        return None
    expected_len = 32 if algorithm == "md5" else 64
    return token if len(token) == expected_len and all(c in "0123456789abcdef" for c in token) else None


def bgzf_like(a: Discovered) -> bool:
    return a.sniff.compression in (Compression.BGZF, Compression.FORMAT_NATIVE)
