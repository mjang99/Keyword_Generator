# URL-Based Product Keyword Generator Service Design

> Prepared on 2026-04-03.
> Constraint: preserve the fixed output schema from `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md`.
> Scope: internal processing, evidence policy, page classification, fallback policy, and AWS architecture.

## 1. Design Summary

This service is a standalone AWS-native async pipeline that converts each input URL into a `Normalized Evidence Pack`, classifies the page before generation, creates a `Canonical Intent Pool`, renders fixed-schema keyword rows for the requested ad platform, validates count and category coverage, and exports per-URL JSON plus combined JSON/CSV.

Core design choices:

- Preserve the requirement schema exactly; all richer metadata stays internal.
- Treat each URL as an isolated unit of work with its own retries, state, evidence, warning state, and failure reason.
- Quality is the primary optimization target in v1. Cost reduction is deferred until quality baselines are validated.
- Post-processing (semantic deduplication, quality evaluation, and supplementation) is LLM-driven via structured multi-prompt pipeline. Deterministic code owns only hard compliance checks (promo, fake price, stock urgency, competitor safety) where factual accuracy cannot be delegated to the model.
- Fail early for `blocked_page`, `waiting_page`, `non_product_page`, and `promo_heavy_commerce_landing`.
- Allow `commerce_pdp`, `image_heavy_commerce_pdp`, `marketing_only_pdp`, `product_marketing_page`, `support_spec_page`, and `document_download_heavy_support_page` to proceed under stricter evidence rules.
- Platform request mode is explicit in v1. `naver_sa` generates and validates Naver only, `google_sa` generates and validates Google only, and `both` generates and validates both platforms independently from one shared evidence pack.
- Apply `quality_warning` conservatively. It becomes `true` when fallback evidence is used, weak-tier backfill is used, or the final supported page class is support-heavy or otherwise sparse.

## 2. Processing Pipeline

1. `POST /jobs` validates auth, URL count `<=30`, notification target, and requested platform.
2. Each URL is canonicalized for cache lookup: lowercase host, remove fragment, remove known tracking params, preserve product-identifying params, preserve path, and store raw URL separately.
3. The API layer creates one `Job` record and one `UrlTask` record per URL, then checks the 30-day cache. Cache lookup resolves in this order: exact `requested_platform_mode` key first, then platform-component reuse (`naver_sa` + `google_sa` → `both`, or `both` → single-platform extraction). See Section 3.4 for cache key format and reuse rules.
4. Cache hits are copied into job-scoped result paths immediately and marked `COMPLETED_CACHED`.
5. Cache misses go to `CollectionQueue`.
6. The collection worker fetches with deterministic profiles in order: `standard browser render`, `stealth browser render`, `extended wait + popup dismissal`. It stores raw HTML, rendered DOM text, structured data, screenshot, and ranked image candidates in S3.
7. Charset normalization runs before extraction. The worker builds a `NormalizedPageSnapshot`, extracts direct facts, and classifies the page with rules first and Bedrock only as a tie-breaker.
8. If the page class is terminal-fail, the task is marked failed and sent to aggregation.
9. If the page class is supported, OCR policy decides whether to run screenshot OCR and ranked asset OCR. OCR output is merged into the evidence pack only after filtering.
10. `Evidence Builder` computes product identity, sellability, stock state, sufficiency, locale, promo admissibility, and fallback eligibility.
11. If the exact page is thin but product-specific, `Evidence Builder` may fetch same-product support/spec/doc pages from the same root domain or approved sibling domain. Promo fallback is narrower: a directly linked promo/event page is fetchable only when the link appears on the exact page and explicitly names the same product or SKU.
12. `Intent Planner` sets generation targets: category quotas, platform targets, evidence tier ceilings, and an over-generation budget (~160 candidates per platform) to absorb dedup loss.
13. `Keyword Generator` calls Bedrock once with the evidence pack and targets to produce the over-generation candidate set. It cannot invent facts outside admitted evidence and approved taxonomy entries.
14. `Dedup & Quality Evaluator` calls Bedrock once to (a) semantically deduplicate candidates (intent-level, not string-level), (b) score each surviving keyword's quality with a justification, and (c) flag categories that are still short after dedup.
15. If all platform floors (`>=100` positive, all 9 categories present, `>=1` negative) are met after dedup → proceed to step 15b. If any gap remains → `Keyword Supplementor` calls Bedrock once more, targeting only the missing categories or shortfall count. After supplementation, the surviving set must meet floors; if not, the URL is marked `FAILED_GENERATION`.
15b. Hard rule pass (deterministic): drop rows that violate promo, fake-price, stock-urgency, or competitor-safety rules. If the post-drop set still meets floors → write results. If not → `FAILED_GENERATION`.
16. Successful URL results are written to S3 as fixed-schema JSON rows plus internal evidence metadata. The final result is also written into the 30-day cache. Cache is written per platform component (`naver_sa` and `google_sa` stored separately) so that future requests with a different platform mode can reuse components. See Section 3.4 for staleness-check policy.
17. `Job Aggregator` tracks terminal URL states. When all URL tasks are terminal, it writes combined JSON, flattened CSV, `failures.json`, updates job status to `COMPLETED`, `PARTIAL_COMPLETED`, or `FAILED`, and sends exactly one SES/webhook notification.

### 2.1 External API Contract

This section locks the handler-facing API contract only. It does not own rendered CSV or combined JSON examples.

`POST /jobs`

- Auth: Cognito-authenticated caller. `job_id` visibility is scoped to the authenticated `user_sub`.
- Purpose: accept up to 30 product URLs, create one `Job`, create one `UrlTask` per distinct input URL position, perform cache lookup, and fan out misses asynchronously.
- Request body:
  - `urls`: required array, length `1..30`, preserves caller order, duplicates allowed and tracked as separate `url_task_id` values inside the job
  - `requested_platform_mode`: optional enum `naver_sa | google_sa | both`, default `both`
  - `notification_target`: optional object, exactly one of `email` or `webhook`
  - `client_request_id`: optional caller-supplied idempotency token for safe retries at the API edge
- Synchronous validation failures:
  - `400` malformed body, invalid URL, unsupported notification shape, duplicate notification channels
  - `401/403` auth failure or cross-user access attempt
  - `409` duplicate `client_request_id` with a conflicting payload
  - `422` more than 30 URLs or unsupported `requested_platform_mode`
- Success response: `202 Accepted`
  - `job_id`
  - `status`: always `RECEIVED`
  - `requested_platform_mode`
  - `submitted_count`
  - `cached_count` at submit time if cache hits were materialized immediately, otherwise `0`
  - `created_at`
  - `status_url`
  - `result_manifest_url`: stable URL for later artifact lookup; returns `409 not_ready` until the job is terminal

`GET /jobs/{job_id}`

- Purpose: return the job lifecycle payload with job counters, URL-task summaries, and download-manifest references when terminal.
- Success response: `200 OK`
  - `job_id`
  - `status`
  - `requested_platform_mode`
  - `counts`
  - `artifacts`
  - `url_tasks`
  - `notification`
- Error response:
  - `404` when the `job_id` does not exist for that user
  - `409` is not used here; non-terminal jobs still return `200` with empty terminal-only artifact fields

`GET /jobs/{job_id}/results/{artifact_name}`

- Purpose: return a redirect or signed URL for a terminal artifact.
- Allowed `artifact_name` values in v1: `per_url_manifest`, `combined_json`, `combined_csv`, `failures_json`
- Success response: `302` redirect or `200` signed-URL envelope, depending on API Gateway deployment style
- Error response:
  - `404` unknown job or artifact name for that job
  - `409` when the requested artifact is not yet available because the job is not terminal

### 2.2 Platform Mode Contract

- `naver_sa`: generation, validation, cache identity, and result manifests are scoped to Naver only. The fixed-schema renderer must leave `google_match` blank on every emitted row.
- `google_sa`: generation, validation, cache identity, and result manifests are scoped to Google only. The fixed-schema renderer must leave `naver_match` blank on every emitted row.
- `both`: one shared evidence pack feeds one canonical intent pool, but validation happens independently for Naver and Google. The contract boundary between validator and exporter must preserve per-platform admitted rows so export can later flatten them without regenerating or revalidating.
- `both` never means "generate one shared 100-row set". It means "produce one Naver-valid set and one Google-valid set from the same URL evidence".
- Cache identity is tracked per platform component. See Section 3.4 for the full reuse rules:
  - `both` request: exact `both` cache hit → serve immediately. If no `both` cache but both `naver_sa` and `google_sa` component caches exist → merge components, serve as `both`, write merged `both` cache entry. Otherwise treat as cache miss.
  - `naver_sa` or `google_sa` request: exact component cache hit → serve immediately. If no component cache but `both` cache exists → extract the relevant platform component, serve it, write the component cache entry. Otherwise treat as cache miss.

### 2.3 Collection And Classification Contract

This section locks the implementation-facing contract for pipeline steps 2 through 9. It consumes the worker boundaries from Section 5 and does not redefine them.

#### 2.3.1 URL Canonicalization

- Canonicalization is computed once in `Submit Lambda` and reused by collection, cache lookup, status payloads, and exports.
- Normalize scheme and host to lowercase.
- Remove URL fragments entirely.
- Remove default ports `:80` for `http` and `:443` for `https`.
- Preserve the path exactly except:
  - collapse duplicate slashes
  - remove a trailing slash only when the path is not root
- Remove known tracking parameters by exact key or prefix:
  - exact keys: `fbclid`, `gclid`, `gbraid`, `wbraid`, `igshid`, `mc_cid`, `mc_eid`, `ref`, `source`, `src`, `_hsenc`, `_hsmi`
  - prefixes: `utm_`
- Preserve all remaining non-empty query parameters, because v1 cannot safely distinguish product identity parameters from legitimate routing parameters across merchants.
- Sort preserved query parameters by key then by value so cache identity is stable across equivalent caller orderings.
- Do not lowercase the path or query values. Model names and SKUs may be case-sensitive.
- Save both values:
  - `raw_url`: exact caller input
  - `canonical_url`: normalized URL used for cache and dedup

#### 2.3.2 Fetch Profile Sequence

| Profile | When used | Minimum behavior | Advance to next profile when |
| --- | --- | --- | --- |
| `standard_render` | first attempt for every cache miss | Fresh browser context, JS render, wait for DOM ready plus short network idle, capture final URL, HTML, visible text, screenshot, structured data, and image candidates | hard blocker, interstitial, unstable DOM, or missing stable product facts |
| `stealth_render` | only after `standard_render` fails | New browser context with bot-resistance settings, same artifact capture contract, same URL only | blocker/interstitial still dominates or normalized snapshot still unstable |
| `extended_wait_popup_dismiss` | final collection profile | New clean session, longer wait budget, dismiss obvious cookie/banner/modal blockers, re-capture the same artifact set | blocker/interstitial still dominates or normalized snapshot still fails minimum stability checks |

- Collection retry order is strict and deterministic: `standard_render -> stealth_render -> extended_wait_popup_dismiss`.
- Collection never changes the input URL intentionally except through normal redirects. Redirect targets are recorded in `final_url`.
- A fetch profile is considered usable only when it yields a stable `final_url`, decodable HTML or rendered DOM text, and a consistent visible-text snapshot. Otherwise the worker advances or fails.
- If a profile already yields a stable supported page class, later profiles are not attempted.

#### 2.3.3 Charset Normalization

- Charset decode priority is fixed: `BOM -> HTTP header -> meta charset -> detector`.
- If decoded text trips mojibake heuristics, retry decode candidates in this order: `utf-8`, `cp949/euc-kr`, then `latin1` recovery.
- Select the decode result with the highest combined Korean/English language score and the lowest mojibake penalty.
- After decoding, normalize with:
  - HTML entity decode
  - Unicode NFKC
  - whitespace collapse
  - removal of duplicate navigation/footer boilerplate blocks when the same block repeats more than once
- Record `charset_selected`, `charset_confidence`, and `mojibake_flags` on the normalized snapshot so downstream tasks know whether OCR or fallback should be favored.

#### 2.3.4 Raw Snapshot Contract

Collection must persist the following raw artifacts before classification emits a downstream message:

- `raw/request.json`
  - `raw_url`
  - `canonical_url`
  - `fetch_profile_used`
  - `fetched_at`
- `raw/fetch_response.json`
  - `http_status`
  - `content_type`
  - `redirect_chain`
  - `final_url`
  - `response_headers`
- `raw/page.html`
  - raw fetched HTML after the selected profile
- `raw/dom.txt`
  - visible text extracted from the rendered DOM before evidence filtering
- `raw/screenshot.png`
  - selected page screenshot used later for OCR if needed
- `raw/structured_data.json`
  - all parsed JSON-LD, microdata, or inline offer/product payloads
- `raw/image_manifest.json`
  - candidate page images with URL, dimensions, DOM position, alt text, and ranking features

#### 2.3.5 Normalized Snapshot Contract

`NormalizedPageSnapshot` is the exact handoff contract from collection to classification and later evidence building. The worker must write `collection/normalized_snapshot.json` with at least:

- identity and fetch metadata:
  - `raw_url`
  - `canonical_url`
  - `final_url`
  - `http_status`
  - `content_type`
  - `fetch_profile_used`
  - `fetched_at`
- decode and locale metadata:
  - `charset_selected`
  - `charset_confidence`
  - `mojibake_flags[]`
  - `meta_locale`
  - `language_scores`
- normalized content:
  - `title`
  - `meta_description`
  - `canonical_tag`
  - `decoded_text`
  - `visible_text_blocks[]`
  - `breadcrumbs[]`
  - `structured_data`
- extracted signal groups:
  - `primary_product_tokens[]`
  - `price_signals[]`
  - `buy_signals[]`
  - `stock_signals[]`
  - `promo_signals[]`
  - `support_signals[]`
  - `download_signals[]`
  - `blocker_signals[]`
  - `waiting_signals[]`
- image and OCR preparation:
  - `image_candidates[]`
  - `ocr_trigger_reasons[]`
  - `ocr_text_blocks` as an empty list at collection time
- classifier features:
  - `single_product_confidence`
  - `sellability_confidence`
  - `support_density`
  - `download_density`
  - `promo_density`
  - `usable_text_chars`

- `decoded_text` is the normalized main text blob used for feature extraction. It must exclude obvious script/style noise but may still include merchandising chrome.
- `visible_text_blocks[]` preserves block-level text with DOM position so later tasks can rank evidence and OCR supplementation without reparsing HTML.
- `image_candidates[]` is the only collection-stage source that OCR may consume. Later tasks should not rescan raw HTML for images.

#### 2.3.6 Classifier Input And Output Contract

- The classifier is rules-first. Bedrock is a tie-breaker only when the top two rule-based classes are within `0.15` confidence and the choice changes supported-vs-terminal behavior.
- **Bedrock must always answer the explicit primary question**: "Is this URL a product description or sales page (판매/구매 유도 페이지)?" regardless of confidence level. This check is not a tie-break; it is a mandatory first gate. If Bedrock determines the page has no product sales intent (e.g., a pure support, FAQ, download, or editorial page), the classifier must assign `non_product_page` or `support_spec_page` before any other class scoring proceeds.
- Support, spec, FAQ, and download-heavy pages with no purchase signal are classified `support_spec_page` (if one product identity is clear) or `non_product_page` (if product identity is absent or multi-product).
- Classifier input is exactly:
  - `NormalizedPageSnapshot`
  - collection attempt history for the current `url_task_id`
  - merchant/domain allowlists from configuration
- Classifier output must be written to `collection/page_classification.json` with:
  - `page_class`
  - `supported_for_generation` boolean
  - `confidence`
  - `decisive_signals[]`
  - `rejected_candidate_classes[]`
  - `failure_code_candidate` when terminal

#### 2.3.7 Page-Class Decision Rules

Class precedence is evaluated in this order so terminal blocker states win before product-specific classes are considered:

1. `blocked_page`
2. `waiting_page`
3. `non_product_page`
4. `promo_heavy_commerce_landing`
5. supported product-specific classes

| Class | Required positive signals | Required negative guards | Local fixtures |
| --- | --- | --- | --- |
| `blocked_page` | access-denied/captcha/forbidden patterns, or explicit block templates, and no stable product facts after the final collection profile | must not have a stable single-product identity with usable text surviving the same profile | `artifacts/service_test_pages/coupang_shampoo_ko.html`, `artifacts/service_test_pages/naver_smartstore_blocked.html`, `artifacts/service_test_pages/sony_wh1000xm5_support_ko.html` |
| `waiting_page` | wait-room/countdown/interstitial language dominates title or main heading and stable product facts are still absent after one clean-session retry | if stable product facts emerge after retry, downgrade to a supported product class instead of keeping waiting | `artifacts/service_test_pages/oliveyoung_mask_ko.html`, `artifacts/service_test_pages/oliveyoung_socks_ko.html` |
| `non_product_page` | category/listing/home/editorial/search shape, multiple unrelated product cards, or no provable single-product identity | if one dominant product identity is proven, do not classify as `non_product_page` | `artifacts/service_test_pages/on_category_en.html` |
| `promo_heavy_commerce_landing` | promo/event/coupon/benefit density is high and page-level commerce language exists, but single-product identity stays low-confidence | if the page explicitly anchors one product or SKU, classify to the strongest supported product class instead | `artifacts/service_test_pages/amoremall_home_ko.html` |
| `commerce_pdp` | one product identity plus trustworthy offer evidence: real price, variant selector, add-to-cart, or stock state | reject when offer is placeholder/zeroed, support-density dominates, or product identity is weak | `artifacts/service_test_pages/on_pdp_en.html`, `artifacts/service_test_pages/aesop_barrier_cream_ko.html`, `artifacts/service_test_pages/drjart_hydro_mask_en.html`, `artifacts/service_test_pages/laneige_retinol_ko.html` |
| `image_heavy_commerce_pdp` | `commerce_pdp` conditions plus either usable text `<2500` chars or image/gallery dominance likely requiring OCR support | reject when sellability evidence is missing; that case belongs to `marketing_only_pdp` or `product_marketing_page` | `artifacts/service_test_pages/allbirds_shoes_ko.html` |
| `marketing_only_pdp` | one product identity and buy-oriented copy on a shop/product URL, but offer evidence is placeholder, zero-valued, or explicitly marketing-only | reject when trustworthy price and add-to-cart signals exist; then it is `commerce_pdp` | `artifacts/service_test_pages/logitech_mxkeys_ko.html` |
| `product_marketing_page` | one product identity and rich feature/benefit copy without a trustworthy commerce offer, and support/download density is not dominant | reject when support/spec tables dominate or linked downloads dominate | `artifacts/service_test_pages/apple_airpodspro_kr.html` |
| `support_spec_page` | one product identity plus technical specs, compatibility, included-items, legal, or support table content | reject when manuals/download links dominate the page chrome; that case is `document_download_heavy_support_page` | `artifacts/service_test_pages/apple_airpodspro3_specs_ko.html`, `artifacts/service_test_pages/logitech_mxkeys_support_specs_ko.html` |
| `document_download_heavy_support_page` | one product identity plus manuals/download links/assets dominate visible content | reject when linked docs do not clearly match the same product family or model | `artifacts/service_test_pages/apple_airpods_docs_downloads_ko.html` |

Class-specific implementation notes:

- `marketing_only_pdp` is the explicit escape hatch for deceptive buy language. Zero or placeholder price plus product-specific copy is not enough for `commerce_pdp`.
- `product_marketing_page` is supported because the page can still ground product identity and claims, but promo/price evidence stays stricter downstream.
- `support_spec_page` and `document_download_heavy_support_page` are supported only because later evidence policy is stricter; `TASK-007` must not relax their admissibility beyond the rules already locked in Section 4.

#### 2.3.8 Terminal-Fail Vs Supported Decision

- Terminal-fail classes:
  - `blocked_page`
  - `waiting_page`
  - `non_product_page`
  - `promo_heavy_commerce_landing`
- Supported classes:
  - `commerce_pdp`
  - `image_heavy_commerce_pdp`
  - `marketing_only_pdp`
  - `product_marketing_page`
  - `support_spec_page`
  - `document_download_heavy_support_page`
- When the classifier returns a terminal-fail class, collection writes `page_classification.json`, sets the corresponding terminal `failure_code`, and emits directly to `AggregationQueue`.
- When the classifier returns a supported class, collection writes `ocr_manifest.json` and either:
  - emits to `OCRQueue`, or
  - emits directly to `GenerationQueue` with `ocr_status=SKIPPED`
- Local/dev verification may explicitly enable OCR experiments on unsupported pages, but the production queue path remains terminal-fail first. Unsupported classes must not consume OCR worker runtime unless the operator has opted into a local verification path.

#### 2.3.9 Acceptance Fixtures

The following local fixtures are the acceptance source for v1 collection/classification tests:

| Fixture | Expected class |
| --- | --- |
| `artifacts/service_test_pages/on_pdp_en.html` | `commerce_pdp` |
| `artifacts/service_test_pages/aesop_barrier_cream_ko.html` | `commerce_pdp` |
| `artifacts/service_test_pages/drjart_hydro_mask_en.html` | `commerce_pdp` |
| `artifacts/service_test_pages/laneige_retinol_ko.html` | `commerce_pdp` |
| `artifacts/service_test_pages/allbirds_shoes_ko.html` | `image_heavy_commerce_pdp` |
| `artifacts/service_test_pages/logitech_mxkeys_ko.html` | `marketing_only_pdp` |
| `artifacts/service_test_pages/apple_airpodspro_kr.html` | `product_marketing_page` |
| `artifacts/service_test_pages/apple_airpodspro3_specs_ko.html` | `support_spec_page` |
| `artifacts/service_test_pages/logitech_mxkeys_support_specs_ko.html` | `support_spec_page` |
| `artifacts/service_test_pages/apple_airpods_docs_downloads_ko.html` | `document_download_heavy_support_page` |
| `artifacts/service_test_pages/coupang_shampoo_ko.html` | `blocked_page` |
| `artifacts/service_test_pages/naver_smartstore_blocked.html` | `blocked_page` |
| `artifacts/service_test_pages/sony_wh1000xm5_support_ko.html` | `blocked_page` |
| `artifacts/service_test_pages/oliveyoung_mask_ko.html` | `waiting_page` |
| `artifacts/service_test_pages/oliveyoung_socks_ko.html` | `waiting_page` |
| `artifacts/service_test_pages/on_category_en.html` | `non_product_page` |
| `artifacts/service_test_pages/amoremall_home_ko.html` | `promo_heavy_commerce_landing` |

## 3. Internal Data Model

### 3.1 Entities

`Job`

- `job_id`
- `user_sub`
- `requested_platform_mode`
- `notification_target`
- `status`
- `submitted_count`
- `cached_count`
- `success_count`
- `failure_count`
- `created_at`
- `completed_at`
- `result_manifest_s3_uri`

`UrlTask`

- `url_task_id`
- `job_id`
- `raw_url`
- `canonical_url`
- `cache_key`
- `status`
- `page_class`
- `locale_detected`
- `market_locale`
- `sellability_state`
- `stock_state`
- `sufficiency_state`
- `quality_warning`
- `fallback_used`
- `weak_backfill_used`
- `failure_code`
- `failure_detail`
- `attempt_counters`
- `snapshot_s3_uri`
- `evidence_pack_s3_uri`
- `result_s3_uri`

`NormalizedPageSnapshot`

- `raw_url`
- `canonical_url`
- `http_status`
- `content_type`
- `final_url`
- `fetch_profile_used`
- `fetched_at`
- `title`
- `meta_description`
- `canonical_tag`
- `charset_selected`
- `charset_confidence`
- `mojibake_flags`
- `meta_locale`
- `language_scores`
- `decoded_text`
- `visible_text_blocks`
- `structured_data`
- `breadcrumbs`
- `primary_product_tokens`
- `price_signals`
- `buy_signals`
- `stock_signals`
- `promo_signals`
- `support_signals`
- `download_signals`
- `blocker_signals`
- `waiting_signals`
- `image_candidates`
- `ocr_trigger_reasons`
- `single_product_confidence`
- `sellability_confidence`
- `support_density`
- `download_density`
- `promo_density`
- `usable_text_chars`
- `ocr_text_blocks`

`EvidenceFact`

- `fact_id`
- `type`
- `value`
- `normalized_value`
- `source`
- `source_uri`
- `page_scope`
- `evidence_tier`
- `admissibility_tags`
- `confidence`

`CanonicalIntent`

- `intent_id`
- `category`
- `base_phrase`
- `evidence_fact_ids`
- `evidence_tier`
- `risk_flags`
- `naver_match`
- `google_match`
- `reason_template`

`ResultArtifact`

- `artifact_name`
- `job_id`
- `url_task_id`
- `requested_platform_mode`
- `s3_uri`
- `content_type`
- `row_count`
- `platform_row_counts`
- `sha256`
- `created_at`
- `expires_at`

`CacheEntry`

- `cache_key`
- `canonical_url`
- `requested_platform_mode`
- `policy_version`
- `taxonomy_version`
- `generator_version`
- `result_s3_uri`
- `row_count`
- `platform_row_counts`
- `page_class`
- `quality_warning`
- `created_at`
- `expires_at`

### 3.2 State Transitions

`UrlTask`

- `ACCEPTED -> CACHE_CHECKED -> COMPLETED_CACHED`
- `ACCEPTED -> CACHE_CHECKED -> COLLECTING -> CLASSIFIED -> OCR_PENDING -> EVIDENCE_READY -> GENERATING -> VALIDATING -> COMPLETED`

`UrlTask` terminal failures

- `FAILED_BLOCKED`
- `FAILED_WAITING`
- `FAILED_UNSUPPORTED_PAGE`
- `FAILED_COLLECTION`
- `FAILED_GENERATION`

`Job`

- `RECEIVED -> RUNNING -> COMPLETED | PARTIAL_COMPLETED | FAILED`

### 3.2.1 Lifecycle Semantics

- `ACCEPTED`: `UrlTask` record created, raw input URL preserved, no cache decision yet
- `CACHE_CHECKED`: canonical URL and versioned cache identity computed
- `COMPLETED_CACHED`: cached final per-URL result copied into the current job prefix; this is terminal success and still emits an aggregation event
- `COLLECTING`: live page fetch, normalization, and page classification inputs in progress
- `CLASSIFIED`: page class chosen and terminal-fail vs supported path decided
- `OCR_PENDING`: OCR work scheduled or explicitly skipped with an OCR status marker
- `EVIDENCE_READY`: exact-page evidence and any admitted fallback/OCR evidence frozen for generation
- `GENERATING`: Bedrock lexicalization and repair-pass logic in progress
- `VALIDATING`: category coverage, count floor, deduplication, promo, stock, and platform match rules in progress
- `COMPLETED`: final per-URL result rendered and cached
- `FAILED_*`: terminal failure with one locked `failure_code` and one human-readable `failure_detail`
- `RECEIVED`: job accepted, at least one `UrlTask` may still be in `ACCEPTED`
- `RUNNING`: at least one `UrlTask` is non-terminal
- `COMPLETED`: all URL tasks are terminal successes (`COMPLETED` or `COMPLETED_CACHED`)
- `PARTIAL_COMPLETED`: at least one terminal success and at least one terminal failure
- `FAILED`: all URL tasks are terminal failures

### 3.2.2 Failure Code Enum

`failure_code` is required on terminal URL failures and omitted on terminal URL successes.

| Terminal status | `failure_code` | Meaning |
| --- | --- | --- |
| `FAILED_BLOCKED` | `blocked_page` | Access-denied, captcha, or anti-bot block remained after the allowed collection profiles. |
| `FAILED_WAITING` | `waiting_page` | Queue/interstitial/wait-room state remained after the allowed clean-session retry. |
| `FAILED_UNSUPPORTED_PAGE` | `non_product_page` | The URL resolved to category/search/editorial/home or another non-product page. |
| `FAILED_UNSUPPORTED_PAGE` | `promo_heavy_commerce_landing` | The URL is promo-heavy and not single-product-specific enough for safe keyword generation. |
| `FAILED_COLLECTION` | `collection_exhausted` | All allowed fetch profiles failed to produce a stable normalized snapshot. |
| `FAILED_COLLECTION` | `insufficient_evidence` | Collection succeeded, but the supported page still failed the sufficiency policy after allowed OCR and fallback. |
| `FAILED_GENERATION` | `generation_schema_repair_exhausted` | Bedrock output could not be repaired into the locked JSON contract. |
| `FAILED_GENERATION` | `generation_count_shortfall` | Final output for a requested platform remained below `100` after the one allowed supplementation pass. |
| `FAILED_GENERATION` | `generation_rule_violation` | Validator rejected the output for deterministic rule violations that repair does not own. |

- `failure_detail` is a short operator-readable sentence and may include stage-local context such as HTTP status, dominant blocker pattern, or missing categories.
- `failure_detail` must not contain raw model output, secrets, or full scraped page text.
- `failure_reason_hints` is an optional short list of operator-readable suspected causes, such as timeout, blocker/challenge, weak product identity, or OCR runtime failure.
- `failure_reason_hints` is advisory only and does not replace the locked `failure_code`.
- collection workers may also persist `fallback_used`, `fallback_reason`, and `preprocessing_source` so operators can see whether the Crawl4AI fallback path ran and whether `cleaned_html` or rendered `raw_html` was actually used.

### 3.2.3 Status Payload Shape

`GET /jobs/{job_id}` returns the following logical payload:

- `job_id`
- `status`
- `requested_platform_mode`
- `counts`
  - `submitted`
  - `running`
  - `cached`
  - `succeeded`
  - `failed`
- `artifacts`
  - `result_manifest_url`
  - `combined_json_url`
  - `combined_csv_url`
  - `failures_json_url`
- `url_tasks[]`
  - `url_task_id`
  - `raw_url`
  - `canonical_url`
  - `status`
  - `page_class`
  - `quality_warning`
  - `failure_code`
  - `failure_detail`
  - `failure_reason_hints`
  - `fallback_used`
  - `fallback_reason`
  - `preprocessing_source`
  - `result_url`
  - `cache_hit`
- `notification`
  - `target_type`
  - `delivery_status`
  - `last_attempt_at`

Example non-terminal job payload:

```json
{
  "job_id": "job_01JABCDEF",
  "status": "RUNNING",
  "requested_platform_mode": "both",
  "counts": {
    "submitted": 3,
    "running": 1,
    "cached": 1,
    "succeeded": 1,
    "failed": 0
  },
  "artifacts": {
    "result_manifest_url": null,
    "combined_json_url": null,
    "combined_csv_url": null,
    "failures_json_url": null
  },
  "url_tasks": [
    {
      "url_task_id": "ut_01",
      "raw_url": "https://example.com/p/sku-1",
      "canonical_url": "https://example.com/p/sku-1",
      "status": "COMPLETED_CACHED",
      "page_class": "commerce_pdp",
      "quality_warning": false,
      "failure_code": null,
      "failure_detail": null,
      "failure_reason_hints": [],
      "fallback_used": false,
      "fallback_reason": null,
      "preprocessing_source": "raw_html",
      "result_url": "/jobs/job_01JABCDEF/results/per_url_manifest",
      "cache_hit": true
    },
    {
      "url_task_id": "ut_02",
      "raw_url": "https://example.com/p/sku-2",
      "canonical_url": "https://example.com/p/sku-2",
      "status": "GENERATING",
      "page_class": "support_spec_page",
      "quality_warning": true,
      "failure_code": null,
      "failure_detail": null,
      "failure_reason_hints": [],
      "fallback_used": false,
      "fallback_reason": null,
      "preprocessing_source": "raw_html",
      "result_url": null,
      "cache_hit": false
    }
  ],
  "notification": {
    "target_type": "email",
    "delivery_status": "NOT_SENT",
    "last_attempt_at": null
  }
}
```

Example terminal partial-complete payload:

```json
{
  "job_id": "job_01JABCXYZ",
  "status": "PARTIAL_COMPLETED",
  "requested_platform_mode": "google_sa",
  "counts": {
    "submitted": 2,
    "running": 0,
    "cached": 0,
    "succeeded": 1,
    "failed": 1
  },
  "artifacts": {
    "result_manifest_url": "/jobs/job_01JABCXYZ/results/per_url_manifest",
    "combined_json_url": "/jobs/job_01JABCXYZ/results/combined_json",
    "combined_csv_url": "/jobs/job_01JABCXYZ/results/combined_csv",
    "failures_json_url": "/jobs/job_01JABCXYZ/results/failures_json"
  },
  "url_tasks": [
    {
      "url_task_id": "ut_10",
      "raw_url": "https://shop.example.com/item/10",
      "canonical_url": "https://shop.example.com/item/10",
      "status": "COMPLETED",
      "page_class": "marketing_only_pdp",
      "quality_warning": true,
      "failure_code": null,
      "failure_detail": null,
      "result_url": "/jobs/job_01JABCXYZ/results/per_url_manifest",
      "cache_hit": false
    },
    {
      "url_task_id": "ut_11",
      "raw_url": "https://shop.example.com/event/sale",
      "canonical_url": "https://shop.example.com/event/sale",
      "status": "FAILED_UNSUPPORTED_PAGE",
      "page_class": "promo_heavy_commerce_landing",
      "quality_warning": null,
      "failure_code": "promo_heavy_commerce_landing",
      "failure_detail": "single-product identity not proven after classification",
      "failure_reason_hints": [
        "single-product identity was not proven strongly enough from product, price, and buy-intent signals",
        "the URL looks closer to a promo landing page or listing than a single PDP"
      ],
      "result_url": null,
      "cache_hit": false
    }
  ],
  "notification": {
    "target_type": "webhook",
    "delivery_status": "SENT",
    "last_attempt_at": "2026-04-03T14:41:22Z"
  }
}
```

### 3.3 Mapping To The Fixed Final Schema

- `url`: original `raw_url`
- `product_name`: highest-confidence normalized display name from direct facts; fallback is a support/spec title only when it exactly matches the same model or SKU
- `category`: one of the 10 fixed categories. The first nine categories are positive-output categories; `negative` is a separate exclusion category and is never counted toward the per-platform `>=100` positive floor
- `keyword`: platform-rendered phrase from `CanonicalIntent`
- `naver_match` / `google_match`: deterministic formatter output with locked internal mapping rules:
  - `naver_sa`: every emitted row must populate `naver_match` only; `google_match` stays blank
  - `google_sa`: every emitted row must populate `google_match` only; `naver_match` stays blank
  - `both`: validator output must preserve `intent_id`, rendered `keyword`, and per-platform admissibility so the exporter can either coalesce a shared row when the rendered keyword is the same on both platforms or emit separate platform rows when it differs; this section locks the upstream pairing contract only, not the final flattened examples
- `reason`: concise natural-language explanation built from the strongest admitted fact; evidence tier is tracked internally and reflected in the sentence, not exposed as a bracket prefix
- `quality_warning`: URL-level boolean copied to every row for that URL; `true` when fallback evidence is used, weak-tier backfill is used, or the final supported page class is support-heavy, image-heavy, or otherwise borderline

### 3.4 Cache Model

Cache is stored per **platform component** (`naver_sa`, `google_sa`). A `both` result is stored as two separate component entries. This allows any future request—regardless of platform mode—to reuse whichever components are already cached.

- Cache key format (per platform component):
  - `kwg:{sha256(canonical_url)}:platform:{naver_sa|google_sa}:policy:{policy_version}:taxonomy:{taxonomy_version}:generator:{generator_version}`
- `both` is never stored as a single cache object. Generation always writes two keys: one `naver_sa` and one `google_sa`.
- Cache TTL is **30 days** from successful per-URL finalization.
- Cache value stores only the final per-URL result artifact plus the minimum metadata needed for validation-safe reuse.
- Policy-version, taxonomy-version, or generator-version bumps invalidate reuse automatically by producing a different key. Existing objects may age out naturally; no synchronous delete is required for correctness.

Concrete cache-key examples:

- `naver_sa` component
  - `kwg:3b7ce6...:platform:naver_sa:policy:policy_v1:taxonomy:tax_v2026_04_03:generator:gen_v3`
- `google_sa` component
  - `kwg:3b7ce6...:platform:google_sa:policy:policy_v1:taxonomy:tax_v2026_04_03:generator:gen_v3`
- `both` request → stored as two component keys above (no separate `both` key)
- generator-version bump
  - `kwg:3b7ce6...:platform:naver_sa:policy:policy_v1:taxonomy:tax_v2026_04_03:generator:gen_v4`

#### 3.4.1 Cache Lookup Resolution Order

Submit resolves cache in this order for each requested platform mode. Submit never performs live URL checks; it only reads existing cache entries.

**`both` request:**

1. Both `naver_sa` and `google_sa` component caches exist → merge and serve as `both` (mark `COMPLETED_CACHED`)
2. Only one component exists → treat the missing component as a cache miss, generate only that component, then merge
3. Neither component exists → full cache miss, generate both

**`naver_sa` or `google_sa` request:**

1. Exact component cache exists → serve immediately (mark `COMPLETED_CACHED`)
2. `both`-equivalent cache exists (i.e., both component keys exist) → extract and serve the requested component (mark `COMPLETED_CACHED`, also write the extracted component key if not already present)
3. No usable cache → full cache miss, generate

#### 3.4.2 Cache Validity Worker

A dedicated background worker (scheduled, independent of the main processing pipeline) proactively scans cached entries and removes those whose source URLs are no longer valid. Submit never performs live URL checks; all proactive invalidation is done by this worker.

- **Schedule**: configurable, default daily (CloudWatch Events / EventBridge rule → Lambda)
- **Scan scope**: all cache objects under `s3://.../cache/` with `cached_at` older than `VALIDITY_CHECK_MIN_AGE_DAYS` (default 7 days; newly written entries are not re-checked immediately)
- **Check per entry**: lightweight HEAD request (or minimal GET) to the `canonical_url` stored in the cache object
  - `2xx` and product identity signal still present → keep entry, update `last_checked_at`
  - `404`, `410`, or product identity absent → **delete cache entry** (S3 object delete); log deletion with `url_hash` and reason
  - Content change detected (significant `Content-Length` delta or new `Last-Modified` vs. `cached_at`) → **delete cache entry**; next submit for that URL will regenerate
  - Check itself fails (timeout, DNS error, network error) → keep entry unchanged; log warning; retry on next scheduled run
- The worker owns only cache object deletion. It never writes new cache entries and never enqueues generation jobs.
- Manual targeted deletion remains available as an operational override (bad output, merchant takedown request).

#### 3.4.3 Cache Operations And Invalidation Baseline

- Only successful final per-URL outputs are cacheable. Collection failures, OCR soft failures, and terminal unsupported-page failures are not cached because merchant availability and access posture may change independently of policy versions.
- Cache write timing is fixed:
  - generation writes both component cache objects only after validator success and per-URL result JSON finalization for each platform
  - aggregation never writes cache entries
  - submit only reads cache (and copies a cache-hit payload into the current job prefix)
- Cache object minimum contents:
  - fixed-schema per-URL rows (platform component only: `naver_sa` rows or `google_sa` rows)
  - validation summary needed for reuse-safe status payloads
  - `page_class`
  - `quality_warning`
  - the exact `policy_version`, `taxonomy_version`, `generator_version`, `platform_component` (`naver_sa` or `google_sa`), and `cached_at` timestamp
- Cache storage prefix is stable and version-addressed:
  - `s3://.../cache/policy={policy_version}/taxonomy={taxonomy_version}/generator={generator_version}/platform={naver_sa|google_sa}/{sha256(canonical_url)}.json`
- Targeted invalidation is allowed only by exact cache key or exact S3 object path. It is an operational override for bad outputs or merchant takedown requests.
- Bulk invalidation uses version bumps, not in-place mutation:
  - prompt or validator-rule changes bump `generator_version`
  - evidence or policy changes bump `policy_version`
  - curated taxonomy changes bump `taxonomy_version`
- Natural TTL expiry remains 30 days even after a version bump. Old objects may coexist until expiry because correctness is enforced by the versioned key.
- Cache hit copy semantics are fixed:
  - submit copies the cached component payload(s) into `jobs/{job_id}/urls/{url_task_id}/result/`
  - the current `UrlTask` is marked `COMPLETED_CACHED`
  - aggregation receives the same terminal event shape as a fresh generation success
- Manual purge does not delete job-scoped copied outputs that were already materialized for a submitted job. It only affects future cache lookups.

## 4. Policy Decisions

| Policy | Decision |
|---|---|
| Page classification | Rules-first classifier. Bedrock is always asked the primary gate question: "Is this a product sales page?" If no purchase intent is found, classify as `support_spec_page` or `non_product_page` immediately. Bedrock acts as a tie-break only when the top two rule-based classes are within `0.15` confidence. |
| `blocked_page` | HTTP `403/429` or block/captcha/access-denied patterns and no stable product facts after all fetch profiles. Terminal fail. |
| `waiting/interstitial_page` | Queue, wait-room, countdown, or interstitial patterns dominate visible text and no stable product facts remain after retry. Terminal fail. |
| `commerce_pdp` | Single product identity plus trustworthy sellability evidence: stable price or variant/add-to-cart/stock signals. |
| `image_heavy_commerce_pdp` | `commerce_pdp` plus direct usable text `<2500 chars` or OCR contributes `>30%` of admitted evidence text. |
| `marketing_only_pdp` | Product-specific page with buy language but no trustworthy offer, empty or placeholder price, or explicit marketing-only state. Generation allowed with stricter commerce rules. |
| `product_marketing_page` | Product-specific feature page without a trustworthy commerce offer and not support-dominant. Generation allowed. |
| `support_spec_page` | Product-specific support or spec content with tables, compatibility, included items, or legal specs. Generation allowed. |
| `document_download_heavy_support_page` | Product-specific support page dominated by manuals, downloads, or assets. Generation allowed only if linked docs or inline headings clearly match the same model or family. |
| `promo_heavy_commerce_landing` | Promo, event, or benefit density is high while single-product specificity is low. Terminal fail as unsupported input. |
| `non_product_page` | Category, search, home, editorial, or multi-product listing without a single target product. Terminal fail. |
| Evidence tiers | `direct`: explicit on exact URL or same-page OCR/JSON. `derived`: safe recombination of direct facts on the exact URL. `inferred`: from same-product fallback docs/specs or curated taxonomy. `weak`: borderline evidence used only for count-fill. |
| Locale policy | Default market language is Korean. Generic intent words are generated in Korean. Brand, model, SKU, ingredient, and trademark tokens stay in their observed language unless a localized alias is explicitly observed. Mixed Korean plus source-language phrases are allowed when anchored by observed product tokens. No invented transliterations. |
| Sufficiency policy | `sufficient` if product identity is high confidence and either usable text `>=3000` or usable text `>=1500` with `>=12` direct facts across `>=4` fact groups. `borderline` if product identity is high confidence and usable text `>=800` with `>=8` facts after OCR or fallback. Otherwise fail unless the page class is already terminal-fail. |
| Sparse/backfill policy | Backfill order is fixed: `brand/model exact -> category/attribute combinations -> use case/audience/occasion -> support/spec derived -> weak inferred`. Weak promo terms are never used for fill. |
| Weak-tier cap | Weak-tier intents may account for at most `20%` of final platform output. Exceeding that limit causes validation failure. |
| Category coverage policy | Hard floor: each requested platform output must contain `>=100` positive keywords across the 9 positive categories and a separate negative-keyword output. For `both`, Naver and Google are validated separately. Soft positive target mix per platform: brand `10`, general `12`, attribute `18`, competitor `8`, purchase `12`, long-tail `16`, benefit/price `6`, season/event `6`, problem/solution `12`. Negative keywords target `10-30` exclusion terms per platform and are never counted toward the positive `100`. |
| Platform generation policy | One canonical intent pool is created, then rendered once per requested platform. Naver match labels must use the requirement-approved exact-match, expanded-match, and exclusion labels. Google uses `exact`, `phrase`, `broad`, and `negative`. Mapping rule: exact brand/model terms -> Naver exact-match and Google exact; long-tail purchase/problem terms -> Naver exact-match and Google phrase; broad category terms -> Naver expanded-match and Google broad; negative intents render only into the separate exclusion output as Naver exclusion and Google negative. |
| Intent dedup policy | Semantic dedup via LLM (Bedrock call B). The model identifies intent-equivalent keyword groups regardless of surface form (e.g., `mens sneaker` / `men sneaker` / `men's sneaker` → one group) and selects the best representative. String normalization alone is insufficient; intent equivalence is the standard. |
| Promo admissibility | Promo evidence is admissible only when explicit on the exact URL, same-page OCR, exact-URL structured data, or a directly linked same-product promo page fetched under the fallback rule. Same-domain home or event pages that are not explicitly product-matching are inadmissible. |
| Stock state | `InStock`: normal generation. `OutOfStock`: generation still proceeds; do not emit urgency or availability phrasing. `Unknown` or placeholder price: treat as non-sellable unless another trustworthy sellability signal exists. |
| Support/spec/docs fallback | Same-product support/spec/docs are allowed as first-class fallback evidence for product identity, attributes, compatibility, included items, and problem/solution. They are not admissible for discount, coupon, or lowest-price claims. Same-root-domain or approved sibling-domain only, max one hop, max three linked docs. |
| OCR policy | Run screenshot OCR when decoded visible text is thin or charset confidence is low. Run asset OCR on ranked images only. Default cap is 24 ranked eligible images per URL, min size `300x300`, reject sprites, logos, icons, thumbnails, decorative runtime UI assets, and templated image URLs, classify ranked assets as `general_detail_image` or `table_like_image` before execution, and route `table_like_image` through the structured OCR branch when enabled. OCR subprocess timeout is env-configurable via `KEYWORD_GENERATOR_OCR_TIMEOUT_SECONDS`. Admit OCR blocks conservatively, but preserve meaningful short image lines for downstream relevance filtering instead of requiring only long paragraphs. |
| Encoding/charset normalization | Decode priority is `BOM -> HTTP header -> meta charset -> charset detector`. If mojibake heuristics trigger, retry decoding with `utf-8`, `cp949/euc-kr`, and `latin1` recovery, choose the highest Korean/English language score, then apply HTML entity decode, Unicode NFKC, and whitespace normalization. |
| Cache policy | Cache per platform component (`naver_sa`, `google_sa`) for **30 days** (S3 TTL safety net). `both` results are stored as two component entries. Cache lookup resolves via exact component match first, then cross-mode reuse (`naver_sa` + `google_sa` → `both`, or `both` → single component). Proactive invalidation is done by a dedicated **Cache Validity Worker** (scheduled daily): scans cached entries, HEAD-checks canonical URLs, deletes entries where URL is gone or content materially changed. Submit never performs live URL checks. Raw HTML and evidence packs are not reused across policy-version changes. |
| Keyword language policy | Korean and English mixed keywords are both allowed and encouraged. Brand names and model numbers retain their original language (typically English). Generic product terms use Korean. The same concept in both languages counts as two distinct keywords (e.g., `나이키 슬리퍼` and `Nike 슬리퍼` are separate rows). Keyword Generator prompt must include mixed-language examples. |
| Partial completion | Successful URLs export normally even if others fail. Failed URLs appear only in `failures.json` and job metadata, never as fake keyword rows. |
| `quality_warning` policy | Set `true` when fallback evidence is used, the surviving set contains `weak`-tier keywords at or above cap, sufficiency is `borderline`, or the final supported page class is `image_heavy_commerce_pdp`, `support_spec_page`, or `document_download_heavy_support_page`. Otherwise `false`. |
| LLM post-processing scope | Three purposeful Bedrock calls per platform: (A) over-generation, (B) semantic dedup + quality evaluation, (C) targeted supplementation only if gaps remain. Quality is the v1 optimization target; cost reduction is deferred. Hard compliance checks (promo, fake price, stock urgency, competitor safety) remain deterministic code — these are factual accuracy rules the model cannot be trusted to self-enforce. |

### 4.1 Evidence Contract

`Evidence Builder` consumes `collection/normalized_snapshot.json`, optional `ocr/ocr_result.json`, and bounded fallback fetch outputs, then emits one `evidence/evidence_pack.json` per `url_task_id`.

Minimum `evidence_pack.json` shape:

- `url_task_id`
- `page_class`
- `product_identity`
  - `display_name`
  - `brand`
  - `model_tokens[]`
  - `sku_tokens[]`
  - `identity_confidence`
- `sellability_state`
- `stock_state`
- `sufficiency_state`
- `fallback_used`
- `ocr_used`
- `quality_warning_inputs`
- `admitted_facts[]`
  - `fact_id`
  - `fact_type`
  - `value`
  - `source_stage`
  - `source_uri`
  - `evidence_tier`
  - `admissibility_tags[]`
  - `same_product_match_reason`

- `admitted_facts[]` is the only evidence surface the generator and validator may consume.
- Raw OCR strings, raw fallback HTML, and rejected candidate facts must stay outside the admitted list.

#### 4.1.1 Evidence Tier Semantics

| Tier | Definition | Typical sources | Allowed uses | Never allowed for |
| --- | --- | --- | --- | --- |
| `direct` | Explicit product fact on the exact input URL or same-page OCR that clearly names the same product | page title, exact-URL structured product data, price block, variant labels, breadcrumb, accepted OCR block on the same page | all keyword categories subject to promo/stock policy | none beyond existing global policy restrictions |
| `derived` | Safe recombination of `direct` facts from the same exact page | combining brand + model + attribute, deriving audience/use-case from explicit variant metadata | all non-promo categories, conservative price/purchase phrases | discount/coupon/lowest-price claims not stated directly |
| `inferred` | Same-product facts from approved fallback docs/specs or disciplined commercial expansion from strong direct evidence | support/spec tables, included-items docs, compatibility docs, obvious category expansions | attribute, problem/solution, long-tail, purchase-intent support terms | unsupported promo, unverifiable superlatives, urgency |
| `weak` | Borderline expansions used only to satisfy count after stronger tiers are exhausted | low-risk long-tail variants, soft occasion/use-case phrasing | count-fill only, at most `20%` of final platform output | promo, price claims, competitor claims, stock/urgency language |

- Tier escalation is one-way. A fallback fact can never be upgraded above `inferred`.
- OCR-origin facts may be `direct` only when they are clearly same-page and same-product; otherwise they are rejected, not downgraded.
- `weak` evidence is allowed only after `brand/model exact -> category/attribute -> use case/audience/occasion -> support/spec derived` is exhausted.

#### 4.1.2 Fallback Fetch Eligibility

- Fallback fetch is owned only by `Generation Worker Lambda`.
- Fallback is allowed only for supported page classes:
  - `commerce_pdp`
  - `image_heavy_commerce_pdp`
  - `marketing_only_pdp`
  - `product_marketing_page`
  - `support_spec_page`
  - `document_download_heavy_support_page`
- Fallback is attempted only when:
  - `product_identity.identity_confidence` is already high, and
  - `sufficiency_state` is not already `sufficient`, or
  - the page class is support-heavy and more same-product structured detail is likely available
- Allowed fallback targets:
  - same-root-domain support/spec/doc pages
  - approved sibling-domain support/spec/doc pages from configuration
  - directly linked same-product promo/event pages under the narrower promo rule below
- Disallowed fallback targets:
  - search snippets
  - home pages, category pages, event hubs, or campaign indexes
  - cross-domain pages outside same root or approved sibling domains
  - linked docs beyond one hop from the exact input page

Limits:

- max one fallback hop from the exact input page
- max three fetched support/spec/doc targets per URL
- max one same-product promo/event target per URL
- if a fallback target blocks or fails, skip it and continue; do not retry via new worker topology

#### 4.1.3 Same-Product Matching Rule

Fallback or OCR evidence is admitted only when the source can be matched to the same product by deterministic rules.

Same-product match passes when at least one strong match rule is true, or two medium rules are true:

- Strong rules:
  - exact SKU or model token match
  - exact product title match after normalization
  - structured-data product ID on fallback page matches the exact page product ID
- Medium rules:
  - same brand plus same normalized product family token
  - same brand plus at least two matching distinctive attribute tokens
  - same breadcrumb terminal node plus same model-family token

Same-product match fails when any disqualifier is true:

- fallback page names a different SKU/model
- page is multi-product or comparison-oriented
- only brand-level match exists without model/family evidence
- title match depends on stripping too much descriptive text or guessing aliases

On failure, the fallback or OCR candidate is rejected entirely rather than admitted as weaker evidence.

#### 4.1.4 Promo Admissibility Examples

| Source pattern | Admissible | Why |
| --- | --- | --- |
| exact product page shows explicit sale price, coupon, or benefit text | yes | same-page direct promo evidence |
| exact-page OCR shows product-specific promo badge tied to the same product | yes | same-page OCR can contribute `direct` promo facts |
| exact-page structured data includes explicit sale/offer data | yes | exact-URL structured commerce evidence |
| exact page links to one promo page explicitly naming the same product or SKU | yes | narrow allowed promo fallback |
| same-domain home/event page with general benefits but no exact product anchor | no | promo-heavy landing evidence is inadmissible |
| category page or banner says "best sellers", "offers", or "deals" without same-product proof | no | not product-specific enough |
| support/spec/doc page mentions warranty or included service only | no for promo | support docs are not promo sources |
| inferred price language such as "best", "cheap", "sale", "under budget" without direct support | no | unsupported promo expansion |

#### 4.1.5 OCR Candidate Ranking And Acceptance

OCR consumes only `image_candidates[]` and the collection screenshot.

Run screenshot OCR when one or more are true:

- `usable_text_chars < 1500`
- `charset_confidence < 0.80`
- the page class is `image_heavy_commerce_pdp`
- visible text is thin but image alt text suggests product/spec text exists

Asset OCR ranking score should favor:

- larger rendered area
- image position near hero/gallery/spec sections
- alt text containing product/model/spec tokens
- filenames or URLs containing model/spec/product tokens
- candidate-type routing into `general_detail_image`, `front_label_closeup`, `long_detail_banner`, or `table_like_image`
- uniqueness over obvious sprite/icon assets

Reject before OCR:

- width or height `<300`
- sprite sheets
- logos, icons, badges, or decorative UI graphics
- thumbnails when a larger version of the same asset exists
- duplicate URLs or near-duplicate hashes

Default cap:

- one screenshot
- up to eight ranked page images

Execution policy:

- `table_like_image` prefers the structured OCR branch first and may fall back to plain OCR
- `long_detail_banner` should prefer tiled OCR over one-shot full-image OCR
- plain-image OCR may run multiple preprocessing passes, but it must stop early once a sufficiently strong pass is found instead of always paying every pass cost
- OCR artifacts must retain per-image pass metadata (`ocr_passes[]`, preprocessing variant, tile count, runtime, recognizer language) for later debugging
- trusted OCR promotion should evaluate merged `line_group` text quality, not only the strongest child block score, so grouped label/spec lines can become direct candidates when the combined line-group text is informative enough

OCR block admission requires all of the following:

- decoded block length `>=30` characters or at least two product/spec tokens
- not mostly numeric/serial junk
- not mostly brand-only repetition
- not dominated by navigation, coupon, or unrelated campaign text
- same-page or same-product match can be established from nearby context
- exact-page label/spec field markers such as `제품명`, `품질표시사항`, `재질`, `제조국`, `가격`, `ingredient(s)`, or `material` may count as deterministic same-product signals on ranked same-page detail images even when the OCR block does not repeat the page title tokens verbatim

Reject OCR blocks when any are true:

- mostly logo/tagline/banner text
- promo slogans not anchored to the exact product
- repeated fragment already present in direct HTML text
- garbled decode or mixed-character noise
- unrelated product names appear in the same block

Admitted OCR facts:

- may support product attributes, materials, compatibility, included items, and long-tail detail
- may support promo only when the OCR block is same-page and explicitly tied to the exact product
- must never become the sole basis for product identity if non-OCR signals do not already establish the same product
- OCR should promote trusted `line_group` candidates, not raw blocks alone, when deciding whether same-page OCR can contribute `direct` evidence

#### 4.1.6 `quality_warning` Inputs

`quality_warning` is computed deterministically at URL level. Set it to `true` when any of the following are true:

- `fallback_used = true`
- `weak_backfill_used = true`
- `sufficiency_state = borderline`
- final `page_class` is one of:
  - `image_heavy_commerce_pdp`
  - `support_spec_page`
  - `document_download_heavy_support_page`
- OCR contributes more than `30%` of admitted evidence text
- one or more admitted facts are `inferred` and no `direct` price/sellability fact exists

Set it to `false` only when all are true:

- no fallback evidence was admitted
- no weak-tier backfill was used
- `sufficiency_state = sufficient`
- OCR contribution is supplemental rather than dominant
- final page class is not one of the support-heavy or image-heavy classes above

Search-snippet-derived evidence remains disabled in v1 and can never be a reason to clear `quality_warning`.

### 4.2 Generation And Validation Contract

`Generation Worker Lambda` consumes `evidence/evidence_pack.json` plus one resolved taxonomy bundle version and writes the following internal artifacts before the URL is marked terminal:

- `generation/intent_plan.json`
- `generation/canonical_intents.json`
- `generation/platform_render_naver.json` when Naver output is requested
- `generation/platform_render_google.json` when Google output is requested
- `generation/validation_report.json`

Generation and validation must operate only on `admitted_facts[]`, the locked taxonomy bundle, and deterministic validator rules. Raw HTML, rejected OCR text, and unpublished taxonomy entries are out of scope once Section 4.1 handoff is complete.

#### 4.2.1 Intent Planner Input And Output

`Intent Planner` input is the minimum safe generation surface:

- `url_task_id`
- `requested_platform_mode`
- `page_class`
- `product_identity`
- `sellability_state`
- `stock_state`
- `sufficiency_state`
- `quality_warning_inputs`
- `admitted_facts[]`
- resolved taxonomy metadata:
  - `taxonomy_version`
  - `bundle_sha256`
  - `enabled_groups[]`

Minimum `generation/intent_plan.json` shape:

- `url_task_id`
- `requested_platform_mode`
- `page_class`
- `positive_target_per_platform`
- `negative_target_range`
  - `min`
  - `max`
- `positive_category_targets`
  - `brand`
  - `generic_category`
  - `feature_attribute`
  - `competitor_comparison`
  - `purchase_intent`
  - `long_tail`
  - `benefit_price`
  - `season_event`
  - `problem_solution`
- `negative_category_target`
- `allowed_taxonomy_groups[]`
- `weak_positive_cap`
- `supplementation_pass_limit`
- `category_evidence_ceiling`
  - one entry per category

Locked planner defaults:

- `positive_target_per_platform = 100` (floor after dedup)
- `initial_generation_target = 160` (over-generate to absorb semantic dedup loss; configurable)
- `negative_target_range = { min: 10, max: 30 }`
- `weak_positive_cap = 20` (applied after dedup, before supplementation)
- `supplementation_pass_limit = 1` (one LLM supplementation call if gaps remain post-dedup)

#### 4.2.2 Category Allocation And Quota Rules

Default positive target allocation per platform:

| Positive category | Target |
| --- | ---: |
| `brand` | 10 |
| `generic_category` | 12 |
| `feature_attribute` | 18 |
| `competitor_comparison` | 8 |
| `purchase_intent` | 12 |
| `long_tail` | 16 |
| `benefit_price` | 6 |
| `season_event` | 6 |
| `problem_solution` | 12 |
| Total positive keywords | 100 |

Separate exclusion output:

- `negative`: target `10-30` per requested platform
- `negative` must be emitted as a separate exclusion output surface and never counted toward the positive `100`

Hard validator rules:

- `naver_sa`
  - `>=100` positive rows
  - all 9 positive categories present with `>=1` row each
  - `negative` output present with `>=1` row
- `google_sa`
  - `>=100` positive rows
  - all 9 positive categories present with `>=1` row each
  - `negative` output present with `>=1` row
- `both`
  - Naver and Google validation run independently from the same canonical intent pool
  - one platform passing does not rescue the other
  - if either platform fails after repair, the URL finishes `FAILED_GENERATION`

Allocation overflow rule:

- If a page cannot safely hit the soft target for one positive category, overflow fill moves in this order:
  - `feature_attribute`
  - `long_tail`
  - `purchase_intent`
  - `problem_solution`
  - `generic_category`
- `brand`, `competitor_comparison`, `benefit_price`, and `season_event` do not borrow overflow quota from one another by default because they are more policy-sensitive.

#### 4.2.3 LLM Supplementation Pass And Evidence Ceilings

If the surviving keyword set after semantic dedup falls short of `positive_target_per_platform` or is missing required categories, one LLM supplementation call is made. The supplementation prompt:

- receives the current surviving set, the gap report (missing count by category and platform), and the evidence pack
- is instructed to fill **only** the identified gaps, not regenerate the whole set
- follows the same evidence ceiling rules as the initial generation
- must not loosen evidence tiers to fill gaps; quality floor takes priority over count floor

If after one supplementation pass a platform still fails floors, the URL is marked `FAILED_GENERATION`. No second supplementation pass is allowed (avoid open-ended cost escalation while preserving quality-first intent).

Supplementation priority guidance for the prompt (ordering is a hint, not a hard rule — LLM judges best fit):

1. Strongest-evidence categories that are still short (`brand`, `feature_attribute`, `purchase_intent`)
2. Medium-evidence fill (`generic_category`, `long_tail`, `problem_solution`)
3. Taxonomy-backed fill only (`competitor_comparison`, `season_event`, `benefit_price`)
4. `weak` fill as last resort, subject to cap

Category evidence ceilings (apply to both initial generation and supplementation):

| Category | Maximum admissible tier | Notes |
| --- | --- | --- |
| `brand` | `derived` | exact product and brand family only |
| `generic_category` | `inferred` | obvious category expansion allowed |
| `feature_attribute` | `inferred` | support/spec fallback allowed |
| `competitor_comparison` | `inferred` | taxonomy-backed only, never `weak` |
| `purchase_intent` | `inferred` | superlatives remain validator-sensitive |
| `long_tail` | `weak` | main destination for final count-fill |
| `benefit_price` | `derived` | explicit price lookups only unless direct promo evidence exists |
| `season_event` | `inferred` | taxonomy-backed only, never `weak` |
| `problem_solution` | `weak` | weak fill allowed only for low-risk need-state phrasing |
| `negative` | `inferred` | curated exclusions plus exact-page negatives |

Additional locked rules:

- `weak` positive intents may account for at most `20` of the final `100` positive rows per platform.
- `benefit_price` rows may use explicit price lookups such as `brand model price` when exact-page price evidence exists, but discount/coupon/lowest-price language still requires direct promo evidence.
- `competitor_comparison` rows must come from the curated competitor taxonomy and the same product class; they must never be synthesized from raw brand popularity alone.
- `season_event` rows require either direct page language or a curated taxonomy entry anchored to the observed product type and use case.

#### 4.2.4 LLM Semantic Deduplication And Quality Evaluation

The `Dedup & Quality Evaluator` Bedrock call receives the full candidate set from the generator and produces `generation/dedup_quality_report.json`.

**Dedup prompt contract:**

The model is asked to:

- Identify groups of semantically equivalent keywords (same core search intent even if surface form differs)
  - e.g., `mens sneaker`, `men sneaker`, `men's sneaker` → one group
  - e.g., `나이키 슬리퍼`, `나이키 슬리퍼 남성` → distinct (modifier changes intent)
- From each duplicate group, select one representative to keep, preferring:
  - the keyword most natural to Korean search behavior
  - the keyword with the strongest evidence_tier annotation
  - the more specific phrase when specificity adds search value
- Output the surviving set with dedup justifications

**Quality evaluation prompt contract:**

For each surviving keyword the model provides:

- `quality_score`: `high` / `medium` / `low`
- `quality_reason`: one-line justification
- `keep`: boolean recommendation (quality < `low` threshold → recommend drop)

Keywords marked `keep: false` by the quality evaluator are dropped before floor checks. This is a quality gate, not a count gate — count shortfall is handled by supplementation, not by lowering quality bar.

**Artifact: `generation/dedup_quality_report.json` minimum shape:**

- `url_task_id`
- `platform`
- `surviving_keywords[]` (keyword text, category, evidence_tier, quality_score, quality_reason)
- `dropped_duplicates[]` (original keyword, duplicate_of, drop_reason)
- `dropped_low_quality[]` (original keyword, quality_score, quality_reason)
- `gap_report` (missing count by category and total, per platform)

#### 4.2.5 Platform Rendering And Validator Split

Rendering is platform-specific but source intents are shared.

- `naver_sa`
  - positive match labels: `exact-match`, `expanded-match`
  - negative match label: `exclusion`
- `google_sa`
  - positive match labels: `exact`, `phrase`, `broad`
  - negative match label: `negative`

Locked rendering rules:

- exact brand/model rows -> Naver `exact-match`, Google `exact`
- purchase-intent and high-specificity long-tail rows -> Naver `exact-match`, Google `phrase`
- broad generic/category rows -> Naver `expanded-match`, Google `broad`
- negative rows -> Naver `exclusion`, Google `negative`

`both` mode rules:

- one canonical intent pool is built once
- renderer produces one Naver candidate set and one Google candidate set from that same pool
- validator then evaluates Naver and Google independently for:
  - positive count
  - soft category coverage diagnostics
  - negative output presence
  - match-label validity
  - rule violations
- one platform may retain or drop a candidate independently of the other based on match-type and dedup outcomes

#### 4.2.6 Deterministic Rule Checks

Validator-owned hard rejections:

| Rule | Reject when | Repair owns replacement |
| --- | --- | --- |
| Unsupported promo | row contains sale, discount, coupon, cheapest, budget, deal, or lowest-price language without admissible direct promo evidence | yes, only by replacing the dropped row with already-approved backlog |
| Fake price | row invents a numeric band, under-`X`, or affordability claim not present in direct exact-page evidence | yes, only by replacement |
| Stock urgency | row contains `limited stock`, `selling fast`, `last chance`, `hurry`, `restock soon`, or similar urgency without direct exact-page urgency evidence | yes, only by replacement |
| Out-of-stock misuse | `stock_state = OutOfStock` and the row still implies immediate availability or urgency | yes, only by replacement |
| Weak-cap overflow | surviving positive rows include more than `20` `weak` intents | yes, by dropping overflow weak rows and filling from stronger backlog if available |
| Competitor safety | competitor token is absent from the active taxonomy bundle or does not match the observed product class | yes, only by replacement |

Rows that fail these checks are dropped before scoring and top-100 selection. Repair never rewrites the rejected phrase into a new unsupported claim; it can only replace it with a backlog intent that already satisfies the same evidence and taxonomy constraints.

Soft shaping rules are score penalties, not immediate drops:

- low-information scaffolds
- weak or fallback-only evidence
- ungrounded feature / season / problem surfaces
- awkward product-prefix or purpose-suffix shapes
- duplicate-family crowding inside the same category

These rows may still survive if the candidate pool is sparse, but they should lose to higher-confidence rows at final selection time.

#### 4.2.7 LLM Post-Processing Pipeline Summary

Operator note (2026-04-10): category presence is now soft at final validation time. The runtime still over-generates and may still supplement for category/count gaps upstream, but the final post-processing flow is:

1. hard remove only for must-never-ship rows
2. assign a deterministic `selection_score` from Bedrock quality tier plus evidence/shape penalties
3. reserve the best available positive row per category when available
4. fill the remaining positive slots by global score until each requested platform reaches `100`

Missing positive categories are recorded in diagnostics/debug output and `missing_positive_categories`; they no longer fail generation by themselves.

Three Bedrock calls are used per platform in the generation stage. Each call is purposeful; no speculative extra calls.

| Step | Bedrock call | Input | Output | Condition |
| --- | --- | --- | --- | --- |
| **A — Generation** | 1 call | evidence pack + intent plan + `initial_generation_target` | ~160 candidate keywords per platform | always |
| **B — Dedup & Quality** | 1 call | candidate set from A | surviving set + dedup justifications + quality scores + gap report | always |
| **C — Supplementation** | 1 call | gap report from B + evidence pack | fill keywords for missing categories/count only | only when gap_report shows shortfall |

After step C, the hard rule pass (deterministic) drops promo, fake-price, stock-urgency, and competitor violations. If the post-drop set still meets all platform floors → write results. If not → `FAILED_GENERATION`.

Supplementation constraints (both prompt instruction and code enforcement):

- targets only the gap identified in step B; must not regenerate the full set
- must not widen evidence ceilings or invent facts outside the admitted evidence pack
- must not invent promo, price-band, urgency, or competitor claims
- runs at most once per platform per URL

`both` mode: steps A-C run once each using a shared evidence pack; gap report and supplementation target each platform's shortfall independently.

Pass examples:

- Step B dedup collapses 18 duplicate long-tail variants, leaving 112 positives across 9 categories → floors met, step C skipped.
- Step B quality evaluator drops 6 low-quality rows; gap report shows `season_event` missing 2 and total short by 8 → step C fills those gaps; hard rule pass finds no violations → success.

Fail examples:

- Step C fills gaps but hard rule pass drops 15 promo rows; post-drop count is 91 → `FAILED_GENERATION` with `generation_count_shortfall`.
- `both` mode: Naver passes after step C; Google still lacks `competitor_comparison` because active taxonomy has no safe entries for this product class → `FAILED_GENERATION` with `generation_category_shortfall`.

#### 4.2.8 Curated Taxonomy Asset Contract

Taxonomy ownership is service-side and curated. Runtime generation must never auto-learn or append new taxonomy entries from live pages.

Authoring source of truth:

- checked-in JSON files under `docs/taxonomy/`
- one file per vocabulary group:
  - `competitor_comparison.json`
  - `season_event.json`
  - `problem_solution.json`
  - `negative_seed.json`

Runtime publication contract:

- publish one immutable bundle to:
  - `s3://<service-artifacts-bucket>/taxonomy/{taxonomy_version}/taxonomy_bundle.json`
- publish the active pointer in Parameter Store:
  - `/kwg/taxonomy/current_version`
- store the resolved `taxonomy_version` and `bundle_sha256` inside every `intent_plan.json`, `validation_report.json`, cache entry, and final per-URL result metadata

Minimum taxonomy bundle shape:

- `taxonomy_version`
- `published_at`
- `source_commit`
- `groups[]`
  - `group_name`
  - `entries[]`
    - `entry_id`
    - `term`
    - `normalized_term`
    - `allowed_categories[]`
    - `allowed_product_types[]`
    - `required_anchor_tags[]`
    - `max_evidence_tier`
    - `risk_flags[]`

Consumption rules:

- generator loads only entries whose `allowed_product_types[]` and `required_anchor_tags[]` match the admitted evidence for the URL
- `competitor_comparison` entries may generate only competitor rows
- `season_event` entries may generate only `season_event` rows
- `problem_solution` entries may generate only `problem_solution` rows
- `negative_seed` entries may generate only `negative` rows
- validator rechecks every taxonomy-backed row against the exact same `taxonomy_version`; rows referencing inactive or mismatched entries are rejected
- taxonomy version changes invalidate cache reuse because the cache key already includes `taxonomy_version`

### 4.3 Export And Aggregation Contract

This section owns fixed-schema row emission, `both`-mode flattening, failure manifests, job final-status aggregation, and notification payloads.

#### 4.3.1 Per-URL JSON Contract

Each successful URL writes one per-URL JSON artifact with:

- `url_task_id`
- `raw_url`
- `page_class`
- `requested_platform_mode`
- `status`
- `cache_hit`
- `rows[]`
  - fixed schema only:
    - `url`
    - `product_name`
    - `category`
    - `keyword`
    - `naver_match`
    - `google_match`
    - `reason`
    - `quality_warning`
- `validation_report`
  - `status`
  - `positive_keyword_counts`
  - `category_counts`
  - `weak_tier_ratio_by_platform`
  - `quality_warning`
  - `failure_code`
  - `failure_detail`

Richer internal metadata such as evidence-tier details, intent IDs, fallback provenance, and taxonomy bundle hashes stay in separate internal artifacts. They do not leak into the fixed export rows.

Per-URL row example:

```json
{
  "url": "https://example.com/product-1",
  "product_name": "Example Product",
  "category": "brand",
  "keyword": "example product",
  "naver_match": "완전일치",
  "google_match": "exact",
  "reason": "brand and product identity observed on page",
  "quality_warning": false
}
```

#### 4.3.2 `both` Mode Row Emission Rule

Exporter input for `both` is the validator-approved row set. Export never revalidates or recomputes platform quotas.

Row emission rule:

- If one canonical intent is admitted on both platforms and the rendered keyword text is the same, emit one row with both `naver_match` and `google_match` populated.
- If one canonical intent is admitted on only one platform, emit one row with the non-requested platform field blank.
- If the two platform renderings differ in `keyword` text, emit two rows, one per rendered keyword, each with the other platform field blank.
- Negative output follows the same flatten rule, but match labels stay `제외키워드` for Naver and `negative` for Google.

Shared-row example in `both`:

```json
{
  "url": "https://example.com/product-1",
  "product_name": "Example Product",
  "category": "brand",
  "keyword": "example product",
  "naver_match": "완전일치",
  "google_match": "exact",
  "reason": "brand and product identity observed on page",
  "quality_warning": false
}
```

Single-platform row example in `both` where only Naver admitted the rendered phrase:

```json
{
  "url": "https://example.com/product-1",
  "product_name": "Example Product",
  "category": "long_tail",
  "keyword": "example product review",
  "naver_match": "완전일치",
  "google_match": "",
  "reason": "platform-specific render only admitted for Naver",
  "quality_warning": false
}
```

CSV flatten example uses the same row semantics and the same fixed columns:

```csv
url,product_name,category,keyword,naver_match,google_match,reason,quality_warning
https://example.com/product-1,Example Product,brand,example product,완전일치,exact,brand and product identity observed on page,false
https://example.com/product-1,Example Product,long_tail,example product review,완전일치,,platform-specific render only admitted for Naver,false
https://example.com/product-1,Example Product,negative,중고,,negative,exclude used-product traffic,false
```

#### 4.3.3 Combined JSON And CSV Rule

- `combined_json` groups successful per-URL payloads under `successes[]` and failed URL records under `failures[]`.
- `combined_csv` is a flat concatenation of only successful fixed-schema rows from every successful URL.
- Failed URLs never emit synthetic export rows. They appear only in `failures.json`, `combined_json.failures[]`, and job-level metadata.

Combined JSON skeleton:

```json
{
  "job_id": "job_001",
  "requested_platform_mode": "both",
  "successes": [
    {
      "url_task_id": "ut_001",
      "status": "COMPLETED",
      "rows": []
    }
  ],
  "failures": [
    {
      "url_task_id": "ut_002",
      "failure_code": "promo_heavy_commerce_landing",
      "failure_detail": "single-product identity not proven"
    }
  ]
}
```

#### 4.3.4 `reason` And `quality_warning` Rendering Rule

- `reason` is always concise natural language grounded in the strongest admitted evidence. It must not expose internal bracket prefixes such as `[direct]` or `[weak]`.
- `quality_warning` is copied as a URL-level boolean to every emitted row for that URL. Export never recalculates it.
- Example rich-PDP row:
  - `reason = "brand and product identity observed on page"`
  - `quality_warning = false`
- Example support-heavy row:
  - `reason = "specification evidence from support page matched the same product model"`
  - `quality_warning = true`

#### 4.3.5 Failure Manifest Contract

`failures.json` shape:

- `failure_count`
- `items[]`
  - `url_task_id`
  - `raw_url`
  - `page_class`
  - `requested_platform_mode`
  - `failure_code`
  - `failure_detail`
  - `failure_reason_hints`
  - `quality_warning`
  - `fallback_used`
  - `fallback_reason`
  - `preprocessing_source`

Failure manifest example:

```json
{
  "failure_count": 1,
  "items": [
    {
      "url_task_id": "ut_002",
      "raw_url": "https://example.com/product-2",
      "page_class": "promo_heavy_commerce_landing",
      "requested_platform_mode": "both",
      "failure_code": "promo_heavy_commerce_landing",
      "failure_detail": "single-product identity not proven",
      "failure_reason_hints": [
        "single-product identity was not proven strongly enough from product, price, and buy-intent signals",
        "the URL looks closer to a promo landing page or listing than a single PDP"
      ],
      "quality_warning": null,
      "fallback_used": true,
      "fallback_reason": "client_side_render_suspected",
      "preprocessing_source": "cleaned_html"
    }
  ]
}
```

#### 4.3.6 Job Final Status Aggregation Rule

- `COMPLETED`: at least one successful URL and zero failed URLs
- `PARTIAL_COMPLETED`: at least one successful URL and at least one failed URL
- `FAILED`: zero successful URLs and one or more failed URLs

Aggregation never inspects row contents. It derives status only from terminal URL outcomes.

#### 4.3.7 Notification Payload Rule

Exactly one notification is emitted per terminal job.

Notification payload minimum shape:

- `job_id`
- `status`
- `requested_platform_mode`
- `notification`
  - `target_type`
  - `value`
- `counts`
  - `submitted`
  - `succeeded`
  - `failed`
- `artifacts`
  - `result_manifest_url`
  - `combined_json_url`
  - `combined_csv_url`
  - `failures_json_url`
- `successful_url_task_ids[]`
- `failed_url_task_ids[]`

Webhook / SES payload example:

```json
{
  "job_id": "job_001",
  "status": "PARTIAL_COMPLETED",
  "requested_platform_mode": "both",
  "notification": {
    "target_type": "webhook",
    "value": "https://example.com/hooks/keyword"
  },
  "counts": {
    "submitted": 2,
    "succeeded": 1,
    "failed": 1
  },
  "artifacts": {
    "result_manifest_url": "/jobs/job_001/results/per_url_manifest",
    "combined_json_url": "/jobs/job_001/results/combined_json",
    "combined_csv_url": "/jobs/job_001/results/combined_csv",
    "failures_json_url": "/jobs/job_001/results/failures_json"
  },
  "successful_url_task_ids": ["ut_001"],
  "failed_url_task_ids": ["ut_002"]
}
```

This payload is delivery-channel-neutral. SES templates and webhook senders may wrap it, but they must not change the field meanings.

## 5. AWS Architecture

- `API Gateway + Cognito Authorizer`: authenticated `create job`, `get status`, `download result`
- `Submit Lambda`: validates request, canonicalizes URLs, creates DynamoDB records, checks cache, enqueues misses
- `DynamoDB`: single-table design for `Job` and `UrlTask`, plus GSIs for `user_sub` and `job_id`
- `S3`: stores raw snapshots, evidence packs, per-URL results, combined JSON, CSV, and failures manifest
- `CollectionQueue -> Collection Worker Lambda (container)`: Crawl4AI + Playwright fetch, charset normalization, signal extraction, page classification
- `OCRQueue -> OCR Worker Lambda (container)`: PaddleOCR over ranked images and screenshots, with a structured PP-StructureV3 branch for table-like assets when enabled
- `GenerationQueue -> Generation Worker Lambda (zip)`: builds evidence pack, runs bounded fallback fetches, calls Bedrock Sonnet 3.5, validates/repairs, writes results and cache
- `AggregationQueue -> Job Aggregator Lambda (zip)`: updates per-job counters, assembles exports when all URL tasks are terminal, and emits one notification request
- `NotificationQueue -> SES/Webhook Sender Lambda (zip)`: sends one completion notification per job
- `CloudWatch + X-Ray + DLQs`: queue depth alarms, error-rate alarms, Bedrock throttle alarms, and per-stage dead-letter handling
- `Secrets Manager / Parameter Store`: webhook secrets, SES config, allowed sibling-domain map, classifier patterns, and taxonomy version pointers

### 5.1 Worker Boundaries

- `Submit Lambda` is the control-plane entrypoint only. It owns auth, request validation, canonicalization, cache lookup, `Job`/`UrlTask` creation, and queue fan-out. It never fetches pages, runs OCR, or calls Bedrock.
- `Collection Worker Lambda` is the only stage allowed to launch Crawl4AI/Playwright against the exact input URL. It produces the `NormalizedPageSnapshot`, direct facts, page classification inputs, and ranked OCR candidates. It never calls Bedrock for keyword generation or assembles final exports.
- `OCR Worker Lambda` is a supplemental media-text stage only. It reads collection artifacts, runs PaddleOCR or the structured PP-StructureV3 branch on screenshots and ranked images, filters OCR blocks, and writes an OCR supplement artifact. It never refetches the page, changes the page class, or calls Bedrock.
- `Generation Worker Lambda` owns `Evidence Builder`, bounded fallback fetches, intent planning, Bedrock calls, supplementation passes, fixed-schema result rendering, and cache writes. It consumes collection/OCR artifacts and never launches Playwright or PaddleOCR.
- `Job Aggregator Lambda` is the only job-scoped reducer. It consumes terminal URL outcomes, recomputes job counters, writes combined exports, and decides whether the job is `COMPLETED`, `PARTIAL_COMPLETED`, or `FAILED`. It never re-runs URL collection, OCR, or generation logic.
- `SES/Webhook Sender Lambda` owns delivery side effects only. It reads job summary and download-link metadata and sends one email/webhook per terminal job. It never recomputes job state or exports.

### 5.2 Queue Boundaries And Artifact Handoffs

- All URL-scoped queues use `batch_size=1`. One queue message maps to one `url_task_id`; bulky artifacts are always stored in S3 and queue payloads carry only identifiers plus artifact references.

| Stage | Queue / trigger | Durable handoff written before emit | Next stage |
| --- | --- | --- | --- |
| Submit | synchronous API call | `Job`, `UrlTask`, cache decision, and job-scoped cached copies for cache hits | Cache miss -> `CollectionQueue`; cache hit -> `AggregationQueue` |
| Collection | `CollectionQueue` | `raw/` browser artifacts, `collection/normalized_snapshot.json`, `collection/direct_facts.json`, `collection/page_classification.json`, `collection/ocr_manifest.json` | Terminal page failure -> `AggregationQueue`; OCR required -> `OCRQueue`; OCR skipped -> `GenerationQueue` |
| OCR | `OCRQueue` | `ocr/ocr_result.json` with per-image status plus admitted OCR blocks | `GenerationQueue` |
| Generation | `GenerationQueue` | `evidence/evidence_pack.json`, per-URL result JSON or failure manifest, cache record for successful final output | `AggregationQueue` |
| Aggregation | `AggregationQueue` | Updated job counters, combined JSON, flattened CSV, `failures.json`, job summary, notification payload | `NotificationQueue` when job becomes terminal |
| Notification | `NotificationQueue` | Delivery log / outbox record on the `Job` item | Terminal side effect only |

- Cache hits do not bypass aggregation. `Submit Lambda` copies the cached final per-URL result into the current job prefix, marks the `UrlTask` as `COMPLETED_CACHED`, and emits the same terminal event shape that generation would have emitted.
- Collection is the last stage that may touch the live product page with a browser. Downstream stages operate on stored artifacts plus bounded fallback fetches only.
- OCR is optional per URL. If OCR is skipped, collection emits a `GenerationQueue` message with `ocr_status=SKIPPED`; if OCR exhausts retries, it emits `ocr_status=FAILED_SOFT` and generation continues without OCR evidence.
- Generation owns the handoff from page artifacts to semantic evidence. Upstream tasks should treat `evidence_pack.json` as the contract boundary, not raw HTML or screenshots.

### 5.3 Packaging Assumptions

- V1 stays on AWS Lambda + SQS. Do not introduce ECS/Fargate or Step Functions unless a later implementation task proves Lambda queue workers are insufficient.

| Worker | Packaging | Why this is locked for v1 |
| --- | --- | --- |
| `Submit Lambda` | zip | Request validation, DynamoDB, SQS, and cache-copy logic fit normal Lambda packaging. |
| `Collection Worker Lambda` | container image required | Crawl4AI, Playwright, Chromium, fonts, and browser system libraries are too heavy and OS-sensitive for zip packaging. |
| `OCR Worker Lambda` | container image required | PaddleOCR/PaddlePaddle plus image-processing native dependencies and model assets require a container build. |
| `Generation Worker Lambda` | zip by default | Bedrock invocation, validators, and evidence assembly do not require browser or OCR native stacks. |
| `Job Aggregator Lambda` | zip | Export assembly and counter updates are lightweight control-plane work. |
| `SES/Webhook Sender Lambda` | zip | Notification logic is lightweight and should stay isolated from heavy runtime images. |

- All workers assume `Python 3.13`, AWS Lambda AL2023, and `arm64` unless a later implementation task documents a concrete package incompatibility.

Current implementation note:

- The design target remains a separate `OCR Worker Lambda`, but the current deployable baseline has not split that worker out yet.
- In the code that exists today, OCR may still execute inside the deployed `collection-worker` via the `HtmlCollectionPipeline` OCR runner seam when OCR env flags are enabled.
- Operators must not assume that the reserved `ocr` queue means OCR is already isolated in production; memory and timeout sizing still apply to the deployed collection worker until the standalone OCR handler exists.
- Container images may share a base image family, but collection and OCR stay as separate deployables because their dependency graphs, memory profiles, and retry semantics differ.

### 5.4 Minimal Idempotency Boundaries

| Stage | Replay-safe key example | Overwrite-safe output boundary |
| --- | --- | --- |
| Submit | `submit:job_01HXYZ:url_hash_9ab3:platform_both:v1` | `Job` + `UrlTask` records and the initial queue emit for that URL within the same job |
| Collection | `collect:url_task_ut_01HXYZ:v1` | `s3://.../jobs/{job_id}/urls/{url_task_id}/collection/` |
| OCR | `ocr:url_task_ut_01HXYZ:ocr_policy_v1` | `s3://.../jobs/{job_id}/urls/{url_task_id}/ocr/` |
| Generation | `generate:url_task_ut_01HXYZ:platform_both:generator_v3` | `s3://.../jobs/{job_id}/urls/{url_task_id}/result/` plus the matching cache key |
| Aggregation | `aggregate:job_01HXYZ:export_v1` | `s3://.../jobs/{job_id}/summary/` and job counter fields on the `Job` item |
| Notification | `notify:job_01HXYZ:channel_email:v1` | Job-level notification outbox / `notification_sent_at` marker |

- Replayed collection/OCR/generation messages may overwrite only their own stage prefix for the same stage key. They must not delete sibling stage outputs or mutate another URL task.
- Aggregation is replay-safe because it derives job counters from current terminal `UrlTask` states plus per-URL result references, then rewrites the same summary keys.
- Notification is replay-safe only after the aggregator has written a job-scoped outbox marker. Sender retries may re-read the same payload, but they must short-circuit when the matching `notify:*` marker already exists.

### 5.5 Runtime Sizing And Queue Baseline

These are v1 starting points, not autoscaling promises. Later implementation tasks may raise memory or timeout values, but they should not lower them without evidence from runtime traces.

| Stage | Package | Timeout | Memory | Queue visibility timeout | Reserved concurrency posture | Operational owner |
| --- | --- | --- | --- | --- | --- | --- |
| Submit | zip | 30s | 512 MB | n/a | unreserved by default | API / control plane |
| Collection | container | 180s | 3072 MB | 1080s | reserved concurrency cap to protect merchant targets | collection stage |
| OCR | container | 120s | 4096 MB | 720s | low reserved concurrency to control CPU-heavy fan-out | OCR stage |
| Generation | zip | 90s | 2048 MB | 540s | moderate reserved concurrency, bounded by Bedrock throughput | generation stage |
| Aggregation | zip | 60s | 1024 MB | 360s | low reserved concurrency is acceptable | aggregation stage |
| Notification | zip | 30s | 512 MB | 180s | low reserved concurrency is acceptable | notification stage |

- Queue visibility timeout baseline is `6 x Lambda timeout` so one cold start plus two Lambda retries can occur before SQS redelivery.
- `CollectionQueue`, `OCRQueue`, and `GenerationQueue` stay `batch_size=1` to preserve URL-level isolation.
- `AggregationQueue` and `NotificationQueue` also stay `batch_size=1` in v1 because deduplication is job-scoped and operational simplicity matters more than throughput.
- `Generation Worker Lambda` must set Bedrock `max_tokens` explicitly. The operational baseline is `2000..4000`; do not rely on the provider default reservation behavior.
- Reserved concurrency on generation is the main Bedrock-throttle control in v1. If throttles rise, reduce generation concurrency before changing prompt shape.

## 6. Operational Reliability Baseline

### 6.1 Failure Modes And Retries

- Collection retry policy: `standard -> stealth -> extended wait/popup dismiss`, max 3 profiles total
- Known hard-block domains after two blocked confirmations: stop retrying and mark `FAILED_BLOCKED`
- Waiting/interstitial pages: one clean-session retry with longer wait; if still waiting, mark `FAILED_WAITING`
- OCR image failures: retry each image twice; OCR failure never fails the URL by itself
- Fallback doc fetch failures: skip that fallback source and continue if base evidence is still sufficient
- Bedrock retry policy: retry throttles and `5xx` twice with jitter. Invalid JSON or schema mismatch gets one immediate repair call
- Count shortfall policy: exactly one supplementation pass. If the requested platform still finishes `<100`, mark `FAILED_GENERATION`
- URL-scoped stages are idempotent by `url_task_id + stage + version`; job-scoped stages are idempotent by `job_id + stage + version`. Replayed messages overwrite only the same stage output or outbox marker
- URL-level failure never blocks sibling URLs. Job status is aggregated only after all URL tasks are terminal

### 6.2 Queue Retry Ownership And DLQ Policy

| Stage | Retry owner | Inline retry budget | Queue redrive baseline | DLQ action |
| --- | --- | --- | --- | --- |
| Submit | Lambda / API caller | no internal retry beyond DynamoDB conditional-write retry | none | synchronous API failure only |
| Collection | worker code + Lambda retry | fetch-profile sequence is the retry strategy; no extra blind queue-level replay for the same profile | `maxReceiveCount=3` on `CollectionQueue` | mark URL failed with the terminal collection failure code and emit `AggregationQueue` event |
| OCR | worker code + Lambda retry | each admitted image retried twice; OCR remains soft-fail | `maxReceiveCount=2` on `OCRQueue` | write `ocr_status=FAILED_SOFT` artifact and continue to generation without OCR evidence |
| Generation | worker code + Lambda retry | Bedrock throttle/5xx retry twice; one schema repair call; one targeted supplementation pass | `maxReceiveCount=2` on `GenerationQueue` | mark URL `FAILED_GENERATION` and emit terminal event to aggregation |
| Aggregation | Lambda retry only | recomputation is replay-safe; no partial aggregation retry loop in code | `maxReceiveCount=3` on `AggregationQueue` | operator alarm plus manual replay after cause is fixed |
| Notification | sender code + Lambda retry | transient delivery retry inside sender for one attempt where safe | `maxReceiveCount=3` on `NotificationQueue` | preserve outbox record, raise delivery alarm, allow manual replay |

- URL-scoped stages own translation from infrastructure failure into terminal URL outcome. Only aggregation translates URL outcomes into a job outcome.
- Collection and generation DLQs are operationally significant because they threaten user-visible completion. OCR DLQ is lower severity because OCR is soft-fail by design.
- Aggregation and notification DLQs are job-scoped. Their alarms should page operators because they can strand already-finished URL work without final artifacts or delivery.
- Manual replay rule:
  - collection/generation replay uses the same stage idempotency key and overwrites only the same stage prefix
  - aggregation replay is safe after any partial failure because summary artifacts are overwrite-safe
  - notification replay must reuse the existing outbox payload and preserve one-notification semantics

### 6.3 Stage Metrics And Alarm List

Required CloudWatch custom metrics:

| Metric | Dimensions | Emitted by | Alarm baseline |
| --- | --- | --- | --- |
| `JobsSubmitted` | `requested_platform_mode` | Submit | no alarm; dashboard only |
| `CacheHitCount` / `CacheMissCount` | `requested_platform_mode` | Submit | no alarm; trend dashboard |
| `UrlTaskTerminalSuccess` / `UrlTaskTerminalFailure` | `page_class`, `failure_code` | Generation or Collection terminal path | failure spike alarm when failure ratio exceeds 30% for 15 minutes |
| `CollectionBlockedCount` | `domain` | Collection | warn when a single domain exceeds 5 blocked URLs in 15 minutes |
| `OCRSoftFailureCount` | none or `domain` | OCR | ticket-level alarm only when persistent for 1 hour |
| `BedrockThrottleCount` | `model_id` | Generation | page when >10 throttles in 5 minutes |
| `GenerationValidationFailureCount` | `failure_code` | Generation | warn when >5 in 15 minutes for the same failure code |
| `AggregationCompletedJobs` | `job_status` | Aggregation | no alarm; dashboard only |
| `NotificationDeliverySuccess` / `NotificationDeliveryFailure` | `channel` | Notification | page when failure count >0 for 10 minutes |

Required AWS native alarms:

| Signal | Stage | Alarm baseline |
| --- | --- | --- |
| SQS `ApproximateAgeOfOldestMessage` | all queues | warn when > 5 minutes for URL queues or > 2 minutes for aggregation/notification |
| SQS `ApproximateNumberOfMessagesVisible` | all queues | warn on sustained backlog growth for 15 minutes |
| Lambda `Errors` | all workers | alarm on any sustained nonzero error rate for 5 minutes |
| Lambda `Throttles` | all workers | alarm on any sustained throttling for 5 minutes |
| Lambda `Duration p95` | collection/generation | warn when > 80% of configured timeout for 15 minutes |
| DLQ visible messages | every DLQ | page on first message for aggregation/notification, warn on first message for collection/generation/OCR |

Stage ownership:

- Submit owns cache-hit ratio, API error rate, and job-submission sanity metrics.
- Collection owns fetch-profile outcomes, blocker rates, and domain-specific failure spikes.
- OCR owns OCR admission volume and soft-failure drift, not final URL success rate.
- Generation owns Bedrock throttles, validation failures, repair-pass rate, and final URL success/failure counters.
- Aggregation owns job terminalization latency, summary artifact write errors, and job-status correctness metrics.
- Notification owns delivery success/failure, retry exhaustion, and channel-specific error codes.

### 6.4 Minimum Logs And Trace Correlation

- Every stage log line must include:
  - `job_id`
  - `url_task_id` for URL-scoped stages
  - `stage`
  - `requested_platform_mode`
  - `attempt`
  - `cache_hit` where applicable
- Generation logs must additionally include:
  - `model_id`
  - `max_tokens`
  - `repair_pass_used`
  - `quality_warning`
  - `failure_code` on terminal failure
- Aggregation and notification logs must include:
  - `submitted_count`
  - `succeeded_count`
  - `failed_count`
  - `job_status`
- A single correlation ID equal to `job_id` is sufficient for X-Ray root trace linkage in v1. URL-scoped subsegments use `url_task_id` annotations.

## 7. Test / Acceptance Criteria

- `commerce_pdp`: produces `>=100` rows for the requested platform, all 10 categories present, `quality_warning=false` when sufficient
- `both` request: produces `>=100` Naver rows and `>=100` Google rows independently, with all 10 categories present for each platform
- `image_heavy_commerce_pdp`: OCR contributes admitted facts and improves attribute/long-tail coverage without leaking banner/logo text
- `marketing_only_pdp`: classified correctly, price/promo claims are suppressed, generation still succeeds if evidence is otherwise sufficient
- `product_marketing_page`: classified correctly, no fake price or discount terms, product-specific purchase, problem, and long-tail terms still generate
- `support_spec_page`: classified correctly, specs feed attribute, problem, and long-tail categories, no discount or coupon terms are emitted from support-only evidence
- `document_download_heavy_support_page`: only model-matching linked docs are used; unrelated manuals are ignored
- `promo_heavy_commerce_landing` and `non_product_page`: fail as unsupported input with no keyword export rows
- `waiting_page` and `blocked_page`: correct terminal failure reason, retries stop at the defined cap, sibling URLs still complete
- Encoding test: mojibake normalizes before extraction; Korean evidence survives into final keywords
- Cache test: same canonical URL within 7 days returns without regeneration; policy-version bump invalidates cache
- Partial completion test: mixed success/failure job produces combined export for successes, failures manifest, correct final job status, and exactly one notification
- Count-fill test: sparse but supported pages reach quota only through the approved backfill order; unsupported promo terms never appear
- Single-platform test: only the requested platform is generated and validated, and the other platform field is blank in export rows

## 8. Locked Assumptions For V1

These are treated as implementation defaults, not open design space:

- Output schema remains fixed as defined in the requirement.
- Request mode is one of `naver_sa`, `google_sa`, or `both`. `both` is a first-class mode that generates and validates both platforms independently from one shared evidence pack.
- Generic keyword language follows the Korean market default; observed brand/model tokens remain in source language.
- Search snippet fallback is disabled in v1.
- Promo expansion outside the exact page is disallowed unless the exact page directly links to a same-product promo page.
- OCR runs as a supplemental path only and never becomes a hard dependency for URL success.
- Competitor, season/event, and problem taxonomy vocabularies are versioned service-owned assets and are not auto-learned at runtime.
