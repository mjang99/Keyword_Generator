# TASK-022 Lambda-First Crawl Execution Boundary For Product Extraction

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-019, TASK-020

## Goal

Design the production execution boundary for browser-backed product-detail extraction with a Lambda-first operating model and a Fargate escape hatch.

## Scope

- Define `Lambda -> SQS -> Crawl Lambda` request/response contracts.
- Define raw artifact persistence for page HTML, DOM text, structured data, image manifest, and optional screenshot.
- Define queueing, retry, timeout, and backpressure behavior.
- Define the measurable thresholds that would justify moving the browser worker from Lambda to Fargate later.
- Keep default HTTP collection available where browser rendering is unnecessary.

## Done When

- A production-ready worker boundary is documented.
- The Lambda-first execution substrate is justified for browser runtime, latency, cost, and observability.
- The Fargate migration trigger conditions are explicit.
- The design preserves current async-job semantics and partial-failure isolation.

## Notes

- Lambda-first browser execution is the target first rollout design.
- Fargate remains an escape hatch if Lambda fan-out proves too slow, too expensive, or too fragile for the target domains.
- This task should lock the operating model before broad rollout.
