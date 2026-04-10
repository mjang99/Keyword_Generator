# TASK-020 Hybrid Product Extraction And Validation

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-019

## Goal

Implement and verify a hybrid extraction stage where deterministic selectors populate `core` fields and LLM-assisted extraction fills dynamic `attributes`.

## Scope

- Build selector-based extraction for `core` fields such as `name`, `price`, `rating`, `review_count`, and `options`.
- Add structured-data fallback for core fields.
- Add LLM-assisted attribute extraction using `cleaned_html` and `raw_text` only as a supplement.
- Implement merge rules between deterministic and LLM-derived outputs.
- Add a validation layer with `PASS/WARN/FAIL` outcomes.

## Done When

- The extraction stage can emit `core`, `attributes`, and `raw_text`.
- Validation catches missing/invalid core fields.
- LLM extraction is limited to supplementing attributes or generating proposals, not silently overriding canonical core fields.

## Notes

- Keep `core` deterministic by default.
- Do not let the first implementation depend on LLM for product identity or price as the primary source.
