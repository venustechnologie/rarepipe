"""Importing proposed research hypotheses, chain link by chain link.

A hypothesis is a chain of arrows. Each arrow is either evidenced — cited to a document that was
actually retrieved, quoting text that is verbatim in it — or explicitly an inference. There is no
third option, and an arrow that claims evidence it cannot produce fails the import rather than the
reader's attention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.mechanism.model import InvalidInference, LLMResearchSession
from rarepipe.stages.mechanism.research import BUNDLES, _normalise
from rarepipe.stages.track2.model import (
    ChainLink,
    EfficacyDependency,
    HypothesisState,
    MindChanger,
    ResearchRepurposingHypothesis,
    ValidationPlan,
)


class IngestError(ValueError):
    pass


@dataclass
class IngestResult:
    session: LLMResearchSession
    hypotheses: list[ResearchRepurposingHypothesis]
    rejected: list[InvalidInference]
    evidence_index: dict[str, dict]


def _documents(root: Path) -> tuple[dict[str, dict], dict[str, Path]]:
    documents: dict[str, dict] = {}
    roots: dict[str, Path] = {}
    for index_path in sorted((root / BUNDLES).glob("*/bundle.json")):
        for doc in json.loads(index_path.read_text())["documents"]:
            documents.setdefault(doc["source_id"], doc)
            roots.setdefault(doc["source_id"], index_path.parent)
    return documents, roots


def import_hypotheses(root: Path, analysis_path: Path, *, session_index: int = 1) -> IngestResult:
    payload = yaml.safe_load(analysis_path.read_text())
    if not isinstance(payload, dict) or "hypotheses" not in payload:
        raise IngestError("analysis file must contain `session:` and `hypotheses:`")
    meta = payload.get("session") or {}
    documents, doc_roots = _documents(root)
    session = LLMResearchSession(
        session_id=f"LLMRS_{session_index:04d}", provider=meta.get("provider", "unrecorded"),
        interface=meta.get("interface", "unrecorded"), model=meta.get("model", "unrecorded"),
        knowledge_task=meta.get("knowledge_task", "unrecorded"), permitted_inputs=sorted(documents),
        prompt_template=meta.get("prompt_template"), human_reviewed=bool(meta.get("human_reviewed")),
        performed_at=utc_now().isoformat(), case_specific_genomic_data_supplied=False, note=meta.get("note", ""))

    hypotheses: list[ResearchRepurposingHypothesis] = []
    rejected: list[InvalidInference] = []
    evidence_index: dict[str, dict] = {}
    cache: dict[str, str] = {}
    who = f"{session.provider}:{session.model} ({session.interface}, human_operated)"

    for i, item in enumerate(payload["hypotheses"], start=1):
        ingredient = str(item.get("active_ingredient", "")).strip()
        hid = f"RH_{i:03d}"
        if not ingredient:
            rejected.append(InvalidInference(produced_by=who, statement="(unnamed)", reason="no_citation",
                                             detail="a hypothesis with no named active ingredient"))
            continue
        links: list[ChainLink] = []
        failure: InvalidInference | None = None
        for n, raw in enumerate(item.get("proposed_chain") or [], start=1):
            kind = str(raw.get("kind", "inference"))
            citations = raw.get("evidence") or []
            ids: list[str] = []
            if kind == "evidenced" and not citations:
                failure = InvalidInference(produced_by=who, statement=raw.get("step", ""), reason="no_citation",
                                           detail="an arrow claiming evidence with nothing cited")
                break
            for citation in citations:
                source_id = str(citation.get("source_id", "")).strip()
                quote = str(citation.get("quote", "")).strip()
                if source_id not in documents:
                    failure = InvalidInference(produced_by=who, statement=raw.get("step", ""),
                                               reason="source_not_in_corpus",
                                               detail=f"{source_id} was never retrieved")
                    break
                if source_id not in cache:
                    path = doc_roots[source_id] / "docs" / f"{source_id.replace(':', '_')}.txt"
                    cache[source_id] = path.read_text() if path.exists() else ""
                if not quote or _normalise(quote) not in _normalise(cache[source_id]):
                    failure = InvalidInference(produced_by=who, statement=raw.get("step", ""),
                                               reason="quote_not_found_in_source",
                                               detail=f"the quoted passage is not in {source_id}")
                    break
                eid = f"EV_T2_{hid}_{n:02d}_{len(ids) + 1:02d}"
                evidence_index[eid] = {
                    "evidence_id": eid, "source_id": source_id, "quote": quote[:600],
                    "pub_year": documents[source_id].get("pub_year"),
                    "independence_group": citation.get("independence_group"),
                    "system": citation.get("system"), "verified_from_source": True}
                ids.append(eid)
            if failure:
                break
            links.append(ChainLink(step=str(raw.get("step", "")), kind="evidenced" if kind == "evidenced" else "inference",
                                   evidence=ids, note=str(raw.get("note", ""))))
        if failure:
            rejected.append(failure)
            continue

        contradicting: list[str] = []
        for citation in item.get("contradicting_evidence") or []:
            source_id = str(citation.get("source_id", "")).strip()
            quote = str(citation.get("quote", "")).strip()
            if source_id not in documents:
                rejected.append(InvalidInference(produced_by=who, statement=f"{hid} contradiction",
                                                 reason="source_not_in_corpus", detail=source_id))
                continue
            if source_id not in cache:
                path = doc_roots[source_id] / "docs" / f"{source_id.replace(':', '_')}.txt"
                cache[source_id] = path.read_text() if path.exists() else ""
            if not quote or _normalise(quote) not in _normalise(cache[source_id]):
                rejected.append(InvalidInference(produced_by=who, statement=f"{hid} contradiction",
                                                 reason="quote_not_found_in_source", detail=source_id))
                continue
            eid = f"EV_T2_{hid}_CONTRA_{len(contradicting) + 1:02d}"
            evidence_index[eid] = {
                "evidence_id": eid, "source_id": source_id, "quote": quote[:600],
                "pub_year": documents[source_id].get("pub_year"), "system": citation.get("system"),
                "independence_group": citation.get("independence_group"), "verified_from_source": True,
                "contradicts": citation.get("contradicts", "")}
            contradicting.append(eid)

        plan = item.get("validation_plan") or {}
        mind = item.get("what_would_change_our_mind") or {}
        hypotheses.append(ResearchRepurposingHypothesis(
            id=hid, active_ingredient=ingredient, statement=str(item.get("statement", "")),
            proposed_chain=links, observed_direction=str(item.get("observed_direction", "unknown")),
            predicted_direction=str(item.get("predicted_direction", "unknown")),
            observed_upstream_effects=list(item.get("observed_upstream_effects") or []),
            efficacy_dependencies=[EfficacyDependency(**d) for d in item.get("efficacy_dependencies") or []],
            establishing_evidence=[e for link in links if link.kind == "evidenced" for e in link.evidence],
            supporting_evidence=list(item.get("supporting_evidence") or []),
            contradicting_evidence=contradicting,
            tested_in_bub1b_deficiency=bool(item.get("tested_in_bub1b_deficiency")),
            tested_in_mva=bool(item.get("tested_in_mva")),
            not_tested_note=str(item.get("not_tested_note", "")),
            exact_allele_dependency=bool(item.get("exact_allele_dependency")),
            validation_plan=ValidationPlan(**plan) if plan else None,
            what_would_change_our_mind=MindChanger(**mind) if mind else MindChanger(),
            limitations=list(item.get("limitations") or []),
            state=HypothesisState.DISCOVERY_ONLY))
    session.produced = [f"hypothesis_{i:02d}" for i in range(1, len(payload["hypotheses"]) + 1)]
    session.accepted = [h.id for h in hypotheses]
    session.rejected = [r.statement[:80] for r in rejected]
    return IngestResult(session=session, hypotheses=hypotheses, rejected=rejected, evidence_index=evidence_index)


def save(root: Path, result: IngestResult) -> Path:
    out = root / "hypotheses"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result.session.session_id}.json"
    path.write_text(json.dumps({
        "session": result.session.model_dump(mode="json"),
        "hypotheses": [h.model_dump(mode="json") for h in result.hypotheses],
        "evidence": result.evidence_index,
        "rejected": [r.model_dump(mode="json") for r in result.rejected]}, indent=2, ensure_ascii=False) + "\n")
    return path


def load_all(root: Path):
    sessions, hypotheses, evidence, rejected = [], [], {}, []
    folder = root / "hypotheses"
    for path in sorted(folder.glob("LLMRS_*.json")) if folder.exists() else []:
        payload = json.loads(path.read_text())
        sessions.append(LLMResearchSession(**payload["session"]))
        hypotheses += [ResearchRepurposingHypothesis(**h) for h in payload["hypotheses"]]
        evidence.update(payload.get("evidence", {}))
        rejected += [InvalidInference(**r) for r in payload["rejected"]]
    return sessions, hypotheses, evidence, rejected
