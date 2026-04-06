# Keyword Generator Workspace Guide

## 목적

이 저장소는 `InsightChat` 내 신규 기능인 `URL Product Keyword Generator`의 사전 준비, 구현 운영, 작업 추적을 위한 작업 공간이다.

## 디렉터리 규칙

- `artifacts/`: 사용자가 옮겨 놓은 참고 자료 원본. Source of truth로 간주한다.
- `docs/`: 구현 판단, 운영 원칙, 해석 문서, 준비 체크리스트를 둔다.
- `tasks/`: 실제 작업 단위를 기록하고 상태를 관리한다.

## 문서 운영 원칙

1. `artifacts/` 문서는 수정하지 않는다.
2. `artifacts/`의 내용이 최신 시스템과 다를 수 있으면, 그 차이는 `docs/`에 명시한다.
3. 구현 전에는 항상 `artifacts/`를 먼저 확인하고, 그 해석이나 가정만 `docs/`에 남긴다.
4. 새 작업은 말로만 남기지 않고 `tasks/`에 생성한다.

## 빠른 링크

- 요구사항 원문: `artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md`
- 운영 모델: `docs/OPERATING_MODEL.md`
- 운영 방식: `docs/AGENT_COLLABORATION.md`
- gstack 사용 규칙: `docs/GSTACK_WORKFLOW.md`
- 현재 handoff: `docs/ACTIVE_HANDOFF.md`
- 구현 준비 체크: `docs/IMPLEMENTATION_READINESS.md`
- 초기 아키텍처 가설: `docs/ARCHITECTURE_BASELINE.md`
- 열린 질문 목록: `docs/OPEN_QUESTIONS.md`
- 스터디 세션 노트: `docs/STUDY_SESSION_2026-04-03.md`
- 작업 관리 규칙: `tasks/README.md`
