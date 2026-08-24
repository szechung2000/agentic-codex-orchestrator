# Agentic Codex Orchestrator

A local-first, stateful software-engineering workflow in which an interactive Codex session refines a high-level goal, a deterministic supervisor launches isolated headless Codex workers, and an independent verifier evaluates the result.

## Source of truth

The product and Agile implementation specification is maintained in [Agentic Codex Orchestrator — Agile System Specification](https://docs.google.com/document/d/1D94YK1fz1u7R6xtrtT0SWmDw2w6KK-ZHpmFaCK2VjTk/edit).

The GitHub backlog mirrors that specification: 9 epics, 30 user stories, Sprint 0–6, post-MVP gates, testable acceptance criteria, golden scenarios, and MVP exit criteria.

## Target architecture

User → Interactive Codex Orchestrator → Orchestration MCP → Python Supervisor → isolated headless Codex worker → Independent Verifier → Supervisor → Orchestrator

Important activity is normalized into immutable events, projected into SQLite operational state and an append-only JSONL audit log, and selectively promoted into Git-backed Markdown memory with provenance. A FastAPI/SSE backend and React dashboard provide live graph, timeline, evidence, memory trace, and replay views.

## MVP boundaries

- One interactive orchestrator.
- At most one implementation worker and one independent verifier at a time.
- Git worktree isolation for writing workers.
- Explicit user approval before implementation.
- Deterministic retry, timeout, cancellation, permission, and integration controls.
- Replay from persisted state and events without live Codex processes.
- No unbounded autonomy, cloud deployment, distributed scheduling, or semantic retrieval before benchmark evidence.

## Agile conventions

- Epic issues use titles beginning with `[EPIC-n]`.
- User-story issues use titles beginning with `[US-nnn]`.
- Every story includes a user/system outcome, testable acceptance criteria, sprint placement, parent epic, and verification evidence.
- A story is complete only when every mandatory acceptance criterion passes or is explicitly waived by the user, independent verification is recorded, and the change is safely integrated.

## Recommended delivery order

Build the smallest closed loop first: create run → persist approved specification → create worktree → dispatch one worker → collect structured events/result → dispatch verifier → persist criterion evidence → return the outcome. Add restart/replay, memory, visualization, and parallelism only after the underlying contracts are reliable.