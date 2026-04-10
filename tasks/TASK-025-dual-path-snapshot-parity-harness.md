# TASK-025 Dual-Path Snapshot Parity Harness

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-024

## Goal

Build a harness that can generate and compare two `NormalizedPageSnapshot` variants for the same URL: current HTML-first preprocessing and a candidate Crawl4AI-preprocessed path.

## Scope

- Keep the current snapshot contract stable.
- Add a dual-path harness that records:
  - field-level diffs
  - classification diffs
  - OCR decision diffs
  - evidence-pack diffs
- Make the harness easy to run on fixtures and on a fixed set of live URLs.
- Record parity failures in a format suitable for review.

## Done When

- The same input can produce both baseline and candidate snapshots.
- Field-level parity and regression diffs are visible without manual inspection.
- The harness can highlight which downstream stage regressed when a preprocessing source changes.

## Notes

- This harness is a precondition for any preprocessing migration.
- Do not widen or rename snapshot fields in this task.
- The first parity helper implementation lives in [evaluate_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/scripts/evaluate_crawl4ai_preprocessing_benchmark.py) and should stay additive until the migration gate passes.
- The current parity output is captured in [results.json](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_preprocessing_benchmark/results.json).
