# TASK-032 Full Eligible-Image OCR Coverage Benchmark

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-031, TASK-007

## Goal

Measure whether Crawl4AI quality improves materially when OCR is run on all filtered eligible images instead of the current ranked-and-capped execution path.

## Scope

- Add a benchmark-only OCR mode that runs OCR across all ranked image candidates that survive the current decorative/runtime reject rules.
- Keep existing reject rules intact for:
  - SVG and icon assets
  - runtime/template asset URLs
  - known decorative promo chrome
  - tiny one-dimension assets
- Compare capped policy execution versus all-eligible execution on the fixed tuning matrix from `TASK-031`.
- Record at minimum:
  - admitted OCR block count
  - direct fact candidate count
  - evidence fact count lift attributable to OCR
  - per-page runtime increase
- Keep the production OCR policy unchanged; this task is benchmark-only.

## Done When

- The tuning benchmark can run in `policy_only` and `eligible_all` OCR modes.
- The artifacts show whether broader OCR coverage improves recall on approved live PDPs.
- The report makes clear whether OCR gain is translating into evidence or product-detail extraction gains rather than raw text volume only.

## Notes

- Depends on `TASK-007` because the existing OCR policy and reject rules remain the source of truth.
- Do not remove the production OCR cap in this task.
- The benchmark path may temporarily bypass runner `max_images`, but runtime behavior must stay unchanged until a later approval.
- Result: compared `policy_only` against `eligible_all` on the same tuning matrix. There were `0` changed rows in evidence count, OCR triggers, admitted OCR deltas, or recommendation flags, so broader OCR execution produced no measurable lift on the fixed set. See [summary.md](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_quality_tuning/summary.md).
