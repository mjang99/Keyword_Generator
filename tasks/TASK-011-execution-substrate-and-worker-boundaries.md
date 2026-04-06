# TASK-011 Execution Substrate And Worker Boundaries

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-003, TASK-004

## Goal

Lock the execution substrate decisions that upstream design tasks need before they can safely define collection, OCR, and generation contracts.

## Scope

- Collection vs OCR vs generation worker split
- Queue boundaries between stages
- Artifact handoff boundaries between stages
- Container vs zip packaging assumptions per worker
- Minimal idempotency boundary per stage

## Done When

- Worker boundaries are explicit enough that collection and OCR tasks do not need to invent runtime structure.
- Queue boundaries and stage handoffs are documented for collection, OCR, generation, aggregation, and notification flows.
- Packaging assumptions are documented for each worker type, including where container images are required.
- Minimal idempotency boundaries are defined per stage with concrete examples of replay-safe identifiers.

## Notes

- This task must complete before `TASK-006` and `TASK-007`.
- `TASK-010` consumes this output and should not redefine worker boundaries.
- Locked output lives in `docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md` Section 5.1 through 5.4.
- V1 worker split is `Submit -> Collection -> OCR? -> Generation -> Aggregation -> Notification`, with one URL-scoped message per `url_task_id` and one job-scoped notification message per `job_id`.
- Packaging is locked to Lambda zip for control-plane workers and Lambda container images for collection/OCR workers. ECS/Fargate stays out of v1.
