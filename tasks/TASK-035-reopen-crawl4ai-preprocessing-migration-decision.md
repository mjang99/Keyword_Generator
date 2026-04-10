# TASK-035 Reopen Crawl4AI Preprocessing Migration Decision

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-034

## Goal

Revisit the blocked preprocessing migration only if the tuned text-plus-OCR benchmark produces evidence strong enough to overturn the current decision.

## Scope

- Review evidence from `TASK-031` through `TASK-034`.
- Write the decision memo at `docs/CRAWL4AI_TEXT_AND_OCR_TUNING_DECISION.md`.
- Allowed outputs:
  - keep experimental only
  - reopen `TASK-029` with an approved limited-rollout cohort
- Explicitly forbid:
  - skipping directly to `TASK-030`
  - changing runtime defaults in this task
  - widening export or snapshot contracts without a separate approved task

## Done When

- `docs/CRAWL4AI_TEXT_AND_OCR_TUNING_DECISION.md` exists and names exactly one decision.
- The memo explains whether the tuned evidence is strong enough to reopen `TASK-029`.
- `TASK-029` and `TASK-030` remain blocked unless the memo explicitly reauthorizes `TASK-029`.

## Notes

- This task reopens the decision only after a new evidence set. It does not retroactively change `TASK-028`.
- See [TASK-029-limited-rollout-of-crawl4ai-preprocessed-snapshots.md](/C:/Users/NHN/Repo/Keyword_Generator/tasks/TASK-029-limited-rollout-of-crawl4ai-preprocessed-snapshots.md) and [TASK-030-promote-crawl4ai-preprocessing-to-default.md](/C:/Users/NHN/Repo/Keyword_Generator/tasks/TASK-030-promote-crawl4ai-preprocessing-to-default.md) for the downstream path that remains blocked today.
- Result: `keep experimental only`. `TASK-029` is not reopened and `TASK-030` remains blocked.
