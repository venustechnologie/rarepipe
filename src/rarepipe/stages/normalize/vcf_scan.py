"""Full-stream VCF characterization.

Two independent passes over the complete file:
1. a strict text parser (this module) that validates every record and
   accumulates aggregate statistics only — no record, allele or genotype value
   is retained, logged, or returned;
2. an htslib pass (the reader downstream tools will use) that must read the
   same number of records.
Nothing is filtered, rewritten, or dropped.
"""

from __future__ import annotations

import gzip
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pysam

pysam.set_verbosity(0)

_REF_OK = re.compile(rb"^[ACGTNacgtn]+$")
_BASES = re.compile(rb"^[ACGTNacgtn]+$")
_GT_SPLIT = re.compile(rb"[/|]")
MAX_LINE_NUMBERS = 20
PROGRESS_EVERY = 250_000


@dataclass
class ScanResult:
    data_lines: int = 0
    records_parsed: int = 0
    malformed: int = 0
    malformed_lines: list[int] = field(default_factory=list)
    header_ok: bool = True
    sample_count: int = 0
    out_of_order: int = 0
    noncontiguous: int = 0
    order_follows_header: bool = True
    undeclared_contig_records: int = 0
    exact_duplicates: int = 0
    sharing_position: int = 0
    invalid_ref: int = 0
    invalid_alt: int = 0
    pass_records: int = 0
    missing_filter: int = 0
    non_pass: int = 0
    by_filter: Counter = field(default_factory=Counter)
    multi_filter: int = 0
    record_classes: Counter = field(default_factory=Counter)
    allele_classes: Counter = field(default_factory=Counter)
    multiallelic: int = 0
    max_alts: int = 0
    spanning_deletion_records: int = 0
    qual_missing: int = 0
    per_contig: Counter = field(default_factory=Counter)
    fmt_declaring: Counter = field(default_factory=Counter)
    fmt_populated: Counter = field(default_factory=Counter)
    gt: Counter = field(default_factory=Counter)
    ploidy: Counter = field(default_factory=Counter)
    het_phased: int = 0
    genotype_malformed: int = 0
    htslib_records: int | None = None
    htslib_error: bool = False
    streamed_completely: bool = False
    elapsed: float = 0.0


def classify_allele(ref: bytes, alt: bytes) -> str | None:
    """Mechanical class of one REF/ALT pair; None if ALT syntax is invalid."""
    if alt == b"*":
        return "spanning_deletion"
    if alt == b".":
        return "no_alt"
    if alt.startswith(b"<") and alt.endswith(b">") and len(alt) > 2:
        return "symbolic"
    if b"[" in alt or b"]" in alt or (len(alt) > 1 and (alt.startswith(b".") or alt.endswith(b"."))):
        return "breakend"
    if not _BASES.match(alt):
        return None
    lr, la = len(ref), len(alt)
    r, a = ref.upper(), alt.upper()
    if lr == la:
        if r == a:
            return "other"
        return "snv" if lr == 1 else "mnv"
    if la > lr:
        return "insertion" if a.startswith(r) else "complex"
    return "deletion" if r.startswith(a) else "complex"


def _populated(v: bytes) -> bool:
    return v.strip(b".,/|") != b""


def scan(path: Path, header_contigs: list[str], filter_ids: set[str], progress: Callable[[int, int], None] | None = None) -> ScanResult:
    res = ScanResult()
    t0 = time.monotonic()
    contig_index = {name.encode(): i for i, name in enumerate(header_contigs)}
    declared = set(contig_index)
    filter_ids_b = {f.encode() for f in filter_ids}
    total_bytes = path.stat().st_size

    with path.open("rb") as raw, gzip.open(raw, "rb") as fh:
        n_samples = 0
        expected_cols = 8
        line_no = 0
        prev_chrom: bytes | None = None
        prev_pos = -1
        prev_contig_idx = -1
        seen_contigs: set[bytes] = set()
        pos_keys: set[bytes] = set()
        next_extra_index = len(contig_index)

        for line in fh:
            line_no += 1
            if line.startswith(b"##"):
                continue
            if line.startswith(b"#CHROM"):
                cols = line.rstrip(b"\r\n").split(b"\t")
                n_samples = max(0, len(cols) - 9)
                expected_cols = 9 + n_samples if n_samples else (9 if len(cols) == 9 else 8)
                res.sample_count = n_samples
                continue
            if line.startswith(b"#"):
                continue

            res.data_lines += 1
            if progress and res.data_lines % PROGRESS_EVERY == 0:
                progress(raw.tell(), total_bytes)
            cols = line.rstrip(b"\r\n").split(b"\t")
            try:
                if len(cols) != expected_cols:
                    raise ValueError
                chrom, pos_b, _id, ref, alt_field, qual, filt = cols[:7]
                pos = int(pos_b)
                if pos < 0 or not chrom:
                    raise ValueError
                if qual != b".":
                    float(qual)
            except ValueError:
                res.malformed += 1
                if len(res.malformed_lines) < MAX_LINE_NUMBERS:
                    res.malformed_lines.append(line_no)
                continue
            res.records_parsed += 1
            res.per_contig[chrom] += 1

            # ── ordering / duplicates
            if chrom != prev_chrom:
                if chrom in seen_contigs:
                    res.noncontiguous += 1
                idx = contig_index.get(chrom)
                if idx is None:
                    contig_index[chrom] = idx = next_extra_index
                    next_extra_index += 1
                if idx < prev_contig_idx:
                    res.order_follows_header = False
                seen_contigs.add(chrom)
                prev_chrom, prev_pos, prev_contig_idx = chrom, -1, idx
                pos_keys = set()
            if chrom not in declared:
                res.undeclared_contig_records += 1
            if pos < prev_pos:
                res.out_of_order += 1
            if pos != prev_pos:
                pos_keys = set()
            else:
                res.sharing_position += 1
            key = ref + b"\t" + alt_field
            if key in pos_keys:
                res.exact_duplicates += 1
            pos_keys.add(key)
            prev_pos = max(prev_pos, pos)

            # ── alleles
            if not _REF_OK.match(ref):
                res.invalid_ref += 1
            alts = alt_field.split(b",")
            if len(alts) > res.max_alts:
                res.max_alts = len(alts)
            record_class = "other"
            has_span = False
            for alt in alts:
                cls = classify_allele(ref, alt)
                if cls is None:
                    res.invalid_alt += 1
                    cls = "other"
                res.allele_classes[cls] += 1
                has_span = has_span or cls == "spanning_deletion"
                record_class = cls
            if has_span:
                res.spanning_deletion_records += 1
            if len(alts) > 1:
                res.multiallelic += 1
                res.record_classes["multiallelic"] += 1
            else:
                res.record_classes[record_class] += 1

            # ── FILTER / QUAL
            if filt == b"PASS":
                res.pass_records += 1
            elif filt == b".":
                res.missing_filter += 1
            else:
                res.non_pass += 1
                parts = filt.split(b";")
                if len(parts) > 1:
                    res.multi_filter += 1
                for p in parts:
                    res.by_filter[p.decode("ascii", "replace")] += 1
            if qual == b".":
                res.qual_missing += 1

            # ── FORMAT / genotypes (single sample expected; all samples aggregated otherwise)
            if n_samples:
                keys = cols[8].split(b":")
                gt_idx = keys.index(b"GT") if b"GT" in keys else -1
                for s in cols[9:]:
                    values = s.split(b":")
                    for i, k in enumerate(keys):
                        res.fmt_declaring[k] += 1
                        if i < len(values) and _populated(values[i]):
                            res.fmt_populated[k] += 1
                    if gt_idx >= 0:
                        _genotype(values[gt_idx] if gt_idx < len(values) else b".", len(alts), res)

        res.streamed_completely = True
        if progress:
            progress(total_bytes, total_bytes)

    res.htslib_records, res.htslib_error = _htslib_count(path)
    res.elapsed = round(time.monotonic() - t0, 2)
    return res


def _genotype(gt: bytes, n_alts: int, res: ScanResult) -> None:
    parts = _GT_SPLIT.split(gt)
    res.ploidy[str(len(parts))] += 1
    called = []
    for p in parts:
        if p == b".":
            continue
        if not p.isdigit() or int(p) > n_alts:
            res.genotype_malformed += 1
            return
        called.append(int(p))
    if not called:
        res.gt["missing"] += 1
        return
    if len(called) < len(parts):
        res.gt["partially_missing"] += 1
        return
    if len(parts) == 1:
        res.gt["haploid_called"] += 1
        return
    distinct = set(called)
    if distinct == {0}:
        res.gt["hom_ref"] += 1
    elif len(distinct) == 1:
        res.gt["hom_alt"] += 1
    elif 0 in distinct:
        res.gt["het"] += 1
        if b"|" in gt:
            res.het_phased += 1
    else:
        res.gt["het_non_ref"] += 1
        if b"|" in gt:
            res.het_phased += 1


def _htslib_count(path: Path) -> tuple[int | None, bool]:
    n = 0
    try:
        with pysam.VariantFile(str(path)) as vf:
            for _ in vf:
                n += 1
    except (OSError, ValueError):
        return n, True
    return n, False
