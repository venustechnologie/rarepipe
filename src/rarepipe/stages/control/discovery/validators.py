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
from rarepipe.stages.control.discovery.external.claims import (
    CAUSAL_ENOUGH, CausalGrade, ContextVerdict, TransferGap, compartment_verdict,
)
from rarepipe.stages.control.discovery.external.semantics import SemanticsRegistry
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
    transfer_gaps: tuple[TransferGap, ...] = ()
    causal_grade: CausalGrade | None = None
    context_verdict: ContextVerdict | None = None
    independence: str = Field(
        "", description="How independence from the gap's forbidden dependencies stands. Silence in "
                        "the sources is recorded as unestablished, never as independence.")
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


def ancestry(inventory: EvidenceInventory, candidate: CapabilityCandidate,
             declared: tuple[tuple[str, str], ...] = ()) -> set[str]:
    """Everything upstream of the output **under this candidate's own mechanism**.

    Not the union of every recorded way to reach the output. The inventory already records that the
    forbidden component drives these outputs — that is why the gaps exist — so walking upward from
    the output would find it for every candidate and declare nothing independent, ever. The walk
    starts from what this mechanism rests on: its declared inputs and the dependencies its own
    sources state.

    The declared dependencies are what stops the check passing vacuously in the other direction. A
    newly discovered entity has no ancestry in the inventory at all, so without them any claim about
    anything unfamiliar would be certified independent by default.
    """
    parents: dict[str, list[str]] = {}
    for item in inventory.edges:
        parents.setdefault(item.target, []).append(item.source)
    roots = set(candidate.required_inputs) | {dependency for _, dependency in declared}
    seen: set[str] = set(roots)
    frontier = list(roots)
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


def _forbidden_terms(gap: CapabilityGap) -> tuple[str, ...]:
    """Spellings of the forbidden dependency a source might use. Node name plus its vocabulary."""
    from rarepipe.stages.control.discovery.external.claims import CandidateClaim  # noqa: F401
    terms: set[str] = set()
    for node in gap.forbidden_dependencies:
        terms.add(node)
        terms.update(FORBIDDEN_SPELLINGS.get(node, ()))
    return tuple(sorted(terms))


# How a source is likely to name a forbidden node. Explicit, because inferring it from the node name
# by string munging would both miss spellings and invent matches.
FORBIDDEN_SPELLINGS: dict[str, tuple[str, ...]] = {
    "bubr1_residual_function": ("BubR1", "BUBR1", "BUB1B", "Bub1b"),
}


def assess(candidate: CapabilityCandidate, gap: CapabilityGap, hits: dict[str, SourceHit],
           inventory: EvidenceInventory, vocab: Vocabulary,
           documents: dict[str, str] | None = None,
           semantics: SemanticsRegistry | None = None) -> CandidateAssessment:
    checks: list[MatchResult] = []
    rejections: list[RejectionReason] = []

    def check(name: str, passed: bool, detail: str, reason: RejectionReason | None = None) -> bool:
        checks.append(MatchResult(validator=name, passed=passed, detail=detail))
        if not passed and reason is not None:
            rejections.append(reason)
        return passed

    def done(entitlement: CapabilityEntitlement, reason: str, *, levels=(), depth=0,
             cited=(), refs=(), support=Support.ASSERTED_ONLY, anc=(), forbidden=(),
             intermediates=(), transfer=(), grade=None, independence="") -> CandidateAssessment:
        return CandidateAssessment(
            candidate_id=candidate.candidate_id, gap_id=gap.gap_id, entitlement=entitlement,
            verification=tuple(levels), checks=tuple(checks), rejections=tuple(rejections),
            ancestry=tuple(sorted(anc)), forbidden_hits=tuple(sorted(forbidden)),
            transfer_gaps=tuple(transfer), causal_grade=grade, independence=independence,
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
    # Where the gap asks for a qualitative state rather than a direction, the direction question is
    # subsumed by the state question, which refuses for the sharper reason — so the report says
    # "an increase is not a restored function" instead of saying "wrong direction" twice.
    state_gap = bool(gap.required_value)
    satisfies_gap = (candidate.claimed_direction is gap.required_direction) or state_gap
    check("gap_direction",
          satisfies_gap,
          ("the gap asks for a qualitative state, so direction is judged by whether the effect "
           "constitutes that state" if state_gap else
           f"the gap requires {gap.required_direction.value} and the candidate offers "
           f"{candidate.claimed_direction.value}"),
          RejectionReason.DIRECTION_MISMATCH)

    # External-evidence checks. Each applies only where a provider supplied the field, and an
    # absent field is treated as "not established" rather than as a pass.
    documents = documents or {}
    semantics = semantics or SemanticsRegistry()
    spans_ungrounded: list[str] = []
    for hit in cited_hits:
        if not hit.quoted_span:
            continue
        text = documents.get(hit.source_id)
        if text is None:
            spans_ungrounded.append(f"{hit.source_id} (no stored document to check the span against)")
        elif " ".join(hit.quoted_span.split()).lower() not in " ".join(text.split()).lower():
            spans_ungrounded.append(f"{hit.source_id} (the quoted span is not in the stored document)")
    if any(hit.quoted_span for hit in cited_hits):
        check("span_grounded", not spans_ungrounded,
              "; ".join(spans_ungrounded) or "every quoted span appears verbatim in its stored source",
              RejectionReason.SPAN_NOT_GROUNDED)

    graded = [hit for hit in cited_hits if hit.causal_grade is not None]
    association_only = tuple(sorted(h.source_id for h in graded
                                    if h.causal_grade is CausalGrade.ASSOCIATION))
    if graded:
        check("causal_grade", not association_only,
              f"{list(association_only)} are association-level" if association_only
              else f"grades: {sorted({h.causal_grade.value for h in graded})}",
              RejectionReason.ASSOCIATION_ONLY)

    state_ok, state_reason = semantics.satisfies(
        resolved, candidate.claimed_direction, gap.required_value)
    if gap.required_value:
        check("effect_constitutes_state", state_ok, state_reason,
              RejectionReason.EFFECT_IS_NOT_STATE)

    named = tuple(sorted({term for hit in cited_hits
                          for term in _forbidden_terms(gap)
                          if hit.quoted_span and term.lower() in hit.quoted_span.lower()}))
    if gap.forbidden_dependencies:
        check("forbidden_not_named_in_span", not named,
              f"the supporting span names {list(named)}, so independence cannot be certified from it"
              if named else "no supporting span names a forbidden dependency",
              RejectionReason.FORBIDDEN_NAMED_IN_SPAN)

    depth, intermediates = _path(candidate, cited_hits)
    check("chain_complete", not intermediates,
          f"unsupported intermediates: {list(intermediates)}" if intermediates
          else "every node the chain needs is produced by a cited claim",
          RejectionReason.UNSUPPORTED_INTERMEDIATE)

    # 6. The ancestry check: a bypass that routes back through the forbidden node is not a bypass.
    declared_edges = tuple(sorted({(hit.claim_output, dependency)
                                   for hit in cited_hits
                                   for dependency in hit.declared_dependencies}))
    anc = ancestry(inventory, candidate, declared_edges)
    forbidden = tuple(sorted(set(gap.forbidden_dependencies) & anc))
    check("forbidden_dependency", not forbidden,
          f"{list(forbidden)} appear upstream of {resolved} under this mechanism" if forbidden
          else f"none of {list(gap.forbidden_dependencies) or ['nothing forbidden']} appears "
               f"upstream of {resolved}",
          RejectionReason.FORBIDDEN_DEPENDENCY)

    # Independence is a claim that needs a source, not a default. Silence is unestablished.
    independence = ""
    if gap.forbidden_dependencies and not forbidden and not named:
        asserted = {entity.lower() for hit in cited_hits
                    for entity in hit.asserts_independence_from}
        wanted = {term.lower() for term in _forbidden_terms(gap)}
        if asserted & wanted:
            independence = (f"a retrieved source states the mechanism does not require "
                            f"{sorted(asserted & wanted)}")
            check("independence_asserted", True, independence)
        else:
            independence = ("no retrieved source states that this mechanism works without "
                            f"{list(gap.forbidden_dependencies)}; absence of a recorded link is not "
                            "evidence of independence")
            check("independence_asserted", False, independence,
                  RejectionReason.INDEPENDENCE_UNESTABLISHED)

    # Transfer gaps, as objects rather than warnings.
    # One transfer gap per dimension that genuinely differs. The system dimension is built from the
    # lattice's most specific descriptor rather than from whichever field the gap happens to
    # constrain: a relation demonstrated in one tissue and required in another is a transfer gap
    # whether or not the gap spelled "tissue" out, and skipping it because the field was blank is how
    # a difference becomes invisible.
    gaps_found: list[TransferGap] = []
    for hit in cited_hits:
        if hit.lattice is None:
            continue
        lattice = hit.lattice
        system_demonstrated = lattice.cell_type or lattice.tissue or lattice.experimental_system
        if system_demonstrated and lattice.disease_state:
            system_demonstrated = f"{system_demonstrated} ({lattice.disease_state})"
        candidates = (
            ("species", lattice.species, "human"),
            ("system", system_demonstrated, gap.required_context.system),
            ("compartment", lattice.compartment, gap.required_context.compartment),
        )
        for dimension, demonstrated, required in candidates:
            if not demonstrated or not required:
                continue
            if dimension == "compartment":
                if compartment_verdict(demonstrated, required) in {
                        ContextVerdict.EXACT_CONTEXT, ContextVerdict.COMPATIBLE_CONTEXT}:
                    continue
            elif _same(demonstrated, required):
                continue
            gaps_found.append(TransferGap(
                gap_id=f"TG::{gap.gap_id}::{hit.source_id}::{dimension}", dimension=dimension,
                demonstrated_in=demonstrated, required=required,
                missing=f"evidence that the relation holds in {required} as well as {demonstrated}"))

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
        if dimension == "compartment":
            # The transfer rule for compartments is explicit, not string equality: a tissue
            # measurement of an intracellular metabolite is compatible; whole blood is not.
            verdict = compartment_verdict(measured, required)
            if verdict is ContextVerdict.INCOMPATIBLE_CONTEXT:
                mismatches.append(f"compartment: measured in {measured!r}, required {required!r}")
                rejections.append(_DIMENSION_REASON[dimension])
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
                  forbidden=forbidden, intermediates=intermediates,
                  transfer=tuple(gaps_found), grade=(min((h.causal_grade for h in graded),
                                                         key=lambda g: _GRADE_RANK[g])
                                                     if graded else None),
                  independence=independence)

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
    if spans_ungrounded:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    "a quoted span could not be found in its stored source: "
                    + "; ".join(spans_ungrounded), **common)
    if association_only:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"{list(association_only)} support an association, and a capability asserting a "
                    "causal transformation cannot rest on one", **common)
    if gap.required_value and not state_ok:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT, state_reason, **common)
    if named:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT,
                    f"the text supporting this claim names {list(named)}, which the gap forbids "
                    "depending on; independence cannot be certified from a span that names it",
                    **common)
    if RejectionReason.INDEPENDENCE_UNESTABLISHED in rejections:
        return done(CapabilityEntitlement.EVIDENCE_INSUFFICIENT, independence, **common)
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


_GRADE_RANK = {CausalGrade.ASSOCIATION: 0, CausalGrade.PERTURBATION_SUPPORTED: 1,
               CausalGrade.MECHANISTIC: 2, CausalGrade.CAUSAL_EXPERIMENTAL: 3}

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
