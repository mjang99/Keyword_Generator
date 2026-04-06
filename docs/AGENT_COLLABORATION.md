# Agent Collaboration

## 역할 정의

- 사용자: 제품 방향, 우선순위, 참고 자료 제공 담당
- Claude: supervisor 역할, 작업 분해와 판단 보조 담당
- Codex: 구현, 검증, 문서/작업 반영 담당

## 기본 작업 순서

1. `artifacts/`에서 source of truth를 확인한다.
2. `docs/`에서 해석, open question, 결정 사항을 정리한다.
3. 현재 요청 범위를 `tasks/` 작업으로 구체화한다.
4. 구현 또는 조사 결과를 `docs/`에 반영한다.
4. 가정, 미확정 사항, 최신성 리스크를 문서에 분리해서 남긴다.

## 운영 프레임

- 문서 운영 기준: `docs/OPERATING_MODEL.md`
- gstack skill 사용 기준: `docs/GSTACK_WORKFLOW.md`

## 문서 배치 규칙

- 에이전트 운영 방식, 구현 규칙, 준비 체크리스트는 `docs/`
- 작업 단위, 진행 상태, 완료 조건은 `tasks/`
- 외부에서 받은 원문 자료는 `artifacts/`
- repo-local agent skill은 `.agents/skills/`

## Source Of Truth 규칙

- 원문 요구사항, 과거 산출물, 사내 공유 자료는 `artifacts/`를 기준으로 본다.
- `docs/`는 해석 계층이다. 원문을 덮어쓰지 않는다.
- 최신 구현 상태와 원문이 다를 수 있으면 아래 항목을 반드시 적는다.
  - 무엇이 다른지
  - 확인 날짜
  - 확인 근거
  - 후속 확인 필요 여부

## 작업 관리 규칙

- 새 구현 단위는 `TASK-xxx` 문서로 만든다.
- 각 task는 최소한 아래 항목을 가진다.
  - 목적
  - 범위
  - 선행조건
  - 완료조건
  - 메모 또는 리스크

## 구현 시작 전 확인

- 메인 프로젝트 접근 권한 확보 여부
- InsightChat 내부 연결 지점 확인 여부
- 기존 공통 인프라/유틸 재사용 가능 여부
- 배포 단위와 저장 위치 확정 여부
- 필요한 경우 gstack의 plan/review skill을 먼저 사용했는지
