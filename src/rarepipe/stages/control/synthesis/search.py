"""Deterministic synthesis: compose typed transformations and see what reaches the target.

This is the search the PRD asks for, implemented as an enumeration over typed compositions rather
than as free generation by an agent. An agent proposing an architecture and an agent *deciding*
that it works are different things; only the first is useful, and only this module answers the
second.

The search is bounded and fails closed. When the composition space exceeds the cap it raises
rather than truncating, because a silently truncated search reports "no architecture found" with
the same words as an exhaustive one.

Every candidate is evaluated on every evidence-consistent variant of every model, through the
existing reachability engine, so an architecture inherits the whole safety and uncertainty
discipline already proven for single controls.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from rarepipe.stages.control.compiler import Problem
from rarepipe.stages.control.controllability import assess
from rarepipe.stages.control.controls import ControlVariable
from rarepipe.stages.control.provenance import EpistemicType, Immutable, Provenance
from rarepipe.stages.control.reachability import Compiled, Outcome, run_strategy
from rarepipe.stages.control.state_space import State
from rarepipe.stages.control.synthesis import composition as comp
from rarepipe.stages.control.synthesis import robustness, stability, synthesizability
from rarepipe.stages.control.synthesis.architecture import (
    ArchitectureAssessment, ControlArchitecture,
)
from rarepipe.stages.control.synthesis.building_blocks import BuildingBlockRegistry
from rarepipe.stages.control.synthesis.feedback import (
    FeedbackPolicy, run_closed_loop, undeclared_releases, unobservable_inputs,
)
from rarepipe.stages.control.synthesis.kinds import (
    CompositionMode, LogicalStatus, PhysicalStatus, StabilityClass,
)
from rarepipe.stages.control.synthesis.population import PopulationLayer, rescue_scope
from rarepipe.stages.control.uncertainty import Variant

COMPOSITION_LIMIT = 25_000


class TooBroadToSynthesize(ValueError):
    """More compositions than the cap. Reported, never silently truncated."""


@dataclass(frozen=True)
class VariantContext:
    """The evidence-consistent biologies, compiled once and shared by every candidate."""

    variants: tuple[Variant, ...]
    compiled: dict[str, Compiled]
    x0: dict[str, tuple[State, ...]]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(v.variant_id for v in self.variants)


def _step_options(available: list[str], max_per_step: int) -> list[tuple[str, ...]]:
    return [tuple(combo) for size in range(1, min(max_per_step, len(available)) + 1)
            for combo in combinations(available, size)]


def enumerate_compositions(block_ids: list[str], max_depth: int,
                           max_per_step: int) -> list[comp.Composition]:
    """Every ordered composition up to the depth cap. Deterministic order."""
    out: list[comp.Composition] = []
    frontier: list[comp.Composition] = [()]
    for _ in range(max_depth):
        nxt: list[comp.Composition] = []
        for current in frontier:
            used = {b for step in current for b in step}
            for added in _step_options([b for b in block_ids if b not in used], max_per_step):
                candidate = current + (added,)
                out.append(candidate)
                nxt.append(candidate)
                if len(out) > COMPOSITION_LIMIT:
                    raise TooBroadToSynthesize(
                        f"more than {COMPOSITION_LIMIT} compositions over {len(block_ids)} blocks "
                        f"at depth {max_depth} and {max_per_step} per step; narrow the registry or "
                        "the depth rather than accepting a truncated search")
        frontier = nxt
    return out


def _loop_as_outcome(loop) -> Outcome:
    status = {"MAINTAINED": "SUCCESS", "NOT_MAINTAINED": "NO_TARGET", "UNSAFE": "UNSAFE"}[loop.status]
    return Outcome(status, final_belief=loop.attractor_states, fired=loop.fired,
                   unsafe_path=loop.unsafe_path, visited=loop.reachable_states)


def assess_composition(problem: Problem, ctx: VariantContext, registry: BuildingBlockRegistry,
                       population: PopulationLayer, architecture: ControlArchitecture
                       ) -> ArchitectureAssessment:
    """Evaluate one architecture on every consistent variant, and say the two feasibilities apart."""
    space = problem.space
    target_ok = lambda s: problem.target.contains(space, s)      # noqa: E731
    unsafe_ok = lambda s: problem.unsafe.contains(space, s)      # noqa: E731
    composition = architecture.composition

    clashes = comp.conflicts(registry, composition)
    moved = comp.moved_variables(registry, composition)
    scales = comp.scales(registry, composition)
    controls, strategy = comp.expand(registry, composition)
    notes: list[str] = []
    if clashes:
        notes.append("refused: " + "; ".join(clashes))

    policy = architecture.feedback
    policy_gaps: tuple[str, ...] = ()
    release_gaps: tuple[str, ...] = ()
    feedback_status = ""
    if policy is not None:
        policy_gaps = unobservable_inputs(policy, problem.observation)
        release_gaps = undeclared_releases(policy, controls)
        unknown = tuple(sorted(set(policy.control_ids) - set(controls)))
        if unknown:
            notes.append(f"policy acts on controls no component provides: {list(unknown)}")

    outcomes: dict[str, Outcome] = {}
    blocked = bool(clashes) or bool(release_gaps) or (policy is not None and policy_gaps)
    for vid in ctx.ids:
        if blocked:
            outcomes[vid] = Outcome("NO_TARGET")
            continue
        if policy is None:
            outcomes[vid] = run_strategy(ctx.compiled[vid], ctx.x0[vid], strategy, controls,
                                         target_ok, unsafe_ok)
        else:
            outcomes[vid] = _loop_as_outcome(run_closed_loop(
                ctx.compiled[vid], ctx.x0[vid], policy, controls, target_ok, unsafe_ok))
    if policy is not None and not blocked:
        statuses = {outcomes[vid].status for vid in ctx.ids}
        feedback_status = (f"closed loop {policy.policy_id}: " +
                           ", ".join(f"{vid}={outcomes[vid].status}" for vid in ctx.ids))
        if policy_gaps:
            statuses.add("unobservable")
    elif policy is not None:
        feedback_status = (f"closed loop {policy.policy_id} not evaluated: " +
                           ("; ".join(notes) or
                            (f"policy inputs {list(policy_gaps)} are not measured" if policy_gaps
                             else f"{list(release_gaps)} do not declare a release value")))

    def unsafe_ids(outcome: Outcome) -> tuple[str, ...]:
        if outcome.status != "UNSAFE" or not outcome.unsafe_path:
            return ()
        return problem.unsafe.violated_by(space, outcome.unsafe_path[-1])

    sa = assess(strategy, list(ctx.variants), outcomes, controls, unsafe_ids)
    works = sa.works_in
    unsafe_in = sa.unsafe_in
    fails = tuple(o.variant_id for o in sa.outcomes if o.status == "NO_TARGET")

    logical = synthesizability.logical_status(works, fails, unsafe_in)
    if clashes:
        logical = LogicalStatus.NOT_REPRESENTABLE
    physical, unassessed = synthesizability.physical_status(registry, composition)
    rclass, rnote = robustness.classify(sa.per_model)

    held = tuple(controls[cid] for cid in sorted(sa.controls))
    if works and not blocked:
        reference = works[0]
        belief = outcomes[reference].final_belief
        if policy is None:
            sclass, snote = stability.classify(ctx.compiled[reference], belief, held,
                                               target_ok, unsafe_ok)
        else:
            # A loop that settles while still holding a control has not shown the state survives
            # withdrawal. Stability is judged against exactly what is held at the attractors, not
            # against an empty hand — otherwise an exogenous variable that simply never moves
            # again would read as self-stabilizing.
            loop = run_closed_loop(ctx.compiled[reference], ctx.x0[reference], policy, controls,
                                   target_ok, unsafe_ok)
            still_held = tuple(controls[cid] for cid in sorted(
                {cid for group in loop.held_at_attractors for cid in group}))
            sclass, snote = stability.classify(ctx.compiled[reference], belief, still_held,
                                               target_ok, unsafe_ok)
            snote = (f"under the closed loop, holding {[c.control_id for c in still_held] or 'nothing'} "
                     f"at the attractors: {snote}")
    else:
        sclass, snote = (StabilityClass.UNKNOWN_STABILITY,
                         "the target is not reached, so there is nothing to hold")

    order_bearing, order_note = (False, "")
    if works and not blocked and policy is None:
        reference = works[0]
        order_bearing, order_note = comp.order_matters(
            ctx.compiled[reference], ctx.x0[reference], registry, composition, target_ok, unsafe_ok)

    pre_gaps = ()
    if not blocked:
        reference = works[0] if works else ctx.ids[0]
        pre_gaps = comp.precondition_gaps(ctx.compiled[reference], ctx.x0[reference], registry,
                                          composition, controls, target_ok, unsafe_ok)
    for gap in pre_gaps:
        notes.append(f"{gap.block_id} needs {gap.requirement}, which holds in {gap.holds_in} of "
                     f"{gap.of_states} states at step {gap.step} ({gap.severity})")

    # Holding a variable that a relationship already defines is an override, not a free control.
    # It asserts an exogenous mechanism can supply what the model attributes to something else.
    override_status = {rel.relationship_id: rel.epistemic_status
                       for model in problem.models for rel in model.relationships
                       if rel.output in moved}
    overrides = tuple(f"{rid} ({override_status[rid]})" for rid in sorted(override_status))
    for rid, status in sorted(override_status.items()):
        notes.append(
            f"overrides {rid} by holding its output directly; whatever supplies that value is a "
            "requirement of its own and is not provided by this model"
            + (". That relationship is established, so this architecture contradicts the best "
               "supported part of the model rather than filling a gap in it"
               if status == "established" else ""))

    outcome_vars = tuple(v for v in problem.target.variables())
    gaps = population.gaps(outcome_vars, problem.observation.observed) if works else ()
    # A population variable this architecture *changes* needs a declared mechanism, whether or not
    # a component sets it directly. Acting one step upstream does not excuse the architecture from
    # saying what makes the effect selective.
    changed: set[str] = set()
    for vid in works:
        before = {name: {space.value(s, name) for s in ctx.x0[vid]}
                  for name in population.population_variables}
        for name, values in before.items():
            after = {space.value(s, name) for s in outcomes[vid].final_belief}
            if after - values:
                changed.add(name)
    undeclared = population.undeclared_movers(space, tuple(sorted(set(moved) | changed)))

    unsafe_path = ()
    for vid in unsafe_in:
        unsafe_path = tuple(space.as_dict(s) for s in outcomes[vid].unsafe_path)
        break

    # Physical feasibility is the components' own, never softened because the logic worked.
    blockers = synthesizability.blockers(registry, composition)
    if physical is PhysicalStatus.PHYSICALLY_FEASIBLE and release_gaps:
        physical = PhysicalStatus.SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN

    return ArchitectureAssessment(
        architecture_id=architecture.architecture_id, family=architecture.family,
        origin=architecture.origin, composition_mode=architecture.composition_mode,
        composition=composition, components=architecture.components, scales=scales,
        rescue_scope=rescue_scope(scales),
        logical=logical, physical=physical, robustness=rclass,
        stability=sclass, stability_note=snote,
        works_in=works, fails_in=fails, unsafe_in=unsafe_in, per_model=sa.per_model,
        blocking_relationships=sa.blocking_relationships, irrelevant_unknowns=sa.irrelevant_unknowns,
        relies_on=sa.relies_on, unresolved_relied_on=sa.unresolved_relied_on,
        feasibility_blockers=unassessed,
        missing_release_declarations=release_gaps, overrides_relationships=overrides,
        confounder_gaps=gaps, undeclared_population_mechanisms=undeclared,
        unobservable_policy_inputs=policy_gaps,
        order_is_load_bearing=order_bearing, order_note=order_note,
        feedback_policy=policy.policy_id if policy else None, feedback_status=feedback_status,
        unsafe_path=unsafe_path,
        assumptions=tuple(sorted(set(architecture.assumptions) | set(blockers))),
        notes=tuple(notes) + (rnote,),
    )


def derived_architecture(registry: BuildingBlockRegistry, composition: comp.Composition,
                         index: int, *, policy: FeedbackPolicy | None = None,
                         family: str = "") -> ControlArchitecture:
    """Wrap a composition the search found as an architecture object, typed as composed, not proposed."""
    blocks = [registry.get(b) for step in composition for b in sorted(step)]
    reversible = all(all(t.released_to is not None for t in b.state_transformations) for b in blocks)
    origin = comp.derive_origin(registry, composition, policy is not None)
    mode = (CompositionMode.CONDITIONAL if policy is not None
            else comp.derive_mode(composition, False, reversible))
    label = "+".join("_".join(sorted(step)) for step in composition)
    return ControlArchitecture(
        architecture_id=f"A{index:03d}::{label}"[:200], family=family or f"derived::{origin.value}",
        composition=composition, composition_mode=mode, feedback=policy, origin=origin,
        rationale=("enumerated by the deterministic composition search over the building-block "
                   "registry; not proposed by any agent"),
        assumptions=tuple(sorted({b.uncertainty for b in blocks})),
        provenance=Provenance(
            epistemic_type=EpistemicType.COMPOSED_CONTROL,
            source="synthesis composition search",
            proposed_by="rarepipe synthesis compiler (deterministic enumeration)",
            rationale="composed from registered building blocks; no claim about feasibility"),
    )


class SynthesisSearch(Immutable):
    assessments: tuple[ArchitectureAssessment, ...]
    compositions_examined: int
    note: str


def synthesize(problem: Problem, ctx: VariantContext, registry: BuildingBlockRegistry,
               population: PopulationLayer, *, max_depth: int = 2, max_per_step: int = 2,
               policies: tuple[FeedbackPolicy, ...] = ()) -> SynthesisSearch:
    """Enumerate compositions, keep the ones that reach the target under some consistent variant."""
    usable = [b.building_block_id for b in registry.usable()]
    compositions = enumerate_compositions(usable, max_depth, max_per_step)
    kept: list[ArchitectureAssessment] = []
    seen_success: set[comp.Composition] = set()
    index = 0
    for candidate in compositions:
        if comp.conflicts(registry, candidate):
            continue
        # A composition that already succeeds as a prefix is not extended: the extra component
        # would be reported as load-bearing when it is not.
        if any(candidate[:k] in seen_success for k in range(1, len(candidate))):
            continue
        index += 1
        architecture = derived_architecture(registry, candidate, index)
        result = assess_composition(problem, ctx, registry, population, architecture)
        if result.works_in:
            seen_success.add(candidate)
            kept.append(result)
        elif result.unsafe_in:
            kept.append(result)
    for policy in policies:
        needed = {cid.split("::")[0] for cid in policy.control_ids}
        available = {b.building_block_id for b in registry.usable()}
        if not needed <= available:
            continue
        index += 1
        architecture = derived_architecture(
            registry, (tuple(sorted(needed)),), index, policy=policy,
            family=f"feedback::{policy.policy_id}")
        kept.append(assess_composition(problem, ctx, registry, population, architecture))
    minimal = _minimal(kept)
    dropped = len(kept) - len(minimal)
    minimal.sort(key=lambda a: (not a.clear, bool(a.unsafe_in), -len(a.works_in),
                                len(a.feasibility_blockers), len(a.components), a.architecture_id))
    return SynthesisSearch(
        assessments=tuple(minimal), compositions_examined=len(compositions),
        note=(f"{len(compositions)} compositions enumerated over {len(usable)} building blocks to "
              f"depth {max_depth}, each evaluated on all {len(ctx.ids)} evidence-consistent "
              f"variants. {dropped} were dropped as non-minimal: a component could be removed "
              "without changing the outcome, and reporting it would overstate what the "
              "architecture needs. Unsafe compositions are kept, so the rejection is visible."),
    )


def _minimal(kept: list[ArchitectureAssessment]) -> list[ArchitectureAssessment]:
    """Two reductions, both about not overstating what an architecture requires.

    * **Removable components.** An architecture whose component set strictly contains a reported
      one with the same outcome is dropped: its extra component changes nothing, and listing it
      would present a free passenger as load-bearing.
    * **Orderings that make no difference.** The same components in several orders are the same
      architecture unless the order changes the verdict. Where `order_matters` found the order to
      be load-bearing every such ordering is kept; where it did not, one representative is kept
      (fewest steps) and its note records how many equivalent orderings were evaluated.
    """
    succeeded = {frozenset(a.components) for a in kept if a.works_in}
    unsafe = {frozenset(a.components) for a in kept if a.unsafe_in and not a.works_in}
    survivors: list[ArchitectureAssessment] = []
    for a in kept:
        mine = frozenset(a.components)
        peers = succeeded if a.works_in else unsafe
        if any(other < mine for other in peers):
            continue
        survivors.append(a)

    groups: dict[tuple, list[ArchitectureAssessment]] = {}
    for a in survivors:
        key = (frozenset(a.components), bool(a.works_in), bool(a.unsafe_in), a.feedback_policy)
        groups.setdefault(key, []).append(a)
    out: list[ArchitectureAssessment] = []
    for key in sorted(groups, key=lambda k: (sorted(k[0]), k[1], k[2], k[3] or "")):
        group = groups[key]
        ordered = [a for a in group if a.order_is_load_bearing]
        if ordered:
            out.extend(ordered)
            continue
        best = min(group, key=lambda a: (len(a.composition), a.composition))
        if len(group) > 1:
            # Rebuilt rather than copied-with-update, so the assessment's validators run again on
            # the object that actually reaches the report.
            best = ArchitectureAssessment(**{**best.model_dump(), "order_note": (
                f"{len(group)} orderings of these components were evaluated and every one gave the "
                "same verdict, so the order is not part of this architecture")})
        out.append(best)
    return out
