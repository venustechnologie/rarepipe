"""JSON Schema export for CaseManifest (committed to schemas/, drift-tested)."""

from __future__ import annotations

import json

from rarepipe.stages.intake.manifest import SCHEMA_VERSION, CaseManifest


def schema_json() -> str:
    schema = CaseManifest.model_json_schema(by_alias=True, mode="serialization")
    schema["$id"] = f"https://rarepipe.local/schemas/case_manifest/{SCHEMA_VERSION}.json"
    schema["title"] = "CaseManifest"
    schema["description"] = (
        f"CaseManifest v{SCHEMA_VERSION} — output of the case_intake stage. "
        "Properties carrying `restricted: true` are populated only in the private manifest."
    )
    return json.dumps(schema, indent=2) + "\n"
