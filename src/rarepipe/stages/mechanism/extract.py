"""Evidence extraction, and the provenance validation every extracted claim must survive.

Extraction here is deterministic: sentences are matched against patterns for model system,
assay, direction and scope, and the matched sentence itself becomes the quote. That makes
every record trivially checkable — the quote is re-found in the stored document before the
record is accepted, and a record whose quote cannot be re-found is an invalid inference.

An LLM extractor produces the same `EvidenceRecord` shape and passes through the same
validation. It is not trusted more for being fluent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rarepipe.stages.mechanism.model import (
    Applicability,
    Direction,
    EpistemicClass,
    EvidenceLevel,
    EvidenceRecord,
    ExperimentalLevel,
    InvalidInference,
    RetrievedDocument,
    Scope,
)

SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

MODEL_PATTERNS: list[tuple[ExperimentalLevel, re.Pattern]] = [
    (ExperimentalLevel.PATIENT_DERIVED_CELLS, re.compile(
        r"\b(patient[- ]derived|patient cells?|patient fibroblasts?|proband|lymphoblastoid|"
        r"fibroblasts? from|MVA (patients?|cells?)|individuals? with)\b", re.I)),
    (ExperimentalLevel.ANIMAL_MODEL, re.compile(r"\b(mice|mouse|murine|zebrafish|drosophila|c\. ?elegans|in vivo model)\b", re.I)),
    (ExperimentalLevel.ENGINEERED_HUMAN_CELL_LINE, re.compile(
        r"\b(HeLa|U2OS|RPE-?1|HEK ?293|DLD-?1|HCT116|transfect\w*|stably express\w*|knock-?in|knock-?down|siRNA|shRNA)\b", re.I)),
    (ExperimentalLevel.BIOCHEMICAL_ASSAY, re.compile(r"\b(recombinant|in vitro kinase assay|purified protein|immunoprecipitat\w+)\b", re.I)),
    (ExperimentalLevel.IN_SILICO, re.compile(r"\b(in silico|predicted by|structural model|molecular dynamics)\b", re.I)),
]

ASSAY_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("BUBR1 protein abundance", "How much BUBR1 protein is present?",
     re.compile(r"\b(protein (levels?|abundance|amount)|western blot|immunoblot|reduced BUBR1|BUBR1 (levels?|expression)|"
                r"undetectable|steady[- ]state levels?)\b", re.I)),
    ("mitotic checkpoint activity", "Does the spindle assembly checkpoint arrest cells?",
     re.compile(r"\b(mitotic checkpoint|spindle (assembly )?checkpoint|SAC (activity|function|response)|nocodazole|"
                r"mitotic (arrest|index)|checkpoint (activity|function|response|signalling|signaling))\b", re.I)),
    ("premature chromatid separation", "Do sister chromatids separate early?",
     re.compile(r"\b(premature (chromatid|sister chromatid) separation|PCS|premature sister[- ]chromatid)\b", re.I)),
    ("chromosome alignment / congression", "Do chromosomes align at the metaphase plate?",
     re.compile(r"\b(chromosome (alignment|congression)|metaphase plate|misaligned chromosomes?)\b", re.I)),
    ("chromosome missegregation", "Are chromosomes segregated correctly?",
     re.compile(r"\b(missegregat\w+|mis-?segregation|lagging chromosomes?|segregation errors?)\b", re.I)),
    ("aneuploidy / karyotype", "Do cells end up with abnormal chromosome counts?",
     re.compile(r"\b(aneuploid\w*|karyotyp\w+|trisom\w+|monosom\w+|variegated aneuploidy)\b", re.I)),
    ("BUBR1 kinase activity", "Is the kinase domain catalytically active?",
     re.compile(r"\b(kinase (activity|dead|domain function)|autophosphorylat\w+|catalytic activity)\b", re.I)),
    ("kinetochore localisation", "Does BUBR1 reach the kinetochore?",
     re.compile(r"\b(kinetochore (localisation|localization|recruitment|binding)|localis\w+ to kinetochores?)\b", re.I)),
    ("rescue / complementation", "Does restoring BUBR1 restore the phenotype?",
     re.compile(r"\b(rescue[ds]?|complementation|complemented|restor\w+|re-?expression of (BUBR1|BUB1B))\b", re.I)),
    ("transcript / NMD", "Is the mutant transcript degraded?",
     re.compile(r"\b(nonsense[- ]mediated (mRNA )?decay|NMD|transcript levels?|mRNA levels?|RT-?PCR)\b", re.I)),
]

SCOPE_PATTERNS: list[tuple[Scope, re.Pattern]] = [
    (Scope.VARIANT_CLASS, re.compile(r"\b(missense|nonsense|frameshift|truncating|splice|kinase[- ]domain (variants?|mutations?)|"
                                     r"biallelic|compound heterozygous|monoallelic)\b", re.I)),
    (Scope.DISEASE_LEVEL, re.compile(r"\b(mosaic variegated aneuploidy|MVA|constitutional aneuploidy|"
                                     r"cancer predisposition syndrome)\b", re.I)),
    (Scope.GENE_LEVEL, re.compile(r"\b(BUB1B|BUBR1)\b", re.I)),
]

CONTRADICTION_CUES = re.compile(
    r"\b(no (significant|detectable|apparent) (difference|change|effect|reduction)|unchanged|not (reduced|affected|altered|required)|"
    r"normal (levels?|abundance|expression|function)|comparable to (control|wild[- ]type)|dispensable|independent of|"
    r"preserved|retained (normal|full)|failed to (show|detect)|contrary to)\b", re.I)
UNCERTAIN_CUES = re.compile(r"\b(may|might|suggest\w*|could|appears? to|remains? unclear|unknown|not (yet )?determined)\b", re.I)

REVIEW_HINT = re.compile(r"\b(review|overview|we discuss|this review)\b", re.I)


@dataclass
class ExtractionResult:
    records: list[EvidenceRecord]
    invalid: list[InvalidInference]


def _experimental_level(sentence: str, document_text: str) -> ExperimentalLevel:
    for level, pattern in MODEL_PATTERNS:
        if pattern.search(sentence):
            return level
    for level, pattern in MODEL_PATTERNS:  # fall back to the document's own setting
        if pattern.search(document_text[:4000]):
            return level
    return ExperimentalLevel.NOT_APPLICABLE


def _evidence_level(doc: RetrievedDocument, experimental: ExperimentalLevel, sentence: str) -> EvidenceLevel:
    if doc.is_review or REVIEW_HINT.search(sentence):
        return EvidenceLevel.REVIEW
    if experimental is ExperimentalLevel.PATIENT_DERIVED_CELLS:
        return EvidenceLevel.HUMAN_EXPERIMENTAL
    if experimental is ExperimentalLevel.ANIMAL_MODEL:
        return EvidenceLevel.MODEL_SYSTEM
    if experimental is ExperimentalLevel.IN_SILICO:
        return EvidenceLevel.COMPUTATIONAL
    return EvidenceLevel.PRIMARY_LITERATURE


def _scope(sentence: str) -> Scope:
    for scope, pattern in SCOPE_PATTERNS:
        if pattern.search(sentence):
            return scope
    return Scope.GENE_LEVEL


def _direction(sentence: str) -> Direction:
    if CONTRADICTION_CUES.search(sentence):
        return Direction.CONTRADICTS
    if UNCERTAIN_CUES.search(sentence):
        return Direction.UNCERTAIN
    return Direction.SUPPORTS


def _applicability(scope: Scope, level: EvidenceLevel) -> Applicability:
    if scope in (Scope.EXACT_VARIANT, Scope.SAME_RESIDUE):
        return Applicability.DIRECT
    if level in (EvidenceLevel.HUMAN_EXPERIMENTAL, EvidenceLevel.EXPERT_CURATED):
        return Applicability.INDIRECT
    return Applicability.BACKGROUND


def extract_document(doc: RetrievedDocument, text: str, start_index: int) -> ExtractionResult:
    """One evidence record per (sentence, assay) match, each anchored to the sentence itself."""
    records: list[EvidenceRecord] = []
    invalid: list[InvalidInference] = []
    n = start_index
    seen: set[tuple[str, str]] = set()
    offset = 0
    for sentence in SENTENCE.split(text):
        raw = sentence.strip()
        position = text.find(raw, offset)
        offset = position + len(raw) if position >= 0 else offset
        if len(raw) < 40 or len(raw) > 1200:
            continue
        if not re.search(r"\b(BUB1B|BUBR1|MVA|mosaic variegated aneuploidy|checkpoint|aneuploid)\b", raw, re.I):
            continue
        experimental = _experimental_level(raw, text)
        scope = _scope(raw)
        for assay, question, pattern in ASSAY_PATTERNS:
            if not pattern.search(raw):
                continue
            key = (assay, raw[:120])
            if key in seen:
                continue
            seen.add(key)
            level = _evidence_level(doc, experimental, raw)
            quote = raw if len(raw) <= 400 else raw[:397] + "..."
            record = EvidenceRecord(
                evidence_id=f"EV_{n:04d}", source_id=doc.source_id,
                statement=f"{assay}: {doc.title[:110]}" if doc.title else assay,
                quote=quote, quote_offsets=(position, position + len(raw)) if position >= 0 else None,
                epistemic_class=EpistemicClass.EXTERNAL_EVIDENCE, evidence_level=level,
                experimental_level=experimental, scope=scope,
                applicability_to_case=_applicability(scope, level), direction=_direction(raw),
                assay=assay, model_system=experimental.value, result=quote,
                rescue_experiment=bool(re.search(r"\b(rescue|complementation|restor\w+|re-?expression)\b", raw, re.I)),
                limitations=[] if scope in (Scope.EXACT_VARIANT, Scope.SAME_RESIDUE) else
                            [f"scope is {scope.value}: this is not evidence about the child's specific allele"],
                extracted_by="rarepipe.deterministic_extractor_v1", pub_year=doc.pub_year)
            records.append(record)
            n += 1
    return ExtractionResult(records=records, invalid=invalid)


def verify(records: list[EvidenceRecord], documents: dict[str, RetrievedDocument], corpus_root: Path
           ) -> tuple[list[EvidenceRecord], list[InvalidInference]]:
    """The hallucination guard: the source must be in the corpus and the quote must be in the source."""
    good: list[EvidenceRecord] = []
    invalid: list[InvalidInference] = []
    cache: dict[str, str] = {}
    for record in records:
        doc = documents.get(record.source_id)
        if doc is None:
            invalid.append(InvalidInference(produced_by=record.extracted_by, statement=record.statement,
                                            reason="source_not_in_corpus", detail=record.source_id))
            continue
        if record.source_id not in cache:
            path = corpus_root / "docs" / f"{record.source_id.replace(':', '_')}.txt"
            cache[record.source_id] = path.read_text() if path.exists() else ""
        body = cache[record.source_id]
        needle = record.quote[:-3] if record.quote.endswith("...") else record.quote
        if needle and needle in body:
            record.verified_from_source = True
            good.append(record)
        else:
            invalid.append(InvalidInference(produced_by=record.extracted_by, statement=record.statement,
                                            reason="quote_not_found_in_source", detail=record.source_id))
    return good, invalid


def local_variant_search(text: str, needles: list[str]) -> list[tuple[str, int]]:
    """Exact-variant matching happens here, locally, against text we already downloaded.

    The residue never becomes a query. This is the whole reason the corpus is fetched first.
    """
    hits: list[tuple[str, int]] = []
    for needle in needles:
        for match in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", text):
            hits.append((needle, match.start()))
    return hits
