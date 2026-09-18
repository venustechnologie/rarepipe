"""The disclosure boundary, enforced in code rather than by discipline.

Policy (set by the project owner): retrieval is local, bulk, or gene-level. Case-specific
variant identity — coordinates, HGVS, rsIDs, ClinVar variation IDs, protein changes, variant
pairs, HPO combinations — must never be transmitted externally by default. If exact-variant
querying becomes necessary, the stage stops and asks for approval instead of doing it.

Every outbound query passes through `check_query`. A query that looks case-specific raises
`DisclosureRefused`, which is a bug to fix or a decision to escalate — never something to
work around.
"""

from __future__ import annotations

import re

# Patterns that would identify this child's variants to a third party.
CASE_SPECIFIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("genomic coordinate", re.compile(r"\b(chr)?(\d{1,2}|X|Y|MT?)[:\-]\d{3,}\b", re.I)),
    ("HGVS coding/genomic", re.compile(r"\b[NX][MRCG]_\d+(\.\d+)?\s*:\s*[cgnmr]\.", re.I)),
    ("HGVS protein", re.compile(r"\bp\.\(?[A-Z][a-z]{2}\d+", re.I)),
    ("protein change shorthand", re.compile(r"\b[A-Z]\d{2,5}[A-Z]\b")),
    ("dbSNP identifier", re.compile(r"\brs\d{4,}\b", re.I)),
    ("ClinVar variation id", re.compile(r"\b(variation[_ ]?id|VCV)\s*:?\s*\d{3,}\b", re.I)),
    ("HPO identifier", re.compile(r"\bHP:\d{7}\b")),
    ("bare allele change", re.compile(r"\b\d{4,}\s*[ACGT]+\s*>\s*[ACGT]+\b", re.I)),
]


class DisclosureRefused(RuntimeError):
    """Raised instead of transmitting case-specific information."""

    def __init__(self, query: str, reason: str):
        self.query, self.reason = query, reason
        super().__init__(f"refusing to transmit a case-specific query ({reason}). "
                         f"Gene-level or bulk retrieval only; exact-variant lookup needs explicit approval.")


def case_specific_reasons(query: str) -> list[str]:
    return [name for name, pattern in CASE_SPECIFIC_PATTERNS if pattern.search(query or "")]


def check_query(query: str) -> str:
    """Returns the query if it is safe to send; raises DisclosureRefused otherwise."""
    reasons = case_specific_reasons(query)
    if reasons:
        raise DisclosureRefused(query, ", ".join(reasons))
    return query


def approval_gate(what: str) -> None:
    """Called where exact-variant retrieval would be required. Always stops."""
    raise DisclosureRefused(what, "exact-variant external querying requires explicit operator approval")
