"""Build the M5 gap register from the real `prospective validate --json` output.

Every source gap record is copied from the validator, with its own field path, owner and reason.
Work packages group them by the decision that resolves them; no gap is invented and none is dropped.
"""

import json
import pathlib

W = pathlib.Path("/Volumes/Lexar/rarepipe_work/MVA_001/m5_packet")
v = json.loads((W / "validator_output.json").read_text())
gaps = v["scientific_readiness"]

PACKAGES = [
    ("WP_001", "EXP01 functional endpoint methods and validity criteria",
     lambda g: g["object_ref"].startswith("E01_") and g["field"] in ("method", "validity_criteria"),
     "assay_scientist", "PROPOSED", "one assay/validity choice per endpoint, recommended from retrieved methods"),
    ("WP_002", "EXP02 mechanism and function endpoint methods and validity criteria",
     lambda g: g["object_ref"].startswith("E02_") and g["field"] in ("method", "validity_criteria"),
     "assay_scientist", "PROPOSED", "one assay/validity choice per endpoint; mechanistic readouts kept separate"),
    ("WP_003", "Effect criteria and threshold versions for every required endpoint",
     lambda g: g["field"] in ("effect_criterion", "threshold_version"),
     "assay_scientist", "BLOCKED_ON_EVIDENCE",
     "a single pilot estimating between-preparation variance and baseline event rates resolves all of these"),
    ("WP_004", "Analysis specification for EXP01, EXP02 and EXP03 (PRD §8.4)",
     lambda g: g["field"].startswith("analysis."),
     "statistician", "PROPOSED",
     "one estimand and experimental-unit definition drives most fields; the meaningful-effect field depends on WP_003"),
    ("WP_005", "Model availability, permitted use and laboratory feasibility",
     lambda g: g["field"] in ("feasibility",) or g["field"].startswith("model_requirements"),
     "research_operations", "BLOCKED_ON_EVIDENCE",
     "requires an owner's confirmation; no publication or inference can establish present availability"),
    ("WP_006", "Result-availability declaration",
     lambda g: g["field"] == "outcome_availability",
     "research_operations", "BLOCKED_ON_EVIDENCE",
     "requires authentic timing records from the operator or investigator"),
    ("WP_007", "Human reviews of the exact plan content",
     lambda g: g["field"].startswith("reviews."),
     "scientific_lead", "HUMAN_DECISION_ONLY",
     "must come through the project's review workflow; an agent cannot supply it"),
]

packages, seen = [], set()
for pid, title, match, owner, state, note in PACKAGES:
    members = [g for g in gaps if match(g)]
    seen |= {g["gap_id"] for g in members}
    packages.append({
        "id": pid, "title": title, "coordinating_owner": owner, "state": state,
        "source_gap_ids": sorted(g["gap_id"] for g in members), "source_gap_count": len(members),
        "shared_dependency": note, "proposal_file": "proposals.json",
    })
unassigned = [g["gap_id"] for g in gaps if g["gap_id"] not in seen]

register = {
    "schema_version": "1.0",
    "document_type": "M5_GAP_REGISTER",
    "source_validator_artifact": "m5_packet/validator_output.json (rarepipe prospective validate --json, "
                                 "run locally 2026-09-28 against the plan store on the controlled drive)",
    "source_plan_version": v["plan_version"],
    "source_plan_content_digest": v["plan_content_digest"],
    "source_baseline": v["baseline"],
    "plan_lifecycle": v["lifecycle"],
    "reported_gap_count": len(gaps),
    "inspected_gap_count": len(gaps),
    "structural_errors": v["structural"],
    "provenance_blockers": v["provenance"],
    "policy_blockers": v["policy"],
    "source_gap_records": gaps,
    "work_packages": packages,
    "unassigned_gap_ids": unassigned,
    "progress": {
        "gaps_inspected": len(gaps),
        "items_researched": 7,
        "proposals_drafted": 7,
        "ready_for_human_review": 0,
        "externally_confirmed_facts": 0,
        "human_accepted_plan_fields": 0,
    },
    "instructions": "Counts are filled from proposals.json after the checker runs. An AI proposal is progress, "
                    "never a closed scientific gate; the real validator still reports these gaps until a human "
                    "accepts edits through the project's versioned workflow.",
}
(W / "gap_register.json").write_text(json.dumps(register, indent=2) + "\n")
print("gaps:", len(gaps), "assigned:", len(seen), "unassigned:", unassigned)
for p in packages:
    print(f"  {p['id']} {p['source_gap_count']:3d}  {p['state']:22} {p['title']}")
