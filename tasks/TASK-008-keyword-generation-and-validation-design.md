# TASK-008 Keyword Generation And Validation Design

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-004, TASK-007

## Goal

Define the canonical intent pipeline, category allocation, backfill order, dedup rules, platform validators, and repair-pass behavior.

## Scope

- Intent planner input and output model
- Category target allocation
- Backfill order and weak-tier cap
- Platform-specific validation rule
- Dedup normalization rule
- One repair-pass rule
- Curated taxonomy asset format
- Taxonomy storage location and versioning rule
- Generator and validator consumption of taxonomy entries

## Done When

- The requested platform can be validated without ambiguity for count and category coverage.
- `both` mode validator behavior is split explicitly between Naver and Google.
- Unsupported promo, fake price, and stock-urgency terms are enforceable by validation rules.
- Weak-tier cap enforcement and repair-pass behavior are documented with pass and fail examples.
- Taxonomy ownership is explicit, including source format, version handling, and how competitor, season/event, and problem vocab are loaded.

## Notes

- Use [KEYWORD_100_CRITERIA.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_100_CRITERIA.md) for category quality anchors.
- Use [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) for the policy baseline.
- Completed in [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) Section 4.2 with:
  - `Intent Planner` input/output contract and per-platform quota rules
  - positive-vs-negative quota split and `both` mode validator split
  - fixed backfill order, per-category evidence ceilings, and weak-tier cap
  - canonical intent dedup normalization and duplicate resolution
  - deterministic promo/price/stock validator rules and one repair-pass contract
  - curated taxonomy source, runtime bundle location, version pointer, and validator consumption rules
