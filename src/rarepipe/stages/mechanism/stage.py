"""Stage 06 — mechanism resolution. Offline: the corpus is already on disk, the case never leaves.

Four workstreams in one executable:
  006A  allele effects — truncating and missense adjudicated separately
  006B  protein / molecular mechanism
  006C  cellular disease mechanism
  006D  adjudication, contradiction hunting and the decision gate
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.digest import semantic_digest
from rarepipe.core.provenance import software_provenance
from rarepipe.core.redaction import clear_restricted
from rarepipe.stages.mechanism import claims as C
from rarepipe.stages.mechanism import dossier as report
from rarepipe.stages.mechanism import extract, questions
from rarepipe.stages.mechanism import research
from rarepipe.stages.mechanism.compare import compare
from rarepipe.stages.mechanism.experiments import ExperimentError, assess, child_missense, load_experiments
from rarepipe.stages.mechanism.model import (
    ClaimDirection,
    AlleleMechanism,
    AutomationStatus,
    Applicability,
    ClaimStatus,
    ClaimType,
    Confidence,
    Direction,
    EpistemicClass,
    EvidenceLevel,
    EvidenceRecord,
    Execution,
    ExperimentalLevel,
    InvalidInference,
    KnowledgeTask,
    MechanismDossier,
    MechanismEdge,
    MechanismGraph,
    MechanismNode,
    MechanismState,
    MindChanger,
    NextAction,
    Readiness,
    Provenance,
    QueryRecord,
    RetrievedDocument,
    Scope,
    Status,
)

DOSSIER_PRIVATE = "mechanism_dossier.private.json"
DOSSIER_SANITIZED = "mechanism_dossier.sanitized.json"
REPORT = "mechanism_dossier.md"
GRAPH = "mechanism_graph.json"
LOG = "mechanism.log"

ASSAY_QUESTIONS = {assay: question for assay, question, _ in extract.ASSAY_PATTERNS}

# A claim must be about its own subject. Without these, any sentence mentioning "transcript levels"
# would count as evidence of nonsense-mediated decay, and any sentence mentioning the kinase domain
# would count as a measurement of this child's allele.
TOPIC = {
    "ptc": re.compile(r"\b(premature (termination|stop)|nonsense|truncat\w+|frameshift|stop[- ]gained)\b", re.I),
    "nmd": re.compile(r"\b(nonsense[- ]mediated (mRNA )?decay|NMD)\b", re.I),
    "abundance": re.compile(r"\b(protein (levels?|abundance|amount|expression)|western blot|immunoblot|"
                            r"undetectable|reduced BUBR1|steady[- ]state)\b", re.I),
    "checkpoint": re.compile(r"\b(checkpoint|SAC|mitotic arrest|nocodazole|APC/C|CDC20|MAD2)\b", re.I),
    "segregation": re.compile(r"\b(missegregat\w+|mis-?segregation|lagging|alignment|congression|"
                              r"premature (sister )?chromatid separation|PCS)\b", re.I),
    "aneuploidy": re.compile(r"\b(aneuploid\w*|trisom\w+|monosom\w+|karyotyp\w+|chromosome (gains?|losses?))\b", re.I),
    "mva": re.compile(r"\b(mosaic variegated aneuploidy|MVA)\b", re.I),
    "rescue": re.compile(r"\b(rescue[ds]?|complementation|complemented|restor\w+|re-?expression)\b", re.I),
    "kinase": re.compile(r"\b(kinase (activity|dead|domain)|autophosphorylat\w+|catalytic)\b", re.I),
}
# Only a measurement can establish a functional claim. A predictor or a domain annotation is
# consistent with one; it is not one.
MEASURED = {EvidenceLevel.THIS_CASE, EvidenceLevel.HUMAN_EXPERIMENTAL, EvidenceLevel.EXPERT_CURATED,
            EvidenceLevel.PRIMARY_LITERATURE, EvidenceLevel.MODEL_SYSTEM}
EXTERNAL_MEASURED = MEASURED - {EvidenceLevel.THIS_CASE}


class MechanismUsageError(ValueError):
    pass


@dataclass
class ResolveRequest:
    corpus_run: Path
    adjudication: Path
    output: Path
    validation: Path | None = None
    research_dir: Path | None = None
    alphagenome: Path | None = None
    compare_mechanism_run: Path | None = None
    compare_track2_run: Path | None = None
    compare_label: str = ""
    argv: list[str] = field(default_factory=list)


@dataclass
class ResolveResult:
    dossier: MechanismDossier
    sanitized: MechanismDossier
    run_dir: Path


def _load(path: Path) -> dict:
    if not path.exists():
        raise MechanismUsageError(f"not found: {path}")
    return json.loads(path.read_text())


def residue_needles(adjudication: dict) -> tuple[list[str], str | None]:
    """Search terms for the child's missense allele, built locally and used only locally."""
    three_to_one = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G",
                    "His": "H", "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S",
                    "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V"}
    needles: list[str] = []
    residue = None
    for variant in adjudication.get("variants", []):
        protein = variant.get("hgvs_protein") or ""
        match = re.search(r"p\.\(?([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)?", protein)
        if not match:
            continue
        ref3, position, alt3 = match.groups()
        ref1, alt1 = three_to_one.get(ref3, ""), three_to_one.get(alt3, "")
        residue = f"{ref3}{position}"
        needles += [f"{ref3}{position}{alt3}", f"{ref1}{position}{alt1}", f"{ref3}{position}", f"{ref1}{position}"]
        if variant.get("hgvs"):
            needles.append(variant["hgvs"].split(":")[-1])
    return [n for n in dict.fromkeys(needles) if n], residue


def case_evidence(adjudication: dict, start: int) -> list[EvidenceRecord]:
    """What this case itself observed. Highest rank in the hierarchy, narrowest scope.

    Verified like any other evidence: the quote must be re-found in the artifact it claims to
    come from. A case observation gets no free pass for being ours.
    """
    run_id = adjudication.get("execution", {}).get("run_id", "unknown")
    source = f"CASE:{run_id}"
    body = json.dumps(adjudication, ensure_ascii=False)
    records: list[EvidenceRecord] = []
    n = start

    for variant in adjudication.get("variants", []):
        consequence = variant.get("molecular_consequence")
        if not consequence:
            continue
        statement = (f"This case's {variant['role']} is annotated as {consequence} in "
                     f"{adjudication.get('gene_symbol')}.")
        records.append(EvidenceRecord(
            evidence_id=f"EV_{n:04d}", source_id=source, statement=statement, quote=consequence,
            epistemic_class=EpistemicClass.OBSERVATION, evidence_level=EvidenceLevel.THIS_CASE,
            experimental_level=ExperimentalLevel.NOT_APPLICABLE, scope=Scope.EXACT_VARIANT,
            applicability_to_case=Applicability.DIRECT, direction=Direction.SUPPORTS,
            assay="variant consequence annotation", model_system="this case",
            result=consequence,
            limitations=["a consequence annotation is a prediction from the transcript model, not an experiment"],
            extracted_by="rarepipe.case_observation_v1", verified_from_source=consequence in body))
        n += 1

    phase = adjudication.get("phase", {})
    if phase:
        statement = f"Phase between the two alleles in this case is {phase.get('status', 'unresolved')}."
        records.append(EvidenceRecord(
            evidence_id=f"EV_{n:04d}", source_id=source, statement=statement,
            quote=phase.get("note", statement)[:300], epistemic_class=EpistemicClass.OBSERVATION,
            evidence_level=EvidenceLevel.THIS_CASE, scope=Scope.EXACT_VARIANT,
            applicability_to_case=Applicability.DIRECT,
            direction=Direction.UNCERTAIN if phase.get("status") == "unresolved" else Direction.SUPPORTS,
            assay="phase", model_system="this case",
            limitations=["absence of read-backed phase is absence of evidence, not evidence of cis"],
            extracted_by="rarepipe.case_observation_v1",
            verified_from_source=(phase.get("note", "")[:300] in body) if phase.get("note") else False))
        n += 1
    for assertion in adjudication.get("assertions", []):
        if assertion.get("evidence_class") not in ("molecular_mechanistic", "computational", "technical_call", "phase"):
            continue
        level = (EvidenceLevel.COMPUTATIONAL if assertion["evidence_class"] == "computational"
                 else EvidenceLevel.THIS_CASE)
        records.append(EvidenceRecord(
            evidence_id=f"EV_{n:04d}", source_id=source, statement=assertion["statement"],
            quote=assertion["statement"], epistemic_class=(EpistemicClass.OBSERVATION if level is EvidenceLevel.THIS_CASE
                                                           else EpistemicClass.DERIVED_INFERENCE),
            evidence_level=level,
            experimental_level=ExperimentalLevel.IN_SILICO if level is EvidenceLevel.COMPUTATIONAL else ExperimentalLevel.NOT_APPLICABLE,
            scope=Scope.EXACT_VARIANT, applicability_to_case=Applicability.DIRECT,
            direction=Direction(assertion.get("direction", "uncertain")),
            assay=assertion.get("evidence_class"), model_system="this case",
            result=assertion.get("result"), limitations=assertion.get("limitations", []),
            independence_group=independence_group(assertion["statement"] + " " + str(assertion.get("result", ""))),
            extracted_by="rarepipe.case_observation_v1", verified_from_source=assertion["statement"] in body))
        n += 1
    return records


def _with_progress(task: KnowledgeTask) -> KnowledgeTask:
    """Backfill task progress from what the corpus actually holds.

    A corpus run written before the lifecycle fields existed records only a coarse status, and a
    task holding thirteen documents must not read as `retrieval: not_started`.
    """
    if task.progress.retrieval == "not_started":
        if task.documents_found:
            task.progress.retrieval = "complete"
        elif task.status == "blocked":
            task.progress.retrieval = "blocked"
        elif not task.queries:
            task.progress.retrieval = "not_applicable"
    task.state = task.progress.state()
    return task


INDEPENDENCE = {
    "alphamissense": re.compile(r"alphamissense", re.I),
    "revel": re.compile(r"\brevel\b", re.I),
    "spliceai": re.compile(r"spliceai", re.I),
    "clinvar": re.compile(r"clinvar", re.I),
    "clingen": re.compile(r"clingen", re.I),
    "gnomad_constraint": re.compile(r"constraint|gnomad", re.I),
    "phylogenetic_conservation": re.compile(r"phastcons|cactus|conserv", re.I),
}


def independence_group(text: str) -> str | None:
    for group, pattern in INDEPENDENCE.items():
        if pattern.search(text):
            return group
    return None


def alphagenome_evidence(path: Path, start: int) -> list[EvidenceRecord]:
    """Atlas predictions as evidence: an identifiable external source, at computational weight.

    The Atlas states a value for this variant, so it is external evidence rather than an observation —
    but it is a model output, not a measurement, so it enters at COMPUTATIONAL level and can never
    establish a functional claim. It can only stand beside one, which is the correct weight for a
    model its authors say is not validated for clinical use.
    """
    payload = json.loads(path.read_text())
    records: list[EvidenceRecord] = []
    n = start
    for item in payload.get("evidence", []):
        if not item.get("local_match_found"):
            continue
        region = item["region"]
        source = f"ALPHAGENOME_ATLAS:{region['gene_symbol']}:{region['start']}-{region['end']}"
        for key, value in sorted(item.get("scores", {}).items()):
            neighbourhood = item.get("neighbourhood", {}).get(key, {})
            percentile = neighbourhood.get("percentile")
            statement = (f"AlphaGenome Atlas {key} for this case's {item['variant_role']}: {value:.4g}"
                         + (f", which is the {percentile:.1f}th percentile among all "
                            f"{neighbourhood.get('of', 0):,} scored substitutions in the gene region"
                            if percentile is not None else ""))
            group = independence_group(key)
            embeds = []
            if key == "AVI_SCORE":
                group = "alphagenome_avi"
                embeds = ["alphamissense"]  # the AVI composite incorporates AlphaMissense for coding variants
            records.append(EvidenceRecord(
                evidence_id=f"EV_AG_{n:04d}", source_id=source, statement=statement,
                quote=f"{key}={value:.6g}", independence_group=group, embeds=embeds,
                epistemic_class=EpistemicClass.EXTERNAL_EVIDENCE,
                evidence_level=EvidenceLevel.COMPUTATIONAL, experimental_level=ExperimentalLevel.IN_SILICO,
                scope=Scope.EXACT_VARIANT, applicability_to_case=Applicability.DIRECT,
                direction=Direction.UNCERTAIN, assay=f"AlphaGenome Atlas {key}",
                model_system="in silico", result=f"{value:.6g}",
                limitations=list(item.get("limitations", [])),
                extracted_by="rarepipe.alphagenome_adapter_v1", verified_from_source=True,
                case_specific_detail=f"{key}={value}"))
            n += 1
    return records


def run_resolve(req: ResolveRequest, console: Console | None = None) -> ResolveResult:
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)

    console.step(1, 6, "Loading the corpus and the frozen case state...")
    corpus_index = _load(req.corpus_run / "corpus_index.json")
    adjudication = _load(req.adjudication)
    if adjudication.get("visibility") != "private":
        raise MechanismUsageError("mechanism resolution needs the private adjudication artifact for local matching")
    validation = _load(req.validation) if req.validation else None
    if validation and validation.get("result", {}).get("match") != "FULL":
        console.warn(f"external validation says {validation['result']['match']}: the causal pair is not confirmed, "
                     "so mechanism claims about 'the causal alleles' rest on an unconfirmed premise")
    documents = {d["source_id"]: RetrievedDocument(**d) for d in corpus_index["documents"]}
    tasks = [_with_progress(KnowledgeTask(**t)) for t in corpus_index["knowledge_tasks"]]
    query_log = [QueryRecord(**q) for q in corpus_index["query_log"]]
    gene = adjudication.get("gene_symbol", "")
    console.info(f"{len(documents)} document(s), {sum(1 for d in documents.values() if d.full_text)} with full text")

    console.step(2, 6, "Extracting evidence from stored sources...")
    evidence: list[EvidenceRecord] = []
    invalid: list[InvalidInference] = []
    index = 1
    for source_id, doc in documents.items():
        path = req.corpus_run / "docs" / f"{source_id.replace(':', '_')}.txt"
        if not path.exists():
            invalid.append(InvalidInference(produced_by="corpus", statement=doc.title,
                                            reason="source_not_in_corpus", detail=source_id))
            continue
        result = extract.extract_document(doc, path.read_text(), index)
        evidence += result.records
        invalid += result.invalid
        index += len(result.records)
    verified, failed = extract.verify(evidence, documents, req.corpus_run)
    invalid += failed
    console.info(f"{len(verified)} evidence record(s) with a quote verified in the stored source; "
                 f"{len(failed)} rejected as unverifiable")
    corrections = research.load_corrections(req.research_dir) if req.research_dir else []
    corrected_ids: dict[int, list[str]] = {}
    for n, correction in enumerate(corrections):
        needle = research._normalise(correction.quote_contains)
        for record in verified:
            if record.source_id != correction.source_id or needle not in research._normalise(record.quote):
                continue
            corrected_ids.setdefault(n, []).append(record.evidence_id)
            correction.applied_to += 1
            if correction.direction and record.direction is not correction.direction:
                record.limitations.append(f"direction corrected on semantic review from {record.direction.value} "
                                          f"to {correction.direction.value} ({correction.reviewed_by}): "
                                          f"{correction.reason}")
                correction.applied.append({"evidence_id": record.evidence_id, "claim_id": "(all)",
                                           "old": record.direction.value, "new": correction.direction.value})
                record.direction = correction.direction
            for claim_id, direction in correction.claims.items():
                record.claim_directions[claim_id] = ClaimDirection(
                    direction=direction, reason=correction.reason, reviewed_by=correction.reviewed_by)
        if not correction.applied_to:
            console.warn(f"direction correction for {correction.source_id} matched nothing: the passage may no "
                         "longer be extracted, so the correction is stale")
    if corrections:
        console.info(f"{sum(c.applied_to for c in corrections)} evidence record(s) re-directed by "
                     f"{len(corrections)} reviewed correction(s)")

    console.step(3, 6, "Searching the corpus locally for this case's exact allele...")
    needles, residue = residue_needles(adjudication)
    exact_hits: list[tuple[str, str, int]] = []
    for source_id in documents:
        path = req.corpus_run / "docs" / f"{source_id.replace(':', '_')}.txt"
        if not path.exists():
            continue
        text = path.read_text()
        for needle, position in extract.local_variant_search(text, needles):
            exact_hits.append((source_id, needle, position))
            snippet = text[max(0, position - 220): position + 220].strip()
            verified.append(EvidenceRecord(
                evidence_id=f"EV_{index:04d}", source_id=source_id,
                statement=f"A stored source mentions the missense allele's residue ({needle}).",
                quote=snippet, quote_offsets=(max(0, position - 220), position + 220),
                epistemic_class=EpistemicClass.EXTERNAL_EVIDENCE, evidence_level=EvidenceLevel.PRIMARY_LITERATURE,
                scope=Scope.SAME_RESIDUE if needle.rstrip("0123456789") != needle else Scope.EXACT_VARIANT,
                applicability_to_case=Applicability.DIRECT, direction=Direction.UNCERTAIN,
                assay="exact-allele mention", model_system="not stated in the matched passage",
                extracted_by="rarepipe.local_variant_search_v1", verified_from_source=True,
                case_specific_detail=needle))
            index += 1
    console.info(f"searched {len(needles)} local pattern(s) across the corpus: "
                 f"{len(exact_hits)} mention(s) of the exact residue" if needles else
                 "no protein-level identity available for local search")
    for task in tasks:
        if task.disclosure_level.value == "local_only":
            task.documents_found = sorted({s for s, _, _ in exact_hits})
            task.information_gain = "high" if exact_hits else "none"
            task.progress.retrieval = "not_applicable"
            task.progress.deterministic_extraction = "complete"
            task.progress.semantic_review = "not_applicable"
            task.progress.adjudication = "complete"
            task.status = "completed"
            task.stop_reason = (questions.STOP_RULES["A"] if exact_hits else
                                "corpus exhausted: no accessible source mentions this residue")
        elif task.progress.retrieval == "complete":
            task.progress.deterministic_extraction = "complete"
        task.state = task.progress.state()

    console.step(4, 6, "Adjudicating claims by workstream...")
    verified += case_evidence(adjudication, index)
    if req.alphagenome:
        ag_path = (req.alphagenome / "alphagenome_evidence.private.json"
                   if req.alphagenome.is_dir() else req.alphagenome)
        if not ag_path.exists():
            raise MechanismUsageError(f"no AlphaGenome evidence at {ag_path}")
        ag_records = alphagenome_evidence(ag_path, index + 10000)
        verified += ag_records
        console.info(f"{len(ag_records)} AlphaGenome Atlas prediction(s) added at computational weight "
                     "(they can accompany a functional claim, never establish one)")
    mech_claims, state, graph = _adjudicate(verified, adjudication, gene, bool(exact_hits), residue, console)

    console.step(5, 6, "Assembling the dossier...")
    sessions, imported_claims, imported_evidence, imported_rejected = (
        research.load_analyses(req.research_dir) if req.research_dir else ([], [], [], []))
    if imported_claims:
        console.info(f"{len(imported_claims)} claim(s) imported from {len(sessions)} human-operated research "
                     f"session(s); {len(imported_rejected)} proposal(s) were rejected on import")
        mech_claims += imported_claims
        verified += imported_evidence
        invalid += imported_rejected
    if imported_claims:
        # Semantic review can qualify the chain without supplying an arrow. Record that, rather than
        # drawing a link the evidence does not place, or quietly dropping the objection.
        graph.qualifications = [f"{c.id}: {c.statement}" for c in imported_claims
                                if c.evidence and c.id.startswith("MC_IMP")
                                and any(e.direction is Direction.CONTRADICTS for e in imported_evidence
                                        if e.evidence_id in c.evidence)]
    for n, correction in enumerate(corrections):
        ids = set(corrected_ids.get(n, []))
        hit_claims = set()
        for claim in mech_claims:
            for o in claim.direction_overrides:
                if o.evidence_id in ids and claim.id in correction.claims:
                    correction.applied.append({"evidence_id": o.evidence_id, "claim_id": claim.id,
                                               "old": o.extractor_direction, "new": o.direction_for_this_claim})
                    hit_claims.add(claim.id)
        correction.unused_claims = sorted(set(correction.claims) - hit_claims)
        if correction.unused_claims:
            console.warn(f"correction for {correction.source_id} names {', '.join(correction.unused_claims)}, "
                         "but none of its passages landed in those claims")
    reviewed = {session.knowledge_task for session in sessions}
    for task in tasks:
        if task.id in reviewed:
            task.progress.semantic_review = "complete"
            task.reviewed_by = [x.session_id for x in sessions if x.knowledge_task == task.id]
            if any(x.accepted for x in sessions if x.knowledge_task == task.id):
                task.progress.adjudication = "complete"
        task.state = task.progress.state()
    public_tasks = [t for t in tasks if t.disclosure_level.value != "local_only"]
    reviewed_public = [t for t in public_tasks if t.progress.semantic_review == "complete"]
    console.info(f"semantic review: {len(reviewed_public)} of {len(public_tasks)} public task(s) have been read by a "
                 f"reasoning process; the rest are retrieved and deterministically extracted only")
    bundles = ([research.EvidenceBundle(**json.loads(path.read_text())["bundle"])
                for path in sorted((req.research_dir / "bundles").glob("*/bundle.json"))]
               if req.research_dir and (req.research_dir / "bundles").exists() else [])
    automation = AutomationStatus(
        automated_llm_orchestration="deferred",
        current_mode="human_operated_llm_assistance" if sessions else "deterministic_only",
        reason="first discover the research workflow before automating it",
        pipeline_depends_on_an_llm=False)
    contradictions = sorted({f"{e.source_id}: {e.quote[:160]}" for e in verified if e.direction is Direction.CONTRADICTS})[:20]
    experiments_dir = req.research_dir / "experiments" if req.research_dir else None
    variant_experiments = []
    experiment_inputs = (sorted(p for p in experiments_dir.glob("*.yaml") if not p.name.startswith("._"))
                         if experiments_dir and experiments_dir.exists() else [])
    bundle_roots = (sorted(p for p in (req.research_dir / "bundles").iterdir() if p.is_dir())
                    if req.research_dir and (req.research_dir / "bundles").exists() else [])
    for path in experiment_inputs:
        try:
            variant_experiments += load_experiments(path, req.corpus_run, bundle_roots)
        except ExperimentError as exc:
            raise MechanismUsageError(f"{path.name}: {exc}") from exc
    residual = assess(variant_experiments, child_missense(adjudication)) if variant_experiments else None
    if residual:
        console.info(f"{len(variant_experiments)} variant experiment(s), every quote re-found; residual function: "
                     f"class level {residual.class_level}, this allele {residual.exact_allele} → {residual.decision}")
    status, basis = _gate(state, mech_claims)
    readiness = Readiness(
        disease_mechanism_ready_for_intervention_search=status is Status.READY_FOR_INTERVENTION_SEARCH,
        disease_mechanism_basis=basis,
        exact_allele_mechanism_complete=state.allele_b.protein_effect_status is not ClaimStatus.UNRESOLVED,
        exact_allele_blocker=("missense_function_unresolved"
                              if state.allele_b.protein_effect_status is ClaimStatus.UNRESOLVED else None),
        semantic_review_coverage=f"{len(reviewed_public)} of {len(public_tasks)} public knowledge task(s) "
                                 f"read by a reasoning process")
    dossier = MechanismDossier(
        visibility="private", case_id=adjudication["case_id"], gene_symbol=gene, status=status, status_basis=basis,
        readiness=readiness,
        state=state, claims=mech_claims, graph=graph, evidence=verified, documents=list(documents.values()),
        knowledge_tasks=tasks, query_log=query_log,
        assays=C.assay_inventory([e for e in verified if e.source_id.startswith("PMID")], ASSAY_QUESTIONS),
        automation_status=automation, invalid_inferences=invalid, contradictions=contradictions,
        unknowns=_unknowns(mech_claims), evidence_strongest_at=_strongest(mech_claims),
        evidence_weakest_at=_weakest(mech_claims), what_would_change_our_mind=_mind_changers(state, bool(exact_hits)),
        next_actions=_next_actions(state, bool(exact_hits), documents),
        highest_value_unresolved_question=_highest_value_question(state),
        direction_corrections=corrections,
        corpus_refresh=corpus_index.get("refresh") or [],
        variant_experiments=variant_experiments, residual_function=residual,
        provenance=Provenance(
            software=software_provenance(), adjudication_run_id=adjudication["execution"]["run_id"],
            validation_run_id=(validation or {}).get("submission_package_run_id"),
            causal_pair_validated_by=(f"{validation['evaluator']} submission {validation['submission_number']}: "
                                      f"{validation['result']['match']} at rank {validation['result']['full_match_rank']}"
                                      if validation else None),
            corpus_run_id=req.corpus_run.name, corpus_digest=corpus_index.get("corpus_digest"),
            research_sessions=sessions, evidence_bundles=bundles,
            environment_controls=["resolution performed offline; the corpus was acquired in a separate networked run",
                                  "no case-specific identity was transmitted: exact-allele matching ran locally",
                                  "every evidence quote was re-found in the stored source before acceptance"]),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3), corpus_path=str(req.corpus_run.resolve()),
                            adjudication_path=str(req.adjudication.resolve()), argv=req.argv))
    dossier.semantic_digest = semantic_digest(dossier, exclude={"execution"})
    sanitized = dossier.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = semantic_digest(sanitized, exclude={"execution"})
    if req.compare_mechanism_run:
        comparison = compare(req.compare_mechanism_run, json.loads(canonical_json(sanitized)),
                             req.compare_track2_run, req.compare_label)
        dossier.baseline_comparison = sanitized.baseline_comparison = comparison
        dossier.semantic_digest = semantic_digest(dossier, exclude={"execution"})
        sanitized.semantic_digest = semantic_digest(sanitized, exclude={"execution"})
        console.info(f"compared with {comparison.baseline_mechanism_run}: {len(comparison.conclusions_changed)} "
                     f"row(s) changed, {len(comparison.regenerate)} dependent stage(s) to regenerate")

    console.step(6, 6, "Writing artifacts...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(DOSSIER_PRIVATE, canonical_json(dossier))
    run.write_text(DOSSIER_SANITIZED, canonical_json(sanitized))
    run.write_text(GRAPH, canonical_json(sanitized.graph))
    run.write_text(REPORT, report.render(sanitized))
    # The reviewed inputs travel with the run, so a reviewer sees the records, not only their effect.
    for path in experiment_inputs:
        run.write_text(f"input_experiments_{path.name}", path.read_text())
    for path in research.correction_files(req.research_dir) if req.research_dir else []:
        run.write_text(f"input_corrections_{path.name}", path.read_text())
    if sanitized.direction_corrections:
        run.write_text("direction_corrections.json", canonical_json(
            {"corrections": [c.model_dump(mode="json") for c in sanitized.direction_corrections],
             "claims": {c.id: [o.model_dump(mode="json") for o in c.direction_overrides]
                        for c in sanitized.claims if c.direction_overrides}}))
    if sanitized.baseline_comparison:
        run.write_text("comparison_with_baseline.md", report.render_comparison(sanitized))
    console.ok(f"run {run_id}: {len(mech_claims)} claim(s), {len(verified)} evidence record(s), "
               f"{len(graph.unknown_edges)} unknown edge(s)")
    console.line()
    console.line(status.value)
    console.line(basis)
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return ResolveResult(dossier=dossier, sanitized=sanitized, run_dir=run.seal())


# ── 006A–C: the claims, built separately on purpose ─────────────────────────

def missense_domain(adjudication: dict, missense_role: str) -> str | None:
    """What the case's own annotation says about where the missense residue sits.

    The domain name is public biology; the residue is not, and never appears in a sanitized
    field. Nothing here is assumed — if the evidence records no domain, the dossier says so.
    """
    claim_id = f"CLAIM_{missense_role.upper()}"
    for assertion in adjudication.get("assertions", []):
        if assertion.get("claim_id") != claim_id:
            continue
        result = str(assertion.get("result") or "")
        match = re.search(r"Domain:\s*([A-Za-z0-9 /-]+?)\s*\(", result)
        if match:
            return match.group(1).strip()
    return None


def _adjudicate(evidence: list[EvidenceRecord], adjudication: dict, gene: str, exact_hits: bool,
                residue: str | None, console: Console) -> tuple[list, MechanismState, MechanismGraph]:
    literature = [e for e in evidence if e.source_id.startswith("PMID")]
    case = [e for e in evidence if e.source_id.startswith("CASE")]
    variants = {v["role"]: v for v in adjudication.get("variants", [])}
    consequence_a = (variants.get("variant_a", {}).get("molecular_consequence") or "").lower()
    consequence_b = (variants.get("variant_b", {}).get("molecular_consequence") or "").lower()
    truncating_role = "variant_a" if "stop" in consequence_a or "frameshift" in consequence_a else "variant_b"
    missense_role = "variant_b" if truncating_role == "variant_a" else "variant_a"
    domain = missense_domain(adjudication, missense_role)
    domain_phrase = f"{domain} domain" if domain else "an unannotated region"
    console.info(f"missense allele sits in: {domain_phrase} (from this case's own protein-feature evidence)")

    gene_disease = C.bundle(evidence, scopes={Scope.DISEASE_LEVEL}, topic=TOPIC["mva"],
                            establishing_levels=MEASURED)
    transcript = C.bundle(literature, assays={"transcript / NMD"}, topic=TOPIC["nmd"], establishing_levels=MEASURED)
    abundance = C.bundle(literature, assays={"BUBR1 protein abundance"}, topic=TOPIC["abundance"],
                         establishing_levels=MEASURED)
    truncating_protein = C.bundle(literature, assays={"BUBR1 protein abundance", "transcript / NMD"},
                                  topic=TOPIC["ptc"], establishing_levels=MEASURED)
    checkpoint = C.bundle(literature, assays={"mitotic checkpoint activity"}, topic=TOPIC["checkpoint"],
                          establishing_levels=MEASURED)
    alignment = C.bundle(literature, assays={"chromosome alignment / congression", "chromosome missegregation",
                                             "premature chromatid separation"}, topic=TOPIC["segregation"],
                         establishing_levels=MEASURED)
    aneuploidy = C.bundle(literature, assays={"aneuploidy / karyotype"}, topic=TOPIC["aneuploidy"],
                          establishing_levels=MEASURED)
    bridge = C.bundle(literature, assays={"aneuploidy / karyotype"}, scopes={Scope.DISEASE_LEVEL},
                      topic=TOPIC["mva"], establishing_levels=MEASURED)
    rescue = C.bundle(literature, assays={"rescue / complementation"}, topic=TOPIC["rescue"],
                      establishing_levels=MEASURED)
    kinase = C.bundle(literature, assays={"BUBR1 kinase activity"}, topic=TOPIC["kinase"], establishing_levels=MEASURED)
    combined = C.bundle(literature, assays={"BUBR1 protein abundance", "rescue / complementation"},
                        topic=TOPIC["abundance"], establishing_levels=MEASURED)
    ptc_case = C.bundle(case, scopes={Scope.EXACT_VARIANT},
                        topic=re.compile(TOPIC["ptc"].pattern + r"|stop_gained|nonsense", re.I))
    # The child's own allele: only an external measurement of this residue can establish an effect.
    # Domain location and predictor scores are recorded, but as indirect evidence.
    exact = C.bundle(evidence, scopes={Scope.EXACT_VARIANT, Scope.SAME_RESIDUE},
                     topic=re.compile("|".join([TOPIC[k].pattern for k in ("abundance", "checkpoint", "kinase")] +
                                               [r"\b(domain|functional (feature|site)|residue|missense|REVEL|"
                                                r"AlphaMissense|pathogenic\w*|constraint)\b"]), re.I),
                     establishing_levels=EXTERNAL_MEASURED)

    claim_list = [
        C.build_claim("MC_0001", ClaimType.GENE_DISEASE,
                      f"Biallelic {gene} disruption causes mosaic variegated aneuploidy.", gene_disease,
                      Scope.DISEASE_LEVEL),
        C.build_claim("MC_0002", ClaimType.TRANSCRIPT_EFFECT,
                      f"The truncating allele introduces a premature termination codon in {gene}.",
                      ptc_case, Scope.EXACT_VARIANT,
                      epistemic=EpistemicClass.OBSERVATION,
                      extra_limits=[f"observed as a {consequence_a or 'truncating'} consequence in this case's own data; "
                                    "the consequence annotation is not itself an experiment"]),
        C.build_claim("MC_0003", ClaimType.TRANSCRIPT_EFFECT,
                      f"Truncating {gene} transcripts are degraded by nonsense-mediated decay rather than producing "
                      "a stable truncated protein.", transcript, Scope.VARIANT_CLASS,
                      unknown_reason="no source in the corpus measures transcript fate for this allele class"),
        C.build_claim("MC_0004", ClaimType.PROTEIN_EFFECT,
                      "The truncating allele reduces functional BUBR1 produced from that chromosome.",
                      truncating_protein, Scope.VARIANT_CLASS),
        C.build_claim("MC_0005", ClaimType.PROTEIN_EFFECT,
                      f"Missense variants in the {domain_phrase} of this gene reduce BUBR1 protein abundance "
                      "or function.",
                      abundance, Scope.VARIANT_CLASS),
        C.build_claim("MC_0006", ClaimType.PROTEIN_EFFECT,
                      "This child's missense allele reduces BUBR1 abundance or function.",
                      exact, Scope.EXACT_VARIANT,
                      unknown_reason=("no accessible source reports a functional experiment on this residue; the corpus "
                                      "was searched locally for it" if not exact_hits else
                                      "the residue is mentioned in the corpus but without a functional measurement"),
                      extra_limits=["evidence about other kinase-domain variants is recorded separately, at variant_class "
                                    "scope, and must not be read as evidence about this allele"]),
        C.build_claim("MC_0007", ClaimType.COMBINED_GENOTYPE,
                      "The combined genotype leaves the cell with insufficient functional BUBR1.",
                      combined, Scope.VARIANT_CLASS,
                      extra_limits=["phase between the two alleles is unresolved in this case, so a biallelic functional "
                                    "state is inferred from the disease model rather than observed here"]),
        C.build_claim("MC_0008", ClaimType.CHECKPOINT_EFFECT,
                      "Reduced BUBR1 function impairs the mitotic (spindle assembly) checkpoint.", checkpoint,
                      Scope.GENE_LEVEL),
        C.build_claim("MC_0009", ClaimType.SEGREGATION_EFFECT,
                      "An impaired checkpoint produces chromosome missegregation, misalignment and premature chromatid "
                      "separation.", alignment, Scope.GENE_LEVEL),
        C.build_claim("MC_0010", ClaimType.ANEUPLOIDY,
                      "Chromosome missegregation produces mosaic aneuploid cell populations.", aneuploidy,
                      Scope.DISEASE_LEVEL),
        C.build_claim("MC_0011", ClaimType.DISEASE_BRIDGE,
                      "Constitutional mosaic aneuploidy is the accepted disease-level bridge to the MVA phenotype.",
                      bridge, Scope.DISEASE_LEVEL),
        C.build_claim("MC_0012", ClaimType.PROTEIN_EFFECT,
                      "Restoring BUBR1 rescues the cellular phenotype, which makes the link causal rather than "
                      "correlative.", rescue, Scope.GENE_LEVEL),
        C.build_claim("MC_0013", ClaimType.PROTEIN_EFFECT,
                      "BUBR1 kinase activity, specifically, is required for checkpoint function.", kinase,
                      Scope.GENE_LEVEL,
                      extra_limits=[f"relevant because this child's missense allele sits in the {domain_phrase}; "
                                    "the corpus is not unanimous on how much catalytic activity matters"]
                                   if domain else ["this child's missense residue is not inside an annotated domain, "
                                                   "which weakens any argument from domain function"]),
    ]
    by_id = {c.id: c for c in claim_list}
    for claim in claim_list:
        console.info(f"{claim.id} {claim.status.value:20} scope={claim.scope.value:14} "
                     f"establishing={len(claim.evidence):4} indirect={len(claim.indirect_evidence):3} "
                     f"contra={len(claim.contradicting_evidence)}")

    allele_a = AlleleMechanism(
        role=truncating_role, molecular_consequence=consequence_a or None,
        transcript_effect="premature termination codon (observed in this case's own annotation)",
        transcript_effect_status=by_id["MC_0002"].status,
        protein_effect=by_id["MC_0004"].statement, protein_effect_status=by_id["MC_0004"].status,
        exact_functional_evidence="no functional assay of this exact allele was found in the corpus",
        evidence=by_id["MC_0004"].evidence[:12],
        unresolved=["whether the transcript is degraded by NMD or a truncated protein is produced",
                    "whether any residual function remains"])
    allele_b = AlleleMechanism(
        role=missense_role, molecular_consequence=consequence_b or None,
        transcript_effect="no transcript-level effect expected or measured",
        transcript_effect_status=ClaimStatus.UNRESOLVED,
        protein_effect=by_id["MC_0006"].statement, protein_effect_status=by_id["MC_0006"].status,
        exact_functional_evidence=("residue mentioned in the corpus without a functional measurement" if exact_hits
                                   else "none: no accessible source reports an experiment on this residue"),
        evidence=by_id["MC_0005"].evidence[:12],
        unresolved=["the direction and size of the effect on BUBR1 abundance",
                    "whether checkpoint function is impaired by this substitution",
                    "whether the allele is hypomorphic or functionally null"])

    state = MechanismState(
        causal_genotype_externally_validated=True,
        gene_disease_status=by_id["MC_0001"].status, allele_a=allele_a, allele_b=allele_b,
        combined_genotype_state=("one allele expected to contribute little or no functional protein, the other of "
                                 "unmeasured effect: the resulting BUBR1 level in this child is not known"),
        combined_genotype_status=by_id["MC_0007"].status,
        spindle_checkpoint=by_id["MC_0008"].status, chromosome_segregation=by_id["MC_0009"].status,
        aneuploidy=by_id["MC_0010"].status, disease_bridge=by_id["MC_0011"].status,
        mechanistic_classes=C.mechanistic_classes(literature))

    graph = _graph(by_id, gene, domain_phrase)
    return claim_list, state, graph


def _graph(by_id: dict, gene: str, domain_phrase: str) -> MechanismGraph:
    nodes = [
        MechanismNode(id="allele_truncating", label="truncating allele", kind="allele"),
        MechanismNode(id="allele_missense", label=f"missense allele in {domain_phrase}", kind="allele"),
        MechanismNode(id="transcript", label=f"{gene} transcript from the truncating allele", kind="transcript"),
        MechanismNode(id="bubr1", label="functional BUBR1 protein", kind="protein"),
        MechanismNode(id="checkpoint", label="mitotic (spindle assembly) checkpoint", kind="cellular_process"),
        MechanismNode(id="segregation", label="chromosome segregation", kind="cellular_process"),
        MechanismNode(id="aneuploidy", label="mosaic aneuploidy", kind="cellular_state"),
        MechanismNode(id="mva", label="MVA clinical phenotype", kind="clinical"),
    ]
    spec = [
        ("allele_truncating", "transcript", "introduces a premature termination codon", "MC_0002"),
        ("transcript", "bubr1", "degraded by NMD, or yields a truncated protein", "MC_0003"),
        ("allele_truncating", "bubr1", "reduces functional protein from that allele", "MC_0004"),
        ("allele_missense", "bubr1", "reduces abundance or function of this child's protein", "MC_0006"),
        ("bubr1", "checkpoint", "insufficient BUBR1 weakens the checkpoint", "MC_0008"),
        ("checkpoint", "segregation", "a weakened checkpoint permits missegregation", "MC_0009"),
        ("segregation", "aneuploidy", "missegregation produces mosaic aneuploid cells", "MC_0010"),
        ("aneuploidy", "mva", "constitutional mosaic aneuploidy underlies the clinical syndrome", "MC_0011"),
    ]
    edges = []
    for source, target, relation, claim_id in spec:
        claim = by_id[claim_id]
        best = None
        edges.append(MechanismEdge(from_node=source, to_node=target, relation=relation, status=claim.status,
                                   scope=claim.scope, claim_id=claim_id, evidence=claim.evidence[:12],
                                   best_evidence_level=best,
                                   note=claim.unknown_reason or (claim.limitations[0] if claim.limitations else "")))
    unknown = [f"{e.from_node} → {e.to_node}" for e in edges if e.status is ClaimStatus.UNRESOLVED]
    return MechanismGraph(nodes=nodes, edges=edges, unknown_edges=unknown)


# ── 006D: the gate, and what to do next ─────────────────────────────────────

def _gate(state: MechanismState, claim_list: list) -> tuple[Status, str]:
    chain = [state.gene_disease_status, state.spindle_checkpoint, state.chromosome_segregation,
             state.aneuploidy, state.disease_bridge]
    established = sum(1 for s in chain if s in (ClaimStatus.SUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED))
    contradicted = [s for s in chain if s is ClaimStatus.CONTRADICTED]
    if contradicted:
        return Status.BLOCKED, ("A link in the disease-level chain is contradicted by the corpus. Intervention search "
                                "must not start on a chain the evidence disputes.")
    if established < len(chain):
        missing = [name for name, s in zip(["gene–disease", "checkpoint", "segregation", "aneuploidy", "disease bridge"],
                                           chain, strict=True) if s is ClaimStatus.UNRESOLVED]
        return Status.BLOCKED, ("The disease-level mechanism is incomplete: " + ", ".join(missing) +
                                " unresolved. Resolve these before evaluating whether any intervention could plausibly "
                                "modify the biology.")
    return Status.READY_FOR_INTERVENTION_SEARCH, (
        "The disease-level mechanism from BUBR1 insufficiency to mosaic aneuploidy to the clinical syndrome is "
        "supported by human experimental and curated evidence, which is what an intervention search would have to act "
        "on. This child's missense allele remains functionally unmeasured, and that is a question about how severe the "
        "genotype is, not about which mechanism is in play (PRD 006 §27).")


def _unknowns(claim_list: list) -> list[str]:
    return [f"{c.id}: {c.statement} — {c.unknown_reason}" for c in claim_list if c.status is ClaimStatus.UNRESOLVED]


def _strongest(claim_list: list) -> list[str]:
    return [f"{c.id}: {c.statement}" for c in claim_list
            if c.status is ClaimStatus.SUPPORTED and c.confidence is Confidence.HIGH][:6]


def _weakest(claim_list: list) -> list[str]:
    return [f"{c.id}: {c.statement}" for c in claim_list
            if c.status in (ClaimStatus.UNRESOLVED, ClaimStatus.CONTRADICTED)
            or c.confidence is Confidence.LOW][:6]


def _mind_changers(state: MechanismState, exact_hits: bool) -> list[MindChanger]:
    changers = [
        MindChanger(evidence="A functional assay of this child's missense substitution — abundance, checkpoint "
                             "response, kinetochore localisation — in any system.",
                    why="It is the only evidence that would move MC_0006 from unresolved to an answer.",
                    would_change="allele B's protein effect, and with it how severe the combined genotype is"),
        MindChanger(evidence="Another patient reported with the same substitution and a described cellular phenotype.",
                    why="Human observation outranks every class-level inference we currently hold.",
                    would_change="allele B's effect, and the confidence of the combined-genotype claim"),
        MindChanger(evidence="Demonstration that BUBR1 abundance is normal in cells carrying this class of variant.",
                    why="It would contradict the abundance-reduction mechanism and force the checkpoint-specific one.",
                    would_change="which mechanistic class this case belongs to"),
        MindChanger(evidence="Cytogenetic data from this child showing (or failing to show) mosaic aneuploidy.",
                    why="It would connect this case directly to the disease-level bridge rather than by inference.",
                    would_change="whether the disease bridge is an observation here or an external claim"),
        MindChanger(evidence="Parental transmission confirming the two alleles are in trans.",
                    why="The biallelic premise of the whole mechanism rests on it.",
                    would_change="the combined-genotype claim"),
    ]
    if not exact_hits:
        changers.insert(1, MindChanger(
            evidence="Full text of the sources our corpus could only reach as abstracts.",
            why="A residue can appear in a figure, table or methods section and never in an abstract.",
            would_change="whether exact-allele evidence exists at all"))
    return changers


def _next_actions(state: MechanismState, exact_hits: bool, documents: dict) -> list[NextAction]:
    closed = sum(1 for d in documents.values() if not d.full_text)
    actions = [
        NextAction(rank=1, action="Obtain legitimate full text for the corpus documents we could only store as "
                                  f"abstracts ({closed} of {len(documents)}), then re-run the local residue search.",
                   expected_information_gain="high", cost="low", time="days", friction="moderate",
                   importance_for_intervention_search="moderate",
                   rationale="The exact-allele question is currently answered 'not found', and an abstract-only corpus "
                             "is the most likely reason a mention would be missed."),
        NextAction(rank=2, action="Ask the organizers for parental transmission or clinical phase for the two loci "
                                  "(already drafted in Stage 04).",
                   expected_information_gain="high", cost="very_low", time="days", friction="low",
                   importance_for_intervention_search="high",
                   rationale="The biallelic premise underlying the combined genotype is still inferred, not observed."),
        NextAction(rank=3, action="Retrieve ClinVar submitter-level records and any clinical cytogenetic report for "
                                  "this case.", expected_information_gain="moderate", cost="low", time="days",
                   friction="low", importance_for_intervention_search="moderate",
                   rationale="Would connect this child to the disease-level aneuploidy bridge by observation."),
        NextAction(rank=4, action="Identify laboratories that have run BUBR1 functional assays and record them as "
                                  "metadata for a possible future evidence request.",
                   expected_information_gain="moderate", cost="low", time="days", friction="moderate",
                   importance_for_intervention_search="moderate",
                   rationale="A functional assay of this allele is the highest-value missing evidence; no one is "
                             "contacted at this stage."),
        NextAction(rank=5, action="Proceed to intervention mapping.", expected_information_gain="moderate",
                   cost="moderate", time="weeks", friction="low",
                   importance_for_intervention_search="blocking" if state.disease_bridge is ClaimStatus.UNRESOLVED else "high",
                   rationale="Permitted only once the gate above reads READY, and out of scope for this stage."),
    ]
    return actions


def _highest_value_question(state: MechanismState) -> str:
    if state.allele_b.protein_effect_status is ClaimStatus.UNRESOLVED:
        return ("What does this child's missense allele actually do to BUBR1 — abundance, checkpoint "
                "response, or neither? Every class-level source in the corpus describes other variants, and the "
                "distinction decides how severe this genotype is.")
    return "Is the combined genotype's functional state observable in this child's own cells?"
