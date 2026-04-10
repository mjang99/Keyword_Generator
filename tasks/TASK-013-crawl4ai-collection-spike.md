# TASK-013 Crawl4AI Collection Spike And Adoption Gate

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-006, TASK-011

## Goal

Determine whether Crawl4AI can become the production collection-worker fetch substrate for this service without weakening the current `NormalizedPageSnapshot` and evidence/OCR contracts.

## Scope

- Map the current collection contract to Crawl4AI outputs:
  - `decoded_text`
  - `visible_text_blocks`
  - `structured_data`
  - `image_candidates`
  - screenshot and raw artifact capture
- Evaluate Crawl4AI preprocessing/features:
  - `cleaned_html`
  - markdown generation
  - filtered markdown / pruning content filter
  - browser/session/cache/anti-bot controls
- Compare the current fetcher vs Crawl4AI on:
  - local fixtures
  - 3 fixed live URLs
- Define an explicit adoption gate:
  - quality first
  - latency increase is acceptable only if collection quality materially improves
- Produce one recommendation:
  - adopt now
  - adopt with limited scope
  - defer and keep the current HTTP seam

## Done When

- A written evaluation doc exists with exact comparison results and a recommendation.
- The evaluation states which current extraction responsibilities can move to Crawl4AI and which must remain custom.
- The evaluation states whether `decoded_text` should come from raw HTML parsing, `cleaned_html`, markdown, or a hybrid.
- The evaluation states whether `image_candidates[]` and screenshot capture are fully supported or still need custom extraction.
- A follow-up implementation task is drafted only if the adoption gate passes.

## Notes

- Use [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) Section 2.3 and Section 5.1 as the non-negotiable collection handoff boundary.
- Preserve current downstream expectations in `src/evidence/` and OCR policy; this spike does not redesign evidence assembly or OCR admission rules.
- Benchmark input is fixed to `fixtures + 3 live URLs`.
- Performance gate is fixed to `quality first`; measured latency regression is acceptable only when rendered text quality, structured data capture, or OCR candidate coverage improves materially.
- Prefer a hybrid migration shape unless the spike proves otherwise: use Crawl4AI for browser rendering and preprocessing, while keeping repo-owned normalization for snapshot shaping, classifier features, and OCR/evidence compatibility.
- The primary written artifact path is fixed to [CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md).
- Current phase is technical investigation and benchmark design only; no collection runtime migration belongs in this task.
- Initial technical investigation has started; see [CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_COLLECTION_SPIKE_2026-04-10.md).
- Initial investigation should land in the doc first; only after the capability and contract-fit findings are written down should benchmark execution begin.
- `TASK-014`, `TASK-015`, `TASK-016`, and `TASK-017` are complete.
- Final recommendation from the spike: `adopt with limited scope`, not a global fetcher replacement.

## Fixed Inputs

### Fixture Inputs

- Reuse existing collection fixtures that already exercise supported PDP, support/spec, blocked, and image-candidate behavior.
- Minimum fixture set:
  - `artifacts/service_test_pages/apple_airpodspro_kr.html`
  - `artifacts/service_test_pages/apple_airpodspro3_specs_ko.html`
  - existing local HTML snippets already locked in `tests/test_collection_html.py` for Samsung PDP, Rankingdak PDP title fallback, and blocked-page/WAF detection

### Live URL Inputs

- `https://www.apple.com/kr/shop/buy-iphone/iphone-16/6.7%ED%98%95-%EB%94%94%EC%8A%A4%ED%94%8C%EB%A0%88%EC%9D%B4-512gb-%ED%8B%B8`
- `https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/`
- `https://www.rankingdak.com/product/view?productCd=F000008814`

## Multi-Agent Split

- Agent 1: Crawl4AI capability research
  - confirm current official support for `cleaned_html`, markdown generation, filtered markdown / pruning, screenshot/media capture, cache modes, and anti-bot/session controls
  - produce a concise feature-to-requirement mapping for this repo
- Agent 2: Current collection-contract mapping
  - inspect current `NormalizedPageSnapshot`, classifier, evidence, and OCR dependencies
  - identify which fields can be sourced directly from Crawl4AI and which still require repo-owned normalization
- Agent 3: Benchmark design and measurement
  - define the exact comparison procedure for fixtures and live URLs
  - record the standard comparison table and pass/fail adoption gate
- Main agent: Synthesis and recommendation
  - consolidate the three workstreams into the fixed output doc
  - make one recommendation: `adopt now`, `adopt with limited scope`, or `defer`
  - open a follow-up implementation task only if the gate passes

## Standard Comparison Table

Every evaluated input must be compared with the same fields:

- `final_url` stability
- `http_status` / blocker or waiting compatibility
- `decoded_text` quality
- `visible_text_blocks` usefulness for downstream evidence
- `usable_text_chars`
- `structured_data` coverage
- `image_candidates[]` coverage and ranking suitability
- screenshot availability
- elapsed time
- extraction gaps or custom post-processing still required

## Mutation Constraints

- This spike may modify only `docs/` and `tasks/`.
- Do not modify `src/`, `tests/`, or infra code as part of the research task.
- If exploratory scripts or one-off commands are used, capture the findings in the fixed output doc instead of leaving partial implementation behind.

## Follow-Up Rule

- If the adoption gate fails, close the spike with a defer recommendation and do not open an implementation task.
- If the adoption gate passes, open exactly one follow-up task for integration planning/implementation, tentatively `TASK-014`, and keep that follow-up task separate from the research artifact.
