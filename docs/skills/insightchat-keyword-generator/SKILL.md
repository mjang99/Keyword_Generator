---
name: insightchat-keyword-generator
description: Support implementation, planning, and maintenance for the InsightChat URL Product Keyword Generator feature. Use when working on this repository or the connected main project for requirement interpretation, task shaping, architecture decisions, async job processing, URL content collection, OCR integration, Bedrock-based keyword generation, result export, or project-specific documentation updates.
---

# InsightChat Keyword Generator

## Start Here

1. Read `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md` first.
2. Treat `artifacts/` as source of truth and do not modify it.
3. Read `docs/OPERATING_MODEL.md`, `docs/GSTACK_WORKFLOW.md`, `docs/README.md`, `docs/AGENT_COLLABORATION.md`, and the relevant task files before making decisions.

## Working Rules

- Put interpretation, assumptions, and freshness notes in `docs/`.
- Put actionable work items in `tasks/`.
- Follow repo-local `gstack` workflow when planning, reviewing, or investigating.
- If the main project differs from `artifacts/`, record the delta in `docs/` with date and reason.
- Prefer reusing existing InsightChat patterns over inventing new infrastructure.

## Requirement Anchors

- Process up to 30 URLs per request.
- Return a job ID immediately and process asynchronously.
- Isolate failures per URL and support partial completion.
- Generate at least 100 keywords per URL across all 10 required categories.
- Separate Naver SA and Google SA outputs with match type and reason.
- Support OCR-enriched content extraction and sufficiency checks.
- Keep execution inside AWS and avoid external SaaS dependencies.
- Cache identical URL results for 7 days.

## Implementation Priorities

1. Confirm host application entry points and existing job infrastructure.
2. Define request, status, and result models before writing workers.
3. Reuse prior scraping and OCR assets when possible.
4. Add verification for category completeness, keyword count, partial failure behavior, and cache hits.

## References

- `docs/IMPLEMENTATION_READINESS.md`
- `docs/ARCHITECTURE_BASELINE.md`
- `docs/OPERATING_MODEL.md`
- `docs/GSTACK_WORKFLOW.md`
- `tasks/TASK-002-main-project-discovery.md`
- `tasks/TASK-003-implementation-readiness-check.md`
