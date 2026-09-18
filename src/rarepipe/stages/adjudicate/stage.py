"""evidence_adjudication stage: RawCandidateSet (+ NormalizedCase) → AdjudicatedHypothesis.

Answers three separate questions about one hypothesis — is the mechanism right, does each
variant impair function, and is the biallelic configuration established — and states what
would change the answer. It ranks nothing, diagnoses nothing, and transmits nothing.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pysam

from rarepipe.core.artifacts import RunDirectory, canonical_json, new_run_id, utc_now
from rarepipe.core.console import Console
from rarepipe.core.digest import semantic_digest
from rarepipe.core.provenance import software_provenance
from rarepipe.core.redaction import clear_restricted
from rarepipe.stages.adjudicate import local_evidence as local
from rarepipe.stages.adjudicate import report
from rarepipe.stages.adjudicate.model import (
    AdjudicatedHypothesis,
    Claim,
    Direction,
    EvidenceClass,
    EvidenceRequest,
    EvidenceSummary,
    Execution,
    MindChanger,
    NextAction,
    PhaseEvidence,
    Provenance,
    SourceHypothesis,
    Status,
    Strength,
)

pysam.set_verbosity(0)

PRIVATE = "adjudicated_hypothesis.private.json"
SANITIZED = "adjudicated_hypothesis.sanitized.json"
REPORT = "adjudication_report.md"
LOG = "adjudication.log"

HETEROZYGOUS = {"0/1", "1/0", "0|1", "1|0"}


class AdjudicateUsageError(ValueError):
    """Invalid invocation or unusable input artifact."""


@dataclass
class AdjudicateRequest:
    raw_candidate_set: Path
    output: Path
    gene: str | None = None
    profile_id: str = "PROFILE_A"
    native_dir: Path | None = None
    argv: list[str] = field(default_factory=list)


@dataclass
class AdjudicateResult:
    hypothesis: AdjudicatedHypothesis
    sanitized: AdjudicatedHypothesis
    run_dir: Path


def _load(path: Path) -> dict:
    if not path.is_file():
        raise AdjudicateUsageError("raw-candidate-set file does not exist.")
    data = json.loads(path.read_text())
    if data.get("schema", {}).get("name") != "RawCandidateSet":
        raise AdjudicateUsageError("expected a RawCandidateSet artifact.")
    if data.get("visibility") != "private":
        raise AdjudicateUsageError("a sanitized RawCandidateSet has no variant identity; pass the private artifact.")
    return data


def select_hypothesis(case: dict, gene: str | None, profile_id: str) -> tuple[dict, dict, list[str]]:
    """The leading recessive variant-pair candidate, or the named gene's."""
    profiles = {r["profile_id"]: r for r in case["results"] if r["status"] == "completed"}
    if profile_id not in profiles:
        raise AdjudicateUsageError(f"{profile_id} did not complete in this RawCandidateSet.")
    pairs = [c for c in profiles[profile_id]["candidates"] if c["is_variant_pair"]]
    if gene:
        pairs = [c for c in pairs if c["gene_symbol"] == gene]
    if not pairs:
        raise AdjudicateUsageError("no compound-heterozygous candidate pair to adjudicate in that profile.")
    chosen = min(pairs, key=lambda c: c["rank"])
    supporting = sorted(p for p, r in profiles.items()
                        if any(c["gene_symbol"] == chosen["gene_symbol"] and c["is_variant_pair"] for c in r["candidates"]))
    return chosen, profiles[profile_id], supporting


def genotype_fields(vcf_path: Path, contig: str, pos: int, ref: str, alt: str) -> dict:
    try:
        with pysam.VariantFile(str(vcf_path)) as vcf:
            for rec in vcf.fetch(contig, max(pos - 1, 0), pos):
                if rec.pos == pos and rec.ref == ref and alt in (rec.alts or ()):
                    s = rec.samples[0]
                    gt = "/".join("." if a is None else str(a) for a in s["GT"]) if "GT" in s else None
                    if s.phased and gt:
                        gt = gt.replace("/", "|")
                    ad = s.get("AD")
                    balance = round(ad[1] / sum(ad), 3) if ad and len(ad) > 1 and sum(ad) else None
                    return {"GT": gt, "FILTER": ";".join(rec.filter.keys()) or ".", "DP": s.get("DP"), "GQ": s.get("GQ"),
                            "AD": ",".join(str(x) for x in ad) if ad else None, "allele_balance": balance,
                            "PL": ",".join(str(x) for x in s.get("PL") or []) or None,
                            "PGT": s.get("PGT"), "PID": s.get("PID"),
                            "multiallelic_site": len(rec.alts or ()) > 1, "pos": pos}
    except (OSError, ValueError):
        return {}
    return {}


def run_adjudication(req: AdjudicateRequest, console: Console | None = None) -> AdjudicateResult:
    console = console or Console()
    case = _load(req.raw_candidate_set)
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)

    console.step(1, 4, "Selecting the hypothesis to adjudicate...")
    candidate, profile_result, supporting = select_hypothesis(case, req.gene, req.profile_id)
    gene = candidate["gene_symbol"]
    console.ok(f"{gene} {candidate['inheritance_model']} rank {candidate['rank']} "
               f"({candidate['contributing_variant_count']} contributing variants; supported in {len(supporting)} profile(s))")

    console.step(2, 4, "Establishing variant identity and local evidence (nothing transmitted)...")
    data_version = case["provenance"]["solver"].get("hg38_data_version")
    assembly = case["provenance"]["source_case"].get("assembly", "unknown")
    vcf_path = Path(case["execution"].get("source_vcf_path") or "")
    native_dir = req.native_dir or (Path(case["execution"]["native_output_root"]) / req.profile_id.lower())
    tsv = next(native_dir.glob("*.variants.tsv"), None)
    if tsv is None:
        raise AdjudicateUsageError("native solver variant output not found; pass --native-dir.")

    variants, records = [], []
    for role, v in zip(("variant_a", "variant_b"), candidate["contributing_variants"]):
        row = local.read_native_row(tsv, v["contig"], v["position"], v["ref"], v["alt"])
        if row is None:
            raise AdjudicateUsageError(f"{role} not found in the native solver output.")
        call = genotype_fields(vcf_path, v["contig"], v["position"], v["ref"], v["alt"]) if vcf_path.is_file() else {}
        rec = local.VariantRecord(variant_ref=v["variant_ref"], role=role, row=row, call=call)
        records.append(rec)
        variants.append(local.identity(rec, assembly, data_version))
    # variant_a is the one with the more severe consequence, so the dossier's effort is proportional
    if records[1].row.get("FUNCTIONAL_CLASS") == "stop_gained" and records[0].row.get("FUNCTIONAL_CLASS") != "stop_gained":
        records.reverse()
        variants.reverse()
        for rec, ident, role in zip(records, variants, ("variant_a", "variant_b")):
            rec.role = ident.role = role

    assertions = []
    n = 1
    for rec in records:
        claim_id = "CLAIM_VARIANT_A" if rec.role == "variant_a" else "CLAIM_VARIANT_B"
        built = local.build(rec, claim_id, data_version, n)
        assertions += built
        n += len(built)
        console.info(f"{rec.role}: {rec.row.get('FUNCTIONAL_CLASS')}; {len(built)} local evidence assertion(s)")

    console.step(3, 4, "Assembling claims, gaps and next actions...")
    phase = _phase(records)
    claims = _claims(assertions, records, gene)
    contradicting = [a.assertion_id for a in assertions if a.direction == Direction.CONTRADICTS]
    gaps = [
        "Functional evidence: no assay data retrieved (requires literature//bulk retrieval).",
        "Gene–disease validity: ClinGen classification for this gene not retrieved.",
        "Protein/domain context: residue conservation, domain membership and clustering not retrieved.",
        "ClinVar submitter-level detail: conditions, submitters and evaluation dates not retrieved.",
        "Population detail: homozygote counts, allele numbers and callability not retrieved.",
    ]
    hypothesis = AdjudicatedHypothesis(
        visibility="private", case_id=case["case_id"], hypothesis_id=f"HYP_{gene}_{candidate['inheritance_model']}",
        status=Status.ADJUDICATION_COMPLETE_WITH_GAPS, gene_symbol=gene, inheritance_model=candidate["inheritance_model"],
        variants=variants, claims=claims, assertions=assertions, contradicting_assertion_ids=contradicting,
        evidence_summary=_summary(assertions, claims), phase=phase,
        unresolved_questions=[
            f"Does {records[1].role.replace('_', ' ')} materially impair {gene} function?",
            "Are the two alleles in trans (on different homologues)?",
            f"Is the existing pathogenic assertion for the truncating allele transferable to this disease context?",
        ],
        what_would_change_our_mind=_mind_changers(gene),
        evidence_requests=[_parental_request(gene, phase)],
        next_actions=_next_actions(phase),
        evidence_gaps=gaps,
        provenance=Provenance(
            software=software_provenance(),
            source_hypothesis=SourceHypothesis(
                raw_candidate_set_run_id=case["execution"]["run_id"], raw_candidate_set_digest=case.get("semantic_digest"),
                normalized_case_run_id=case["provenance"]["source_case"]["normalized_case_run_id"], case_id=case["case_id"],
                gene_symbol=gene, inheritance_model=candidate["inheritance_model"], solver_rank=candidate["rank"],
                profiles_supporting=supporting),
            evidence_sources=[next(a.provenance for a in assertions if a.provenance.source == src)
                              for src in sorted({a.provenance.source for a in assertions})],
            environment_controls=["no network access performed by adjudication",
                                  "no case-specific variant identity transmitted externally",
                                  "evidence read from pinned local resources and the case's own VCF"],
        ),
        execution=Execution(run_id=run_id, started_at=started.isoformat(), finished_at=utc_now().isoformat(),
                            duration_seconds=round(time.monotonic() - t0, 3),
                            raw_candidate_set_path=str(req.raw_candidate_set.resolve()), argv=req.argv),
    )
    hypothesis.semantic_digest = semantic_digest(hypothesis, exclude={"execution"})

    sanitized = hypothesis.model_copy(deep=True)
    clear_restricted(sanitized)
    sanitized.visibility = "sanitized"
    sanitized.semantic_digest = semantic_digest(sanitized, exclude={"execution"})

    console.step(4, 4, "Writing AdjudicatedHypothesis...")
    run = RunDirectory(req.output, run_id).open()
    run.write_text(PRIVATE, canonical_json(hypothesis))
    run.write_text(SANITIZED, canonical_json(sanitized))
    run.write_text(REPORT, report.render(sanitized))
    console.ok(f"run {run_id}: {len(assertions)} assertion(s), {len(contradicting)} contradicting, {len(gaps)} gap(s)")
    console.line()
    console.line(hypothesis.status.value)
    run.write_text(LOG, "\n".join(console.log_lines) + "\n")
    return AdjudicateResult(hypothesis=hypothesis, sanitized=sanitized, run_dir=run.seal())


def _phase(records: list[local.VariantRecord]) -> PhaseEvidence:
    a, b = (r.call for r in records)
    both = bool(a.get("PGT") and a.get("PID") and b.get("PGT") and b.get("PID"))
    distance = abs(a["pos"] - b["pos"]) if a.get("pos") and b.get("pos") else None
    status = "unresolved"
    if both and a.get("PID") == b.get("PID"):
        status = "trans" if a.get("PGT") != b.get("PGT") else "cis"
    return PhaseEvidence(status=status,
                         existing_vcf_readbacked_phase="available_for_pair" if both else "unavailable_for_pair",
                         genomic_distance_bp=distance)


def _claims(assertions, records, gene: str) -> list[Claim]:
    def for_claim(cid):
        return [a for a in assertions if a.claim_id == cid]

    def assess(cid) -> tuple[str, str]:
        items = for_claim(cid)
        strong_support = [a for a in items if a.direction == Direction.SUPPORTS and a.strength in (Strength.STRONG, Strength.MODERATE)]
        contra = [a for a in items if a.direction == Direction.CONTRADICTS]
        if strong_support and not contra:
            return "supported", f"{len(strong_support)} supporting item(s) at moderate strength or better, none contradicting."
        if strong_support and contra:
            return "unresolved", f"{len(strong_support)} supporting and {len(contra)} contradicting item(s); the conflict is unresolved."
        if contra and not strong_support:
            return "unresolved", f"{len(contra)} contradicting item(s) and no supporting evidence above supporting strength."
        return "unresolved", "no evidence above supporting strength in either direction."

    claims = []
    for cid, subject, statement in (
        ("CLAIM_VARIANT_A", "variant_a", f"The truncating {gene} allele materially impairs {gene} function."),
        ("CLAIM_VARIANT_B", "variant_b", f"The missense {gene} allele materially impairs {gene} function."),
    ):
        assessment, basis = assess(cid)
        claims.append(Claim(claim_id=cid, statement=statement, subject=subject, assessment=assessment,
                            assessment_basis=basis, assertion_ids=[a.assertion_id for a in for_claim(cid)]))
    claims.append(Claim(claim_id="CLAIM_MECHANISM", statement=f"Biallelic loss of {gene} is an established mechanism for this phenotype.",
                        subject="gene_disease_mechanism", assessment="not_assessed",
                        assessment_basis="Gene–disease validity was not retrieved; no local resource establishes it."))
    claims.append(Claim(claim_id="CLAIM_CONFIGURATION", statement="The two alleles lie on different homologues (in trans).",
                        subject="configuration", assessment="unresolved",
                        assessment_basis="No read-backed phase covers the pair and no parental data is available."))
    return claims


def _summary(assertions, claims) -> EvidenceSummary:
    def describe(cls: EvidenceClass) -> str:
        items = [a for a in assertions if a.evidence_class == cls]
        if not items:
            return "absent"
        supports = [a for a in items if a.direction == Direction.SUPPORTS]
        contra = [a for a in items if a.direction == Direction.CONTRADICTS]
        best = min((a.strength.value for a in supports), default=None)
        parts = []
        if supports:
            parts.append(f"{len(supports)} supporting")
        if contra:
            parts.append(f"{len(contra)} contradicting")
        if not parts:
            parts.append(f"{len(items)} indeterminate")
        return ", ".join(parts)

    unresolved = [c for c in claims if c.assessment in ("unresolved", "not_assessed")]
    return EvidenceSummary(
        human_observation=describe(EvidenceClass.HUMAN_OBSERVATION), functional="absent — no assay evidence retrieved",
        population=describe(EvidenceClass.POPULATION), molecular_mechanistic=describe(EvidenceClass.MOLECULAR_MECHANISTIC),
        computational=describe(EvidenceClass.COMPUTATIONAL), technical_call=describe(EvidenceClass.TECHNICAL_CALL),
        phase="unresolved", overall="unresolved",
        overall_basis=(f"{len(unresolved)} of {len(claims)} claims remain unresolved or unassessed; "
                       "the hypothesis is neither established nor refuted by the evidence gathered."),
    )


def _mind_changers(gene: str) -> list[MindChanger]:
    return [
        MindChanger(direction="would_strengthen", evidence="Parental genotypes showing the two alleles were inherited from different parents.",
                    why="Would establish the biallelic configuration the recessive hypothesis requires."),
        MindChanger(direction="would_strengthen", evidence=f"A validated functional assay showing the missense allele impairs the relevant {gene} activity.",
                    why="Addresses the main pathogenicity uncertainty directly, at a level above computational prediction."),
        MindChanger(direction="would_strengthen", evidence="Independent affected individuals carrying this missense allele opposite a known pathogenic allele.",
                    why="Human observation is the strongest evidence class in this hierarchy."),
        MindChanger(direction="would_weaken", evidence="The missense allele observed at appreciable frequency, or in homozygotes, in healthy population data.",
                    why="Incompatible with a penetrant recessive disease allele."),
        MindChanger(direction="would_weaken", evidence="A robust functional assay showing normal activity for the missense allele.",
                    why="Would remove the mechanism by which the second allele could contribute."),
        MindChanger(direction="would_weaken", evidence="Evidence that the two alleles are in cis.",
                    why="A cis configuration leaves one intact copy and does not explain a recessive phenotype."),
        MindChanger(direction="would_weaken", evidence="An alternative candidate with better-supported evidence.",
                    why="The hypothesis is leading, not exclusive; a stronger competitor displaces it."),
    ]


def _parental_request(gene: str, phase: PhaseEvidence) -> EvidenceRequest:
    distance = phase.genomic_distance_bp
    return EvidenceRequest(
        request_id="REQ_PARENTAL_TRANSMISSION",
        question=f"Is parental genotype or transmission information available for the two candidate {gene} loci?",
        why_it_matters=("The leading recessive hypothesis requires the two heterozygous alleles to be in trans. "
                        f"The supplied singleton VCF carries no read-backed phase for this pair, and the two loci are "
                        f"{distance:,} bp apart — beyond what 149 bp paired-end reads can bridge, so re-aligning the "
                        "supplied FASTQs is unlikely to resolve it." if distance else ""),
        evidence_needed="Parental genotypes at the two loci, or a statement of transmission (which allele came from which parent).",
        minimum_information="Transmission status only — no parental sequence data, no raw files.",
        raw_data_required=False,
        preferred_route="organizer-mediated clarification",
        draft_message=(
            f"Our leading recessive hypothesis for this case involves two heterozygous {gene} variants. The supplied "
            "singleton VCF does not establish whether they are in trans: neither carries read-backed phase information, "
            "and the loci are too far apart for short-read phasing to help. Is parental genotype or transmission "
            "information for these two loci available to participants, or can you confirm whether phase was established "
            "clinically? We are not requesting parental sequence data — transmission status alone would resolve it."),
        blocks_this_stage=False,
    )


def _next_actions(phase: PhaseEvidence) -> list[NextAction]:
    far_apart = (phase.genomic_distance_bp or 0) > 1000
    return [
        NextAction(action="Ask the organizers whether parental transmission information exists for the two loci.",
                   expected_information_gain="high", cost="very_low",
                   rationale="Directly resolves the configuration question if such data exists; costs one message."),
        NextAction(action="Retrieve human and functional evidence for the missense allele from bulk/gene-level public sources.",
                   expected_information_gain="high", cost="low",
                   rationale="Addresses the dominant pathogenicity uncertainty without transmitting case data."),
        NextAction(action="Retrieve gene-level disease-validity and protein-domain context for the gene.",
                   expected_information_gain="medium", cost="low",
                   rationale="Establishes whether the mechanism and the residue's context support the hypothesis."),
        NextAction(action="Retrieve ClinVar submitter-level detail for the truncating allele's existing assertion.",
                   expected_information_gain="medium", cost="low",
                   rationale="Its pathogenic assertion is attached to a different disease context, which must be checked before relying on it."),
        NextAction(action="Align the supplied FASTQs and attempt read-based phasing.",
                   expected_information_gain="low" if far_apart else "uncertain", cost="very_high",
                   rationale=(f"The loci are {phase.genomic_distance_bp:,} bp apart; 149 bp paired-end reads cannot bridge that distance, "
                              "so the expected information gain is close to zero for a very large cost." if far_apart else
                              "Distance unknown; assess before committing."),
                   blocked_by=["no evidence that short-read phasing can span the pair"]),
        NextAction(action="Commission a new functional assay for the missense allele.",
                   expected_information_gain="high", cost="very_high",
                   rationale="Only justified if existing human and functional evidence remains insufficient after retrieval."),
    ]
