# URL Product Keyword Generator

## Test Run

```powershell
.\scripts\run_pytests.ps1
```

Direct invocation also works:

```powershell
.\.venv-dev\Scripts\python.exe -m pytest tests -q
```

InsightChat의 URL 기반 검색 광고 키워드 자동 생성 서비스.

URL을 입력하면 해당 제품 페이지를 분석해 Naver SA / Google SA 광고에 사용할 키워드를 자동으로 생성한다.

---

## 서비스 개요

- **입력**: URL 최대 30개
- **출력**: 플랫폼별 URL당 최소 100개 키워드 (CSV / JSON)
- **처리 방식**: 비동기 job 모델. 결과는 완료 후 알림으로 전달.
- **지원 플랫폼**: `naver_sa`, `google_sa`, `both`

### 출력 스키마 (고정)

| 컬럼 | 설명 |
| --- | --- |
| `url` | 입력 URL 원문 |
| `product_name` | 추출된 제품명 |
| `category` | 10개 카테고리 중 하나 |
| `keyword` | 생성된 키워드 |
| `naver_match` | 네이버 매칭 타입 (naver_sa / both 시 채워짐) |
| `google_match` | 구글 매칭 타입 (google_sa / both 시 채워짐) |
| `reason` | 키워드 생성 근거 |
| `quality_warning` | 증거 품질 경고 여부 (boolean) |

---

## InsightChat 연동

### API 흐름

```
POST   /jobs                          → job_id 발급
GET    /jobs/{job_id}                 → job 상태 조회
GET    /jobs/{job_id}/results/{file}  → 결과 파일 다운로드 (presigned URL)
```

`GET /jobs/{job_id}`의 terminal URL task 항목은 `failure_code`, `failure_detail` 외에 운영자용 추정 원인 목록인 `failure_reason_hints[]`, 그리고 수집 fallback 가시성 필드인 `fallback_used`, `fallback_reason`, `preprocessing_source`를 포함할 수 있다.

### 요청 예시

```json
POST /jobs
{
  "urls": ["https://example.com/product/123"],
  "requested_platform_mode": "both",
  "notification_target": {
    "email": "user@example.com"
  }
}
```

### 응답 예시

```json
{
  "job_id": "j_abc123",
  "status": "RECEIVED",
  "submitted_count": 1,
  "created_at": "2026-04-06T10:00:00Z"
}
```

### Job 상태

| 상태 | 의미 |
| --- | --- |
| `RECEIVED` | 접수됨 |
| `RUNNING` | 처리 중 |
| `COMPLETED` | 전체 성공 |
| `PARTIAL_COMPLETED` | 일부 성공, 일부 실패 |
| `FAILED` | 전체 실패 |

### 인증

AWS Cognito JWT. `Authorization: Bearer <token>` 헤더 필수.

---

## 기술 스택

| 항목 | 선택 |
| --- | --- |
| 언어 | Python 3.13 |
| 스크래핑 | Crawl4AI + Playwright |
| OCR | PaddleOCR PP-OCRv5 (한국어) |
| LLM | AWS Bedrock Claude Sonnet 3.5 |
| 인프라 | AWS Lambda (Arm64), SQS, DynamoDB, S3, SES |
| 인증 | AWS Cognito + Naver/Google OAuth |

---

수집 라우팅 기본값:

- 기본 수집기: `HttpPageFetcher`
- 선택적 fallback 수집기: `Crawl4AI`
- fallback 전처리 우선순위: `cleaned_html` -> 비어 있거나 너무 약하면 rendered `raw_html`

## 저장소 구조

```
Keyword_Generator/
├── artifacts/          # 요구사항 원문 (수정 금지)
├── docs/               # 설계 문서, 정책 결정, 운영 규칙
│   ├── URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md  ← 핵심 설계 문서
│   ├── ACTIVE_HANDOFF.md                        ← 현재 진행 상태
│   └── OPEN_QUESTIONS.md                        ← 미결 사항
├── tasks/              # TASK-xxx 단위 작업 관리
├── CLAUDE.md           # Claude supervisor 가이드
├── AGENTS.md           # Codex 구현 가이드
└── README.md           # 이 파일
```

---

## 상세 문서

| 목적 | 문서 |
| --- | --- |
| 서비스 전체 설계 | [docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) |
| 요구사항 원문 | [artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md](artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md) |
| 현재 진행 상태 | [docs/ACTIVE_HANDOFF.md](docs/ACTIVE_HANDOFF.md) |
| 미결 사항 | [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) |
| 작업 목록 | [tasks/README.md](tasks/README.md) |

---

## 주요 제약

- `both` 모드: Naver와 Google 각각 독립적으로 최소 100개 검증
- 페이지 유형별 처리 방식 상이 (지원 6종, 즉시 실패 4종)
- 캐시: 동일 URL 7일 재사용 (canonical URL + 버전 기반 키)
- LLM은 AWS Bedrock Claude Sonnet 3.5 단독 사용 (FR-14)
