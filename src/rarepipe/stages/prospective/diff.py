"""What changed between two plan versions, and what a baseline change touches (PRD §16.5, FR-043).

Scientific, editorial and operational changes are told apart. Whitespace, punctuation or letter-case
changes to text are editorial. Any other change to a scientific field is scientific — a sentence
that changes scope is a scientific change, whatever its length.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rarepipe.stages.prospective.model import BaselineRef, ProspectivePlan

OPERATIONAL_FIELDS = {"owner", "owners", "status", "tasks", "capability_requests", "blockers", "reviews",
                      "execution_state", "recheck_by", "estimated_cost", "estimated_time", "completion_evidence"}
IGNORED = {"version_id", "parent_version", "change_reason", "change_kind", "content_digest", "lifecycle"}
COLLECTIONS = ("hypotheses", "assumptions", "endpoints", "experiments", "forecasts", "rules", "tasks",
               "capability_requests")


@dataclass
class Change:
    path: str
    kind: str  # scientific | editorial | operational
    old: object
    new: object

    def render(self) -> str:
        def short(v):
            s = str(v)
            return s if len(s) <= 90 else s[:87] + "..."
        return f"[{self.kind}] {self.path}: {short(self.old)} → {short(self.new)}"


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text).strip().lower()


def _classify(path: str, old, new) -> str:
    leaf = path.split(".")[-1].split("[")[0]
    if leaf in OPERATIONAL_FIELDS or any(f".{f}" in f".{path}" for f in ("tasks", "capability_requests", "reviews")):
        return "operational"
    if isinstance(old, str) and isinstance(new, str) and _norm(old) == _norm(new):
        return "editorial"
    return "scientific"


def _walk(path: str, old, new, out: list[Change]) -> None:
    if old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if not path and key in IGNORED:
                continue
            _walk(f"{path}.{key}" if path else key, old.get(key), new.get(key), out)
        return
    if isinstance(old, list) and isinstance(new, list) and path.split(".")[-1] in COLLECTIONS:
        def index(items):
            return {i.get("id", str(n)): i for n, i in enumerate(items)} if all(isinstance(i, dict) for i in items) \
                else None
        a, b = index(old), index(new)
        if a is not None and b is not None:
            for key in sorted(set(a) | set(b)):
                _walk(f"{path}[{key}]", a.get(key), b.get(key), out)
            return
    out.append(Change(path, _classify(path, old, new), old, new))


def diff_plans(old: ProspectivePlan, new: ProspectivePlan) -> list[Change]:
    out: list[Change] = []
    _walk("", old.model_dump(mode="json", by_alias=True), new.model_dump(mode="json", by_alias=True), out)
    return out


@dataclass
class ImpactReport:
    changed_baseline_fields: list[str]
    changed_refs: list[str]
    affected_assumptions: list[str]
    affected_hypotheses: list[str]
    affected_forecasts: list[str]
    affected_experiments: list[str]
    affected_tasks: list[str]
    reviews_invalidated: list[str]

    def render(self) -> str:
        lines = ["Baseline impact report"]
        for name in ("changed_baseline_fields", "changed_refs", "affected_assumptions", "affected_hypotheses",
                     "affected_forecasts", "affected_experiments", "affected_tasks", "reviews_invalidated"):
            lines.append(f"- {name.replace('_', ' ')}: {', '.join(getattr(self, name)) or 'none'}")
        return "\n".join(lines)


def impact(plan: ProspectivePlan, new_baseline: BaselineRef, changed_refs: list[str]) -> ImpactReport:
    """Everything downstream of a baseline change. The historical version stays intact; the successor's
    reviews are invalidated. `changed_refs` names the baseline items a source correction touched."""
    old = plan.baseline.model_dump(mode="json")
    new = new_baseline.model_dump(mode="json")
    fields = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    refs = set(changed_refs)
    assumptions = [a.id for a in plan.assumptions if refs & set(a.depends_on)]
    hypotheses = [h.id for h in plan.hypotheses
                  if refs & {e.ref for e in h.evidence} or set(assumptions) & set(h.dependencies)]
    forecasts = [f.id for f in plan.forecasts
                 if set(assumptions) & set(f.assumptions) or f.hypothesis in hypotheses
                 or (f.evidence_snapshot not in new_baseline.semantic_digests.values())]
    experiments = sorted({f.experiment for f in plan.forecasts if f.id in forecasts})
    tasks = [t.id for t in plan.tasks if set(t.dependencies) & set(experiments + hypotheses + forecasts)
             or t.origin in experiments + hypotheses + forecasts]
    return ImpactReport(fields, sorted(refs), assumptions, hypotheses, forecasts, experiments, tasks,
                        [r.review_id for r in plan.reviews])
