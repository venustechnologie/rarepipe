"""JSON Schema for the Stage 05 artifacts."""

from __future__ import annotations

import json

from rarepipe.stages.track1.model import ExternalValidationResult, Track1SubmissionPackage


def schema_json(artifact: str = "track1_submission_package") -> str:
    model = Track1SubmissionPackage if artifact == "track1_submission_package" else ExternalValidationResult
    return json.dumps(model.model_json_schema(by_alias=True), indent=2) + "\n"
