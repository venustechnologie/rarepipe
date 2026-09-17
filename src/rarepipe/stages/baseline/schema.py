"""JSON Schema export for Stage 03 artifacts (committed to schemas/, drift-tested)."""

from __future__ import annotations

import json

from rarepipe.stages.baseline import model


def schema_json() -> str:
    schema = model.RawCandidateSet.model_json_schema(by_alias=True, mode="serialization")
    schema["title"] = "RawCandidateSet"
    schema["$id"] = f"https://rarepipe.local/schemas/raw_candidate_set/{model.SCHEMA_VERSION}.json"
    schema["description"] = (f"RawCandidateSet v{model.SCHEMA_VERSION} — output of the baseline_analysis stage. "
                             "Records what an external solver reported under declared profiles; not a diagnosis. "
                             "Properties carrying `restricted: true` are populated only in the private artifact.")
    return json.dumps(schema, indent=2) + "\n"
