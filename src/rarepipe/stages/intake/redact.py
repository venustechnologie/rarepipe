"""Private → sanitized manifest.

Driven entirely by the schema: every field declared with ``restricted()`` is
reset to its empty default, recursively. Adding a new sensitive field means
tagging it in the schema — there is no second list to keep in sync.
"""

from __future__ import annotations

from pydantic import BaseModel

from rarepipe.stages.intake.manifest import CaseManifest, Redaction

SANITIZED_NOTE = (
    "Sanitized: local paths, filenames, source sample labels, read-group identifiers, raw header claims, "
    "HPO term lists and configuration paths are removed. Internal aliases (ASSET_*, SAMPLE_*) remain. "
    "This is NOT anonymous: it still describes one real individual's case structure."
)
PRIVATE_NOTE = "Private: contains local paths and source identifiers required for execution. Keep inside the controlled environment."


def _clear(obj) -> None:
    if isinstance(obj, BaseModel):
        for name, info in type(obj).model_fields.items():
            extra = info.json_schema_extra
            if isinstance(extra, dict) and extra.get("restricted"):
                setattr(obj, name, info.get_default(call_default_factory=True))
            else:
                _clear(getattr(obj, name))
    elif isinstance(obj, list):
        for item in obj:
            _clear(item)
    elif isinstance(obj, dict):
        for item in obj.values():
            _clear(item)


def sanitize(manifest: CaseManifest) -> CaseManifest:
    clone = manifest.model_copy(deep=True)
    _clear(clone)
    clone.redaction = Redaction(visibility="sanitized", note=SANITIZED_NOTE)
    return clone
