# TASK-024 Crawl4AI Preprocessing Source Benchmark

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-017

## Goal

Benchmark whether Crawl4AI preprocessing outputs can outperform the current repo-owned HTML normalization as the source for snapshot content fields.

## Scope

- Compare exactly these candidate sources per case:
  - `raw_html`
  - `cleaned_html`
  - `markdown`
  - `fit_markdown`
- Measure impact on:
  - `decoded_text`
  - `visible_text_blocks`
  - page classification
  - OCR trigger behavior
  - evidence fact quality
- Reuse the fixed fixture/live URL set only; do not expand the input set in this task.

## Candidate Source Definitions

- `raw_html`
  - repo-owned extraction from browser-rendered Crawl4AI `result.html`
- `cleaned_html`
  - repo-owned extraction from Crawl4AI `result.cleaned_html`
- `markdown`
  - Crawl4AI markdown output without fit/pruning reduction
- `fit_markdown`
  - Crawl4AI filtered markdown generated with an explicit content filter

## Fixed Invariants

- `title`, `meta_description`, `canonical_tag`, `meta_locale`, `structured_data`, and `image_candidates[]` must continue to come from rendered HTML in this task.
- Only the source used to build `decoded_text` and derived `visible_text_blocks` may vary.
- Do not change classifier thresholds, OCR policy, evidence rules, or the stable snapshot contract.
- Do not add hybrid or extra candidates in this task. If all four fixed candidates fail, report that result directly.

## Required Output Columns

The comparison artifact for this task must contain one row per `{case_id, candidate_source}` with exactly these columns:

- `case_id`
- `case_type`
- `candidate_source`
- `fetch_mode`
- `final_url`
- `http_status`
- `page_class`
- `supported_for_generation`
- `decoded_text_chars`
- `visible_block_count`
- `structured_data_count`
- `image_candidate_count`
- `ocr_trigger_reasons`
- `evidence_fact_count`
- `quality_warning`
- `elapsed_seconds`
- `source_loss_notes`
- `recommendation_flag`

## Execution Rules

- `recommendation_flag` must be one of `keep_testing`, `reject`, or `candidate`.
- Reject a candidate if it changes a fixed case from correct supported classification to incorrect unsupported classification, or the reverse.
- Reject a candidate if it materially collapses useful block structure even when char count increases.
- Prefer `cleaned_html` over markdown-derived sources when results are otherwise similar because it preserves current repo extraction semantics better.
- Do not promote `fit_markdown` unless it shows a clear evidence-quality win without misclassification on the fixed cases.

## Done When

- A comparison report exists for every fixed case and all four candidate sources.
- The report identifies one of:
  - no migration candidate
  - one candidate worth a limited rollout
  - one candidate worth default-path promotion
- The report includes measured latency and quality deltas, not just qualitative impressions.
- The report explicitly states which candidate, if any, should be used for `decoded_text` and `visible_text_blocks`.

## Notes

- This task is about preprocessing source selection, not raw fetcher selection.
- Do not change the stable snapshot contract in this task.
- Use the measurement table and candidate definitions locked in [CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md).
- The current benchmark harness lives in [evaluate_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/scripts/evaluate_crawl4ai_preprocessing_benchmark.py) with coverage in [test_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/tests/test_crawl4ai_preprocessing_benchmark.py).
- Actual benchmark output is recorded in [results.json](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_preprocessing_benchmark/results.json) and summarized in [CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md).
