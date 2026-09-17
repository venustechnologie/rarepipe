"""Contig identity layer: source contig names → canonical assembly identities.

The source VCF is never rewritten. Each declared contig is bound, by name AND
length, to a row of a pinned NCBI assembly report; the binding records its basis.
Contigs the report does not describe (decoys, HLA, EBV…) are classified by an
explicitly-labelled name heuristic or left unbound — never discarded.
"""

from __future__ import annotations

import re
from collections import Counter

from rarepipe.resources.assembly import AssemblyReport, SequenceRow
from rarepipe.stages.intake.reference import canonical_key
from rarepipe.stages.normalize.model import ContigBinding, ContigClass, ContigSummary

ROLE_CLASS = {
    "alt-scaffold": ContigClass.ALTERNATE_LOCUS,
    "unlocalized-scaffold": ContigClass.UNLOCALIZED,
    "unplaced-scaffold": ContigClass.UNPLACED,
    "fix-patch": ContigClass.PATCH,
    "novel-patch": ContigClass.PATCH,
}


def _row_class(row: SequenceRow) -> ContigClass:
    if row.role == "assembled-molecule":
        return ContigClass.MITOCHONDRIAL if row.location_type.lower() == "mitochondrion" else ContigClass.PRIMARY_CHROMOSOME
    return ROLE_CLASS.get(row.role, ContigClass.UNKNOWN)


def _heuristic(name: str) -> ContigClass | None:
    key, _ = canonical_key(name)
    if key == "MT":
        return ContigClass.MITOCHONDRIAL
    if key:
        return ContigClass.PRIMARY_CHROMOSOME
    lower = name.lower()
    if lower.endswith("_alt"):
        return ContigClass.ALTERNATE_LOCUS
    if lower.endswith("_random"):
        return ContigClass.UNLOCALIZED
    if lower.startswith(("chrun_", "un_")) and not lower.endswith("_decoy"):
        return ContigClass.UNPLACED
    if lower.endswith("_decoy") or lower.startswith("jtfh01") or lower in ("hs38d1", "hs37d5"):
        return ContigClass.DECOY_OR_OTHER
    if name.startswith("HLA-") or lower in ("chrebv", "ebv", "nc_007605.1", "nc_007605"):
        return ContigClass.DECOY_OR_OTHER
    return None


def source_scheme(names: list[str]) -> str:
    prefixed = sum(1 for n in names if canonical_key(n)[0] and canonical_key(n)[1])
    numeric = sum(1 for n in names if canonical_key(n)[0] and not canonical_key(n)[1])
    if prefixed and numeric:
        return "mixed"
    return "chr_prefixed" if prefixed else "numeric" if numeric else "nonstandard"


def bind_contigs(contigs: list[tuple[str, int | None]], report: AssemblyReport | None, assembly: str,
                 records_per_contig: dict[str, int] | None) -> tuple[list[ContigBinding], ContigSummary]:
    idx = report.alias_index() if report else {}
    out: list[ContigBinding] = []
    for name, length in contigs:
        row = idx.get(name)
        records = (records_per_contig or {}).get(name) if records_per_contig is not None else None
        if row:
            conflict = length is not None and row.length is not None and length != row.length
            cls = _row_class(row)
            accession = row.refseq or row.genbank
            label = (f"chromosome {row.assigned_molecule}" if cls == ContigClass.PRIMARY_CHROMOSOME
                     else "mitochondrion" if cls == ContigClass.MITOCHONDRIAL else row.sequence_name)
            aliases = {k: v for k, v in (("sequence_name", row.sequence_name), ("genbank", row.genbank), ("refseq", row.refseq), ("ucsc", row.ucsc)) if v}
            out.append(ContigBinding(
                source_name=name, source_length=length, contig_class=cls,
                canonical_id=None if conflict else f"{assembly}:{accession}", label=label, aliases=aliases,
                basis="assembly_report_name_only" if (length is None or conflict) else "assembly_report_name_and_length",
                length_conflict=conflict, records=records,
            ))
            continue
        cls = _heuristic(name)
        out.append(ContigBinding(source_name=name, source_length=length, contig_class=cls or ContigClass.UNKNOWN,
                                 basis="name_heuristic" if cls else "unbound", records=records))

    with_records = sum(1 for b in out if b.records) if records_per_contig is not None else 0
    by_class = Counter(b.contig_class.value for b in out)
    rec_by_class: Counter = Counter()
    for b in out:
        if b.records:
            rec_by_class[b.contig_class.value] += b.records
    summary = ContigSummary(
        source_scheme=source_scheme([n for n, _ in contigs]), declared=len(out), with_records=with_records,
        by_class=dict(sorted(by_class.items())), records_by_class=dict(sorted(rec_by_class.items())),
        by_basis=dict(sorted(Counter(b.basis for b in out).items())), length_conflicts=sum(1 for b in out if b.length_conflict),
    )
    return out, summary


_ASSEMBLY_NAME = re.compile(r"^(GRCh\d+|T2T-CHM13)", re.I)


def report_matches_assembly(report: AssemblyReport, assembly: str) -> bool:
    m = _ASSEMBLY_NAME.match(report.assembly_name or "")
    return bool(m) and m.group(1).lower() == assembly.split("+")[0].lower()
