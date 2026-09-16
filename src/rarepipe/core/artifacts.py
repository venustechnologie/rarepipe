"""Immutable, versioned run directories.

Every stage execution writes into a fresh ``<output>/<run_id>/`` directory:

* files are staged under ``<output>/.incomplete-<run_id>/`` and the directory
  is atomically renamed only once every file is written — a crashed run never
  looks like a finished artifact;
* files are created with exclusive-create and made read-only afterwards;
* a ``SHA256SUMS`` file seals the run's outputs.

Artifacts are never modified in place. Re-running produces a sibling run.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


def new_run_id(now: datetime) -> str:
    return f"RUN_{now.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(3)}"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def canonical_json(obj: BaseModel | dict) -> str:
    data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class RunDirectory:
    def __init__(self, output_root: Path, run_id: str):
        self.output_root = output_root
        self.run_id = run_id
        self.staging = output_root / f".incomplete-{run_id}"
        self.final = output_root / run_id
        self._written: list[str] = []

    def open(self) -> RunDirectory:
        self.output_root.mkdir(parents=True, exist_ok=True)
        if self.final.exists():
            raise FileExistsError(f"run directory already exists: {self.final}")
        self.staging.mkdir(parents=False, exist_ok=False)
        return self

    def write_text(self, name: str, content: str) -> Path:
        path = self.staging / name
        with path.open("x", encoding="utf-8") as fh:
            fh.write(content)
        self._written.append(name)
        return path

    def seal(self) -> Path:
        sums = []
        for name in sorted(self._written):
            digest = hashlib.sha256((self.staging / name).read_bytes()).hexdigest()
            sums.append(f"{digest}  {name}\n")
        self.write_text("SHA256SUMS", "".join(sums))
        for name in self._written:
            os.chmod(self.staging / name, 0o444)
        os.replace(self.staging, self.final)
        return self.final
