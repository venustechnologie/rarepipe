"""NCBI assembly report reader (e.g. GCF_000001405.40_GRCh38.p14_assembly_report.txt).

Provides authoritative sequence roles and name aliases (Sequence-Name, GenBank,
RefSeq, UCSC) with lengths, so source contig names can be bound to canonical
identities without rewriting any source file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SequenceRow:
    sequence_name: str
    role: str
    assigned_molecule: str
    location_type: str
    genbank: str | None
    refseq: str | None
    unit: str
    length: int | None
    ucsc: str | None


@dataclass
class AssemblyReport:
    assembly_name: str | None
    genbank_accession: str | None
    refseq_accession: str | None
    rows: list[SequenceRow]

    def alias_index(self) -> dict[str, SequenceRow]:
        idx: dict[str, SequenceRow] = {}
        for r in self.rows:
            for alias in (r.sequence_name, r.genbank, r.refseq, r.ucsc):
                if alias:
                    idx.setdefault(alias, r)
        return idx


def _na(v: str) -> str | None:
    return None if v in ("na", "", "<>") else v


def load_assembly_report(path: Path) -> AssemblyReport:
    meta: dict[str, str] = {}
    columns: list[str] | None = None
    rows: list[SequenceRow] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.startswith("# Sequence-Name"):
                columns = line[2:].split("\t")
                continue
            if line.startswith("#"):
                if ":" in line:
                    k, v = line[1:].split(":", 1)
                    meta[k.strip()] = v.strip()
                continue
            if not line.strip() or columns is None:
                continue
            rec = dict(zip(columns, line.split("\t")))
            length = rec.get("Sequence-Length", "")
            rows.append(SequenceRow(
                sequence_name=rec.get("Sequence-Name", ""), role=rec.get("Sequence-Role", ""),
                assigned_molecule=rec.get("Assigned-Molecule", ""), location_type=rec.get("Assigned-Molecule-Location/Type", ""),
                genbank=_na(rec.get("GenBank-Accn", "")), refseq=_na(rec.get("RefSeq-Accn", "")), unit=rec.get("Assembly-Unit", ""),
                length=int(length) if length.isdigit() else None, ucsc=_na(rec.get("UCSC-style-name", "")),
            ))
    return AssemblyReport(assembly_name=meta.get("Assembly name"), genbank_accession=meta.get("GenBank assembly accession"),
                          refseq_accession=meta.get("RefSeq assembly accession"), rows=rows)
