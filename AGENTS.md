# Codex Agent Guide

## 역할

Codex는 구현 담당이다. Claude는 supervisor 역할로 설계 결정과 리뷰를 담당한다.

## Source Of Truth

- `artifacts/`: 수정 금지. 원문 요구사항 기준.
- `docs/`: 설계·해석 계층. 구현 전 반드시 확인.
- `tasks/`: 작업 단위. TASK-xxx 기준으로 범위 통제.

## 작업 시작 순서

1. `docs/ACTIVE_HANDOFF.md` — 현재 목표와 blocker 확인
2. 해당 `tasks/TASK-xxx.md` — 스코프와 완료 기준 확인
3. `docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md` — 설계 앵커 확인
4. 필요 시 `docs/OPEN_QUESTIONS.md` — 미확정 항목 확인

## README 최신화 규칙

`README.md`는 InsightChat 연동 담당자와 신규 합류자가 가장 먼저 읽는 문서다. 구현 중 아래 항목이 바뀌면 Claude에게 보고하고 README.md를 함께 업데이트한다.

- API 엔드포인트 또는 요청/응답 스키마 변경
- 출력 스키마 컬럼 변경 (고정 스키마이므로 변경 시 Claude 승인 필요)
- Job 상태 enum 추가·삭제·이름 변경
- 인증 방식 변경
- 기술 스택 변경 (언어 버전, 주요 라이브러리, 인프라)
- 저장소 구조 변경 (디렉터리 추가·삭제)

## 재발 방지 규칙

구현 중 발생한 실수와 결정 사항은 모두 기록되어 있다. 아래 규칙을 반드시 따른다.

1. **FR 정독 전 결정 금지**: `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md` 정독 전 모델·라이브러리·버전을 코드나 문서에 쓰지 않는다.
2. **확정되지 않은 항목은 구현하지 않는다**: `docs/OPEN_QUESTIONS.md`에서 "미정"인 항목은 Claude에게 먼저 확인한다.
3. **버전 결정은 근거 필수**: 라이브러리 버전을 선택할 때 PyPI wheel 지원 현황을 확인하고 근거를 주석이나 문서에 남긴다.
4. **스코프 확장 금지**: task 파일의 Scope와 Done When을 벗어나는 작업은 Claude에게 먼저 올린다.

## Claude에게 올려야 하는 경우

- 요구사항 해석이 2가지 이상으로 갈릴 때
- 설계 문서에 명시되지 않은 결정이 필요할 때
- API 경계, auth, storage, deployment 관련 결정
- 범위 확대나 큰 리팩터링이 필요할 때
- 구현 완료 후 설계 관점 최종 확인이 필요할 때

## 기술 스택 (확정)

| 항목 | 결정 |
| --- | --- |
| 언어 | Python 3.13 |
| 스크래핑 | Crawl4AI + Playwright |
| OCR | PaddleOCR PP-OCRv5 |
| LLM | AWS Bedrock Claude Sonnet 3.5 (FR-14, 단일 모델) |
| 인프라 | AWS Lambda Arm64, SQS, DynamoDB, S3, SES |
| 인증 | Cognito + Naver/Google OAuth |
| Bedrock 호출 | max_tokens 반드시 명시 (미설정 시 64,000 예약) |
| Bedrock 엔드포인트 | Geo cross-region 필수 (On-demand 50 RPM 부족) |

## 출력 스키마 (고정, 수정 금지)

```text
url, product_name, category, keyword, naver_match, google_match, reason, quality_warning
```

## 완료 보고 형식

- 완료된 task 파일의 `status`를 `done`으로 변경
- `docs/ACTIVE_HANDOFF.md` Current Status 업데이트
- Claude 리뷰가 필요한 판단 포인트 정리 후 전달

## Added Recurrence Rules (2026-04-08)

1. **No domain-agnostic hardcoded semantic boosts**: do not add or keep fixed keyword maps that promote `benefit`, `problem_solution`, `use_case`, `usage`, `audience`, or similar facts from broad tokens like `보습`, `건조`, `장벽`, `야간`, `수면`. Semantic uplift must be grounded in structure, explicit phrases, or page-class/domain-specific evidence.
2. **Do not trade quality for floor**: when the only way to reach count floor is filler, generic scaffolds, self-comparison, or hardcoded boosts, keep the shortfall and fail generation instead.
3. **UTF-8 write safety is mandatory**: when editing Python, Markdown, JSON, YAML, or test fixtures, save as UTF-8 and immediately run a syntax/import check (`py_compile` or pytest collection) before moving on.
4. **When a bug is found, codify the prevention in the same task**: update `ACTIVE_HANDOFF.md` and the relevant operator guide (`AGENTS.md` and/or `CLAUDE.md`) in the same change, not later.
5. **If a fix changes extraction semantics, add a regression test**: every removal of leakage, hardcoded boosts, or malformed rendering must ship with a focused regression test that reproduces the failure mode.
6. **Bedrock mode must not silently fall back**: when `KEYWORD_GENERATOR_GENERATION_MODE=bedrock`, do not route generation errors into deterministic output. Fail explicitly so live validation reflects the real LLM path.
7. **OCR verification requires an engine smoke, not policy tests alone**: do not claim OCR is verified from `tests/test_ocr_policy.py` or admitted-block fixtures only. Run `scripts/verify_collection_ocr.py` with an OCR image smoke and, if the PaddleOCR subprocess/runtime fails, record OCR as an environment blocker rather than a pass.
8. **Windows OCR smoke must disable the fast CPU path**: when using `.venv-paddleocr` on Windows for local OCR verification, run through the base interpreter from `.venv-paddleocr/pyvenv.cfg`, prepend `.venv-paddleocr/Lib/site-packages` to `PYTHONPATH`, and force `device='cpu'`, `enable_mkldnn=False`, `enable_cinn=False`, `enable_hpi=False` until the upstream runtime issue is resolved.
9. **Do not judge OCR quality before collecting lazy detail assets**: if a commerce page uses hidden product-detail banners via `ec-data-src`, `data-src`, or similar lazy attributes, collect and rank those assets before concluding that OCR quality is poor. Hero shots and package photos are not representative OCR targets.
10. **Do not expand generic usage context into deterministic long-tail or seasonal scaffolds**: raw `use_case` / `usage_context` evidence like bedtime or application-order phrases must not be auto-converted into `<usage> <category>` or season/event keywords unless there is separate grounded event evidence.
10. **Keep Bedrock Step A payload minimal**: Bedrock generation should emit only the smallest intermediate fields needed to survive downstream hydration. Do not require final export metadata such as full renders, match labels, or per-row reasons in the first generation call when code can deterministically add them later.
10. **Reject decorative runtime assets before live OCR sweeps**: `.svg` UI assets, `echosting.cafe24.com` button GIFs, `/web/upload/images/` promo chrome, tiny one-dimension icons, and templated JS URLs such as `product/'+stickImgSrc+'` are not OCR candidates. Filter them out before evaluating live OCR quality or timeout behavior.
11. **Do not drop short OCR lines before downstream relevance filtering**: on detail/spec images, single-line OCR outputs like ingredient names, spec labels, and short product phrases are expected. Do not require long paragraphs or 2+ product-token matches before admission; preserve meaningful short image lines and let downstream evidence filtering decide relevance.
10. **Slot-based generation must stay slot-scoped**: when Bedrock generation uses `slot_plan`, supplementation and debug artifacts must target `gap_slots` / `slot_gap_report` / `slot_drop_report` with explicit `slot_type`; do not regress to broad category-only filler that hides which noun-phrase shape is missing.
11. **Do not aggressively trim OCR candidates before quality review**: preserve broad-sweep OCR semantics until evidence/extractor stages reject irrelevant text. Ranking may guide execution order, but it must not silently collapse detail-banner coverage back to tiny top-k behavior.
12. **Table/grid images require structured OCR before failure calls**: do not judge table-like assets from plain OCR alone. When candidate signals suggest comparison/spec/shade tables, run or inspect the structured OCR branch before concluding that OCR quality is poor.
13. **Category completion is hard, slot diversity is soft**: for Bedrock `slot_plan`, require category presence first and treat non-primary slot coverage as preference/debug only. Do not force every active slot to emit at least one keyword when that would create filler.
14. **slot_drop_report must explain the drop**: when rows are removed after dedup/policy/surface cleanup, persist `drop_stage`, `drop_reason_code`, and `drop_reason_detail` with `category` and `slot_type`; raw dropped-row lists alone are insufficient for debugging.
15. **Real Bedrock parity lives in a dedicated test suite**: keep default regression tests deterministic/mock-based. Use a separate `live_bedrock` pytest suite, gated by explicit env, for classifier/fact-lift/generation calls against real Bedrock.
16. **Do not let promo heuristics override strong PDP evidence**: if a page has product-level metadata/schema, product-shaped URLs, or credible sellability signals, keep it in supported commerce classes unless blocker/waiting/support rules clearly win.
17. **Do not use Bedrock gate to relabel blocked or waiting pages as non-product**: explicit `blocked_page`, `waiting_page`, and support-page classifications are environment/status signals and should bypass the Bedrock product gate.
18. **Real external Bedrock generation smoke must bypass moto**: use `moto` for storage/queue seams only. When verifying actual keyword generation against live URLs, call fetch/classify/evidence/generate directly so `Converse` is exercised against the real Bedrock endpoint.
19. **Prefer cluster-first adaptive Bedrock fanout over fixed per-category calls**: when one Step A call under-generates, split generation by category clusters first and only split weak clusters further. Do not jump straight to permanent per-category fanout when a smaller adaptive batching strategy can preserve cost and diversity.
20. **Do not lose raw Bedrock responses on parse failure**: if a generation, dedup, or supplementation response cannot be parsed, preserve the raw `response_text`, model metadata, and batch context in `debug_payload` so live failures can be diagnosed from artifacts without reproducing the exact call again.
21. **Treat lightweight Bedrock wrapper drift as a parser concern first**: when live Bedrock returns the same keyword payload under `keywords[]` or another lightweight wrapper, widen the parser before tightening prompts. Do not leave recoverable wrapper drift as a hard runtime failure.
22. **Tighten category quality with evidence/shape rules, not literal blacklist churn**: when a category emits noisy rows, strengthen admissibility around grounded evidence sources and allowed shapes. Do not paper over the problem by hardcoding individual bad strings one by one.
23. **Do not remap concern semantics through handcrafted phrase dictionaries**: deterministic generation may normalize formatting or strip generic context, but it must not translate concern evidence into preferred phrases through case-by-case mappings such as `당김 -> 피부 당김` or `장벽 -> 장벽 케어`.
24. **Do not keep dead semantic-boost helpers around**: if a broad uplift helper or category-alias map is no longer allowed, remove the helper and its tests rather than leaving it dormant in the file for later reuse.
25. **Audience/use-case normalization is formatting-only**: deterministic generation may trim whitespace or preserve observed phrasing, but it must not expand raw `audience` or `use_case` facts into `<audience> <category>`, `<use_case> <category>`, or similar category-led scaffolds.
26. **Problem-slot seeds must stay concern-grounded**: do not mix `audience` or `usage_context` values into deterministic `problem_noun_phrase` seeds. Problem-slot expansion must start from explicit concern/problem evidence.
25. **Do not split or embellish explicit audience/concern facts in deterministic generation**: keep observed audience and concern phrases intact. Do not expand `건성 복합성 피부` into separate audience rows, do not strip temporal clauses like `수면 중`, and do not append handcrafted suffixes like `케어` just to make the surface sound more search-like.
26. **Do not infer canonical category from product-name token lore**: deterministic generation must not guess category labels from ad hoc product-name token maps such as `mask -> 스킨케어` or `earbud -> 무선 이어폰`. Prefer explicit category evidence and generic evidence-ordering heuristics over handcrafted token-to-category rewrites.
27. **Do not auto-promote broad audience evidence into category phrases**: broad audience values like `건성 복합성 피부` may remain as observed evidence, but deterministic helpers must not synthesize category-appended surfaces such as `건성 복합성 피부 마스크` unless the page explicitly contains that phrase.
