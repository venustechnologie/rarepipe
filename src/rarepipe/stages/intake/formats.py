"""Content-first format detection.

The filename *claims* a format; the bytes *are* a format. Both are recorded and
disagreement is surfaced, never silently reconciled. Only a bounded prefix of
each file is read (magic bytes + first decompressed block), plus the final 28
bytes for BGZF end-of-file checks.
"""

from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path

from rarepipe.stages.intake.manifest import Compression, Format

HEAD_BYTES = 256 * 1024
TEXT_SNIFF_CHARS = 64 * 1024
JSON_FULL_PARSE_LIMIT = 32 * 1024 * 1024

BGZF_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")

# Longest suffix wins.
EXTENSION_FORMATS: dict[str, Format] = {
    ".vcf": Format.VCF, ".vcf.gz": Format.VCF, ".vcf.bgz": Format.VCF, ".g.vcf.gz": Format.VCF,
    ".bcf": Format.BCF, ".bam": Format.BAM, ".cram": Format.CRAM, ".sam": Format.SAM,
    ".tbi": Format.TBI, ".csi": Format.CSI, ".bai": Format.BAI, ".crai": Format.CRAI, ".gzi": Format.GZI,
    ".fa": Format.FASTA, ".fasta": Format.FASTA, ".fna": Format.FASTA,
    ".fa.gz": Format.FASTA, ".fasta.gz": Format.FASTA, ".fna.gz": Format.FASTA,
    ".fastq": Format.FASTQ, ".fq": Format.FASTQ, ".fastq.gz": Format.FASTQ, ".fq.gz": Format.FASTQ,
    ".docx": Format.DOCX, ".fai": Format.FAI, ".dict": Format.SEQUENCE_DICTIONARY,
    ".ped": Format.PED, ".fam": Format.PED,
    ".json": Format.JSON, ".csv": Format.CSV, ".tsv": Format.TSV,
    ".txt": Format.TEXT, ".md": Format.TEXT, ".obo": Format.TEXT,
    ".pdf": Format.PDF, ".md5": Format.CHECKSUM_MD5, ".sha256": Format.CHECKSUM_SHA256,
}

TEXTUAL_COMPATIBLE = {Format.TEXT, Format.TSV, Format.CSV}
# Suffixes browsers/transfer clients append to files that have not finished downloading.
PARTIAL_DOWNLOAD_SUFFIXES = (".download-part", ".crdownload", ".partial", ".part", ".download", ".aria2", ".!ut", ".filepart")
APPLEDOUBLE_MAGIC = b"\x00\x05\x16\x07"

PLAIN_TEXT_KINDS = TEXTUAL_COMPATIBLE | {Format.PED, Format.JSON, Format.CHECKSUM_MD5, Format.CHECKSUM_SHA256}

_FASTA_SEQ = re.compile(r"^[A-Za-z*\-.]+$")
_MD5_LINE = re.compile(r"^[0-9a-fA-F]{32}(\s+\*?\S.*)?$")
_SHA256_LINE = re.compile(r"^[0-9a-fA-F]{64}(\s+\*?\S.*)?$")


@dataclass(frozen=True)
class Sniff:
    format: Format
    compression: Compression
    bgzf_eof_present: bool | None = None
    note: str | None = None


def partial_download_suffix(filename: str) -> str | None:
    lower = filename.lower()
    return next((s for s in PARTIAL_DOWNLOAD_SUFFIXES if lower.endswith(s)), None)


def strip_partial_suffix(filename: str) -> str:
    suffix = partial_download_suffix(filename)
    return filename[: -len(suffix)] if suffix else filename


def split_extension(filename: str) -> str:
    lower = strip_partial_suffix(filename).lower()
    best = ""
    for ext in EXTENSION_FORMATS:
        if lower.endswith(ext) and len(ext) > len(best):
            best = ext
    if best:
        return best
    suffix = Path(lower).suffix
    return suffix


def extension_format(filename: str) -> Format | None:
    return EXTENSION_FORMATS.get(split_extension(filename))


def has_bgzf_eof(path: Path) -> bool:
    size = path.stat().st_size
    if size < len(BGZF_EOF):
        return False
    with path.open("rb") as fh:
        fh.seek(size - len(BGZF_EOF))
        return fh.read() == BGZF_EOF


BGZF_MAX_BLOCK = 65536


def block_gzip_tail_intact(path: Path) -> bool:
    """For block-gzip files (BGZF-style 'BC' extra field) that lack the BGZF EOF marker — typical of
    Illumina FASTQ writers — prove the file ends on a complete block: find the last block header whose
    BSIZE ends exactly at end-of-file and decompress it (zlib verifies CRC32 and ISIZE)."""
    size = path.stat().st_size
    span = min(size, BGZF_MAX_BLOCK + 28)
    with path.open("rb") as fh:
        fh.seek(size - span)
        tail = fh.read(span)
    pos = tail.rfind(b"\x1f\x8b\x08\x04")
    while pos != -1:
        if tail[pos + 12 : pos + 14] == b"BC" and pos + 18 <= len(tail):
            bsize = int.from_bytes(tail[pos + 16 : pos + 18], "little")
            if pos + bsize + 1 == len(tail):
                d = zlib.decompressobj(31)
                try:
                    d.decompress(tail[pos:])
                    return d.eof and not d.unused_data
                except zlib.error:
                    return False
        pos = tail.rfind(b"\x1f\x8b\x08\x04", 0, pos)
    return False


def _gunzip_prefix(raw: bytes, limit: int = HEAD_BYTES) -> bytes:
    """Decompress the leading gzip members (BGZF blocks) contained in `raw`."""
    out = bytearray()
    data = raw
    while data and len(out) < limit:
        d = zlib.decompressobj(31)
        try:
            out += d.decompress(data, limit - len(out))
        except zlib.error:
            break
        if not d.eof:
            break
        data = d.unused_data
        if not data.startswith(b"\x1f\x8b"):
            break
    return bytes(out)


def _is_bgzf(raw: bytes) -> bool:
    return len(raw) >= 18 and raw[:2] == b"\x1f\x8b" and raw[3] & 0x04 and raw[12:14] == b"BC"


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:TEXT_SNIFF_CHARS]:
        return None
    sample = data[:TEXT_SNIFF_CHARS]
    # tolerate a multibyte character cut at the sniff boundary
    for trim in range(4):
        try:
            text = sample[: len(sample) - trim].decode("utf-8")
        except UnicodeDecodeError:
            continue
        controls = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\n\r\f")
        return text if controls <= max(1, len(text) // 100) else None
    return None


def _data_lines(text: str, *, drop_last: bool) -> list[str]:
    lines = text.splitlines()
    if drop_last and lines:
        lines = lines[:-1]  # possibly truncated by the sniff window
    return [ln for ln in lines if ln.strip()]


def _classify_text(text: str, full: bool, path: Path, ext_fmt: Format | None) -> Format:
    lines = _data_lines(text, drop_last=not full)
    if not lines:
        return Format.EMPTY if not text.strip() else Format.TEXT
    first = lines[0]
    if first.startswith("##fileformat=VCF"):
        return Format.VCF
    if first.startswith(">") and len(lines) > 1 and _FASTA_SEQ.match(lines[1].strip()):
        return Format.FASTA
    if _looks_like_fastq(lines):
        return Format.FASTQ
    if first.startswith(("@HD", "@SQ")):
        return Format.SEQUENCE_DICTIONARY if all(ln.startswith("@") for ln in lines) else Format.SAM
    if len(lines) == 1 and _MD5_LINE.match(first.strip()):
        return Format.CHECKSUM_MD5
    if len(lines) == 1 and _SHA256_LINE.match(first.strip()):
        return Format.CHECKSUM_SHA256
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        if path.stat().st_size <= JSON_FULL_PARSE_LIMIT:
            try:
                json.loads(path.read_text(encoding="utf-8"))
                return Format.JSON
            except (ValueError, UnicodeDecodeError):
                pass
    if _looks_like_fai(lines):
        return Format.FAI
    if _looks_like_ped(lines, ext_fmt):
        return Format.PED
    return _delimited(lines)


def _looks_like_fastq(lines: list[str]) -> bool:
    records = [lines[i : i + 4] for i in range(0, min(len(lines), 40) - 3, 4)]
    if not records:
        return False
    return all(r[0].startswith("@") and r[2].startswith("+") and len(r[1]) == len(r[3]) for r in records)


def _is_docx(path: Path) -> bool:
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            return "word/document.xml" in zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def _looks_like_fai(lines: list[str]) -> bool:
    for ln in lines[:200]:
        cols = ln.split("\t")
        if len(cols) not in (5, 6) or not all(c.isdigit() for c in cols[1:]):
            return False
    return True


def _looks_like_ped(lines: list[str], ext_fmt: Format | None) -> bool:
    header_hint = any(ln.startswith("#") and re.search(r"famil|individual|paternal|father", ln, re.I) for ln in lines[:3])
    if ext_fmt != Format.PED and not header_hint:
        return False  # six whitespace columns alone is too weak to claim a pedigree
    data = [ln for ln in lines if not ln.startswith("#")]
    if not data:
        return False
    for ln in data[:500]:
        cols = ln.split()
        if len(cols) < 6 or cols[4] not in {"0", "1", "2", "other", "-9"}:
            return False
    return True


def _delimited(lines: list[str]) -> Format:
    sample = [ln for ln in lines[:200] if not ln.startswith("#")] or lines[:200]
    for delim, fmt in (("\t", Format.TSV), (",", Format.CSV)):
        counts = {ln.count(delim) for ln in sample}
        if len(sample) >= 2 and len(counts) == 1 and next(iter(counts)) >= 1:
            return fmt
    return Format.TEXT


def sniff(path: Path, ext_fmt: Format | None) -> Sniff:
    size = path.stat().st_size
    if size == 0:
        return Sniff(Format.EMPTY, Compression.NONE)
    with path.open("rb") as fh:
        raw = fh.read(HEAD_BYTES)
    full = size <= HEAD_BYTES

    if raw[:4] == b"CRAM":
        return Sniff(Format.CRAM, Compression.FORMAT_NATIVE)
    if raw[:4] == b"BAI\x01":
        return Sniff(Format.BAI, Compression.NONE)
    if raw[:4] == b"%PDF":
        return Sniff(Format.PDF, Compression.NONE)
    if raw[:4] == APPLEDOUBLE_MAGIC:
        return Sniff(Format.APPLEDOUBLE, Compression.NONE)
    if raw[:4] == b"PK\x03\x04" and _is_docx(path):
        return Sniff(Format.DOCX, Compression.FORMAT_NATIVE)

    if raw[:2] == b"\x1f\x8b":
        bgzf = _is_bgzf(raw)
        eof = has_bgzf_eof(path) if bgzf else None
        compression = Compression.BGZF if bgzf else Compression.GZIP
        inner = _gunzip_prefix(raw)
        if inner[:4] == b"BAM\x01":
            return Sniff(Format.BAM, Compression.FORMAT_NATIVE, eof)
        if inner[:3] == b"BCF" and inner[3:4] in (b"\x02",):
            return Sniff(Format.BCF, Compression.FORMAT_NATIVE, eof)
        if inner[:4] == b"TBI\x01":
            return Sniff(Format.TBI, compression, eof)
        if inner[:4] == b"CSI\x01":
            return Sniff(Format.CSI, compression, eof)
        text = _decode_text(inner)
        if text is None:
            return Sniff(Format.GZIP_UNKNOWN, compression, eof)
        lines = _data_lines(text, drop_last=True) or _data_lines(text, drop_last=False)
        if text.startswith("##fileformat=VCF"):
            return Sniff(Format.VCF, compression, eof)
        if text.startswith(">"):
            return Sniff(Format.FASTA, compression, eof)
        if _looks_like_fastq(lines):
            return Sniff(Format.FASTQ, compression, eof)
        if lines and all(len(ln.split("\t")) == 6 and all(c.lstrip("-").isdigit() for c in ln.split("\t")) for ln in lines[:200]):
            return Sniff(Format.CRAI, compression, eof)
        return Sniff(Format.GZIP_UNKNOWN, compression, eof, note="gzip-compressed content of unrecognized type")

    # GZI has no magic: uint64 count followed by count*(uint64, uint64).
    if ext_fmt == Format.GZI and size >= 8 and (size - 8) % 16 == 0:
        if int.from_bytes(raw[:8], "little") * 16 + 8 == size:
            return Sniff(Format.GZI, Compression.NONE)

    text = _decode_text(raw)
    if text is None:
        return Sniff(Format.BINARY_UNKNOWN, Compression.NONE)
    return Sniff(_classify_text(text, full, path, ext_fmt), Compression.NONE)


def is_mismatch(ext_fmt: Format | None, detected: Format) -> bool:
    """True when the filename claims one format and the content is another.

    Generic text names (.txt/.tsv/.csv/.md) holding plain-text formats are not
    a mismatch; everything else that disagrees is.
    """
    if ext_fmt is None or ext_fmt == detected:
        return False
    if ext_fmt in TEXTUAL_COMPATIBLE and detected in PLAIN_TEXT_KINDS:
        return False
    return True
