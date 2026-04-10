# TASK-027 Downstream Parity For Crawl4AI Preprocessing

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-026

## Goal

Prove that a Crawl4AI-preprocessed snapshot source does not regress classifier, OCR, or evidence behavior before any default-path migration is allowed.

## Scope

- Run parity checks for:
  - `classify_snapshot()`
  - `run_ocr_policy()`
  - `build_evidence_pack()`
- Evaluate not only pass/fail but also:
  - `page_class`
  - `supported_for_generation`
  - OCR trigger reasons
  - admitted OCR blocks
  - evidence fact counts and types
  - thin-pack / quality-warning behavior
- Add focused regression tests for any accepted preprocessing-source change.

## Done When

- Parity results exist for fixtures and fixed live URLs.
- Known regressions are either fixed or documented as migration blockers.
- Accepted changes are locked with regression tests.

## Notes

- Any preprocessing source that hurts support-page classification, blocker detection, or OCR trigger behavior should fail this task.
- Use the parity output from [evaluate_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/scripts/evaluate_crawl4ai_preprocessing_benchmark.py) to localize whether regressions come from classification, OCR triggering/admission, or evidence assembly before touching runtime defaults.
- Current outcome: no non-raw candidate passed downstream parity strongly enough to justify rollout. See [CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md).
