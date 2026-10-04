"""From per-variant outcomes to what can honestly be said about a strategy.

A strategy is evaluated on every evidence-consistent variant. What it depends on is then derived,
not asserted:

* an unknown relationship **blocks** a strategy only if changing that relationship's candidate —
  with everything else held fixed — changes the outcome. An unknown that does not change the
  answer is reported as irrelevant to this question, not as a blocker. Over-reporting blockers
  hides the real one in noise;
* named models **disagree** when their verdicts on the strategy differ;
* a control whose feasibility is not established blocks the strategy by name.
"""
from __future__ import annotations

from pydantic import Field

from rarepipe.stages.control.controls import ControlVariable, Feasibility
from rarepipe.stages.control.provenance import Immutable
from rarepipe.stages.control.reachability import Outcome
from rarepipe.stages.control.uncertainty import Variant


class VariantOutcome(Immutable):
    variant_id: str
    model_id: str
    status: str
    unsafe_constraints: tuple[str, ...] = ()


class StrategyAssessment(Immutable):
    strategy: tuple[tuple[str, ...], ...]
    controls: tuple[str, ...]
    outcomes: tuple[VariantOutcome, ...]
    works_in: tuple[str, ...]
    unsafe_in: tuple[str, ...]
    per_model: tuple[tuple[str, str], ...] = Field(
        description="model_id -> ALL | SOME | NONE across that model's consistent variants")
    blocking_relationships: tuple[str, ...]
    irrelevant_unknowns: tuple[str, ...]
    model_disagreement: bool
    feasibility_blockers: tuple[str, ...]
    relies_on: tuple[str, ...]
    unresolved_relied_on: tuple[str, ...]

    @property
    def robust(self) -> bool:
        return bool(self.per_model) and all(v == "ALL" for _, v in self.per_model)

    @property
    def works_somewhere(self) -> bool:
        return bool(self.works_in)


def assess(strategy, variants: list[Variant], outcomes: dict[str, Outcome],
           controls: dict[str, ControlVariable], unsafe_ids) -> StrategyAssessment:
    ordered = sorted(variants, key=lambda v: v.variant_id)
    rows = []
    for v in ordered:
        out = outcomes[v.variant_id]
        rows.append(VariantOutcome(variant_id=v.variant_id, model_id=v.model_id, status=out.status,
                                   unsafe_constraints=unsafe_ids(out)))
    works = tuple(r.variant_id for r in rows if r.status == "SUCCESS")
    unsafe = tuple(r.variant_id for r in rows if r.status == "UNSAFE")

    per_model = []
    for model_id in sorted({v.model_id for v in ordered}):
        mine = [r for r in rows if r.model_id == model_id]
        ok = sum(1 for r in mine if r.status == "SUCCESS")
        per_model.append((model_id, "ALL" if ok == len(mine) else "NONE" if ok == 0 else "SOME"))

    # An unknown blocks only if flipping its candidate, all else equal, flips the outcome.
    unknown_ids = sorted({rid for v in ordered for rid, _ in v.choices})
    blocking, irrelevant = [], []
    for rid in unknown_ids:
        groups: dict[tuple, set[str]] = {}
        for v in ordered:
            rest = (v.model_id, tuple((r, lab) for r, lab in v.choices if r != rid))
            groups.setdefault(rest, set()).add(outcomes[v.variant_id].status == "SUCCESS")
        (blocking if any(len(s) > 1 for s in groups.values()) else irrelevant).append(rid)

    used = tuple(sorted({cid for step in strategy for cid in step}))
    feasibility = tuple(f"control_feasibility:{cid}" for cid in used
                        if controls[cid].feasibility is not Feasibility.ESTABLISHED)

    relied, unresolved = set(), set()
    status_of = {fn.relationship_id: fn.epistemic_status for v in ordered for fn in v.functions}
    for v in ordered:
        if outcomes[v.variant_id].status == "SUCCESS":
            relied.update(outcomes[v.variant_id].fired)
    unresolved = {rid for rid in relied if status_of.get(rid) != "established"}

    return StrategyAssessment(
        strategy=strategy, controls=used, outcomes=tuple(rows), works_in=works, unsafe_in=unsafe,
        per_model=tuple(per_model), blocking_relationships=tuple(blocking),
        irrelevant_unknowns=tuple(irrelevant),
        model_disagreement=len({verdict for _, verdict in per_model}) > 1,
        feasibility_blockers=feasibility, relies_on=tuple(sorted(relied)),
        unresolved_relied_on=tuple(sorted(unresolved)),
    )
