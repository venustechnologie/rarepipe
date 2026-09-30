"""Immutable campaign journal. Events contain opaque references, never request payloads.

The numbered event files are the authoritative append-only audit log. HEAD is only a
recoverable cache. An abandoned writer lock fails closed and requires operator recovery;
never steal it on a timeout, because a slow writer could still dispatch.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from enum import StrEnum
import os
from pathlib import Path
from uuid import uuid4

from pydantic import Field, field_validator

from rarepipe.stages.network.model import ImmutableModel, Origin, RequestState
from rarepipe.stages.prospective.model import Actor
from rarepipe.stages.prospective.store import (
    _atomic_write, _write_once, canonical_bytes, content_digest,
)


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def opaque(value: str) -> str:
    """Digest covers the exact UTF-8 string wrapped as a canonical JSON value."""
    return content_digest({"value": value}).split(":", 1)[1]


class Reason(StrEnum):
    PREPARED = "PREPARED"
    READY = "READY"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    CONTACT_UNVERIFIED = "CONTACT_UNVERIFIED"
    DISPATCH_CLAIMED = "DISPATCH_CLAIMED"
    PROVIDER_ACCEPTED = "PROVIDER_ACCEPTED"
    DELIVERY_AMBIGUOUS = "DELIVERY_AMBIGUOUS"
    RECONCILED_SENT = "RECONCILED_SENT"
    RECONCILED_NOT_SENT = "RECONCILED_NOT_SENT"
    RECONCILED_UNKNOWN = "RECONCILED_UNKNOWN"
    DELIVERY_RECEIPT = "DELIVERY_RECEIPT"
    WAIT_SCHEDULED = "WAIT_SCHEDULED"
    OWNER_UNASSIGNED = "OWNER_UNASSIGNED"
    TRIGGER_UNSET = "TRIGGER_UNSET"
    TIMER_CLAIMED = "TIMER_CLAIMED"
    FOLLOWUP_REQUIRED = "FOLLOWUP_REQUIRED"
    RESPONSE_IMPORTED = "RESPONSE_IMPORTED"
    ASSESSMENT_RECORDED = "ASSESSMENT_RECORDED"
    WORK_COMPLETE = "WORK_COMPLETE"
    OPERATOR_PAUSE = "OPERATOR_PAUSE"
    OPERATOR_CANCEL = "OPERATOR_CANCEL"
    OPERATOR_RESUME = "OPERATOR_RESUME"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class Event(ImmutableModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sequence: int
    timestamp: datetime
    task_id: str
    previous_state: str | None
    new_state: str
    reason: Reason
    actor: str
    kind: str
    origin: Origin | None = None
    snapshot_ref: str
    previous_event: str | None = None
    digest_coverage: str = "all event fields except digest, canonical-json-v1"
    digest: str

    _utc = field_validator("timestamp")(utc)


class StoreBusy(RuntimeError):
    pass


class EventLog:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def writer(self):
        lock = self.root / ".writer"
        try:
            lock.mkdir()
        except FileExistsError:
            raise StoreBusy("campaign writer is busy or needs crash recovery") from None
        try:
            yield
        finally:
            lock.rmdir()

    def events(self) -> list[Event]:
        events = []
        for path in sorted((self.root / "events").glob("[0-9]*.json")):
            event = Event.model_validate_json(path.read_bytes())
            if (event.sequence != len(events) + 1
                    or event.previous_event != (events[-1].digest if events else None)
                    or content_digest(event, {"digest"}) != event.digest):
                raise ValueError("event journal integrity failure")
            events.append(event)
        return events

    def replay(self, task_id: str) -> tuple[Event, ...]:
        return tuple(event for event in self.events() if event.task_id == opaque(task_id))

    def snapshot(self, event: Event) -> dict:
        import json
        value = json.loads((self.root / "snapshots" / f"{event.snapshot_ref}.json").read_bytes())
        if content_digest(value).split(":", 1)[1] != event.snapshot_ref:
            raise ValueError("snapshot integrity failure")
        return value

    def append(self, **fields) -> Event:
        with self.writer():
            return self._append(**fields)

    def _append(self, *, task_id: str, previous_state: str | None, new_state: str,
               reason: Reason, actor: Actor, kind: str, snapshot: dict,
               origin: Origin | None, now: datetime) -> Event:
        """Internal transaction operation; caller must hold writer() for read/check/write."""
        reason = Reason(reason)
        if kind not in {"task", "campaign", "dispatch", "receipt", "reconciliation", "timer", "response"}:
            raise ValueError("unknown audit kind")
        events = self.events()
        valid_states = {state.value for state in RequestState} | {"ACTIVE", "CANCELLED"}
        if new_state not in valid_states or (previous_state is not None and previous_state not in valid_states):
            raise ValueError("unknown audit state")
        history = [event for event in events if event.task_id == opaque(task_id)]
        if previous_state != (history[-1].new_state if history else None):
            raise ValueError("stale event transition")
        reference = content_digest(snapshot).split(":", 1)[1]
        path = self.root / "snapshots" / f"{reference}.json"
        if not path.exists():
            _write_once(path, canonical_bytes(snapshot))
            self._sync(path)
        data = dict(id=str(uuid4()), sequence=len(events) + 1, timestamp=utc(now).isoformat(),
                    task_id=opaque(task_id), previous_state=previous_state, new_state=new_state,
                    reason=reason.value, actor=opaque(actor.identity), kind=kind,
                    origin=origin.value if origin else None, snapshot_ref=reference,
                    previous_event=events[-1].digest if events else None,
                    digest_coverage="all event fields except digest, canonical-json-v1")
        # Validate first, then digest the normalized serialization (UTC uses Z).
        event = Event(**data, digest="")
        data = event.model_dump(mode="json")
        data["digest"] = content_digest(event, {"digest"})
        event = Event(**data)
        path = self.root / "events" / f"{event.sequence:012d}.json"
        _write_once(path, canonical_bytes(event))
        self._sync(path)
        _atomic_write(self.root / "HEAD", event.id.encode())
        self._sync(self.root / "HEAD")
        return event

    @staticmethod
    def _sync(path: Path):
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        # Some removable filesystems reject directory fsync. File fsync still applies.
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
