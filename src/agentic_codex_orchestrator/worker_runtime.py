from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from .worker_contracts import WORKER_RESULT_SCHEMA, WorkerResult, WorkerStatus, WorkerTask


class WorkerRuntime(Protocol):
    def run(self, task: WorkerTask) -> WorkerResult: ...

    def cancel(self, worker_id: str) -> bool: ...


class CodexWorkerRuntime:
    """Headless Codex adapter using stable non-interactive CLI flags."""

    def __init__(self, executable: str = "codex") -> None:
        self.executable = executable
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def build_command(self, task: WorkerTask, schema_path: Path, output_path: Path) -> list[str]:
        return [
            self.executable,
            "exec",
            "--cd",
            task.worktree_path,
            "--sandbox",
            "workspace-write",
            "--json",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]

    def run(self, task: WorkerTask) -> WorkerResult:
        with tempfile.TemporaryDirectory(prefix="aco-worker-") as temporary:
            root = Path(temporary)
            schema_path = root / "result.schema.json"
            output_path = root / "last-message.json"
            schema_path.write_text(json.dumps(WORKER_RESULT_SCHEMA), encoding="utf-8")
            process = subprocess.Popen(
                self.build_command(task, schema_path, output_path),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._lock:
                self._processes[task.worker_id] = process
            try:
                stdout, stderr = process.communicate(task.prompt(), timeout=task.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.terminate()
                stdout, stderr = process.communicate()
                return WorkerResult(
                    WorkerStatus.TIMED_OUT, "Worker timed out", (), (), stderr.strip(), process.returncode or 124
                )
            finally:
                with self._lock:
                    self._processes.pop(task.worker_id, None)

            events = tuple(
                json.loads(line) for line in stdout.splitlines() if line.strip().startswith("{")
            )
            if process.returncode != 0 or not output_path.exists():
                return WorkerResult(
                    WorkerStatus.FAILED,
                    "Codex worker failed",
                    (),
                    (),
                    stderr.strip(),
                    process.returncode,
                    events,
                )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            return WorkerResult(
                WorkerStatus.SUCCEEDED,
                payload["summary"],
                tuple(payload["changed_files"]),
                tuple(payload["tests"]),
                output_path.read_text(encoding="utf-8"),
                process.returncode,
                events,
            )

    def cancel(self, worker_id: str) -> bool:
        with self._lock:
            process = self._processes.get(worker_id)
        if process is None:
            return False
        process.terminate()
        return True

