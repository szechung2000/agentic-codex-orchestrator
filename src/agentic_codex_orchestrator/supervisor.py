from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

from .models import Event, RunState, utc_now
from .persistence import JSONLAuditLog, SQLiteStore
from .specification_service import SpecificationService
from .worker_contracts import WorkerResult, WorkerStatus, WorkerTask
from .worker_runtime import WorkerRuntime
from .worktrees import WorktreeManager


class WorkerAlreadyRunningError(RuntimeError):
    pass


class Supervisor:
    def __init__(
        self,
        store: SQLiteStore,
        audit_log_path: str | Path,
        worktrees: WorktreeManager,
        runtime: WorkerRuntime,
    ) -> None:
        self.store = store
        self.audit_log = JSONLAuditLog(audit_log_path)
        self.specifications = SpecificationService(store, audit_log_path)
        self.worktrees = worktrees
        self.runtime = runtime
        self._dispatch_lock = threading.Lock()

    def _event(self, connection, run_id: str, event_type: str, payload: dict) -> None:
        event = Event(
            event_id=str(uuid4()),
            run_id=run_id,
            sequence=self.store.next_sequence(connection, run_id),
            event_type=event_type,
            occurred_at=utc_now(),
            payload=payload,
        )
        self.store.append_event(connection, event)
        self.audit_log.append(event)

    def dispatch(
        self,
        run_id: str,
        specification_version: int,
        objective: str,
        acceptance_criteria: tuple[str, ...],
        allowed_write_paths: tuple[str, ...] = (".",),
        timeout_seconds: int = 900,
    ) -> tuple[str, WorkerResult]:
        if not self._dispatch_lock.acquire(blocking=False):
            raise WorkerAlreadyRunningError("Sprint 0 permits only one active implementation worker")
        try:
            self.specifications.assert_dispatch_allowed(run_id, specification_version)
            run = self.store.get_run(run_id)
            if run is None:
                raise KeyError(f"Unknown run: {run_id}")
            worker_id = str(uuid4())
            allocation = self.worktrees.allocate(
                run.repository_path, run_id, worker_id, run.base_commit
            )
            started_at = utc_now()
            task = WorkerTask(
                run_id=run_id,
                worker_id=worker_id,
                specification_version=specification_version,
                worktree_path=str(allocation.path),
                base_commit=run.base_commit,
                objective=objective,
                acceptance_criteria=acceptance_criteria,
                allowed_write_paths=allowed_write_paths,
                timeout_seconds=timeout_seconds,
            )
            with self.store.transaction() as connection:
                connection.execute(
                    "INSERT INTO workers VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                    (
                        worker_id,
                        run_id,
                        specification_version,
                        "running",
                        str(allocation.path),
                        allocation.branch_name,
                        started_at,
                    ),
                )
                self.store.set_run_state(connection, run_id, RunState.WORKER_RUNNING)
                self._event(
                    connection,
                    run_id,
                    "worker.dispatched",
                    {
                        "worker_id": worker_id,
                        "specification_version": specification_version,
                        "worktree_path": str(allocation.path),
                        "branch_name": allocation.branch_name,
                    },
                )

            result = self.runtime.run(task)
            completed_at = utc_now()
            terminal_state = (
                RunState.COMPLETED if result.status == WorkerStatus.SUCCEEDED else RunState.FAILED
            )
            with self.store.transaction() as connection:
                connection.execute(
                    "UPDATE workers SET status = ?, completed_at = ?, result_json = ? WHERE worker_id = ?",
                    (result.status.value, completed_at, json.dumps(result.to_dict()), worker_id),
                )
                self.store.set_run_state(connection, run_id, terminal_state)
                self._event(
                    connection,
                    run_id,
                    f"worker.{result.status.value}",
                    {"worker_id": worker_id, "result": result.to_dict()},
                )
            return worker_id, result
        finally:
            self._dispatch_lock.release()

    def cancel(self, worker_id: str) -> bool:
        return self.runtime.cancel(worker_id)

