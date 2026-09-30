"""Source-grounded extraction of research-network responses (PRD §9, Task T06).

Extracts structured fields from raw responses and attachments, ensuring that:
1. Every extracted field is traceable to source spans (start/end character offsets).
   A field with no span is not "extracted", it is proposed.
2. Missing, conflicting, and ambiguous fields are explicitly marked without defaults.
3. Untrusted external content is treated strictly as inert data; embedded instructions
   are never executed, permissions are never modified, and attachments are never run.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from rarepipe.stages.network.model import (
    AdditionalResponseState, Compartment, EvidenceCriteria, ImmutableModel,
    Intervention, NetworkEnvelope, OperationalResponse, Origin, Restrictions,
    ScientificFinding, unknown_quantity, new_id,
)
from rarepipe.stages.prospective.model import Knowledge, Quantity
from rarepipe.stages.prospective.nodes import ResponseState


class SourceSpan(ImmutableModel):
    """Character-level span in raw text grounding an extracted field."""

    start: int = Field(ge=0, description="0-indexed start character offset in raw text")
    end: int = Field(ge=0, description="0-indexed end character offset (exclusive) in raw text")
    text: str = Field(description="Exact substring from raw text")

    @model_validator(mode="after")
    def _validate_offsets(self):
        if self.end < self.start:
            raise ValueError("end offset cannot be smaller than start offset")
        return self

    def verify(self, raw_text: str) -> bool:
        """Verify that the span text exactly matches raw_text[start:end]."""
        return raw_text[self.start:self.end] == self.text


class ExtractedField(ImmutableModel):
    """Structured field with provenance. A field without a verified span is proposed, not extracted."""

    name: str
    value: Any = None
    span: SourceSpan | None = None
    is_extracted: bool = False
    confidence: float | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_extraction_grounding(self):
        if self.span is not None and not self.is_extracted:
            raise ValueError("field with verified span must have is_extracted=True")
        if self.span is None and self.is_extracted:
            raise ValueError("a field with no span is not 'extracted', it is proposed")
        return self


class ScientificExtraction(ImmutableModel):
    """Structured extraction result for a scientific finding response."""

    intervention: ExtractedField | None = None
    compartment: ExtractedField | None = None
    species: ExtractedField | None = None
    model: ExtractedField | None = None
    tissue_or_cell: ExtractedField | None = None
    comparator: ExtractedField | None = None
    endpoint: ExtractedField | None = None
    experimental_unit: ExtractedField | None = None
    denominator: ExtractedField | None = None
    estimate: ExtractedField | None = None
    uncertainty: ExtractedField | None = None
    quality: ExtractedField | None = None
    limitations: tuple[ExtractedField, ...] = ()
    not_measured: tuple[ExtractedField, ...] = ()
    provenance: ExtractedField | None = None
    permitted_uses: ExtractedField | None = None

    missing_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    ambiguous_fields: tuple[str, ...] = ()
    security_flags: tuple[str, ...] = ()
    raw_text: str = ""

    def to_evidence_criteria(self) -> EvidenceCriteria:
        """Convert extracted fields into typed EvidenceCriteria, preserving unknown state."""
        interv = self.intervention.value if (self.intervention and self.intervention.value) else Knowledge.UNKNOWN
        comp = self.compartment.value if (self.compartment and self.compartment.value) else Knowledge.UNKNOWN
        spec = self.species.value if (self.species and self.species.value) else None
        mdl = self.model.value if (self.model and self.model.value) else None
        tissue = self.tissue_or_cell.value if (self.tissue_or_cell and self.tissue_or_cell.value) else None
        cmpr = self.comparator.value if (self.comparator and self.comparator.value) else None
        endp = self.endpoint.value if (self.endpoint and self.endpoint.value) else None
        unit = self.experimental_unit.value if (self.experimental_unit and self.experimental_unit.value) else None
        denom = self.denominator.value if (self.denominator and self.denominator.value) else None

        return EvidenceCriteria(
            intervention=interv,
            compartment=comp,
            species=spec,
            model=mdl,
            tissue_or_cell=tissue,
            comparator=cmpr,
            endpoint=endp,
            experimental_unit=unit,
            denominator=denom,
            exposure=unknown_quantity(),
            effect_criterion=unknown_quantity(),
        )


class CapabilityExtraction(ImmutableModel):
    """Structured extraction result for a capability or referral response."""

    capability: ExtractedField | None = None
    availability_evidence: ExtractedField | None = None
    constraints: tuple[ExtractedField, ...] = ()
    responsible_route: ExtractedField | None = None
    followup_permission: ExtractedField | None = None
    missing_fields: tuple[str, ...] = ()
    security_flags: tuple[str, ...] = ()
    raw_text: str = ""


class ResponseTypeClassification(ImmutableModel):
    """Classification of inbound response type and state."""

    is_delivery_receipt: bool = False
    kind: Literal["delivery_receipt", "operational", "scientific"]
    state: ResponseState | AdditionalResponseState
    rationale: str
    security_flags: tuple[str, ...] = ()


# ── Hostile Command Patterns ───────────────────────────────────────────────────

_HOSTILE_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"ignore\s+(?:all\s+)?rules",
    r"system\s+override",
    r"grant\s+permission",
    r"export\s+(?:the\s+)?(?:case|private|patient)",
    r"change\s+(?:the\s+)?permissions",
    r"os\.(?:system|popen|exec)",
    r"eval\(",
    r"exec\(",
    r"chmod\s+\+x",
    r"rm\s+-rf",
    r"shutil\.",
]


def detect_security_threats(text: str) -> tuple[str, ...]:
    """Scan untrusted external content for prompt injection or command execution attempts.
    
    The content is never executed: detecting threats simply tags the payload for audit.
    """
    flags: list[str] = []
    for pattern in _HOSTILE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            flags.append(f"HOSTILE_INSTRUCTION_DETECTED: {pattern}")
    return tuple(flags)


# ── Response Type Classification ───────────────────────────────────────────────

_RECEIPT_HEADERS = {
    "action": {"delivered", "failed", "relayed", "delayed"},
}


def classify_response_type(raw_text: str, headers: dict[str, str] | None = None) -> ResponseTypeClassification:
    """Detect whether a response is a delivery receipt, operational outcome, or scientific result.
    
    A delivery receipt is NOT a contribution.
    """
    headers = headers or {}
    security_flags = detect_security_threats(raw_text)

    # 1. Delivery Receipt Detection
    action_hdr = headers.get("Action", "").lower()
    ct_hdr = headers.get("Content-Type", "").lower()
    subj_hdr = headers.get("Subject", "").lower()
    if (
        action_hdr in _RECEIPT_HEADERS["action"]
        or "delivery-status" in ct_hdr
        or "report-type=delivery-status" in ct_hdr
        or "delivery status notification" in subj_hdr
        or "automatic reply: delivery receipt" in subj_hdr
        or re.search(r"\b(?:delivery status notification|message was delivered|message delivered to|has been received by the mail system)\b", raw_text, re.IGNORECASE)
    ):
        return ResponseTypeClassification(
            is_delivery_receipt=True,
            kind="delivery_receipt",
            state=ResponseState.NO_RESPONSE,
            rationale="Automated transport delivery receipt / DSN; not a contribution",
            security_flags=security_flags,
        )

    # 2. Operational states
    # Refusal / Declined
    if re.search(r"\b(?:decline(?:d)?|refuse(?:d)?|unable to participate|cannot participate|not accepting (?:new )?requests|cannot take on|opt[- ]out|(?:are |am )?(?:not able|unable) to (?:share|help|assist|provide|supply)|must decline)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="operational",
            state=AdditionalResponseState.DECLINED,
            rationale="Node declined to participate or contribute",
            security_flags=security_flags,
        )
    # Access Denied
    if re.search(r"\b(?:access denied|permission denied|confidentiality policy forbids access|data access request rejected)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="operational",
            state=ResponseState.ACCESS_DENIED,
            rationale="Access denied under institutional confidentiality/data policy",
            security_flags=security_flags,
        )
    # Cannot Disclose
    if re.search(r"\b(?:cannot disclose|proprietary data|under nda|confidential ip|confidentiality agreement prevents)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="operational",
            state=AdditionalResponseState.CANNOT_DISCLOSE,
            rationale="Node cannot disclose requested information due to legal or IP constraints",
            security_flags=security_flags,
        )
    # No Relevant Resource
    if re.search(r"\b(?:do not (?:have|maintain|hold)|no longer (?:have|hold|maintain|keep)|no relevant resources?|no samples? available|cell line unavailable|no stocks?|samples? (?:exhausted|depleted))\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="operational",
            state=AdditionalResponseState.NO_RELEVANT_RESOURCE,
            rationale="Node holds no relevant biospecimens, cell lines or physical resources",
            security_flags=security_flags,
        )
    # No Relevant Data
    if re.search(r"\b(?:no relevant data|no data in our (?:records|repository|database)|not searched|no records found)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="operational",
            state=ResponseState.NO_RELEVANT_DATA,
            rationale="Node has no relevant data in records or repository",
            security_flags=security_flags,
        )

    # 3. Scientific outcomes
    # QC failure
    if re.search(r"\b(?:qc failure|quality control failed|assay failed|samples? degraded|batch contaminated|control failure|invalid measurement|unreliable assay|failed validation)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="scientific",
            state=AdditionalResponseState.INVALID_MEASUREMENT,
            rationale="Assay or measurement failed quality control checks",
            security_flags=security_flags,
        )
    # Inconclusive Result
    if re.search(r"\b(?:inconclusive|uninterpretable|high variance|ambiguous results?|cannot conclude|unresolved findings?)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="scientific",
            state=ResponseState.INCONCLUSIVE_RESULT,
            rationale="Measured result is inconclusive or uninterpretable",
            security_flags=security_flags,
        )
    # Informative Negative
    if re.search(r"\b(?:informative negative|confirmed absence of effect|well[- ]powered negative|no detectable increase with positive control validated|validated negative result)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="scientific",
            state=AdditionalResponseState.INFORMATIVE_NEGATIVE,
            rationale="Validated negative finding with verified controls and power",
            security_flags=security_flags,
        )
    # Measured No Effect
    if re.search(r"\b(?:no (?:significant )?effect|no (?:detectable |significant )?change|did not change|showed no (?:change|increase|decrease|difference)|no significant difference|p\s*>\s*0\.05|unchanged|levels remained constant)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="scientific",
            state=ResponseState.MEASURED_NO_EFFECT,
            rationale="Measurement showed no statistically or biologically significant change",
            security_flags=security_flags,
        )
    # Measured Effect
    if re.search(r"\b(?:measured effect|increased by|decreased by|fold[- ]change|statistically significant|p\s*<\s*0\.05|significant (?:elevation|reduction)|levels were|rescued|elevated|reduced)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="scientific",
            state=ResponseState.MEASURED_EFFECT,
            rationale="Measurement demonstrated an observed effect",
            security_flags=security_flags,
        )

    # Capability / Referral reply
    if re.search(r"\b(?:we have (?:the )?capability|(?:our lab |we )can (?:measure|run|perform|analyse|analyze|carry out)|assay is available|refer you to|in collaboration with|collaboration)\b", raw_text, re.IGNORECASE):
        return ResponseTypeClassification(
            kind="operational",
            state=AdditionalResponseState.CAPABILITY_REPORTED,
            rationale="Node reported analysis capability or referral",
            security_flags=security_flags,
        )

    # Empty or uninformative text defaults to no response
    if not raw_text.strip():
        return ResponseTypeClassification(
            kind="operational",
            state=ResponseState.NO_RESPONSE,
            rationale="Empty reply body; no response content",
            security_flags=security_flags,
        )

    # Default fallback. Text this classifier did not recognise says nothing about the node, so
    # the fallback must assert nothing. It previously returned CAPABILITY_REPORTED, which turned
    # every unparsed reply — including refusals and measured null results phrased in wording the
    # patterns above do not cover — into a claim that the institution reported a capability.
    return ResponseTypeClassification(
        kind="operational",
        state=AdditionalResponseState.UNCLASSIFIED,
        rationale="Reply did not match any known operational or scientific pattern; "
                  "no capability, resource or result is claimed. A human must read it.",
        security_flags=security_flags,
    )


# ── Scientific Extraction ──────────────────────────────────────────────────────

def _extract_field(name: str, pattern: str, raw_text: str, value_mapper=None) -> ExtractedField | None:
    match = re.search(pattern, raw_text, re.IGNORECASE)
    if not match:
        return None
    start, end = match.start(), match.end()
    snippet = raw_text[start:end]
    span = SourceSpan(start=start, end=end, text=snippet)
    val = value_mapper(match) if value_mapper else snippet
    return ExtractedField(name=name, value=val, span=span, is_extracted=True)


def extract_scientific_fields(raw_text: str) -> ScientificExtraction:
    """Extract structured scientific fields from raw response text.
    
    Every extracted field must carry its source span in raw_text.
    Fields not present in the source are marked in missing_fields and NOT populated with defaults.
    """
    security_flags = detect_security_threats(raw_text)
    missing: list[str] = []
    conflicting: list[str] = []
    ambiguous: list[str] = []

    # 1. Exact Intervention
    interv_field: ExtractedField | None = None
    interv_matches: list[tuple[Intervention, re.Match]] = []

    for pattern, enum_val in [
        (r"\b(?:NMN|nicotinamide\s+mononucleotide)\b", Intervention.NMN),
        (r"\b(?:NR|nicotinamide\s+riboside)\b", Intervention.NR),
        (r"\b(?:nicotinic\s+acid|niacin|vitamin\s+b3)\b", Intervention.NICOTINIC_ACID),
        (r"\b(?:NAM|nicotinamide(?!\s+mononucleotide|\s+riboside))\b", Intervention.NAM),
    ]:
        for m in re.finditer(pattern, raw_text, re.IGNORECASE):
            interv_matches.append((enum_val, m))

    if interv_matches:
        distinct_interventions = {val for val, _ in interv_matches}
        if len(distinct_interventions) > 1:
            conflicting.append("intervention")
        # Use first match for primary extracted field
        first_val, first_match = interv_matches[0]
        start, end = first_match.start(), first_match.end()
        span = SourceSpan(start=start, end=end, text=raw_text[start:end])
        interv_field = ExtractedField(name="intervention", value=first_val, span=span, is_extracted=True)
    else:
        missing.append("intervention")

    # 2. Compartment
    comp_field: ExtractedField | None = None
    comp_matches: list[tuple[Compartment, re.Match]] = []
    for pattern, enum_val in [
        (r"\b(?:blood|plasma|serum|whole\s+blood|circulating)\b", Compartment.BLOOD),
        (r"\b(?:intracellular(?:ly)?|cellular|cell\s+lysate|inside\s+cells?|cytosol(?:ic)?|mitochondrial?)\b", Compartment.INTRACELLULAR),
        (r"\b(?:extracellular(?:ly)?|supernatant|conditioned\s+media)\b", Compartment.EXTRACELLULAR),
    ]:
        for m in re.finditer(pattern, raw_text, re.IGNORECASE):
            comp_matches.append((enum_val, m))

    if comp_matches:
        distinct_comp = {val for val, _ in comp_matches}
        if len(distinct_comp) > 1:
            conflicting.append("compartment")
        first_val, first_match = comp_matches[0]
        start, end = first_match.start(), first_match.end()
        span = SourceSpan(start=start, end=end, text=raw_text[start:end])
        comp_field = ExtractedField(name="compartment", value=first_val, span=span, is_extracted=True)
    else:
        missing.append("compartment")

    # 3. Measured Endpoint
    endpoint_field = _extract_field(
        "endpoint",
        r"\b(?:NAD\+|NAD|NADH|ATP|cell\s+viability|viability|cell\s+death|proliferation|division\s+rate)\b",
        raw_text,
    )
    if not endpoint_field:
        missing.append("endpoint")

    # 4. Comparator
    comparator_field = _extract_field(
        "comparator",
        r"\b(?:vehicle(?:[- ]treated)?|untreated|wild[- ]type|WT|control|placebo|baseline)\b",
        raw_text,
    )
    if not comparator_field:
        missing.append("comparator")

    # 5. Species
    species_field = _extract_field(
        "species",
        r"\b(?:human|mouse|mus\s+musculus|homo\s+sapiens|rat)\b",
        raw_text,
    )
    if not species_field:
        missing.append("species")

    # 6. Model
    model_field = _extract_field(
        "model",
        r"\b(?:primary\s+fibroblasts?|fibroblasts?|lymphoblasts?|patient\s+cells?|HEK293|organoids?|iPSCs?)\b",
        raw_text,
    )
    if not model_field:
        missing.append("model")

    # 7. Tissue or Cell
    tissue_field = _extract_field(
        "tissue_or_cell",
        r"\b(?:fibroblasts?|PBMC|lymphocytes?|hepatocytes?|skin|muscle|brain|blood\s+cells?)\b",
        raw_text,
    )
    if not tissue_field:
        missing.append("tissue_or_cell")

    # 8. Experimental Unit and Denominator
    unit_field = _extract_field(
        "experimental_unit",
        r"\b(?:wells?|biological\s+replicates?|triplicates?|technical\s+replicates?|patients?)\b",
        raw_text,
    )
    if not unit_field:
        missing.append("experimental_unit")

    denom_field = _extract_field(
        "denominator",
        r"\bn\s*=\s*(\d+)\b",
        raw_text,
        value_mapper=lambda m: m.group(1),
    )
    if not denom_field:
        missing.append("denominator")

    # 9. Estimate and Uncertainty
    estimate_field: ExtractedField | None = None
    m_est = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:fold[- ]change|%|uM|µM|mM|nmol/L)", raw_text, re.IGNORECASE)
    if m_est:
        start, end = m_est.start(), m_est.end()
        estimate_field = ExtractedField(
            name="estimate",
            value=m_est.group(0),
            span=SourceSpan(start=start, end=end, text=raw_text[start:end]),
            is_extracted=True,
        )
    else:
        missing.append("estimate")

    uncertainty_field: ExtractedField | None = None
    m_unc = re.search(r"(?:±\s*([0-9.]+)|p\s*[<=]\s*([0-9.]+)|SD\s*=\s*([0-9.]+)|95%\s*CI\s*\[[^\]]+\])", raw_text, re.IGNORECASE)
    if m_unc:
        start, end = m_unc.start(), m_unc.end()
        uncertainty_field = ExtractedField(
            name="uncertainty",
            value=m_unc.group(0),
            span=SourceSpan(start=start, end=end, text=raw_text[start:end]),
            is_extracted=True,
        )
    else:
        missing.append("uncertainty")

    # 10. Quality Checks
    quality_field = _extract_field(
        "quality",
        r"\b(?:QC\s+passed|standard\s+controls\s+valid|quality\s+control\s+passed|CV\s*<\s*\d+%)\b",
        raw_text,
        value_mapper=lambda m: "VALID",
    )

    # 11. Limitations
    limitations: list[ExtractedField] = []
    for m in re.finditer(r"(?:Limitations?|Caveat|Note):\s*([^\n.]+)", raw_text, re.IGNORECASE):
        start, end = m.start(), m.end()
        limitations.append(ExtractedField(
            name="limitation",
            value=m.group(1).strip(),
            span=SourceSpan(start=start, end=end, text=raw_text[start:end]),
            is_extracted=True,
        ))

    # 12. Not measured links
    not_measured: list[ExtractedField] = []
    for m in re.finditer(r"([^\n.]+?(?:was\s+not\s+measured|not\s+assessed|unmeasured|not\s+tested))", raw_text, re.IGNORECASE):
        start, end = m.start(), m.end()
        not_measured.append(ExtractedField(
            name="not_measured",
            value=m.group(1).strip(),
            span=SourceSpan(start=start, end=end, text=raw_text[start:end]),
            is_extracted=True,
        ))

    # 13. Provenance (DOI, PMID, study reference)
    provenance_field = _extract_field(
        "provenance",
        r"(?:10\.\d{4,9}/[-._;()/:A-Za-z0-9]+|PMID:?\s*\d+|\bstudy[-_ ](?:id|ref)?[: ]\s*[\w\-.]+)",
        raw_text,
    )
    if not provenance_field:
        missing.append("provenance")

    # 14. Permitted Uses / Restrictions in text
    permitted_field = _extract_field(
        "permitted_uses",
        r"(?:case[- ]specific\s+use\s+only|for\s+[\w\-]+\s+only|no\s+public\s+export|academic\s+(?:research\s+)?use\s+only)",
        raw_text,
    )

    return ScientificExtraction(
        intervention=interv_field,
        compartment=comp_field,
        species=species_field,
        model=model_field,
        tissue_or_cell=tissue_field,
        comparator=comparator_field,
        endpoint=endpoint_field,
        experimental_unit=unit_field,
        denominator=denom_field,
        estimate=estimate_field,
        uncertainty=uncertainty_field,
        quality=quality_field,
        limitations=tuple(limitations),
        not_measured=tuple(not_measured),
        provenance=provenance_field,
        permitted_uses=permitted_field,
        missing_fields=tuple(missing),
        conflicting_fields=tuple(conflicting),
        ambiguous_fields=tuple(ambiguous),
        security_flags=security_flags,
        raw_text=raw_text,
    )


# ── Capability Extraction ──────────────────────────────────────────────────────

def extract_capability_fields(raw_text: str) -> CapabilityExtraction:
    """Extract capability, availability evidence, constraints, and follow-up route from reply.
    
    Does not demand nonexistent experimental values (PRD §9).
    """
    security_flags = detect_security_threats(raw_text)
    missing: list[str] = []

    # Capability
    cap_field = _extract_field(
        "capability",
        r"(?:capability|can\s+(?:measure|perform|run)|service|assay):\s*([^\n.]+)",
        raw_text,
    )
    if not cap_field:
        # Broader sentence match
        cap_field = _extract_field(
            "capability",
            r"(?:we\s+(?:can|have\s+the\s+capacity\s+to|offer)\s+[^\n.]+)",
            raw_text,
        )
    if not cap_field:
        missing.append("capability")

    # Availability Evidence
    avail_field = _extract_field(
        "availability_evidence",
        r"(?:currently\s+operational|slots?\s+available|capacity\s+is\s*[^\n.]+|turnaround\s+time\s*[^\n.]+)",
        raw_text,
    )
    if not avail_field:
        missing.append("availability_evidence")

    # Constraints
    constraints: list[ExtractedField] = []
    for m in re.finditer(r"(?:MTA\s+required|academic\s+collaboration\s+only|subject\s+to\s+[^\n.]+|fee\s+for\s+service)", raw_text, re.IGNORECASE):
        start, end = m.start(), m.end()
        constraints.append(ExtractedField(
            name="constraint",
            value=m.group(0),
            span=SourceSpan(start=start, end=end, text=raw_text[start:end]),
            is_extracted=True,
        ))

    # Responsible Route
    route_field = _extract_field(
        "responsible_route",
        r"[\w.-]+@[\w.-]+\.\w+",
        raw_text,
    )
    if not route_field:
        missing.append("responsible_route")

    # Permission to follow up
    followup_field = _extract_field(
        "followup_permission",
        r"(?:permission\s+to\s+follow\s+up|happy\s+to\s+discuss|welcome\s+to\s+contact|please\s+reach\s+out)",
        raw_text,
        value_mapper=lambda m: True,
    )

    return CapabilityExtraction(
        capability=cap_field,
        availability_evidence=avail_field,
        constraints=tuple(constraints),
        responsible_route=route_field,
        followup_permission=followup_field,
        missing_fields=tuple(missing),
        security_flags=security_flags,
        raw_text=raw_text,
    )
