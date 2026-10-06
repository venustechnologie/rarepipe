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
from dataclasses import dataclass
from pathlib import Path

# Patterns that would identify this child's variants to a third party.
CASE_SPECIFIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("genomic coordinate", re.compile(r"\b(chr)?(\d{1,2}|X|Y|MT?)[:\-]\d{3,}\b", re.I)),
    ("HGVS coding/genomic", re.compile(r"\b[NX][MRCG]_\d+(\.\d+)?\s*:\s*[cgnmr]\.", re.I)),
    ("HGVS protein", re.compile(r"\bp\.\(?[A-Z][a-z]{2}\d+", re.I)),
    ("protein change shorthand", re.compile(r"\b[A-Z]\d{2,5}[A-Z]\b")),
    # A bare residue position identifies a variant as surely as a substitution does, and it was not
    # gated at all until the provenance work exposed it: "K668" matched no pattern, so the private
    # cross-check below had nothing to compare. Tightening, which is the safe direction.
    ("residue position", re.compile(r"\b[ACDEFGHIKLMNPQRSTVWY]\d{2,5}\b")),
    ("dbSNP identifier", re.compile(r"\brs\d{4,}\b", re.I)),
    ("ClinVar variation id", re.compile(r"\b(variation[_ ]?id|VCV)\s*:?\s*\d{3,}\b", re.I)),
    ("HPO identifier", re.compile(r"\bHP:\d{7}\b")),
    ("bare allele change", re.compile(r"\b\d{4,}\s*[ACGT]+\s*>\s*[ACGT]+\b", re.I)),
]


# Residue-shaped patterns are the only ones a public provenance can release. A coordinate, an rsID, a
# ClinVar id or an HPO code is identity-grade whatever its origin, so provenance never unlocks those.
# Attestation must pre-exist the release decision. A provenance may therefore only point at the
# committed literature snapshots: a caller cannot write a file during the call and attest against it,
# and nothing it supplies as metadata is consulted — only the stored text is.
ATTESTATION_BASE = Path(__file__).resolve().parents[4] / "data" / "literature"

RESIDUE_SHAPED = {"protein change shorthand", "residue position", "HGVS protein"}
RESIDUE_TOKEN = re.compile(
    r"\b[A-Z]\d{2,5}[A-Z]\b"                      # K668A
    r"|\b[ACDEFGHIKLMNPQRSTVWY]\d{2,5}\b"          # K668
    r"|\bp\.\(?[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2})?\)?")   # p.Lys668Arg / p.(Lys668)


@dataclass(frozen=True)
class PublicResidueProvenance:
    """Why a residue in an outbound query is a published fact rather than this child's.

    Not a whitelist of syntax. Each token must be named here AND found verbatim in the stored public
    document that attests it, so the licence is per token and per source and is checkable after the
    fact. A token that is also the case's own residue is refused however well attested it is: the
    private boundary is not a question of whether a string is public somewhere.
    """

    residues: tuple[str, ...]
    source_id: str
    corpus_roots: tuple[Path, ...]
    reason: str = ""

    def roots_are_committed_evidence(self) -> bool:
        """Every root must lie inside the committed snapshot tree.

        This is what makes the attestation pre-existing rather than manufactured: a scratch directory
        written during the call cannot attest anything, however the provenance describes itself.
        """
        if not self.corpus_roots:
            return False
        for root in self.corpus_roots:
            try:
                Path(root).resolve().relative_to(ATTESTATION_BASE)
            except (ValueError, OSError):
                return False
        return True

    def attested(self, token: str) -> bool:
        """The token must be found verbatim in committed text that also names the attesting source.

        Two places count. A stored document, when the snapshot holds the text containing the residue.
        And the snapshot manifest, because this project stores titles and abstracts only — a residue
        quoted from full text during verification lives in the manifest's own record, which is a
        committed, auditable attestation rather than a claim made at call time. The manifest must name
        both the token and the source, so one source's record cannot attest another's residue.
        """
        if token not in self.residues or not self.roots_are_committed_evidence():
            return False
        stem = self.source_id.replace(":", "_")
        for root in self.corpus_roots:
            root = Path(root)
            for candidate in (root / "docs" / f"{stem}.txt", root / f"{stem}.txt"):
                try:
                    if token in candidate.read_text():
                        return True
                except OSError:
                    continue
            try:
                manifest = (root / "manifest.json").read_text()
            except OSError:
                continue
            if token in manifest and self.source_id in manifest:
                return True
        return False


class DisclosureRefused(RuntimeError):
    """Raised instead of transmitting case-specific information."""

    def __init__(self, query: str, reason: str):
        self.query, self.reason = query, reason
        super().__init__(f"refusing to transmit a case-specific query ({reason}). "
                         f"Gene-level or bulk retrieval only; exact-variant lookup needs explicit approval.")


def case_specific_reasons(query: str) -> list[str]:
    return [name for name, pattern in CASE_SPECIFIC_PATTERNS if pattern.search(query or "")]


def check_query(query: str, *, provenance: PublicResidueProvenance | None = None,
                private_residues: frozenset[str] = frozenset()) -> str:
    """Returns the query if it is safe to send; raises DisclosureRefused otherwise.

    Default behaviour is unchanged and fails closed. A residue-level query may leave the boundary only
    when `provenance` attests every residue token in it against a stored public document — which is
    positive evidence that the residue is published, not permission for residue syntax in general.
    `private_residues`, passed by callers that hold the case adjudication, is refused unconditionally.
    """
    # The private cross-check runs FIRST and on every residue-like token, whatever else the query
    # looks like. Ordering it after the pattern scan was a bug: a token that tripped no pattern was
    # never compared against the case's own residue.
    tokens = set(RESIDUE_TOKEN.findall(query or ""))
    leaked = tokens & set(private_residues)
    if leaked:
        raise DisclosureRefused(query, f"residue derived from the private case: {sorted(leaked)}")
    reasons = case_specific_reasons(query)
    if not reasons:
        return query
    if provenance is None or set(reasons) - RESIDUE_SHAPED or not tokens:
        raise DisclosureRefused(query, ", ".join(reasons))
    if not provenance.roots_are_committed_evidence():
        raise DisclosureRefused(
            query, "the provenance does not point at committed snapshot evidence, so its attestation "
                   "does not pre-exist this release decision")
    unattested = sorted(t for t in tokens if not provenance.attested(t))
    if unattested:
        raise DisclosureRefused(
            query, f"residue(s) {unattested} are not attested verbatim in {provenance.source_id}; a "
                   "provenance claim is not a whitelist and must be checkable against stored text")
    return query


def approval_gate(what: str) -> None:
    """Called where exact-variant retrieval would be required. Always stops."""
    raise DisclosureRefused(what, "exact-variant external querying requires explicit operator approval")
