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
- `TASK-013` Crawl4AI collection spike and adoption gate
- `TASK-014` Crawl4AI install and env verification
- `TASK-015` Crawl4AI experimental fetcher
- `TASK-016` Crawl4AI benchmark harness and evaluation
- `TASK-017` Crawl4AI adoption decision and migration gate
- `TASK-018` Crawl4AI conditional integration execution
- `TASK-019` Product detail extraction contract design
- `TASK-020` Hybrid product extraction and validation
- `TASK-021` Selector registry and self-healing review flow
- `TASK-022` Crawl worker split for product extraction
- `TASK-023` Limited-scope Crawl4AI rollout for product pages
- `TASK-024` Crawl4AI preprocessing source benchmark
- `TASK-025` Dual-path snapshot parity harness
- `TASK-026` Crawl4AI preprocessing contract widening
- `TASK-027` Downstream parity for Crawl4AI preprocessing
- `TASK-028` Crawl4AI preprocessing migration gate
- `TASK-029` Limited rollout of Crawl4AI preprocessed snapshots
- `TASK-030` Promote Crawl4AI preprocessing to default
- `TASK-031` Crawl4AI text-quality tuning matrix
- `TASK-032` Full eligible-image OCR coverage benchmark
- `TASK-033` Product-page text and markdown filter tuning
- `TASK-034` Text and OCR parity gate for tuned Crawl4AI preprocessing
- `TASK-035` Reopen Crawl4AI preprocessing migration decision
