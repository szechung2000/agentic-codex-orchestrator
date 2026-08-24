from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class WorkerStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class WorkerTask:
    run_id: str
    worker_id: str
    specification_version: int
    worktree_path: str
    base_commit: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    allowed_write_paths: tuple[str, ...] = (".",)
    timeout_seconds: int = 900

    def prompt(self) -> str:
        criteria = "\n".join(f"- {item}" for item in self.acceptance_criteria)
        paths = ", ".join(self.allowed_write_paths)
        return (
            f"Run: {self.run_id}\nWorker: {self.worker_id}\n"
            f"Approved specification version: {self.specification_version}\n\n"
            f"Objective:\n{self.objective}\n\nAcceptance criteria:\n{criteria}\n\n"
            f"Allowed write paths: {paths}\n"
            "Implement the objective in this worktree, run focused tests, and return the required JSON result."
        )


@dataclass(frozen=True, slots=True)
class WorkerResult:
    status: WorkerStatus
    summary: str
    changed_files: tuple[str, ...]
    tests: tuple[str, ...]
    final_message: str
    return_code: int
    events: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


WORKER_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["status", "summary", "changed_files", "tests"],
    "additionalProperties": False,
    "properties": {
        "status": {"const": "succeeded"},
        "summary": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "tests": {"type": "array", "items": {"type": "string"}},
    },
}

