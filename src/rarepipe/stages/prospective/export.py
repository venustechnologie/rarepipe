"""Export with an output policy (PRD FR-053, §13.1, §17).

Public exports are built from an allowlist, then every string — structured field or free text — is
scanned for private markers. A hit is either removed with a logged reason or rejects the export,
depending on the mode. Private references (``private:...``) never leave. The export is written as a
sealed run directory: atomic, checksummed, and a failed build writes nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from rarepipe.core.artifacts import RunDirectory, new_run_id, utc_now
from rarepipe.stages.prospective.model import ProspectivePlan
from rarepipe.stages.prospective.store import PlanStore, content_digest

PUBLIC_PLAN_FIELDS = {"schema", "plan_id", "version_id", "parent_version", "change_reason", "change_kind", "case_ref",
                      "decision_question", "patient_relevant_goal", "lifecycle", "synthetic_fixture",
                      "evaluation_mode", "owner", "policy", "hypotheses", "assumptions", "endpoints", "experiments",
                      "forecasts", "rules", "rules_version", "reviews", "tasks", "capability_requests", "blockers",
                      "outcome_availability", "temporal_status", "not_established", "content_digest", "baseline"}
PUBLIC_BASELINE_FIELDS = {"manifest_entries", "manifest_verified", "stage_runs", "semantic_digests",
                          "digest_algorithm", "code_commit", "git_describe", "corpus_snapshot", "status",
                          "known_limitations", "residual_function", "hypothesis_versions"}
ALWAYS_PRIVATE = re.compile(r"private:[\w\-./]+|/Users/|/Volumes/|/private/tmp|\.private\.json", re.I)
HYPOTHETICAL = "HYPOTHETICAL SCENARIO — not evidence, not a decision"


class ExportRejected(ValueError):
    def __init__(self, findings: list[str]):
        super().__init__("public export rejected by output policy: " + "; ".join(findings))
        self.findings = findings


@dataclass
class ScanResult:
    removed: list[str] = field(default_factory=list)


def _scan(obj, path: str, patterns: list[re.Pattern], mode: str, result: ScanResult):
    if isinstance(obj, dict):
        return {k: v for k, v in ((k, _scan(v, f"{path}.{k}", patterns, mode, result)) for k, v in obj.items())
                if v is not _DROP}
    if isinstance(obj, list):
        out = [_scan(v, f"{path}[{i}]", patterns, mode, result) for i, v in enumerate(obj)]
        return [v for v in out if v is not _DROP]
    if isinstance(obj, str):
        for pattern in patterns:
            if pattern.search(obj):
                reason = f"{path}: matched output-policy pattern {pattern.pattern[:40]!r}"
                if mode == "reject":
                    raise ExportRejected([reason])
                result.removed.append(reason)
                return _DROP
    return obj


_DROP = object()


def public_view(plan: ProspectivePlan, private_terms: list[str] = (), mode: str = "remove") -> tuple[dict, list[str]]:
    """Allowlist, then scan. `private_terms` come from the authorized local environment, never from the plan."""
    data = plan.model_dump(mode="json", by_alias=True)
    data = {k: v for k, v in data.items() if k in PUBLIC_PLAN_FIELDS}
    data["baseline"] = {k: v for k, v in data["baseline"].items() if k in PUBLIC_BASELINE_FIELDS}
    patterns = [ALWAYS_PRIVATE] + [re.compile(re.escape(t), re.I) for t in private_terms if t]
    result = ScanResult()
    cleaned = _scan(data, "plan", patterns, mode, result)
    return cleaned, result.removed


def export(store: PlanStore, output: Path, visibility: str, private_terms: list[str] = (), mode: str = "remove",
           version_id: str | None = None) -> Path:
    plan = store.load(version_id)
    run = RunDirectory(output, new_run_id(utc_now())).open()
    manifest: dict = {"plan_id": plan.plan_id, "version_id": plan.version_id, "content_digest": plan.content_digest,
                      "visibility": visibility, "complete_for_freeze": plan.lifecycle.value == "FROZEN",
                      "note": ("incomplete: exported for review; not frozen" if plan.lifecycle.value != "FROZEN"
                               else "frozen version"), "synthetic_fixture": plan.synthetic_fixture}
    try:
        if visibility == "public":
            payload, removed = public_view(plan, private_terms, mode)
            manifest["output_policy"] = {"mode": mode, "removed": removed, "allowlist": sorted(PUBLIC_PLAN_FIELDS)}
            decisions = []
            for d in store.decisions():
                view, more = _scan_decision(d.model_dump(mode="json"), private_terms, mode)
                decisions.append(view)
                manifest["output_policy"]["removed"] += more
            if removed or manifest["output_policy"]["removed"]:
                store.audit("export_fields_removed", count=len(manifest["output_policy"]["removed"]),
                            version=plan.version_id)
        else:
            payload = plan.model_dump(mode="json", by_alias=True)
            decisions = [d.model_dump(mode="json") for d in store.decisions()]
        run.write_text("plan.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        run.write_text("decisions.json", json.dumps(decisions, indent=2, ensure_ascii=False) + "\n")
        manifest["payload_digest"] = content_digest({"plan": payload, "decisions": decisions})
        run.write_text("export_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    except BaseException:
        import shutil
        shutil.rmtree(run.staging, ignore_errors=True)
        raise
    store.audit("export", visibility=visibility, version=plan.version_id)
    return run.seal()


def _scan_decision(d: dict, private_terms, mode) -> tuple[dict, list[str]]:
    patterns = [ALWAYS_PRIVATE] + [re.compile(re.escape(t), re.I) for t in private_terms if t]
    result = ScanResult()
    return _scan(d, f"decision[{d.get('decision_id')}]", patterns, mode, result), result.removed
