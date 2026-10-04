"""The deterministic validators. Agents discover possibilities; this module decides what exists.

Each validator answers one question and each can fail on its own, because the failures mean
different things and collapsing them into a single verdict destroys the information. In particular:

* **input match** is here because of a real bug this project already hit. A capability `A -> B` may
  not cite evidence for `C -> B` as if it demonstrated `A`. "The paper is about the same output" is
  not the same claim.
* **output match** refuses a readout standing in for a function. A marker associated with a
  checkpoint is not checkpoint activation, and no amount of plausibility makes it one.
* **forbidden-dependency ancestry** is what makes a bypass a bypass. A candidate that looks
  independent while its mechanism runs upstream through the forbidden node has found nothing, and
  the check walks the whole ancestry graph rather than the candidate's own description of itself.
* **context** is split into compartment, agent and system, each compared separately. Whole-blood is
  not intracellular; one compound does not inherit another's measured effect; and a result in one
  system transferring to another is a claim of its own, not a silent assumption.

Three verification levels are tracked and never merged: a source existing and saying something, a
claim being grounded in it, and a capability being entitled for the required context.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.discovery.candidates import CapabilityCandidate
from rarepipe.stages.control.discovery.capabilities import (
    GroundedCapability, NotEntitled,
)
from rarepipe.stages.control.discovery.gaps import CapabilityGap
from rarepipe.stages.control.discovery.kinds import (
    CapabilityEntitlement, RejectionReason, VerificationLevel,
)
from rarepipe.stages.control.discovery.providers import SourceHit
from rarepipe.stages.control.discovery.vocabulary import Vocabulary
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.evidence import EvidenceInventory
from rarepipe.stages.simulate.chain import Support

_CONTEXT_DIMENSIONS = ("compartment", "agent", "system")
_DIMENSION_REASON = {
    "compartment": RejectionReason.COMPARTMENT_MISMATCH,
    "agent": RejectionReason.AGENT_MISMATCH,
    "system": RejectionReason.CONTEXT_MISMATCH,
}


class MatchResult(Immutable):
    validator: str
    passed: bool
    detail: str


class CandidateAssessment(Immutable):
    candidate_id: str
    gap_id: str
    entitlement: CapabilityEntitlement
    verification: tuple[VerificationLevel, ...] = ()
    checks: tuple[MatchResult, ...] = ()
    rejections: tuple[RejectionReason, ...] = ()
    ancestry: tuple[str, ...] = ()
    forbidden_hits: tuple[str, ...] = ()
    unsupported_intermediates: tuple[str, ...] = ()
    causal_depth: int = 0
    source_ids: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    support_level: Support = Support.ASSERTED_ONLY
    reason: str = Field("", description="Why this entitlement, in words a reviewer can check.")

    @property
    def can_ground(self) -> bool:
        """`UNVERIFIED_SOURCE` is included deliberately: the rule is "at most CONDITIONAL", not
        "nothing". The builder downgrades it, so the capability carries the weaker claim."""
        return self.entitlement in {CapabilityEntitlement.GROUNDED,
                                    CapabilityEntitlement.CONDITIONAL,
                                    CapabilityEntitlement.UNVERIFIED_SOURCE}

    @property
    def only_blocker_is_dependency(self) -> bool:
        return bool(self.forbidden_hits) and set(self.rejections) <= {
            RejectionReason.FORBIDDEN_DEPENDENCY}


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def ancestry(inventory: EvidenceInventory, candidate: CapabilityCandidate) -> set[str]:
    """Every node upstream of the claimed output, including through the candidate's own assertion."""
    parents: dict[str, list[str]] = {}
    for item in inventory.edges:
        parents.setdefault(item.target, []).append(item.source)
    for source in candidate.required_inputs:
        parents.setdefault(candidate.claimed_output, []).append(source)
    seen: set[str] = set()
    frontier = [candidate.claimed_output]
    while frontier:
        for parent in parents.get(frontier.pop(), []):
            if parent not in seen:
                seen.add(parent)
                frontier.append(parent)
    return seen


def _path(candidate: CapabilityCandidate, hits: tuple[SourceHit, ...]) -> tuple[int, tuple[str, ...]]:
    """Depth of the cited chain, and nodes it needs that no cited claim produces."""
    produced = {hit.claim_output for hit in hits}
    needed = {hit.claim_input for hit in hits}
    origins = set(candidate.required_inputs)
    gaps = tuple(sorted(node for node in needed
                        if node not in produced and node not in origins))
    if candidate.claimed_output not in produced:
        gaps = tuple(sorted({*gaps, f"{candidate.claimed_output} (claimed output, produced by no "
                                    "cited claim)"}))
    return max(len(hits), 1), gaps


def assess(candidate: CapabilityCandidate, gap: CapabilityGap, hits: dict[str, SourceHit],
           inventory: EvidenceInventory, vocab: Vocabulary) -> CandidateAssessment:
    checks: list[MatchResult] = []
    rejections: list[RejectionReason] = []

    def check(name: str, passed: bool, detail: str, reason: RejectionReason | None = None) -> bool:
        checks.append(MatchResult(validator=name, passed=passed, detail=detail))
        if not passed and reason is not None:
            rejections.append(reason)
        return passed

    def done(entitlement: CapabilityEntitlement, reason: str, *, levels=(), depth=0,
             cited=(), refs=(), support=Support.ASSERTED_ONLY, anc=(), forbidden=(),
             intermediates=()) -> CandidateAssessment:
        return CandidateAssessment(
            candidate_id=candidate.candidate_id, gap_id=gap.gap_id, entitlement=entitlement,
            verification=tuple(levels), checks=tuple(checks), rejections=tuple(rejections),
            ancestry=tuple(sorted(anc)), forbidden_hits=tuple(sorted(forbidden)),
            unsupported_intermediates=tuple(intermediates), causal_depth=depth,
            source_ids=tuple(cited), references=tuple(sorted(set(refs) - {""})),
            support_level=support, reason=reason)

    # 1. The claimed output must be something the compiler can connect to a state variable.
    resolved = vocab.resolve(candidate.claimed_output)
    if not check("vocabulary", resolved is not None,
                 f"{candidate.claimed_output!r} resolves to "
                 f"{resolved or 'nothing in the controlled vocabulary'}",
                 RejectionReason.NOT_IN_VOCABULARY):
        return done(CapabilityEntitlement.NOT_REPRESENTABLE,
                    f"{candidate.claimed_output!r} is outside the controlled vocabulary, so no "
                    "verdict it could change exists")

    # 2. Provenance: every cited id must resolve to something a provider actually returned.
    cited = tuple(candidate.supporting_evidence_refs)
    unresolved = tuple(sorted(ref for ref in cited if ref not in hits))
    if not check("provenance", bool(cited), "cites at least one source id",
                 RejectionReason.NO_PROVENANCE):
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    "the candidate cites no source, so nothing grounds it")
    if not check("sources_resolve", not unresolved,
                 f"unresolved source ids: {list(unresolved)}" if unresolved
                 else "every cited id came from a provider",
                 RejectionReason.FABRICATED):
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"cited source ids {list(unresolved)} were not returned by any provider; a "
                    "citation nobody retrieved is not evidence")
    cited_hits = tuple(hits[ref] for ref in cited)
    refs = tuple(hit.reference for hit in cited_hits)
    terminal = next((hit for hit in cited_hits if hit.claim_output == candidate.claimed_output),
                    cited_hits[-1])
    support = min((hit.support for hit in cited_hits),
                  key=lambda s: _SUPPORT_RANK.get(s, 99))

    # 3. A contradicting result is not weak support; it is the opposite of support.
    contradicting = tuple(sorted(hit.source_id for hit in cited_hits
                                 if hit.support is Support.CONTRADICTED))
    if not check("contradiction", not contradicting,
                 f"contradicting claims: {list(contradicting)}" if contradicting
                 else "no cited claim is a null or opposite result",
                 RejectionReason.CONTRADICTED):
        return done(CapabilityEntitlement.CONTRADICTED,
                    f"{list(contradicting)} record a null or opposite result for this "
                    "transformation", cited=cited, refs=refs, support=support)

    # 4. The claim must be about the entity the candidate names.
    subject = vocab.resolve(candidate.proposed_entity_or_process) or \
        candidate.proposed_entity_or_process
    entity_ok = any(_same(subject, hit.claim_subject) for hit in cited_hits)
    check("entity_match", entity_ok,
          f"{subject!r} versus cited subjects {[h.claim_subject for h in cited_hits]}",
          RejectionReason.ENTITY_MISMATCH)

    # 5. Input, output and direction, each against the claim rather than the description.
    claimed_inputs = {vocab.resolve(i) or i for i in candidate.required_inputs}
    input_ok = bool(claimed_inputs) and claimed_inputs <= {hit.claim_input for hit in cited_hits}
    check("input_match", input_ok,
          f"candidate acts on {sorted(claimed_inputs)}; cited claims are about "
          f"{sorted({h.claim_input for h in cited_hits})}",
          RejectionReason.INPUT_MISMATCH)
    output_ok = _same(terminal.claim_output, resolved)
    check("output_match", output_ok,
          f"cited claim measures {terminal.claim_output!r}; the candidate claims {resolved!r}",
          RejectionReason.OUTPUT_MISMATCH)
    direction_ok = terminal.claim_direction is candidate.claimed_direction
    check("direction_match", direction_ok,
          f"cited claim is {terminal.claim_direction.value}; the candidate claims "
          f"{candidate.claimed_direction.value}",
          RejectionReason.DIRECTION_MISMATCH)
    # Consistency with the claim is not the same question as satisfying the gap. A source may say
    # faithfully that something lowers the output; a gap asking for it to be raised is unanswered.
    satisfies_gap = candidate.claimed_direction is gap.required_direction
    check("gap_direction", satisfies_gap,
          f"the gap requires {gap.required_direction.value} and the candidate offers "
          f"{candidate.claimed_direction.value}",
          RejectionReason.DIRECTION_MISMATCH)

    depth, intermediates = _path(candidate, cited_hits)
    check("chain_complete", not intermediates,
          f"unsupported intermediates: {list(intermediates)}" if intermediates
          else "every node the chain needs is produced by a cited claim",
          RejectionReason.UNSUPPORTED_INTERMEDIATE)

    # 6. The ancestry check: a bypass that routes back through the forbidden node is not a bypass.
    anc = ancestry(inventory, candidate)
    forbidden = tuple(sorted(set(gap.forbidden_dependencies) & anc))
    check("forbidden_dependency", not forbidden,
          f"{list(forbidden)} appear upstream of {resolved} under this mechanism" if forbidden
          else f"none of {list(gap.forbidden_dependencies) or ['nothing forbidden']} appears "
               f"upstream of {resolved}",
          RejectionReason.FORBIDDEN_DEPENDENCY)

    # 7. Context, one dimension at a time.
    mismatches: list[str] = []
    unrecorded: list[str] = []
    for dimension in _CONTEXT_DIMENSIONS:
        required = gap.required_context.dimension(dimension)
        if not required:
            continue
        measured = terminal.dimension(dimension)
        if not measured:
            unrecorded.append(dimension)
            continue
        if not _same(required, measured):
            mismatches.append(f"{dimension}: measured in {measured!r}, required {required!r}")
            rejections.append(_DIMENSION_REASON[dimension])
    check("context_match", not mismatches,
          "; ".join(mismatches) if mismatches else "every constrained dimension matches")
    if unrecorded:
        checks.append(MatchResult(
            validator="context_recorded", passed=False,
            detail=f"the source records no {', '.join(unrecorded)}, so transfer is unestablished "
                   "rather than shown"))

    # 8. A candidate that drives a forbidden state cannot satisfy the gap at any entitlement.
    unsafe = tuple(sorted(set(candidate.possible_safety_effects) & set(gap.forbidden_states)))
    check("forbidden_state", not unsafe,
          f"would drive {list(unsafe)}" if unsafe else "declares no forbidden state",
          RejectionReason.FORBIDDEN_STATE)

    unverified = tuple(sorted(hit.source_id for hit in cited_hits if not hit.verified))
    check("source_verified", not unverified,
          f"citations with no retrieval record: {list(unverified)}" if unverified
          else "every citation has a retrieval record",
          RejectionReason.UNVERIFIED_SOURCE)

    levels: list[VerificationLevel] = []
    if not unverified:
        levels.append(VerificationLevel.SOURCE_VERIFIED)
    grounded_in_source = entity_ok and input_ok and output_ok and direction_ok and not intermediates
    if grounded_in_source:
        levels.append(VerificationLevel.CLAIM_GROUNDED_IN_SOURCE)
    if grounded_in_source and not mismatches and not unrecorded and not forbidden:
        levels.append(VerificationLevel.CAPABILITY_ENTITLED_FOR_CONTEXT)

    common = dict(levels=levels, depth=depth, cited=cited, refs=refs, support=support, anc=anc,
                  forbidden=forbidden, intermediates=intermediates)

    if unsafe:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"the candidate would drive {list(unsafe)}, which the gap forbids", **common)
    if forbidden:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"the mechanism routes through {list(forbidden)}, which the gap forbids, so it "
                    "is not the independent route the gap asked for", **common)
    if not satisfies_gap:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"the gap requires {gap.required_direction.value} and the only claim found "
                    f"offers {candidate.claimed_direction.value}; a faithful source for the "
                    "opposite effect does not answer this gap", **common)
    if not grounded_in_source:
        failed = [c.validator for c in checks if not c.passed
                  and c.validator in {"entity_match", "input_match", "output_match",
                                      "direction_match", "chain_complete"}]
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"the cited evidence does not establish the claimed transformation: {failed}",
                    **common)
    if mismatches:
        return done(CapabilityEntitlement.CONTEXT_MISMATCH,
                    "the transformation is in the sources, in an incompatible context: "
                    + "; ".join(mismatches), **common)
    if unrecorded:
        return done(CapabilityEntitlement.CONDITIONAL,
                    f"the source records no {', '.join(unrecorded)}, so the capability holds only "
                    "if it transfers, which is unestablished", **common)
    if unverified:
        return done(CapabilityEntitlement.UNVERIFIED_SOURCE,
                    f"every check passes, and {list(unverified)} have no retrieval record; the "
                    "capability is conditional on the citation being confirmed", **common)
    return done(CapabilityEntitlement.GROUNDED,
                "the claim is about this entity, this input, this output and this direction, in the "
                "required context, with a verified source and no forbidden dependency", **common)


_SUPPORT_RANK = {Support.CONTRADICTED: 0, Support.ASSERTED_ONLY: 1, Support.COMPUTATIONAL: 2,
                 Support.CLASS_LEVEL: 3, Support.DIFFERENT_COMPARTMENT: 4,
                 Support.DIFFERENT_AGENT: 5, Support.MODEL_EXPERIMENTAL: 6,
                 Support.HUMAN_EXPERIMENTAL: 7}


def build(candidate: CapabilityCandidate, gap: CapabilityGap, assessment: CandidateAssessment,
          hits: dict[str, SourceHit]) -> GroundedCapability:
    """The only way a capability comes into existence. Refuses anything the validators did not pass."""
    if not assessment.can_ground:
        raise NotEntitled(
            f"{candidate.candidate_id}: entitlement is {assessment.entitlement.value}; a capability "
            f"is built only from GROUNDED or CONDITIONAL. Rejections: "
            f"{[r.value for r in assessment.rejections]}")
    cited = tuple(hits[ref] for ref in assessment.source_ids)
    terminal = next((hit for hit in cited if hit.claim_output == candidate.claimed_output), cited[-1])
    return GroundedCapability(
        capability_id=f"GC::{gap.gap_id}::{candidate.candidate_id}",
        gap_id=gap.gap_id, candidate_id=candidate.candidate_id,
        physical_primitive=candidate.proposed_entity_or_process,
        input=sorted(candidate.required_inputs)[0] if candidate.required_inputs else terminal.claim_input,
        output=candidate.claimed_output, output_value=candidate.claimed_value,
        direction=candidate.claimed_direction,
        mechanism=candidate.proposed_mechanism, context=candidate.context,
        cell_type=terminal.measured_in_system or "unrecorded by the source",
        scale=candidate.biological_scale,
        evidence_claims=tuple(hit.source_id for hit in cited), references=assessment.references,
        support_level=assessment.support_level,
        # "at most CONDITIONAL" for an unverified citation, applied here so the capability itself
        # cannot be read as more than that.
        entitlement=(CapabilityEntitlement.CONDITIONAL
                     if assessment.entitlement is CapabilityEntitlement.UNVERIFIED_SOURCE
                     else assessment.entitlement),
        verification=assessment.verification,
        validity_domain=terminal.span or "unrecorded by the source",
        known_caveats=tuple(sorted({hit.caveat for hit in cited if hit.caveat})),
        known_confounders=candidate.possible_confounders,
        known_off_targets=candidate.possible_safety_effects,
        forbidden_dependencies_satisfied=gap.forbidden_dependencies,
        causal_depth=assessment.causal_depth,
        provenance=Provenance(
            epistemic_type=EpistemicType.GROUNDED_CAPABILITY,
            source=f"deterministic capability builder for {gap.gap_id}",
            proposed_by="rarepipe discovery compiler (validators, not a proposer)",
            references=assessment.references,
            rationale=assessment.reason))
