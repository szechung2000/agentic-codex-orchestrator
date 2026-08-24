from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentic_codex_orchestrator.git_repository import RepositoryPreflightError
from agentic_codex_orchestrator.persistence import SQLiteStore
from agentic_codex_orchestrator.run_service import RunService


def git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(repository), *arguments], text=True).strip()


class RunServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = self.root / "repo"
        self.repository.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        git(self.repository, "config", "user.email", "sprint0@example.invalid")
        git(self.repository, "config", "user.name", "Sprint Zero")
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        git(self.repository, "add", "README.md")
        git(self.repository, "commit", "-qm", "fixture")
        self.store = SQLiteStore(self.root / "state.sqlite3")
        self.audit_path = self.root / "events.jsonl"
        self.service = RunService(self.store, self.audit_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_run_persists_normalized_state_and_event(self) -> None:
        run = self.service.create_run(self.repository)

        persisted = self.store.get_run(run.run_id)
        events = self.store.list_events(run.run_id)
        audit = json.loads(self.audit_path.read_text(encoding="utf-8").strip())

        self.assertEqual(run, persisted)
        self.assertEqual(git(self.repository, "rev-parse", "HEAD"), run.base_commit)
        self.assertEqual("run.created", events[0].event_type)
        self.assertEqual(events[0].to_dict(), audit)

    def test_invalid_repository_is_rejected_before_state_is_written(self) -> None:
        with self.assertRaises(RepositoryPreflightError):
            self.service.create_run(self.root / "missing")

        with self.store.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        self.assertEqual(0, count)

