# TASK-028 Crawl4AI Preprocessing Migration Gate

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-027

## Goal

Make one explicit migration decision for the Crawl4AI-preprocessed snapshot path after benchmark, contract, and downstream parity work are complete.

This task may authorize only:

- keep experimental only
- proceed to Lambda-first limited rollout via `TASK-029`

This task must not authorize a global default flip. Default promotion remains blocked until `TASK-029` succeeds and `TASK-030` is completed.

## Scope

- Review evidence from `TASK-024` through `TASK-027`.
- Write the decision memo at `docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md`.
- Define the exact rollout cohort selection rule for `TASK-029`.
- Define measurable success criteria for:
  - entering limited rollout
  - remaining in limited rollout
  - becoming eligible for default promotion in `TASK-030`
- Define the Lambda-first rollback path that preserves the current HTML-first baseline as the safe default.

## Required Evidence

- A fixed-input comparison table covering fixtures and the approved live URL set from the Crawl4AI spike.
- A parity summary for:
  - `classify_snapshot()`
  - `run_ocr_policy()`
  - `build_evidence_pack()`
- A contract decision that states which Crawl4AI artifacts are canonical inputs and which remain debug-only sidecars.
- A proposed Lambda rollout mechanism:
  - config flag or profile selector
  - domain allowlist input
  - rollback switch
- A written recommendation naming the approved rollout cohort or explicitly stating that no rollout is allowed.

## Promotion Criteria

### Gate To Start `TASK-029`

- Fixture gate:
  - `0` accepted regressions for blocker, waiting-room, or support-page classification on the fixed fixture set
  - `0` accepted export-schema changes
- Downstream parity gate on the approved live set:
  - page-class parity `>= 95%`
  - `supported_for_generation` parity `>= 95%`
  - OCR trigger parity `>= 95%`
  - evidence-pack thin-pack or `quality_warning` regressions `<= 5 percentage points`
- Quality-improvement gate:
  - the candidate path must show at least one material quality win on the target cohort, documented as one of:
    - median `usable_text_chars` gain `>= 25%`
    - admitted OCR block count gain `>= 10%`
    - evidence thin-pack rate reduction `>= 10 percentage points`
    - operator-reviewed product-detail extraction win on at least `2` approved live URLs
- Lambda safety gate:
  - candidate p95 collection duration must remain `<= 30s`
  - candidate timeout or fetch-failure rate must not exceed baseline by more than `1 percentage point`

### Gate To Create `TASK-030`

- `TASK-029` must complete successfully first.
- This task may only define the future default-promotion bar; it may not skip directly to default.
- The default-promotion bar must require all of:
  - page-class parity `>= 99%`
  - OCR trigger parity `>= 98%`
  - failure-rate regression `<= 0.5 percentage points`
  - no blocker/waiting/support false-positive regressions on reviewed rollout samples
  - a documented quality win that persists under real Lambda traffic

## Rollback Rules

- The current HTML-first preprocessing path remains the baseline and must stay deployable throughout `TASK-029`.
- Rollback from the limited rollout must be possible by Lambda configuration only:
  - revert the candidate preprocessing selector
  - clear the rollout allowlist
  - redeploy the collection Lambda without schema or storage migrations
- If the rollout path needs a contract or artifact-schema change to turn off, this task fails.

## Done When

- `docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md` exists and names exactly one decision.
- The decision includes measurable gates for `TASK-029` and future eligibility for `TASK-030`.
- The rollout cohort, rollback switch, and evidence requirements are explicit.
- If the candidate fails the gate, `TASK-029` and `TASK-030` remain blocked in the memo.

## Notes

- Do not promote a preprocessing source because text volume is larger if downstream quality does not improve.
- The gate is about end-to-end downstream quality under Lambda constraints, not raw preprocessing novelty.
- Keep the export schema, snapshot schema, and current baseline path unchanged unless a later task explicitly widens them.
- Decision result: `keep experimental only`. Limited rollout is not authorized. See [CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md).
