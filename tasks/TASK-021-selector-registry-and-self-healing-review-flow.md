# TASK-021 Selector Registry And Self-Healing Review Flow

- status: todo
- owner: Codex
- priority: high
- depends_on: TASK-020

## Goal

Create a selector registry and a review-gated self-healing workflow so selector drift can be detected and repaired without unsafe automatic schema replacement.

## Scope

- Define per-domain selector schema storage and versioning.
- Define failure-detection thresholds for selector drift.
- Define the LLM proposal format for replacement selectors.
- Define replay validation against sample pages and no-regression checks.
- Define approval, promotion, rollback, and audit rules for selector changes.

## Done When

- Selector schemas have explicit `active/proposed/rejected/deprecated` states.
- A failed extraction can produce a repair proposal instead of mutating production automatically.
- Replay validation and conditional promotion rules are written down and testable.

## Notes

- Automatic production selector replacement is forbidden.
- Review-gated promotion is mandatory for core-field selectors.
