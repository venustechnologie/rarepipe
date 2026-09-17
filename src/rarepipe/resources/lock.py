"""Pinned external resources (ontologies, assembly metadata).

A resources directory holds files plus ``resources.lock.json`` recording, for
each file: kind, version, origin, retrieval time, size and SHA-256. Case runs
never fetch anything; they verify the lock and refuse a file whose bytes differ.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

LOCK_NAME = "resources.lock.json"


class ResourceKind(StrEnum):
    HPO_ONTOLOGY = "hpo_ontology"
    ASSEMBLY_REPORT = "assembly_report"
    EXOMISER_DISTRIBUTION = "exomiser_distribution"
    EXOMISER_DATA = "exomiser_data"


class ResourceEntry(BaseModel):
    kind: ResourceKind
    name: str
    version: str
    path: str = Field(description="Relative to the resources directory.")
    sha256: str
    size_bytes: int
    source_url: str | None = None
    retrieved_at: str | None = None
    notes: str | None = None


class ResourceLock(BaseModel):
    schema_: dict = Field(default_factory=lambda: {"name": "ResourceLock", "version": "1.0.0"}, alias="schema")
    resources: list[ResourceEntry] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_lock(resources_dir: Path) -> ResourceLock | None:
    p = resources_dir / LOCK_NAME
    return ResourceLock.model_validate_json(p.read_text()) if p.exists() else None


def verify(resources_dir: Path, entry: ResourceEntry) -> str:
    """'verified' | 'missing' | 'checksum_mismatch'"""
    p = resources_dir / entry.path
    if not p.is_file():
        return "missing"
    return "verified" if sha256_file(p) == entry.sha256 else "checksum_mismatch"


def register(resources_dir: Path, kind: ResourceKind, file: Path, *, name: str, version: str,
             source_url: str | None = None, retrieved_at: str | None = None, notes: str | None = None) -> ResourceEntry:
    file = file.resolve()
    root = resources_dir.resolve()
    if not file.is_relative_to(root):
        raise ValueError("resource file must live inside the resources directory")
    entry = ResourceEntry(kind=kind, name=name, version=version, path=file.relative_to(root).as_posix(), sha256=sha256_file(file),
                          size_bytes=file.stat().st_size, source_url=source_url,
                          retrieved_at=retrieved_at or datetime.now(UTC).replace(microsecond=0).isoformat(), notes=notes)
    lock = load_lock(root) or ResourceLock()
    lock.resources = [r for r in lock.resources if not (r.kind == kind and r.path == entry.path)] + [entry]
    (root / LOCK_NAME).write_text(lock.model_dump_json(indent=2) + "\n")
    return entry
