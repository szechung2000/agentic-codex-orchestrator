from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunState(StrEnum):
    CREATED = "created"
    SPECIFICATION_PENDING = "specification_pending"
    SPECIFICATION_APPROVED = "specification_approved"
    WORKER_RUNNING = "worker_running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Run:
    run_id: str
    repository_path: str
    base_commit: str
    state: RunState
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    run_id: str
    sequence: int
    event_type: str
    occurred_at: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Specification:
    specification_id: str
    run_id: str
    version: int
    content: dict[str, Any]
    content_sha256: str
    created_by: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    run_id: str
    specification_id: str
    specification_version: int
    approved_by: str
    approved_at: str
