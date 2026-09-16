"""Pedigree intake: record only relationships a file explicitly asserts.

PED/FAM columns: family, individual, paternal, maternal, sex, phenotype.
VCF ``##PEDIGREE`` header lines are also honoured when they name Father/Mother.
Filenames, sample-label patterns and sample order are never pedigree evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.issues import Issue, IssueCode, Severity

MISSING = {"0", "", ".", "-9", "NA"}
SEX = {"1": "male", "2": "female"}
AFFECTED = {"2": "affected", "1": "unaffected"}


@dataclass
class PedRow:
    family: str
    individual: str
    father: str | None
    mother: str | None
    sex: str
    affected: str


@dataclass
class ParsedPedigree:
    rows: list[PedRow] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def parse_ped(path: Path, asset_id: str) -> ParsedPedigree:
    out = ParsedPedigree()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        out.issues.append(Issue(code=IssueCode.PEDIGREE_PARSE_FAILED, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                                message=f"Pedigree file could not be read ({type(exc).__name__})."))
        return out
    bad = 0
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split()
        if len(cols) < 6:
            bad += 1
            continue
        fam, ind, pat, mat, sex, pheno = cols[:6]
        out.rows.append(PedRow(fam, ind, None if pat in MISSING else pat, None if mat in MISSING else mat,
                               SEX.get(sex, "unknown"), AFFECTED.get(pheno, "unknown")))
    if bad:
        out.issues.append(Issue(code=IssueCode.PEDIGREE_PARSE_FAILED, severity=Severity.WARNING, asset_ids=[asset_id],
                                message=f"{bad} pedigree line(s) have fewer than 6 columns and were not interpreted."))

    ids = [r.individual for r in out.rows]
    if len(ids) != len(set(ids)):
        out.issues.append(Issue(code=IssueCode.PEDIGREE_INCONSISTENT, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                                message="An individual appears on more than one pedigree line."))
    sex_of = {r.individual: r.sex for r in out.rows}
    for r in out.rows:
        if r.father and sex_of.get(r.father) == "female":
            out.issues.append(Issue(code=IssueCode.PEDIGREE_INCONSISTENT, severity=Severity.WARNING, asset_ids=[asset_id],
                                    message="An individual listed as a father is recorded with female sex."))
        if r.mother and sex_of.get(r.mother) == "male":
            out.issues.append(Issue(code=IssueCode.PEDIGREE_INCONSISTENT, severity=Severity.WARNING, asset_ids=[asset_id],
                                    message="An individual listed as a mother is recorded with male sex."))
        if r.father and r.father == r.mother:
            out.issues.append(Issue(code=IssueCode.PEDIGREE_INCONSISTENT, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                                    message="An individual has the same father and mother identifier."))
    return out


def vcf_pedigree_pairs(path: Path) -> list[tuple[str, str]]:
    """(child, parent) pairs from ##PEDIGREE=<...,Father=..,Mother=..> header lines."""
    import pysam

    pairs = []
    try:
        with pysam.VariantFile(str(path)) as vf:
            for rec in vf.header.records:
                if rec.key != "PEDIGREE" or rec.type != "STRUCTURED":
                    continue
                items = dict(rec.items())
                child = items.get("ID") or items.get("Child") or items.get("Name_0")
                for parent_key in ("Father", "Mother"):
                    if child and items.get(parent_key):
                        pairs.append((child, items[parent_key]))
    except (OSError, ValueError):
        return []
    return pairs
