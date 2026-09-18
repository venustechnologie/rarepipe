"""Evidence from public resources, read locally.

Every function here takes a *pinned local file* (downloaded once, by gene or in bulk) and
queries it on this machine. Nothing about the case is transmitted: the ClinVar VCF is
region-queried locally with tabix, the ClinGen table is filtered by gene symbol, the UniProt
entry is fetched by protein accession, and literature is searched by gene-level terms whose
hits are then matched against our residue *locally*.

Any query string that would identify the case is refused by `disclosure.check_query`.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pysam

from rarepipe.stages.adjudicate.disclosure import check_query
from rarepipe.stages.adjudicate.model import (
    Direction,
    EvidenceAssertion,
    EvidenceClass,
    EvidenceProvenance,
    Retrieval,
    Strength,
)

pysam.set_verbosity(0)

HGVS_PROTEIN = re.compile(r"p\.\(?([A-Za-z]{3})(\d+)([A-Za-z]{3}|\*|=)?")
AA3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G",
    "His": "H", "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S",
    "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V", "Ter": "*",
}


@dataclass
class ProteinChange:
    position: int
    ref_aa3: str
    alt_aa3: str | None
    transcript: str | None
    coding: str | None

    @property
    def short(self) -> str:
        ref, alt = AA3_TO_1.get(self.ref_aa3, self.ref_aa3), AA3_TO_1.get(self.alt_aa3 or "", self.alt_aa3 or "")
        return f"{ref}{self.position}{alt}"


def parse_hgvs(hgvs: str | None) -> ProteinChange | None:
    """Exomiser writes GENE:TRANSCRIPT:c.…:p.… — split it into a precise identity."""
    if not hgvs:
        return None
    parts = hgvs.split(":")
    transcript = next((p for p in parts if p.startswith(("ENST", "NM_", "XM_"))), None)
    coding = next((p for p in parts if p.startswith("c.")), None)
    protein = next((p for p in parts if p.startswith("p.")), None)
    m = HGVS_PROTEIN.search(protein or "")
    if not m:
        return None
    return ProteinChange(position=int(m.group(2)), ref_aa3=m.group(1), alt_aa3=m.group(3), transcript=transcript, coding=coding)


# ── ClinVar (bulk VCF, queried locally by region) ───────────────────────────


def clinvar_records(vcf_path: Path, contig: str, start: int, end: int) -> list[dict]:
    """All ClinVar records in a region. The region is derived locally; nothing is sent anywhere."""
    out = []
    with pysam.VariantFile(str(vcf_path)) as vcf:
        for name in (contig, f"chr{contig}", contig.removeprefix("chr")):
            try:
                for rec in vcf.fetch(name, max(start - 1, 0), end):
                    info = rec.info
                    out.append({
                        "pos": rec.pos, "ref": rec.ref, "alts": list(rec.alts or ()),
                        "variation_id": rec.id,
                        "clnsig": ";".join(info.get("CLNSIG", ()) or ()),
                        "clnrevstat": ";".join(info.get("CLNREVSTAT", ()) or ()),
                        "clndn": ";".join(info.get("CLNDN", ()) or ()),
                        "clnvc": info.get("CLNVC"),
                        "mc": ";".join(info.get("MC", ()) or ()),
                    })
                break
            except (ValueError, OSError):
                continue
    return out


def clinvar_release(vcf_path: Path) -> str | None:
    with pysam.VariantFile(str(vcf_path)) as vcf:
        for rec in str(vcf.header).splitlines():
            if rec.startswith("##fileDate") or "ClinVar" in rec and "Date" in rec:
                return rec.split("=", 1)[-1]
    return None


def clinvar_provenance(version: str | None, identifier: str | None = None) -> EvidenceProvenance:
    return EvidenceProvenance(source="ClinVar VCF (GRCh38, bulk download)", source_version=version, identifier=identifier,
                              retrieval=Retrieval.BULK_PUBLIC, query=check_query("local region query against the bulk file"),
                              url="https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz")


def exact_record(records: list[dict], pos: int, ref: str, alt: str) -> dict | None:
    return next((r for r in records if r["pos"] == pos and r["ref"] == ref and alt in r["alts"]), None)


# ── ClinGen gene–disease validity (bulk CSV, filtered by gene) ──────────────


def clingen_validity(csv_path: Path, gene: str) -> list[dict]:
    check_query(gene)
    rows = []
    text = csv_path.read_text(errors="replace").splitlines()
    header_idx = next((i for i, line in enumerate(text) if line.upper().startswith(("GENE SYMBOL", '"GENE SYMBOL', "GENE_SYMBOL"))), None)
    if header_idx is None:
        return rows
    reader = csv.DictReader(text[header_idx:])
    for row in reader:
        symbol = (row.get("GENE SYMBOL") or row.get("GENE_SYMBOL") or "").strip().strip('"')
        if symbol.upper() == gene.upper():
            rows.append({k.strip(): (v or "").strip() for k, v in row.items() if k})
    return rows


# ── UniProt (gene-level entry, features read locally) ───────────────────────


def uniprot_features_at(entry_path: Path, position: int) -> list[dict]:
    data = json.loads(entry_path.read_text())
    hits = []
    for feature in data.get("features", []):
        loc = feature.get("location", {})
        start, end = (loc.get("start") or {}).get("value"), (loc.get("end") or {}).get("value")
        if start is None or end is None:
            continue
        if start <= position <= end:
            hits.append({"type": feature.get("type"), "description": feature.get("description"),
                         "start": start, "end": end})
    return hits


def uniprot_sequence_aa(entry_path: Path, position: int) -> str | None:
    seq = json.loads(entry_path.read_text()).get("sequence", {}).get("value")
    return seq[position - 1] if seq and 0 < position <= len(seq) else None


def uniprot_provenance(accession: str, version: str | None = None) -> EvidenceProvenance:
    return EvidenceProvenance(source="UniProtKB entry", source_version=version, identifier=accession,
                              retrieval=Retrieval.GENE_LEVEL_LOOKUP, query=check_query(accession),
                              url=f"https://rest.uniprot.org/uniprotkb/{accession}.json")


# ── literature (gene-level search, matched locally) ─────────────────────────


def literature_hits(records_path: Path, tokens: list[str]) -> list[dict]:
    """Papers from a gene-level search whose text mentions one of our local tokens."""
    if not records_path.is_file():
        return []
    papers = json.loads(records_path.read_text())
    hits = []
    for paper in papers:
        blob = " ".join(str(paper.get(k) or "") for k in ("title", "abstractText", "keywords"))
        matched = [t for t in tokens if t and t.lower() in blob.lower()]
        if matched:
            hits.append({**{k: paper.get(k) for k in ("id", "pmid", "doi", "title", "journal", "pubYear")}, "matched": matched})
    return hits


def literature_provenance(query: str, retrieved_at: str | None, identifier: str | None = None) -> EvidenceProvenance:
    return EvidenceProvenance(source="Europe PMC (gene-level search)", identifier=identifier, retrieval=Retrieval.GENE_LEVEL_LOOKUP,
                              retrieved_at=retrieved_at, query=check_query(query), url="https://www.ebi.ac.uk/europepmc/webservices/rest/search")


# ── assertion builders ──────────────────────────────────────────────────────


def build_clinvar_assertions(next_id, claim_id: str, exact: dict | None, gene_records: list[dict], change: ProteinChange | None,
                             version: str | None) -> list[EvidenceAssertion]:
    out = []
    if exact:
        sig, rev, conditions = exact["clnsig"], exact["clnrevstat"], exact["clndn"]
        pathogenic = "Pathogenic" in sig and "Conflicting" not in sig
        benign = "Benign" in sig and "Pathogenic" not in sig
        out.append(EvidenceAssertion(
            assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.HUMAN_OBSERVATION,
            statement=f"The current ClinVar release classifies this variant as {sig or 'unclassified'}.",
            result=f"{sig}; review status: {rev}; reported conditions: {conditions}",
            direction=Direction.SUPPORTS if pathogenic else Direction.CONTRADICTS if benign else Direction.UNCERTAIN,
            strength=Strength.MODERATE if pathogenic and "criteria_provided" in rev else Strength.SUPPORTING if pathogenic or benign else Strength.INDETERMINATE,
            strength_basis=("ClinVar review status indicates assertion confidence; 'criteria provided, multiple submitters, no conflicts' "
                            "or expert-panel review carries more weight than a single submitter."),
            provenance=clinvar_provenance(version, identifier=f"VariationID {exact['variation_id']}"),
            limitations=["Aggregate classification; submitter-level evidence was not individually reviewed.",
                         "The reported conditions may differ from this case's phenotype."],
            case_specific_detail=f"ClinVar VariationID {exact['variation_id']} — {sig} for {conditions}"))
    else:
        out.append(EvidenceAssertion(
            assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.HUMAN_OBSERVATION,
            statement="This variant has no record in the current ClinVar release.",
            result="absent from ClinVar", direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
            strength_basis="Absence of a submission is absence of evidence, in either direction.",
            provenance=clinvar_provenance(version),
            limitations=["Other submission databases were not consulted.",
                         "Absence may reflect that no laboratory has reported this variant, not that it is unremarkable."]))

    # gene-level context: what ClinVar holds for this gene, and for this residue
    pathogenic_in_gene = [r for r in gene_records if "Pathogenic" in r["clnsig"] and "Conflicting" not in r["clnsig"]]
    benign_in_gene = [r for r in gene_records if "Benign" in r["clnsig"] and "Pathogenic" not in r["clnsig"]]
    out.append(EvidenceAssertion(
        assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.MOLECULAR_MECHANISTIC,
        statement="Classification landscape for this gene in the current ClinVar release.",
        result=f"{len(gene_records)} records in the gene region: {len(pathogenic_in_gene)} pathogenic/likely pathogenic, {len(benign_in_gene)} benign/likely benign",
        direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
        strength_basis="Gene-level context only: it describes what has been reported in the gene, not this allele.",
        provenance=clinvar_provenance(version),
        limitations=["Counts include all variant types and all reported conditions."]))
    return out


def build_clingen_assertion(next_id, claim_id: str, rows: list[dict], gene: str) -> EvidenceAssertion:
    if not rows:
        return EvidenceAssertion(
            assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.MOLECULAR_MECHANISTIC,
            statement=f"No ClinGen gene–disease validity classification was found for {gene} in the downloaded table.",
            result="no matching row", direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
            strength_basis="Absence from the curation table means the gene–disease pair has not been curated, not that it is invalid.",
            provenance=EvidenceProvenance(source="ClinGen gene–disease validity (bulk download)", retrieval=Retrieval.BULK_PUBLIC,
                                          query=check_query(gene), url="https://search.clinicalgenome.org/kb/gene-validity"),
            limitations=["Only the gene-validity table was consulted; dosage sensitivity and VCEP specifications were not."])
    summaries = []
    for r in rows:
        disease = r.get("DISEASE LABEL") or r.get("DISEASE_LABEL") or ""
        classification = r.get("CLASSIFICATION") or ""
        moi = r.get("MOI") or r.get("MODE OF INHERITANCE") or ""
        summaries.append(f"{disease} — {classification} ({moi})")
    definitive = any("definitive" in (r.get("CLASSIFICATION") or "").lower() or "strong" in (r.get("CLASSIFICATION") or "").lower() for r in rows)
    return EvidenceAssertion(
        assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.MOLECULAR_MECHANISTIC,
        statement=f"ClinGen has curated the {gene} gene–disease relationship.",
        result="; ".join(summaries),
        direction=Direction.SUPPORTS if definitive else Direction.UNCERTAIN,
        strength=Strength.MODERATE if definitive else Strength.INDETERMINATE,
        strength_basis=("ClinGen gene–disease validity classifications ('Definitive', 'Strong', …) are expert-curated statements "
                        "about whether variation in the gene causes the disease."),
        provenance=EvidenceProvenance(source="ClinGen gene–disease validity (bulk download)", retrieval=Retrieval.BULK_PUBLIC,
                                      query=check_query(gene), url="https://search.clinicalgenome.org/kb/gene-validity"),
        limitations=["Gene-level statement: it does not establish that these particular alleles are causal.",
                     "The curated inheritance pattern must match the configuration proposed here."])


def build_uniprot_assertion(next_id, claim_id: str, features: list[dict], residue: str | None, change: ProteinChange | None,
                            accession: str) -> EvidenceAssertion:
    domains = [f for f in features if f["type"] in ("Domain", "Region", "Binding site", "Active site", "Motif", "Coiled coil")]
    matches_ref = residue is not None and change is not None and residue == AA3_TO_1.get(change.ref_aa3)
    described = "; ".join(f"{f['type']}: {f['description'] or 'unnamed'} ({f['start']}–{f['end']})" for f in domains) or "no annotated domain or site at this residue"
    return EvidenceAssertion(
        assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.MOLECULAR_MECHANISTIC,
        statement=("The affected residue lies within an annotated functional feature of the protein." if domains
                   else "The affected residue lies outside any annotated domain or functional site."),
        result=described + (f"; reference residue confirmed as {residue}" if matches_ref else
                            f"; WARNING: UniProt residue {residue} does not match the annotation's reference amino acid" if residue else ""),
        direction=Direction.SUPPORTS if domains else Direction.UNCERTAIN,
        strength=Strength.SUPPORTING if domains else Strength.INDETERMINATE,
        strength_basis=("Domain membership is context for plausibility, not evidence of functional disruption; "
                        "ACMG PM1 requires a mutational hot spot or well-established functional domain without benign variation."),
        provenance=uniprot_provenance(accession),
        limitations=["Domain membership does not establish that this substitution impairs function.",
                     "Residue conservation across species was not computed.",
                     "No structural modelling was performed."])


def build_literature_assertions(next_id, claim_id: str, hits: list[dict], query: str, retrieved_at: str | None,
                                total_searched: int) -> list[EvidenceAssertion]:
    if not hits:
        return [EvidenceAssertion(
            assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.FUNCTIONAL,
            statement="No publication from the gene-level literature search mentions this residue or substitution.",
            result=f"0 of {total_searched} retrieved records matched the residue tokens",
            direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
            strength_basis="Absence of published functional work on a specific residue is common and is not evidence of benignity.",
            provenance=literature_provenance(query, retrieved_at),
            limitations=["Only titles, abstracts and keywords were searched; full texts were not retrieved.",
                         "A paper may study the residue without naming it in the abstract.",
                         "Assay evidence for nearby residues was not assessed."])]
    out = []
    for hit in hits[:10]:
        out.append(EvidenceAssertion(
            assertion_id=next_id(), claim_id=claim_id, evidence_class=EvidenceClass.FUNCTIONAL,
            statement=f"A publication mentions this residue or substitution: {hit.get('title')}",
            result=f"matched {', '.join(hit['matched'])} in {hit.get('journal')} {hit.get('pubYear')}",
            direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
            strength_basis=("A mention is not functional evidence. Assay type, biological system, controls and whether the assay "
                            "reflects the disease mechanism must be assessed before any strength is assigned."),
            provenance=literature_provenance(query, retrieved_at, identifier=f"PMID {hit.get('pmid') or hit.get('id')}"),
            limitations=["Retrieved by abstract match only; the paper has not been read or appraised.",
                         "Strength deliberately withheld pending assessment of the assay itself."]))
    return out


def build_transfer_assertion(next_id, exact: dict | None, clingen_rows: list[dict], version: str | None) -> EvidenceAssertion | None:
    """Does the prior classification's disease context match the gene–disease relationship this
    hypothesis rests on? Compared between two public resources — no disease name is assumed."""
    if not exact:
        return None
    conditions = (exact.get("clndn") or "").replace("_", " ").lower()
    curated = [(r.get("DISEASE LABEL") or r.get("DISEASE_LABEL") or "").lower() for r in clingen_rows]
    curated = [c for c in curated if c]
    matched = [c for c in curated if c and c in conditions]
    if not curated:
        return None
    return EvidenceAssertion(
        assertion_id=next_id(), claim_id="CLAIM_PRIOR_CLASSIFICATION_TRANSFER", evidence_class=EvidenceClass.HUMAN_OBSERVATION,
        statement=("The prior classification was asserted for the same disease that ClinGen curates for this gene."
                   if matched else
                   "The prior classification's reported conditions do not include the disease ClinGen curates for this gene."),
        result=(f"ClinVar conditions: {exact.get('clndn')}; ClinGen curated disease(s): {', '.join(curated)}"),
        direction=Direction.SUPPORTS if matched else Direction.CONTRADICTS,
        strength=Strength.MODERATE if matched else Strength.SUPPORTING,
        strength_basis=("Two independent public resources are compared: the conditions a ClinVar submission was made for, "
                        "and the gene–disease relationship ClinGen has curated. No disease name is assumed by this pipeline."),
        provenance=clinvar_provenance(version, identifier=f"VariationID {exact['variation_id']}"),
        limitations=["Condition names are matched textually; synonyms or subtypes may not align.",
                     "Submitter-level conditions were not inspected individually."])
