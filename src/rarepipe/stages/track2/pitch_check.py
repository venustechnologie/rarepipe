"""Claim-to-artifact check for hand-edited pitch wording.

A person may rewrite the generated pitch in plainer language. That is welcome, but every factual
sentence must still trace to something a sealed artifact states. The mapping from sentence to artifact
ids is written by a reviewer; this module checks the mapping instead of trusting it. Every sentence has
to be covered, every cited id has to exist in the sealed runs, and a sentence marked `not_in_artifact`
fails the check. It never edits the pitch.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

STATUSES = ("supported", "supported_with_note", "not_in_artifact", "editorial")
FORBIDDEN = ("mg/kg", "dose of", "prescrib", "we recommend", "should be given", "should take", "cures ", "a cure for")
ABSOLUTE = re.compile(r"\b(never|nobody|no one|does not exist|proves?|proven|guarantee\w*)\b", re.I)


class MappedSentence(BaseModel):
    sentence: str = Field(description="A verbatim span of the pitch.")
    status: Literal[STATUSES]  # type: ignore[valid-type]
    supported_by: list[str] = Field(default_factory=list, description="Artifact ids or PMIDs.")
    note: str = ""


class CheckedSentence(BaseModel):
    text: str
    status: str
    supported_by: list[str] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    note: str = ""
    flags: list[str] = Field(default_factory=list)

    @property
    def fails(self) -> bool:
        return self.status in ("not_in_artifact", "unmapped") or bool(self.missing_ids) or any(
            f.startswith("forbidden") for f in self.flags)


def sentences(markdown: str) -> list[str]:
    body = "\n".join(line for line in markdown.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    body = re.sub(r"\s+", " ", body)
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+(?=[A-Z0-9])", body) if s.strip()]


def check(pitch: str, mapping: list[MappedSentence], artifact_text: str) -> list[CheckedSentence]:
    out: list[CheckedSentence] = []
    for text in sentences(pitch):
        entry = next((m for m in mapping if m.sentence in text or text in m.sentence), None)
        flags = [f"forbidden phrase: {p.strip()!r}" for p in FORBIDDEN if p in text.lower()]
        flags += [f"absolute wording: {m.group(0)!r}" for m in ABSOLUTE.finditer(text)]
        if entry is None:
            out.append(CheckedSentence(text=text, status="unmapped", flags=flags,
                                       note="no reviewer mapping covers this sentence"))
            continue
        missing = [i for i in entry.supported_by if i not in artifact_text]
        out.append(CheckedSentence(text=text, status=entry.status, supported_by=entry.supported_by,
                                   missing_ids=missing, note=entry.note, flags=flags))
    return out


def load_mapping(path: Path) -> list[MappedSentence]:
    return [MappedSentence(**m) for m in (yaml.safe_load(path.read_text()) or {}).get("sentences", [])]


def artifact_text(runs: list[Path]) -> str:
    parts = []
    for run in runs:
        for path in sorted(run.glob("*.json")):
            if "private" not in path.name and not path.name.startswith("._"):  # skip macOS resource forks
                parts.append(json.dumps(json.loads(path.read_text())))
        for path in sorted(run.glob("*.md")):
            if not path.name.startswith("._"):
                parts.append(path.read_text())
    return "\n".join(parts)


def render(pitch_name: str, results: list[CheckedSentence], runs: list[Path]) -> str:
    failed = [r for r in results if r.fails]
    out = [f"# Pitch claim check — {pitch_name}\n",
           f"Checked against sealed runs: {', '.join(r.name for r in runs)}.\n",
           f"**Result: {'PASS' if not failed else 'FAIL'}** — {len(results)} sentence(s); {len(failed)} fail; "
           f"{sum(1 for r in results if r.flags and not r.fails)} carry a wording flag.\n",
           "The check never edits the pitch. A failing sentence needs either an artifact that states it or a "
           "change of wording by its author.\n",
           "| # | sentence | status | traced to | note |", "|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        ids = ", ".join(r.supported_by) + (f" (MISSING: {', '.join(r.missing_ids)})" if r.missing_ids else "")
        note = "; ".join([r.note] + r.flags).strip("; ")
        mark = "**FAIL**" if r.fails else r.status.replace("_", " ")
        out.append(f"| {i} | {r.text} | {mark} | {ids} | {note} |")
    out.append("")
    return "\n".join(out)
