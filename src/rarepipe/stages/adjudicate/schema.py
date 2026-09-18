"""JSON Schema export for the AdjudicatedHypothesis artifact."""

from __future__ import annotations

import json

from rarepipe.stages.adjudicate import model


def schema_json() -> str:
    schema = model.AdjudicatedHypothesis.model_json_schema(by_alias=True, mode="serialization")
    schema["title"] = "AdjudicatedHypothesis"
    schema["$id"] = f"https://rarepipe.local/schemas/adjudicated_hypothesis/{model.SCHEMA_VERSION}.json"
    schema["description"] = (f"AdjudicatedHypothesis v{model.SCHEMA_VERSION} — evidence dossier for one causal "
                             "hypothesis. Not a diagnosis, not a clinical variant classification, not a ranking. "
                             "Properties carrying `restricted: true` are populated only in the private artifact.")
    return json.dumps(schema, indent=2) + "\n"
