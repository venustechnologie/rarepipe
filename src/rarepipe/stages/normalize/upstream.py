"""Loading the upstream CaseManifest and describing VCF header provenance."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pysam

from rarepipe.stages.normalize.model import FilterDefinition, UpstreamStep

pysam.set_verbosity(0)


def seal_status(manifest_path: Path) -> bool | None:
    """True/False against the Stage 01 run's SHA256SUMS; None if no seal exists."""
    sums = manifest_path.parent / "SHA256SUMS"
    if not sums.exists():
        return None
    for line in sums.read_text().splitlines():
        digest, _, name = line.partition("  ")
        if name == manifest_path.name:
            return hashlib.sha256(manifest_path.read_bytes()).hexdigest() == digest
    return None


def _unquote(v: str | None) -> str | None:
    return v.strip('"') if v else v


_BCFTOOLS_CMD = re.compile(r"^(?P<tool>[A-Za-z0-9]+)_(?P<sub>[A-Za-z0-9]+)Command$")
_BCFTOOLS_VER = re.compile(r"^(?P<tool>[A-Za-z0-9]+)_(?P<sub>[A-Za-z0-9]+)Version$")


def header_description(path: Path) -> tuple[list[UpstreamStep], list[FilterDefinition], list[str], dict[str, tuple[str | None, str | None]]]:
    """(upstream steps, FILTER definitions, INFO ids, FORMAT id → (Number, Type)). Header only."""
    steps: list[UpstreamStep] = []
    versions: dict[str, str] = {}
    with pysam.VariantFile(str(path)) as vf:
        h = vf.header
        for rec in h.records:
            key = rec.key or ""
            if rec.type == "STRUCTURED" and key.endswith("CommandLine"):
                items = {k: _unquote(v) for k, v in rec.items()}
                cmd = items.get("CommandLine") or items.get("CommandLineOptions")
                steps.append(UpstreamStep(tool=f"{key[: -len('CommandLine')] or 'unknown'} {items.get('ID') or ''}".strip(),
                                          version=items.get("Version"), date=items.get("Date"),
                                          parameters="available" if cmd else "unavailable",
                                          source=f"vcf_header:{key}", command_line=cmd))
            elif rec.type == "GENERIC":
                value = rec.value or ""
                if m := _BCFTOOLS_VER.match(key):
                    versions[f"{m['tool']} {m['sub']}"] = value.split()[0] if value else ""
                elif m := _BCFTOOLS_CMD.match(key):
                    cmd, _, date = value.partition("; Date=")
                    steps.append(UpstreamStep(tool=f"{m['tool']} {m['sub']}", date=date or None, parameters="available" if cmd else "unavailable",
                                              source=f"vcf_header:{key}", command_line=cmd or None))
                elif key == "source":
                    steps.append(UpstreamStep(tool=Path(value.split()[0]).name if value.strip() else "unspecified", parameters="unavailable",
                                              source="vcf_header:source"))
                elif key.endswith("Version") and key not in ("fileformat",):
                    steps.append(UpstreamStep(tool=key[: -len("Version")] or key, version=value or None, parameters="unavailable",
                                              source=f"vcf_header:{key}"))
        for s in steps:
            if s.version is None and s.tool in versions:
                s.version = versions[s.tool]
        filters = [FilterDefinition(id=fid, description=_unquote(f.description)) for fid, f in h.filters.items()]
        info_ids = sorted(h.info.keys())
        formats = {fid: (str(f.number) if f.number is not None else None, f.type) for fid, f in h.formats.items()}
    return steps, filters, info_ids, formats
