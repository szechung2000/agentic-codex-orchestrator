from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorktreeAllocation:
    path: Path
    branch_name: str


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not normalized:
        raise ValueError("Identifier does not contain a branch-safe character")
    return normalized[:64]


class WorktreeManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def allocate(
        self,
        repository_path: str | Path,
        run_id: str,
        worker_id: str,
        base_commit: str,
    ) -> WorktreeAllocation:
        repository = Path(repository_path).resolve()
        branch = f"aco/run-{_slug(run_id)}/worker-{_slug(worker_id)}"
        path = self.root / _slug(run_id) / _slug(worker_id)
        if path.exists():
            raise FileExistsError(f"Worker worktree already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "-C", str(repository), "worktree", "add", "-b", branch, str(path), base_commit],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Unable to allocate worker worktree")
        return WorktreeAllocation(path=path, branch_name=branch)

