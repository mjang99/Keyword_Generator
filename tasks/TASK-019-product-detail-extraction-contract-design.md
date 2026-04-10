# TASK-019 Product Detail Extraction Contract Design

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-017

## Goal

Define the production contract for product-detail extraction so Crawl4AI-backed collection can enrich product data without replacing the current `NormalizedPageSnapshot` contract.

## Scope

- Define `core + attributes + raw_text` artifact schema.
- Define how the new extraction artifact relates to `NormalizedPageSnapshot`, evidence, and OCR outputs.
- Define required core fields and optional domain-specific attributes.
- Define persistence path and versioning strategy for the extraction artifact.
- Keep the current keyword-generation snapshot contract stable.

## Done When

- A written contract exists for `collection/product_detail_extraction.json`.
- The contract clearly separates `core`, `attributes`, `raw_text`, and extraction metadata.
- The contract states which fields remain in `NormalizedPageSnapshot` and which belong only to product-detail extraction.

## Notes

- Do not widen `NormalizedPageSnapshot` just to fit the new extraction shape.
- The new artifact must coexist with the current collection/classification/evidence pipeline.
