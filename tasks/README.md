# Task Management

## Rules

- Task files must use the format `TASK-xxx-short-name.md`.
- Status must be one of `todo`, `in_progress`, `blocked`, or `done`.
- If implementation starts, the work should be represented in `tasks/` first.
- If design ambiguity remains, resolve it before implementation instead of burying it in code.
- When code changes become real, use review discipline before landing them.

## Minimum Template

```md
# TASK-000 Title

- status:
- owner:
- priority:
- depends_on:

## Goal

## Scope

## Done When

## Notes
```

## Current Backlog

- `TASK-001` Project bootstrap
- `TASK-002` Main project discovery
- `TASK-003` Implementation readiness check
- `TASK-004` API and job model design
- `TASK-005` GStack operating rules
- `TASK-011` Execution substrate and worker boundary design
- `TASK-006` Page collection and classification design
- `TASK-007` Evidence fallback and OCR policy
- `TASK-008` Keyword generation and validation design
- `TASK-009` Export aggregation and notification design
- `TASK-010` AWS runtime and observability baseline
