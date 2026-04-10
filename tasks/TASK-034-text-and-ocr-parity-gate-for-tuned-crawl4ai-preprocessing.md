# TASK-034 Text And OCR Parity Gate For Tuned Crawl4AI Preprocessing

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-031, TASK-032, TASK-033

## Goal

Apply a new parity gate to the tuned Crawl4AI preprocessing candidates and decide whether any candidate is strong enough to reopen rollout planning after `TASK-028` previously failed.

## Scope

- Reuse the dual-path comparison approach from `TASK-025`.
- Reuse downstream parity expectations from `TASK-027`.
- Judge tuned candidates on:
  - classification parity
  - OCR trigger parity
  - admitted OCR block parity
  - evidence fact count and type parity
  - product-detail extraction completeness
- Hard fail conditions:
  - any blocker, waiting-room, or support-page misclassification
  - any supported commerce case becoming unsupported
  - loss of `product_name`, `brand`, or `product_category` evidence types
  - decorative/runtime assets re-entering OCR candidate sets
- Success bar to reopen migration:
  - live PDP median `decoded_text_chars` gain `>= 15%`
  - admitted OCR block median gain `>= 25%`
  - evidence fact count median `>= baseline`
  - `0` classification regressions on the fixed set
  - operator-reviewed product-detail recall improvement on at least `2` approved live URLs

## Done When

- A parity report exists for every surviving tuned candidate.
- The report states clearly whether any candidate beats the current `raw_html` baseline strongly enough to reopen migration work.
- If no candidate clears the bar, the report closes the retry path without reopening rollout planning.

## Notes

- This is a new gate after `TASK-028`; it does not modify the earlier failed decision.
- Reuse [TASK-025-dual-path-snapshot-parity-harness.md](/C:/Users/NHN/Repo/Keyword_Generator/tasks/TASK-025-dual-path-snapshot-parity-harness.md) and [TASK-027-downstream-parity-for-crawl4ai-preprocessing.md](/C:/Users/NHN/Repo/Keyword_Generator/tasks/TASK-027-downstream-parity-for-crawl4ai-preprocessing.md) rather than inventing new parity semantics.
- Result: gate failed. No tuned candidate cleared the reopen bar; `eligible_all` OCR yielded no measurable lift, `cleaned_html` showed no material quality win over `raw_html`, and markdown sources remained weaker. See [CRAWL4AI_TEXT_AND_OCR_TUNING_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_TEXT_AND_OCR_TUNING_DECISION.md).
