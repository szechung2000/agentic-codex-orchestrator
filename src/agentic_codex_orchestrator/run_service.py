from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .git_repository import preflight_repository
from .models import Event, Run, RunState, utc_now
from .persistence import JSONLAuditLog, SQLiteStore


class RunService:
    def __init__(self, store: SQLiteStore, audit_log_path: str | Path) -> None:
        self.store = store
        self.audit_log = JSONLAuditLog(audit_log_path)

    def create_run(self, repository_path: str | Path, base_ref: str = "HEAD") -> Run:
        snapshot = preflight_repository(repository_path, base_ref)
        created_at = utc_now()
        run = Run(
            run_id=str(uuid4()),
            repository_path=str(snapshot.root),
            base_commit=snapshot.base_commit,
            state=RunState.SPECIFICATION_PENDING,
            created_at=created_at,
        )
        event = Event(
            event_id=str(uuid4()),
            run_id=run.run_id,
            sequence=1,
            event_type="run.created",
            occurred_at=created_at,
            payload={
                "repository_path": run.repository_path,
                "base_commit": run.base_commit,
                "state": run.state.value,
            },
        )
        with self.store.transaction() as connection:
            self.store.insert_run(connection, run)
            self.store.append_event(connection, event)
            self.audit_log.append(event)
        return run

