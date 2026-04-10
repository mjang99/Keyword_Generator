# TASK-031 Crawl4AI Text-Quality Tuning Matrix

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-028

## Goal

Re-run the blocked Crawl4AI preprocessing migration track with a richer Crawl4AI tuning matrix focused on text recall, not latency.

This task exists because `TASK-024` through `TASK-028` rejected the current preprocessing candidates under conservative Crawl4AI settings. It is a benchmark-only retry path and must not change runtime defaults.

## Scope

- Extend the benchmark runner so the fixed fixture/live set can be executed across named Crawl4AI fetch profiles.
- Required profiles:
  - `baseline_render`
  - `wait_images_render`
  - `interaction_render`
  - `magic_render`
  - `stealth_render`
  - `text_rich_render`
- For each profile, compare the same candidate preprocessing sources:
  - `raw_html`
  - `cleaned_html`
  - `markdown`
  - `fit_markdown`
- Store quality-tuning artifacts separately from the rejected migration artifacts:
  - `artifacts/crawl4ai_quality_tuning/`
- Keep runtime code, snapshot defaults, and Lambda configuration unchanged.

## Done When

- The benchmark runner can execute the full tuning matrix deterministically.
- Results are written under `artifacts/crawl4ai_quality_tuning/`.
- The output records profile-level as well as candidate-source-level summaries.
- The task notes identify whether any profile appears strong enough to continue into OCR and markdown tuning work.

## Notes

- This task is a retry path after `TASK-024` and the `TASK-028` decision `keep experimental only`.
- Review [CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md) before changing candidate criteria.
- Quality is prioritized over latency in this task, but no rollout may start here.
- Result: full fixture plus live matrix completed across all six profiles. No profile produced a `candidate` row; `cleaned_html` stayed parity-safe but did not beat `raw_html`, and `fit_markdown` remained non-viable. See [summary.md](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_quality_tuning/summary.md).
