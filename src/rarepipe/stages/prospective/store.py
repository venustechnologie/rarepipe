"""Canonical digests and the immutable, versioned plan store (PRD §13.1, §14, §17).

Layout under a workspace directory::

    <workspace>/<plan_id>/
        versions/<version_id>.json     immutable (exclusive create, then read-only)
        HEAD                           the active version id, replaced atomically
        observations/<observation_id>.json
        decisions/<decision_id>.json   the proposal; reviews are separate events
        reviews/<review_id>.json
        idempotency.json               idempotency key → result
        audit.jsonl                    what happened, never the sensitive payload

A frozen version is never edited. Any change is a successor with a parent version and a reason. A
write that names a stale parent is refused with a diff (no last-write-wins), and a failed write never
moves HEAD.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from rarepipe.core.artifacts import utc_now
from rarepipe.stages.prospective.model import CANONICALIZATION, DecisionRecord, Observation, ProspectivePlan


class VersionConflict(RuntimeError):
    def __init__(self, message: str, diff: list[str] | None = None):
        super().__init__(message)
        self.diff = diff or []


class ImmutableError(RuntimeError):
    pass


def canonical_bytes(obj: BaseModel | dict | list) -> bytes:
    """rarepipe-canonical-json-v1 (see model.CANONICALIZATION). Units and full numbers stay in the content."""
    data = obj.model_dump(mode="json", by_alias=True) if isinstance(obj, BaseModel) else obj
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_digest(obj: BaseModel | dict, exclude: set[str] = frozenset()) -> str:
    data = obj.model_dump(mode="json", by_alias=True) if isinstance(obj, BaseModel) else dict(obj)
    for key in exclude:
        data.pop(key, None)
    return "sha256:" + hashlib.sha256(canonical_bytes(data)).hexdigest()


PLAN_DIGEST_EXCLUDE = {"content_digest", "version_id", "parent_version", "change_reason", "change_kind", "reviews",
                       "lifecycle"}


def plan_digest(plan: ProspectivePlan) -> str:
    """Scientific content only. Lineage, lifecycle and the reviews themselves sit beside it, so a review can
    name the exact content it approved and any scientific edit invalidates it."""
    return content_digest(plan, PLAN_DIGEST_EXCLUDE)


def review_digest(plan: ProspectivePlan) -> str:
    """What a freeze review approves: the scientific content, without the timing declaration recorded at freeze."""
    return content_digest(plan, PLAN_DIGEST_EXCLUDE | {"outcome_availability", "temporal_status"})


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _write_once(path: Path, data: bytes) -> None:
    """Create-only. A hard link publishes the complete file atomically; filesystems without links (the
    exFAT/NTFS case drive) fall back to an exclusive create, which still never replaces a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    try:
        os.link(tmp, path)
    except FileExistsError as exc:
        raise ImmutableError(f"{path.name} already exists and is immutable") from exc
    except OSError:
        try:
            with path.open("xb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
        except FileExistsError as exc:
            raise ImmutableError(f"{path.name} already exists and is immutable") from exc
    finally:
        Path(tmp).unlink(missing_ok=True)
    os.chmod(path, 0o444)


def _pretty(obj: BaseModel | dict) -> bytes:
    data = obj.model_dump(mode="json", by_alias=True) if isinstance(obj, BaseModel) else obj
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class PlanStore:
    def __init__(self, workspace: Path, plan_id: str):
        self.root = workspace / plan_id
        self.plan_id = plan_id

    # ── versions ─────────────────────────────────────────────────────────────
    def head(self) -> str | None:
        head = self.root / "HEAD"
        return head.read_text().strip() if head.exists() else None

    def versions(self) -> list[str]:
        folder = self.root / "versions"
        return sorted(p.stem for p in folder.glob("*.json") if not p.name.startswith("._")) if folder.exists() else []

    def load(self, version_id: str | None = None) -> ProspectivePlan:
        version_id = version_id or self.head()
        if not version_id:
            raise FileNotFoundError(f"plan {self.plan_id} has no versions")
        return ProspectivePlan.model_validate_json((self.root / "versions" / f"{version_id}.json").read_text())

    def commit(self, plan: ProspectivePlan, *, expected_parent: str | None, reason: str, kind: str,
               actor: str, idempotency_key: str | None = None) -> ProspectivePlan:
        """Write a new immutable version. The caller names the version it edited; a stale name is a conflict."""
        if idempotency_key:
            prior = self._idempotent(idempotency_key)
            if prior:
                return self.load(prior)
        current = self.head()
        if current != expected_parent:
            diff = []
            if current:
                from rarepipe.stages.prospective.diff import diff_plans
                diff = [c.render() for c in diff_plans(self.load(current), plan)]
            raise VersionConflict(f"stale edit: the plan is at {current}, the edit was made against "
                                  f"{expected_parent}. Reconcile explicitly; nothing was written.", diff)
        plan = plan.model_copy(deep=True)
        plan.parent_version = current
        plan.change_reason = reason
        plan.change_kind = kind  # type: ignore[assignment]
        plan.content_digest = plan_digest(plan)
        number = len(self.versions()) + 1
        plan.version_id = f"{self.plan_id}@{number:04d}-{plan.content_digest.split(':')[1][:8]}"
        _write_once(self.root / "versions" / f"{plan.version_id}.json", _pretty(plan))
        _atomic_write(self.root / "HEAD", (plan.version_id + "\n").encode())
        if idempotency_key:
            self._remember(idempotency_key, plan.version_id)
        self.audit("commit", actor=actor, version=plan.version_id, parent=current, kind=kind, reason=reason)
        return plan

    # ── observations, decisions, reviews ─────────────────────────────────────
    def put_observation(self, obs: Observation) -> tuple[Observation, bool]:
        """Returns (observation, created). Identical evidence keeps one identity (AT15)."""
        path = self.root / "observations" / f"{obs.observation_id}.json"
        if path.exists():
            return Observation.model_validate_json(path.read_text()), False
        _write_once(path, _pretty(obs))
        return obs, True

    def observations(self) -> list[Observation]:
        folder = self.root / "observations"
        return [Observation.model_validate_json(p.read_text()) for p in sorted(folder.glob("OBS_*.json"))] \
            if folder.exists() else []

    def put_decision(self, record: DecisionRecord) -> None:
        path = self.root / "decisions" / f"{record.decision_id}.json"
        if path.exists():
            existing = DecisionRecord.model_validate_json(path.read_text())
            if existing.review_version >= record.review_version:
                raise VersionConflict(f"{record.decision_id} is already at review version {existing.review_version}")
            os.chmod(path, 0o644)
            _atomic_write(path, _pretty(record))
        else:
            _atomic_write(path, _pretty(record))
        os.chmod(path, 0o444)

    def load_decision(self, decision_id: str) -> DecisionRecord:
        return DecisionRecord.model_validate_json((self.root / "decisions" / f"{decision_id}.json").read_text())

    def decisions(self) -> list[DecisionRecord]:
        folder = self.root / "decisions"
        return [DecisionRecord.model_validate_json(p.read_text()) for p in sorted(folder.glob("DR_*.json"))] \
            if folder.exists() else []

    def execution(self) -> dict:
        path = self.root / "execution.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def set_execution(self, experiment_id: str, state: str, observation_id: str | None = None) -> None:
        """Execution state lives beside the frozen plan, never inside it (§14)."""
        data = self.execution()
        entry = data.setdefault(experiment_id, {"state": "NOT_STARTED", "observations": []})
        entry["state"] = state
        if observation_id and observation_id not in entry["observations"]:
            entry["observations"].append(observation_id)
        _atomic_write(self.root / "execution.json", json.dumps(data, sort_keys=True, indent=2).encode())

    def put_review(self, review) -> None:
        _write_once(self.root / "reviews" / f"{review.review_id}.json", _pretty(review))

    # ── bookkeeping ──────────────────────────────────────────────────────────
    def audit(self, event: str, **fields) -> None:
        """Operational record only: ids, kinds, reasons. Never observation values or private refs."""
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"at": utc_now().isoformat(), "event": event, **fields}, sort_keys=True)
        with (self.root / "audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def audit_events(self) -> list[dict]:
        path = self.root / "audit.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def _idempotent(self, key: str) -> str | None:
        path = self.root / "idempotency.json"
        return json.loads(path.read_text()).get(key) if path.exists() else None

    def _remember(self, key: str, value: str) -> None:
        path = self.root / "idempotency.json"
        data = json.loads(path.read_text()) if path.exists() else {}
        data[key] = value
        _atomic_write(path, json.dumps(data, sort_keys=True, indent=2).encode())


__all__ = ["CANONICALIZATION", "ImmutableError", "PlanStore", "VersionConflict", "canonical_bytes",
           "content_digest", "plan_digest"]
