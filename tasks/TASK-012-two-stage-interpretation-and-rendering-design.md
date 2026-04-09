# TASK-012 Two-Stage Interpretation And Rendering Design

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-007, TASK-008

## Goal

Redesign keyword generation around a two-stage flow that first interprets product meaning and then renders keywords from that structured interpretation.

## Scope

- Define the `ProductInterpretation` schema
- Split canonical category from secondary facets
- Separate specs, ingredients, technology, audience, benefits, concerns, usage context, and commerce facts
- Define rendering families and template rules for each facet type
- Make quality-first shortfall behavior explicit: low-quality rows must be dropped even when the floor is missed
- Define which responsibilities stay deterministic vs Bedrock-driven

## Done When

- The design clearly explains why current `attributes` and `generic_category` buckets create category drift and awkward phrases
- A single `canonical_category` contract is defined for rendering
- Rendering rules show which facet combinations are allowed and which are forbidden
- The design explicitly states that floor shortfall is preferable to low-quality filler
- The migration path from the current phrase-bank generator to the two-stage design is documented

## Notes

- Use [URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/URL_KEYWORD_GENERATOR_SERVICE_DESIGN.md) as the baseline contract.
- This task is a redesign note for generation quality; it does not change the external API or export schema.
- Completed with:
  - [KEYWORD_INTERPRETATION_AND_RENDERING_REDESIGN.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_INTERPRETATION_AND_RENDERING_REDESIGN.md)
  - typed-facet interpretation wired into deterministic generation
  - Bedrock prompt payloads updated to carry `interpretation`, `canonical_category`, and comparison/surface-cleanup policy hints
