# TASK-006 Page Collection And Classification Design

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-002, TASK-003, TASK-004, TASK-011

## Goal

Turn the v1 collection and page-classification portion of the design into an implementation-ready task spec.

## Scope

- URL canonicalization rule
- Fetch profile sequence
- Charset normalization rule
- Raw snapshot and normalized snapshot contract
- Page type classifier input and output contract
- Terminal-fail vs supported-page decision rule

## Done When

- Classification rules are defined for `commerce_pdp`, `image_heavy_commerce_pdp`, `marketing_only_pdp`, `product_marketing_page`, `support_spec_page`, `document_download_heavy_support_page`, `blocked_page`, `waiting_page`, `non_product_page`, and `promo_heavy_commerce_landing`.
- The snapshot contract is explicit enough for the evidence builder to consume without extra assumptions.
- Acceptance fixtures are identified from local sample HTML files.

## Notes

- Use [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) pipeline steps 1-9 as the baseline.
- Use [SERVICE_TEST_MATRIX.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/SERVICE_TEST_MATRIX.md) as the first fixture source.
- Consume runtime and worker-boundary decisions from `TASK-011` instead of redefining them here.
- Locked output lives in `docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md` Section 2.3 and the expanded `NormalizedPageSnapshot` entity in Section 3.1.
- Fixture-to-class expectations are fixed against `artifacts/service_test_pages/` so later collection tests can assert classification without inventing new acceptance sources.
