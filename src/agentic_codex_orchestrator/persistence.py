from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import Event, Run, RunState


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    repository_path TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS specifications (
    specification_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    version INTEGER NOT NULL,
    content_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, version)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    specification_id TEXT NOT NULL REFERENCES specifications(specification_id),
    specification_version INTEGER NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    UNIQUE(run_id, specification_id, approved_by)
);

CREATE TABLE IF NOT EXISTS workers (
    worker_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    specification_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    result_json TEXT
);
"""


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def insert_run(self, connection: sqlite3.Connection, run: Run) -> None:
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
            (run.run_id, run.repository_path, run.base_commit, run.state.value, run.created_at),
        )

    def append_event(self, connection: sqlite3.Connection, event: Event) -> None:
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.run_id,
                event.sequence,
                event.event_type,
                event.occurred_at,
                json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
            ),
        )

    def next_sequence(self, connection: sqlite3.Connection, run_id: str) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["value"])

    def get_run(self, run_id: str) -> Run | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return Run(
            run_id=row["run_id"],
            repository_path=row["repository_path"],
            base_commit=row["base_commit"],
            state=RunState(row["state"]),
            created_at=row["created_at"],
        )

    def list_events(self, run_id: str) -> list[Event]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [
            Event(
                event_id=row["event_id"],
                run_id=row["run_id"],
                sequence=row["sequence"],
                event_type=row["event_type"],
                occurred_at=row["occurred_at"],
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    def set_run_state(self, connection: sqlite3.Connection, run_id: str, state: RunState) -> None:
        cursor = connection.execute(
            "UPDATE runs SET state = ? WHERE run_id = ?", (state.value, run_id)
        )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown run: {run_id}")

    def get_worker(self, worker_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        if value["result_json"]:
            value["result"] = json.loads(value.pop("result_json"))
        return value


class JSONLAuditLog:
    """Append-only event mirror; event IDs make reconciliation idempotent."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: Event) -> None:
        line = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
