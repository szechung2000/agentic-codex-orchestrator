from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_codex_orchestrator.models import Run, RunState, utc_now
from agentic_codex_orchestrator.persistence import SQLiteStore
from agentic_codex_orchestrator.specification_service import (
    ApprovalRequiredError,
    SpecificationService,
    SpecificationValidationError,
)


CONTENT = {
    "goal": "Deliver one controlled worker path",
    "scope": ["run", "approval", "worker"],
    "acceptance_criteria": ["No dispatch before approval"],
    "constraints": ["Local-first", "One worker"],
}


class SpecificationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = SQLiteStore(root / "state.sqlite3")
        self.audit = root / "events.jsonl"
        self.run = Run("run-1", str(root), "a" * 40, RunState.SPECIFICATION_PENDING, utc_now())
        with self.store.transaction() as connection:
            self.store.insert_run(connection, self.run)
        self.service = SpecificationService(self.store, self.audit)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_approval_is_bound_to_exact_latest_version(self) -> None:
        first = self.service.create_revision(self.run.run_id, CONTENT, "orchestrator")
        self.service.approve(self.run.run_id, first.version, "user")
        self.service.assert_dispatch_allowed(self.run.run_id, first.version)

        second = self.service.create_revision(
            self.run.run_id, {**CONTENT, "goal": "Revised goal"}, "orchestrator"
        )
        with self.assertRaises(ApprovalRequiredError):
            self.service.assert_dispatch_allowed(self.run.run_id, first.version)
        with self.assertRaises(ApprovalRequiredError):
            self.service.assert_dispatch_allowed(self.run.run_id, second.version)

        self.service.approve(self.run.run_id, second.version, "user")
        self.service.assert_dispatch_allowed(self.run.run_id, second.version)

    def test_incomplete_specification_is_rejected(self) -> None:
        with self.assertRaises(SpecificationValidationError):
            self.service.create_revision(self.run.run_id, {"goal": "Only a goal"}, "orchestrator")

