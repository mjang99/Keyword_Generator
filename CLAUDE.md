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
