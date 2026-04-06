# GStack Workflow

## 설치 상태

- 소스: `.agents/skills/gstack`
- 생성된 Codex skills: `.agents/skills/gstack-*`
- 설치 방식: repo-local install + `setup --host codex`

## 이 프로젝트에서 쓸 gstack skill

### 계획/스펙 정리

- `gstack-office-hours`
  - 문제 정의가 아직 흐릴 때
  - 기능 목표, 사용자 가치, 범위 경계 정리
- `gstack-plan-ceo-review`
  - 기능 방향이 맞는지 점검할 때
  - 요구사항의 가치와 제품 레벨 리스크 검토
- `gstack-plan-eng-review`
  - 구현 전 설계 점검
  - API, job model, worker 분리, 저장 방식 검토

### 구현 중 품질 점검

- `gstack-review`
  - 코드 변경 후 버그/회귀/테스트 누락 점검
- `gstack-qa` / `gstack-qa-only`
  - 실제 UI 또는 endpoint 흐름 검증이 가능해졌을 때 사용
- `gstack-cso`
  - webhook, file download, auth, secret handling 같은 보안 검토가 필요할 때 사용

### 조사/추적

- `gstack-investigate`
  - 원인 불명 실패, queue stuck, scraper 이상 동작 조사
- `gstack-browse`
  - 웹 문서/공식 문서 조사 시 우선 사용

## 권장 사용 순서

1. 기능 정의 초안: `gstack-office-hours`
2. 제품 적합성 점검: `gstack-plan-ceo-review`
3. 구현 설계 점검: `gstack-plan-eng-review`
4. 구현 후 코드 리뷰: `gstack-review`
5. 배포 전 검증: `gstack-qa` 또는 `gstack-qa-only`

## 이 프로젝트 기준 기본 루틴

### 구현 시작 전

- `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md` 확인
- `docs/OPEN_QUESTIONS.md`와 `docs/STUDY_SESSION_2026-04-03.md` 확인
- `gstack-plan-eng-review`로 설계 공백 점검

### 구현 중

- 큰 단위 변경 전에는 먼저 task를 나눈다
- task 완료 후 `gstack-review`를 건다
- 외부 연동이나 보안 영향이 있으면 `gstack-cso`를 추가한다

### 구현 후

- 실행 가능한 환경이 있으면 `gstack-qa`
- UI 없는 단계면 `gstack-review` + 테스트 결과로 마감

## 주의점

- `gstack`은 강한 의견을 가진 skill pack이라 초반 탐색에는 유용하지만, 현재 저장소의 실제 제약보다 우선하면 안 된다.
- `artifacts/` 원문과 충돌하면 항상 원문 해석을 `docs/`에 남기고 판단 근거를 기록한다.
