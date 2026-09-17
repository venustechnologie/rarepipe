"""JSON Schema export for Stage 02 artifacts (committed to schemas/, drift-tested)."""

from __future__ import annotations

import json

from rarepipe.stages.normalize import assertions, model


def schema_json(artifact: str) -> str:
    if artifact == "normalized_case":
        schema = model.NormalizedCase.model_json_schema(by_alias=True, mode="serialization")
        schema["title"] = "NormalizedCase"
        schema["$id"] = f"https://rarepipe.local/schemas/normalized_case/{model.SCHEMA_VERSION}.json"
        schema["description"] = (f"NormalizedCase v{model.SCHEMA_VERSION} — output of the case_normalization stage. "
                                 "Properties carrying `restricted: true` are populated only in the private artifact.")
    elif artifact == "case_assertions":
        schema = assertions.CaseAssertions.model_json_schema(by_alias=True)
        schema["title"] = "CaseAssertions"
        schema["$id"] = f"https://rarepipe.local/schemas/case_assertions/{assertions.SCHEMA_VERSION}.json"
    else:
        raise ValueError(artifact)
    return json.dumps(schema, indent=2) + "\n"
