# Active Handoff

## Purpose

Keep the current goal, locked decisions, and immediate next work visible between Claude and Codex sessions.

## Operating Rules

- This file is a current-state summary only.
- Keep background short and decision-oriented.
- Move unresolved questions to `docs/OPEN_QUESTIONS.md`.
- When a task completes, record the durable output location and promote the next task.

## Current Goal

- Replace the fixture resolver inside `src/runtime/` with real collection / OCR / evidence-builder work
- Keep the handler layer and local E2E contract fixed unless implementation exposes a real gap

## Current Status

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
  - full local suite currently passes with `59 passed`
  - validated with `$env:PYTHONPATH='src'; .\.venv-dev\Scripts\python.exe -m pytest tests -v --tb=short`
  - test fixtures now explicitly clear `AWS_PROFILE` / `AWS_DEFAULT_PROFILE` so moto-backed runtime tests stay isolated from local AWS profile config
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

1. Replace the deterministic fallback generator with real Bedrock output in runtime environments where `KEYWORD_GENERATOR_GENERATION_MODE=bedrock`
2. Wire actual AWS Lambda entrypoints to env-backed runtime bootstrap and real queue/resources
3. Add the last missing runtime smoke checks around AWS resource/env configuration and real Bedrock access
4. Re-check `TASK-004`, `TASK-006`, `TASK-007`, `TASK-008`, `TASK-009`, and `TASK-010` only if implementation exposes a contract gap

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

- Keep `src/runtime/` and `src/handlers/` aligned with URL-level isolation, `COMPLETED_CACHED` handling, and one-notification semantics while real collection/OCR work replaces the fixture-backed seams.
