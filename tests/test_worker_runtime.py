from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_codex_orchestrator.worker_contracts import WorkerTask
from agentic_codex_orchestrator.worker_runtime import CodexWorkerRuntime


class WorkerRuntimeTest(unittest.TestCase):
    def test_command_uses_headless_json_contract_and_workspace_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = WorkerTask("run", "worker", 1, str(root), "a" * 40, "Build", ("Pass",))
            command = CodexWorkerRuntime().build_command(
                task, root / "schema.json", root / "last.json"
            )
        self.assertEqual(["codex", "exec"], command[:2])
        self.assertIn("--json", command)
        self.assertEqual("workspace-write", command[command.index("--sandbox") + 1])
        self.assertEqual("-", command[-1])

