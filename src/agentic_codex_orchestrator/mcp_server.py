from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .persistence import SQLiteStore
from .supervisor import Supervisor
from .worker_runtime import CodexWorkerRuntime
from .worktrees import WorktreeManager


def create_server(state_root: str | Path | None = None) -> Any:
    try:
        from mcp.server import MCPServer
    except ImportError as error:
        raise RuntimeError("Install the MCP adapter with: pip install -e '.[mcp]'") from error

    root = Path(state_root or os.environ.get("ACO_STATE_ROOT", ".aco")).resolve()
    store = SQLiteStore(root / "state.sqlite3")
    supervisor = Supervisor(
        store,
        root / "events.jsonl",
        WorktreeManager(root / "worktrees"),
        CodexWorkerRuntime(),
    )
    server = MCPServer(
        "Agentic Codex Orchestrator",
        instructions=(
            "Use dispatch_worker only after the user has approved the current persisted specification. "
            "Sprint 0 permits one implementation worker at a time."
        ),
    )

    @server.tool()
    def dispatch_worker(
        run_id: str,
        specification_version: int,
        objective: str,
        acceptance_criteria: list[str],
        allowed_write_paths: list[str] | None = None,
        timeout_seconds: int = 900,
    ) -> dict[str, Any]:
        """Dispatch one isolated headless Codex implementation worker (writes state and files)."""
        worker_id, result = supervisor.dispatch(
            run_id,
            specification_version,
            objective,
            tuple(acceptance_criteria),
            tuple(allowed_write_paths or ["."]),
            timeout_seconds,
        )
        return {"worker_id": worker_id, "result": result.to_dict()}

    @server.tool()
    def get_worker(worker_id: str) -> dict[str, Any] | None:
        """Read persisted worker status and result."""
        return store.get_worker(worker_id)

    @server.tool()
    def cancel_worker(worker_id: str) -> dict[str, bool]:
        """Request cancellation of a running worker (process mutation)."""
        return {"cancel_requested": supervisor.cancel(worker_id)}

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()

