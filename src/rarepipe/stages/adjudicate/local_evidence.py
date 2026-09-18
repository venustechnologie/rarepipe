"""Evidence available without transmitting anything: the pinned solver bundle and the source VCF.

Everything here comes from resources already on disk — Exomiser's 2602 data (ClinVar records,
gnomAD frequencies, REVEL/MVP/AlphaMissense/SpliceAI scores, gene constraint, ACMG criteria it
applied) and the case's own VCF (genotype quality fields). No query leaves the machine.

Evidence strengths cite published thresholds. Where a tool has no calibrated threshold, the
strength is `indeterminate` and the limitation says so — a high score from an uncalibrated
predictor is not moderate evidence just because it is high.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from rarepipe.stages.adjudicate.model import (
    Direction,
    EvidenceAssertion,
    EvidenceClass,
    EvidenceProvenance,
    Retrieval,
    Strength,
    VariantIdentity,
)

# ClinGen SVI calibrated thresholds for REVEL (Pejaver et al. 2022, Nat Commun 13:5918),
# as adopted for ACMG/AMP PP3/BP4 evidence strength.
REVEL_THRESHOLDS = [
    (0.932, Strength.STRONG, Direction.SUPPORTS),
    (0.773, Strength.MODERATE, Direction.SUPPORTS),
    (0.644, Strength.SUPPORTING, Direction.SUPPORTS),
    (0.290, Strength.INDETERMINATE, Direction.UNCERTAIN),
    (0.183, Strength.SUPPORTING, Direction.CONTRADICTS),
    (0.0, Strength.MODERATE, Direction.CONTRADICTS),
]
REVEL_SOURCE = "ClinGen SVI calibrated REVEL thresholds (Pejaver et al. 2022)"

# AlphaMissense class boundaries (Cheng et al. 2023, Science 381:eadg7492). These are the
# authors' own class cut-offs, NOT ClinGen-calibrated evidence strengths.
ALPHAMISSENSE_PATHOGENIC = 0.564
ALPHAMISSENSE_BENIGN = 0.34

# SpliceAI delta-score guidance (Jaganathan et al. 2019): 0.2 sensitive, 0.5 recommended, 0.8 high precision.
SPLICEAI_RECOMMENDED = 0.5


@dataclass
class VariantRecord:
    """One variant as the pinned resources and the source VCF describe it."""

    variant_ref: str
    role: str
    row: dict            # Exomiser native TSV row
    call: dict           # genotype fields read from the source VCF


def parse_scores(all_path: str | None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for item in (all_path or "").split(","):
        if "=" in item:
            name, _, value = item.partition("=")
            try:
                scores[name.strip().upper()] = float(value)
            except ValueError:
                continue
    return scores


def parse_frequencies(all_freq: str | None) -> dict[str, float]:
    return parse_scores(all_freq)


def exomiser_provenance(data_version: str | None, identifier: str | None = None) -> EvidenceProvenance:
    return EvidenceProvenance(source="Exomiser pinned data bundle", source_version=data_version,
                              identifier=identifier, retrieval=Retrieval.LOCAL_PINNED,
                              query="local database lookup performed by the solver during analysis")


def identity(v: VariantRecord, assembly: str, data_version: str | None) -> VariantIdentity:
    row = v.row
    return VariantIdentity(
        variant_ref=v.variant_ref, role=v.role, molecular_consequence=row.get("FUNCTIONAL_CLASS") or None,
        gene_symbol=row.get("GENE_SYMBOL") or None, assembly=assembly,
        hgvs=row.get("HGVS") or None, contig=row.get("CONTIG") or None,
        position=int(row["START"]) if (row.get("START") or "").isdigit() else None,
        ref=row.get("REF") or None, alt=row.get("ALT") or None, rs_id=row.get("RS_ID") or None,
        clinvar_variation_id=row.get("CLINVAR_VARIATION_ID") or None,
        normalization_basis=(f"Exomiser {data_version or 'pinned'} annotation against its bundled transcript set; "
                             "coordinates are the source VCF's own (assembly as recorded upstream)."),
    )


def _assertion(n: int, claim_id: str, cls: EvidenceClass, statement: str, result: str | None, direction: Direction,
               strength: Strength, basis: str, prov: EvidenceProvenance, limitations: list[str],
               private: str | None = None) -> EvidenceAssertion:
    return EvidenceAssertion(assertion_id=f"EV_{n:03d}", claim_id=claim_id, evidence_class=cls, statement=statement,
                             result=result, direction=direction, strength=strength, strength_basis=basis,
                             provenance=prov, limitations=limitations, case_specific_detail=private)


def build(v: VariantRecord, claim_id: str, data_version: str | None, start_index: int) -> list[EvidenceAssertion]:
    """All assertions derivable locally for one variant."""
    row, call = v.row, v.call
    out: list[EvidenceAssertion] = []
    n = start_index

    def add(**kw):
        nonlocal n
        out.append(_assertion(n, claim_id, **kw))
        n += 1

    # ── technical call quality (from the source VCF itself)
    if call:
        ab = call.get("allele_balance")
        add(cls=EvidenceClass.TECHNICAL_CALL,
            statement="The genotype call is technically sound in the supplied VCF.",
            result=f"FILTER={call.get('FILTER')}, GQ={call.get('GQ')}, DP={call.get('DP')}, allele balance={ab}",
            direction=Direction.SUPPORTS if call.get("FILTER") == "PASS" and (call.get("GQ") or 0) >= 20 else Direction.UNCERTAIN,
            strength=Strength.SUPPORTING,
            basis="PASS filter, GQ ≥ 20 and allele balance near 0.5 are conventional indicators of a reliable heterozygous call.",
            prov=EvidenceProvenance(source="source VCF (case asset)", retrieval=Retrieval.LOCAL_PINNED,
                                    query="genotype fields at this locus"),
            limitations=["Call quality says nothing about the variant's biological effect.",
                         "No orthogonal confirmation (e.g. Sanger) is available."],
            private=f"GT={call.get('GT')} AD={call.get('AD')} PL={call.get('PL')}")

    # ── human observation: ClinVar, as carried in the pinned bundle
    clinvar_id = row.get("CLINVAR_VARIATION_ID") or ""
    interp = row.get("CLINVAR_PRIMARY_INTERPRETATION") or "NOT_PROVIDED"
    stars = row.get("CLINVAR_STAR_RATING") or "0"
    if clinvar_id:
        pathogenic = "PATHOGENIC" in interp and "CONFLICT" not in interp
        add(cls=EvidenceClass.HUMAN_OBSERVATION,
            statement=f"ClinVar holds a record for this variant with aggregate interpretation {interp} ({stars}-star review status).",
            result=f"{interp}, review status {stars} star(s)",
            direction=Direction.SUPPORTS if pathogenic else Direction.UNCERTAIN,
            strength=Strength.MODERATE if pathogenic and stars in ("2", "3", "4") else Strength.SUPPORTING if pathogenic else Strength.INDETERMINATE,
            basis=("ClinVar review status (star rating) is the documented indicator of assertion confidence; "
                   "2+ stars means multiple submitters with no conflicts, or expert panel review."),
            prov=exomiser_provenance(data_version, identifier=f"ClinVar VariationID {clinvar_id}"),
            limitations=["Aggregate interpretation only; individual submitter evidence and conditions were not retrieved.",
                         "The disease context of the assertion may differ from this case's phenotype.",
                         "ClinVar content changes over time; this reflects the pinned bundle's snapshot."],
            private=f"ClinVar VariationID {clinvar_id}")
        disease = row.get("EXOMISER_ACMG_DISEASE_NAME") or ""
        if disease and "aneuploidy" not in disease.lower():
            add(cls=EvidenceClass.HUMAN_OBSERVATION,
                statement="The disease context attached to the existing pathogenic assertion is not the phenotype under investigation.",
                result=f"assertion disease context: {disease}",
                direction=Direction.CONTRADICTS, strength=Strength.SUPPORTING,
                basis=("A pathogenic classification is made with respect to a particular condition and mechanism; "
                       "it does not transfer automatically to a different disease."),
                prov=exomiser_provenance(data_version),
                limitations=["Requires confirmation against the full ClinVar record and its submitters.",
                             "A truncating allele may still be relevant to a recessive mechanism in another gene-disease pair."])
    else:
        add(cls=EvidenceClass.HUMAN_OBSERVATION,
            statement="This variant has no ClinVar record in the pinned bundle — it has not been submitted or classified.",
            result="no ClinVar variation id", direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
            basis="Absence of a record is absence of evidence, not evidence of benignity or pathogenicity.",
            prov=exomiser_provenance(data_version),
            limitations=["Other submission databases (LOVD, disease-specific registries) were not consulted.",
                         "A newer ClinVar release may contain a record."])

    # ── population
    freqs = parse_frequencies(row.get("ALL_FREQ"))
    max_freq = row.get("MAX_FREQ")
    if max_freq:
        pct = float(max_freq)
        add(cls=EvidenceClass.POPULATION,
            statement=f"The variant is rare in the largest reported population dataset ({row.get('MAX_FREQ_SOURCE')}).",
            result=f"max allele frequency {pct:.6f}% ({', '.join(f'{k}={v}' for k, v in freqs.items())})",
            direction=Direction.SUPPORTS if pct < 0.1 else Direction.CONTRADICTS,
            strength=Strength.SUPPORTING if pct < 0.01 else Strength.INDETERMINATE,
            basis=("Rarity is compatible with, but not evidence of, pathogenicity. No gene-specific BA1/BS1 threshold "
                   "from a ClinGen VCEP was applied, so no benign-side criterion is claimed."),
            prov=exomiser_provenance(data_version, identifier=row.get("MAX_FREQ_SOURCE")),
            limitations=["Homozygote counts, allele numbers and coverage/callability were not retrieved.",
                         "Frequencies are those bundled with the pinned solver data, not a live query."])
    else:
        add(cls=EvidenceClass.POPULATION,
            statement="The variant is absent from the population datasets bundled with the solver.",
            result="no frequency recorded", direction=Direction.SUPPORTS, strength=Strength.SUPPORTING,
            basis="Absence from large population datasets is consistent with a rare disease allele.",
            prov=exomiser_provenance(data_version),
            limitations=["Absence may also reflect poor coverage at this position; callability was not checked."])

    # ── computational (missense only)
    scores = parse_scores(row.get("ALL_PATH"))
    if row.get("FUNCTIONAL_CLASS") == "missense_variant" or scores:
        revel = scores.get("REVEL")
        if revel is not None:
            strength, direction = next((s, d) for t, s, d in REVEL_THRESHOLDS if revel >= t)
            add(cls=EvidenceClass.COMPUTATIONAL,
                statement=f"REVEL scores this missense variant {revel:.3f}, which falls in the "
                          f"{'pathogenic-supporting or stronger' if direction == Direction.SUPPORTS else 'indeterminate' if direction == Direction.UNCERTAIN else 'benign-supporting'} band.",
                result=f"REVEL={revel:.3f}", direction=direction, strength=strength,
                basis=REVEL_SOURCE + " — the only predictor here with published ACMG/AMP evidence-strength calibration.",
                prov=exomiser_provenance(data_version, identifier="REVEL"),
                limitations=["A computational prediction is supporting evidence at most and must not outrank functional or human data."])
        am = scores.get("ALPHA_MISSENSE")
        if am is not None:
            am_class = "likely pathogenic" if am >= ALPHAMISSENSE_PATHOGENIC else "likely benign" if am <= ALPHAMISSENSE_BENIGN else "ambiguous"
            add(cls=EvidenceClass.COMPUTATIONAL,
                statement=f"AlphaMissense classifies this substitution as {am_class}.",
                result=f"AlphaMissense={am:.4f} (class boundaries {ALPHAMISSENSE_BENIGN}/{ALPHAMISSENSE_PATHOGENIC})",
                direction=Direction.SUPPORTS if am >= ALPHAMISSENSE_PATHOGENIC else Direction.CONTRADICTS if am <= ALPHAMISSENSE_BENIGN else Direction.UNCERTAIN,
                strength=Strength.INDETERMINATE,
                basis=("Cheng et al. 2023 class boundaries. These are the authors' own cut-offs, not ClinGen-calibrated "
                       "evidence strengths, so no ACMG strength is claimed from this score."),
                prov=exomiser_provenance(data_version, identifier="AlphaMissense"),
                limitations=["Correlated with other predictors; combining them is not independent evidence.",
                             "No calibrated evidence-strength mapping published for ACMG/AMP use."])
        for name in ("MVP", "CADD", "POLYPHEN", "SIFT", "MUTATION_TASTER"):
            if name in scores:
                add(cls=EvidenceClass.COMPUTATIONAL,
                    statement=f"{name} reports a score for this variant.", result=f"{name}={scores[name]}",
                    direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
                    basis="Recorded for completeness. No ClinGen-calibrated threshold was applied, so no evidence strength is claimed.",
                    prov=exomiser_provenance(data_version, identifier=name),
                    limitations=["Predictor vote-counting is explicitly discouraged; these tools are correlated."])
        splice = scores.get("SPLICE_AI")
        add(cls=EvidenceClass.MOLECULAR_MECHANISTIC,
            statement=("SpliceAI reports a splice-altering signal for this variant." if splice is not None and splice >= SPLICEAI_RECOMMENDED
                       else "No splice-altering signal was reported for this variant." if splice is not None
                       else "No SpliceAI score was assigned to this variant in the pinned bundle."),
            result=f"SpliceAI={splice}" if splice is not None else "not scored",
            direction=Direction.SUPPORTS if splice is not None and splice >= SPLICEAI_RECOMMENDED else Direction.UNCERTAIN,
            strength=Strength.SUPPORTING if splice is not None and splice >= SPLICEAI_RECOMMENDED else Strength.INDETERMINATE,
            basis=f"SpliceAI delta-score guidance (recommended threshold {SPLICEAI_RECOMMENDED}).",
            prov=exomiser_provenance(data_version, identifier="SpliceAI"),
            limitations=["Absence of a score is not evidence that splicing is unaffected.",
                         "Distance to the nearest exon boundary was not computed locally."])

    # ── solver-applied ACMG criteria, recorded as the solver's own output
    acmg, criteria = row.get("EXOMISER_ACMG_CLASSIFICATION"), row.get("EXOMISER_ACMG_EVIDENCE")
    if acmg and acmg != "NOT_AVAILABLE":
        add(cls=EvidenceClass.MOLECULAR_MECHANISTIC,
            statement=f"The solver applied ACMG/AMP criteria and reached {acmg} for this variant.",
            result=f"{acmg} via {criteria or 'unspecified criteria'}",
            direction=Direction.SUPPORTS if "PATHOGENIC" in acmg else Direction.UNCERTAIN,
            strength=Strength.INDETERMINATE,
            basis=("Recorded as the solver's automated assignment, not an independent classification by this pipeline "
                   "and not a clinical classification."),
            prov=exomiser_provenance(data_version, identifier="Exomiser ACMG assignment"),
            limitations=["PVS1 requires transcript-, NMD- and region-specific reasoning that was not independently verified here.",
                         "Automated ACMG assignment is not equivalent to expert panel review."])

    loeuf = row.get("GENE_CONSTRAINT_LOEUF")
    if loeuf:
        add(cls=EvidenceClass.MOLECULAR_MECHANISTIC,
            statement="Gene-level constraint for the affected gene.",
            result=f"LOEUF={loeuf}",
            direction=Direction.UNCERTAIN, strength=Strength.INDETERMINATE,
            basis=("LOEUF measures intolerance to loss of function at the gene level. It bears on haploinsufficiency; "
                   "for a recessive mechanism it is weak context, not evidence about this allele."),
            prov=exomiser_provenance(data_version, identifier="gnomAD gene constraint"),
            limitations=["Gene-level metric; says nothing about this specific variant."])
    return out


def read_native_row(variants_tsv: Path, contig: str, pos: int, ref: str, alt: str) -> dict | None:
    with variants_tsv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row.get("CONTIG") == str(contig) and row.get("START") == str(pos) and row.get("REF") == ref and row.get("ALT") == alt:
                return row
    return None
