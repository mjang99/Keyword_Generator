# TASK-002 Main Project Discovery

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-001

## Goal

메인 InsightChat 프로젝트 접근 권한 확보 후 실제 연결 지점과 재사용 가능한 기존 구조를 파악한다.

## Scope

- API 진입점 확인
- 비동기 작업 처리 구조 확인
- auth, logging, storage, notification 공통 모듈 확인
- 기존 crawler/OCR/LLM 유틸 존재 여부 확인

## Done When

- 실제 구현 위치가 확정된다.
- 재사용 가능 모듈과 신규 구현 모듈이 구분된다.
- 아키텍처 가설과 실제 구조 차이가 문서화된다.

## Notes

- 이 task 완료 전에는 실제 폴더 구조나 런타임에 대한 단정 금지
