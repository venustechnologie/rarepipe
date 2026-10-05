"""Recompile every layer that depends on the evidence, and report what moved.

The order is the dependency order: a layer is recomputed only after everything it rests on. Nothing
here edits a conclusion — each layer's observable is read out of a fresh compilation, and the delta
is the comparison with the recorded baseline.

A layer that did not move still gets a line. "Unchanged" without a reason is indistinguishable from
"not recomputed", and the difference is the whole point of the exercise.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field

from rarepipe.stages.control.evidence_repair.records import RepairLedger
from rarepipe.stages.control.provenance import Immutable

# PRD section 9, in dependency order. A layer is recomputed only after everything it rests on.
LAYER_ORDER = (
    "source_inventory", "grounded_claims", "causal_chain_support", "contradiction_state",
    "direction_and_entitlement", "hypotheses", "control_model", "synthesis_architectures",
    "physical_realizations", "capability_gaps", "experiment_implications",
)


class LayerDelta(Immutable):
    layer: str
    position: int
    before: dict
    after: dict
    changed: bool
    why: str = Field(min_length=20, description="Why it moved, or why it did not. Never blank.")
    attributed_to: tuple[str, ...] = Field(
        (), description="The repairs this layer's movement follows from.")


def observe() -> dict:
    """Read every layer out of a fresh compilation. No cached values, no recorded conclusions."""
    from collections import Counter

    from rarepipe.stages.control.compiler import compile_problem
    from rarepipe.stages.control.discovery import mva_gaps
    from rarepipe.stages.control.discovery.compiler import compile_discovery
    from rarepipe.stages.control.discovery.external import corpus as C
    from rarepipe.stages.control.discovery.external.citation_audit import audit
    from rarepipe.stages.control.mva import problem as control_problem
    from rarepipe.stages.control.realization import mva_realization
    from rarepipe.stages.control.realization.compiler import compile_realization
    from rarepipe.stages.control.synthesis import mva_synthesis
    from rarepipe.stages.control.synthesis.compiler import compile_synthesis
    from rarepipe.stages.prospective.seed import hypotheses as seed_hypotheses
    from rarepipe.stages.simulate.mva import BUBR1, MISSEG, NAD_CELL, NIACIN, mva_chain
    from rarepipe.stages.simulate.validate import published_behaviours

    root = Path(__file__).resolve().parents[5]
    chain = mva_chain()
    snapshot = C.load(C.snapshot_path(root, mva_gaps.CORPUS_VERSION))
    texts = {d.source_id: C.text_of(C.snapshot_path(root, mva_gaps.CORPUS_VERSION), d)
             for d in snapshot.documents}
    rows = audit(snapshot, texts, chain)

    to_nad = chain.predict(NIACIN, NAD_CELL)
    to_misseg = chain.predict(NIACIN, MISSEG)
    to_abundance = chain.predict(NIACIN, BUBR1)
    unknowns = {p.name: p for p in chain.unknown_parameters()}
    effect = chain.propagate(NIACIN, BUBR1, {name: 0.5 for name in unknowns})

    control = compile_problem(control_problem())
    synthesis = compile_synthesis(mva_synthesis.problem())
    bypass = compile_realization(mva_realization.problem())
    abundance = compile_realization(mva_realization.abundance_problem())
    gaps = compile_discovery(mva_gaps.problem(), mva_gaps.targets())

    h04 = sorted(e.ref for h in seed_hypotheses() if h.id == "H04" for e in (h.evidence or ()))
    assert h04, "the hypothesis layer must be observed, not silently skipped"

    direct_step = next(
        (s.entitlement.value for f in abundance.functions for a in f.realizations
         if a.realization_id == "MR_ABUNDANCE_DIRECTLY" for s in a.steps), None)

    return {
        "source_inventory": {
            "chain_edges": len(chain.edges),
            "cited_refs": len({e.evidence_ref for e in chain.edges if e.evidence_ref}),
            "unverified_labels": sorted({e.evidence_ref for e in chain.edges
                                         if e.evidence_ref and "UNVERIFIED" in e.evidence_ref}),
        },
        "grounded_claims": {
            "backward_audit": dict(sorted(Counter(a.verdict.value for a in rows).items())),
            "disqualified": sorted(f"{a.ref}@{a.edge_id}" for a in rows if a.disqualifies),
        },
        "causal_chain_support": {
            "niacin_to_intracellular_nad_verdict": to_nad.verdict,
            "niacin_to_missegregation_verdict": to_misseg.verdict,
            "niacin_to_missegregation_weakest_link": to_misseg.weakest_link,
        },
        "contradiction_state": {
            "contradicted_alternatives_to_abundance": list(to_abundance.contradicted_alternatives),
            "excluded_contradicted_routes_to_abundance_count":
                len(effect.excluded_contradicted_routes),
        },
        "direction_and_entitlement": {"direct_route_step_entitlement": direct_step},
        "hypotheses": {"h04_citations": h04},
        "control_model": {"result": control.result.value, "digest": control.content_digest},
        "synthesis_architectures": {"result": synthesis.result.value,
                                    "digest": synthesis.content_digest},
        "physical_realizations": {
            "bypass": bypass.result.value, "abundance": abundance.result.value,
            "abundance_per_route": {a.realization_id: a.status.value
                                    for f in abundance.functions for a in f.realizations},
            "bypass_digest": bypass.content_digest,
            "abundance_digest": abundance.content_digest,
        },
        "capability_gaps": {"results": {g.gap_id: g.result.value for g in gaps.gaps},
                            "digest": gaps.content_digest},
        "experiment_implications": {
            "published_behaviour_cases": len(published_behaviours()),
            "case_ids_including": sorted(c.case_id for c in published_behaviours()),
            "negative_record_state_for_direct_route": _negative_record_state(),
            "unmeasured_parameters": len(unknowns),
        },
    }


def _negative_record_state() -> str:
    from rarepipe.stages.simulate.negatives import NegativeStore, seed_mva_direct_route_record
    store = NegativeStore()
    return str(seed_mva_direct_route_record(store).result.state)


# Which repairs each layer's movement follows from. Stated, because "something changed somewhere"
# is not an account of why.
ATTRIBUTION: dict[str, tuple[str, ...]] = {
    "source_inventory": ("REPAIR_R1", "REPAIR_R2", "REPAIR_R3", "REPAIR_R4"),
    "grounded_claims": ("REPAIR_R1", "REPAIR_R4"),
    "causal_chain_support": ("REPAIR_R2",),
    "contradiction_state": ("REPAIR_R1",),
    "direction_and_entitlement": ("REPAIR_R1",),
    "hypotheses": ("REPAIR_R1", "REPAIR_R2"),
    # The control compiler's own verdict does not read the chain's citations, but its actuator
    # layer does record them, so the repair moves the report's digest without moving the verdict.
    "control_model": ("REPAIR_R1", "REPAIR_R2"),
    "synthesis_architectures": (),
    "physical_realizations": ("REPAIR_R1", "REPAIR_R2"),
    "capability_gaps": ("REPAIR_R2", "REPAIR_R3"),
    "experiment_implications": ("REPAIR_R1", "REPAIR_R2", "REPAIR_R4"),
}

# How to read a layer that moved only in its digest: the verdict is the scientific claim, the digest
# is the artifact's identity. A digest-only move means the report's contents changed without the
# conclusion changing, and saying so is more honest than reporting either one alone.
WHY_UNCHANGED: dict[str, str] = {
    "synthesis_architectures": (
        "Architectures are composed from declared transformations, and no component's feasibility "
        "changed. The repair altered what is known about a route's evidence, not what any piece is "
        "declared able to do."),
}


def deltas(ledger: RepairLedger, after: dict | None = None) -> tuple[LayerDelta, ...]:
    after = after if after is not None else observe()
    before = ledger.baseline.layers
    out: list[LayerDelta] = []
    for position, layer in enumerate(LAYER_ORDER, start=1):
        was, now = before.get(layer, {}), after.get(layer, {})
        changed = was != now
        if changed:
            moved = sorted(k for k in set(was) | set(now) if was.get(k) != now.get(k))
            verdict_moved = [k for k in moved if "digest" not in k]
            why = (f"{', '.join(moved)} moved, following "
                   f"{list(ATTRIBUTION.get(layer, ())) or 'the repairs'}")
            if not verdict_moved:
                why += (". Only the artifact digest moved: the report's contents changed and its "
                        "conclusion did not")
        else:
            why = WHY_UNCHANGED.get(layer, (
                "Recomputed from the repaired evidence and identical to the baseline; nothing this "
                "layer reads was touched by the repairs."))
        out.append(LayerDelta(layer=layer, position=position, before=was, after=now,
                              changed=changed, why=why,
                              attributed_to=ATTRIBUTION.get(layer, ())))
    return tuple(out)
