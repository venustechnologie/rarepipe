"""Stage 07 — build the InterventionMap from the frozen mechanism dossier. Offline, no drug anything.

Everything here derives from Stage 06's claims, its rescue evidence, its assay inventory and its
qualifications. Nothing is invented because it sounds therapeutic, and no medication is named.
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
from rarepipe.stages.intervention import report
from rarepipe.stages.intervention.model import (
    ActionOutcome,
    AxisState,
    AxisSupport,
    CandidateAxis,
    DesiredEffect,
    Direction,
    Execution,
    ForbiddenEffect,
    InterventionMap,
    InterventionPoint,
    InterventionSearchSpec,
    MechanisticAxis,
    MindChanger,
    NegativePredictionEvidence,
    PointStatus,
    Priority,
    Provenance,
    ReversibilityClaim,
    Role,
    Scope,
    Status,
    ValidationEndpoints,
)

MAP_PRIVATE = "intervention_map.private.json"
MAP_SANITIZED = "intervention_map.sanitized.json"
REPORT = "intervention_logic.md"
LOG = "intervention.log"

# A model feature contributing less than this share of the total predicted impact is not a
# positive signal for that mechanism. It is also not evidence that the mechanism is absent.
MATERIAL_SHARE = 0.05


class InterventionUsageError(ValueError):
    pass


@dataclass
class BuildRequest:
    mechanism_run: Path
    output: Path
    research_dir: Path | None = None
    argv: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    intervention_map: InterventionMap
    sanitized: InterventionMap
    run_dir: Path


def _load(path: Path) -> dict:
    if not path.exists():
        raise InterventionUsageError(f"not found: {path}")
    return json.loads(path.read_text())


def negative_predictions(evidence: list[dict]) -> list[NegativePredictionEvidence]:
    """Read the Atlas attribution as what it is: a share of predicted impact, not a verdict.

    A feature contributing a negligible share is a reason to deprioritize that mechanism while the
    protein-level signal dominates. The object says, in its own fields, that this establishes nothing
    about whether the effect exists.
    """
    atlas = [e for e in evidence if e.get("source_id", "").startswith("ALPHAGENOME_ATLAS")]
    if not atlas:
        return []
    features: dict[str, float] = {}
    for record in atlas:
        match = re.search(r"AVI_SCORE_FEATURE_IMPORTANCE:(\w+)", record.get("assay", ""))
        if match and record.get("result"):
            features[match.group(1)] = max(features.get(match.group(1), 0.0), abs(float(record["result"])))
    if not features:
        return []
    total = sum(features.values()) or 1.0
    protein_share = (features.get("ALPHAMISSENSE", 0.0) + features.get("PROTEIN_TERMINATION", 0.0)) / total
    out: list[NegativePredictionEvidence] = []
    for hypothesis, keys in (("major_splice_effect", ["MERGED_SPLICING"]),
                             ("transcriptional_or_expression_effect", ["MAX_ABS_RNA_SEQ", "MAX_ABS_CAGE",
                                                                       "MAX_ABS_PROCAP", "MAX_ABS_POLYADENYLATION"])):
        share = sum(features.get(k, 0.0) for k in keys) / total
        if share < MATERIAL_SHARE and protein_share > share:
            out.append(NegativePredictionEvidence(
                hypothesis=hypothesis, source="AlphaGenome Atlas (AVI feature attribution)",
                scope=Scope.EXACT_VARIANT,
                detail=(f"this mechanism accounts for {share * 100:.1f}% of the predicted impact, against "
                        f"{protein_share * 100:.1f}% from protein-level features; a computational attribution, "
                        "not a measurement"),
                evidence=[e["evidence_id"] for e in atlas
                          if any(k in e.get("assay", "") for k in keys)]))
    return out


def _endpoints(dossier: dict) -> ValidationEndpoints:
    """Only endpoints the dossier's own assay inventory actually reports."""
    assays = {a["assay"]: a for a in dossier.get("assays", [])}
    pick = lambda names: [a for a in names if a in assays]  # noqa: E731
    return ValidationEndpoints(
        proximal=pick(["BUBR1 protein abundance", "transcript / NMD"]),
        cellular=pick(["mitotic checkpoint activity", "chromosome alignment / congression",
                       "chromosome missegregation", "premature chromatid separation",
                       "kinetochore localisation", "BUBR1 kinase activity"]),
        disease_related=pick(["aneuploidy / karyotype"]),
        sources=sorted({s for a in assays.values() for s in a.get("sources", [])})[:10])


def build(req: BuildRequest, console: Console | None = None) -> BuildResult:
    console = console or Console()
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)

    console.step(1, 4, "Reading the frozen mechanism dossier...")
    dossier = _load(req.mechanism_run / "mechanism_dossier.private.json")
    if dossier.get("status") != "MECHANISM_READY_FOR_INTERVENTION_SEARCH":
        raise InterventionUsageError(
            f"the mechanism dossier is {dossier.get('status')}: intervention logic must not be built on a "
            "mechanism the evidence does not support")
    claims = {c["id"]: c for c in dossier["claims"]}
    evidence = {e["evidence_id"]: e for e in dossier["evidence"]}
    state = dossier["state"]
    gene = dossier["gene_symbol"]
    console.info(f"{len(claims)} claim(s), {len(evidence)} evidence record(s), "
                 f"{len(dossier['graph'].get('qualifications', []))} chain qualification(s)")

    rescue = [e for e in dossier["evidence"] if e.get("rescue_experiment")
              and e.get("direction") == "supports" and e.get("evidence_level") in
              ("human_experimental", "primary_literature", "this_case", "expert_curated")]
    console.info(f"{len(rescue)} rescue/complementation record(s) — the evidence that makes a direction causal")

    console.step(2, 4, "Deriving mechanistic axes...")
    negatives = negative_predictions(dossier["evidence"])
    for negative in negatives:
        console.info(f"{negative.hypothesis}: {negative.result} — {negative.detail[:96]}")
    deprioritized = [CandidateAxis(
        axis=n.hypothesis.replace("_", " "), state=AxisState.DEPRIORITIZED,
        reason=f"no material positive computational signal ({n.detail})", evidence_type="computational",
        reopen_if=["human RNA or transcript evidence for this allele",
                   "a direct transcript or minigene assay",
                   "a stronger splice or expression prediction from an independent method"],
        evidence=n.evidence) for n in negatives]

    exact_measured = state["allele_b"]["protein_effect_status"] != "UNRESOLVED"
    protein_axis = MechanisticAxis(
        id="MA_001", biological_level="protein",
        state=f"dysfunctional or insufficient functional {state.get('gene_symbol', 'BUBR1') or 'BUBR1'} protein",
        support=AxisSupport(
            human_experimental=any(e["evidence_level"] == "human_experimental" for e in dossier["evidence"]),
            curated_human_evidence=claims["MC_0001"]["status"] == "SUPPORTED",
            primary_literature=True,
            human_class_level=claims["MC_0005"]["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED"),
            exact_variant_experimental=exact_measured,
            computational_exact_variant=any(e["source_id"].startswith("ALPHAGENOME_ATLAS")
                                            for e in dossier["evidence"]),
            supporting_claims=["MC_0001", "MC_0004", "MC_0005", "MC_0007", "MC_0012"],
            supporting_evidence=[e["evidence_id"] for e in rescue][:10]),
        competing_axes=deprioritized, confidence="moderate",
        limitations=["the exact biochemical effect of this child's missense allele is unknown",
                     "class-level evidence describes other variants, not this allele",
                     "the computational signal is dominated by AlphaMissense, which the case already held: "
                     "it is not an independent second witness"])
    cellular_axis = MechanisticAxis(
        id="MA_002", biological_level="cellular_process",
        state="impaired mitotic checkpoint, chromosome alignment and segregation fidelity",
        support=AxisSupport(
            human_experimental=True, curated_human_evidence=True, primary_literature=True,
            human_class_level=True, exact_variant_experimental=False, computational_exact_variant=False,
            supporting_claims=["MC_0008", "MC_0009", "MC_0010", "MC_0011"],
            supporting_evidence=[e["evidence_id"] for e in rescue][:10]),
        confidence="moderate",
        limitations=["whether these processes can be corrected without repairing BUBR1 itself is unknown",
                     "chromosome alignment is reported as separable from checkpoint function"])
    axes = [protein_axis, cellular_axis]

    console.step(3, 4, "Building intervention points...")
    endpoints = _endpoints(dossier)
    imported = {c["id"]: c for c in dossier["claims"] if c["id"].startswith("MC_IMP")}
    console.info(f"{len(imported)} claim(s) from human-operated research sessions are available to attach")
    points = _points(gene, claims, rescue, endpoints, exact_measured, dossier)
    _attach_imported(points, imported, dossier, console)
    forbidden = _forbidden(gene, claims, rescue)
    for point in points:
        console.info(f"{point.id} {point.status.value:14} {point.priority.value:11} "
                     f"exact-allele-dependent={str(point.requires_exact_allele_mechanism).lower():5} "
                     f"{point.biological_state[:44]}")
    specs = [_spec(p, gene, endpoints) for p in points if p.status is PointStatus.SUPPORTED]

    console.step(4, 4, "Writing the intervention map...")
    status, basis = _gate(points, specs)
    sessions = []
    if req.research_dir and (req.research_dir / "analyses").exists():
        sessions = [p.stem for p in sorted((req.research_dir / "analyses").glob("LLMRS_*.json"))]
    imap = InterventionMap(
        visibility="private", case_id=dossier["case_id"], gene_symbol=gene, status=status, status_basis=basis,
        axes=axes, intervention_points=points, forbidden_effects=forbidden, negative_predictions=negatives,
        deprioritized_axes=deprioritized,
        not_currently_justified=[f"{p.id}: {p.biological_state} — {p.limitations[0] if p.limitations else ''}"
                                 for p in points if p.status in (PointStatus.NOT_JUSTIFIED, PointStatus.DEPRIORITIZED)],
        unresolved_points=[f"{p.id}: {p.biological_state}" for p in points if p.status is PointStatus.UNRESOLVED],
        search_specs=specs, action_outcomes=_outcomes(negatives, exact_measured),
        knowledge_tasks=_tasks(dossier, req.research_dir),
        readiness={"approved_drug_search": {"ready": status is Status.READY, "basis": basis},
                   "exact_allele_mechanism": {"complete": exact_measured,
                                              "blocker": None if exact_measured else "missense_function_unresolved"}},
        provenance=Provenance(
            software=software_provenance(), mechanism_run_id=dossier["execution"]["run_id"],
            mechanism_digest=dossier.get("semantic_digest"), mechanism_status=dossier.get("status"),
            validation_run_id=dossier["provenance"].get("validation_run_id"),
            alphagenome_used=any(e["source_id"].startswith("ALPHAGENOME_ATLAS") for e in dossier["evidence"]),
            research_sessions=sessions,
            environment_controls=["built offline from the frozen dossier",
                                  "no drug, medication or compound database was consulted",
                                  "no medication is named, ranked or recommended"]),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3),
                            mechanism_path=str(req.mechanism_run.resolve()), argv=req.argv))
    imap.semantic_digest = semantic_digest(imap, exclude={"execution"})
    sanitized = imap.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = semantic_digest(sanitized, exclude={"execution"})

    run = RunDirectory(req.output, run_id).open()
    run.write_text(MAP_PRIVATE, canonical_json(imap))
    run.write_text(MAP_SANITIZED, canonical_json(sanitized))
    run.write_text(REPORT, report.render(sanitized))
    console.ok(f"run {run_id}: {len(points)} intervention point(s), {len(specs)} search spec(s), "
               f"{len(deprioritized)} deprioritized axis(es)")
    console.line()
    console.line(status.value)
    console.line(basis)
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return BuildResult(intervention_map=imap, sanitized=sanitized, run_dir=run.seal())


# Which kind of imported claim bears on which point. Deliberately coarse: the claim types come from
# the research schema, and anything finer would be keyword archaeology.
ATTACH = {
    "IP_001": {"protein_effect", "combined_genotype"},
    "IP_002": {"checkpoint_effect", "segregation_effect", "aneuploidy"},
}
CILIARY = re.compile(r"cili", re.I)
ONGOING = re.compile(r"postnatal|ongoing|with (natural )?ageing|with (natural )?aging|progeroid", re.I)


def _tasks(dossier: dict, research_dir: Path | None) -> list[dict]:
    """Every question that informed this map — the corpus's and the research workspace's."""
    tasks = list(dossier.get("knowledge_tasks", []))
    seen = {t.get("id") for t in tasks}
    if research_dir and (research_dir / "tasks").exists():
        for path in sorted((research_dir / "tasks").glob("KT_*.json")):
            task = json.loads(path.read_text())
            if task.get("id") not in seen:
                tasks.append(task)
    return tasks


def _attach_imported(points: list[InterventionPoint], imported: dict, dossier: dict, console: Console) -> None:
    """Fold the research sessions' claims into the points they bear on, and let them move a status."""
    evidence = {e["evidence_id"]: e for e in dossier["evidence"]}
    by_id = {p.id: p for p in points}
    for claim_id, claim in sorted(imported.items()):
        statement = claim["statement"]
        if CILIARY.search(statement):
            by_id["IP_003"].mechanism_claims.append(claim_id)
            continue
        for point_id, types in ATTACH.items():
            if claim["type"] in types:
                by_id[point_id].mechanism_claims.append(claim_id)
                if any(evidence.get(e, {}).get("rescue_experiment") for e in claim.get("evidence", [])):
                    by_id[point_id].rescue_evidence += [e for e in claim.get("evidence", [])
                                                        if evidence.get(e, {}).get("rescue_experiment")]
        if claim["type"] == "disease_bridge" and ONGOING.search(statement):
            ip1 = by_id["IP_001"]
            ip1.reversibility = ReversibilityClaim(
                biological_state="BubR1-level-dependent pathology", timing="both",
                reversible="partially_supported",
                evidence=list(claim.get("evidence", [])),
                note=("part of the pathology is ongoing and level-dependent rather than purely developmental, so "
                      "preventing further damage is coherent even where developmental damage is not reversible"))

    ciliary = by_id["IP_003"]
    if ciliary.mechanism_claims:
        supporting = [c for c in ciliary.mechanism_claims if imported[c]["evidence"]
                      and any(evidence.get(e, {}).get("direction") == "supports" for e in imported[c]["evidence"])]
        against = [c for c in ciliary.mechanism_claims if c not in supporting]
        ciliary.limitations.append(
            f"the corpus disagrees with itself: {len(supporting)} claim(s) assert a ciliary role, {len(against)} "
            "report no ciliary alteration where it was looked for. It stays a qualification until an experiment "
            "connects ciliary dysfunction to a phenotype in this genotype.")
    for point in points:
        point.mechanism_claims = sorted(set(point.mechanism_claims))
        point.rescue_evidence = sorted(set(point.rescue_evidence))
        console.info(f"{point.id}: {len(point.mechanism_claims)} claim(s), {len(point.rescue_evidence)} rescue record(s)")


def _points(gene: str, claims: dict, rescue: list[dict], endpoints: ValidationEndpoints,
            exact_measured: bool, dossier: dict) -> list[InterventionPoint]:
    """The points themselves, each tied to claims that already exist in the frozen dossier."""
    rescue_ids = [e["evidence_id"] for e in rescue][:12]
    qualifications = dossier["graph"].get("qualifications", [])
    ciliary = [q for q in qualifications if "cili" in q.lower()]
    beyond_protein = [q for q in qualifications if "beyond protein level" in q.lower()]

    ip1 = InterventionPoint(
        id="IP_001",
        biological_state=f"sufficient functional {gene}/BUBR1 activity and availability",
        role=Role.PROXIMAL_MECHANISM,
        desired_effect=DesiredEffect(
            target_state="functional BUBR1", current_state="insufficient or dysfunctional",
            desired_state="toward normal", direction=Direction.RESTORE,
            evidence=rescue_ids, confidence="moderate"),
        rationale=("Restoring BUBR1 in patient-derived cells restored mitotic checkpoint activity, which makes "
                   "this a causal rescue direction rather than an association. The state is defined broadly on "
                   "purpose: the reason this child's missense allele loses function is unknown, so the modality "
                   "that could restore it must not be pre-decided."),
        mechanism_claims=["MC_0001", "MC_0004", "MC_0007", "MC_0012"], evidence_scope=Scope.GENE_LEVEL,
        axis="MA_001",
        expected_downstream_effect="improved checkpoint response, chromosome alignment and segregation fidelity",
        rescue_evidence=rescue_ids, validation_endpoints=endpoints,
        reversibility=ReversibilityClaim(
            biological_state="mitotic fidelity", timing="unknown", reversible="unknown",
            note="whether correcting mitotic biology later reverses developmental consequences is not established "
                 "in the corpus; KT_I04 exists to ask it"),
        directness="upstream", requires_exact_allele_mechanism=False,
        status=PointStatus.SUPPORTED if rescue_ids else PointStatus.UNRESOLVED,
        priority=Priority.HIGH if rescue_ids else Priority.SPECULATIVE,
        confidence="moderate",
        limitations=["the rescue evidence is ectopic expression of BUBR1 in cells, which establishes a direction, "
                     "not that any intervention can achieve it",
                     "a molecular rescue is not a clinical rescue",
                     "class-level and disease-level scope: no experiment addressed this child's allele"],
        contraindicated_direction="any reduction of functional BUBR1",
        what_would_change_our_mind=MindChanger(
            would_strengthen="restoration of BUBR1 by a means other than artificial overexpression improving the "
                             "same endpoints",
            would_weaken="evidence that restoring BUBR1 after development does not improve cellular phenotypes",
            would_falsify="evidence that the disease phenotype is independent of BUBR1 availability"),
        track2_relevance="high")

    downstream_supported = claims["MC_0009"]["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    ip2 = InterventionPoint(
        id="IP_002",
        biological_state="checkpoint, chromosome-alignment and segregation fidelity, engaged downstream of BUBR1",
        role=Role.INTERMEDIATE_MECHANISM,
        desired_effect=DesiredEffect(
            target_state="mitotic fidelity", current_state="impaired", desired_state="toward normal",
            direction=Direction.RESTORE, evidence=claims["MC_0009"].get("evidence", [])[:8],
            confidence="low"),
        rationale=("Whether the cellular consequence can be corrected without repairing BUBR1 itself is the second "
                   "question, and may matter more for repurposing than raising BUBR1 directly. The corpus "
                   "establishes that these processes are impaired; it does not yet show that any of them has been "
                   "improved without correcting the gene."),
        mechanism_claims=["MC_0008", "MC_0009", "MC_0010"], evidence_scope=Scope.CELLULAR_PROCESS, axis="MA_002",
        expected_downstream_effect="reduced missegregation, and so reduced accumulation of aneuploid cells",
        rescue_evidence=[], validation_endpoints=endpoints,
        reversibility=ReversibilityClaim(biological_state="aneuploidy burden", timing="ongoing", reversible="unknown",
                                         note="existing aneuploid cells are not corrected by preventing future "
                                              "missegregation; prevention and reversal are different goals"),
        directness="intermediate", requires_exact_allele_mechanism=False,
        status=PointStatus.UNRESOLVED,
        priority=Priority.MODERATE if downstream_supported else Priority.SPECULATIVE, confidence="low",
        limitations=["no retrieved evidence shows checkpoint, alignment or segregation improved without directly "
                     "correcting BUB1B — KT_I02 exists to look for it",
                     "chromosome alignment is reported as separable from checkpoint function, so improving one "
                     "may not improve the other"],
        contraindicated_direction="anything that further weakens the spindle assembly checkpoint",
        what_would_change_our_mind=MindChanger(
            would_strengthen="an experiment improving segregation fidelity in BUB1B-deficient cells without "
                             "restoring BUB1B",
            would_weaken="evidence that downstream correction requires BUBR1 to be present",
            would_falsify="evidence that missegregation in this genotype is not correctable downstream"),
        track2_relevance="high")

    ip3 = InterventionPoint(
        id="IP_003", biological_state="BUBR1's non-mitotic role in primary cilium formation",
        role=Role.PROXIMAL_MECHANISM,
        desired_effect=DesiredEffect(target_state="ciliary function", current_state="unknown in this case",
                                     desired_state="unknown", direction=Direction.UNKNOWN, evidence=[],
                                     confidence="low"),
        rationale=("The dossier records a ciliary role as a qualification of the chain, not as a measured "
                   "contribution to this disease process. Promoting it to an intervention point would require "
                   "evidence connecting ciliary dysfunction to MVA phenotypes, which the corpus does not supply."),
        mechanism_claims=[], evidence_scope=Scope.GENE_LEVEL, axis=None,
        expected_downstream_effect="unknown", rescue_evidence=[],
        validation_endpoints=ValidationEndpoints(),
        reversibility=ReversibilityClaim(biological_state="ciliary function", timing="unknown", reversible="unknown"),
        directness="upstream", requires_exact_allele_mechanism=False,
        status=PointStatus.DEPRIORITIZED, priority=Priority.SPECULATIVE, confidence="low",
        limitations=["recorded as a mechanism qualification, with no evidence placing it in the causal chain for "
                     "this phenotype" + (f"; source: {ciliary[0][:80]}" if ciliary else "")],
        what_would_change_our_mind=MindChanger(
            would_strengthen="an experiment linking ciliary dysfunction to an MVA phenotype in a BUB1B genotype",
            would_weaken="evidence that the ciliary role is dispensable for the phenotypes of interest",
            would_falsify="evidence that MVA phenotypes arise entirely through mitotic mechanisms"),
        track2_relevance="low")

    ip4 = InterventionPoint(
        id="IP_004", biological_state="stabilisation of the mutant BUBR1 protein specifically",
        role=Role.PROXIMAL_MECHANISM,
        desired_effect=DesiredEffect(target_state="mutant protein stability", current_state="unknown",
                                     desired_state="unknown", direction=Direction.UNKNOWN, evidence=[],
                                     confidence="low"),
        rationale=("The class-level literature attributes low abundance partly to high turnover of missense "
                   "mutants in or near the kinase domain, and the computational attribution for this allele is "
                   "protein-dominated. That makes protein stability a working axis — it does not establish that "
                   "this child's protein is unstable, and no experiment has measured it."),
        mechanism_claims=["MC_0005", "MC_0006"], evidence_scope=Scope.EXACT_VARIANT, axis="MA_001",
        expected_downstream_effect="higher functional BUBR1 availability, if the premise holds",
        rescue_evidence=[], validation_endpoints=endpoints,
        reversibility=ReversibilityClaim(biological_state="protein abundance", timing="ongoing", reversible="unknown"),
        directness="upstream", requires_exact_allele_mechanism=True,
        status=PointStatus.NOT_JUSTIFIED if not exact_measured else PointStatus.UNRESOLVED,
        priority=Priority.SPECULATIVE, confidence="unresolved",
        limitations=["depends on an exact-allele mechanism that is unresolved: MC_0006 has no establishing evidence",
                     "the computational signal is dominated by AlphaMissense, which the case already held, so it "
                     "is not independent corroboration",
                     "kept as a narrower variant of IP_001 rather than replacing it"],
        what_would_change_our_mind=MindChanger(
            would_strengthen="a measurement of this substitution's effect on BUBR1 abundance or turnover",
            would_weaken="evidence that variants of this class maintain normal abundance yet still cause disease",
            would_falsify="a measurement showing this allele's protein is stable and functional"),
        track2_relevance="moderate")

    if beyond_protein:
        ip1.limitations.append("allelic effects beyond protein level contribute to disease heterogeneity, so "
                               "restoring availability may not address everything the genotype does")
    return [ip1, ip2, ip3, ip4]


def _forbidden(gene: str, claims: dict, rescue: list[dict]) -> list[ForbiddenEffect]:
    """Derived from the mechanism graph and functional evidence only — never from a prediction."""
    out = [ForbiddenEffect(
        biological_state=f"functional {gene}/BUBR1 availability", prohibited_direction=Direction.DECREASE,
        reason="reducing it moves the system further along the supported disease mechanism; the rescue evidence "
               "runs in the opposite direction",
        evidence=[e["evidence_id"] for e in rescue][:6], derived_from="functional_evidence")]
    if claims["MC_0008"]["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
        out.append(ForbiddenEffect(
            biological_state="spindle assembly checkpoint activity", prohibited_direction=Direction.DECREASE,
            reason="checkpoint impairment is the supported proximal cellular defect; weakening it further would be "
                   "expected to increase missegregation",
            evidence=claims["MC_0008"].get("evidence", [])[:6], derived_from="mechanism_graph"))
    if claims["MC_0010"]["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
        out.append(ForbiddenEffect(
            biological_state="chromosome missegregation and aneuploidy burden", prohibited_direction=Direction.INCREASE,
            reason="aneuploidy is the disease-level bridge; anything increasing missegregation acts along the "
                   "disease mechanism rather than against it",
            evidence=claims["MC_0010"].get("evidence", [])[:6], derived_from="mechanism_graph"))
    return out


def _spec(point: InterventionPoint, gene: str, endpoints: ValidationEndpoints) -> InterventionSearchSpec:
    return InterventionSearchSpec(
        spec_id=f"SPEC_{point.id.split('_')[1]}", intervention_point=point.id,
        biological_target=point.biological_state, desired_effect=point.desired_effect.direction,
        acceptable_mechanisms=["any mechanism with evidence of raising functional BUBR1 availability or activity",
                               "any mechanism with evidence of improving mitotic fidelity in cells deficient for it"],
        disallowed_mechanisms=[f"anything reducing functional {gene}/BUBR1 availability",
                               "anything weakening the spindle assembly checkpoint",
                               "anything increasing chromosome missegregation or aneuploidy"],
        expected_rescue_readout=endpoints.proximal + endpoints.cellular + endpoints.disease_related,
        minimum_evidence="mechanistic", patient_specificity=point.evidence_scope,
        exact_allele_dependency=point.requires_exact_allele_mechanism,
        uncertainties=list(point.limitations))


def _outcomes(negatives: list[NegativePredictionEvidence], exact_measured: bool) -> list[ActionOutcome]:
    """What the research actions actually bought. Kept so we eventually learn which are worth taking."""
    out = [ActionOutcome(
        action="query AlphaGenome Atlas for this variant's predicted molecular consequences",
        expected_gain="high",
        actual_result=("the predicted impact is protein-dominated, with no material splice or expression signal; "
                       "the exact missense mechanism remains unmeasured"),
        information_gain="moderate",
        case_state_change="splicing and transcription axes deprioritized; protein axis unchanged as the working one",
        lesson="a capability that removes candidate mechanisms is worth as much as one that adds them, and its "
               "score did not move a functional claim — which is the behaviour we wanted")]
    if not exact_measured:
        out.append(ActionOutcome(
            action="attempt to resolve the exact missense mechanism from the accessible literature",
            expected_gain="high", actual_result="no accessible source reports an experiment on this residue",
            information_gain="none", case_state_change="none",
            lesson="the question needs an experiment or full-text access, not more retrieval of the same corpus"))
    out.append(ActionOutcome(
        action="investigate the ciliary role as a candidate intervention point", expected_gain="moderate",
        actual_result="evidence insufficient to promote ciliary biology to a primary intervention point",
        information_gain="moderate", case_state_change="none",
        lesson="remains a mechanism qualification"))
    return out


def _gate(points: list[InterventionPoint], specs: list[InterventionSearchSpec]) -> tuple[Status, str]:
    supported = [p for p in points if p.status is PointStatus.SUPPORTED]
    if not supported:
        return Status.BLOCKED, ("No intervention point is supported: there is no biological state with a defined "
                                "direction and evidence behind it, so an approved-drug search would have nothing "
                                "to aim at.")
    if not specs:
        return Status.BLOCKED, "A point is supported but no search specification could be built from it."
    incomplete = [p for p in supported if p.desired_effect.direction is Direction.UNKNOWN
                  or not p.validation_endpoints.cellular]
    if incomplete:
        return Status.BLOCKED, (f"{', '.join(p.id for p in incomplete)} lack a direction or a measurable endpoint. "
                                "A target without a direction is how a search finds something that pushes the "
                                "wrong way.")
    return Status.READY, (
        f"{len(supported)} supported intervention point(s) with an explicit direction, causal rescue evidence and "
        f"measurable endpoints, and {len(specs)} search specification(s) stating what must not happen as well as "
        "what should. The exact-allele mechanism remains unresolved, and every point that depends on it is marked "
        "as depending on it.")
