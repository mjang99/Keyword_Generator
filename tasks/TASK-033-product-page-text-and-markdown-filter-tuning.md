# TASK-033 Product-Page Text And Markdown Filter Tuning

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-031

## Goal

Determine whether Crawl4AI markdown and content-filter tuning can recover product-detail text well enough to overturn the rejection reasons recorded in `TASK-024`.

## Scope

- Tune markdown generation and pruning specifically for product-detail pages.
- Compare at minimum:
  - default markdown generator
  - tuned pruning/content filter for PDP detail and spec content
  - no-fit markdown baseline
- Evaluate whether `fit_markdown` can become operational and useful on the approved live PDP set.
- Record structure loss, evidence parity, and product-detail field recovery, not just text-length gains.
- Keep these changes benchmark-only until a later migration gate reopens rollout planning.

## Done When

- The tuning artifacts show whether `markdown` or `fit_markdown` becomes a credible preprocessing candidate.
- Any continued rejection of `fit_markdown` is backed by concrete benchmark evidence rather than assumption.
- The task explicitly states whether markdown candidates remain sidecar-only or should continue to the parity gate.

## Notes

- This task must directly address the rejection reasons from `TASK-024`, especially the current non-viability of `fit_markdown`.
- If markdown candidates remain weak, record that explicitly so future migration work stays focused on `raw_html` or `cleaned_html`.
- Result: richer Crawl4AI fetch profiles did not make markdown candidates viable. `markdown` preserved classification but kept evidence regressions, and `fit_markdown` still produced classification/evidence failures on the fixed set. This retry path closes with markdown sources still ruled out for migration. See [CRAWL4AI_TEXT_AND_OCR_TUNING_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_TEXT_AND_OCR_TUNING_DECISION.md).
