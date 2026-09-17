"""Operator-facing progress output + the run log.

Everything emitted here is also written to the run's ``intake.log``. Callers
pass only operational facts and internal aliases — never sample labels, paths,
sequences or record content.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from typing import TextIO


class Console:
    def __init__(self, stream: TextIO | None = None, quiet: bool = False):
        self.stream = stream if stream is not None else sys.stderr
        self.quiet = quiet
        self.log_lines: list[str] = []
        self._last_progress = 0.0
        self._finished: set[str] = set()

    def _emit(self, text: str) -> None:
        self.log_lines.append(f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {text.strip()}")
        if not self.quiet:
            print(text, file=self.stream, flush=True)

    def step(self, index: int, total: int, title: str) -> None:
        self._emit(f"\n[{index}/{total}] {title}")

    def ok(self, text: str) -> None:
        self._emit(f"      ✓ {text}")

    def warn(self, text: str) -> None:
        self._emit(f"      ! {text}")

    def fail(self, text: str) -> None:
        self._emit(f"      ✗ {text}")

    def info(self, text: str) -> None:
        self._emit(f"      {text}")

    def line(self, text: str = "") -> None:
        self._emit(text)

    def progress(self, label: str, done: int, total: int) -> None:
        """Terminal-only (not logged), throttled."""
        if self.quiet or total <= 0 or label in self._finished:
            return
        if done >= total:
            self._finished.add(label)
        now = time.monotonic()
        if done < total and now - self._last_progress < 0.5:
            return
        self._last_progress = now
        pct = 100 * done / total
        end = "\n" if done >= total else ""
        if self.stream.isatty():
            print(f"\r      … {label}: {pct:5.1f}% of {total / 1e9:.2f} GB", end=end, file=self.stream, flush=True)
        elif done >= total:
            print(f"      … {label}: done ({total / 1e9:.2f} GB)", file=self.stream, flush=True)
