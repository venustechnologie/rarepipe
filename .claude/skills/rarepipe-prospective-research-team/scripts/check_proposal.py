#!/usr/bin/env python3
"""Check an agent handoff; never approve science, identity or a native plan.

Standard library only. Reads one JSON file and writes a bounded report to stdout.
No network access and no changes to input files or plan stores.
"""
import argparse
import json
from pathlib import Path

STATUSES = {"DRAFT_PROPOSAL", "READY_FOR_HUMAN_REVIEW", "NEEDS_EXTERNAL_EVIDENCE", "NEEDS_DESIGN_DECISION"}
BASIS = {"EVIDENCE_DERIVED", "DESIGN_CHOICE", "MODELLING_ASSUMPTION", "UNVERIFIED_PRIOR", "UNRESOLVED"}
RETRIEVAL = {"STORED_FULL_TEXT", "STORED_ABSTRACT", "STORED_SUPPLEMENT", "VERIFIED_PROJECT_ARTIFACT", "NOT_RETRIEVED"}

def check(document):
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)
    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())
    def strings(value):
        return isinstance(value, list) and all(nonempty(x) for x in value)
    if not isinstance(document, dict):
        return ["document must be an object"]
    need(document.get("schema_version") == "1.0", "schema_version must be 1.0")
    need(document.get("document_type") == "M5_AGENT_PROPOSAL", "not an agent proposal")
    producer = document.get("producer")
    need(isinstance(producer, dict), "producer must be an object")
    if isinstance(producer, dict):
        need(producer.get("actor_type") == "AGENT", "producer must remain AGENT")
        need(nonempty(producer.get("role")), "producer role is required")
    baseline = document.get("baseline")
    need(isinstance(baseline, dict), "baseline must be an object")
    if isinstance(baseline, dict):
        need(strings(baseline.get("limitations")), "baseline limitations must be a string list")
    scope = document.get("scope")
    need(isinstance(scope, dict), "scope must be an object")
    if isinstance(scope, dict):
        need(scope.get("data_boundary") in {"PUBLIC_ONLY", "LOCAL_PRIVATE_APPROVED"}, "unknown data boundary")
        if scope.get("data_boundary") == "LOCAL_PRIVATE_APPROVED":
            need(nonempty(scope.get("authorization_ref")), "private boundary needs an authorization reference")
            need(scope.get("runner_authorization_verified") is True, "private boundary needs runner-authorization declaration")
    actions = document.get("actions")
    need(isinstance(actions, dict), "actions must be an object")
    if isinstance(actions, dict):
        for key in ["automatic_external_action", "clinical_action", "real_plan_freeze", "human_signoff_created"]:
            need(actions.get(key) is False, key + " must be false")
    need(document.get("new_human_reviews") == [], "agent proposals must not create human reviews")
    sources = document.get("sources")
    need(isinstance(sources, list), "sources must be a list")
    source_map = {}
    if isinstance(sources, list):
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"source {index} must be an object")
                continue
            sid = source.get("id")
            if not nonempty(sid):
                errors.append(f"source {index} needs an ID")
                continue
            need(sid not in source_map, "duplicate source ID: " + sid)
            source_map[sid] = source
            for field in ["locator", "provenance_note", "scope", "source_location"]:
                need(nonempty(source.get(field)), sid + " needs " + field)
            need(source.get("retrieval_status") in RETRIEVAL, sid + " has invalid retrieval status")
    items = document.get("items")
    need(isinstance(items, list) and bool(items), "items must be a nonempty list")
    item_ids = set()
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"item {index} must be an object")
                continue
            label = item.get("id")
            if not nonempty(label):
                errors.append(f"item {index} needs an ID")
                continue
            need(label not in item_ids, "duplicate item ID: " + label)
            item_ids.add(label)
            need(item.get("status") in STATUSES, label + " has invalid status")
            need(strings(item.get("source_gap_ids")), label + " needs a gap-ID list")
            need(item.get("source_gap_mapping") in {"VERIFIED", "UNVERIFIED"}, label + " has invalid gap-mapping status")
            if item.get("source_gap_mapping") == "VERIFIED":
                need(bool(item.get("source_gap_ids")), label + " verified mapping needs real gap IDs")
                need(nonempty(item.get("field_path")), label + " verified mapping needs a field path")
                need(isinstance(baseline, dict) and baseline.get("plan_version") is not None and nonempty(baseline.get("plan_content_hash")), label + " verified mapping needs the inspected plan version/hash")
            for field in ["question", "reviewer_question", "next_action"]:
                need(nonempty(item.get(field)), label + " needs " + field)
            need(strings(item.get("required_reviewer_roles")) and bool(item.get("required_reviewer_roles")), label + " needs reviewer roles")
            proposal, basis = item.get("proposal"), item.get("basis")
            need(isinstance(proposal, dict), label + " proposal must be an object")
            need(isinstance(basis, dict), label + " basis must be an object")
            if not isinstance(proposal, dict) or not isinstance(basis, dict):
                continue
            need("value" in proposal, label + " needs an explicit value or null")
            need(nonempty(proposal.get("rationale")), label + " needs rationale")
            for field in ["alternatives", "conditions", "limitations"]:
                need(strings(proposal.get(field)), label + " needs a " + field + " list")
            need(basis.get("kind") in BASIS, label + " has invalid basis")
            for field in ["source_refs", "calculation_refs", "assumptions"]:
                need(strings(basis.get(field)), label + " needs a " + field + " list")
            refs = basis.get("source_refs")
            if strings(refs):
                need(all(ref in source_map for ref in refs), label + " has an unresolved source reference")
                if basis.get("kind") == "EVIDENCE_DERIVED":
                    need(bool(refs), label + " evidence-derived proposal needs retrieved sources")
                    need(all(ref in source_map and source_map[ref].get("retrieval_status") in RETRIEVAL - {"NOT_RETRIEVED"} for ref in refs), label + " evidence-derived basis cites unretrieved material")
            if basis.get("kind") == "MODELLING_ASSUMPTION":
                need(bool(basis.get("assumptions")), label + " modelling basis needs explicit assumptions")
            if item.get("status") == "READY_FOR_HUMAN_REVIEW":
                need(proposal.get("value") is not None, label + " ready proposal needs a recommendation")
                need(basis.get("kind") not in {"UNRESOLVED", "UNVERIFIED_PRIOR"}, label + " unresolved basis cannot be ready")
                need(bool(proposal.get("alternatives")), label + " needs alternatives or an explained absence")
                need(bool(proposal.get("limitations")), label + " needs explicit limits")
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.proposal.read_text(encoding="utf-8"))
        errors = check(document)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "INVALID_HANDOFF", "error": str(exc)}))
        return 1
    print(json.dumps({
        "status": "HANDOFF_FORMAT_OK" if not errors else "INVALID_HANDOFF",
        "errors": errors,
        "scientific_readiness_assessed": False,
        "source_claims_verified": False,
        "human_identity_authenticated": False,
        "native_rarepipe_validation_run": False,
    }, indent=2))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
