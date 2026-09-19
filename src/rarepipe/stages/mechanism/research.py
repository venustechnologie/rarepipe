"""The human-in-the-loop research workflow: tasks, bundles, briefs, and the import gate.

The pipeline owns the questions and the evidence. An assistant — Claude Code today, something
else tomorrow — is a replaceable worker that reads a bundle of public papers and proposes
structured claims. Nothing it writes becomes a claim until deterministic code has checked that
every cited source was actually retrieved and every quoted passage actually appears in it.

The assistant proposes. The evidence store proves. No part of this module calls a model, and
the pipeline runs end to end without one.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.mechanism.model import (
    Applicability,
    Confidence,
    Direction,
    EpistemicClass,
    EvidenceBundle,
    EvidenceLevel,
    EvidenceRecord,
    ExperimentalLevel,
    InvalidInference,
    KnowledgeTask,
    LLMResearchSession,
    MechanismClaim,
    Scope,
)

PROMPT_DIR = Path(__file__).resolve().parents[3].parent / "prompts" / "mechanism"
TASKS, BUNDLES, ANALYSES = "tasks", "bundles", "analyses"


class ResearchError(ValueError):
    pass


def workspace(root: Path) -> Path:
    for sub in (TASKS, BUNDLES, ANALYSES):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def next_task_id(root: Path) -> str:
    """One past the highest id, never a count.

    Counting files assigns an id that already exists as soon as the sequence has a gap — and a
    workspace that adopts tasks from a corpus run always has gaps. The first version of this
    silently overwrote two existing tasks.
    """
    highest = 0
    for path in (root / TASKS).glob("KT_*.json"):
        try:
            highest = max(highest, int(path.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return f"KT_{highest + 1:04d}"


def save_task(root: Path, task: KnowledgeTask, *, allow_overwrite: bool = True) -> Path:
    path = workspace(root) / TASKS / f"{task.id}.json"
    if path.exists() and not allow_overwrite:
        existing = KnowledgeTask(**json.loads(path.read_text()))
        if existing.question != task.question:
            raise ResearchError(
                f"{task.id} already exists and asks a different question; refusing to overwrite it")
    path.write_text(json.dumps(task.model_dump(mode="json"), indent=2) + "\n")
    return path


def load_task(root: Path, task_id: str) -> KnowledgeTask:
    path = root / TASKS / f"{task_id}.json"
    if not path.exists():
        raise ResearchError(f"no such knowledge task: {task_id}")
    return KnowledgeTask(**json.loads(path.read_text()))


def load_prompt_template(name: str) -> tuple[str, str]:
    """Prompt templates are versioned files a person pastes, not something the pipeline executes."""
    candidates = sorted(PROMPT_DIR.glob(f"{name}_v*.txt"))
    if not candidates:
        raise ResearchError(f"no prompt template named {name} in {PROMPT_DIR}")
    path = candidates[-1]
    return path.read_text(), f"{name}_v{path.stem.rsplit('_v', 1)[-1]}"


# ── the brief a person hands to an assistant ────────────────────────────────

def render_brief(task: KnowledgeTask, bundle: EvidenceBundle, documents: list[dict], template: str,
                 template_id: str) -> str:
    """Everything the assistant may see, and nothing else.

    The gene, the disease, the claim under investigation and the variant *class* are public
    biology. The child's coordinates, alleles, HGVS and residue are not here, and the exact-variant
    question is answered afterwards by local code against the same documents.
    """
    out = [f"# Research brief — {task.id}\n",
           f"**Question:** {task.question}\n",
           f"**Why it matters:** {task.reason}\n",
           f"**Evidence bundle:** `{bundle.bundle_id}` · {len(documents)} document(s) · digest `{bundle.digest}`\n",
           "## Rules for this interaction\n",
           "- Answer **only** from the documents listed below. Prior knowledge is not evidence here.",
           "- Every proposed claim must cite source ids from this bundle and quote the passage it rests on,",
           "  verbatim. A claim without a verifiable quote will be rejected on import, by code, not by opinion.",
           "- State the narrowest scope the evidence actually has. Evidence about a class of variants is not",
           "  evidence about one patient's allele.",
           "- 'Insufficient evidence' is a correct and valued answer.",
           "- Do not discuss drugs, treatments, repurposing or gene therapy. This stage does not go there.\n",
           "## Prompt template\n", f"_{template_id}_\n", "```", template.strip(), "```\n",
           "## Documents in this bundle\n",
           "| source | year | full text | title |", "|---|---|---|---|"]
    for doc in documents:
        out.append(f"| `{doc['source_id']}` | {doc.get('pub_year') or '—'} | "
                   f"{'yes' if doc.get('full_text') else 'abstract only'} | {(doc.get('title') or '')[:90]} |")
    out += ["",
            "## Return this shape\n",
            "```yaml",
            "session:",
            "  provider: Anthropic",
            "  interface: Claude Code",
            "  model: Claude Opus 5",
            f"  knowledge_task: {task.id}",
            f"  prompt_template: {template_id}",
            "  human_reviewed: true",
            "proposed_claims:",
            "  - statement: BUBR1 deficiency weakens spindle-checkpoint activity",
            "    claim_type: checkpoint_effect        # see the ClaimType enum",
            "    scope: gene_level                    # the narrowest scope the evidence supports",
            "    direction: supports                  # supports | contradicts | uncertain",
            "    confidence: moderate                 # low | moderate | high",
            "    reasoning: one or two sentences, referring only to the quoted passages",
            "    evidence:",
            "      - source_id: PMID:00000000",
            "        quote: >-",
            "          the exact sentence from that document, copied verbatim",
            "        experimental_level: patient_derived_cells",
            "```\n",
            "Import it with `rarepipe research import-analysis --analysis <file> --research <workspace>`.",
            "Sources that were not retrieved, and quotes that are not in the documents, are rejected.\n"]
    return "\n".join(out)


# ── the import gate ─────────────────────────────────────────────────────────

@dataclass
class ImportResult:
    session: LLMResearchSession
    accepted_claims: list[MechanismClaim]
    accepted_evidence: list[EvidenceRecord]
    rejected: list[InvalidInference]

    @property
    def ok(self) -> bool:
        return bool(self.accepted_claims) and not self.rejected


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _bundle_documents(root: Path, bundle_id: str) -> tuple[dict[str, dict], Path]:
    index_path = root / BUNDLES / bundle_id / "bundle.json"
    if not index_path.exists():
        raise ResearchError(f"no such evidence bundle: {bundle_id}")
    index = json.loads(index_path.read_text())
    return {d["source_id"]: d for d in index["documents"]}, index_path.parent


def _all_bundle_documents(root: Path) -> tuple[dict[str, dict], dict[str, Path]]:
    """Synthesis spans bundles by nature. It is still bounded — every citation must already have
    been accepted by an earlier session, which is a stronger constraint than bundle membership."""
    documents: dict[str, dict] = {}
    roots: dict[str, Path] = {}
    for index_path in sorted((root / BUNDLES).glob("*/bundle.json")):
        for doc in json.loads(index_path.read_text())["documents"]:
            documents.setdefault(doc["source_id"], doc)
            roots.setdefault(doc["source_id"], index_path.parent)
    if not documents:
        raise ResearchError("no evidence bundles in this workspace")
    return documents, roots


def import_analysis(root: Path, analysis_path: Path, *, residue_needles: list[str] | None = None,
                    session_index: int = 1, synthesis_only: bool = False) -> ImportResult:
    """Validate a proposed analysis against the evidence store. Claude proposes; this proves.

    With `synthesis_only`, a proposal may only reconcile evidence that earlier sessions already had
    accepted: a synthesiser connects claims, it does not introduce new biomedical facts.
    """
    payload = yaml.safe_load(analysis_path.read_text())
    if not isinstance(payload, dict) or "proposed_claims" not in payload:
        raise ResearchError("analysis file must contain `session:` and `proposed_claims:`")
    meta = payload.get("session") or {}
    task_id = meta.get("knowledge_task")
    if not task_id:
        raise ResearchError("session.knowledge_task is required: a proposal must answer a recorded question")
    task = load_task(root, task_id)
    bundle_id = meta.get("evidence_bundle") or task.id
    if synthesis_only:
        documents, doc_roots = _all_bundle_documents(root)
        docs_root = None
    else:
        documents, docs_root = _bundle_documents(root, bundle_id)
        doc_roots = {source_id: docs_root for source_id in documents}

    session = LLMResearchSession(
        session_id=f"LLMRS_{session_index:04d}", provider=meta.get("provider", "unrecorded"),
        interface=meta.get("interface", "unrecorded"), model=meta.get("model", "unrecorded"),
        knowledge_task=task_id, permitted_inputs=sorted(documents), prompt_template=meta.get("prompt_template"),
        human_reviewed=bool(meta.get("human_reviewed")), performed_at=utc_now().isoformat(),
        case_specific_genomic_data_supplied=False,
        note=meta.get("note", ""))

    accepted_claims: list[MechanismClaim] = []
    accepted_evidence: list[EvidenceRecord] = []
    rejected: list[InvalidInference] = []
    produced = 0
    cache: dict[str, str] = {}
    already_accepted: set[tuple[str, str]] = set()
    if synthesis_only:
        _, _, prior_evidence, _ = load_analyses(root)
        already_accepted = {(e.source_id, _normalise(e.quote)) for e in prior_evidence}

    for i, proposal in enumerate(payload["proposed_claims"], start=1):
        produced += 1
        statement = str(proposal.get("statement", "")).strip()
        who = f"{session.provider}:{session.model} ({session.interface}, {session.mode})"
        citations = proposal.get("evidence") or []
        if not statement:
            rejected.append(InvalidInference(produced_by=who, statement="(empty)", reason="no_citation",
                                             detail="proposal carried no statement"))
            continue
        if not citations:
            rejected.append(InvalidInference(produced_by=who, statement=statement, reason="no_citation",
                                             detail="a claim with no cited source cannot enter the graph"))
            continue
        try:
            scope = Scope(str(proposal.get("scope", "")).strip())
        except ValueError:
            rejected.append(InvalidInference(produced_by=who, statement=statement, reason="scope_overreach",
                                             detail=f"unknown scope {proposal.get('scope')!r}"))
            continue

        records: list[EvidenceRecord] = []
        failure: InvalidInference | None = None
        for citation in citations:
            source_id = str(citation.get("source_id", "")).strip()
            quote = str(citation.get("quote", "")).strip()
            if source_id not in documents:
                failure = InvalidInference(produced_by=who, statement=statement, reason="source_not_in_corpus",
                                           detail=f"{source_id} was never retrieved for this bundle")
                break
            if source_id not in cache:
                text_path = doc_roots[source_id] / "docs" / f"{source_id.replace(':', '_')}.txt"
                cache[source_id] = text_path.read_text() if text_path.exists() else ""
            if not quote or _normalise(quote) not in _normalise(cache[source_id]):
                failure = InvalidInference(produced_by=who, statement=statement, reason="quote_not_found_in_source",
                                           detail=f"the quoted passage is not in {source_id}")
                break
            if synthesis_only and (source_id, _normalise(quote)) not in already_accepted:
                failure = InvalidInference(
                    produced_by=who, statement=statement, reason="scope_overreach",
                    detail=f"a synthesis may only reconcile evidence already accepted; {source_id} was cited with a "
                           "passage no earlier session had accepted")
                break
            level = _level_for(citation, documents[source_id])
            records.append(EvidenceRecord(
                evidence_id=f"EV_IMP_{session.session_id}_{i:02d}_{len(records) + 1:02d}", source_id=source_id,
                statement=statement, quote=quote[:600], epistemic_class=EpistemicClass.EXTERNAL_EVIDENCE,
                evidence_level=level, experimental_level=_experimental(citation), scope=scope,
                applicability_to_case=(Applicability.DIRECT if scope in (Scope.EXACT_VARIANT, Scope.SAME_RESIDUE)
                                       else Applicability.INDIRECT),
                direction=Direction(str(proposal.get("direction", "supports"))),
                assay=citation.get("assay"), model_system=citation.get("experimental_level"),
                result=citation.get("result"), rescue_experiment=bool(citation.get("rescue_experiment")),
                variant_tested=citation.get("variant_tested"),
                limitations=list(citation.get("limitations") or []),
                extracted_by=f"{who} via {session.session_id}", verified_from_source=True,
                pub_year=documents[source_id].get("pub_year")))
        if failure:
            rejected.append(failure)
            continue

        # An exact-variant claim has to be about the actual residue, in the actual text.
        if scope in (Scope.EXACT_VARIANT, Scope.SAME_RESIDUE):
            needles = residue_needles or []
            if not needles or not any(any(n.lower() in _normalise(cache[r.source_id]) for n in needles) for r in records):
                rejected.append(InvalidInference(
                    produced_by=who, statement=statement, reason="scope_overreach",
                    detail="claimed exact-variant scope, but no cited document mentions this case's residue "
                           "(checked locally against the private artifact)"))
                continue

        accepted_evidence += records
        accepted_claims.append(MechanismClaim(
            id=f"MC_IMP_{session.session_id}_{i:02d}", type=proposal.get("claim_type", "protein_effect"),
            statement=statement, status="PARTIALLY_SUPPORTED" if len({r.source_id for r in records}) == 1 else "SUPPORTED",
            scope=scope, epistemic_class=EpistemicClass.DERIVED_INFERENCE,
            evidence=[r.evidence_id for r in records],
            inference={"derived_by": f"{who} via {session.session_id}",
                       "reasoning": str(proposal.get("reasoning", "")).strip(),
                       "inputs": [r.evidence_id for r in records]},
            limitations=list(proposal.get("limitations") or []),
            confidence=_confidence(proposal.get("confidence"))))

    session.produced = [f"proposal_{i:02d}" for i in range(1, produced + 1)]
    session.accepted = [c.id for c in accepted_claims]
    session.rejected = [r.statement[:80] for r in rejected]
    return ImportResult(session=session, accepted_claims=accepted_claims, accepted_evidence=accepted_evidence,
                        rejected=rejected)


def _level_for(citation: dict, document: dict) -> EvidenceLevel:
    experimental = str(citation.get("experimental_level", "")).strip()
    if experimental == "patient_derived_cells":
        return EvidenceLevel.HUMAN_EXPERIMENTAL
    if experimental == "animal_model":
        return EvidenceLevel.MODEL_SYSTEM
    if experimental == "in_silico":
        return EvidenceLevel.COMPUTATIONAL
    return EvidenceLevel.REVIEW if document.get("is_review") else EvidenceLevel.PRIMARY_LITERATURE


def _experimental(citation: dict) -> ExperimentalLevel:
    try:
        return ExperimentalLevel(str(citation.get("experimental_level", "")).strip())
    except ValueError:
        return ExperimentalLevel.NOT_APPLICABLE


def _confidence(value) -> Confidence | None:
    try:
        return Confidence(str(value).strip().lower())
    except ValueError:
        return None


def save_analysis(root: Path, result: ImportResult) -> Path:
    path = workspace(root) / ANALYSES / f"{result.session.session_id}.json"
    path.write_text(json.dumps({
        "session": result.session.model_dump(mode="json"),
        "accepted_claims": [c.model_dump(mode="json") for c in result.accepted_claims],
        "accepted_evidence": [e.model_dump(mode="json") for e in result.accepted_evidence],
        "rejected": [r.model_dump(mode="json") for r in result.rejected],
    }, indent=2, ensure_ascii=False) + "\n")
    return path


def load_analyses(root: Path) -> tuple[list[LLMResearchSession], list[MechanismClaim], list[EvidenceRecord], list[InvalidInference]]:
    sessions, claims, evidence, rejected = [], [], [], []
    for path in sorted((root / ANALYSES).glob("LLMRS_*.json")) if (root / ANALYSES).exists() else []:
        payload = json.loads(path.read_text())
        sessions.append(LLMResearchSession(**payload["session"]))
        claims += [MechanismClaim(**c) for c in payload["accepted_claims"]]
        evidence += [EvidenceRecord(**e) for e in payload["accepted_evidence"]]
        rejected += [InvalidInference(**r) for r in payload["rejected"]]
    return sessions, claims, evidence, rejected


def bundle_from_corpus(corpus_run: Path, task: KnowledgeTask, root: Path) -> EvidenceBundle:
    """Carve a task's documents out of a corpus run into a bundle a person can hand over."""
    index = json.loads((corpus_run / "corpus_index.json").read_text())
    if task.documents_found:
        documents = [d for d in index["documents"] if d["source_id"] in set(task.documents_found)]
    elif task.queries:
        # A bundle answers one question: carve only what this task's own queries surfaced.
        documents = [d for d in index["documents"] if d.get("query") in set(task.queries)]
    else:
        documents = list(index["documents"])
    if not documents:
        raise ResearchError(f"no document in {corpus_run.name} came from {task.id}'s queries; "
                            "run `research retrieve` without --corpus-run to query for them")
    target = workspace(root) / BUNDLES / task.id
    (target / "docs").mkdir(parents=True, exist_ok=True)
    total = 0
    for doc in documents:
        name = f"{doc['source_id'].replace(':', '_')}.txt"
        source = corpus_run / "docs" / name
        if source.exists():
            text = source.read_text()
            (target / "docs" / name).write_text(text)
            total += len(text)
    bundle = EvidenceBundle(
        bundle_id=task.id, knowledge_task=task.id, created_at=utc_now().isoformat(),
        documents=[d["source_id"] for d in documents], queries=list(task.queries), characters=total,
        digest="sha256:" + hashlib.sha256(json.dumps(sorted(d["content_hash"] for d in documents)).encode()).hexdigest())
    (target / "bundle.json").write_text(json.dumps(
        {"bundle": bundle.model_dump(mode="json"), "documents": documents}, indent=2, ensure_ascii=False) + "\n")
    return bundle
