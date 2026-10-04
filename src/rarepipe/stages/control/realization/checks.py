"""The deterministic checks. Agents generate possibilities; this module decides what may stand.

Each check answers one question, and each refuses rather than guesses:

* **direction** — if the function needs a node raised and the component lowers it, reject. A
  component with the opposite sign is not a weak candidate, it is the wrong candidate.
* **connectivity** — a chain with a hole in it is a chain with a hole in it. A step whose input is
  produced by nothing and declared by nobody is a missing link, and the realization is partial.
* **dependencies** — what a step needs in order to act is declared, so an unmet one is visible.
* **compatibility** — two components cannot compose when one destroys a precondition of the other.
* **safety** — a capability touching a variable the safety region refers to must say what value it
  drives it to. An undeclared safety interaction fails closed; a declared unsafe one is rejected
  outright, never weighed against the benefit.
* **redundancy** — if removing a component changes nothing, remove it. The synthesis layer applies
  this to compositions and the same rule applies here to steps.
* **provenance** — a step with no cited claim is not grounded, whatever its rationale says.
* **confounding** — where the cited claim itself carries a caveat, the realization must name the
  observable that would exclude it, or its readout supports no conclusion.

Nothing here reads an entitlement a proposer supplied; entitlement comes from `evidence.entitle`,
which reads the repository.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.realization.evidence import (
    EvidenceInventory, Entitling, entitle, transfer_gap,
)
from rarepipe.stages.control.realization.kinds import (
    OPPOSITE, Effect, Entitlement, EpistemicBurden, RealizationResult, SUFFICIENT_ENTITLEMENT,
)
from rarepipe.stages.control.realization.mechanisms import MechanisticRealization
from rarepipe.stages.control.realization.primitives import PhysicalPrimitiveRegistry
from rarepipe.stages.control.safety_constraints import UnsafeRegion
from rarepipe.stages.control.state_space import StateSpace

# Preference when several realizations exist for one function. UNSAFE is last and is never chosen.
STATUS_ORDER = {
    RealizationResult.GROUNDED_REALIZATION_CANDIDATE: 0,
    RealizationResult.CONTEXT_MISMATCH: 1,
    RealizationResult.PARTIAL_REALIZATION: 2,
    RealizationResult.EVIDENCE_INSUFFICIENT: 3,
    RealizationResult.NO_GROUNDED_REALIZATION: 4,
    RealizationResult.NOT_REPRESENTABLE: 5,
    RealizationResult.UNSAFE_REALIZATION: 6,
}


class Finding(Immutable):
    kind: str
    detail: str


class StepAssessment(Immutable):
    step_id: str
    primitive: str
    capability_id: str
    acts_on: str
    affects: str
    effect: Effect
    to: str | None = None
    entitlement: Entitlement
    entitlings: tuple[Entitling, ...] = ()
    transfer_gaps: tuple[str, ...] = ()
    grounded: bool
    reason: str


class RealizationAssessment(Immutable):
    realization_id: str
    required_transformation: str
    burden: EpistemicBurden
    status: RealizationResult
    steps: tuple[StepAssessment, ...] = ()
    findings: tuple[Finding, ...] = ()
    missing_links: tuple[str, ...] = ()
    redundant_steps: tuple[str, ...] = ()
    transfer_gaps: tuple[str, ...] = ()
    unknown_steps: tuple[str, ...] = ()
    decomposes_into: tuple[str, ...] = ()
    reaches_target: bool = False
    reason: str = Field("", description="Why this status, in words a reviewer can check.")

    @property
    def grounded(self) -> bool:
        return self.status is RealizationResult.GROUNDED_REALIZATION_CANDIDATE


def _weakest(entitlements: list[Entitlement]) -> Entitlement:
    order = [Entitlement.CONTRADICTED, Entitlement.UNKNOWN, Entitlement.UNSUPPORTED,
             Entitlement.CONTEXT_MISMATCH, Entitlement.CONDITIONAL, Entitlement.SUPPORTED]
    for level in order:
        if level in entitlements:
            return level
    return Entitlement.UNKNOWN


def assess_step(realization: MechanisticRealization, step, registry: PhysicalPrimitiveRegistry,
                inventory: EvidenceInventory, burden: EpistemicBurden) -> StepAssessment:
    primitive = registry.get(step.uses_primitive)
    capability = primitive.capability(step.capability_id)
    if not capability.evidence_edges:
        return StepAssessment(
            step_id=step.step_id, primitive=primitive.primitive_id,
            capability_id=capability.capability_id, acts_on=capability.acts_on,
            affects=capability.affects, effect=capability.effect, to=capability.to,
            entitlement=Entitlement.UNKNOWN, grounded=False,
            reason="the capability cites no claim in the evidence inventory, so nothing entitles it")
    # The realization's agent, falling back to the capability's only when the realization declares
    # none. A step cannot borrow the evidence of a compound the chain is not administering.
    agent = realization.agent or capability.agent
    entitlings = tuple(entitle(inventory, edge_id, agent=agent,
                               compartment=capability.compartment)
                       for edge_id in capability.evidence_edges)
    gaps = tuple(gap for edge_id in capability.evidence_edges
                 if (gap := transfer_gap(inventory, edge_id, system=realization.context_system)))
    overall = _weakest([e.entitlement for e in entitlings])
    sufficient = SUFFICIENT_ENTITLEMENT[burden]
    grounded = overall in sufficient
    reason = (f"{overall.value}; the burden is {burden.value}, which is met by "
              f"{sorted(e.value for e in sufficient)}")
    return StepAssessment(
        step_id=step.step_id, primitive=primitive.primitive_id,
        capability_id=capability.capability_id, acts_on=capability.acts_on,
        affects=capability.affects, effect=capability.effect, to=capability.to,
        entitlement=overall, entitlings=entitlings, transfer_gaps=gaps, grounded=grounded,
        reason=reason)


def sign_findings(realization: MechanisticRealization, registry: PhysicalPrimitiveRegistry,
                  inventory: EvidenceInventory) -> list[Finding]:
    """A capability cannot claim an effect the claim it cites does not imply.

    The cited edge carries its own sign. Composing it with the direction the capability pushes its
    input gives the effect that follows; anything else is a component asserting an effect its
    evidence contradicts, which is a stronger error than weak support.
    """
    out: list[Finding] = []
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        for edge_id in capability.evidence_edges:
            edge = inventory.edge(edge_id)
            # The cited claim must be about the input this capability actually acts on. Citing a
            # claim about a different input is borrowing evidence, not having it.
            if capability.acts_on and edge.source != capability.acts_on:
                out.append(Finding(kind="provenance", detail=(
                    f"{step.step_id}: {capability.capability_id} acts on {capability.acts_on} and "
                    f"cites {edge_id}, which is a claim about {edge.source}; the claim does not "
                    "describe this step")))
                continue
            if edge.target != capability.affects:
                out.append(Finding(kind="provenance", detail=(
                    f"{step.step_id}: {capability.capability_id} affects {capability.affects} and "
                    f"cites {edge_id}, which is a claim about {edge.target}")))
                continue
            implied = edge.effect
            if capability.acts_on and capability.acts_by is Effect.DECREASE:
                implied = OPPOSITE.get(edge.effect, edge.effect)
            if capability.effect is Effect.SET or implied is capability.effect:
                continue
            out.append(Finding(kind="direction", detail=(
                f"{step.step_id}: {capability.capability_id} claims to {capability.effect.value} "
                f"{capability.affects}, but {edge_id} records that {edge.source} "
                f"{edge.effect.value}s it and this capability "
                f"{capability.acts_by.value}s {capability.acts_on or 'nothing upstream'}, which "
                f"implies {implied.value}")))
    return out


def direction_findings(realization: MechanisticRealization,
                       registry: PhysicalPrimitiveRegistry) -> list[Finding]:
    out: list[Finding] = []
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        if capability.affects != realization.target_variable:
            continue
        wanted = realization.required_effect
        if capability.effect is OPPOSITE.get(wanted):
            out.append(Finding(kind="direction", detail=(
                f"{step.step_id}: the transformation needs {realization.target_variable} to "
                f"{wanted.value} and {capability.capability_id} makes it {capability.effect.value}; "
                "a component with the opposite sign is the wrong component, not a weak one")))
        if (capability.effect is Effect.SET and capability.to is not None
                and capability.to != realization.target_value):
            out.append(Finding(kind="direction", detail=(
                f"{step.step_id}: holds {capability.affects} at {capability.to!r} and the "
                f"transformation requires {realization.target_value!r}")))
    return out


def connectivity(realization: MechanisticRealization, registry: PhysicalPrimitiveRegistry
                 ) -> tuple[bool, tuple[str, ...]]:
    """Does the chain run from something applied directly to the target, with no hole?"""
    produced: set[str] = set()
    needed: dict[str, str] = {}
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        produced.add(capability.affects)
        if capability.acts_on:
            needed[capability.acts_on] = step.step_id
    missing = tuple(sorted(f"{node} (needed by {step_id}) is produced by no step and applied by no "
                           "primitive directly" for node, step_id in needed.items()
                           if node not in produced))
    return realization.target_variable in produced, missing


def dependency_findings(realization: MechanisticRealization,
                        registry: PhysicalPrimitiveRegistry) -> list[Finding]:
    produced = {registry.get(s.uses_primitive).capability(s.capability_id).affects
                for s in realization.steps}
    out: list[Finding] = []
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        for requirement in capability.requires:
            if requirement not in produced:
                out.append(Finding(kind="dependency", detail=(
                    f"{step.step_id} requires {requirement}, which no step in this realization "
                    "produces; it is a declared dependency of the chain, not a detail")))
    return out


def compatibility_findings(realization: MechanisticRealization,
                           registry: PhysicalPrimitiveRegistry) -> list[Finding]:
    out: list[Finding] = []
    caps = {s.step_id: registry.get(s.uses_primitive).capability(s.capability_id)
            for s in realization.steps}
    for breaker_id, breaker in sorted(caps.items()):
        for victim_id, victim in sorted(caps.items()):
            if breaker_id == victim_id:
                continue
            clash = sorted(set(breaker.destroys) & (set(victim.requires) | {victim.acts_on}))
            for node in clash:
                if not node:
                    continue
                out.append(Finding(kind="compatibility", detail=(
                    f"{breaker_id} destroys {node}, which {victim_id} needs; the two cannot be "
                    "composed in one realization")))
    return out


def safety_findings(realization: MechanisticRealization, registry: PhysicalPrimitiveRegistry,
                    unsafe: UnsafeRegion, space: StateSpace) -> list[Finding]:
    guarded = {c.unsafe_when.variable: set(c.unsafe_when.allowed) for c in unsafe.constraints}
    out: list[Finding] = []
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        if capability.affects not in guarded:
            continue
        if capability.to is None:
            out.append(Finding(kind="safety", detail=(
                f"{step.step_id} moves {capability.affects}, which the safety region refers to, "
                "without saying what value it drives it to; the interaction cannot be checked so "
                "it is refused")))
        elif capability.to in guarded[capability.affects]:
            out.append(Finding(kind="safety", detail=(
                f"{step.step_id} drives {capability.affects} to {capability.to!r}, which is a "
                "forbidden state; no function it produces is weighed against that")))
    return out


def confound_findings(realization: MechanisticRealization, registry: PhysicalPrimitiveRegistry,
                      inventory: EvidenceInventory, observed: tuple[str, ...]) -> list[Finding]:
    """Where the cited claim carries a caveat, the realization must name what would exclude it."""
    seen = set(observed)
    out: list[Finding] = []
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        for edge_id in capability.evidence_edges:
            edge = inventory.edge(edge_id)
            if not edge.caveat:
                continue
            if not realization.confound_observables:
                out.append(Finding(kind="confound", detail=(
                    f"{step.step_id} rests on {edge_id}, which the chain records with a caveat "
                    f"({edge.caveat[:120]}); the realization names no observable that would "
                    "exclude it, so its readout supports no conclusion")))
            missing = [o for o in realization.confound_observables if o not in seen]
            if missing:
                out.append(Finding(kind="confound", detail=(
                    f"{step.step_id} needs {missing} measured beside it and no available "
                    "experiment measures them")))
    return out


def provenance_findings(realization: MechanisticRealization,
                        registry: PhysicalPrimitiveRegistry) -> list[Finding]:
    out: list[Finding] = []
    for step in realization.steps:
        capability = registry.get(step.uses_primitive).capability(step.capability_id)
        if not capability.evidence_edges:
            out.append(Finding(kind="provenance", detail=(
                f"{step.step_id} uses {capability.capability_id}, which cites no claim; a step with "
                "no source is not grounded however convincing its rationale")))
    return out


def redundant_steps(realization: MechanisticRealization, registry: PhysicalPrimitiveRegistry,
                    inventory: EvidenceInventory, burden: EpistemicBurden) -> tuple[str, ...]:
    """A step whose removal leaves the chain complete and every remaining step grounded."""
    if len(realization.steps) < 2:
        return ()
    out: list[str] = []
    for candidate in realization.steps:
        kept = tuple(s for s in realization.steps if s.step_id != candidate.step_id)
        trimmed = MechanisticRealization(**{**realization.model_dump(),
                                            "steps": tuple(s.model_dump() for s in kept)})
        reaches, missing = connectivity(trimmed, registry)
        if not reaches or missing:
            continue
        if all(assess_step(trimmed, s, registry, inventory, burden).grounded for s in kept):
            out.append(candidate.step_id)
    return tuple(sorted(out))


def assess(realization: MechanisticRealization, registry: PhysicalPrimitiveRegistry,
           inventory: EvidenceInventory, burden: EpistemicBurden, unsafe: UnsafeRegion,
           space: StateSpace, observed: tuple[str, ...]) -> RealizationAssessment:
    steps = tuple(assess_step(realization, s, registry, inventory, burden)
                  for s in realization.steps)
    findings = (direction_findings(realization, registry)
                + sign_findings(realization, registry, inventory)
                + dependency_findings(realization, registry)
                + compatibility_findings(realization, registry)
                + safety_findings(realization, registry, unsafe, space)
                + confound_findings(realization, registry, inventory, observed)
                + provenance_findings(realization, registry))
    reaches, missing = connectivity(realization, registry)
    redundant = redundant_steps(realization, registry, inventory, burden)
    if redundant:
        findings.append(Finding(kind="redundancy", detail=(
            f"steps {list(redundant)} can be removed without changing the outcome; keeping them "
            "would present a component that does nothing as necessary")))
    gaps = tuple(sorted({g for s in steps for g in s.transfer_gaps}))
    unknown_nodes = {c.affects for p in registry.primitives for c in p.capabilities}
    unrepresentable = tuple(sorted(
        {s.affects for s in steps if s.affects not in set(space.names) | unknown_nodes
         | {e.target for e in inventory.edges}}))

    kinds = {f.kind for f in findings}
    base = dict(realization_id=realization.realization_id,
                required_transformation=realization.required_transformation, burden=burden,
                steps=steps, findings=tuple(findings), missing_links=missing,
                redundant_steps=redundant, transfer_gaps=gaps,
                unknown_steps=realization.unknown_steps,
                decomposes_into=realization.decomposes_into, reaches_target=reaches)

    def done(status: RealizationResult, reason: str) -> RealizationAssessment:
        return RealizationAssessment(**base, status=status, reason=reason)

    if "safety" in kinds:
        return done(RealizationResult.UNSAFE_REALIZATION,
                    "a step enters or may enter a forbidden state; safety is a filter here, never "
                    "a cost weighed against the function produced")
    if unrepresentable:
        return done(RealizationResult.NOT_REPRESENTABLE,
                    f"the mechanism needs {list(unrepresentable)}, which the state model cannot "
                    "represent")
    if "direction" in kinds:
        return done(RealizationResult.NO_GROUNDED_REALIZATION,
                    "a component acts in the wrong direction for the transformation it is meant to "
                    "produce")
    if any(s.entitlement is Entitlement.CONTRADICTED for s in steps):
        contradicted = [s.step_id for s in steps if s.entitlement is Entitlement.CONTRADICTED]
        return done(RealizationResult.NO_GROUNDED_REALIZATION,
                    f"{contradicted} rest on a claim the evidence contradicts; a contradicted route "
                    "is not an uncertain one")
    if not realization.steps and realization.decomposes_into:
        return done(RealizationResult.PARTIAL_REALIZATION,
                    "no direct chain; this transformation reduces to "
                    f"{list(realization.decomposes_into)}, each compiled in turn")
    if missing or realization.unknown_steps or not reaches:
        return done(RealizationResult.PARTIAL_REALIZATION,
                    "the chain is incomplete: " + "; ".join(
                        [*missing, *realization.unknown_steps]
                        or [f"no step produces {realization.target_variable}"]))
    if "compatibility" in kinds or "dependency" in kinds:
        return done(RealizationResult.PARTIAL_REALIZATION,
                    "the components do not compose as declared; the conflicting or unmet "
                    "requirement is named")
    if "confound" in kinds:
        return done(RealizationResult.EVIDENCE_INSUFFICIENT,
                    "a cited claim carries a caveat that nothing in this realization would exclude")
    if all(s.grounded for s in steps):
        if gaps:
            return done(RealizationResult.CONTEXT_MISMATCH,
                        "every step is entitled where it was measured, and none of it was measured "
                        f"in {realization.context_system}: " + "; ".join(gaps))
        return done(RealizationResult.GROUNDED_REALIZATION_CANDIDATE,
                    "every step is entitled at the burden this transformation carries, the chain is "
                    "complete, and no transfer gap remains")
    failing = [s for s in steps if not s.grounded]
    if all(s.entitlement is Entitlement.CONTEXT_MISMATCH for s in failing):
        return done(RealizationResult.CONTEXT_MISMATCH,
                    f"{[s.step_id for s in failing]} rest on evidence from a different agent or "
                    "compartment than this realization requires")
    return done(RealizationResult.EVIDENCE_INSUFFICIENT,
                f"{[s.step_id for s in failing]} are not entitled at the {burden.value} burden: "
                + "; ".join(f"{s.step_id} is {s.entitlement.value}" for s in failing))
