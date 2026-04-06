# TASK-004 API And Job Model Design

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-003

## Goal

Define the API contract, job model, URL task model, cache model, and export semantics required to implement the service safely.

## Scope

- Request and response schema
- Job state machine
- URL task state model
- Result file metadata model
- Cache key and TTL model
- `requested_platform_mode` semantics for `naver_sa`, `google_sa`, and `both`
- Export contract semantics for `both` mode
- Failure-code enum and status payload shape
- Cache-key examples for `naver_sa`, `google_sa`, and `both`
- Fixed output schema mapping for `naver_match`, `google_match`, `reason`, and `quality_warning`

## Done When

- The API shape and lifecycle model are documented in enough detail to implement handlers directly.
- `both` mode contract behavior is defined together with the validator/exporter interface, without owning CSV or JSON rendering examples.
- Failure-code and status payload examples are documented for terminal URL states and partial-completion job states.
- Cache-key semantics are documented with concrete examples, including platform mode and version-bump invalidation behavior.
- The fixed output schema is preserved exactly and only the internal mapping rules are defined here.

## Notes

- Use [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) Sections 2, 3, and 4 as the design anchor.
- Do not define CSV or combined JSON examples here. Those belong to `TASK-009`.
- Locked outputs now live in [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) Sections 2.1, 2.2, 3.1, 3.2.1, 3.2.2, 3.2.3, 3.3, and 3.4.
- `POST /jobs`, `GET /jobs/{job_id}`, and `GET /jobs/{job_id}/results/{artifact_name}` are now specified tightly enough to implement request validation, status handlers, and artifact lookup handlers directly.
- `requested_platform_mode`, `failure_code`, `status` payloads, cache-key versioning, and fixed-schema mapping rules are locked here so downstream tasks should consume them instead of redefining them.
