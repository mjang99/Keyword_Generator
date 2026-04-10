# TASK-030 Promote Crawl4AI Preprocessing To Default

- status: blocked
- owner: Codex
- priority: high
- depends_on: TASK-029

## Goal

Promote the approved Crawl4AI-preprocessed snapshot path to the default collection preprocessing source only after the limited rollout succeeds under real Lambda traffic and proves it is better than the current baseline.

## Scope

- Review `TASK-029` rollout evidence and confirm that every default-promotion gate is met.
- Flip the default collection preprocessing path from the current HTML-first baseline to the approved Crawl4AI path.
- Keep an immediate rollback path to the prior default for at least one release after promotion.
- Update Lambda runtime wiring, configuration defaults, regression coverage, and operator docs to reflect the new default.
- Preserve the previous path as an explicit fallback profile until post-promotion canary evidence is green.

## Preconditions

- `TASK-029` completed with an explicit recommendation to promote.
- Limited-rollout evidence covers at least:
  - `14` consecutive days
  - `500` successful collection runs total
  - `100` successful runs on each approved domain
- No rollback trigger fired during the final `7` days of the limited rollout window.

## Required Evidence

- A promotion decision memo at `docs/CRAWL4AI_PREPROCESSING_DEFAULT_PROMOTION.md`.
- The completed limited-rollout report from `TASK-029`.
- A pre-promotion canary plan and a post-promotion verification log.
- Regression tests that lock the promoted default behavior.
- Updated operator notes covering:
  - default path
  - fallback path
  - rollback switch
  - expected artifact behavior

## Promotion Criteria

- Stability:
  - candidate fetch-failure rate is not worse than baseline by more than `0.5 percentage points`
  - candidate timeout rate is not worse than baseline by more than `0.25 percentage points`
  - candidate p95 collection duration is `<= 20s`
- Downstream quality:
  - page-class parity `>= 99%`
  - `supported_for_generation` parity `>= 99%`
  - OCR trigger parity `>= 99%`
  - admitted OCR block parity `>= 98%` on OCR-relevant pages
- Evidence quality:
  - thin-pack or `quality_warning` rate is equal to or better than baseline
  - no approved domain regresses in reviewed product-detail extraction quality
  - at least `2` quality metrics show sustained improvement versus baseline on the rollout cohort
- Safety:
  - no blocker/waiting/support false-positive regression is accepted
  - no export-schema, artifact-schema, or downstream contract widening is introduced as part of the default flip unless separately approved

## Rollback Rules

- Promotion must be reversible by configuration and one deploy:
  - restore the prior default preprocessing selector
  - keep the Crawl4AI path available as a non-default profile until the rollback window closes
- Immediate rollback is required if, after default promotion, any of the following occur:
  - two consecutive `15` minute windows breach the post-promotion failure or timeout thresholds
  - canary review finds blocker, waiting-room, or support-page false positives that suppress supported PDP generation
  - export or artifact contract corruption is detected
- If rollback requires data migration, artifact cleanup, or schema repair, this task is not done.

## Done When

- The default preprocessing source is switched in code and Lambda configuration.
- `docs/CRAWL4AI_PREPROCESSING_DEFAULT_PROMOTION.md` records the evidence, promotion decision, and rollback plan.
- Regression tests and post-promotion canary checks pass.
- The prior default remains available as a documented fallback path for at least one release.

## Notes

- This task must not start unless `TASK-029` succeeds.
- Promotion requires stronger evidence than the limited rollout gate; mixed evidence means keep the candidate as a limited profile.
- Do not promote because the candidate is interesting or richer in raw text alone. Promotion requires measured downstream wins under Lambda constraints.
- Blocked because `TASK-029` is not authorized after the current migration decision.
- A future tuned benchmark may reopen `TASK-029` through `TASK-035`, but `TASK-030` must still wait for a successful limited rollout first.
- The current tuning retry path ended with `TASK-035 = keep experimental only`, so this task remains blocked.
