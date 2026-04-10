# Crawl4AI Collection Spike - 2026-04-10

## Status

- `TASK-013` is in progress.
- This document records the capability, contract-fit, and prototype-install findings before benchmark execution is complete.
- The benchmark execution phase is now in progress.
- Environment blocker: `.venv-dev` currently resolves to Python 3.14.3, and Crawl4AI's dependency set is not installing cleanly there because a required binary wheel falls back to a source build.
- Fallback plan: create a dedicated prototype environment with `C:\Users\NHN\.local\bin\python3.12.exe` and use that venv for the Crawl4AI install, smoke, and benchmark work.
- Prototype environment status:
  - `.venv-crawl4ai` was created as the dedicated Crawl4AI experiment environment
  - `crawl4ai==0.8.0` and `playwright==1.58.0` are installed there
  - Chromium is installed for Playwright
  - a minimal `AsyncWebCrawler` smoke against `https://example.com` succeeded
  - `crawl4ai-doctor` succeeds when `PYTHONIOENCODING=utf-8` is set; the default Windows `cp949` console path can throw a Unicode logging error
  - the repo-local `Crawl4AiPageFetcher` also completed a real fetch against `https://example.com` and returned rendered HTML through the stable `HtmlFetchResult` seam

## Prototype Progress

- `Crawl4AiPageFetcher` now exists behind the same `fetch(raw_url) -> HtmlFetchResult` seam as `HttpPageFetcher`.
- The current prototype keeps `HtmlFetchResult` stable and stores Crawl4AI-only comparison data as fetcher sidecars rather than widening the collection contract.
- Benchmark helper scaffolding now exists in `scripts/evaluate_collection_fetch_benchmark.py`.
- Seam-focused regression coverage exists for:
  - `Crawl4AiPageFetcher.fetch()` success/failure behavior
  - `HtmlCollectionPipeline` compatibility with the new fetcher
  - benchmark comparison-row helper functions

## Objective

Determine whether the collection worker should move from the current `HttpPageFetcher` seam to a Crawl4AI-backed browser fetcher without breaking the current `NormalizedPageSnapshot`, classifier, OCR, and evidence contracts.

## Fixed Inputs

### Fixture Inputs

- `artifacts/service_test_pages/apple_airpodspro_kr.html`
- `artifacts/service_test_pages/apple_airpodspro3_specs_ko.html`
- existing inline HTML cases in `tests/test_collection_html.py` for Samsung PDP, Rankingdak PDP title fallback, and blocked-page/WAF detection

### Live URL Inputs

- `https://www.apple.com/kr/shop/buy-iphone/iphone-16/6.7%ED%98%95-%EB%94%94%EC%8A%A4%ED%94%8C%EB%A0%88%EC%9D%B4-512gb-%ED%8B%B8`
- `https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/`
- `https://www.rankingdak.com/product/view?productCd=F000008814`

## Current Repo Contract

### Current Fetcher Shape

- The current runtime path is `HtmlCollectionPipeline -> collect_snapshot_from_html -> classify_snapshot -> run_ocr_policy -> build_evidence_pack`.
- The current fetcher seam is `HttpPageFetcher.fetch(raw_url) -> HtmlFetchResult`.
- `HttpPageFetcher` is HTML-first and profile-based; it retries request headers and preserves HTML bodies for HTTP error pages.

Key references:

- [pipeline.py](/C:/Users/NHN/Repo/Keyword_Generator/src/runtime/pipeline.py)
- [service.py](/C:/Users/NHN/Repo/Keyword_Generator/src/collection/service.py)
- [test_collection_fetcher.py](/C:/Users/NHN/Repo/Keyword_Generator/tests/test_collection_fetcher.py)
- [test_runtime_bedrock_live.py](/C:/Users/NHN/Repo/Keyword_Generator/tests/test_runtime_bedrock_live.py)

### Snapshot Fields Currently Derived From Fetch HTML

These fields are populated directly from fetched HTML in `collect_snapshot_from_html()`:

- `title`, `meta_description`, `canonical_tag`, `meta_locale`, `locale_detected`
- `decoded_text` from `_extract_visible_text(fetch_result.html)`
- `visible_text_blocks` from `_meaningful_visible_blocks_v2(decoded_text)`
- `structured_data` from `_extract_structured_data(fetch_result.html)`
- `image_candidates` from `_extract_image_candidates(fetch_result.html, fetch_result.final_url)`
- `product_name`, `primary_product_tokens`, `price_signals`, `buy_signals`, `stock_signals`, `promo_signals`, `support_signals`, `download_signals`, `blocker_signals`, `waiting_signals`
- classifier features such as `single_product_confidence`, `sellability_confidence`, `support_density`, `download_density`, `promo_density`, and `usable_text_chars`

These fields come from fetch metadata rather than HTML extraction:

- `raw_url`, `final_url`, `http_status`, `content_type`, `fetch_profile_used`
- `charset_selected`, `charset_confidence`, `mojibake_flags`

Important consequence:

- the fetcher boundary today is narrower than the target browser-worker design; screenshot and raw image/media metadata are expected by the design doc, but the current runtime contract only carries `image_candidates[]` and does not yet persist a collection screenshot artifact through the same seam

## Missing Investigation Closed

The missing part from the first investigation pass was the exact repo integration shape. That gap is now narrowed to one concrete prototype boundary:

- keep `collect_snapshot_from_html()` as the snapshot shaper
- keep `HtmlCollectionPipeline` and downstream classifier/OCR/evidence flow unchanged
- replace only the fetch implementation behind `fetcher.fetch(raw_url) -> HtmlFetchResult`

This keeps the experiment focused on the collection substrate rather than turning the spike into a migration.

## Integration Touchpoints

The exact repo-local touchpoints for a Crawl4AI prototype are:

- collection fetch seam export surface in [`src/collection/__init__.py`](/C:/Users/NHN/Repo/Keyword_Generator/src/collection/__init__.py)
- current fetch result model and fetcher implementation in [`src/collection/service.py`](/C:/Users/NHN/Repo/Keyword_Generator/src/collection/service.py#L62)
- runtime wiring that defaults to `HttpPageFetcher()` in [`src/runtime/service.py`](/C:/Users/NHN/Repo/Keyword_Generator/src/runtime/service.py#L118)
- collection pipeline resolver in [`src/runtime/pipeline.py`](/C:/Users/NHN/Repo/Keyword_Generator/src/runtime/pipeline.py#L44)

Safest prototype path:

- add a new browser-backed fetcher class alongside `HttpPageFetcher`
- keep the same `fetch(raw_url) -> HtmlFetchResult` interface
- inject it through `create_html_collection_runtime(..., fetcher=...)` or `create_html_collection_runtime_from_env(..., fetcher=...)`
- do not alter `collect_snapshot_from_html()`, `classify_snapshot()`, `run_ocr_policy()`, or `build_evidence_pack()` during the spike

## HtmlFetchResult Boundary

For the first prototype, `HtmlFetchResult` should remain stable:

- required today:
  - `raw_url`
  - `final_url`
  - `html`
  - `content_type`
  - `http_status`
  - `fetch_profile_used`
  - `response_headers`
  - `charset_selected`
  - `charset_confidence`
  - `mojibake_flags`

Recommended rule for the spike:

- do not expand `HtmlFetchResult` yet
- keep Crawl4AI-only artifacts such as screenshot bytes/base64, cleaned HTML, markdown, and raw media lists as prototype-side debug outputs or sidecar measurements
- only propose widening `HtmlFetchResult` after the benchmark proves those artifacts are necessary for the permanent collection seam

Reason:

- widening the seam too early would force snapshot, OCR, runtime, and persistence decisions before the adoption gate is passed

## Screenshot And Media Gap

Current repo gap between design and implementation:

- service design expects collection-stage screenshot capture and richer raw artifacts
- current runtime seam does not pass screenshot or raw media payloads through `HtmlFetchResult`
- OCR policy operates only on `image_candidates[]` already materialized into `NormalizedPageSnapshot`

Relevant references:

- collection artifact expectations in [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md#L172)
- current persisted artifact keys in [service.py](/C:/Users/NHN/Repo/Keyword_Generator/src/runtime/service.py#L830)
- current success/failure runtime payload model in [models.py](/C:/Users/NHN/Repo/Keyword_Generator/src/runtime/models.py)

Therefore the prototype should evaluate screenshot/media usefulness without immediately making them part of the stable seam.

## Prototype Recommendation

The safest prototype shape is:

- Crawl4AI fetcher performs browser render and returns final rendered HTML through `HtmlFetchResult.html`
- existing repo logic continues to derive:
  - `decoded_text`
  - `visible_text_blocks`
  - `structured_data`
  - `image_candidates[]`
  - classifier features
- prototype also records non-seam debug artifacts for comparison only:
  - `cleaned_html`
  - markdown / `fit_markdown`
  - screenshot presence
  - Crawl4AI media inventory summary

This lets the benchmark answer whether Crawl4AI materially improves collection quality before the repo commits to any contract expansion.

## Downstream Dependencies

### Classifier

The classifier depends heavily on:

- `decoded_text`
- `price_signals`, `buy_signals`, `support_signals`, `download_signals`, `promo_signals`
- `blocker_signals` and `waiting_signals`
- `structured_data`
- `product_name` and `primary_product_tokens`
- `usable_text_chars`

Risk:

- changing the text source from raw visible DOM text to a more aggressively cleaned or markdown-shaped source can alter page class outcomes, especially for support/spec, blocker, and promo-heavy classifications

### OCR Policy

The OCR policy depends on:

- `usable_text_chars`
- `charset_confidence`
- `page_class_hint`
- `image_candidates[]`
- `ocr_trigger_reasons`

The design contract also expects screenshot OCR as a first-class path when visible text is thin or charset confidence is low, but the current seam does not yet model screenshot capture in the same way the service design describes.

Risk:

- Crawl4AI media extraction may help with image discovery, but the repo still needs deterministic ranking and rejection rules around `image_candidates[]`
- if `decoded_text` becomes much shorter after filtering, OCR may trigger more often

### Evidence Builder

The evidence builder depends on:

- `decoded_text`
- `visible_text_blocks`
- `structured_data`
- `product_name`
- OCR-admitted blocks downstream

Risk:

- `visible_text_blocks` currently come from splitting `decoded_text`; switching to `cleaned_html` or markdown may collapse block structure and reduce evidence quality even if top-level text looks cleaner

## Crawl4AI Capability Fit

Initial doc review suggests Crawl4AI can cover a meaningful portion of the target collection-worker contract.

### Strong Matches

- `result.html` provides original final-page HTML
- `result.cleaned_html` provides sanitized HTML with scripts, styles, and excluded tags removed
- markdown generation is first-class and supports:
  - raw markdown
  - `fit_markdown`
  - `fit_html`
  - content filters such as pruning or BM25
- `result.media` exposes discovered images, videos, and audio with fields such as `src`, `alt`, and heuristic `score`
- `result.screenshot` can return a base64 screenshot when enabled
- browser/runtime config supports:
  - `BrowserConfig`
  - `CrawlerRunConfig`
  - cache modes
  - persistent context / `user_data_dir`
  - cookies / headers
  - random user-agent mode
  - stealth / anti-bot settings
  - popup and overlay removal
  - interaction helpers such as `simulate_user`, `override_navigator`, and `magic`

### Likely Good Fit For This Repo

- browser-rendered HTML acquisition for `standard_render`
- `stealth_render` experiments using stealth, managed-browser, or undetected-browser options
- markdown or filtered-content experiments for alternative `decoded_text` sources
- richer image/media discovery than the current regex-only HTML extraction
- screenshot capture for the OCR branch

### Gaps Or Cautions

- current repo downstream logic expects repo-owned `visible_text_blocks` semantics; Crawl4AI does not directly provide that same contract, so block shaping likely remains custom
- current repo image ranking and rejection logic is highly policy-specific; Crawl4AI media scores can help but should not replace repo-owned OCR candidate filtering without proof
- `fit_markdown` and `fit_html` are present only when a content filter is configured; they should be treated as optional experimental inputs, not guaranteed defaults
- session-management guidance favors sequential or identity-based reuse; our planned collection-worker concurrency still needs explicit rules
- anti-bot options exist, but the repo still needs a deterministic mapping to `standard_render -> stealth_render -> extended_wait_popup_dismiss`

## Recommended Migration Shape

Current recommendation is still a hybrid shape, not a full replacement of collection normalization:

Use Crawl4AI for:

- rendered navigation and final HTML capture
- screenshot capture
- media discovery
- optional cleaned/fit HTML and markdown generation
- anti-bot and popup-dismiss experimentation

Keep repo-owned normalization for:

- `NormalizedPageSnapshot` construction
- `visible_text_blocks` shaping
- classifier signal derivation
- OCR candidate ranking and rejection
- evidence compatibility

## Benchmark Results

### Fixture Parity

| Case | Mode | Page class | Supported | Usable text chars | Structured data | Image candidates |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `apple_airpodspro_fixture` | `fixture_html` | `commerce_pdp` | `true` | 21475 | 2 | 30 |
| `apple_airpodspro_fixture` | `crawl4ai_fixture_adapter` | `commerce_pdp` | `true` | 21475 | 2 | 30 |
| `apple_airpodspro3_specs_fixture` | `fixture_html` | `support_spec_page` | `true` | 10309 | 0 | 2 |
| `apple_airpodspro3_specs_fixture` | `crawl4ai_fixture_adapter` | `support_spec_page` | `true` | 10309 | 0 | 2 |

Fixture conclusion:

- The fetcher seam preserves snapshot/classification behavior when the underlying HTML is the same.
- No contract drift was observed at the `HtmlFetchResult -> collect_snapshot_from_html()` boundary.

### Live URL Comparison

| Case | Mode | Final URL stability | HTTP | Page class | Usable text chars | Structured data | Image candidates | Elapsed seconds | Sidecars |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| `apple_iphone16` | `http` | canonicalized to `/shop/buy-iphone/iphone-16` | 200 | `commerce_pdp` | 12809 | 4 | 30 | 1.782 | none |
| `apple_iphone16` | `crawl4ai` | kept raw variant URL; status surfaced as 301 | 301 | `commerce_pdp` | 22488 | 4 | 30 | 27.059 | cleaned HTML, markdown, media images=17 |
| `samsung_s25_case` | `http` | stable | 200 | `commerce_pdp` | 23791 | 3 | 30 | 0.662 | none |
| `samsung_s25_case` | `crawl4ai` | stable | 200 | `commerce_pdp` | 33489 | 3 | 30 | 20.586 | cleaned HTML, markdown, media images=34, videos=2 |
| `rankingdak_chicken` | `http` | stable | 200 | `commerce_pdp` | 11528 | 0 | 30 | 0.754 | none |
| `rankingdak_chicken` | `crawl4ai` | stable | 200 | `commerce_pdp` | 21868 | 0 | 30 | 20.538 | cleaned HTML, markdown, media images=73 |

Live benchmark conclusions:

- Crawl4AI materially increased `usable_text_chars` on all three live PDPs.
- Page-class outcomes did not improve because the baseline HTTP path already classified all three cases correctly as supported commerce PDPs.
- `structured_data` counts stayed flat across all three live cases.
- `image_candidates[]` counts stayed flat because the current repo-owned extractor still caps/ranks from HTML into the stable snapshot contract.
- Crawl4AI sidecars exposed richer raw media inventories than the stable seam currently preserves.
- Latency regressed sharply, from roughly `0.7s-1.8s` to `20s-27s`.
- Apple showed weaker final-URL normalization on the Crawl4AI path because the fetch returned rendered content while still surfacing a `301` / raw variant URL combination.

## Preprocessing Source Benchmark

The live fetch benchmark above only answers whether a browser-backed fetcher is useful behind the current seam. It does not yet answer which text-preprocessing source should drive `decoded_text` and `visible_text_blocks` if Crawl4AI is adopted for limited-scope fallback or later broader rollout.

This benchmark must compare four candidate sources extracted from the same Crawl4AI fetch result:

- `raw_html`
  - definition: repo-owned extraction from browser-rendered `result.html`
  - intended use: current baseline semantics with a browser-rendered HTML source
- `cleaned_html`
  - definition: repo-owned extraction from Crawl4AI `result.cleaned_html`
  - intended use: remove script/style/chrome noise while preserving HTML structure
- `markdown`
  - definition: Crawl4AI markdown output without fit/pruning reduction
  - intended use: assess whether markdown is a better direct source for `decoded_text`
- `fit_markdown`
  - definition: Crawl4AI filtered markdown generated with a configured content filter
  - intended use: assess whether aggressive content filtering improves evidence quality enough to justify structure loss

### Candidate-Source Rules

- `title`, `meta_description`, `canonical_tag`, `meta_locale`, `structured_data`, and `image_candidates[]` must continue to come from rendered HTML for this benchmark.
- Only the source material for `decoded_text` and derived `visible_text_blocks` should vary.
- `raw_html` and `cleaned_html` candidates must continue to use repo-owned text extraction and block shaping.
- `markdown` and `fit_markdown` candidates must be converted into the current snapshot text fields without changing downstream classifier, OCR, or evidence-builder behavior.
- No candidate may change classifier thresholds, OCR admission rules, or evidence promotion rules during the benchmark.

### Proposed Measurement Table

The preprocessing benchmark report should contain one row per `{case_id, candidate_source}` with these required columns:

| Column | Meaning |
| --- | --- |
| `case_id` | Stable case label such as `apple_iphone16` or `apple_airpodspro_fixture` |
| `case_type` | `fixture` or `live` |
| `candidate_source` | One of `raw_html`, `cleaned_html`, `markdown`, `fit_markdown` |
| `fetch_mode` | `http` or `crawl4ai` |
| `final_url` | Final URL used for extraction |
| `http_status` | Status observed at fetch time |
| `page_class` | Classifier output |
| `supported_for_generation` | `true` or `false` |
| `decoded_text_chars` | Character count of the candidate-derived `decoded_text` |
| `visible_block_count` | Count of candidate-derived `visible_text_blocks` |
| `structured_data_count` | Count of structured-data nodes; should stay constant across candidates for the same fetch |
| `image_candidate_count` | Count of ranked image candidates; should stay constant across candidates for the same fetch |
| `ocr_trigger_reasons` | Joined trigger reasons after snapshot shaping |
| `evidence_fact_count` | Fact count from `build_evidence_pack()` |
| `quality_warning` | Final quality warning state on the evidence pack |
| `elapsed_seconds` | End-to-end elapsed time for shaping plus classify/OCR-policy/evidence steps |
| `source_loss_notes` | Short note on obvious losses such as nav collapse, block collapse, or missing spec text |
| `recommendation_flag` | `keep_testing`, `reject`, or `candidate` |

### Acceptance Gate For Source Selection

- Reject a candidate if it changes correct supported-vs-terminal classification on a fixed case.
- Reject a candidate if it materially reduces evidence usefulness through block collapse even when top-line char count improves.
- Prefer `cleaned_html` over markdown-derived candidates when quality is similar, because HTML-based extraction better preserves current repo semantics.
- Do not promote `fit_markdown` unless it shows a clear evidence-quality win on noisy live pages without causing support/spec or blocker misclassification.
- A source can be considered a limited-rollout `candidate` only if it improves `decoded_text` usefulness or evidence quality on at least one live PDP class without regressing the fixed fixture cases.

### Current Implementation Status

- The first benchmark/parity harness is implemented in [evaluate_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/scripts/evaluate_crawl4ai_preprocessing_benchmark.py).
- Coverage for the additive harness exists in [test_crawl4ai_preprocessing_benchmark.py](/C:/Users/NHN/Repo/Keyword_Generator/tests/test_crawl4ai_preprocessing_benchmark.py).
- Current scope of the harness:
  - keep rendered HTML as the canonical source for `title`, `meta_description`, `structured_data`, and `image_candidates[]`
  - swap only the candidate text source for `decoded_text` and `visible_text_blocks`
  - emit benchmark rows and downstream parity diffs for classification, OCR, and evidence
- Remaining work:
  - run the harness across the fixed fixture and live set
  - write the comparison rows into the preprocessing migration decision artifacts
  - decide whether any source is eligible for Lambda-first limited rollout

### Executed Benchmark Result

- Fixed cases evaluated: `5`
- Candidate rows evaluated: `20`
- Live cases evaluated: `3`
- Candidate rows promoted to `candidate`: `0`
- Artifact outputs:
  - [results.json](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_preprocessing_benchmark/results.json)
  - [summary.md](/C:/Users/NHN/Repo/Keyword_Generator/artifacts/crawl4ai_preprocessing_benchmark/summary.md)
  - [CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PREPROCESSING_MIGRATION_DECISION.md)

Observed result:

- `raw_html` remained the best-performing source on all three fixed live PDPs.
- `cleaned_html` preserved live classification but did not produce a material downstream win.
- `markdown` reduced text volume on all three fixed live PDPs and did not justify canonical promotion.
- `fit_markdown` was not available under the current Crawl4AI setup and is not a rollout candidate.

Decision:

- Keep Crawl4AI preprocessing experimental only.
- Do not start limited rollout for preprocessed snapshots.

## Adoption Decision

Recommendation: `adopt with limited scope`

Reasoning:

- Do not replace `HttpPageFetcher` globally right now.
- The quality gain is real, but in the current seam it mostly shows up as richer rendered text and richer sidecar media inventory.
- The current stable snapshot contract did not show corresponding gains in `structured_data`, `image_candidates[]`, or page-class correctness on the fixed live set.
- The latency regression is too large to justify a default-path replacement for pages that already work with the HTTP fetcher.
- The prototype is still valuable because it proves a browser-backed fetcher can sit behind the existing seam and can be reserved for cases where rendering quality matters more than latency.

Recommended limited-scope rollout:

- Keep `HttpPageFetcher` as the default fetch path.
- Use `Crawl4AiPageFetcher` as an explicit fallback or targeted profile for:
  - JS-heavy PDPs that underperform on plain HTTP fetch
  - anti-bot or interaction-sensitive fetch profiles
  - future screenshot or richer media-capture experiments for OCR escalation
- Do not switch `decoded_text` wholesale to markdown or `cleaned_html` yet.
- Do not widen `HtmlFetchResult` until the fallback path proves that screenshot/media artifacts materially improve OCR/evidence outcomes.

## Primary Sources

- Crawl4AI Markdown Generation docs: https://docs.crawl4ai.com/core/markdown-generation/
- Crawl4AI CrawlResult docs: https://docs.crawl4ai.com/api/crawl-result/
- Crawl4AI Cache Modes docs: https://docs.crawl4ai.com/core/cache-modes/
- Crawl4AI Browser/Crawler Config docs: https://docs.crawl4ai.com/core/browser-crawler-config/
- Crawl4AI Page Interaction docs: https://docs.crawl4ai.com/core/page-interaction/
- Crawl4AI Undetected Browser docs: https://docs.crawl4ai.com/advanced/undetected-browser/
- Crawl4AI Hooks/Auth docs: https://docs.crawl4ai.com/advanced/hooks-auth/

## Next Steps

1. Execute `TASK-018` as a limited-scope integration task, not a global replacement.
2. Add runtime selection rules for when to fall back from `HttpPageFetcher` to `Crawl4AiPageFetcher`.
3. Measure whether screenshot/media sidecars materially improve OCR/evidence quality before widening the stable contract.
4. Revisit filtered markdown / `fit_markdown` only after content-filter configuration is benchmarked explicitly.
