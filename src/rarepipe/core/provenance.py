"""Software/runtime provenance — the 'this exact software' half of every artifact."""

from __future__ import annotations

import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from pydantic import BaseModel

import rarepipe


class SourceControl(BaseModel):
    commit: str
    dirty: bool | None


class SoftwareProvenance(BaseModel):
    rarepipe: str
    source_control: SourceControl
    python: str
    implementation: str
    platform: str
    machine: str
    libraries: dict[str, str]


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def source_control() -> SourceControl:
    pkg_dir = Path(rarepipe.__file__).resolve().parent
    commit = _git(["rev-parse", "HEAD"], pkg_dir)
    if not commit:
        return SourceControl(commit="unknown", dirty=None)
    status = _git(["status", "--porcelain", "--untracked-files=no"], pkg_dir)
    return SourceControl(commit=commit, dirty=bool(status) if status is not None else None)


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "not-installed"


def software_provenance() -> SoftwareProvenance:
    import pysam

    libraries = {name: _version(name) for name in ("pysam", "pydantic", "typer")}
    libraries["htslib"] = pysam.version.__htslib_version__
    libraries["samtools(pysam-bundled)"] = pysam.__samtools_version__
    return SoftwareProvenance(
        rarepipe=rarepipe.__version__,
        source_control=source_control(),
        python=sys.version.split()[0],
        implementation=platform.python_implementation(),
        platform=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        libraries=dict(sorted(libraries.items())),
    )
