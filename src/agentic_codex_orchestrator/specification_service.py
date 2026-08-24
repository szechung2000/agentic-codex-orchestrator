from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .models import Approval, Event, RunState, Specification, utc_now
from .persistence import JSONLAuditLog, SQLiteStore


REQUIRED_SECTIONS = ("goal", "scope", "acceptance_criteria", "constraints")


class SpecificationValidationError(ValueError):
    pass


class ApprovalRequiredError(PermissionError):
    pass


def _canonical_content(content: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    normalized = dict(content)
    missing = [section for section in REQUIRED_SECTIONS if not normalized.get(section)]
    if missing:
        raise SpecificationValidationError(
            "Missing required specification sections: " + ", ".join(missing)
        )
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return normalized, hashlib.sha256(encoded).hexdigest()


class SpecificationService:
    def __init__(self, store: SQLiteStore, audit_log_path: str | Path) -> None:
        self.store = store
        self.audit_log = JSONLAuditLog(audit_log_path)

    def create_revision(
        self, run_id: str, content: Mapping[str, Any], created_by: str
    ) -> Specification:
        normalized, digest = _canonical_content(content)
        now = utc_now()
        with self.store.transaction() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise KeyError(f"Unknown run: {run_id}")
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM specifications WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            specification = Specification(
                specification_id=str(uuid4()),
                run_id=run_id,
                version=version,
                content=normalized,
                content_sha256=digest,
                created_by=created_by,
                created_at=now,
            )
            connection.execute(
                "INSERT INTO specifications VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    specification.specification_id,
                    run_id,
                    version,
                    json.dumps(normalized, sort_keys=True, separators=(",", ":")),
                    digest,
                    created_by,
                    now,
                ),
            )
            self.store.set_run_state(connection, run_id, RunState.SPECIFICATION_PENDING)
            event = Event(
                event_id=str(uuid4()),
                run_id=run_id,
                sequence=self.store.next_sequence(connection, run_id),
                event_type="specification.revision_created",
                occurred_at=now,
                payload={
                    "specification_id": specification.specification_id,
                    "version": version,
                    "content_sha256": digest,
                },
            )
            self.store.append_event(connection, event)
            self.audit_log.append(event)
        return specification

    def approve(self, run_id: str, version: int, approved_by: str) -> Approval:
        now = utc_now()
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM specifications WHERE run_id = ? AND version = ?",
                (run_id, version),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown specification version {version} for run {run_id}")
            latest = connection.execute(
                "SELECT MAX(version) FROM specifications WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            if version != latest:
                raise SpecificationValidationError("Only the latest specification revision can be approved")
            approval = Approval(
                approval_id=str(uuid4()),
                run_id=run_id,
                specification_id=row["specification_id"],
                specification_version=version,
                approved_by=approved_by,
                approved_at=now,
            )
            connection.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?)",
                (
                    approval.approval_id,
                    run_id,
                    approval.specification_id,
                    version,
                    approved_by,
                    now,
                ),
            )
            self.store.set_run_state(connection, run_id, RunState.SPECIFICATION_APPROVED)
            event = Event(
                event_id=str(uuid4()),
                run_id=run_id,
                sequence=self.store.next_sequence(connection, run_id),
                event_type="specification.approved",
                occurred_at=now,
                payload={
                    "approval_id": approval.approval_id,
                    "specification_id": approval.specification_id,
                    "version": version,
                    "approved_by": approved_by,
                },
            )
            self.store.append_event(connection, event)
            self.audit_log.append(event)
        return approval

    def assert_dispatch_allowed(self, run_id: str, specification_version: int) -> None:
        with self.store.connect() as connection:
            latest = connection.execute(
                "SELECT MAX(version) FROM specifications WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            approved = connection.execute(
                "SELECT 1 FROM approvals WHERE run_id = ? AND specification_version = ?",
                (run_id, specification_version),
            ).fetchone()
        if latest != specification_version or approved is None:
            raise ApprovalRequiredError(
                "Dispatch requires explicit approval of the current specification version"
            )
