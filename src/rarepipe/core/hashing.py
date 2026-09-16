"""Streaming content digests with a resumable cache.

Files are read in fixed-size chunks — an 85 GB case never enters memory and is
never copied. Completed digests are persisted to a small cache keyed by
(relative path, size, mtime_ns, inode) so an interrupted intake can resume
without re-reading files it already finished. The cache holds digests only.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CHUNK_BYTES = 8 * 1024 * 1024

ProgressFn = Callable[[int, int], None]  # (bytes_done, bytes_total)


@dataclass(frozen=True)
class Digests:
    sha256: str
    md5: str | None


def stream_digest(path: Path, *, want_md5: bool = False, progress: ProgressFn | None = None) -> Digests:
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False) if want_md5 else None
    total = path.stat().st_size
    done = 0
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_BYTES):
            sha.update(chunk)
            if md5 is not None:
                md5.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return Digests(sha.hexdigest(), md5.hexdigest() if md5 else None)


class DigestCache:
    """Resume support. Writes are atomic (temp file + rename) after every file."""

    def __init__(self, path: Path | None):
        self.path = path
        self._entries: dict[str, dict] = {}
        self.hits = 0
        if path and path.exists():
            try:
                self._entries = json.loads(path.read_text())
            except (OSError, ValueError):
                self._entries = {}

    @staticmethod
    def _key(rel: str, st: os.stat_result) -> str:
        return f"{rel}|{st.st_size}|{st.st_mtime_ns}|{st.st_ino}"

    def get(self, rel: str, st: os.stat_result, want_md5: bool) -> Digests | None:
        entry = self._entries.get(self._key(rel, st))
        if not entry or (want_md5 and not entry.get("md5")):
            return None
        self.hits += 1
        return Digests(entry["sha256"], entry.get("md5"))

    def put(self, rel: str, st: os.stat_result, digests: Digests) -> None:
        if self.path is None:
            return
        self._entries[self._key(rel, st)] = {"sha256": digests.sha256, "md5": digests.md5}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._entries, sort_keys=True))
        tmp.replace(self.path)


def fingerprint(values: list[str]) -> str:
    """Order-independent digest over a list of strings."""
    h = hashlib.sha256()
    for v in sorted(values):
        h.update(v.encode())
        h.update(b"\n")
    return "sha256:" + h.hexdigest()
