"""Turning evidence into claims, one arrow at a time.

Nothing here decides what is true by counting. Each claim states what evidence exists, at
what scope, from what kind of experiment — and a claim with no evidence stays UNRESOLVED
rather than being filled in with the obvious biology.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from rarepipe.stages.mechanism.model import (
    AssayRecord,
    ClaimStatus,
    ClaimType,
    Confidence,
    Direction,
    DirectionOverride,
    EpistemicClass,
    EvidenceLevel,
    EvidenceRecord,
    Inference,
    MechanismClaim,
    Scope,
)

HUMAN_LEVELS = {EvidenceLevel.THIS_CASE, EvidenceLevel.HUMAN_EXPERIMENTAL, EvidenceLevel.EXPERT_CURATED}


@dataclass
class Bundle:
    supporting: list[EvidenceRecord]
    contradicting: list[EvidenceRecord]
    uncertain: list[EvidenceRecord]
    indirect: list[EvidenceRecord] = None  # consistent, but cannot establish the claim

    def __post_init__(self):
        if self.indirect is None:
            self.indirect = []

    def for_claim(self, claim_id: str) -> tuple[Bundle, list[DirectionOverride]]:
        """Apply reviewed per-claim relationships. Records without one keep the extractor's direction."""
        routed: dict[str, list[EvidenceRecord]] = {"supports": [], "contradicts": [], "uncertain": []}
        indirect: list[EvidenceRecord] = []
        overrides: list[DirectionOverride] = []
        indirect_ids = {id(r) for r in self.indirect}
        for record in self.supporting + self.contradicting + self.uncertain + self.indirect:
            review = record.claim_directions.get(claim_id)
            if review:
                overrides.append(DirectionOverride(
                    evidence_id=record.evidence_id, extractor_direction=record.direction.value,
                    direction_for_this_claim=review.direction, reason=review.reason, reviewed_by=review.reviewed_by))
                if review.direction == "not_applicable":
                    continue
            direction = review.direction if review else record.direction.value
            if id(record) in indirect_ids:
                indirect.append(record)
            else:
                routed[direction].append(record)
        return Bundle(supporting=routed["supports"], contradicting=routed["contradicts"],
                      uncertain=routed["uncertain"], indirect=indirect), overrides

    @property
    def sources(self) -> set[str]:
        return {e.source_id for e in self.supporting}

    @property
    def human_sources(self) -> set[str]:
        return {e.source_id for e in self.supporting if e.evidence_level in HUMAN_LEVELS}


def bundle(evidence: list[EvidenceRecord], *, assays: set[str] | None = None,
           scopes: set[Scope] | None = None, topic: re.Pattern | None = None,
           establishing_levels: set[EvidenceLevel] | None = None) -> Bundle:
    """Select the evidence a claim may rest on.

    `topic` is the guard against a claim being satisfied by its assay class alone: a sentence
    mentioning transcript levels is not evidence of nonsense-mediated decay. `establishing_levels`
    is the guard against a predictor or a domain annotation being treated as a measurement —
    anything outside it lands in `indirect` and cannot change the claim's status.
    """
    picked = [e for e in evidence
              if (assays is None or e.assay in assays) and (scopes is None or e.scope in scopes)
              and (topic is None or topic.search(f"{e.quote} {e.statement}"))]
    if establishing_levels is None:
        establishing = picked
        indirect: list[EvidenceRecord] = []
    else:
        establishing = [e for e in picked if e.evidence_level in establishing_levels]
        indirect = [e for e in picked if e.evidence_level not in establishing_levels]
    return Bundle(supporting=[e for e in establishing if e.direction is Direction.SUPPORTS],
                  contradicting=[e for e in establishing if e.direction is Direction.CONTRADICTS],
                  uncertain=[e for e in establishing if e.direction is Direction.UNCERTAIN],
                  indirect=indirect)


def status_of(b: Bundle) -> tuple[ClaimStatus, Confidence | None]:
    """Contextual, not arithmetic: who observed it and in what system decides, not how loudly."""
    if not b.supporting and not b.contradicting:
        return ClaimStatus.UNRESOLVED, None
    if b.supporting and not b.contradicting:
        if b.human_sources:
            return (ClaimStatus.SUPPORTED, Confidence.HIGH) if len(b.sources) > 1 else (ClaimStatus.SUPPORTED, Confidence.MODERATE)
        if len(b.sources) > 1:
            return ClaimStatus.SUPPORTED, Confidence.MODERATE
        return ClaimStatus.PARTIALLY_SUPPORTED, Confidence.LOW
    if b.contradicting and not b.supporting:
        return ClaimStatus.CONTRADICTED, Confidence.LOW
    return ClaimStatus.PARTIALLY_SUPPORTED, Confidence.MODERATE if b.human_sources else Confidence.LOW


def _limits(b: Bundle, extra: list[str] | None = None) -> list[str]:
    limits = list(extra or [])
    if b.indirect and not b.supporting:
        kinds = ", ".join(sorted({e.evidence_level.value for e in b.indirect}))
        limits.append(f"{len(b.indirect)} record(s) are consistent with this claim but cannot establish it ({kinds})")
    scopes = {e.scope.value for e in b.supporting}
    if scopes and not scopes & {Scope.EXACT_VARIANT.value, Scope.SAME_RESIDUE.value}:
        limits.append(f"all supporting evidence is at {', '.join(sorted(scopes))} scope, not this child's allele")
    if b.contradicting:
        limits.append(f"{len(b.contradicting)} statement(s) in the corpus point the other way")
    levels = {e.evidence_level for e in b.supporting}
    if levels and not levels & HUMAN_LEVELS:
        limits.append("no human experimental or expert-curated source among the supporting evidence")
    return limits


def build_claim(claim_id: str, claim_type: ClaimType, statement: str, b: Bundle, scope: Scope,
                *, extra_limits: list[str] | None = None, unknown_reason: str | None = None,
                epistemic: EpistemicClass = EpistemicClass.EXTERNAL_EVIDENCE,
                inference: Inference | None = None) -> MechanismClaim:
    b, overrides = b.for_claim(claim_id)
    status, confidence = status_of(b)
    return MechanismClaim(
        direction_overrides=overrides,
        id=claim_id, type=claim_type, statement=statement, status=status, scope=scope,
        epistemic_class=epistemic if status is not ClaimStatus.UNRESOLVED else EpistemicClass.UNKNOWN,
        evidence=[e.evidence_id for e in b.supporting], indirect_evidence=[e.evidence_id for e in b.indirect],
        contradicting_evidence=[e.evidence_id for e in b.contradicting],
        inference=inference, limitations=_limits(b, extra_limits), confidence=confidence,
        unknown_reason=unknown_reason if status is ClaimStatus.UNRESOLVED else None)


def assay_inventory(evidence: list[EvidenceRecord], questions: dict[str, str]) -> list[AssayRecord]:
    by_assay: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for e in evidence:
        if e.assay:
            by_assay[e.assay].append(e)
    records = []
    for assay, items in sorted(by_assay.items(), key=lambda kv: -len(kv[1])):
        models = sorted({e.experimental_level.value for e in items})
        records.append(AssayRecord(
            assay=assay, biological_question=questions.get(assay, ""), models_used=models,
            readout=items[0].quote[:160],
            source_count=len({e.source_id for e in items}), sources=sorted({e.source_id for e in items})[:12],
            case_applicability=min((e.applicability_to_case for e in items), key=lambda a: ["direct", "indirect", "background"].index(a.value))))
    return records


def mechanistic_classes(evidence: list[EvidenceRecord]) -> list[str]:
    """Where sources disagree, both mechanisms stay. Averaging them would erase the finding."""
    classes: list[str] = []
    abundance = bundle(evidence, assays={"BUBR1 protein abundance"})
    checkpoint = bundle(evidence, assays={"mitotic checkpoint activity"})
    kinase = bundle(evidence, assays={"BUBR1 kinase activity"})
    if abundance.supporting:
        classes.append("variants that reduce BUBR1 protein abundance")
    if abundance.contradicting:
        classes.append("variants reported with preserved or unchanged BUBR1 abundance")
    if checkpoint.supporting:
        classes.append("variants that impair mitotic checkpoint activity")
    if kinase.supporting or kinase.contradicting:
        classes.append("variants discussed in terms of kinase activity, where the corpus is not unanimous"
                       if kinase.contradicting else "variants that affect kinase activity")
    return classes
