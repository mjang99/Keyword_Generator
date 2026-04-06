# Operating Model

## 원칙

이 저장소는 `artifact 기반 스펙 관리`와 `gstack 기반 작업 흐름`을 함께 사용한다.

## Source Of Truth 계층

- `artifacts/`
  - 외부에서 받은 요구사항 원문, 참고 자료, 과거 산출물
  - source of truth
  - 수정 금지
- `docs/`
  - 요구사항 해석, 운영 규칙, readiness, open questions, 결정 로그
- `tasks/`
  - 실제 작업 단위와 진행 상태
- `.agents/skills/`
  - repo-local agent skill
  - 현재는 `gstack`과 그 generated Codex skills를 둔다

## 작업 흐름

1. `artifacts/`에서 원문 기준을 확인한다.
2. `docs/`에서 해석, 질문, 결정, 리스크를 정리한다.
3. `tasks/`로 구현 단위를 내린다.
4. 구현 중 판단 보조와 리뷰는 `gstack` skill로 수행한다.

## 현재 운영 방침

- `gstack`은 repo-local로 유지한다.
- 이 저장소의 작업 방식은 `gstack` skill을 전제로 한다.
- `spec-kit`은 당장 본 저장소에 init하지 않는다.
- `spec-kit`은 별도 preview 또는 향후 구조 정리 시점에 다시 검토한다.

## 왜 이렇게 가는가

- `gstack`은 현재 repo에 이미 안전하게 설치되었고 Codex skill 생성까지 끝났다.
- `spec-kit`은 프로젝트 루트 구조 생성 성격이 강해서 현재 `docs/`, `tasks/` 체계와 충돌 가능성이 있다.
- 지금 우선순위는 구현 운영 강화이지, 저장소 구조 재초기화가 아니다.
