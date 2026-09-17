"""Schema-driven redaction shared by stages from Stage 02 on.

(Stage 01 carries its own frozen copy of the same mechanism in stages/intake.)
Fields declared with ``restricted()`` exist only in a stage's private artifact;
``clear_restricted`` resets every one of them recursively.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

_R = {"restricted": True}


def restricted(default=None, **kw):
    if default is list:
        return Field(default_factory=list, json_schema_extra=_R, **kw)
    if default is dict:
        return Field(default_factory=dict, json_schema_extra=_R, **kw)
    return Field(default=default, json_schema_extra=_R, **kw)


def clear_restricted(obj) -> None:
    if isinstance(obj, BaseModel):
        for name, info in type(obj).model_fields.items():
            extra = info.json_schema_extra
            if isinstance(extra, dict) and extra.get("restricted"):
                setattr(obj, name, info.get_default(call_default_factory=True))
            else:
                clear_restricted(getattr(obj, name))
    elif isinstance(obj, list):
        for item in obj:
            clear_restricted(item)
    elif isinstance(obj, dict):
        for item in obj.values():
            clear_restricted(item)
