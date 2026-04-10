# TASK-029 Limited Rollout Of Crawl4AI Preprocessed Snapshots

- status: blocked
- owner: Codex
- priority: high
- depends_on: TASK-028

## Goal

Run a Lambda-first limited rollout of the approved Crawl4AI-preprocessed snapshot path on an explicit allowlist cohort and prove whether it is safe enough to remain enabled beyond experiment status.

This task is a limited rollout only. It must not flip the global default.

## Scope

- Enable the candidate path only through the collection Lambda runtime:
  - keep the current HTML-first preprocessing path as the baseline default
  - gate the Crawl4AI candidate behind a config/profile switch
  - restrict activation to an explicit domain allowlist approved by `TASK-028`
- Keep the stable snapshot, OCR, evidence, export, and storage contracts unchanged during rollout.
- Measure:
  - p50 and p95 collection duration
  - fetch-failure rate
  - timeout rate
  - page-class parity
  - `supported_for_generation` parity
  - OCR trigger parity
  - admitted OCR block parity on OCR-relevant pages
  - evidence thin-pack and `quality_warning` rates
  - operator-reviewed product-detail extraction quality on sampled URLs
- Prove that rollback to the current baseline is config-only and low-risk.

## Rollout Shape

- Cohort size:
  - at most `3` approved domains in the first rollout wave
  - domains must be named explicitly in the task notes before rollout begins
- Traffic shape:
  - Lambda-first allowlist rollout only
  - no global percentage rollout
  - no default switch
- Observation window:
  - at least `7` consecutive days
  - and at least `100` successful collection runs per approved domain

## Required Evidence

- A rollout report at `docs/CRAWL4AI_PREPROCESSING_LIMITED_ROLLOUT_REPORT.md`.
- Raw metric exports or summarized artifacts under `artifacts/crawl4ai_rollout/limited/`.
- Per-domain parity tables comparing baseline and candidate outcomes.
- A sampled operator review log for at least `10` URLs per approved domain covering:
  - commerce PDPs
  - support/spec pages if present
  - OCR-relevant pages if present
- A rollback drill record showing:
  - the exact Lambda configuration change used to disable the candidate path
  - confirmation that baseline collection resumed without schema repair or data migration

## Success Criteria

- Stability:
  - candidate fetch-failure rate is not worse than baseline by more than `1 percentage point`
  - candidate timeout rate is not worse than baseline by more than `0.5 percentage points`
  - p95 collection duration remains `<= 30s`
- Downstream parity:
  - page-class parity `>= 98%`
  - `supported_for_generation` parity `>= 98%`
  - OCR trigger parity `>= 98%`
  - admitted OCR block parity `>= 95%` on OCR-relevant pages
- Quality:
  - thin-pack or `quality_warning` rate is not worse than baseline by more than `2 percentage points`
  - at least one documented quality win from `TASK-028` persists in real Lambda traffic
  - no reviewed domain shows new blocker/waiting/support false positives on sampled URLs

## Rollback Rules

- Immediate rollback is required if any of the following occur:
  - two consecutive `15` minute windows exceed the fetch-failure threshold
  - two consecutive `15` minute windows exceed the timeout threshold
  - any export-schema or artifact-schema corruption is observed
  - reviewed rollout samples show blocker, waiting-room, or support-page misclassification that would suppress supported PDP generation
- Rollback method:
  - disable the candidate preprocessing selector in the collection Lambda configuration
  - clear the Crawl4AI rollout allowlist
  - redeploy the collection Lambda
- Rollback is incomplete if it requires data backfills, queue drains, or artifact repair.

## Done When

- The rollout cohort is explicit and was enforced through Lambda configuration.
- `docs/CRAWL4AI_PREPROCESSING_LIMITED_ROLLOUT_REPORT.md` contains the full metric summary and operator review.
- The rollout either:
  - meets all success criteria and explicitly recommends `TASK-030`, or
  - documents the failure and recommends rollback to experimental-only status
- The rollback drill is completed and evidenced.

## Notes

- This task should only start if `TASK-028` authorizes a limited rollout.
- A global default flip is out of scope even if the rollout looks strong early.
- Preserve the current HTML-first path as the safe baseline throughout the rollout.
- Blocked by `TASK-028` decision `keep experimental only`.
- This task may be reopened only by `TASK-035` after a new tuned evidence set clears the replacement parity gate.
- `TASK-035` completed with `keep experimental only`, so this task remains blocked.
