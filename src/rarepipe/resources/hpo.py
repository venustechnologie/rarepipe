"""Minimal, dependency-free reader for the HPO OBO release.

Only what identity normalization needs: id, name, obsolescence, replaced_by,
consider, alt_id, and is_a (used solely to name which top-level HPO branch a
*supplied* term belongs to — no terms are ever added).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = "HP:0000001"
BRANCHES = {
    "HP:0000118": "phenotypic_abnormality",
    "HP:0000005": "mode_of_inheritance",
    "HP:0012823": "clinical_modifier",
    "HP:0031797": "clinical_course",
    "HP:0040279": "frequency",
    "HP:0032443": "past_medical_history",
    "HP:0032223": "blood_group",
}


@dataclass
class Term:
    id: str
    name: str | None = None
    is_obsolete: bool = False
    replaced_by: list[str] = field(default_factory=list)
    consider: list[str] = field(default_factory=list)
    alt_ids: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)


@dataclass
class Ontology:
    data_version: str | None
    format_version: str | None
    terms: dict[str, Term]
    alt_index: dict[str, str]

    def branches(self, term_id: str) -> list[str]:
        found, seen, stack = set(), set(), [term_id]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur in BRANCHES:
                found.add(BRANCHES[cur])
                continue
            t = self.terms.get(cur)
            if t:
                stack.extend(t.parents)
        return sorted(found)


def _value(raw: str) -> str:
    return raw.split(" ! ", 1)[0].strip()


def load_obo(path: Path) -> Ontology:
    header: dict[str, str] = {}
    terms: dict[str, Term] = {}
    cur: Term | None = None
    in_term = False
    in_header = True
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("["):
                in_header = False
                in_term = line.strip() == "[Term]"
                cur = None
                continue
            if not line or ":" not in line:
                continue
            key, raw = line.split(":", 1)
            raw = raw.strip()
            if in_header:
                header.setdefault(key, raw)
                continue
            if not in_term:
                continue
            if key == "id":
                cur = Term(id=raw)
                terms[raw] = cur
            elif cur is None:
                continue
            elif key == "name":
                cur.name = raw
            elif key == "is_obsolete":
                cur.is_obsolete = raw.lower() == "true"
            elif key == "replaced_by":
                cur.replaced_by.append(_value(raw))
            elif key == "consider":
                cur.consider.append(_value(raw))
            elif key == "alt_id":
                cur.alt_ids.append(_value(raw))
            elif key == "is_a":
                cur.parents.append(_value(raw).split()[0])
    alt_index = {alt: t.id for t in terms.values() for alt in t.alt_ids}
    return Ontology(data_version=header.get("data-version"), format_version=header.get("format-version"), terms=terms, alt_index=alt_index)


def release_date(ontology: Ontology) -> str | None:
    """'hp/releases/2025-05-06' → '2025-05-06'."""
    dv = ontology.data_version
    return dv.rsplit("/", 1)[-1] if dv else None
