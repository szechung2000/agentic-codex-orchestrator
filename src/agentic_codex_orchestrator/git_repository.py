from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class RepositoryPreflightError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    root: Path
    base_commit: str


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RepositoryPreflightError(result.stderr.strip() or "Git repository preflight failed")
    return result.stdout.strip()


def preflight_repository(repository_path: str | Path, base_ref: str = "HEAD") -> RepositorySnapshot:
    candidate = Path(repository_path).expanduser().resolve()
    if not candidate.exists():
        raise RepositoryPreflightError(f"Repository path does not exist: {candidate}")
    root = Path(_git(candidate, "rev-parse", "--show-toplevel"))
    commit = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    return RepositorySnapshot(root=root, base_commit=commit)

