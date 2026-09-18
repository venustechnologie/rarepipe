"""Semantic digests, and the rule that keeps them meaningful.

A stage's semantic digest must answer "did the *content* change?" — so anything
that varies between two identical runs (timing, peak memory, run ids, absolute
paths containing a run id) must live in the stage's `execution` block, not in
the digested payload.

This has silently broken twice: Stage 02 carried the VCF stream time inside the
payload, Stage 03 carried per-profile wall-clock, peak RSS and run-specific
paths. `volatile_fields` is the shared check so a fourth stage cannot repeat it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

VOLATILE_KEY_HINTS = ("elapsed", "_seconds", "peak_rss", "started_at", "finished_at", "timestamp", "wall_clock")
VOLATILE_VALUE_HINTS = ("/RUN_", "run_20")


def semantic_digest(model: BaseModel, *, exclude: set[str]) -> str:
    """sha256 over the artifact minus its execution-specific sections."""
    data = model.model_dump(mode="json", by_alias=True, exclude=exclude | {"semantic_digest"})
    return "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# Deliberate pointers to the upstream artifact this one was derived from. They are part of
# the artifact's identity (a different upstream run IS a different input), so they belong in
# the digest even though they contain a run id.
UPSTREAM_POINTERS = frozenset({
    "provenance.source_manifest.run_id",
    "provenance.source_case.normalized_case_run_id",
})


def volatile_fields(payload: Any, path: str = "", allow: frozenset[str] = UPSTREAM_POINTERS) -> list[str]:
    """Paths inside a digested payload that look run-specific. Empty list = digest is safe."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else str(key)
            if here in allow:
                continue
            if any(hint in str(key).lower() for hint in VOLATILE_KEY_HINTS):
                found.append(here)
            else:
                found += volatile_fields(value, here, allow)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            found += volatile_fields(item, f"{path}[{i}]", allow)
    elif isinstance(payload, str) and any(hint.lower() in payload.lower() for hint in VOLATILE_VALUE_HINTS):
        found.append(f"{path} (value contains a run id)")
    return found
