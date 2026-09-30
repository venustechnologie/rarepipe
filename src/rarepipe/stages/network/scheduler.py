"""Validated waiting tasks and UTC timers; reading due work never fires a follow-up."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from rarepipe.stages.network.eventlog import Reason, utc
from rarepipe.stages.network.model import ImmutableModel, Request, RequestState


class QuietHours(ImmutableModel):
    timezone: str
    start: time
    end: time

    @model_validator(mode="after")
    def _valid(self):
        ZoneInfo(self.timezone)
        if self.start == self.end or self.start.tzinfo or self.end.tzinfo:
            raise ValueError("quiet hours require distinct local wall times")
        return self

    def contains(self, when: datetime) -> bool:
        local = utc(when).astimezone(ZoneInfo(self.timezone)).time()
        if self.start < self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end

    def next_allowed(self, when: datetime) -> datetime:
        value = utc(when)
        # Walking UTC handles missing/repeated wall times at DST boundaries.
        while self.contains(value):
            value += timedelta(minutes=1)
        return value


def parse_quiet_hours(value: str | None) -> QuietHours | None:
    """Explicit wire format: 'Europe/Berlin 22:00-08:00'; invalid config blocks."""
    if value is None:
        return None
    zone, hours = value.split()
    start, end = hours.split("-")
    return QuietHours(timezone=zone, start=time.fromisoformat(start), end=time.fromisoformat(end))


class WaitingTask(Request):
    """T04's persisted Request subtype; raw T02 requests are validated on entry."""

    schedule_state: Literal["SCHEDULED", "UNSCHEDULED"] = "UNSCHEDULED"
    followup_count: int = Field(0, ge=0)
    max_followups: int | None = Field(None, ge=0)
    followup_reason: Literal[Reason.FOLLOWUP_REQUIRED] | None = None
    unscheduled_reason: Reason | None = None

    @field_validator("next_trigger")
    @classmethod
    def _utc(cls, value):
        return utc(value) if value is not None else None

    @model_validator(mode="after")
    def _waiting(self):
        if self.state is RequestState.WAITING:
            if self.schedule_state == "SCHEDULED":
                if self.owner is None or not self.owner.identity.strip() or self.next_trigger is None:
                    raise ValueError("scheduled waiting requires an owner and next trigger")
                if self.unscheduled_reason is not None:
                    raise ValueError("scheduled task cannot have an unscheduled reason")
            elif self.unscheduled_reason is None or self.next_trigger is not None:
                raise ValueError("UNSCHEDULED waiting requires a visible reason and no trigger")
        if self.max_followups is not None and self.followup_count > self.max_followups:
            raise ValueError("follow-up bound exceeded")
        return self


class Scheduler:
    def __init__(self, outbox):
        self.outbox = outbox

    def due(self, now: datetime) -> tuple[WaitingTask, ...]:
        now = utc(now)
        if self.outbox.campaign().status != "ACTIVE":
            return ()
        return tuple(task for task in self.outbox.tasks()
                     if task.state is RequestState.WAITING and task.schedule_state == "SCHEDULED"
                     and task.next_trigger <= now)

    def claim(self, task_id: str, *, actor, now: datetime) -> WaitingTask:
        """Consume once before handing control to an operator; this does not send."""
        with self.outbox.log.writer():
            self.outbox.require_active()
            task = self.outbox.load(task_id)
            if task.state is not RequestState.WAITING or task.next_trigger is None or task.next_trigger > utc(now):
                raise ValueError("timer is not due")
            task = self.outbox.successor(task, schedule_state="UNSCHEDULED", next_trigger=None,
                                        unscheduled_reason=Reason.TIMER_CLAIMED)
            self.outbox.record(task, Reason.TIMER_CLAIMED, actor, now, kind="timer")
            return task
