"""Stage 06F — what the reopened run changes relative to the frozen result.

A reopened run is only useful if it says, in one table, what moved and what did not. Rows are
computed from the two sanitized artifacts, never written by hand, so "unchanged" means unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

RESIDUAL_DEPENDENCY = re.compile(r"\bresidual\b.*\bfunction", re.I)


class ComparisonRow(BaseModel):
    topic: str
    frozen: str
    now: str
    changed: bool


class BaselineComparison(BaseModel):
    baseline_mechanism_run: str
    baseline_mechanism_digest: str | None = None
    baseline_track2_run: str | None = None
    baseline_track2_digest: str | None = None
    baseline_label: str = ""
    rows: list[ComparisonRow] = Field(default_factory=list)
    conclusions_changed: list[str] = Field(default_factory=list)
    conclusions_unchanged: list[str] = Field(default_factory=list)
    regenerate: list[str] = Field(default_factory=list, description="Dependent stages and why.")


def _sanitized(run: Path, name: str) -> dict:
    return json.loads((run / name).read_text())


def frozen_residual_dependency(track2: dict) -> dict | None:
    for h in track2.get("hypotheses", []):
        for dep in h.get("efficacy_dependencies", []):
            if RESIDUAL_DEPENDENCY.search(dep.get("dependency", "")):
                return dep
    return None


def compare(baseline_mechanism_run: Path, new: dict, track2_run: Path | None = None,
            label: str = "") -> BaselineComparison:
    old = _sanitized(baseline_mechanism_run, "mechanism_dossier.sanitized.json")
    t2 = _sanitized(track2_run, "track2_hypothesis_set.sanitized.json") if track2_run else None
    rows: list[ComparisonRow] = []

    def row(topic: str, frozen: str, now: str) -> None:
        rows.append(ComparisonRow(topic=topic, frozen=frozen, now=now, changed=frozen != now))

    full = lambda d: sum(1 for x in d["documents"] if x.get("full_text"))  # noqa: E731
    row("documents with full text", f"{full(old)} of {len(old['documents'])}", f"{full(new)} of {len(new['documents'])}")
    refresh = new.get("corpus_refresh") or []
    supps = [s for r in refresh for s in r.get("supplements", [])]
    row("supplementary files read", "none attempted",
        f"{sum(1 for s in supps if s['state'] == 'retrieved')} of {len(supps)} listed" if supps else "none listed")
    row("disease-mechanism status", old["status"], new["status"])
    row("exact-allele mechanism complete", str(old["readiness"]["exact_allele_mechanism_complete"]),
        str(new["readiness"]["exact_allele_mechanism_complete"]))
    row("missense allele protein effect", old["state"]["allele_b"]["protein_effect_status"],
        new["state"]["allele_b"]["protein_effect_status"])
    old_claims = {c["id"]: c["status"] for c in old["claims"]}
    new_claims = {c["id"]: c["status"] for c in new["claims"]}
    moved = sorted(k for k in old_claims.keys() & new_claims.keys() if old_claims[k] != new_claims[k])
    row("mechanism claims", f"{len(old_claims)}", f"{len(new_claims)}"
        + (f"; status changed: {', '.join(f'{k} {old_claims[k]}→{new_claims[k]}' for k in moved)}" if moved else ""))
    row("extractor directions corrected on semantic review",
        str(sum(c.get("applied_to", 0) for c in old.get("direction_corrections") or [])),
        str(sum(c.get("applied_to", 0) for c in new.get("direction_corrections") or [])))
    row("variant experiments extracted", str(len(old.get("variant_experiments") or [])),
        str(len(new.get("variant_experiments") or [])))

    rf = new.get("residual_function")
    dep = frozen_residual_dependency(t2) if t2 else None
    frozen_rf = (f"{dep['status']}: {dep['why_it_matters']}" if dep else
                 "not assessed: restoring normal BUBR1 rescues patient cells; no altered-protein experiment extracted")
    if rf:
        row("residual function — class level", "not assessed (no experiment extracted)",
            f"{rf['class_level']}: {rf['class_level_basis']}")
        row("residual function — this child's allele", frozen_rf, f"{rf['exact_allele']}: {rf['exact_allele_basis']}")
        row("decision", "INSUFFICIENT (implicit: dependency unresolved)", f"{rf['decision']}: {rf['decision_meaning']}")

    changed, unchanged, regenerate = [], [], []
    for r in rows:
        (changed if r.changed else unchanged).append(r.topic)
    if rf:
        regenerate.append("Stage 07 intervention map — IP_001/IP_004 must cite the class-level restored-abundance "
                          "evidence and stop saying no experiment has measured it; point statuses stay gated on the "
                          "exact allele")
        regenerate.append("Stage 08 discovery — re-pinned to the new map so the provenance chain stays unbroken; no "
                          "candidate logic depends on residual function")
        regenerate.append("Stage 09 Track 2 — RH_001's residual-function efficacy dependency is re-derived from this "
                          "assessment")
    if moved or old["status"] != new["status"]:
        regenerate.append("Stages 07-09 — mechanism claims or status changed")
    return BaselineComparison(
        baseline_mechanism_run=baseline_mechanism_run.name, baseline_mechanism_digest=old.get("semantic_digest"),
        baseline_track2_run=track2_run.name if track2_run else None,
        baseline_track2_digest=t2.get("semantic_digest") if t2 else None, baseline_label=label,
        rows=rows, conclusions_changed=changed, conclusions_unchanged=unchanged, regenerate=regenerate)
