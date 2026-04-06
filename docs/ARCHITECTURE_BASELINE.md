# Architecture Baseline

## 확정된 요구사항 신호

- AWS 내부에서만 동작해야 한다.
- 요청은 비동기 작업으로 접수한다.
- 최대 30개 URL을 한 번에 처리한다.
- URL 단위 실패 격리가 필요하다.
- 전체 작업은 30분 이내를 목표로 한다.
- 결과물은 URL별 JSON, 통합 JSON, CSV를 제공해야 한다.
- 동일 URL 재요청은 7일 TTL 캐시가 필요하다.

## 1차 구조 가설

```text
InsightChat API
  -> Job Create
  -> Job Store / Status Store
  -> Queue
  -> Content Collection Workers
  -> Keyword Generation Worker
  -> Result Persistor
  -> Notification Sender
```

## 구현 단위 제안

### 1. API 계층

- 작업 생성 endpoint
- 작업 상태 조회 endpoint
- 결과 다운로드 endpoint

### 2. 도메인 계층

- job lifecycle 관리
- URL 단위 처리 상태 관리
- partial completion 집계
- 캐시 hit/miss 판단

### 3. 수집 계층

- scraper orchestration
- OCR orchestration
- 콘텐츠 정제와 sufficiency 판정
- 실패 원인 분류

### 4. 생성 계층

- prompt 구성
- 키워드 카테고리 강제
- 플랫폼별 매칭 타입 매핑
- 최소 개수 보장 및 재시도

### 5. 결과 계층

- URL별 구조화 JSON 저장
- 통합 JSON 생성
- CSV flatten 생성
- 다운로드 메타데이터 기록

## 메인 프로젝트 연결 시 우선 검증할 가정

1. 기존 queue 인프라가 있다면 새로 만들지 않고 붙인다.
2. 기존 상태 저장 모델이 있다면 DynamoDB 신규 설계보다 우선 재사용한다.
3. 콘텐츠 수집은 선행 구현 자산을 최대한 재사용한다.
4. OCR와 scraper가 별도 worker로 남을지, 하나의 pipeline으로 합쳐질지는 런타임 제약을 보고 결정한다.

## 아직 미정인 항목

- API 스펙 세부 필드
- 인증/권한 처리 방식
- 저장소 종류(S3, DB, 둘 다)
- 알림 채널 구현 주체
- 실제 Bedrock 모델 버전 정책
