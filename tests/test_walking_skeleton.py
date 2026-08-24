from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agentic_codex_orchestrator.persistence import SQLiteStore
from agentic_codex_orchestrator.run_service import RunService
from agentic_codex_orchestrator.specification_service import (
    ApprovalRequiredError,
    SpecificationService,
)
from agentic_codex_orchestrator.supervisor import Supervisor
from agentic_codex_orchestrator.worker_contracts import WorkerResult, WorkerStatus, WorkerTask
from agentic_codex_orchestrator.worktrees import WorktreeManager


class FakeRuntime:
    def run(self, task: WorkerTask) -> WorkerResult:
        changed = Path(task.worktree_path) / "sprint0.txt"
        changed.write_text("walking skeleton\n", encoding="utf-8")
        return WorkerResult(
            WorkerStatus.SUCCEEDED,
            "Created Sprint 0 marker",
            ("sprint0.txt",),
            ("fake-runtime: passed",),
            "done",
            0,
        )

    def cancel(self, worker_id: str) -> bool:
        return False


class WalkingSkeletonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = self.root / "repo"
        self.repository.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Test"], check=True)
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "fixture"], check=True)
        self.store = SQLiteStore(self.root / "state.sqlite3")
        self.audit = self.root / "events.jsonl"
        self.run = RunService(self.store, self.audit).create_run(self.repository)
        self.specifications = SpecificationService(self.store, self.audit)
        self.specification = self.specifications.create_revision(
            self.run.run_id,
            {
                "goal": "Prove one worker path",
                "scope": ["worker"],
                "acceptance_criteria": ["File is isolated"],
                "constraints": ["One worker"],
            },
            "orchestrator",
        )
        self.supervisor = Supervisor(
            self.store,
            self.audit,
            WorktreeManager(self.root / "worktrees"),
            FakeRuntime(),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_approved_task_runs_in_isolated_worktree_and_persists_result(self) -> None:
        with self.assertRaises(ApprovalRequiredError):
            self.supervisor.dispatch(
                self.run.run_id, self.specification.version, "Build marker", ("File is isolated",)
            )

        self.specifications.approve(self.run.run_id, self.specification.version, "user")
        worker_id, result = self.supervisor.dispatch(
            self.run.run_id, self.specification.version, "Build marker", ("File is isolated",)
        )

        worker = self.store.get_worker(worker_id)
        self.assertEqual(WorkerStatus.SUCCEEDED, result.status)
        self.assertEqual("succeeded", worker["status"])
        self.assertTrue((Path(worker["worktree_path"]) / "sprint0.txt").exists())
        self.assertFalse((self.repository / "sprint0.txt").exists())
        event_types = [event.event_type for event in self.store.list_events(self.run.run_id)]
        self.assertIn("worker.dispatched", event_types)
        self.assertIn("worker.succeeded", event_types)

