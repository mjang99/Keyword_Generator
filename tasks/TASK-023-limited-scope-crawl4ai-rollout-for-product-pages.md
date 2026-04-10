# TASK-023 Limited-Scope Crawl4AI Rollout For Product Pages

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-021, TASK-022

## Goal

Roll out Crawl4AI-backed product extraction only on approved fallback or domain-scoped paths, while keeping the current HTTP-first flow as the default.

## Scope

- Add routing rules for when to use `HttpPageFetcher` vs `Crawl4AiPageFetcher`.
- Limit initial rollout to a small set of JS-heavy or interaction-sensitive domains.
- Measure extraction quality, validation pass rates, and runtime cost per domain.
- Verify whether screenshot/media sidecars materially improve OCR or product-detail completeness.
- Keep rollback simple and immediate.

## Done When

- The rollout is limited to explicit domains or profiles.
- Quality and latency metrics exist for the rollout cohort.
- The system can roll back to the HTTP path without contract changes.

## Notes

- This is not a global fetcher replacement task.
- Promotion from limited rollout to default path requires a new decision gate.
