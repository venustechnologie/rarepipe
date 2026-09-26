"""Importing intervention experiences, under the same proof rule as every other stage.

An experience is a claim that someone tried something and something happened. It enters only if the
cited source was actually retrieved into a lane bundle and the quoted passage is verbatim in it.

The outcome vocabulary is enforced here rather than trusted: `unknown` means untested or not
reported, and an experience may not be recorded as `no_effect` unless the source says an endpoint
was measured and did not move. A search that found nothing produces no experience at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.discovery.model import (
    EvidenceSource,
    InterventionExperience,
    Lane,
    MeasuredEndpoint,
    Outcome,
    SubjectScope,
)
from rarepipe.stages.mechanism.model import InvalidInference, LLMResearchSession
from rarepipe.stages.mechanism.research import BUNDLES, _normalise


class IngestError(ValueError):
    pass


@dataclass
class IngestResult:
    session: LLMResearchSession
    experiences: list[InterventionExperience]
    rejected: list[InvalidInference]


def _documents(root: Path) -> tuple[dict[str, dict], dict[str, Path]]:
    documents: dict[str, dict] = {}
    roots: dict[str, Path] = {}
    for index_path in sorted((root / BUNDLES).glob("*/bundle.json")):
        for doc in json.loads(index_path.read_text())["documents"]:
            documents.setdefault(doc["source_id"], doc)
            roots.setdefault(doc["source_id"], index_path.parent)
    return documents, roots


def import_experiences(root: Path, analysis_path: Path, *, session_index: int = 1) -> IngestResult:
    payload = yaml.safe_load(analysis_path.read_text())
    if not isinstance(payload, dict) or "experiences" not in payload:
        raise IngestError("analysis file must contain `session:` and `experiences:`")
    meta = payload.get("session") or {}
    documents, doc_roots = _documents(root)
    session = LLMResearchSession(
        session_id=f"LLMRS_{session_index:04d}", provider=meta.get("provider", "unrecorded"),
        interface=meta.get("interface", "unrecorded"), model=meta.get("model", "unrecorded"),
        knowledge_task=meta.get("knowledge_task", "unrecorded"), permitted_inputs=sorted(documents),
        prompt_template=meta.get("prompt_template"), human_reviewed=bool(meta.get("human_reviewed")),
        performed_at=utc_now().isoformat(), case_specific_genomic_data_supplied=False, note=meta.get("note", ""))

    experiences: list[InterventionExperience] = []
    rejected: list[InvalidInference] = []
    cache: dict[str, str] = {}
    who = f"{session.provider}:{session.model} ({session.interface}, human_operated)"

    for i, item in enumerate(payload["experiences"], start=1):
        ingredient = str(item.get("intervention_ingredient", "")).strip()
        source_id = str(item.get("source_id", "")).strip()
        quote = str(item.get("quote", "")).strip()
        label = f"{ingredient or '(unnamed)'} — {str(item.get('outcome', '?'))}"
        if not ingredient:
            rejected.append(InvalidInference(produced_by=who, statement=label, reason="no_citation",
                                             detail="an experience with no named intervention"))
            continue
        if source_id not in documents:
            rejected.append(InvalidInference(produced_by=who, statement=label, reason="source_not_in_corpus",
                                             detail=f"{source_id} was not retrieved into any lane bundle"))
            continue
        if source_id not in cache:
            path = doc_roots[source_id] / "docs" / f"{source_id.replace(':', '_')}.txt"
            cache[source_id] = path.read_text() if path.exists() else ""
        if not quote or _normalise(quote) not in _normalise(cache[source_id]):
            rejected.append(InvalidInference(produced_by=who, statement=label, reason="quote_not_found_in_source",
                                             detail=f"the quoted passage is not in {source_id}"))
            continue
        try:
            outcome = Outcome(str(item.get("outcome", "unknown")))
            scope = SubjectScope(str(item.get("subject_scope", "biochemical")))
            lane = Lane(str(item.get("lane")))
        except ValueError as exc:
            rejected.append(InvalidInference(produced_by=who, statement=label, reason="scope_overreach",
                                             detail=f"unknown vocabulary: {exc}"))
            continue
        endpoints = [MeasuredEndpoint(**e) for e in (item.get("measured_endpoints") or [])]
        if outcome in (Outcome.NO_EFFECT, Outcome.IMPROVED, Outcome.WORSENED) and not endpoints:
            rejected.append(InvalidInference(
                produced_by=who, statement=label, reason="no_citation",
                detail=f"outcome '{outcome.value}' requires at least one measured endpoint: "
                       "'no effect' without an endpoint is not reusable by anyone"))
            continue
        experiences.append(InterventionExperience(
            id=f"IX_{session.session_id}_{i:02d}", intervention_ingredient=ingredient,
            intervention_identifiers=dict(item.get("identifiers") or {}),
            disease=item.get("disease"), gene=item.get("gene"), mechanism=item.get("mechanism"),
            model=item.get("model"), subject_scope=scope, intervention_intent=item.get("intent", ""),
            outcome=outcome, measured_endpoints=endpoints,
            relevant_to=list(item.get("relevant_to") or []), lane=lane,
            evidence_source=EvidenceSource(
                source_id=source_id, quote=quote[:600], pub_year=documents[source_id].get("pub_year"),
                url=documents[source_id].get("url"), verified_from_source=True),
            independence_group=item.get("independence_group"),
            limitations=list(item.get("limitations") or []), extracted_by=f"{who} via {session.session_id}"))

    session.produced = [f"experience_{i:02d}" for i in range(1, len(payload["experiences"]) + 1)]
    session.accepted = [e.id for e in experiences]
    session.rejected = [r.statement[:80] for r in rejected]
    return IngestResult(session=session, experiences=experiences, rejected=rejected)


def save(root: Path, result: IngestResult) -> Path:
    out = root / "experiences"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result.session.session_id}.json"
    path.write_text(json.dumps({
        "session": result.session.model_dump(mode="json"),
        "experiences": [e.model_dump(mode="json") for e in result.experiences],
        "rejected": [r.model_dump(mode="json") for r in result.rejected]}, indent=2, ensure_ascii=False) + "\n")
    return path


def load_all(root: Path) -> tuple[list[LLMResearchSession], list[InterventionExperience], list[InvalidInference]]:
    sessions, experiences, rejected = [], [], []
    folder = root / "experiences"
    for path in sorted(folder.glob("LLMRS_*.json")) if folder.exists() else []:
        payload = json.loads(path.read_text())
        sessions.append(LLMResearchSession(**payload["session"]))
        experiences += [InterventionExperience(**e) for e in payload["experiences"]]
        rejected += [InvalidInference(**r) for r in payload["rejected"]]
    return sessions, experiences, rejected
