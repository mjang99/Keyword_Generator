# Codex Agent Guide

## ??븷

Codex??援ы쁽 ?대떦?대떎. Claude??supervisor ??븷濡??ㅺ퀎 寃곗젙怨?由щ럭瑜??대떦?쒕떎.

## Source Of Truth

- `artifacts/`: ?섏젙 湲덉?. ?먮Ц ?붽뎄?ы빆 湲곗?.
- `docs/`: ?ㅺ퀎쨌?댁꽍 怨꾩링. 援ы쁽 ??諛섎뱶???뺤씤.
- `tasks/`: ?묒뾽 ?⑥쐞. TASK-xxx 湲곗??쇰줈 踰붿쐞 ?듭젣.

## ?묒뾽 ?쒖옉 ?쒖꽌

1. `docs/ACTIVE_HANDOFF.md` ???꾩옱 紐⑺몴? blocker ?뺤씤
2. ?대떦 `tasks/TASK-xxx.md` ???ㅼ퐫?꾩? ?꾨즺 湲곗? ?뺤씤
3. `docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md` ???ㅺ퀎 ?듭빱 ?뺤씤
4. ?꾩슂 ??`docs/OPEN_QUESTIONS.md` ??誘명솗????ぉ ?뺤씤

## README 理쒖떊??洹쒖튃

`README.md`??InsightChat ?곕룞 ?대떦?먯? ?좉퇋 ?⑸쪟?먭? 媛??癒쇱? ?쎈뒗 臾몄꽌?? 援ы쁽 以??꾨옒 ??ぉ??諛붾뚮㈃ Claude?먭쾶 蹂닿퀬?섍퀬 README.md瑜??④퍡 ?낅뜲?댄듃?쒕떎.

- API ?붾뱶?ъ씤???먮뒗 ?붿껌/?묐떟 ?ㅽ궎留?蹂寃?- 異쒕젰 ?ㅽ궎留?而щ읆 蹂寃?(怨좎젙 ?ㅽ궎留덉씠誘濡?蹂寃???Claude ?뱀씤 ?꾩슂)
- Job ?곹깭 enum 異붽?쨌??젣쨌?대쫫 蹂寃?- ?몄쬆 諛⑹떇 蹂寃?- 湲곗닠 ?ㅽ깮 蹂寃?(?몄뼱 踰꾩쟾, 二쇱슂 ?쇱씠釉뚮윭由? ?명봽??
- ??μ냼 援ъ“ 蹂寃?(?붾젆?곕━ 異붽?쨌??젣)

## ?щ컻 諛⑹? 洹쒖튃

援ы쁽 以?諛쒖깮???ㅼ닔? 寃곗젙 ?ы빆? 紐⑤몢 湲곕줉?섏뼱 ?덈떎. ?꾨옒 洹쒖튃??諛섎뱶???곕Ⅸ??

1. **FR ?뺣룆 ??寃곗젙 湲덉?**: `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md` ?뺣룆 ??紐⑤뜽쨌?쇱씠釉뚮윭由?룸쾭?꾩쓣 肄붾뱶??臾몄꽌???곗? ?딅뒗??
2. **?뺤젙?섏? ?딆? ??ぉ? 援ы쁽?섏? ?딅뒗??*: `docs/OPEN_QUESTIONS.md`?먯꽌 "誘몄젙"????ぉ? Claude?먭쾶 癒쇱? ?뺤씤?쒕떎.
3. **踰꾩쟾 寃곗젙? 洹쇨굅 ?꾩닔**: ?쇱씠釉뚮윭由?踰꾩쟾???좏깮????PyPI wheel 吏???꾪솴???뺤씤?섍퀬 洹쇨굅瑜?二쇱꽍?대굹 臾몄꽌???④릿??
4. **?ㅼ퐫???뺤옣 湲덉?**: task ?뚯씪??Scope? Done When??踰쀬뼱?섎뒗 ?묒뾽? Claude?먭쾶 癒쇱? ?щ┛??

## Claude?먭쾶 ?щ젮???섎뒗 寃쎌슦

- ?붽뎄?ы빆 ?댁꽍??2媛吏 ?댁긽?쇰줈 媛덈┫ ??- ?ㅺ퀎 臾몄꽌??紐낆떆?섏? ?딆? 寃곗젙???꾩슂????- API 寃쎄퀎, auth, storage, deployment 愿??寃곗젙
- 踰붿쐞 ?뺣?????由ы뙥?곕쭅???꾩슂????- 援ы쁽 ?꾨즺 ???ㅺ퀎 愿??理쒖쥌 ?뺤씤???꾩슂????
## 湲곗닠 ?ㅽ깮 (?뺤젙)

| ??ぉ | 寃곗젙 |
| --- | --- |
| ?몄뼱 | Python 3.13 |
| ?ㅽ겕?섑븨 | Crawl4AI + Playwright |
| OCR | PaddleOCR PP-OCRv5 |
| LLM | AWS Bedrock Claude Sonnet 3.5 (FR-14, ?⑥씪 紐⑤뜽) |
| ?명봽??| AWS Lambda Arm64, SQS, DynamoDB, S3, SES |
| ?몄쬆 | Cognito + Naver/Google OAuth |
| Bedrock ?몄텧 | max_tokens 諛섎뱶??紐낆떆 (誘몄꽕????64,000 ?덉빟) |
| Bedrock ?붾뱶?ъ씤??| Geo cross-region ?꾩닔 (On-demand 50 RPM 遺議? |

## 異쒕젰 ?ㅽ궎留?(怨좎젙, ?섏젙 湲덉?)

```text
url, product_name, category, keyword, naver_match, google_match, reason, quality_warning
```

## ?꾨즺 蹂닿퀬 ?뺤떇

- ?꾨즺??task ?뚯씪??`status`瑜?`done`?쇰줈 蹂寃?- `docs/ACTIVE_HANDOFF.md` Current Status ?낅뜲?댄듃
- Claude 由щ럭媛 ?꾩슂???먮떒 ?ъ씤???뺣━ ???꾨떖

## Added Recurrence Rules (2026-04-08)

1. **No domain-agnostic hardcoded semantic boosts**: do not add or keep fixed keyword maps that promote `benefit`, `problem_solution`, `use_case`, `usage`, `audience`, or similar facts from broad tokens like `蹂댁뒿`, `嫄댁“`, `?λ꼍`, `?쇨컙`, `?섎㈃`. Semantic uplift must be grounded in structure, explicit phrases, or page-class/domain-specific evidence.
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
23. **Do not remap concern semantics through handcrafted phrase dictionaries**: deterministic generation may normalize formatting or strip generic context, but it must not translate concern evidence into preferred phrases through case-by-case mappings such as `?밴? -> ?쇰? ?밴?` or `?λ꼍 -> ?λ꼍 耳??.
24. **Do not keep dead semantic-boost helpers around**: if a broad uplift helper or category-alias map is no longer allowed, remove the helper and its tests rather than leaving it dormant in the file for later reuse.
25. **Audience/use-case normalization is formatting-only**: deterministic generation may trim whitespace or preserve observed phrasing, but it must not expand raw `audience` or `use_case` facts into `<audience> <category>`, `<use_case> <category>`, or similar category-led scaffolds.
26. **Problem-slot seeds must stay concern-grounded**: do not mix `audience` or `usage_context` values into deterministic `problem_noun_phrase` seeds. Problem-slot expansion must start from explicit concern/problem evidence.
25. **Do not split or embellish explicit audience/concern facts in deterministic generation**: keep observed audience and concern phrases intact. Do not expand `嫄댁꽦 蹂듯빀???쇰?` into separate audience rows, do not strip temporal clauses like `?섎㈃ 以?, and do not append handcrafted suffixes like `耳?? just to make the surface sound more search-like.
26. **Do not infer canonical category from product-name token lore**: deterministic generation must not guess category labels from ad hoc product-name token maps such as `mask -> ?ㅽ궓耳?? or `earbud -> 臾댁꽑 ?댁뼱??. Prefer explicit category evidence and generic evidence-ordering heuristics over handcrafted token-to-category rewrites.
27. **Do not auto-promote broad audience evidence into category phrases**: broad audience values like `嫄댁꽦 蹂듯빀???쇰?` may remain as observed evidence, but deterministic helpers must not synthesize category-appended surfaces such as `嫄댁꽦 蹂듯빀???쇰? 留덉뒪?? unless the page explicitly contains that phrase.
28. **Do not expand weak preservation or convenience copy into situational queries**: evidence such as `냉동 보관`, storage guidance, or convenience phrasing must not be turned into `나들이`, `캠핑`, `피크닉`, `여행`, or similar situational/seasonal keywords unless those exact situations are explicitly grounded on the page.
29. **Public OCR benchmark adapters must inspect dataset GT schema before assuming same-stem labels**: some product OCR datasets ship manifest-level annotations instead of one label file per image. `Unitail-OCR` gallery uses COCO-style `ocr_gt.json`; benchmark code must group `annotations[*].text-words` by `image_id` into per-image reference text before scoring.
29. **Local OCR benchmarks must use the Windows-safe real engine path and explicit speed mode**: on Windows, run OCR benchmarks through the base interpreter from `.venv-paddleocr/pyvenv.cfg`, prepend `.venv-paddleocr/Lib/site-packages` to `PYTHONPATH`, keep `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1`, and benchmark one product sample at a time with `scripts/evaluate_ocr_benchmark.py --product-label ...`. If a very tall detail banner is slowing iteration, use `--product-max-side` as an explicit speed-vs-coverage tradeoff and record the resized dimensions with the result.
30. **Do not pay every OCR multipass cost once a strong pass exists**: multi-pass OCR is allowed for quality recovery, but runner logic must stop after the first pass that already yields strong text volume/coverage for the candidate type. Do not force every contrast/upscale fallback on large images if the original pass is already good enough.
31. **Public OCR benchmark roots must exclude local preprocessing artifacts**: when benchmarking cloned or extracted public datasets, ignore locally generated files such as `*_enhance_contrast`, `*_upscale_x2`, tiles, or similar derivative images. Benchmark rows must come from source dataset assets only.
32. **Do not require page-title token overlap for same-page OCR label/spec fields**: on ranked same-page detail images, explicit product field labels such as `제품명`, `품질표시사항`, `재질`, `제조국`, `가격`, `ingredient(s)`, or `material` are valid deterministic same-product signals. Do not reject these blocks solely because they omit the page-title tokens verbatim.
33. **Recompute trusted OCR eligibility at the merged line-group level**: when short same-page label/spec blocks are grouped, evaluate the merged text quality and direct-candidate eligibility from the combined line-group text. Do not inherit only the strongest child block score if that would hide an informative grouped field cluster.
34. **Windows OCR subprocesses must not rely on console-default decoding**: when OCR helpers spawn Python subprocesses on Windows, capture stdout/stderr as bytes, set `PYTHONIOENCODING=utf-8`, and decode explicitly with a safe fallback. Do not depend on `cp949`/console defaults for JSON payloads from OCR workers.
35. **Image-level OCR subprocess timeouts must degrade to error payloads, not crash the sweep**: quality-first OCR may spend a long time on hard detail assets, but a single timed-out image must be recorded as a failed OCR result and the broader benchmark/runtime pass must continue.

