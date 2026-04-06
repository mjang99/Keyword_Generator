# TASK-007 Evidence Fallback And OCR Policy

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-004, TASK-006, TASK-011

## Goal

Define the evidence tiering, fallback rules, promo admissibility rules, OCR acceptance rules, and `quality_warning` inputs in implementation-ready form.

## Scope

- `direct`, `derived`, `inferred`, `weak` evidence contract
- Fallback fetch eligibility rule
- Same-product matching rule
- Promo admissibility and inadmissibility examples
- OCR candidate ranking and OCR text acceptance thresholds
- `quality_warning` trigger inputs

## Done When

- Fallback evidence rules define domain boundaries, identity-matching rules, and max-hop limits.
- OCR acceptance rules clearly reject banner, logo, and noise text while preserving useful product/spec text.
- URL-level `quality_warning` triggers are explicit and deterministic.

## Notes

- Start from [KEYWORD_SERVICE_TEST_FINDINGS.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_SERVICE_TEST_FINDINGS.md).
- Unsupported promo claims must remain blocked in v1.
- Use the stage and artifact boundaries from `TASK-011` instead of introducing new worker splits here.
- Locked output lives in `docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md` Section 4.1 plus the policy rows in Section 4.
- `Evidence Builder` may admit only facts that pass the `TASK-006` snapshot/classification boundaries and the same-product matching rules defined here.
