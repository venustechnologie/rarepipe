"""The LLM adapter, and the rules that keep model output from becoming evidence.

An LLM may propose queries, triage papers, extract findings from text it was given, hunt
contradictions and synthesise. It may not remember. Every claim it produces must cite a
document in the local corpus and quote text that is verifiably in that document; anything
else is recorded as an `InvalidInference` and discarded.

When no provider is configured the stage still runs: the deterministic planner and extractor
below take the same roles, and the artifact records which identity did the work. That is a
weaker run, and it says so rather than pretending.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PROMPT_DIR = Path(__file__).resolve().parents[3].parent / "prompts" / "mechanism"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


def load_prompt(name: str) -> Prompt:
    """Prompts are versioned artifacts: the filename carries the version, the run carries the hash."""
    candidates = sorted(PROMPT_DIR.glob(f"{name}_v*.txt"))
    if not candidates:
        raise FileNotFoundError(f"no prompt file for {name} in {PROMPT_DIR}")
    path = candidates[-1]
    return Prompt(name=name, version=path.stem.rsplit("_v", 1)[-1], text=path.read_text())


class LLM(Protocol):
    provider: str
    model: str

    def complete(self, prompt: str, payload: str) -> str: ...


class NoLLM:
    """The honest default: no provider configured, so no synthesis happens at all."""

    provider = "none"
    model = "deterministic_fallback"
    available = False

    def complete(self, prompt: str, payload: str) -> str:
        raise RuntimeError("no LLM provider configured")


class AnthropicLLM:
    """Used only if ANTHROPIC_API_KEY is present. Never receives case-specific identity —
    callers pass gene/disease-level text and corpus excerpts, and the disclosure guard
    checks every payload before it leaves."""

    provider = "anthropic"
    available = True

    def __init__(self, model: str = "claude-opus-5", api_key: str | None = None):
        self.model = model
        self._key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"

    def complete(self, prompt: str, payload: str) -> str:
        from rarepipe.stages.adjudicate.disclosure import check_query

        check_query(payload[:4000])
        body = json.dumps({"model": self.model, "max_tokens": 4096,
                           "system": prompt, "messages": [{"role": "user", "content": payload}]}).encode()
        req = urllib.request.Request(self._url, data=body, headers={
            "content-type": "application/json", "x-api-key": self._key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.load(resp)
        return "".join(part.get("text", "") for part in data.get("content", []))


def configured_llm() -> LLM:
    return AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else NoLLM()
