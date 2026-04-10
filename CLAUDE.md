# Claude Supervisor Guide

## 紐⑹쟻

????μ냼?먯꽌 Claude??supervisor ??븷??留〓뒗?? Codex??援ы쁽 ?대떦?대떎.

## Source Of Truth

- ?먮Ц ?붽뎄?ы빆怨??몃? 李멸퀬 ?먮즺??`artifacts/`瑜?湲곗??쇰줈 蹂몃떎.
- `artifacts/`???섏젙?섏? ?딅뒗??
- ?먮Ц怨?理쒖떊 ?먮떒???ㅻⅤ硫?`docs/`??李⑥씠瑜?湲곕줉?쒕떎.

## Claude ??븷

- ?붽뎄?ы빆 ?댁꽍 異⑸룎 ?뺣━
- 踰붿쐞 ?듭젣? ?곗꽑?쒖쐞 寃곗젙
- stack/task 遺꾪빐 諛⑺뼢 ?쒖떆
- ?ㅺ퀎 ???鍮꾧탳? ?좏깮
- 援ы쁽 醫낅즺 ???곸쐞 由щ럭

## Claude媛 媛쒖엯?댁빞 ?섎뒗 寃쎌슦

- ?붽뎄?ы빆 ?댁꽍??媛덈┫ ??- 援ы쁽?덉씠 2媛??댁긽?쇰줈 媛덈┫ ??- API 寃쎄퀎, auth, security, storage, deployment 媛숈? ?곸쐞 寃곗젙????- 踰붿쐞 ?뺣? ?먮뒗 ??由ы뙥?곕쭅???꾩슂????- Codex媛 援ы쁽? ?앸깉吏留??쒗뭹/?ㅺ퀎 愿??理쒖쥌 ?뺤씤???꾩슂????
## Claude媛 源딄쾶 媛쒖엯?섏? ?딆븘???섎뒗 寃쎌슦

- 湲곗〈 ?⑦꽩??留욎텣 肄붾뱶 ?묒꽦
- ?뚯뒪??異붽?/?섏젙
- ?뚭퇋紐?踰꾧렇 ?섏젙
- 援?냼 由ы뙥?곕쭅
- 1李????由щ럭 諛섏쁺

## Codex ??븷

- 肄붾뱶踰좎씠???뺤씤
- ?ㅼ젣 援ы쁽
- ?뚯뒪?몄? ?붾쾭源?- 1李?肄붾뱶 由щ럭
- Claude?먭쾶 ?щ┫ ?먮떒 ?ъ씤???뺣━

## ?묒뾽 ?쒖옉 ?쒖꽌

1. `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md` ?뺤씤
2. `docs/OPERATING_MODEL.md` ?뺤씤
3. `docs/GSTACK_WORKFLOW.md` ?뺤씤
4. `docs/ACTIVE_HANDOFF.md`?먯꽌 ?꾩옱 紐⑺몴? 誘명빐寃?吏덈Ц ?뺤씤
5. ?꾩슂 ??`docs/OPEN_QUESTIONS.md`? `tasks/` ?뺤씤

## Claude?먭쾶 湲곕??섎뒗 異쒕젰 ?뺤떇

- ?대쾲 ?댁쓽 紐⑺몴
- ?대쾲 ??踰붿쐞 諛???ぉ
- Codex媛 援ы쁽???⑥쐞
- ?먮떒???꾩슂???댁뒋
- ?꾨즺 湲곗?

## README 理쒖떊??洹쒖튃

`README.md`??InsightChat ?곕룞 ?대떦?먯? ?좉퇋 ?⑸쪟?먭? 媛??癒쇱? ?쎈뒗 臾몄꽌?? ?꾨옒 ??ぉ??蹂寃쎈릺硫?諛섎뱶??README.md瑜??④퍡 ?낅뜲?댄듃?쒕떎.

- API ?붾뱶?ъ씤???먮뒗 ?붿껌/?묐떟 ?ㅽ궎留?蹂寃?- 異쒕젰 ?ㅽ궎留?`url`, `product_name`, `category`, `keyword`, `naver_match`, `google_match`, `reason`, `quality_warning`) 蹂寃?- Job ?곹깭 enum 異붽?쨌??젣쨌?대쫫 蹂寃?- ?몄쬆 諛⑹떇 蹂寃?- 湲곗닠 ?ㅽ깮 蹂寃?(?몄뼱 踰꾩쟾, 二쇱슂 ?쇱씠釉뚮윭由? ?명봽??
- ??μ냼 援ъ“ 蹂寃?(?붾젆?곕━ 異붽?쨌??젣)

## ?щ컻 諛⑹? 洹쒖튃

?몄뀡 ?쒖옉 ???꾨옒 ?쇰뱶諛?洹쒖튃??諛섎뱶???뺤씤?쒕떎. 怨쇨굅???ㅼ젣濡?諛쒖깮???ㅼ닔瑜?湲곕컲?쇰줈 ?묒꽦??

1. **FR ?뺣룆 ???ㅺ퀎 寃곗젙 湲덉?**: `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md`瑜??뺣룆?섍린 ?꾩뿉 紐⑤뜽쨌?쇱씠釉뚮윭由?룹뒪肄뷀봽瑜??ㅺ퀎 臾몄꽌???ы븿?섏? ?딅뒗??
2. **?ъ슜?먭? 紐낆떆??寃껊쭔 ?뺤젙 泥섎━**: 異붾줎?대굹 湲곕낯媛믪? "?뺤젙(??" 泥섎━ 湲덉?. ?ъ슜?먭? 吏곸젒 留먰븳 寃껊쭔 ?뺤젙.
3. **踰꾩쟾 吏????wheel ?뺤씤 ?꾩닔**: Python 踰꾩쟾?대굹 ?듭떖 ?쇱씠釉뚮윭由?踰꾩쟾???뺥븷 ??PyPI wheel 吏???꾪솴怨?LTS 湲곌컙???뺤씤?섍퀬 洹쇨굅? ?④퍡 湲곕줉?쒕떎.

?곸꽭 ?댁슜: `C:\Users\NHN\.claude\projects\c--Users-NHN-Repo-Keyword-Generator\memory\` ??feedback_*.md ?뚯씪 李몄“.

## 李멸퀬 臾몄꽌

- `docs/OPERATING_MODEL.md`
- `docs/GSTACK_WORKFLOW.md`
- `docs/OPEN_QUESTIONS.md`
- `docs/ACTIVE_HANDOFF.md`
- `tasks/README.md`

## Added Recurrence Rules (2026-04-08)

1. **Reject hardcoded semantic shortcuts during review**: if Codex introduces broad fixed-word mappings for facts like `benefit`, `problem_solution`, `use_case`, `usage`, or `audience`, stop and require a grounded alternative.
2. **Quality beats count floor**: do not approve filler, forced purchase scaffolds, self-comparison rows, or domain-agnostic boosts just to satisfy category or count quotas.
3. **Encoding failures must block progress**: any UTF-8 corruption, mojibake, or syntax/import break after edits must be treated as a release blocker, and the session should not proceed to deploy until syntax/import checks pass.
4. **Recurrence prevention must be written down immediately**: when a defect reveals a missing operating rule, update supervisor/operator guidance in the same task rather than leaving it in chat history only.
5. **Require regression coverage for extraction-policy changes**: if a fix changes evidence promotion rules, require a focused regression test before approving deploy.
6. **Do not accept silent Bedrock fallback**: if deploy intent is to validate the LLM path, `bedrock` mode must fail explicitly on Bedrock errors rather than silently using deterministic generation.
7. **Review slot-completion changes at slot granularity**: when generation moves to `slot_plan`, require `slot_type`-level gaps/debug (`gap_slots`, `slot_gap_report`, `slot_drop_report`) instead of approving category-only completion that obscures which noun-phrase shapes are still missing.
8. **Hold the line on category-hard / slot-soft semantics**: review Bedrock completion changes against category presence first. Do not approve logic that forces every active slot to emit at least one keyword when that would manufacture weak surfaces.
9. **Require reasoned slot-drop artifacts**: `slot_drop_report` should preserve `drop_stage`, `drop_reason_code`, and `drop_reason_detail` with `category` and `slot_type`; a plain list of removed rows is not enough for live debugging.
10. **Keep real Bedrock verification explicit**: default tests stay deterministic; real Bedrock parity should be validated in a dedicated `live_bedrock` suite gated by env and skipped when the environment is unavailable.
11. **Do not approve promo-first classifier regressions**: strong PDP signals such as product schema, product-level meta, product URLs, and credible buy/price evidence must outrank promo-heavy landing heuristics.
12. **Treat blocked/waiting page classes as status signals, not semantic judgments**: Bedrock product gate should not rewrite explicit `blocked_page`, `waiting_page`, or support-page results into `non_product_page`.
13. **Require live generation smoke to bypass moto when Bedrock is the subject**: `moto` is acceptable for runtime storage/queue seams, but real URL keyword-generation verification should use direct fetch/classify/evidence/generate calls so Bedrock transport failures are not masked by the local harness.
14. **Prefer minimal intermediate Bedrock contracts**: when the final API/export schema can be reconstructed deterministically, review Bedrock Step A prompts against the smallest viable payload first. Do not approve verbose first-pass JSON contracts that spend output tokens on fields the runtime can fill later.
15. **Review under-generation fixes as adaptive batching decisions, not only token-budget decisions**: when one Bedrock pass stays sparse, prefer cluster-first generation with split-later escalation for weak clusters before approving permanent per-category fanout or large prompt bloat.
16. **Require parse-failure observability in Bedrock reviews**: if live Bedrock output fails contract parsing, the failure artifact must retain raw `response_text`, model metadata, and the failed batch/stage context. Do not approve parser changes that turn live contract drift into opaque `ValueError` failures.
17. **Treat lightweight wrapper drift as tolerance work before prompt work**: if live Bedrock returns semantically correct keyword payloads under `keywords[]` or similar lightweight wrappers, require parser tolerance before approving prompt-tightening as the primary fix.
18. **Reject literal blacklist churn for category cleanup**: when noisy rows appear in `feature_attribute`, `season_event`, `problem_solution`, or `competitor_comparison`, require evidence-gating and shape admissibility tightening rather than approving one-off bad-string blocklists.
19. **Reject handcrafted concern rewrites in deterministic generation**: if Codex maps raw concern evidence to preferred keyword phrases through case-by-case dictionaries, send it back. Formatting cleanup is acceptable; semantic rewriting by concern label is not.
20. **Require semantic hardcoding cleanup to delete the old path, not just bypass it**: when a deterministic uplift helper or alias table is no longer acceptable, ask Codex to remove the helper and update tests/docs rather than leaving dead boost code in place.
21. **Keep audience/use-case normalization formatting-only during review**: preserving whitespace-normalized observed phrasing is acceptable, but deterministic generation should not expand raw `audience` or `use_case` facts into category-led scaffolds like `<audience> <category>` or `<use_case> <category>`.
22. **Require problem-slot seeds to remain concern-grounded**: if deterministic logic mixes `audience` or `usage_context` values into `problem_noun_phrase` seeds, send it back. Problem-slot expansion must start from explicit concern/problem evidence.
21. **Reject product-name token folklore as category inference**: if deterministic generation infers canonical product categories from ad hoc token maps like `mask -> ?ㅽ궓耳?? or `earbud -> 臾댁꽑 ?댁뼱??, require an evidence-first fallback instead.
22. **Reject audience-to-category auto-promotion in deterministic helpers**: broad audience evidence such as `嫄댁꽦 蹂듯빀???쇰?` should not be deterministically turned into category phrases like `嫄댁꽦 蹂듯빀???쇰? 留덉뒪?? unless the exact phrase is grounded on the page.
28. **Do not expand weak preservation or convenience copy into situational queries**: evidence such as `냉동 보관`, storage guidance, or convenience phrasing must not be turned into `나들이`, `캠핑`, `피크닉`, `여행`, or similar situational/seasonal keywords unless those exact situations are explicitly grounded on the page.
29. **Public OCR benchmark adapters must inspect dataset GT schema before assuming same-stem labels**: some product OCR datasets ship manifest-level annotations instead of one label file per image. `Unitail-OCR` gallery uses COCO-style `ocr_gt.json`; benchmark code must group `annotations[*].text-words` by `image_id` into per-image reference text before scoring.
29. **Run local OCR benchmarks through the real Windows-safe paddle path and record speed mode**: when reviewing or asking Codex to benchmark OCR locally on Windows, require the base interpreter from `.venv-paddleocr/pyvenv.cfg`, `PYTHONPATH` prepended with `.venv-paddleocr/Lib/site-packages`, and `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1`. Prefer one-sample benchmark runs via `scripts/evaluate_ocr_benchmark.py --product-label ...`, and if `--product-max-side` is used to speed up very tall banners, make sure the resized dimensions are recorded with the result instead of being treated as the default quality baseline.
30. **Do not pay every OCR multipass cost once a strong pass exists**: multi-pass OCR is acceptable for recovery, but the runner should stop after the first pass that already yields strong text volume/coverage for the current candidate type. Do not insist on running contrast/upscale fallbacks on large images when the original pass is already good enough.
31. **Public OCR benchmark roots must exclude local preprocessing artifacts**: when benchmarking cloned or extracted public datasets, ignore locally generated files such as `*_enhance_contrast`, `*_upscale_x2`, tiles, or similar derivative images. Benchmark rows must come from source dataset assets only.
32. **Do not require page-title token overlap for same-page OCR label/spec fields**: on ranked same-page detail images, explicit product field labels such as `제품명`, `품질표시사항`, `재질`, `제조국`, `가격`, `ingredient(s)`, or `material` are valid deterministic same-product signals. Do not reject these blocks solely because they omit the page-title tokens verbatim.
33. **Recompute trusted OCR eligibility at the merged line-group level**: when short same-page label/spec blocks are grouped, evaluate the merged text quality and direct-candidate eligibility from the combined line-group text. Do not inherit only the strongest child block score if that would hide an informative grouped field cluster.

