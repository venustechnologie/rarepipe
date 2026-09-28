#!/usr/bin/env python3
"""Cross-artifact integrity check for an M5 packet.

The handoff format checker validates one document's shape. It cannot see that two documents in the
same packet name different plan content, which is exactly the defect that reached a reviewer: a
fabricated digest in `proposals.json` that shared a prefix with the real one and looked plausible.

This check compares every identity field in the packet against one authoritative source — the
validator artifact — and, when the plan store is reachable, recomputes the digest from the stored
plan with the project's own canonical implementation. It also reconciles the gap coverage and the
advertised counts. It asserts nothing about the science.

Usage: uv run python tools/m5/check_consistency.py <packet-dir> [--plan-store DIR --plan-id ID]
Exit code 0 only if nothing was found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def check(packet: Path, plan_store: Path | None, plan_id: str | None) -> list[str]:
    problems: list[str] = []
    validator = load(packet / "validator_output.json")
    register = load(packet / "gap_register.json")
    proposals = load(packet / "proposals.json")
    if validator is None:
        return ["validator_output.json is missing: there is no authoritative identity to check against"]
    truth = {"plan_id": validator["plan_id"], "plan_version": validator["plan_version"],
             "content_digest": validator["plan_content_digest"]}

    # The strongest available check: recompute from the plan store with the project's own code.
    if plan_store and plan_id:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
            from rarepipe.stages.prospective.store import PlanStore, plan_digest
            plan = PlanStore(plan_store, plan_id).load()
            recomputed = plan_digest(plan)
            if recomputed != truth["content_digest"]:
                problems.append(f"validator digest {truth['content_digest']} does not match the digest recomputed "
                                f"from the plan store ({recomputed}): the validator artifact is stale or the plan "
                                "moved")
            if plan.version_id != truth["plan_version"]:
                problems.append(f"plan store HEAD is {plan.version_id}, validator artifact says "
                                f"{truth['plan_version']}")
        except Exception as exc:  # noqa: BLE001 — a failed recomputation is a finding, not a crash
            problems.append(f"could not recompute the digest from the plan store: {type(exc).__name__}: {exc}")

    if register is not None:
        if register.get("source_plan_version") != truth["plan_version"]:
            problems.append(f"gap_register.source_plan_version {register.get('source_plan_version')!r} != "
                            f"{truth['plan_version']!r}")
        if register.get("source_plan_content_digest") != truth["content_digest"]:
            problems.append("gap_register.source_plan_content_digest disagrees with the validator artifact")
    if proposals is not None:
        baseline = proposals.get("baseline", {})
        if baseline.get("plan_id") != truth["plan_id"]:
            problems.append(f"proposals.baseline.plan_id {baseline.get('plan_id')!r} != {truth['plan_id']!r}")
        if baseline.get("plan_version") != truth["plan_version"]:
            problems.append(f"proposals.baseline.plan_version {baseline.get('plan_version')!r} != "
                            f"{truth['plan_version']!r}")
        if baseline.get("plan_content_hash") != truth["content_digest"]:
            problems.append(f"proposals.baseline.plan_content_hash {baseline.get('plan_content_hash')} disagrees "
                            f"with the validator artifact {truth['content_digest']}")

    # Any digest anywhere in the packet's prose that is not a digest the packet legitimately carries.
    known = {truth["content_digest"], validator.get("review_digest")}
    for name in ("review_packet.md", "critique.md"):
        text = (packet / name).read_text() if (packet / name).exists() else ""
        for found in set(DIGEST.findall(text)):
            if found not in known and found not in json.dumps(validator):
                problems.append(f"{name} cites digest {found}, which is not the plan's content or review digest")

    # Coverage and counting (R02): advertise nothing a field does not have.
    if register is not None and proposals is not None:
        real = {g["gap_id"] for g in register["source_gap_records"]}
        if len(real) != len(register["source_gap_records"]):
            problems.append("gap_register contains duplicate gap_id values")
        covered: dict[str, list[str]] = {}
        for item in proposals["items"]:
            for gid in item["source_gap_ids"]:
                covered.setdefault(gid, []).append(item["id"])
        invented = sorted(set(covered) - real)
        missing = sorted(real - set(covered))
        twice = sorted(g for g, owners in covered.items() if len(owners) > 1)
        if invented:
            problems.append(f"proposals cite {len(invented)} gap id(s) absent from the validator output: "
                            f"{invented[:5]}")
        if missing:
            problems.append(f"{len(missing)} validator gap(s) are covered by no proposal: {missing[:5]}")
        if twice:
            problems.append(f"gap(s) claimed by more than one proposal: {twice[:5]}")
        progress = register.get("progress", {})
        ready_fields = sum(1 for item in proposals["items"] for _ in item["source_gap_ids"]
                           if item.get("field_readiness") == "APPLY_READY")
        declared = progress.get("ready_for_human_review")
        if declared is not None and declared != ready_fields and "field_readiness" in json.dumps(proposals):
            problems.append(f"gap_register.progress.ready_for_human_review is {declared} but the proposals mark "
                            f"{ready_fields} field(s) apply-ready")
        # The reviewer-facing value must be exactly what the fields say, or two specifications are
        # active at once — the defect that let a stale 30% threshold survive beside its own repeal.
        for item in proposals["items"]:
            fv = item.get("field_values") or {}
            pv = (item.get("proposal") or {}).get("value")
            if fv and isinstance(pv, dict):
                drifted = [g for g, spec in fv.items() if g not in pv or pv[g] != spec.get("value")]
                extra = [g for g in pv if g not in fv]
                if drifted:
                    problems.append(f"{item['id']}: proposal.value disagrees with field_values for "
                                    f"{len(drifted)} field(s): {drifted[:3]}")
                if extra:
                    problems.append(f"{item['id']}: proposal.value carries {len(extra)} key(s) with no field "
                                    f"record: {extra[:3]}")
            elif fv and pv is not None and not isinstance(pv, dict):
                problems.append(f"{item['id']}: has field_values but proposal.value is not generated from them")
            if item.get("superseded_proposal") and not item["superseded_proposal"].get("reason"):
                problems.append(f"{item['id']}: superseded_proposal must say why it was superseded")
        for item in proposals["items"]:
            if item.get("status") == "READY_FOR_HUMAN_REVIEW":
                fields = item.get("field_values")
                if isinstance(fields, dict):
                    nulls = sorted(k for k, v in fields.items()
                                   if v is None or (isinstance(v, dict) and v.get("value") is None))
                    if nulls:
                        problems.append(f"{item['id']} is READY_FOR_HUMAN_REVIEW but these advertised fields carry "
                                        f"no value: {nulls}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packet", type=Path)
    ap.add_argument("--plan-store", type=Path, default=None)
    ap.add_argument("--plan-id", default=None)
    args = ap.parse_args()
    problems = check(args.packet, args.plan_store, args.plan_id)
    print(json.dumps({
        "status": "PACKET_CONSISTENT" if not problems else "PACKET_INCONSISTENT",
        "problems": problems,
        "checked": ["plan identity against the validator artifact",
                    "digest recomputed from the plan store where reachable",
                    "digests cited in prose", "gap coverage: invented, missing, double-claimed",
                    "advertised ready fields actually carry values",
                    "reviewer-facing proposal.value matches field_values exactly"],
        "not_checked": ["whether the science is right", "whether a cited source says what is claimed",
                        "human identity", "native Rarepipe plan validation"],
    }, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
