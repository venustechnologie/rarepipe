"""HPO phenotype intake: identify, parse where straightforward, syntax-check.

No ontology lookups, parent expansion, synonym mapping or similarity — an ID
like HP:0001250 is checked for *syntax* only. Polarity (observed/excluded) is
recorded only where the source states it explicitly.
"""

from __future__ import annotations

import html
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.issues import Issue, IssueCode, Severity
from rarepipe.stages.intake.manifest import Format, HpoTerm, PhenotypeMetadata

VALID = re.compile(r"^HP:\d{7}$")
# Anything a human plausibly meant as an HPO identifier.
CANDIDATE = re.compile(r"(?<![A-Za-z0-9])HPO?[:_ ]?\d{3,9}(?![0-9])", re.I)
STRICT_TOKEN = re.compile(r"(?<![A-Za-z0-9])HP:\d{7}(?![0-9])")

NEGATIVE_VALUES = {"excluded", "absent", "no", "not", "negative", "false", "0", "-", "not_observed", "not observed"}
POSITIVE_VALUES = {"observed", "present", "yes", "positive", "true", "1", "+"}
POLARITY_COLUMNS = {"excluded", "negated", "observed", "present", "status", "polarity", "presence"}
NEGATION_PREFIX = re.compile(r"^\s*(NOT\s+|!)", re.I)  # "- HP:..." is a bullet, not a negation

MAX_TEXT_BYTES = 16 * 1024 * 1024
# In prose, only a separator-bearing token is plausibly an intended HPO ID ("HPO 2020" is not).
DOCX_CANDIDATE = re.compile(r"(?<![A-Za-z0-9])HPO?[:_]\s?\d{3,9}(?![0-9])", re.I)


def docx_text(path: Path) -> str:
    """Paragraph text of word/document.xml. Bounded; never logged."""
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo("word/document.xml")
        if info.file_size > MAX_TEXT_BYTES * 4:
            raise ValueError("document.xml too large")
        xml = zf.read(info).decode("utf-8", "replace")
    xml = re.sub(r"</w:p>|<w:br[^>]*/>|<w:tab[^>]*/>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))
LINE_LIST_THRESHOLD = 0.5


@dataclass
class _Tally:
    terms: list[HpoTerm] = field(default_factory=list)
    malformed_lines: list[int] = field(default_factory=list)
    malformed: int = 0

    def candidate(self, token: str, polarity: str, line_no: int) -> None:
        normalized = token.strip()
        if VALID.match(normalized):
            self.terms.append(HpoTerm(id=normalized, polarity=polarity))
        else:
            self.malformed += 1
            self.malformed_lines.append(line_no)


def looks_like_phenotype(path: Path, detected: Format) -> bool:
    if detected == Format.DOCX:
        try:
            return bool(STRICT_TOKEN.search(docx_text(path)))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return False
    if detected not in (Format.TEXT, Format.TSV, Format.CSV, Format.JSON):
        return False
    if path.stat().st_size > MAX_TEXT_BYTES:
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if detected == Format.JSON:
        return "phenotypicFeatures" in text or bool(STRICT_TOKEN.search(text))
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return False
    hits = sum(1 for ln in lines if CANDIDATE.search(ln))
    return hits / len(lines) >= LINE_LIST_THRESHOLD


def _polarity_from_value(v) -> str:
    s = str(v).strip().lower()
    if s in NEGATIVE_VALUES:
        return "excluded"
    if s in POSITIVE_VALUES:
        return "observed"
    return "unspecified"


def _parse_json(data, tally: _Tally) -> str:
    if isinstance(data, dict) and isinstance(data.get("phenotypicFeatures"), list):
        for i, feat in enumerate(data["phenotypicFeatures"], start=1):
            ftype = (feat or {}).get("type") or {}
            fid = ftype.get("id") if isinstance(ftype, dict) else None
            if fid is None:
                tally.malformed += 1
                tally.malformed_lines.append(i)
                continue
            excluded = feat.get("excluded")
            polarity = "excluded" if excluded is True else "observed" if excluded is False or "excluded" not in feat else "unspecified"
            # Phenopacket schema: absence of `excluded` means observed.
            tally.candidate(str(fid), polarity, i)
        return "phenopacket_json"

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            for m in CANDIDATE.finditer(node):
                tally.candidate(m.group(0), "unspecified", 0)

    walk(data)
    return "json_scan"


def _parse_delimited(lines: list[str], delim: str, tally: _Tally) -> str:
    header = [c.strip().lower() for c in lines[0].lstrip("#").split(delim)]
    has_header = not CANDIDATE.search(lines[0])
    polarity_col = next((i for i, c in enumerate(header) if c in POLARITY_COLUMNS), None) if has_header else None
    polarity_name = header[polarity_col] if polarity_col is not None else None
    start = 1 if has_header else 0
    for n, line in enumerate(lines[start:], start=start + 1):
        cols = line.split(delim)
        polarity = "unspecified"
        if polarity_col is not None and polarity_col < len(cols):
            polarity = _polarity_from_value(cols[polarity_col])
            if polarity_name in ("excluded", "negated") and polarity != "unspecified":
                polarity = "excluded" if polarity == "observed" else "observed"  # 'excluded=true' means excluded
        for m in CANDIDATE.finditer(line):
            tally.candidate(m.group(0), polarity, n)
    return "delimited_table"


def _parse_lines(lines: list[str], tally: _Tally) -> str:
    for n, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        polarity = "excluded" if NEGATION_PREFIX.match(line) else "unspecified"
        for m in CANDIDATE.finditer(line):
            tally.candidate(m.group(0), polarity, n)
    return "line_list"


def inspect_phenotype(path: Path, asset_id: str, detected: Format) -> tuple[PhenotypeMetadata | None, list[Issue]]:
    issues: list[Issue] = []
    tally = _Tally()
    try:
        text = "" if detected == Format.DOCX else path.read_text(encoding="utf-8")
        if detected == Format.JSON:
            parser = _parse_json(json.loads(text), tally)
        elif detected == Format.DOCX:
            for n, line in enumerate(docx_text(path).splitlines(), start=1):
                for m in DOCX_CANDIDATE.finditer(line):
                    tally.candidate(m.group(0).replace(" ", ""), "unspecified", n)
            parser = "docx_text_scan"
        else:
            lines = text.splitlines()
            data_lines = [ln for ln in lines if ln.strip()]
            if detected in (Format.TSV, Format.CSV) and data_lines:
                parser = _parse_delimited(data_lines, "\t" if detected == Format.TSV else ",", tally)
            else:
                parser = _parse_lines(lines, tally)
    except (OSError, ValueError, UnicodeDecodeError, KeyError, zipfile.BadZipFile) as exc:
        issues.append(Issue(code=IssueCode.HPO_PARSE_FAILED, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message=f"Phenotype file could not be parsed ({type(exc).__name__}).", suggested_action="Verify file encoding/structure."))
        return None, issues

    polarities = [t.polarity for t in tally.terms]
    meta = PhenotypeMetadata(
        parser=parser,
        valid_term_count=len(tally.terms),
        unique_valid_term_count=len({t.id for t in tally.terms}),
        malformed_identifier_count=tally.malformed,
        observed_count=polarities.count("observed"),
        excluded_count=polarities.count("excluded"),
        polarity_unspecified_count=polarities.count("unspecified"),
        terms=tally.terms,
        malformed_line_numbers=sorted(set(tally.malformed_lines)),
    )
    if tally.malformed:
        issues.append(Issue(code=IssueCode.HPO_TERM_MALFORMED, severity=Severity.WARNING, asset_ids=[asset_id],
                            message=f"{tally.malformed} identifier(s) resemble HPO IDs but are not syntactically valid (expected HP: followed by 7 digits).",
                            suggested_action="Correct identifiers at the source; intake does not rewrite them."))
    if not tally.terms:
        issues.append(Issue(code=IssueCode.HPO_NO_VALID_TERMS, severity=Severity.ACTION_REQUIRED, asset_ids=[asset_id],
                            message="Phenotype file contains no syntactically valid HPO identifiers.",
                            suggested_action="Confirm the correct phenotype file was supplied."))
    return meta, issues
