# Crawl4AI Preprocessing Migration Decision - 2026-04-10

## Decision

`keep experimental only`

Do not start `TASK-029`. Do not allow default promotion work from `TASK-030`.

## Evidence Reviewed

- Benchmark artifact: [results.json](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_preprocessing_benchmark/results.json)
- Benchmark summary: [summary.md](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_preprocessing_benchmark/summary.md)
- Harness: [evaluate_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/scripts/evaluate_crawl4ai_preprocessing_benchmark.py)

## Fixed-Case Outcome

- Cases evaluated: `5`
- Rows evaluated: `20`
- Case fetch errors: `0`
- Live cases evaluated: `3`
- Candidate rows marked `candidate`: `0`

## Candidate Assessment

### `raw_html`

- Best result on all three live PDPs.
- Preserved current page classification and OCR trigger behavior.
- Remains the only acceptable text source among the evaluated candidates.

### `cleaned_html`

- No material win on the fixed live set.
- Reduced `decoded_text_chars` versus `raw_html` on all three live PDPs.
- Preserved page class on live cases, but did not improve evidence count or OCR behavior enough to justify rollout.
- Fixture coverage is not meaningful yet because fixture cases do not provide Crawl4AI sidecars.

### `markdown`

- Reduced `decoded_text_chars` on all three live PDPs.
- Produced one small evidence-count increase on the Apple live PDP, but not enough to offset structure loss risk and the repo's HTML-first semantics.
- Remains a sidecar-only comparison artifact.

### `fit_markdown`

- Not available from the current Crawl4AI configuration on the fixed live set.
- Rejected as a migration candidate.

## Regression Summary

- Classification regressions recorded: `5`
- OCR trigger regressions recorded: `9`
- Evidence regressions recorded: `9`

Important nuance:

- Most regressions came from non-raw candidates, especially missing sidecar cases and `fit_markdown` absence.
- No non-raw candidate produced a durable, reviewable downstream win across the fixed live set.

## Gate Result

`TASK-028` fails the limited-rollout entry gate.

Reasons:

- No candidate source qualified as `candidate`.
- No candidate demonstrated a material quality win that survived classifier/OCR/evidence parity review.
- `fit_markdown` is not operationally available under the current Crawl4AI setup.
- `cleaned_html` is still interesting as an experimental input, but the current evidence is not strong enough for Lambda-first allowlist rollout.

## Operational Direction

- Keep the current HTML-first preprocessing path as the default.
- Keep Crawl4AI preprocessing sources as benchmark-only or debug-only sidecars.
- Preserve `collection/preprocessed_page.json` as the preferred intermediate artifact shape if benchmarking resumes later.
- If the team retries migration with richer Crawl4AI tuning plus broader OCR coverage, use `TASK-031` through `TASK-035` as the reopen path before touching `TASK-029`.
- Re-open migration only if one of the following changes:
  - Crawl4AI content-filter configuration starts producing usable `fit_markdown` consistently
  - a broader fixed live set shows repeated evidence or OCR wins for `cleaned_html`
  - product-detail extraction proves measurable recall gains from `cleaned_html` without snapshot regressions

## Effect On Tasks

- `TASK-024`: done
- `TASK-025`: done
- `TASK-026`: done
- `TASK-027`: done
- `TASK-028`: done with `keep experimental only`
- `TASK-029`: blocked
- `TASK-030`: blocked
