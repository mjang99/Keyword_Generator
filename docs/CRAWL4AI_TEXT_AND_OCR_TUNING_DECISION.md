# Crawl4AI Text And OCR Tuning Decision - 2026-04-10

## Status

`done`

## Decision

`keep experimental only`

Do not reopen `TASK-029`. Do not allow default-promotion work in `TASK-030`.

## Evidence Reviewed

- Full tuning matrix with all profiles and full eligible-image OCR:
  - [quality_tuning_latest.json](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_quality_tuning/quality_tuning_latest.json)
- Matching capped-OCR comparison run:
  - [quality_tuning_policy_only.json](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_quality_tuning/quality_tuning_policy_only.json)
- Run summary:
  - [summary.md](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_quality_tuning/summary.md)
- Prior blocked migration decision:
  - [CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md)

## Fixed-Set Outcome

- Cases evaluated per run: `5`
- Profiles evaluated per run: `6`
- Candidate sources evaluated per run: `4`
- Rows per run: `120`
- Candidate rows marked `candidate`: `0`
- OCR expanded-vs-capped changed rows: `0`

## Source Assessment

### `raw_html`

- Remained the strongest baseline across every tuned profile.
- Produced `0` classification regressions and `0` evidence regressions.
- No tuned profile produced a reason to displace it.

### `cleaned_html`

- Stayed classification-safe across all tuned profiles.
- Did not produce a material text, OCR, or evidence win over `raw_html`.
- Remains interesting as a debug or product-extraction sidecar, not as a migration candidate.

### `markdown`

- Preserved classification in this matrix but still accumulated evidence regressions.
- Did not produce a durable end-to-end gain on the fixed live set.
- Remains sidecar-only.

### `fit_markdown`

- Still non-viable under richer profiles.
- Produced the only classification regressions in the matrix and the highest evidence-regression count.
- Remains ruled out for migration.

## OCR Coverage Result

- `eligible_all` versus `policy_only` produced no changes in:
  - evidence fact counts
  - OCR trigger reasons
  - admitted OCR block deltas
  - recommendation flags
- On the current fixed set, running OCR on all filtered eligible images did not create a measurable quality lift.

## Gate Result

`TASK-034` fails.

Reasons:

- No tuned profile plus candidate-source combination produced a `candidate` row.
- `cleaned_html` did not demonstrate the required material quality win.
- Markdown sources remained weaker than the current baseline.
- Full eligible-image OCR did not improve downstream results on the fixed cases.

## Effect On Tasks

- `TASK-031`: done
- `TASK-032`: done
- `TASK-033`: done
- `TASK-034`: done with gate failure
- `TASK-035`: done with `keep experimental only`
- `TASK-029`: remains blocked
- `TASK-030`: remains blocked

## Notes

- This memo does not change the earlier `TASK-028` decision; it confirms the retry path also fails to reopen rollout.
- Future retries require materially different evidence, not another pass over the same profile matrix.
