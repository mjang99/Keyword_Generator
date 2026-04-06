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
