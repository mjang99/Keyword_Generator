# TASK-009 Export Aggregation And Notification Design

- status: done
- owner: Codex
- priority: medium
- depends_on: TASK-004, TASK-007, TASK-008

## Goal

Define how fixed-schema rows are emitted, how `both` mode is flattened into per-row exports, how failures are represented, and how final job notifications work.

## Scope

- Per-URL JSON row shape
- Combined JSON and CSV flatten rule
- `both` mode row emission rule
- Row-level rendering examples for `reason` and `quality_warning`
- Failure manifest shape
- Job final status aggregation rule
- SES and webhook notification payload rule

## Done When

- The exporter preserves the fixed schema exactly and keeps richer metadata in a separate internal artifact.
- `both` mode row flattening is documented with explicit JSON and CSV examples.
- `both` mode includes one example where an intent is emitted for both platforms and one where it is emitted for only one platform.
- Row examples show how `reason` and `quality_warning` are rendered from locked upstream contracts.
- Partial completion, no fake rows, and one-notification semantics are locked.

## Notes

- This is the task that should fully lock `both` export semantics.
- Use [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) Sections 3.3, 5, and 6 as the starting point.
- Do not redefine request semantics, cache keys, or failure-code enums here. Those belong to `TASK-004`.
- Locked design output now lives in [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) Section 4.3.
- Runtime helpers now live in [models.py](/c:/Users/NHN/Repo/Keyword_Generator/src/exporting/models.py) and [service.py](/c:/Users/NHN/Repo/Keyword_Generator/src/exporting/service.py).
- Coverage includes per-URL JSON payloads, `both` flatten semantics, failure manifest generation, terminal job aggregation, and channel-neutral notification payloads.
