# Agentic Codex Orchestrator

A local-first, stateful software-engineering workflow in which an interactive Codex session refines a high-level goal, a deterministic supervisor launches isolated headless Codex workers, and an independent verifier evaluates the result.

The product and Agile source of truth is the private Google Drive document named **Agentic Codex Orchestrator — Agile System Specification**. GitHub issues mirror its epics, stories, tasks, acceptance criteria, and sprint placement without publishing the private document link.

## Sprint 0 walking skeleton

Sprint 0 establishes the smallest controlled implementation path:

1. Validate a Git repository and immutable base commit, then create a persisted run.
2. Persist a versioned specification and require approval of that exact version.
3. Allocate an isolated worktree and dispatch one headless Codex worker through a structured contract.
4. Persist normalized lifecycle events to SQLite and an append-only JSONL audit log.
5. Expose dispatch through a local stdio MCP server for an interactive Codex host.

Run the tests with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Install the optional MCP adapter with `pip install -e '.[mcp]'`.

