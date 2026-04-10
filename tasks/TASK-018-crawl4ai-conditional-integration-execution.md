# TASK-018 Crawl4AI Conditional Integration Execution

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-017, TASK-019, TASK-020, TASK-021, TASK-022, TASK-024, TASK-025, TASK-026, TASK-027, TASK-028

## Goal

Execute the permanent collection integration only if the adoption gate passes.

## Scope

- Decide the permanent text source strategy for collection.
- Decide whether `HtmlFetchResult` needs to widen for the adopted path.
- Add regression tests for the chosen collection path.
- Update runtime and persistence behavior for any adopted collection artifacts.
- Keep worker packaging and deployment alignment for a later stage if needed.

## Done When

- Crawl4AI is integrated into the collection runtime on the approved path.
- The chosen collection path is covered by regression tests.
- The implementation reflects the benchmarked contract rather than speculation.

## Notes

- This task should not be opened unless the gate in `TASK-017` passes.
- The prototype remains quality-first and contract-stable until this task exists.
- The gate passed as `adopt with limited scope`; this task is now the correct place for fallback or conditional integration work.
- `TASK-018` should be treated as the umbrella implementation task after the contract, hybrid extraction, selector registry, and worker-boundary tasks are locked.
- If the team wants to migrate preprocessing itself to Crawl4AI outputs, that work must pass `TASK-024` through `TASK-028` first.
- If the team retries preprocessing migration with richer Crawl4AI tuning, use `TASK-031` through `TASK-035` as the reopen path. Do not add them as direct dependencies here unless that retry path succeeds.
