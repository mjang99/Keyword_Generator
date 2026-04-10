# TASK-026 Crawl4AI Preprocessing Contract Widening

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-025

## Goal

Lock the minimum contract change required to adopt Crawl4AI preprocessing without destabilizing `HtmlFetchResult`, `NormalizedPageSnapshot`, or downstream runtime stages.

## Scope

- Define the preferred widening target as a repo-owned intermediate preprocessing artifact:
  - `collection/preprocessed_page.json`
- Decide which Crawl4AI outputs may be promoted into canonical inputs:
  - rendered final HTML
  - final URL and stable fetch metadata
  - `cleaned_html`, but only as a text-input candidate
- Decide which Crawl4AI outputs must remain sidecars:
  - markdown
  - `fit_markdown`
  - screenshot metadata
  - media inventory
- Specify how the intermediate artifact may influence existing snapshot fields:
  - `decoded_text`
  - `visible_text_blocks`
  - `structured_data`
  - `image_candidates[]`

## Non-Goals

- Do not widen `NormalizedPageSnapshot` with raw Crawl4AI fields.
- Do not add markdown, screenshot, or media inventory fields to `HtmlFetchResult`.
- Do not redesign OCR, evidence, or classifier contracts in this task.

## Required Decisions

- `HtmlFetchResult` remains fetch-oriented and narrow by default.
- `collection/preprocessed_page.json` is the first-class widening target.
- Rendered HTML is the canonical DOM input when Crawl4AI is used.
- `cleaned_html` may only be promoted as the preferred text-input candidate after benchmark proof.
- Markdown and `fit_markdown` are explicitly non-canonical for snapshot shaping.
- Screenshot data and media inventory remain sidecars until a later task proves a concrete downstream contract need.

## Done When

- The architecture doc explicitly separates:
  - canonical inputs
  - sidecars
  - promotion rules
- The preferred intermediate artifact and its path are written down.
- The task defines which existing snapshot fields may consume the intermediate artifact and which may not.
- Any widening proposal is tied to measured quality gains from `TASK-024`, not convenience alone.

## Notes

- Favor indirect computation changes over schema growth. For example, allow `decoded_text` to prefer `cleaned_html` before adding any new snapshot field.
- `image_candidates[]` and `structured_data` stay repo-owned normalized outputs even if Crawl4AI sidecars help seed them.
- If a later task proposes widening `HtmlFetchResult`, it must justify why `collection/preprocessed_page.json` is insufficient.
- The canonical-vs-sidecar decision is recorded in [CRAWL4AI_PRODUCT_EXTRACTION_ARCHITECTURE_2026-04-10.md](/C:/Users/NHN/Repo/Keyword_Generator/docs/CRAWL4AI_PRODUCT_EXTRACTION_ARCHITECTURE_2026-04-10.md).
