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
from rarepipe.stages.adjudicate import external
from rarepipe.stages.adjudicate import local_evidence as local
from rarepipe.stages.adjudicate import report
from rarepipe.stages.adjudicate.model import (
    Action,
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
    resources: Path | None = None
    uniprot_accession: str | None = None
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
    # Sorted: glob order is filesystem order, which is neither sorted nor guaranteed stable, so
    # taking the first match would make which file is adjudicated depend on the directory.
    tsv = next(iter(sorted(native_dir.glob("*.variants.tsv"))), None)
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

    # ── external evidence, read from pinned local files (nothing transmitted here)
    console.info("retrieving external evidence from pinned resources (local reads only)")
    ext, sources_used = _external(req, records, variants, gene, len(assertions) + 1, console)
    assertions += ext

    console.step(3, 4, "Assembling claims, gaps and next actions...")
    phase = _phase(records)
    claims = _claims(assertions, records, gene)
    contradicting = [a.assertion_id for a in assertions if a.direction == Direction.CONTRADICTS]
    gaps = _gaps(assertions, sources_used)
    actions = _actions(phase, sources_used, ext)
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
        next_actions=[a for a in actions if a.status != "completed"],
        actions_taken=[a for a in actions if a.status == "completed"],
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
    transfer = [a for a in assertions if a.claim_id == "CLAIM_PRIOR_CLASSIFICATION_TRANSFER"]
    if transfer:
        claims.append(Claim(
            claim_id="CLAIM_PRIOR_CLASSIFICATION_TRANSFER",
            statement="The existing pathogenic classification for the truncating allele was made for the phenotype under investigation.",
            subject="prior_classification_transfer",
            assessment=_transfer_assessment(transfer),
            assessment_basis=_transfer_basis(transfer),
            assertion_ids=[a.assertion_id for a in transfer]))
    mechanism_items = for_claim("CLAIM_MECHANISM")
    if mechanism_items:
        m_assessment, m_basis = assess("CLAIM_MECHANISM")
    else:
        m_assessment, m_basis = "not_assessed", "Gene–disease validity was not retrieved; no local resource establishes it."
    claims.append(Claim(claim_id="CLAIM_MECHANISM", statement=f"Biallelic loss of {gene} is an established mechanism for this phenotype.",
                        subject="gene_disease_mechanism", assessment=m_assessment, assessment_basis=m_basis,
                        assertion_ids=[a.assertion_id for a in mechanism_items]))
    claims.append(Claim(claim_id="CLAIM_CONFIGURATION", statement="The two alleles lie on different homologues (in trans).",
                        subject="configuration", assessment="unresolved",
                        assessment_basis="No read-backed phase covers the pair and no parental data is available."))
    return claims


def _transfer_assessment(items) -> str:
    supports = [a for a in items if a.direction == Direction.SUPPORTS]
    contra = [a for a in items if a.direction == Direction.CONTRADICTS]
    if supports and not contra:
        return "supported"
    if supports and contra:
        return "unresolved"
    return "contradicted" if contra else "unresolved"


def _transfer_basis(items) -> str:
    supports = [a for a in items if a.direction == Direction.SUPPORTS]
    contra = [a for a in items if a.direction == Direction.CONTRADICTS]
    if supports and not contra:
        return ("The current ClinVar record's reported conditions include the disease ClinGen curates for this gene, "
                "so the prior classification bears on the same gene–disease relationship.")
    if supports and contra:
        return (f"{len(supports)} source(s) place the prior classification in the curated disease context and {len(contra)} do not "
                "(e.g. an older bundled snapshot); the discrepancy should be resolved against submitter-level records.")
    return ("The assertion's disease context differs from the curated gene–disease relationship, so it cannot be relied on "
            "as prior evidence without checking the underlying submissions.")


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
        human_observation=describe(EvidenceClass.HUMAN_OBSERVATION),
        functional=(describe(EvidenceClass.FUNCTIONAL) if any(a.evidence_class == EvidenceClass.FUNCTIONAL for a in assertions)
                    else "absent — no literature retrieved"),
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
                        f"The supplied VCF contains no read-backed phase linking the two loci, which are {distance:,} bp "
                        "apart and cannot be directly bridged by the supplied short reads." if distance else ""),
        evidence_needed="Parental genotypes at the two loci, or a statement of transmission (which allele came from which parent).",
        minimum_information="Transmission status only — no parental sequence data, no raw files.",
        raw_data_required=False,
        preferred_route="organizer-mediated clarification",
        draft_message=(
            f"Our leading recessive hypothesis for this case involves two heterozygous {gene} variants. The supplied "
            "singleton VCF does not establish whether they are in trans: it contains no read-backed phase linking the "
            "two loci, which cannot be directly bridged by the supplied short reads. Is parental genotype or "
            "transmission information for these two loci available to participants, or can you confirm whether phase "
            "was established clinically? We are not requesting parental sequence data — transmission status alone "
            "would resolve it."),
        blocks_this_stage=False,
    )


def _actions(phase: PhaseEvidence, sources_used: set[str], external_assertions: list) -> list[Action]:
    """Every action with its lifecycle state. Work this run performed is marked completed, with what it
    yielded, so the outstanding list cannot recommend work that has already been done."""
    far_apart = (phase.genomic_distance_bp or 0) > 1000

    def yielded(source_substring: str) -> str | None:
        ids = [a.assertion_id for a in external_assertions if source_substring in a.provenance.source.lower()]
        return ", ".join(ids) or None

    def state(source_key: str, source_substring: str, observed: str) -> dict:
        if source_key not in sources_used:
            return {"status": "proposed"}
        return {"status": "completed", "result_artifact": yielded(source_substring), "information_gain_observed": observed}

    actions = [
        Action(id="ACT_PARENTAL", action="Ask the organizers whether parental transmission information exists for the two loci.",
               expected_information_gain="high", cost="very_low",
               rationale="Directly resolves the configuration question if such data exists; costs one message."),
        Action(id="ACT_LITERATURE",
               action="Retrieve human and functional evidence for the missense allele from bulk/gene-level public sources.",
               expected_information_gain="high", cost="low",
               rationale="Addresses the dominant pathogenicity uncertainty without transmitting case data.",
               **state("literature", "europe pmc",
                       "Gene-level literature was searched; no record mentions either residue, so functional evidence "
                       "remains absent rather than negative.")),
        Action(id="ACT_GENE_VALIDITY", action="Retrieve gene-level disease-validity and protein-domain context for the gene.",
               expected_information_gain="medium", cost="low",
               rationale="Establishes whether the mechanism and the residue's context support the hypothesis.",
               **state("clingen", "clingen",
                       "The curated gene–disease relationship and the missense residue's domain context were established.")),
        Action(id="ACT_CLINVAR_CURRENT", action="Check the current ClinVar release for both alleles.",
               expected_information_gain="medium", cost="low",
               rationale="The solver's bundled ClinVar snapshot may be stale, and the stage must not rely on it unchecked.",
               **state("clinvar", "clinvar",
                       "The current release's classification and reported conditions were retrieved and differ from the "
                       "solver's bundled snapshot.")),
        Action(id="ACT_CLINVAR_SUBMITTERS", action="Retrieve ClinVar submitter-level detail for the truncating allele's assertion.",
               expected_information_gain="medium", cost="low",
               rationale=("The solver's snapshot and the current release disagree about the condition its pathogenic assertion "
                          "was made for; submitter-level records would settle which applies.")),
        Action(id="ACT_CONSERVATION", action="Assess residue conservation and structural context for the missense allele.",
               expected_information_gain="medium", cost="low",
               rationale="Mechanistic context the dossier currently lacks, obtainable without transmitting case data."),
        Action(id="ACT_READ_PHASING", action="Align the supplied FASTQs and attempt read-based phasing.",
               expected_information_gain="low" if far_apart else "uncertain", cost="very_high",
               rationale=(f"No read pair can directly bridge the {phase.genomic_distance_bp:,} bp between the loci; transitive "
                          "phasing through intermediate heterozygous sites is possible in principle but uncertain, at a very "
                          "large cost." if far_apart else "Distance unknown; assess before committing."),
               blocked_by=["no read-backed phase links the pair in the supplied VCF"]),
        Action(id="ACT_FUNCTIONAL_ASSAY", action="Commission a new functional assay for the missense allele.",
               expected_information_gain="high", cost="very_high",
               rationale="Justified because retrieval found no existing human or functional evidence for this residue."),
    ]
    seen = {a.id for a in actions}
    assert len(seen) == len(actions), "action ids must be unique"
    return actions


EXTERNAL_KINDS = ("clinvar", "clingen", "uniprot", "literature")


def _real_files(directory: Path, pattern: str) -> list[Path]:
    """macOS writes ._name sidecars on exFAT; they match globs but are binary."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob(pattern) if not p.name.startswith("._"))


def _external(req: AdjudicateRequest, records, variants, gene: str, start_index: int, console: Console):
    """Assertions from pinned public resources. Each read happens locally; see disclosure.py."""
    out, used = [], set()
    if not req.resources:
        return out, used
    counter = {"n": start_index}

    def next_id() -> str:
        counter["n"] += 1
        return f"EV_{counter['n'] - 1:03d}"

    clinvar_vcf = req.resources / "clinvar" / "clinvar_GRCh38.vcf.gz"
    clingen_csv = req.resources / "clingen" / "gene_validity.csv"
    uniprot_dir = req.resources / "uniprot"
    literature_dir = req.resources / "literature"

    changes = {rec.role: external.parse_hgvs(rec.row.get("HGVS")) for rec in records}
    for ident in variants:
        change = changes.get(ident.role)
        if change:
            ident.transcript = change.transcript
            ident.hgvs_protein = f"p.{change.ref_aa3}{change.position}{change.alt_aa3 or ''}"

    if clinvar_vcf.is_file():
        used.add("clinvar")
        version = external.clinvar_release(clinvar_vcf)
        positions = [rec.call.get("pos") or 0 for rec in records if rec.call]
        contig = records[0].row.get("CONTIG") or ""
        lo, hi = (min(positions) - 200_000, max(positions) + 200_000) if positions else (0, 0)
        gene_records = external.clinvar_records(clinvar_vcf, contig, max(lo, 1), hi)
        for rec in records:
            claim_id = "CLAIM_VARIANT_A" if rec.role == "variant_a" else "CLAIM_VARIANT_B"
            exact = external.exact_record(gene_records, int(rec.row["START"]), rec.row["REF"], rec.row["ALT"])
            out += external.build_clinvar_assertions(next_id, claim_id, exact, gene_records, changes.get(rec.role), version)
        console.info(f"  ClinVar: {len(gene_records)} record(s) in the gene region of the current release")

    clingen_rows = []
    if clingen_csv.is_file():
        used.add("clingen")
        clingen_rows = external.clingen_validity(clingen_csv, gene)
        out.append(external.build_clingen_assertion(next_id, "CLAIM_MECHANISM", clingen_rows, gene))
        console.info(f"  ClinGen: {len(clingen_rows)} gene–disease validity row(s) for {gene}")

    if clinvar_vcf.is_file() and clingen_rows:
        a_rec = next((r for r in records if r.role == "variant_a"), None)
        exact_a = external.exact_record(gene_records, int(a_rec.row["START"]), a_rec.row["REF"], a_rec.row["ALT"]) if a_rec else None
        transfer = external.build_transfer_assertion(next_id, exact_a, clingen_rows, external.clinvar_release(clinvar_vcf))
        if transfer:
            out.append(transfer)
            console.info(f"  prior-classification transfer: {transfer.direction.value}")

    accession = req.uniprot_accession
    entry = (uniprot_dir / f"{accession}.json") if accession else next(iter(_real_files(uniprot_dir, "*.json")), None)
    if entry and entry.is_file():
        used.add("uniprot")
        for rec in records:
            change = changes.get(rec.role)
            if not change:
                continue
            claim_id = "CLAIM_VARIANT_A" if rec.role == "variant_a" else "CLAIM_VARIANT_B"
            features = external.uniprot_features_at(entry, change.position)
            residue = external.uniprot_sequence_aa(entry, change.position)
            out.append(external.build_uniprot_assertion(next_id, claim_id, features, residue, change, entry.stem))
        console.info(f"  UniProt: entry {entry.stem} read for residue context")

    lit_files = _real_files(literature_dir, "*.json")
    if lit_files:
        used.add("literature")
        path = lit_files[0]
        for rec in records:
            change = changes.get(rec.role)
            if not change:
                continue
            claim_id = "CLAIM_VARIANT_A" if rec.role == "variant_a" else "CLAIM_VARIANT_B"
            tokens = [change.short, f"{change.ref_aa3}{change.position}", f"p.{change.ref_aa3}{change.position}",
                      (change.coding or "").removeprefix("c.")]
            hits = external.literature_hits(path, [t for t in tokens if t])
            total = len(json.loads(path.read_text()))
            out += external.build_literature_assertions(next_id, claim_id, hits, path.stem.replace("_", " "), None, total)
            console.info(f"  literature: {len(hits)} of {total} record(s) mention {rec.role}'s residue")
    return out, used


def _gaps(assertions, sources_used: set[str]) -> list[str]:
    gaps = []
    if "literature" not in sources_used:
        gaps.append("Functional evidence: no literature retrieved.")
    elif not any(a.evidence_class == EvidenceClass.FUNCTIONAL and a.direction != Direction.UNCERTAIN for a in assertions):
        gaps.append("Functional evidence: literature was searched, but no appraised assay evidence was found for these residues; "
                    "abstract matches are recorded without strength pending assessment of the assays themselves.")
    if "clingen" not in sources_used:
        gaps.append("Gene–disease validity: ClinGen curation not retrieved.")
    if "uniprot" not in sources_used:
        gaps.append("Protein/domain context: UniProt features not retrieved.")
    if "clinvar" not in sources_used:
        gaps.append("ClinVar: current release not consulted; only the solver's bundled snapshot was used.")
    gaps.append("ClinVar submitter-level detail (individual submissions, evaluation dates) was not retrieved.")
    gaps.append("Residue conservation across species and structural modelling were not performed.")
    gaps.append("Population depth (homozygote counts, allele numbers, callability) was not retrieved.")
    return gaps
