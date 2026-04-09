# Active Handoff

## Purpose

Keep the current goal, locked decisions, and immediate next work visible between Claude and Codex sessions.

## Operating Rules

- This file is a current-state summary only.
- Keep background short and decision-oriented.
- Move unresolved questions to `docs/OPEN_QUESTIONS.md`.
- When a task completes, record the durable output location and promote the next task.

## Current Goal

- Redesign keyword generation around a two-stage `interpretation -> rendering` flow
- Keep quality above floor: low-quality rows must be dropped even when that causes shortfall

## Current Status

  - 2026-04-09 residual semantic hardcoding cleanup completed for deterministic rendering:
  - `src/keyword_generation/service.py` no longer expands observed audience phrases like `건성 복합성 피부` into split audience tokens such as `건성 피부` / `복합성 피부`; deterministic generation now keeps the observed audience phrase intact
  - `problem_solution` seed construction is now concern-only: `problem_noun_phrases` no longer absorb `audience` or `usage_context` values just to widen slot coverage
  - concern rendering no longer strips temporal clauses like `수면 중` and no longer appends handcrafted `케어` suffixes; deterministic `problem_solution` rows now stay anchored to the observed concern phrase plus the category head/type only
  - focused regressions now lock the new contract in `tests/test_generation_quality.py` and `tests/test_slot_planning.py`
  - targeted verification passes locally via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m py_compile src\keyword_generation\service.py tests\test_generation_quality.py tests\test_slot_planning.py` and `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_generation_quality.py tests\test_slot_planning.py -q`

  - 2026-04-09 Bedrock Step A payload slimming and count-aware supplementation completed:
  - `src/keyword_generation/bedrock_adapter.py` Step A / supplementation prompts now prefer lightweight `items[]` payloads (`category` + `keyword`) instead of requiring full render/reason metadata up front
  - legacy `intents[]` and `rows[]` parsing remains supported, but lightweight `items[]` now hydrate internal `CanonicalIntent` values with generated `intent_id`, default `slot_type`, inferred renders, and downstream default reasons
  - `src/keyword_generation/service.py` now aligns Step A planning with `initial_generation_target` instead of the final floor target, and supplementation can add count-repair volume on top of category/slot gap repair
  - `src/clients/bedrock.py` now defaults `BEDROCK_MAX_TOKENS` to `6000` and surfaces Bedrock `stop_reason` / `usage` metadata for debug payloads
  - Terraform defaults now match the new token budget in `infra/terraform/variables.tf`, `infra/terraform/terraform.tfvars.example`, and `infra/terraform/dev.auto.tfvars`
  - focused regression coverage now locks lightweight item parsing, downstream reason filling, shared-render hydration, and count-aware supplementation in `tests/test_bedrock_adapter.py`, `tests/test_bedrock_quality_contract.py`, and `tests/test_bedrock_shared_render.py`
  - 2026-04-09 adaptive multi-batch generation is now active on top of the lightweight Step A contract:
  - `src/keyword_generation/service.py` now runs cluster-first generation batches (`brand/generic/purchase`, `feature/price`, `long_tail/problem/season`, `competitor/negative`) instead of one monolithic Step A Bedrock call
  - weak clusters now split into narrower follow-up batches only when batch-local category hits or volume are too low, so the runtime does not pay fixed per-category fanout cost on every URL
  - batch activation no longer depends on slot-plan presence alone; categories with a target but sparse slot seeds still receive a generation batch, which prevents weak categories from disappearing before Bedrock is called
  - metadata handling is now backward-tolerant inside the runtime: generation, dedup, and supplementation callers accept both `(result, metadata)` tuples and legacy bare return values, which keeps focused tests and partial mocks compatible while the live path records per-batch metadata
  - `src/keyword_generation/bedrock_adapter.py` response parsing now unwraps fenced JSON / nested wrapper payloads before looking for `items[]`, `intents[]`, or `rows[]`, reducing live parser failures from non-canonical Bedrock wrappers
  - Bedrock parse failures now preserve raw response context instead of collapsing into a plain `ValueError`: `src/keyword_generation/bedrock_adapter.py` raises `BedrockResponseParseError` with `stage`, `model_id`, `usage`, and `response_text`, and `src/keyword_generation/service.py` attaches that context (including failed `batch_name` / `categories` when available) to `GenerationResult.debug_payload`
  - Bedrock parser tolerance now accepts lightweight `keywords[]` wrappers in addition to `items[]`, `intents[]`, and `rows[]`, so live contract drift no longer hard-fails when the model returns the same payload under a different top-level key
  - category cleanup is now tightened through evidence/shape admissibility instead of literal blacklists:
    - `feature_attribute` rows must overlap grounded spec/attribute evidence
    - `season_event` rows must overlap grounded event terms or explicit usage-context evidence
    - `problem_solution` rows must overlap explicit concern/use-case evidence rather than derived product-type scaffolds
  - legacy concern-specific phrase templates were removed from deterministic generation: `_concern_surface_forms()` now derives surfaces from the normalized evidence phrase itself instead of hardcoded mappings like `수분 부족 -> 수분 부족 케어`, `당김 -> 피부 당김`, or similar concern-by-concern boosts
  - deterministic broad-token uplift helpers were also reduced:
    - skincare-specific category aliases like `슬리핑마스크 -> 수면팩/슬리핑팩` were removed from `_category_aliases()`
    - generic-category and long-tail banks no longer synthesize extra rows from broad `benefit` / `concern` / `usage_context` token templates
    - dead semantic helper paths such as `_benefit_category_phrases()`, `_concern_category_phrases()`, `_usage_category_phrases()`, and `_default_signal_terms()` were deleted
  - focused batching regressions now live in `tests/test_bedrock_batching.py`
  - focused parser/admissibility regressions now live in `tests/test_bedrock_adapter.py` and `tests/test_keyword_category_admissibility.py`
  - targeted verification passes locally via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_bedrock_batching.py tests\test_bedrock_adapter.py tests\test_bedrock_quality_contract.py tests\test_bedrock_shared_render.py tests\test_slot_planning.py -q` and `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_generation_quality.py tests\test_keyword_surface_policy.py tests\test_bedrock_batching.py tests\test_bedrock_adapter.py tests\test_bedrock_quality_contract.py tests\test_bedrock_shared_render.py tests\test_slot_planning.py -q`

  - 2026-04-09 collection/classifier live PDP recovery completed:
  - `src/collection/service.py` now falls back to `og:title`, `og:description`, and structured `Product` fields when `<title>` is generic or missing, so product identity is no longer tied to brand-shell titles alone
  - `single_product_confidence` now uses structured product presence, broader product URL patterns, product-level tokens, and sellability signals instead of a narrow title-only heuristic
  - `promo_heavy_commerce_landing` no longer wins over strong PDP evidence; Apple/Samsung/Rankingdak-style pages with real product/sellability signals now classify as supported commerce pages
  - Bedrock product gate is skipped for `blocked_page`, `waiting_page`, and support-page classes, and its prompt now uses product name plus decoded-text fallback when visible blocks are low-signal
  - blocker detection now recognizes AWS WAF / challenge HTML markers such as `window.awsWafCookieDomainList` and `gokuProps`, so Gentle Monster style challenge pages are reported as `blocked_page` instead of `non_product_page`
  - focused regressions added in `tests/test_collection_html.py` and `tests/test_collection_pipeline.py`
  - local verification passes via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m py_compile src\collection\service.py tests\test_collection_html.py tests\test_collection_pipeline.py` and `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_collection_html.py tests\test_collection_pipeline.py -q`
  - post-fix live classifier probe on the five candidate URLs now returns:
    - Apple iPhone 16: `commerce_pdp`
    - Samsung S25 case: `commerce_pdp`
    - Rankingdak chicken PDP: `commerce_pdp`
    - Olive Young Innisfree PDP URL: `waiting_page`
    - Gentle Monster item URL: `blocked_page`
  - real external generation smoke now has a dedicated path:
    - `tests/test_runtime_bedrock_live.py` includes external-URL Bedrock smoke cases for Apple iPhone 16, Samsung S25 case, and Rankingdak chicken PDP
    - these smokes bypass the `moto` runtime harness entirely and call `HttpPageFetcher -> collect_snapshot_from_html -> classify_snapshot -> build_evidence_pack -> generate_keywords` directly
    - reason: `moto.mock_aws()` is valid for S3/DynamoDB/SQS seams, but it is not a trustworthy harness for real Bedrock generation verification because the local mixed seam can surface `Converse 404 Not yet implemented`

- 2026-04-09 OCR quality-first routing expanded for broad sweep plus table-like branches:
  - `src/ocr/service.py` now classifies ranked assets as `general_detail_image` vs `table_like_image` before execution; table-like candidates carry `ocr_pipeline_type=structured_table` while broad-sweep candidate retention stays unchanged
  - `src/ocr/runner.py` now supports gated structured OCR via `KEYWORD_GENERATOR_OCR_STRUCTURED_ENABLED=1`, optional rectification via `KEYWORD_GENERATOR_OCR_RECTIFY_ENABLED=1`, and configurable subprocess timeout via `KEYWORD_GENERATOR_OCR_TIMEOUT_SECONDS`; structured candidates route to `PPStructureV3`, general candidates stay on `PaddleOCR`, and both paths retain WEBP->PNG conversion plus Windows CPU-safe flags
  - `ocr_result` now persists per-image execution metadata under `image_results[]`, including `candidate_type`, `pipeline_type`, `engine_used`, `raw_block_count`, `raw_char_count`, `admitted_block_count`, `rejected_block_count`, and `error`
  - `HtmlCollectionPipeline` no longer executes the OCR runner for unsupported page classes by default; local/dev experiments must opt in explicitly with `allow_ocr_for_unsupported=True` or `KEYWORD_GENERATOR_OCR_ALLOW_UNSUPPORTED=1`
  - `scripts/verify_collection_ocr.py` can now execute page-image OCR through the runtime seam with `--run-page-ocr`, and unsupported-page OCR experiments remain local/dev-only behind `--allow-ocr-on-unsupported`
  - regression coverage now locks table-like candidate routing, per-image OCR metadata accounting, unsupported-page OCR guardrails, and the explicit local/dev escape hatch in `tests/test_ocr_policy.py` and `tests/test_collection_pipeline.py`
  - local real-engine follow-up on 2026-04-09:
    - structured OCR was initially blocked because `.venv-paddleocr` had `paddlex` base installed without the `ocr` extra; the missing set included `beautifulsoup4`, `einops`, `ftfy`, `Jinja2`, `lxml`, `openpyxl`, `premailer`, `regex`, `scikit-learn`, `scipy`, `sentencepiece`, `tiktoken`, and `tokenizers`
    - after installing those dependencies into `.venv-paddleocr`, `PPStructureV3` instantiated successfully and a local table-like smoke on `.tmp/ocr_smoke/airpods_specs_text.png` returned `52` raw blocks / `915` chars via `engine_used=PPStructureV3`
    - live APRILSKIN ranking root cause was decorative runtime assets outranking detail banners (`/web/upload/images/`, `.svg`, `echosting.cafe24.com` GIFs, templated JS URLs such as `product/'+stickImgSrc+'`); OCR policy now rejects those assets before the broad sweep and treats `/web/product/extra/` as a detail-priority path
    - OCR admission root cause on APRILSKIN was policy-side, not engine-side: useful short lines such as `MUGWORT`, `CALMING SERUM`, and ingredient names were being dropped as `too_short_without_product_tokens` before downstream relevance filtering
    - OCR admission now preserves short image-line blocks when they carry at least one matched token, multiple alpha/Korean terms, a single long term, or table-like code text; image OCR also skips the unrelated-product-name rejection that was designed for HTML text
    - refreshed live smoke on `https://aprilskin.com/product/detail.html?product_no=1448` now completes without timeout and returns `ocr_ranked_image_count=5`, `ocr_admitted_block_count=74`, `fact_count=30`

- 2026-04-09 Bedrock generation slot-plan contract wired for category-slot filling:
  - `src/keyword_generation/service.py` now expands `ProductInterpretation` with slot-friendly facets: `grounded_event_terms`, `price_band_candidates`, `navigational_aliases`, `problem_noun_phrases`, and `generic_type_phrases`
  - Bedrock path now builds a per-category `slot_plan` before generation, keeps `slot_type` on `CanonicalIntent` and `KeywordRow`, and computes `slot_gap_report` / `slot_drop_report` instead of relying only on broad category gaps
  - `src/keyword_generation/bedrock_adapter.py` generation prompts now declare `generation_mode=category_slot_filling`, include `slot_plan`, require `slot_type` in `intents[]`, and supplementation now targets `gap_slots`
  - dedup parsing accepts `slot_gap_report` while remaining backward-compatible with legacy `gap_report`
  - per-URL debug payloads now include `slot_plan`, `pre_policy_slot_gap_report`, `slot_gap_report`, and `slot_drop_report`
  - focused regression coverage added/updated in `tests/test_bedrock_adapter.py`, `tests/test_bedrock_quality_contract.py`, `tests/test_bedrock_shared_render.py`, and `tests/test_slot_planning.py`
  - targeted verification passes locally via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_bedrock_adapter.py tests\test_bedrock_quality_contract.py tests\test_bedrock_shared_render.py tests\test_keyword_surface_policy.py tests\test_slot_planning.py -q` and `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_generation_quality.py tests\test_bedrock_quality_contract.py tests\test_bedrock_shared_render.py tests\test_bedrock_adapter.py -q`
  - follow-up stabilization shipped the same day:
    - legacy Bedrock `rows[]` payloads now default missing `slot_type` values instead of letting slot-gap accounting treat them as empty coverage
    - slot completion semantics are now `category hard / slot soft`: supplementation derives hard repairs from category-presence gaps first, then asks for at most one uncovered preferred slot per remaining category instead of forcing every active slot
    - `slot_plan` now marks primary required slots explicitly, Bedrock prompts tell the model not to force weak slot diversity, and supplementation carries `missing_categories` alongside `gap_slots`
    - `slot_drop_report` is now a structured debug artifact with `drop_stage`, `drop_reason_code`, and `drop_reason_detail` instead of a raw dropped-row copy
  - dedicated real-Bedrock verification is now available:
    - `tests/test_runtime_bedrock_live.py` adds a `live_bedrock` suite that exercises real Bedrock across classifier gate, thin-pack fact lift, and end-to-end runtime generation
    - live execution is explicitly gated by `RUN_LIVE_BEDROCK_TESTS=1`; default test runs stay deterministic/mock-based
    - `tests/conftest.py` now preserves AWS profile env only for the live suite and probes Bedrock once before running live assertions, skipping when the environment is unavailable
    - Laneige snapshot fixtures for live parity now live under `tests/fixtures/laneige_retinol_live_snapshot.json` and `tests/fixtures/laneige_retinol_thin_snapshot.json`

- 2026-04-08 surface policy tightened for user-like search behavior:
  - `src/keyword_generation/service.py` now treats informational/help-query surfaces structurally instead of blocking one-off strings:
    - commerce PDP rows containing `방법`, `사용법`, `가이드`, setup/pairing/how-to style phrasing are dropped by post-policy cleanup
    - product-name-prefixed purpose surfaces such as `Apple Pencil 그림용` are dropped, while short model alias navigational forms such as `Apple Pencil 1` remain allowed
    - `benefit_price` now allows search-like price surfaces (`<product> 가격`, `<price band> + product type`) and rejects raw exact-number surfaces such as `149000` / `149,000원`
    - promo-event rows (for example `블랙프라이데이`) are no longer categorically banned, but are allowed only when the same event is grounded in admitted evidence text
  - `src/keyword_generation/bedrock_adapter.py` prompts now explicitly prohibit informational/how-to commerce queries, unsupported promo-event rows, raw exact-price-number rows, and product-name + purpose suffix surfaces
  - regression coverage added in `tests/test_keyword_surface_policy.py`
  - targeted keyword-surface regressions pass locally via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests\test_keyword_surface_policy.py tests\test_bedrock_quality_contract.py tests\test_bedrock_shared_render.py -q`
  - note: the full local suite currently shows two unrelated OCR ranking regressions in `tests/test_collection_pipeline.py` and `tests/test_ocr_policy.py`; this surface-policy change does not touch OCR code paths

- 2026-04-08 `both` shared-render contract added:
  - `src/keyword_generation/models.py` now distinguishes a platform-neutral `shared_render` from optional `naver_render` / `google_render` overrides
  - `src/keyword_generation/bedrock_adapter.py` prompt schema now tells Bedrock to use `shared_render` by default and only emit platform overrides when the surface should differ
  - Bedrock parsing now hydrates missing platform renders from `shared_render` in `both` mode, so Google-only outputs no longer collapse into one-sided rows by default
  - deterministic intents in `src/keyword_generation/service.py` also emit `shared_render`, keeping the non-Bedrock path aligned with the same contract
  - Bedrock dedup now honors stable `intent_id` first instead of relying on free-text `intent_text` matching
  - generation results now persist `debug` payloads in `per_url.json`, including raw intents, dedup results, pre/post-policy rows, dropped rows, and platform gap reports
  - stricter surface cleanup now drops product-plus-action phrases such as `Apple Pencil 구매`, `Apple Pencil 그림 그리기`, and `Apple Pencil 문서 주석 작성`
  - regression coverage added in `tests/test_bedrock_shared_render.py` and `tests/test_bedrock_quality_contract.py`
  - full local suite passes with `108 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
  - dev `gen_v22` deployed from `lambda-packages/keyword-generator-20260408-171551.zip`
  - post-deploy live smoke on Apple Pencil still ends as `FAILED_GENERATION`, but:
    - previous Google-only split remains fixed
    - `apple pencil 구매`, `apple pencil 그림 그리기`, and `apple pencil 문서 주석 작성` no longer survive to final rows
    - current remaining quality problems are noun-ish but still weak surfaces such as `apple pencil 충전방법`, `apple pencil 블랙프라이데이`, `apple pencil 그림용`, `apple pencil 필기감`, and `apple pencil 149000`

- 2026-04-08 golden-set quality tuning scaffold completed:
  - `src/quality_eval/golden.py` now provides a repo-local golden-set contract, source loader, keyword normalization, and per-platform `must_keep` / `must_not_emit` / `forbidden_substrings` / `required_categories` evaluation
  - `tests/evaluate_golden_sets.py` is the local golden-set smoke entrypoint; it reuses current generation and reports case-by-case REWORK/PASS without adding runtime prompt tokens
  - initial cases now live under `tests/golden_sets/`:
    - `laneige_retinol_live.json` reuses legacy `gen_v10` retinol/serum surfaces as quality seeds while banning placeholder/scaffold carryovers
    - `airpods_pro_live.json` bans skincare leakage and requires audio-category basics
    - `support_spec_fixture.json` blocks obvious purchase/comparison scaffolds on support-heavy evidence
  - regression coverage added in `tests/test_golden_set_eval.py`
  - current smoke on `airpods_pro_live` returns `REWORK`: both platforms still miss `wireless earbuds`, which confirms the evaluator is catching the present Bedrock/output quality gap instead of silently passing it

- 2026-04-08 `gen_v20` dev deployment completed for Bedrock-first generation and live artifact debugging:
  - dev `generation_mode` is now `bedrock`, with default cross-region Sonnet candidates verified locally via `tests/check_bedrock_access.py`
  - `infra/terraform/compute.tf` now sets `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` for every zip Lambda
  - `src/handlers/runtime_factory.py` now reconfigures `stdout` / `stderr` to UTF-8 with `backslashreplace`, and `tests/test_runtime_factory.py` locks the bootstrap behavior
  - `src/collection/service.py` Bedrock product gate no longer reads a nonexistent `snapshot.visible_text`; it now builds the excerpt from `visible_text_blocks` or `decoded_text`, and `tests/test_collection_pipeline.py` locks the regression
  - latest live smoke on `https://www.on.com/en-us/products/cloudmonster` now reaches `FAILED_GENERATION` with persisted partial rows instead of stalling in collection:
    - `job_id=job_0001`
    - `page_class=commerce_pdp`
    - `failure_code=generation_count_shortfall`
    - current Bedrock rows are Google-only and cover `brand`, `generic_category`, `feature_attribute`, `purchase_intent`, `long_tail`, `season_event`, and `problem_solution`, still missing `competitor_comparison` and `negative` while providing no Naver rows
  - the remaining blocker is prompt/render completeness for `both` mode and full category coverage, not runtime collection stability

- 2026-04-08 Windows OCR smoke root cause identified and local workaround validated:
  - the previous OCR-engine failure was not an OCR-policy issue; PaddleOCR on Windows CPU was entering the default `mkldnn/cinn` inference path and failing in oneDNN/PIR conversion with `ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]`
  - `scripts/verify_collection_ocr.py` now runs OCR smoke through the real base interpreter declared in `.venv-paddleocr/pyvenv.cfg`, injects `.venv-paddleocr/Lib/site-packages` into `PYTHONPATH`, and forces `device='cpu'`, `enable_mkldnn=False`, `enable_cinn=False`, `enable_hpi=False`
  - a local OCR smoke against `.tmp/ocr_smoke/airpods_specs_text.png` now returns non-empty text (`14` blocks) instead of crashing; use this workaround path for any Windows OCR verification until the runtime stack is cleaned up
  - this validates the engine path for local smoke only; product-detail OCR should still be rechecked on a real text-heavy detail image before calling the OCR rollout complete

- 2026-04-08 detail-image OCR path is now wired for quality-first collection:
  - collection no longer stops at literal `<img src=...>`; it also captures lazy/detail assets from `data-src`, `data-lazy-src`, `data-original`, `ec-data-src`, and `srcset`, and preserves candidate metadata such as the source attribute and `detail_hint`
  - OCR policy now raises `detail_image_candidate` for hidden detail banners and ranks `/web/upload/webp/...`-style assets ahead of generic hero/product-shot images, so APRILSKIN-style detail content is eligible even when the page already has enough HTML text
  - `HtmlCollectionPipeline` now accepts an optional OCR runner; when OCR is triggered but no source blocks exist yet, it can execute OCR against ranked image candidates, inject the recovered blocks into the snapshot, and rerun OCR admission before evidence assembly
  - regression coverage now locks hidden detail image extraction, detail-candidate prioritization, and the runtime seam that converts runner output into admitted OCR evidence
  - quality-first fallback now prefers a broad OCR sweep over aggressive early ranking cuts: OCR policy no longer truncates ranked candidates to a tiny top-k, and the subprocess OCR runner defaults to scanning up to 24 eligible images before later optimization

- 2026-04-08 scraping/OCR verification helper added and exercised:
  - `scripts/verify_collection_ocr.py` now verifies fixture scraping/classification, live URL scraping, and separate OCR-engine smoke without depending on final keyword-count success
  - local fixture verification passes for `commerce_pdp`, `support_spec_page`, and `blocked_page`
  - live smoke against Aesop and Laneige confirms current scraping/classification/evidence assembly is healthy on real URLs
  - local OCR engine smoke is still blocked on the Windows PaddleOCR runtime in `.venv-paddleocr`; the subprocess reaches the installed runtime but fails with `ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]`
  - do not mark OCR as verified from `tests/test_ocr_policy.py` alone; engine verification must pass through `scripts/verify_collection_ocr.py`

- 2026-04-08 Bedrock-first category-completion refactor completed:
  - `src/keyword_generation/bedrock_adapter.py` no longer sends a coarse `domain` field; prompt interpretation now exposes `product_types`, `canonical_category`, typed evidence facets, required positive categories, negative-category requirement, and the ideal per-category target mix
  - Bedrock generation prompts now explicitly require all 9 positive categories plus the negative category, and instruct the model to own category completion directly instead of relying on deterministic fallback buckets
  - `src/keyword_generation/service.py` now uses an LLM-specific category plan for Bedrock mode, recomputes supplementation gaps deterministically from surviving category counts, and no longer silently falls back to deterministic generation when the Bedrock pipeline errors
  - `tests/test_bedrock_adapter.py` now locks the required-category prompt contract and the explicit failure path for Bedrock errors
  - full local suite passes with `97 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`

- 2026-04-08 generation seed refactor completed for evidence-first keyword rendering:
  - `src/keyword_generation/service.py` no longer injects `season_event` or `problem_solution` rows from default season seeds, season taxonomy seeds, or product-family fallback buckets
  - `usage_context` normalization is now conservative and keeps source-grounded values instead of synthesizing labels such as `야간 케어` or `데일리 루틴`
  - `season_event` rows are now generated only from usage-context evidence, and `problem_solution` rows no longer append taxonomy-backed concern seeds beyond direct evidence
  - the unused `cosmetics/electronics/fashion/general` interpretation-family split was removed from `ProductInterpretation`
  - `tests/test_generation_quality.py` now locks that audio pages do not invent `season_event` or `problem_solution` rows, and the quality tests separate row quality from floor attainment
  - full local suite passes with `97 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`

- 2026-04-08 failed-generation artifact persistence completed:
  - `src/runtime/service.py` now writes `result/per_url.json` even when keyword generation ends as `FAILED_GENERATION`
  - the failed-task manifest entry now points to `result/per_url.json` when that partial result exists, while `failure.json` remains the failure-summary artifact
  - `tests/test_runtime_e2e.py` now locks that failed generation still persists rows plus validation metadata for later live review
  - full local suite passes with `96 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`

- 2026-04-08 `gen_v14` dev deployment completed with the semantic-cleanup package `lambda-packages/keyword-generator-20260408-142843.zip`:
  - `infra/terraform/dev.auto.tfvars` now points to `generator_version = "gen_v14"` and the new zip package
  - post-deploy live smoke still fails for both Laneige (`job_0001`) and AirPods (`job_0002`) with `generation_count_shortfall` / `naver_sa positive rows below 100`
  - both latest manifests currently point only to `result/failure.json`, so current-run keyword rows are still not persisted on failed jobs

- 2026-04-08 evidence semantic cleanup completed for domain-agnostic hardcoded term leakage:
  - `src/evidence/service.py` no longer promotes `benefit` / `problem_solution` / `use_case` facts from broad hardcoded Korean keyword maps such as `보습`, `건조`, `장벽`, `야간`, or `수면`
  - evidence promotion now relies on narrower structural signals, ingredient patterns, benefit phrases, and block-filtered text instead of domain-agnostic fixed-word boosts
  - AirPods-style commerce pages no longer leak skincare semantics during local evidence reconstruction; a local reproduction now returns only `brand`, `product_category`, and `product_name`
  - `tests/test_evidence_builder.py` now locks the non-leakage regression for AirPods pages and relaxes sparse-fallback expectations so generic concern uplift is no longer required
  - full local suite passes with `95 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`

- 2026-04-08 live Laneige investigation identified two concrete root causes and shipped the first local remediation:
  - `src/runtime/service.py` still allocates `job_id` from in-memory `_job_sequence`, so Lambda cold starts can reuse `job_0001`; because failed URLs write only `failure.json` and never overwrite `result/per_url.json`, stale success artifacts can remain beside current failure artifacts for the same `job_id`/`url_task_id`
  - the actual live Laneige failure is not collection/OCR; latest live `evidence_pack.json` is valid commerce evidence, but deterministic generation still shortfalls on that evidence
  - `src/evidence/service.py` now falls back to `decoded_text` block-splitting when `visible_text_blocks` are present but too sparse to represent the page body, fixing the case where title-only blocks prevented body facts like `15ml / 30ml`, `야간`, `민감`, and ingredient/spec clues from being promoted
  - `tests/test_evidence_builder.py` now locks the sparse-visible-block fallback behavior
  - `src/keyword_generation/service.py` now prefers more specific category candidates over broad top-level values like `스킨케어` when the evidence supports them, and `tests/test_generation_quality.py` now locks that category interpretation behavior
  - local reproduction against the live Laneige snapshot improved from `naver_sa=41` / `49 rows` to `naver_sa=74` / `82 rows`, but the URL still fails floor because deterministic rendering remains too narrow for this evidence set
  - full local suite now passes with `94 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`

- 2026-04-08 competitor category redesign completed for quality-first comparison handling:
  - `src/keyword_generation/service.py` no longer treats same-product `용량 비교` or `70ml 25ml 비교` rows as `competitor_comparison`
  - deterministic `competitor_comparison` now uses weak type-level competitor brand seeds and renders only `competitor brand + product type` surfaces; current-brand-only and measurement-only comparison rows are blocked
  - `src/keyword_generation/policy.py` now enforces competitor safety: competitor rows must include a non-current competitor brand, must include the active product type, and cannot be generic comparison filler or same-product measurement comparisons
  - `src/keyword_generation/bedrock_adapter.py` now exposes `competitor_brand_hints` and requires LLM-generated competitor rows to use non-current competitor brands plus the product type; same-product measurement comparisons are explicitly prohibited in generation, dedup, and supplementation prompts
  - regression coverage in `tests/test_generation_quality.py` now locks competitor-brand outputs instead of self-comparison outputs; `tests/test_bedrock_adapter.py` now asserts competitor-brand prompt hints
  - rich commerce fixture competitor output is currently `이니스프리 슬리핑 마스크`, `메디힐 슬리핑 마스크`, `닥터자르트 슬리핑 마스크`, `에스트라 슬리핑 마스크`
  - full local suite passes with `92 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
- 2026-04-08 generation mix rebalance completed for deterministic quality-first rendering:
  - `src/keyword_generation/service.py` now applies the same surface-policy guard during phrase-bank selection that post-filter cleanup applies after rendering, so weak scaffold/logistics rows do not consume quota before validation
  - default `purchase_intent` generation now uses exact/navigational queries instead of `구매` / `주문` suffix templates; logistics filler like `구매처`, `판매처`, `재고`, or `배송` is also blocked from default selection
  - merchandising-heavy surfaces such as `베스트셀러`, `신상품`, and `어워드 위너` are now rejected before selection unless verbose surfaces are explicitly enabled
  - fallback/default signal seeds no longer inject `구매 전 체크`-style scaffolds when type-specific evidence is weak
  - regression coverage in `tests/test_generation_quality.py` now explicitly blocks purchase/order/logistics scaffolds while keeping the mask-category quality assertions
  - commerce rich fixture floor is restored without reintroducing bottom-funnel filler; local suite passes with `86 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
- 2026-04-08 generation surface cleanup completed for feature/price/season buckets:
  - `feature_attribute` now renders spec-only rows for cosmetics fixtures instead of product-name + ingredient/technology/form-factor/benefit copies
  - `benefit_price` now behaves as a price bucket (`제품명 가격`, `카테고리 가격`) and no longer emits `효과` / `장점` / benefit-sentence templates
  - `season_event` now prefers generic situational search heads (`야간 슬리핑 마스크`, `겨울 보습 마스크`, `수면팩`) instead of product-name-prefixed content phrases like `데일리 루틴` or `건조한 날씨`
  - `generic_category` / `long_tail` now absorb natural category aliases such as `수면팩` / `슬리핑팩`, preserving floor without reverting to explanation-like keyword templates
  - regression coverage in `tests/test_generation_quality.py` now locks spec-only feature rows, price-only benefit rows, generic season heads, and ingredient search heads such as `스쿠알란 마스크`
  - full local suite passes with `90 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
- 2026-04-08 problem/comparison cleanup completed for final surface review:
  - `problem_solution` no longer emits product-name-prefixed care templates and now normalizes concerns into direct search forms such as `수분 부족 케어 마스크`, `피부 당김 케어 마스크`, `민감 피부 케어 마스크`, and `피부 장벽 케어 마스크`
  - `season_event` seed rendering now flips suffix-style phrases into search-shaped forms such as `야간 케어 마스크`, `겨울 보습 슬리핑 마스크`, and `건조 시즌 마스크`
  - `competitor_comparison` now drops generic category-level volume-comparison queries and keeps only exact product comparison rows
  - regression coverage in `tests/test_generation_quality.py` now locks the absence of product-prefixed problem rows and generic comparison filler
  - full local suite passes with `92 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
- 2026-04-08 evidence extraction hardening completed for live thin-pack regressions:
  - `src/evidence/service.py` now treats evidence assembly as layered extraction instead of a few title/text heuristics
  - JSON-LD `Product` / `Offer` / breadcrumb signals now feed `brand`, `product_name`, `product_category`, and guarded `price` candidates before legacy fallbacks
  - textual extraction now lifts `benefit`, `key_ingredient`, `technology`, `volume`, `variant`, `texture`, `audience`, and `problem_solution` facts from `title`, `meta_description`, structured descriptions, decoded text, and admitted OCR
  - decoded-text fact promotion now drops block-level navigation, badge, lineup, and URL noise before semantic extraction, instead of letting menu/global UI text leak into facts
  - structured/breadcrumb category candidates that are URL-like are now rejected before `product_category` promotion
  - support-page evidence no longer emits commerce `price` facts even if offer payloads exist
  - thin supported commerce packs now raise `quality_warning_inputs += thin_pack`; when Bedrock mode is enabled, a constrained fact-lift fallback may add grounded evidence from admitted source fields only
  - regression coverage now includes live-style Laneige retinol snapshot enrichment, nav/badge block filtering, and thin-pack Bedrock fallback guardrails
  - full local suite passes with `84 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
- 2026-04-08 local verification rerun completed:
  - fixed corrupted prompt/test literals in `src/keyword_generation/bedrock_adapter.py` and `tests/test_bedrock_adapter.py` so the Bedrock generation path imports cleanly again
  - `competitor_comparison` replenishment now uses measurement-pair comparison phrases when variant evidence is strong enough, restoring the cosmetics fixture floor without reintroducing weak comparison filler
  - full local suite passes again with `80 passed` via `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -q`
- 2026-04-07 dev quality hardening rollout is partially verified:
  - shared policy/taxonomy hardening shipped in `gen_v12`
  - fallback garbage top-up removal shipped locally: deterministic fallback now fails fast instead of sparse/legacy top-up, repeated-phrase policy catches `보습 크림 보습`-style loops, and Bedrock supplementation prompt now carries diversification hints
  - local suite currently passes with `79 passed`
  - fresh dev smoke: Aesop PASS, Dr.Jart still `blocked_page`
  - Laneige still fails live with `generation_count_shortfall` (`naver_sa positive rows below 100`) despite local/fixture regressions passing, so the remaining blocker is live Laneige evidence composition rather than the already-fixed placeholder/product-term regressions
- `TASK-012` started:
- `TASK-012` completed:
  - two-stage redesign baseline is documented in [KEYWORD_INTERPRETATION_AND_RENDERING_REDESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_INTERPRETATION_AND_RENDERING_REDESIGN.md)
  - deterministic generation now builds typed facets (`audience`, `benefits`, `usage_context`, `ingredients`, `technology`, `specs`) and locks a single `canonical_category`
  - cosmetics fixture generation now drops adjacent-category drift (`보습 크림`, `장벽 크림`, `페이스 크림`) and weak comparison/price filler (`옵션 비교`, `라인 비교`, `가성비`, raw price)
  - Bedrock prompts now carry an `interpretation` payload plus `canonical_category`, comparison policy, and surface-cleanup hints
  - full local suite currently passes with `80 passed`
- Service design baseline exists in [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md)
- `TASK-004` completed:
  - API contract locked in Sections 2.1 and 2.2
  - Entity, lifecycle, failure-code, status payload, fixed-schema mapping, and cache model locked in Sections 3.1 through 3.4
- `TASK-011` completed:
  - Worker boundaries, queue handoffs, packaging assumptions, and idempotency boundaries locked in Sections 5.1 through 5.4
- `TASK-006` completed:
  - URL canonicalization, fetch profile sequence, charset normalization, snapshot contract, classifier contract, and local acceptance fixtures locked in Section 2.3
  - `NormalizedPageSnapshot` expanded in Section 3.1 so downstream evidence-builder work does not need to invent fields
- `TASK-007` completed:
  - Evidence tier semantics, fallback eligibility, same-product matching, promo admissibility examples, OCR ranking/admission, and `quality_warning` inputs locked in Section 4.1
- `TASK-008` completed:
  - `Intent Planner` contract, category allocation, positive-vs-negative quota split, dedup normalization, platform validator split, one repair-pass rule, and curated taxonomy ownership/runtime loading locked in Section 4.2
  - Category coverage policy now means `>=100` positive keywords per platform across the 9 positive categories plus a separate negative output; negative rows are not counted toward the positive floor
- `TASK-009` completed:
  - per-URL JSON payload, `both` flatten rule, combined JSON/CSV rule, failure manifest shape, job final-status aggregation, and notification payload locked in Section 4.3
  - runtime exporter helpers added under `src/exporting/`
- `TASK-010` completed:
  - successful-result-only cache semantics, version-bump invalidation, and cache-hit copy rules locked in Section 3.4.1
  - runtime sizing baseline, queue visibility defaults, and Bedrock concurrency posture locked in Section 5.5
  - queue retry ownership, DLQ policy, CloudWatch metrics/alarms, and minimum log correlation fields locked in Sections 6.1 through 6.4
- Local integration / E2E harness completed:
  - moto-backed runtime harness added under `src/runtime/`
  - queue-backed local lifecycle now covers submit, cache-hit copy, generation/failure terminalization, aggregation, summary artifacts, and one-notification semantics
  - regression coverage added in `tests/test_runtime_e2e.py`
  - local suite currently passes with `20 passed`
- Handler seam completed:
  - API handlers now live under `src/handlers/api.py`
  - worker handlers now live under `src/handlers/workers.py`
  - handler coverage added in `tests/test_handlers.py`
  - local suite currently passes with `22 passed`
- Collection / evidence / OCR seam completed:
  - fixture-backed collection/classification lives under `src/collection/`
  - real HTTP fetch abstraction now exists in `src/collection/service.py` via `HttpPageFetcher`, profile fallback, charset detection, and HTML-body preservation for HTTP error pages
  - evidence-pack assembly now derives normalized facts from snapshot signals plus admitted OCR blocks under `src/evidence/`
  - OCR policy now performs deterministic trigger selection, ranked image candidate selection, OCR block admission/rejection filtering, and admitted-block contribution accounting under `src/ocr/`
  - runtime pipeline now persists `normalized_snapshot`, `page_classification`, `ocr_result`, and `evidence_pack` artifacts before generation
  - regression coverage added in `tests/test_collection_pipeline.py`
  - local HTML fixture collector now parses captured service pages under `artifacts/service_test_pages/` and classifies commerce PDP, support/spec, blocked, listing, and promo-heavy landing cases in `tests/test_collection_html.py`
  - `HtmlCollectionPipeline` now resolves fetched HTML through classification, OCR policy, and evidence assembly without fixture JSON
  - `create_html_collection_runtime()` now wires `HttpPageFetcher` + `HtmlCollectionPipeline` into the local runtime seam
  - fetcher regression coverage added in `tests/test_collection_fetcher.py`
  - OCR/evidence regression coverage added in `tests/test_ocr_policy.py`
  - evidence-builder regression coverage added in `tests/test_evidence_builder.py`
  - local suite currently passes with `49 passed`
- Handler/runtime bootstrap is nearly production-ready:
  - handlers can now lazily create runtime instances via `src/handlers/runtime_factory.py`
  - env-based runtime loading lives in `src/runtime/service.py` via `load_runtime_resources_from_env()` and `create_html_collection_runtime_from_env()`
- Generation seam is now Bedrock-ready:
  - `src/keyword_generation/models.py` now preserves internal `CanonicalIntent` plus per-platform render metadata before fixed-schema row export
  - `src/keyword_generation/bedrock_adapter.py` now prefers canonical-intent JSON, still accepts legacy `rows[]`, and can be enabled via `KEYWORD_GENERATOR_GENERATION_MODE=bedrock`
  - `src/keyword_generation/service.py` now follows `intents -> platform render -> validate` so `both` mode reuses shared intent generation instead of treating final rows as the planner boundary
  - LLM 3-call pipeline is explicit: generate -> dedup/quality -> supplementation
  - official generation contract is `supplementation_pass_limit` / `supplementation_attempts`; `repair_*` is compatibility-only
  - deterministic generation remains the fallback path so local tests stay stable
  - Bedrock adapter regression coverage added in `tests/test_bedrock_adapter.py`
- Quality refactor completed:
  - deterministic generation now canonicalizes support/spec product names before rendering keyword intents
  - refined phrase-bank selection removes cross-category exact duplicates before export and uses a legacy quantity fallback only when sparse evidence would otherwise miss the floor
  - quality regression coverage added in `tests/test_generation_quality.py`
- Shared keyword quality hardening completed:
  - shared keyword policy now filters malformed exact rows, repeated phrases, placeholder-unit artifacts, and invalid negative rows before export/validation
  - deterministic and Bedrock paths now both pass through the same post-generation quality filter
  - curated taxonomy assets now live under `docs/taxonomy/` and drive negative/season/problem/comparison vocabulary selection by product type
  - evaluator now surfaces malformed-positive and invalid-negative diagnostics in addition to filler/naturalness/semantic-uniqueness metrics
- Quality evaluation split completed:
  - deployed-first evaluator core now lives under `src/quality_eval/`
  - deployed acceptance entrypoint is `scripts/evaluate_deployed_quality.py`
  - fixture regression entrypoint remains `tests/evaluate_quality.py` as reference-only
  - gate and scorecard are now separated; deployed gate uses semantic uniqueness while reference evaluation preserves exact-uniqueness regression checks
  - adapter coverage added in `tests/test_quality_eval_core.py` and `tests/test_quality_eval_deployed.py`
  - current evaluator baselines are PASS for `evidence_commerce_pdp_rich.json`, `evidence_support_spec.json`, and `evidence_borderline.json`
  - local suite currently passes with `69 passed`
- Cache/runtime follow-up completed:
  - cache component split is active in `src/runtime/service.py` via `naver_cache_key` / `google_cache_key`
  - Cache Validity Worker exists in `src/handlers/cache_validity_worker.py`
  - product-page LLM gate is active in `src/collection/service.py` and related models
  - Terraform now applies 30-day lifecycle expiry to `cache/` artifacts in `infra/terraform/main.tf`
- Current test status:
  - full local suite currently passes with `79 passed`
  - validated with `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -v --tb=short`
  - test fixtures now explicitly clear `AWS_PROFILE` / `AWS_DEFAULT_PROFILE` so moto-backed runtime tests stay isolated from local AWS profile config
- 2026-04-09 residual semantic hardcoding cleanup continued for deterministic rendering:
  - `_infer_category_value()` no longer guesses product categories from product-name tokens like `mask`, `cream`, `earbud`, or `laptop`; fallback category inference is now evidence-first
  - `_preferred_category_term()` no longer applies handcrafted boosts/penalties for preferred category heads or audience-like phrases
  - deterministic audience/use-case expansion is now formatting-only: raw `audience` and `use_case` facts are no longer auto-expanded into category-led surfaces like `<audience> <category>` or `<use_case> <category>`
  - `problem_noun_phrase` seeding stays concern-grounded; deterministic helpers no longer mix `audience` or `usage_context` into problem-slot seeds
  - audience/category uplift such as `건성 복합성 피부 마스크` is no longer generated by deterministic helpers; broad audience evidence is not auto-promoted into category phrases
- AWS resource-management baseline now exists:
 - 2026-04-09 follow-up semantic cleanup tightened deterministic generation further:
   - `_infer_category_value()` now falls back to the observed product name instead of token-to-category folklore
   - `_preferred_category_term()` no longer applies handcrafted boosts/penalties for favored category heads or audience-like phrases
   - `_audience_category_phrases()` no longer auto-promotes broad audience facts into category phrases
   - `_long_tail_phrases_refined()` no longer expands `audience` or `usage_context` into deterministic long-tail scaffolds
   - `_seasonal_context_phrases()` now requires grounded event terms instead of treating generic usage context as seasonal evidence
- AWS resource-management baseline now exists:
  - operator-facing inventory lives in `docs/AWS_RESOURCE_INVENTORY.md`
  - Terraform scaffold for S3, DynamoDB, SQS, and DLQs lives in `infra/terraform/`
  - env var mapping and apply order live in `infra/README.md`
- Core implementation choices already fixed:
  - Python 3.13
  - Crawl4AI
  - PaddleOCR
  - Bedrock Claude Sonnet 3.5
  - SQS, DynamoDB, S3, SES
- Service posture remains standalone AWS-native async processing
- Auth assumption remains Cognito plus existing InsightChat identity integration

## Codex Working Plan

1. Introduce `ProductInterpretation` as an internal generation boundary and split broad `attributes` into typed facets
2. Refactor deterministic phrase-bank generation to anchor on one `canonical_category` and stop adjacent-category drift
3. Move Bedrock prompts from raw fact lists toward typed interpretation inputs
4. Re-check `TASK-008` and related service-design sections only if implementation exposes a contract gap

`TASK-002` and `TASK-003` are treated as non-blocking readiness context unless the main project discovery materially changes.

## Confirmed Decisions

| Item | Decision |
| --- | --- |
| Runtime baseline | Python 3.13 on AWS Lambda AL2023 |
| LLM model | Bedrock Claude Sonnet 3.5 |
| Platform floor | `both` means Naver `>=100` positive plus Google `>=100` positive, validated independently |
| Negative keywords | Separate exclusion output per platform; **not** counted toward the positive `100` (OPEN_QUESTIONS RQ-02 정정 2026-04-06) |
| Service topology | Standalone service with its own SQS, DynamoDB, S3, and SES integrations |
| Cache TTL | **30 days** (기존 7일에서 변경, 2026-04-06) |
| Cache storage unit | Per platform component (`naver_sa`, `google_sa`); `both` stored as two components |
| Cache cross-mode reuse | `naver_sa` + `google_sa` components → satisfy `both`; `both` components → satisfy single-platform requests |
| Cache validity worker | Dedicated scheduled worker (daily) scans cached entries, HEAD-checks canonical URLs, deletes entries where URL is gone or content materially changed. Submit never performs live URL checks. |
| Keyword language | Korean + English mixed allowed; brand/model names keep original form; same concept in both languages = two distinct keyword rows |
| Page product gate | LLM must always answer "Is this a product sales page?" as mandatory first gate before class scoring; non-sales pages → `support_spec_page` or `non_product_page` immediately |
| Post-processing strategy | LLM-driven: (A) over-generate ~130, (B) LLM semantic dedup + quality eval, (C) LLM supplementation if gaps remain. Hard compliance rules (promo/price/stock/competitor) stay deterministic. Quality is v1 priority; cost optimization deferred. |

## Blockers

- None at the workspace-design level

## Next Decision Request

- Use [KEYWORD_INTERPRETATION_AND_RENDERING_REDESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_INTERPRETATION_AND_RENDERING_REDESIGN.md) as the baseline for the next generation-quality refactor, starting with cosmetics fixtures and `canonical_category` locking.
