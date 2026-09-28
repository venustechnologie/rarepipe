#!/usr/bin/env python3
"""Make `field_values` the single current representation of each proposed choice.

The successor packet carried corrected per-field values *beside* the original proposal objects, so two
specifications were active at once: one field rejected an arbitrary 30% cutoff while the proposal text
still applied it, and the reviewer questions still asked for approval of superseded reasoning. A
reviewer could have approved the wrong design.

After this pass, for every item that has field values:
  * `proposal.value` is generated from `field_values`, so the reviewer-facing value cannot drift;
  * `proposal.conditions` is the union of the fields' `depends_on`;
  * the original object is kept verbatim as `superseded_proposal`, marked, not deleted;
  * `reviewer_question` is regenerated from the current fields.

`tools/m5/check_consistency.py` then fails the packet if the generated value ever disagrees again.

Usage: uv run python tools/m5/reconcile.py <packet-dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

UNDECIDED = (" or ",)
DECISION_WORDS = ("median or", "robust mean", "holm or", "hierarchy", "mean or")

# Replacement reviewer questions. W003/W004/W007 are the integration review's proposed wording;
# W001/W002/W005/W006 are regenerated from the corrected fields.
QUESTIONS = {
    "M5_W003": ("Which biological adequacy, meaningful-improvement and adverse-effect boundaries do the scientific "
                "reviewers propose, with what rationale? Separately, which nuisance quantities need local "
                "calibration, and should that calibration be a separate pilot or a prespecified internal component?"),
    "M5_W004": ("What does the bench protocol establish about treatment allocation and the intended inference "
                "population? For each endpoint, which effect summary and error-control procedure is proposed, and "
                "which assay or simulation results must be available before selecting it?"),
    "M5_W007": ("Should the designated reviewers now assess the explicitly conditional successor proposals, with "
                "unresolved criteria and dependencies recorded? Completing that review would not by itself "
                "authorise a scientific freeze while the required fields remain unresolved."),
    "M5_W001": ("For each EXP01 endpoint, do you accept the proposed measurement and its validity criteria as "
                "stated in the field values, and which of the remaining expression-linkage options (titrated "
                "expression, prospective intensity window, or population-level measurement) should be developed "
                "first? No numeric pass threshold is proposed; the earlier 30% matched-subset rule is withdrawn."),
    "M5_W002": ("For each EXP02 endpoint, do you accept the proposed measurement and validity criteria, including "
                "recording SIRT2 activity and K668 acetylation as NOT_MEASURED when no validated reagent exists? "
                "Who owns the exposure concentration and duration, which no field here proposes?"),
    "M5_W005": ("Which model route do you want costed first, and who is the named owner able to confirm present "
                "availability and permitted use for it?"),
    "M5_W006": ("Will you complete the five-item timing attestation before any freeze, or freeze with "
                "TEMPORAL_STATUS_UNVERIFIED recorded and no preregistration claim?"),
}


def unfinished(value: object) -> str | None:
    """A proposed executable value must select one option or give a deterministic rule."""
    if not isinstance(value, str):
        return None
    low = value.lower()
    for word in DECISION_WORDS:
        if word in low:
            start = max(0, low.find(word) - 40)
            return value[start:start + 120].strip()
    return None


def main() -> int:
    packet = Path(sys.argv[1])
    path = packet / "proposals.json"
    doc = json.loads(path.read_text())
    changes: list[dict] = []

    for item in doc["items"]:
        fv = item.get("field_values") or {}
        if not fv:
            continue

        # 1. Demote fields whose proposed value still contains an undecided choice.
        for gid, spec in fv.items():
            frag = unfinished(spec.get("value"))
            if frag and spec.get("status") == "APPLY_READY":
                spec["status"] = "CONDITIONAL"
                spec.setdefault("depends_on", []).append(
                    "a design decision selecting one option (or a deterministic rule for selecting it)")
                spec["note"] = (spec.get("note", "") + " Demoted from APPLY_READY: the proposed value still "
                                f"offers alternatives ({frag!r}) rather than selecting one.").strip()
                changes.append({"field": gid, "change": "APPLY_READY -> CONDITIONAL", "reason": "undecided choice"})
            # EXP03 inherits EXP02's choices; record that dependency explicitly.
            if gid.startswith("EXP03.") and isinstance(spec.get("value"), str) and \
                    ("EXP02" in spec["value"] or "as EXP02" in spec["value"].lower()):
                dep = "EXP02 selection of the same field (inherited)"
                if dep not in (spec.get("depends_on") or []):
                    spec.setdefault("depends_on", []).append(dep)
                    if spec.get("status") == "APPLY_READY":
                        spec["status"] = "CONDITIONAL"
                        changes.append({"field": gid, "change": "APPLY_READY -> CONDITIONAL",
                                        "reason": "inherits an EXP02 choice that is not yet selected"})
                    else:
                        changes.append({"field": gid, "change": "recorded inherited dependency",
                                        "reason": "inherits an EXP02 choice"})
            # 2. Route a scientific judgement to a human, without discarding the validator's owner.
            deps = " ".join(spec.get("depends_on") or [])
            if spec.get("status") == "BLOCKED_EVIDENCE" and ("decision" in deps.lower() or "lead" in deps.lower()):
                mixes_calibration = any(w in deps.lower() for w in ("assay sensitivity", "calibration", "variance",
                                                                    "detectable"))
                spec["status"] = "BLOCKED_HUMAN"
                spec["decision_owner"] = "scientific_lead"
                if mixes_calibration:
                    spec["also_blocked_on_evidence"] = True
                    spec["note"] = (spec.get("note", "") + " Mixed: a scientific judgement about acceptable effect "
                                    "AND an analytical calibration input. Both are represented; the validator's "
                                    "owner field is unchanged.").strip()
                changes.append({"field": gid, "change": "BLOCKED_EVIDENCE -> BLOCKED_HUMAN",
                                "reason": "its stated dependency is a human decision"})

        # 3. Generate the reviewer-facing proposal from the fields, and archive the original.
        original = item["proposal"]
        if "superseded_proposal" not in item:
            item["superseded_proposal"] = {
                "superseded_at": "2026-09-29",
                "reason": ("kept for audit only. It contained an alternative operational specification that "
                           "contradicted the corrected field values (for example an arbitrary matched-subset "
                           "threshold, a single pilot resolving every threshold gap, and a pilot-derived margin). "
                           "It is not an active specification and must not be reviewed for approval."),
                "object": original,
            }
        conditions = sorted({d for spec in fv.values() for d in (spec.get("depends_on") or [])})
        blocked = {k: v["status"] for k, v in fv.items()
                   if v.get("status") in ("BLOCKED_EVIDENCE", "BLOCKED_HUMAN", "DISCUSSION_ONLY")}
        item["proposal"] = {
            "value": {gid: spec.get("value") for gid, spec in fv.items()},
            "value_source": "generated from field_values by tools/m5/reconcile.py; field_values is the single "
                            "current representation of each proposed choice",
            "rationale": (f"One proposed value per gap, from the corrected specialist report for {item['id']}. "
                          "Where a value is null the field is deliberately unresolved and names what it waits on. "
                          "The superseded proposal object is retained separately for audit."),
            "alternatives": original.get("alternatives", []),
            "conditions": conditions or ["none recorded"],
            "limitations": [
                f"{len(fv)} field(s) declared; {len(blocked)} carry no applicable value "
                f"({', '.join(sorted(set(blocked.values()))) or 'none'}).",
                "No numeric threshold is proposed anywhere in this item unless its field says so explicitly.",
                "Nothing here is accepted: the native validator still reports every gap until a human accepts "
                "edits through the versioned workflow.",
                *[x for x in original.get("limitations", [])
                  if "could not be brought" not in x and "32 gaps" not in x and "one dependency, not 32" not in x],
            ],
        }
        item["reviewer_question"] = QUESTIONS.get(item["id"], item["reviewer_question"])

    doc.setdefault("corrections", []).append({
        "at": "2026-09-29",
        "finding": "Successor review finding 1 and 2: corrected field values coexisted with unchanged, "
                   "contradictory proposal objects and stale reviewer questions, so two specifications were active "
                   "at once; and six APPLY_READY fields still contained undecided alternatives.",
        "correction": "field_values is now the single current representation. proposal.value is generated from it, "
                      "conditions are the union of the fields' dependencies, the original objects are archived as "
                      "superseded_proposal, and reviewer questions are regenerated. Fields whose value still "
                      "offered alternatives were demoted to CONDITIONAL, EXP03's inherited dependencies recorded, "
                      "and scientific-judgement fields rerouted to BLOCKED_HUMAN while keeping the validator owner.",
        "field_changes": changes,
    })
    path.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps({"fields_changed": len(changes), "changes": changes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
