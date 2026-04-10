# TASK-017 Crawl4AI Adoption Decision And Migration Gate

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-016

## Goal

Convert the benchmark results into one explicit adoption decision and preserve the quality-first migration gate.

## Scope

- Review benchmark outcomes against the adoption gate.
- Decide one of `adopt now`, `adopt with limited scope`, or `defer`.
- Record the decision in the spike document and related task notes.
- Only open a follow-up implementation task if the gate passes.

## Done When

- The spike has one final recommendation.
- The recommendation is supported by the benchmark evidence.
- The follow-up implementation task is either opened or explicitly withheld.

## Notes

- Do not widen the collection contract until the gate passes.
- Keep the decision based on collection quality, not on browser novelty.
- Current recommendation: `adopt with limited scope`.
- The benchmark showed materially richer rendered text and sidecar media inventory, but not enough seam-level gain to justify replacing `HttpPageFetcher` globally.
