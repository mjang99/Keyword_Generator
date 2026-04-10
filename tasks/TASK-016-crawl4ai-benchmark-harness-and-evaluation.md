# TASK-016 Crawl4AI Benchmark Harness And Evaluation

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-015

## Goal

Compare the existing HTTP fetcher against the Crawl4AI prototype on fixed fixtures and fixed live URLs, then write the results into the spike document.

## Scope

- Reuse the fixed fixture and live URL set already locked in `TASK-013`.
- Build a small benchmark harness for side-by-side evaluation.
- Measure the same comparison columns for every input.
- Record the benchmark table and the qualitative findings in `docs/CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md`.
- Keep the benchmark isolated from production runtime behavior.

## Done When

- The benchmark harness can run the baseline and prototype fetchers on the same cases.
- The evaluation doc contains a filled comparison table and a clear recommendation.
- The report states which collection responsibilities should stay custom.

## Notes

- Quality is the primary gate.
- Latency can regress only if rendered text quality, structured data capture, or OCR candidate coverage improves materially.
- Benchmark helper scaffolding landed and the fixed fixture/live matrix was executed into the spike report.
