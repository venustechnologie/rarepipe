"""JSON Schema for the Stage 06 artifact."""

from __future__ import annotations

import json

from rarepipe.stages.mechanism.model import MechanismDossier


def schema_json() -> str:
    return json.dumps(MechanismDossier.model_json_schema(by_alias=True), indent=2) + "\n"
