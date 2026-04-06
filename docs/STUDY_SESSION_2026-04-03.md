# Study Session — 2026-04-03

> 오늘 스터디 목표: 내일 구현 착수 전 기술 스택 검증 + 아키텍처 설계 확도 높이기

---

## 참고 자료

- `artifacts/NOL_kwd_generator_006.ipynb` — 유사 서비스 선행 구현 예시 (Bedrock 호출 패턴, 파싱 로직 참고용)
- 요구사항 원문이 항상 1순위. 노트북은 구현 기술 참고만.

---

## 서비스 성격 확정 (2026-04-03)

**이 기능은 독립 서비스다.**

- Input: URL 목록 (최대 30개)
- Output: 키워드 CSV / JSON
- InsightChat이 이 서비스를 호출하는 형태
- 기존 인프라 의존성 없음 → 모든 인프라 자체 구축
- 공유 DB, 공유 job queue, 공유 notification 없음

→ IQ-02, IQ-03, IQ-04, IQ-05 모두 "자체 구축"으로 확정.

---

## 결정된 사항 (스터디 완료)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| Provisioned Concurrency | **불필요** | 비동기 처리, Cold Start 허용 가능 |
| ECS Fargate 전환 | **불필요** | Lambda로 충분 |
| LLM 모델 | **Claude Sonnet 3.5 (전용)** | FR-14 명시. Sonnet 4.6은 요구사항 외 |
| OCR 방식 | **PaddleOCR(PP-OCRv5) 유지** | Textract 한국어 미지원, 비용 80% 절감 |
| 30개 동시 Bedrock 호출 | **가능** | max_tokens 명시 필수 (아래 참고) |
| Lambda 아키텍처 | **Arm64 권장** | 30% 비용 절감, CPU 성능 향상 |
| 알림 구현 | **AWS SES 직접** | 독립 서비스이므로 자체 구현 |
| 결과 저장 | **전용 S3 버킷** | 독립 서비스이므로 자체 버킷 |
| Job 상태 저장 | **DynamoDB** | 서버리스 친화적, TTL 기능 활용 |
| 구현 언어 | **Python 3.13** | PaddlePaddle 3.14 wheel 미제공, 3.12는 security-only (2026-04-06) |

---

## 1. Crawl4AI Lambda Cold Start — 결론

### 조사 결과

- Lambda 컨테이너 Cold Start 2025년 대폭 개선 (15x faster)
- 1.5GB 이미지 기준 실측: **약 4~10초** (ECR 레이어 캐싱 덕분에 이미지 크기보다 네트워크 latency가 지배적)
- Playwright + Chromium 포함 시: **5~40초** (최적화 수준에 따라)
- **2025년 8월부터 INIT phase(Cold Start)도 과금됨** → 비용 10~50% 증가 가능

### 결론: Provisioned Concurrency 불필요

비동기 처리(SQS triggered)이므로 사용자가 Cold Start를 실시간으로 기다리지 않는다.
30개 URL × 병렬 처리 구조에서 첫 Cold Start는 전체 시간에 1회만 영향.

- Lambda 유지, Provisioned Concurrency 미사용
- Arm64 아키텍처 적용 → CPU 성능 4~5x 향상, 비용 30% 절감
- 메모리: Playwright 특성상 **3GB 이상** 권장

---

## 2. PaddleOCR vs OCR 대안 — 결론

### OCR 옵션 비교

| 선택지 | 한국어 지원 | 비용(10K 이미지/월) | 품질 | 결론 |
| --- | --- | --- | --- | --- |
| **PaddleOCR (PP-OCRv5)** | O (정확도 0.93) | ~$10~15 | 우수 | **채택** |
| AWS Textract | **X (미지원)** | — | — | **탈락** |
| Bedrock Claude vision | O (최우수) | ~$49 | 최우수 | Fallback |
| EasyOCR | O (정확도 0.85) | ~$10~15 | 보통 | 미채택 |

**Textract는 영어/스페인어/독일어 등 6개 언어만 지원. 한국어 로드맵 미공개.**

### 결론: PaddleOCR(PP-OCRv5) 유지

- PP-OCRv5: CPU 최적화, 2GB Lambda 내 운영 가능
- 모델 컨테이너 빌드 시 사전 다운로드 (runtime cold start 제거)
- vision 보정이 필요한 경우도 Sonnet 3.5로 처리 (FR-14 기준)

---

## 3. Bedrock 쓰로틀링 — 핵심 발견

### 사용 모델: Claude Sonnet 3.5 (FR-14 기준, 전 용도 단일 모델)

### max_tokens 함정

> **`max_tokens`를 명시하지 않으면 기본값 64,000 토큰을 예약한다.**

| 시나리오 | max_tokens | 동시 가능 요청 수 (2M TPM 기준) |
| --- | --- | --- |
| 미설정 (기본값) | 64,000 | **3~6개** ← 함정 |
| 명시 설정 | 2,000 | 500+ |
| 명시 설정 | 1,000 | 1,000+ |

→ **Bedrock 호출 시 반드시 `max_tokens` 명시. 키워드 100개 생성 기준 2,000~4,000 정도.**

### ap-northeast-2 실제 Quota (2026-04-03 AWS 콘솔 확인)

| 모델 | 타입 | TPM | RPM |
| --- | --- | --- | --- |
| Claude 3.5 Sonnet | On-demand | 400K | 50 |
| Claude 3.5 Sonnet | Geo cross-region | 800K | **100** |
| Claude 3.5 Sonnet V2 | Geo cross-region | 800K | 100 |
| Claude 3.7 Sonnet V1 | Geo cross-region | 1M | 250 |

FR-14 기준 사용 모델은 Sonnet 3.5. 다른 모델은 참고만.

- On-demand 50 RPM은 낮음 → **Geo cross-region 사용 권장** (100 RPM, 800K TPM)
- 초과 시 Service Quotas에서 증량 요청 (1~2일 소요)

### 30개 동시 처리 RPM 계산 (단일 풀 전략 기준)

```text
URL당 Bedrock 호출:
  - 콘텐츠 충족도 판정: 1회
  - 키워드 생성(단일 풀): 1회
  - 실패 진단(필요 시): 0~1회
  합계: 최소 2회/URL

30개 URL 동시:
  - 최대 60~90 RPM 순간 발생
  - SQS 자연 분산으로 실제로는 분 단위로 퍼짐
  - Geo cross-region 100 RPM 내에서 처리 가능
  - On-demand 50 RPM은 초과 가능 → Geo 사용 필수
```

### 30개 동시 호출 가능 조건

- SQS 버퍼가 이미 load leveling 역할 → 순간 동시 호출 폭증 방지
- max_tokens 명시 + SQS 조합으로 30개 동시 처리 가능
- ThrottlingException 대비: exponential backoff with jitter (SDK adaptive mode)

---

## 4. 병렬 처리 설계 — 30분 SLA

### 병렬 처리 구조 (확정)

```text
API Gateway
    │
    ▼
Lambda(Dispatcher) → job_id 발급, DynamoDB job 생성
    │
    ▼ (30개 SQS 메시지 동시 발행)
SQS(scrape-queue)
    │ batch_size=1
    ▼
Lambda(Scraper) × 30 동시          ← Crawl4AI, Arm64, 3GB, 15분
    │ 성공 → scrape-done-queue
    │ 실패 → DynamoDB FAILED 기록
    ▼
SQS(ocr-queue)
    │ batch_size=1
    ▼
Lambda(OCR Worker) × N 동시        ← PaddleOCR, Arm64, 4GB
    │ 성공 → ocr-done-queue
    ▼
SQS(keyword-queue)
    │ batch_size=1
    ▼
Lambda(Keyword Gen) × 30 동시      ← Bedrock Sonnet 3.5, max_tokens 명시
    │ 성공 → S3 저장, DynamoDB DONE
    │ 전체 완료 → Lambda(Notifier) → SES 발송
    ▼
DynamoDB 집계 → job 상태 업데이트
```

### SLA 계산 (병렬 기준)

```text
1 URL 처리 시간:
  Scraping:     30~60초
  OCR:          10~30초 (이미지 수에 따라)
  Keyword Gen:  20~40초
  합계:         60~130초

30개 완전 병렬:
  이론적 최소: 130초 (~2분)
  Cold Start + 대기 포함: ~5~10분
  → 30분 SLA 여유 충분
```

---

## 5. 상태 모델 (DynamoDB)

### Job 테이블

```text
PK: job_id (UUID)
- status: PENDING | COLLECTING | GENERATING | COMPLETED | PARTIAL | FAILED
- created_at, updated_at (ISO8601)
- total_urls, success_count, fail_count
- platform: naver_sa | google_sa | both
- notification: { email?, webhook_url? }
- result_s3_prefix: s3://bucket/results/{job_id}/
- ttl: epoch (결과 보관 7일)
```

### URL Item 테이블

```text
PK: job_id  SK: url_hash (SHA256)
- url: 원본 URL
- status: PENDING | SCRAPING | OCR | GENERATING | DONE | FAILED
- fail_reason: 실패 유형 (bot_block | not_found | render_fail | llm_fail | ...)
- keyword_count
- quality_warning: bool
- cached: bool
- result_s3_key: URL별 JSON
```

### 캐시 테이블

```text
PK: url_cache_key (정규화된 URL의 SHA256)
- result_s3_key: S3 경로
- created_at
- ttl: epoch (7일, DynamoDB TTL 자동 삭제)
```

---

## 6. S3 구조

```text
s3://keyword-generator-results/
  jobs/{job_id}/
    urls/{url_hash}.json    ← URL별 키워드 JSON
    summary.json            ← 통합 JSON
    keywords.csv            ← 평탄화 CSV
    metadata.json           ← job 메타데이터
```

- 다운로드: **Presigned URL (유효 24시간)** — API Gateway → Lambda → S3 GetObject 프록시보다 단순
- 캐시 결과는 별도 prefix: `cache/{url_hash}.json`

---

## 7. 실패 격리 패턴

```text
각 SQS Queue:
  - maxReceiveCount: 3
  - 3회 실패 → DLQ
  - DLQ → Lambda(FailureRecorder) → DynamoDB FAILED 기록

실패 유형별 처리 (Appendix A.4 기준):
  - bot_block: 스텔스 재시도 1회 후 FAIL
  - not_found: 즉시 FAIL
  - render_fail: 팝업 제거 + 대기 연장 재시도 후 FAIL
  - llm_fail: ThrottlingException → backoff 재시도 / 기타 → FAIL
```

---

## 내일 구현 착수 전 남은 확인 항목

### 즉시 확인 가능한 것 (AWS 콘솔)

- [x] ap-northeast-2 Bedrock Sonnet 3.5 모델 활성화 여부 → Geo cross-region 사용 가능 확인
- [x] ap-northeast-2 Bedrock 기본 TPM/RPM quota 수치 → Sonnet 3.5 Geo: 800K TPM / 100 RPM

### 기획 확인 필요 (RQ 미정 항목)

- [ ] RQ-01: URL당 100개 — 합산인가, 플랫폼별인가?
- [ ] RQ-02: 부정 키워드 count 포함 여부
- [ ] RQ-04: URL 캐시 키 정규화 방식

### InsightChat 접근 후 확인 (IQ 잔여)

- [ ] IQ-01: InsightChat 백엔드 기술 스택 (API 연동 방식 결정에 영향)
- [ ] IQ-06: 사용자 인증/권한 모델 (API 호출 시 인증 헤더 방식)
