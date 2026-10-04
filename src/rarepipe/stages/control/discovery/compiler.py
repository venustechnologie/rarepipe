"""The discovery compiler: a missing function in, a verdict on whether it can be filled out.

    missing function -> search specification -> candidate -> evidence -> capability -> recompile

The last step is what makes this more than a retrieval exercise. A new grounded capability updates
the physical registry, the realization is recompiled, and the report states the delta — or states
that there is none. "Previously `NO_GROUNDED_REALIZATION`, now `PARTIAL_REALIZATION`" is a useful
sentence; "we found forty-seven papers" is not.

Every negative result names the universe that was inspected. A gap closing with
`NO_GROUNDED_CAPABILITY` against a fifteen-claim corpus means something very different from the same
words against a literature index, and the report says which it was.
"""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field, model_validator

from rarepipe.stages.control.discovery.candidates import (
    CapabilityCandidate, MechanismHypothesis,
)
from rarepipe.stages.control.discovery.capabilities import (
    CapabilityRegistry, GroundedCapability,
)
from rarepipe.stages.control.discovery.gaps import CapabilityGap, specification
from rarepipe.stages.control.discovery.kinds import (
    GAP_MEANING, RESULT_ORDER, CandidateStatus, CapabilityEntitlement, GapResult, RejectionReason,
    VerificationLevel,
)
from rarepipe.stages.control.discovery.providers import (
    CapabilitySourceProvider, ProviderReport, SourceHit, search,
)
from rarepipe.stages.control.discovery.external.citation_audit import CitationAudit
from rarepipe.stages.control.discovery.external.semantics import SemanticsRegistry
from rarepipe.stages.control.discovery.validators import CandidateAssessment, assess, build
from rarepipe.stages.control.discovery.vocabulary import Vocabulary, dedup_key, vocabulary
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.realization.compiler import (
    RealizationProblem, compile_realization,
)
from rarepipe.stages.control.realization.evidence import (
    ContextRecord, EvidenceEdge, EvidenceInventory,
)
from rarepipe.stages.control.realization.kinds import PrimitiveClass
from rarepipe.stages.control.realization.primitives import (
    Capability, PhysicalPrimitive, PhysicalPrimitiveRegistry,
)
from rarepipe.stages.control.state_space import StateSpace
from rarepipe.stages.prospective.store import content_digest

DISCOVERY_COMPILER_VERSION = "discovery-compiler-0.1.0"

NO_RECOMMENDATION = (
    "This report contains no treatment recommendation and no clinical advice. It states whether a "
    "named biological capability could be grounded in evidence this compiler was given access to, "
    "and what changed in the compiled architecture as a result. A grounded capability is a claim "
    "about evidence, not about what should be done to anyone."
)


@dataclass(frozen=True)
class GapProblem:
    """Providers are objects with behaviour, so this is a dataclass rather than a model."""

    problem_id: str
    case_ref: str
    gaps: tuple[CapabilityGap, ...]
    inventory: EvidenceInventory
    space: StateSpace
    providers: tuple[CapabilitySourceProvider, ...]
    discovery_model_version: str
    hypotheses: tuple[MechanismHypothesis, ...] = ()
    agent_candidates: tuple[CapabilityCandidate, ...] = field(default_factory=tuple)
    documents: dict[str, str] = field(default_factory=dict)
    semantics: SemanticsRegistry = field(default_factory=lambda: SemanticsRegistry())
    baseline_results: dict[str, str] = field(
        default_factory=dict,
        metadata={"why": "the previous run's result per gap. The headline metric is a change of "
                         "epistemic state, and a state cannot be seen to change without something "
                         "to compare it to."})
    baseline_providers: tuple[str, ...] = ()
    citation_attributions: tuple[CitationAudit, ...] = ()


class RejectedCandidate(Immutable):
    candidate_id: str
    entity: str
    reasons: tuple[str, ...]
    detail: str


class CapabilityGapReport(Immutable):
    gap_id: str
    required_transformation: str
    forbidden_dependencies: tuple[str, ...]
    epistemic_burden: str
    result: GapResult
    result_meaning: str
    universe_inspected: tuple[dict, ...] = Field(
        description="Each provider, its corpus size and what it is, so a negative result is "
                    "readable as a statement about the corpus.")
    candidate_mechanisms_considered: tuple[str, ...] = ()
    candidate_physical_primitives: tuple[str, ...] = ()
    assessments: tuple[CandidateAssessment, ...] = ()
    grounded_capabilities: tuple[GroundedCapability, ...] = ()
    conditional_candidates: tuple[str, ...] = ()
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    context_gaps: tuple[str, ...] = ()
    remaining_missing_steps: tuple[str, ...] = ()
    transfer_gaps: tuple[str, ...] = ()
    newly_grounded_claims: tuple[str, ...] = ()
    architecture_impact: str = ""
    current_known_paths: tuple[str, ...] = ()
    reason: str

    @model_validator(mode="after")
    def _contents_support_the_result(self):
        if self.result is GapResult.CAPABILITY_FOUND and not self.grounded_capabilities:
            raise ValueError("CAPABILITY_FOUND requires a capability the builder actually produced")
        if self.result is GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND:
            if not any(a.forbidden_hits for a in self.assessments):
                raise ValueError(
                    "ONLY_DEPENDENT_CAPABILITIES_FOUND must name the forbidden dependency each "
                    "candidate routed through")
        if self.result is GapResult.NO_GROUNDED_CAPABILITY and not self.universe_inspected:
            raise ValueError("a negative result must say what universe was inspected")
        return self


class GapDelta(Immutable):
    """What moved for one gap, against the previous run.

    A headline that stays the same while the reasons change is still progress: the open problem has
    become more specific. Both are recorded, and neither is presented as the other.
    """

    gap_id: str
    before: str
    after: str
    headline_changed: bool
    grounds_changed: bool
    new_providers: tuple[str, ...] = ()
    new_candidates: tuple[str, ...] = ()
    note: str


class RecompileDelta(Immutable):
    target: str
    before: str
    after: str
    changed: bool
    capabilities_added: tuple[str, ...] = ()
    note: str


class DiscoveryReport(Immutable):
    origin: str = "simulated_prediction"
    discovery_compiler_version: str
    realization_compiler_version: str
    discovery_model_version: str
    problem_id: str
    case_ref: str
    gaps: tuple[CapabilityGapReport, ...]
    gap_deltas: tuple[GapDelta, ...] = ()
    citation_audit: tuple[CitationAudit, ...] = Field(
        (), description="The repository's own citations, checked against the retrieved documents. "
                        "The grounding rule applied backwards.")
    grounded_capabilities: tuple[GroundedCapability, ...] = ()
    recompiles: tuple[RecompileDelta, ...] = ()
    interfaces_whose_state_changed: tuple[str, ...] = Field(
        (), description="The metric: previously-open functional interfaces whose epistemic state "
                        "moved, in either direction. Not papers found, not candidates generated.")
    no_treatment_recommendation: str = NO_RECOMMENDATION
    abstention_reason: str = ""
    reproducibility: dict
    content_digest: str = ""

    @model_validator(mode="after")
    def _honest(self):
        if self.origin != "simulated_prediction":
            raise ValueError("a discovery report is a simulated prediction, never an observation")
        if self.no_treatment_recommendation != NO_RECOMMENDATION:
            raise ValueError("the no-recommendation statement is fixed and may not be reworded")
        built = {c.capability_id for c in self.grounded_capabilities}
        claimed = {c.capability_id for g in self.gaps for c in g.grounded_capabilities}
        if claimed - built:
            raise ValueError("a gap reports a capability the discovery report does not hold")
        return self

    def with_digest(self) -> "DiscoveryReport":
        return DiscoveryReport(**{**self.model_dump(),
                                  "content_digest": content_digest(
                                      self, exclude={"content_digest", "reproducibility"})})


def _repro() -> dict:
    root = Path(__file__).resolve().parents[5]

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001 — reproducibility metadata is best-effort
            return "unavailable"
    return {"code_revision": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "python": platform.python_version(),
            "digest_covers": "every field except content_digest and this block"}


def candidates_from_hits(gap: CapabilityGap, reports: tuple[ProviderReport, ...]
                         ) -> tuple[CapabilityCandidate, ...]:
    """Enumerate what the sources actually say. This is not an agent inventing anything.

    One candidate per hit, asserting exactly the claim the source makes. A candidate built this way
    passes the entity, input, output and direction checks by construction, which is the point: the
    checks that then decide the verdict are the ones about context and forbidden dependencies.
    """
    out: list[CapabilityCandidate] = []
    for report in reports:
        for hit in report.hits:
            out.append(CapabilityCandidate(
                candidate_id=f"CC::{gap.gap_id}::{hit.source_id}",
                gap_id=gap.gap_id,
                proposed_mechanism=(f"{hit.claim}, as {hit.provider} records it for "
                                    f"{hit.claim_input} -> {hit.claim_output}"),
                proposed_entity_or_process=hit.claim_subject,
                required_inputs=(hit.claim_input,), claimed_output=hit.claim_output,
                claimed_direction=hit.claim_direction, claimed_value=gap.required_value,
                context=gap.required_context, biological_scale=gap.biological_scale,
                dependencies=(hit.claim_input,),
                possible_confounders=(hit.caveat,) if hit.caveat else (),
                supporting_evidence_refs=(hit.source_id,),
                provenance=Provenance(
                    epistemic_type=EpistemicType.LITERATURE_EVIDENCE,
                    source=f"{hit.provider} hit {hit.source_id}",
                    proposed_by="rarepipe discovery compiler (enumeration of provider hits)",
                    references=(hit.reference,) if hit.reference else ("no citation in corpus",),
                    rationale="asserts exactly the claim the source makes, no more")))
    return tuple(sorted(out, key=lambda c: c.candidate_id))


def _result(gap: CapabilityGap, assessments: tuple[CandidateAssessment, ...],
            built: tuple[GroundedCapability, ...]) -> tuple[GapResult, str]:
    if built and any(c.entitlement is CapabilityEntitlement.GROUNDED for c in built):
        return (GapResult.CAPABILITY_FOUND,
                f"{len(built)} capability/capabilities satisfy the specification, including its "
                "forbidden dependencies")
    if not assessments:
        return (GapResult.NO_GROUNDED_CAPABILITY,
                "no provider returned a claim about this output, so there was nothing to assess")
    if all(a.forbidden_hits for a in assessments):
        routed = sorted({f for a in assessments for f in a.forbidden_hits})
        return (GapResult.ONLY_DEPENDENT_CAPABILITIES_FOUND,
                f"every candidate found routes upstream through {routed}, which this gap forbids. "
                "That is a sharper result than finding nothing: the inspected universe contains no "
                "independent route to this output")
    if any(a.entitlement is CapabilityEntitlement.CONTRADICTED for a in assessments):
        return (GapResult.CONTRADICTED_CAPABILITY,
                "the most relevant claim for this transformation is a null or opposite result")
    if any(a.entitlement is CapabilityEntitlement.CONTEXT_MISMATCH for a in assessments):
        return (GapResult.CONTEXT_ONLY_CAPABILITY,
                "the transformation exists in the sources, in a compartment, agent or system "
                "incompatible with the one required")
    if built:
        return (GapResult.PARTIAL_CAPABILITY,
                "a capability was built at a conditional entitlement, so the gap is not closed; "
                "what remains is named")
    if any(a.unsupported_intermediates for a in assessments):
        return (GapResult.PARTIAL_CAPABILITY,
                "a chain exists and at least one transformation in it is not grounded; the "
                "ungrounded link is named")
    return (GapResult.NO_GROUNDED_CAPABILITY,
            "candidates were found and none is admissible; each rejection is named")


def compile_gap(problem: GapProblem, gap: CapabilityGap, vocab: Vocabulary) -> CapabilityGapReport:
    spec = specification(gap)
    reports = search(problem.providers, spec)
    # Candidates are enumerated from the claims about the required output; a citation resolves
    # against everything the providers hold, so a multi-step candidate can be audited step by step
    # instead of being refused as fabricated.
    hits: dict[str, SourceHit] = {hit.source_id: hit
                                  for report in reports
                                  for hit in (*report.hits, *report.related)}

    enumerated = candidates_from_hits(gap, reports)
    proposed = tuple(c for c in problem.agent_candidates if c.gap_id == gap.gap_id)
    seen: set[tuple[str, ...]] = set()
    candidates: list[CapabilityCandidate] = []
    for candidate in sorted([*enumerated, *proposed], key=lambda c: c.candidate_id):
        key = dedup_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)

    assessments = tuple(assess(c, gap, hits, problem.inventory, vocab,
                               documents=problem.documents, semantics=problem.semantics)
                        for c in candidates)
    built: list[GroundedCapability] = []
    for candidate, assessment in zip(candidates, assessments):
        if assessment.can_ground:
            built.append(build(candidate, gap, assessment, hits))
    result, reason = _result(gap, assessments, tuple(built))

    rejected = tuple(RejectedCandidate(
        candidate_id=a.candidate_id,
        entity=next(c.proposed_entity_or_process for c in candidates if c.candidate_id == a.candidate_id),
        reasons=tuple(sorted({r.value for r in a.rejections})), detail=a.reason)
        for a in assessments if not a.can_ground)

    return CapabilityGapReport(
        gap_id=gap.gap_id, required_transformation=gap.required_transformation,
        forbidden_dependencies=gap.forbidden_dependencies,
        epistemic_burden=gap.epistemic_burden.value, result=result,
        result_meaning=GAP_MEANING[result],
        universe_inspected=tuple({"provider": r.provider, "corpus_size": r.corpus_size,
                                  "corpus": r.corpus_description, "hits": len(r.hits),
                                  "note": r.note, "accounting": r.accounting,
                                  "queries": list(r.queries)} for r in reports),
        candidate_mechanisms_considered=tuple(sorted(
            {h.statement for h in problem.hypotheses if h.gap_id == gap.gap_id}
            | {c.proposed_mechanism for c in candidates})),
        candidate_physical_primitives=tuple(sorted({c.proposed_entity_or_process
                                                    for c in candidates})),
        assessments=assessments, grounded_capabilities=tuple(built),
        conditional_candidates=tuple(sorted(
            a.candidate_id for a in assessments
            if a.entitlement in {CapabilityEntitlement.CONDITIONAL,
                                 CapabilityEntitlement.UNVERIFIED_SOURCE})),
        rejected_candidates=rejected,
        rejection_reasons=tuple(sorted({r.value for a in assessments for r in a.rejections})),
        contradictions=tuple(sorted(a.candidate_id for a in assessments
                                    if a.entitlement is CapabilityEntitlement.CONTRADICTED)),
        context_gaps=tuple(sorted({c.detail for a in assessments for c in a.checks
                                   if not c.passed and c.validator.startswith("context")})),
        remaining_missing_steps=tuple(sorted({i for a in assessments
                                              for i in a.unsupported_intermediates})),
        transfer_gaps=tuple(sorted({g.summary for a in assessments for g in a.transfer_gaps})),
        newly_grounded_claims=tuple(sorted({claim for c in built for claim in c.evidence_claims})),
        current_known_paths=gap.current_known_paths, reason=reason)


def as_primitive(capability: GroundedCapability,
                 produced: frozenset[str] = frozenset()) -> PhysicalPrimitive:
    """A grounded capability, expressed as a piece the realization compiler can use.

    Whether the capability's input is something you administer or something upstream has to produce
    is decided by the corpus, not guessed: an input no claim produces is an origin, so the piece is
    applied directly. An input other claims do produce is an internal node, so the piece acts on it
    and declares needing it — which the realization's connectivity check then has to satisfy.
    """
    internal = capability.input in produced
    return PhysicalPrimitive(
        primitive_id=f"PP::{capability.capability_id}",
        primitive_class=PrimitiveClass.OTHER, identity=capability.physical_primitive,
        capabilities=(Capability(
            capability_id=f"CAP::{capability.capability_id}", claim=capability.mechanism,
            acts_on=capability.input if internal else "", affects=capability.output,
            effect=capability.direction, to=capability.output_value or None,
            agent=capability.context.agent, compartment=capability.context.compartment,
            evidence_edges=capability.evidence_claims,
            requires=(capability.input,) if internal else ()),),
        required_context=capability.context.system, cell_type=capability.cell_type,
        biological_scale=capability.scale,
        reversibility="unrecorded by the grounding source",
        temporal_properties="unrecorded by the grounding source; no value is invented",
        delivery_requirements="unrecorded by the grounding source",
        known_off_targets=capability.known_off_targets,
        evidence=(f"grounded for gap {capability.gap_id} at entitlement "
                  f"{capability.entitlement.value}, support {capability.support_level.value}"),
        validity_domain=capability.validity_domain,
        uncertainty="; ".join(capability.known_caveats) or "no caveat recorded by the source",
        feasibility_status=f"entitlement {capability.entitlement.value}",
        provenance=Provenance(
            epistemic_type=EpistemicType.BUILDING_BLOCK_CAPABILITY,
            source=f"grounded capability {capability.capability_id}",
            proposed_by="rarepipe discovery compiler (deterministic builder)",
            references=capability.references,
            rationale=f"causal depth {capability.causal_depth}; "
                      f"{capability.entitlement.value} for the required context"))


def extended_inventory(target: RealizationProblem,
                       added: tuple[GroundedCapability, ...]) -> EvidenceInventory:
    """The realization's evidence inventory, plus the claims the new capabilities rest on.

    A capability grounded from external literature cites source ids the realization's own inventory
    has never seen, and that inventory refuses a citation it does not hold — correctly, since that
    check is what stops invented references. So the registry update has to carry the evidence as well
    as the piece: the grounded claim becomes an edge, with the support level, scope and context the
    grounding established, and the realization layer then applies its own checks to it unchanged.
    """
    edges = list(target.inventory.edges)
    contexts = list(target.inventory.contexts)
    known = {edge.edge_id for edge in edges}
    seen_refs = {record.ref for record in contexts}
    for capability in added:
        for claim in capability.evidence_claims:
            if claim in known:
                continue
            known.add(claim)
            edges.append(EvidenceEdge(
                edge_id=claim, source=capability.input, target=capability.output,
                effect=capability.direction,
                mechanism=f"{capability.mechanism} (grounded for {capability.gap_id})",
                support=capability.support_level,
                ref=capability.references[0] if capability.references else "",
                verified=VerificationLevel.SOURCE_VERIFIED in capability.verification,
                scope=capability.validity_domain,
                caveat="; ".join(capability.known_caveats)))
        reference = capability.references[0] if capability.references else ""
        if reference and reference not in seen_refs:
            seen_refs.add(reference)
            contexts.append(ContextRecord(
                ref=reference, measured_with=capability.context.agent or "unrecorded",
                measured_in_compartment=capability.context.compartment,
                measured_in_system=capability.context.system,
                transcribed_from=f"grounded capability {capability.capability_id}"))
    return EvidenceInventory(edges=tuple(sorted(edges, key=lambda e: e.edge_id)),
                             contexts=tuple(sorted(contexts, key=lambda c: c.ref)))


def recompile(target: RealizationProblem, added: tuple[GroundedCapability, ...]) -> RecompileDelta:
    """Update the registry, recompile, and report the delta — including when there is none."""
    before = compile_realization(target)
    if not added:
        return RecompileDelta(
            target=target.target_architecture, before=before.result.value,
            after=before.result.value, changed=False,
            note=("no capability was grounded, so nothing was added and nothing recompiled "
                  "differently. The result is unchanged for a stated reason, not by omission"))
    produced = frozenset(edge.target for edge in target.inventory.edges)
    primitives = tuple(as_primitive(c, produced) for c in added)
    updated = RealizationProblem(**{
        **target.model_dump(),
        "inventory": extended_inventory(target, added).model_dump(),
        "registry": PhysicalPrimitiveRegistry(
            primitives=(*target.registry.primitives, *primitives)).model_dump()})
    after = compile_realization(updated)
    return RecompileDelta(
        target=target.target_architecture, before=before.result.value, after=after.result.value,
        changed=after.result is not before.result,
        capabilities_added=tuple(sorted(c.capability_id for c in added)),
        note=(f"{len(added)} capability/capabilities added to the registry; the compiled result "
              + ("changed" if after.result is not before.result else
                 "did not change, because the new piece does not lie on a route to the target")))


def compile_discovery(problem: GapProblem,
                      targets: tuple[RealizationProblem, ...] = ()) -> DiscoveryReport:
    vocab = vocabulary(problem.space, problem.inventory)
    reports = [compile_gap(problem, gap, vocab)
               for gap in sorted(problem.gaps, key=lambda g: g.gap_id)]
    built = tuple(sorted({c.capability_id: c for r in reports
                          for c in r.grounded_capabilities}.values(),
                         key=lambda c: c.capability_id))
    deltas = tuple(recompile(target, built) for target in targets)

    impact = {d.target: d for d in deltas}
    finished = []
    for report in reports:
        note = "; ".join(
            f"{d.target}: {d.before} -> {d.after}" + ("" if d.changed else " (unchanged)")
            for d in deltas) or "no realization target was recompiled"
        finished.append(CapabilityGapReport(**{**report.model_dump(),
                                               "architecture_impact": note}))

    # The metric: functional interfaces whose epistemic state moved, measured against the previous
    # run rather than against nothing. A headline change and a change in why the headline holds are
    # both progress, and they are reported as different things.
    gap_deltas = []
    for report in finished:
        before = problem.baseline_results.get(report.gap_id, "")
        providers_now = {item["provider"] for item in report.universe_inspected}
        new_providers = tuple(sorted(providers_now - set(problem.baseline_providers)))
        new_candidates = tuple(sorted(
            a.candidate_id for a in report.assessments
            if any(p in a.candidate_id for p in ("PMID:", "EPMC:")) and new_providers))
        headline = bool(before) and before != report.result.value
        grounds = bool(new_providers) and bool(report.assessments)
        gap_deltas.append(GapDelta(
            gap_id=report.gap_id, before=before or "not previously compiled",
            after=report.result.value, headline_changed=headline, grounds_changed=grounds,
            new_providers=new_providers, new_candidates=new_candidates,
            note=(f"headline {before} -> {report.result.value}" if headline else
                  (f"headline unchanged at {report.result.value}; candidates from "
                   f"{list(new_providers)} were examined and refused for named reasons, so the open "
                   "problem is more specific than it was" if grounds else
                   f"unchanged at {report.result.value}"))))

    changed = tuple(sorted(
        [f"{d.gap_id}: {d.before} -> {d.after}" for d in gap_deltas if d.headline_changed]
        + [f"{d.gap_id}: grounds changed, {d.after} now rests on {list(d.new_providers)}"
           for d in gap_deltas if d.grounds_changed and not d.headline_changed]
        + [f"{d.target}: {d.before} -> {d.after}" for d in deltas if d.changed]))

    return DiscoveryReport(
        discovery_compiler_version=DISCOVERY_COMPILER_VERSION,
        realization_compiler_version="realization-compiler-0.1.0",
        discovery_model_version=problem.discovery_model_version,
        problem_id=problem.problem_id, case_ref=problem.case_ref, gaps=tuple(finished),
        gap_deltas=tuple(gap_deltas), citation_audit=problem.citation_attributions,
        grounded_capabilities=built, recompiles=deltas,
        interfaces_whose_state_changed=changed,
        abstention_reason=("" if built else
                           "no capability was grounded in the universe inspected; every gap states "
                           "which providers were searched, how large their corpora are, and why "
                           "each candidate was rejected"),
        reproducibility=_repro()).with_digest()
