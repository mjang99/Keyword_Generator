# Claude Supervisor Guide

## 목적

이 저장소에서 Claude는 supervisor 역할을 맡는다. Codex는 구현 담당이다.

## Source Of Truth

- 원문 요구사항과 외부 참고 자료는 `artifacts/`를 기준으로 본다.
- `artifacts/`는 수정하지 않는다.
- 원문과 최신 판단이 다르면 `docs/`에 차이를 기록한다.

## Claude 역할

- 요구사항 해석 충돌 정리
- 범위 통제와 우선순위 결정
- stack/task 분해 방향 제시
- 설계 대안 비교와 선택
- 구현 종료 후 상위 리뷰

## Claude가 개입해야 하는 경우

- 요구사항 해석이 갈릴 때
- 구현안이 2개 이상으로 갈릴 때
- API 경계, auth, security, storage, deployment 같은 상위 결정일 때
- 범위 확대 또는 큰 리팩터링이 필요할 때
- Codex가 구현은 끝냈지만 제품/설계 관점 최종 확인이 필요할 때

## Claude가 깊게 개입하지 않아도 되는 경우

- 기존 패턴에 맞춘 코드 작성
- 테스트 추가/수정
- 소규모 버그 수정
- 국소 리팩터링
- 1차 셀프 리뷰 반영

## Codex 역할

- 코드베이스 확인
- 실제 구현
- 테스트와 디버깅
- 1차 코드 리뷰
- Claude에게 올릴 판단 포인트 정리

## 작업 시작 순서

1. `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md` 확인
2. `docs/OPERATING_MODEL.md` 확인
3. `docs/GSTACK_WORKFLOW.md` 확인
4. `docs/ACTIVE_HANDOFF.md`에서 현재 목표와 미해결 질문 확인
5. 필요 시 `docs/OPEN_QUESTIONS.md`와 `tasks/` 확인

## Claude에게 기대하는 출력 형식

- 이번 턴의 목표
- 이번 턴 범위 밖 항목
- Codex가 구현할 단위
- 판단이 필요한 이슈
- 완료 기준

## README 최신화 규칙

`README.md`는 InsightChat 연동 담당자와 신규 합류자가 가장 먼저 읽는 문서다. 아래 항목이 변경되면 반드시 README.md를 함께 업데이트한다.

- API 엔드포인트 또는 요청/응답 스키마 변경
- 출력 스키마(`url`, `product_name`, `category`, `keyword`, `naver_match`, `google_match`, `reason`, `quality_warning`) 변경
- Job 상태 enum 추가·삭제·이름 변경
- 인증 방식 변경
- 기술 스택 변경 (언어 버전, 주요 라이브러리, 인프라)
- 저장소 구조 변경 (디렉터리 추가·삭제)

## 재발 방지 규칙

세션 시작 전 아래 피드백 규칙을 반드시 확인한다. 과거에 실제로 발생한 실수를 기반으로 작성됨.

1. **FR 정독 전 설계 결정 금지**: `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md`를 정독하기 전에 모델·라이브러리·스코프를 설계 문서에 포함하지 않는다.
2. **사용자가 명시한 것만 확정 처리**: 추론이나 기본값은 "확정(✅)" 처리 금지. 사용자가 직접 말한 것만 확정.
3. **버전 지정 전 wheel 확인 필수**: Python 버전이나 핵심 라이브러리 버전을 정할 때 PyPI wheel 지원 현황과 LTS 기간을 확인하고 근거와 함께 기록한다.

상세 내용: `C:\Users\NHN\.claude\projects\c--Users-NHN-Repo-Keyword-Generator\memory\` 내 feedback_*.md 파일 참조.

## 참고 문서

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
21. **Reject product-name token folklore as category inference**: if deterministic generation infers canonical product categories from ad hoc token maps like `mask -> 스킨케어` or `earbud -> 무선 이어폰`, require an evidence-first fallback instead.
22. **Reject audience-to-category auto-promotion in deterministic helpers**: broad audience evidence such as `건성 복합성 피부` should not be deterministically turned into category phrases like `건성 복합성 피부 마스크` unless the exact phrase is grounded on the page.
