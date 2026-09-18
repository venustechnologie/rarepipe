"""Corpus acquisition run: execute the KnowledgeTasks' queries, store what comes back.

Separated from resolution on purpose. This half touches the network and never opens a case
artifact; the other half opens the case and never touches the network.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import RunDirectory, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.provenance import software_provenance
from rarepipe.stages.mechanism import questions
from rarepipe.stages.mechanism.llm import configured_llm, load_prompt
from rarepipe.stages.mechanism.model import AgentRun
from rarepipe.stages.mechanism.retrieve import Corpus, RetrievalRefused

INDEX = "corpus_index.json"
LOG = "fetch_corpus.log"


@dataclass
class FetchRequest:
    output: Path
    select_top: int = 6
    page_size: int = 25
    full_text: bool = True
    argv: list[str] = field(default_factory=list)


@dataclass
class FetchResult:
    run_dir: Path
    documents: int
    full_texts: int
    queries: int


def run_fetch(req: FetchRequest, console: Console | None = None) -> FetchResult:
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)
    run = RunDirectory(req.output, run_id).open()
    corpus = Corpus(root=run.staging)

    tasks = questions.seed_tasks()
    llm = configured_llm()
    planner = load_prompt("query_planner")
    agent_runs: list[AgentRun] = []
    if getattr(llm, "available", False):
        console.info(f"query planner: {llm.provider}:{llm.model} prompt {planner.name} v{planner.version}")
    else:
        console.warn("no LLM provider configured — queries come from the deterministic seed plan, "
                     "and the dossier will record that this run had no agent synthesis")
    generated_by = (f"{llm.provider}:{llm.model}:{planner.name}_v{planner.version}"
                    if getattr(llm, "available", False) else "rarepipe.seed_plan_v1")

    console.step(1, 3, "Executing knowledge tasks against public literature...")
    for task in tasks:
        if not task.queries:
            task.status = "planned"
            task.stop_reason = "answered locally in the resolution run; nothing is transmitted for it"
            continue
        console.line(f"  {task.id}: {task.question}")
        found: list[str] = []
        for query in task.queries:
            try:
                docs = corpus.run_query(query, task.id, generated_by=generated_by, select_top=req.select_top,
                                        page_size=req.page_size, want_full_text=req.full_text, console=console)
            except RetrievalRefused as exc:
                console.fail(str(exc))
                continue
            found += [d.source_id for d in docs]
        task.documents_found = sorted(set(found))
        task.status = "completed" if found else "blocked"
        task.stop_reason = (questions.STOP_RULES["C"] if found else
                            "no records passed the relevance threshold for any query")

    console.step(2, 3, "Sealing the corpus...")
    documents = sorted(corpus.documents.values(), key=lambda d: d.source_id)
    payload = {
        "schema": {"name": "MechanismCorpus", "version": "1.0.0"},
        "created_at": started.isoformat(),
        "software": software_provenance().model_dump(mode="json"),
        "retrieval_policy": ("Gene-, protein- and disease-level queries only; every query passed the disclosure "
                             "guard and the intervention-search filter. Full text stored only where openly "
                             "available; no paywall was circumvented."),
        "llm": {"provider": llm.provider, "model": llm.model, "available": getattr(llm, "available", False)},
        "knowledge_tasks": [t.model_dump(mode="json") for t in tasks],
        "documents": [d.model_dump(mode="json") for d in documents],
        "query_log": [q.model_dump(mode="json") for q in corpus.queries],
        "agent_runs": [a.model_dump(mode="json") for a in agent_runs],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    payload["corpus_digest"] = "sha256:" + hashlib.sha256(
        json.dumps({"documents": [d.content_hash for d in documents]}, sort_keys=True).encode()).hexdigest()
    run.write_text(INDEX, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    console.step(3, 3, "Done.")
    full = sum(1 for d in documents if d.full_text)
    console.ok(f"run {run_id}: {len(documents)} document(s), {full} with full text, {len(corpus.queries)} query(ies), "
               f"{round(time.monotonic() - t0, 1)}s")
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return FetchResult(run_dir=run.seal(), documents=len(documents), full_texts=full, queries=len(corpus.queries))
