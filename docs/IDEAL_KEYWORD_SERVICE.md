# Ideal Keyword Service

> Drafted on 2026-04-03.
> Purpose: define the ideal product behavior for the URL-based keyword generator without changing the fixed output schema in the requirement document.

---

## 1. Goal

The ideal service should do one thing extremely well:

- take a product URL
- extract the strongest possible commercial signals from that page
- generate at least 100 usable ad keywords
- return them in the fixed requirement output format
- make weak or inferred outputs explicit instead of hiding uncertainty

The ideal system is not just a keyword generator.
It is a `keyword generation and quality-control system`.

---

## 2. Product Principle

The requirement already fixes the final output columns.
So the product challenge is not output design.
The challenge is upstream quality control.

The ideal service should optimize for:

1. relevance to the actual product
2. commercial usefulness for search ads
3. stable category coverage
4. explainability of why each keyword exists
5. graceful behavior on weak or sparse pages

---

## 3. Ideal User Experience

### Input

The user provides:

- up to 30 product URLs
- target platform: `naver_sa`, `google_sa`, or `both`
- optional notification target

### Output

The user receives:

- job status updates
- per-URL results
- combined CSV/JSON output in the fixed schema
- partial-complete results when some URLs fail

### What makes the ideal UX different

The ideal experience is:

- fast enough to trust
- transparent about uncertainty
- consistent across page types
- good enough that an operator edits results, not invents them from scratch

---

## 4. Ideal Processing Pipeline

### Stage 1: URL Intake

- validate URL shape
- normalize cache key
- detect duplicate URLs in the same request
- classify obvious unsupported URL types early

### Stage 2: Page Acquisition

- fetch rendered product page content
- collect title, description, breadcrumbs, structured data, visible text, variant data, price, options, and images
- isolate failures per URL

### Stage 3: Page Classification

Before keyword generation, classify the page:

- `rich_text_page`
- `balanced_page`
- `sparse_page`
- `blocked_page`

This should drive later behavior.

### Stage 4: Evidence Assembly

Build a normalized evidence package with:

- direct evidence
- derived evidence
- OCR evidence
- inferred but defensible expansions

### Stage 5: Keyword Generation

Generate candidates by category:

- brand
- generic/category
- feature/attribute
- competitor/comparison
- purchase intent
- long-tail
- price/promotion
- season/occasion
- problem/need
- negative keywords separately

### Stage 6: Quality Control

- deduplicate literal duplicates
- deduplicate intent duplicates
- remove unsupported promo claims
- remove misleading use-case claims
- mark weak evidence
- backfill intelligently to reach 100+

### Stage 7: Platform Shaping

Using the same final fixed schema:

- assign `naver_match`
- assign `google_match`
- assign `reason`
- assign `quality_warning`

### Stage 8: Export

- write per-URL JSON
- write merged CSV
- expose result API
- emit completion notification

---

## 5. Ideal Intelligence Layer

The ideal system should not rely on one extraction method.
It should use a ranked evidence model.

### Evidence Levels

- `direct`: explicit on the page
- `derived`: normalized or lightly transformed from direct page data
- `inferred`: commercially reasonable expansion from strong evidence
- `weak`: low-confidence expansion that should usually be filtered or warned

This does not change the output schema.
It changes how `reason` and `quality_warning` are populated.

### Why this matters

Without evidence levels:

- weak pages look the same as rich pages
- operators cannot distinguish strong vs speculative terms
- reaching 100 becomes noisy instead of controlled

---

## 6. Ideal Sparse-Page Behavior

This is the biggest product requirement exposed by testing.

For sparse pages:

- OCR becomes secondary, not primary
- the service should lean more on product family, category, use-case, and need-state expansion
- promo claims should be blocked unless explicitly supported
- confidence-aware backfill should be used to reach 100

The ideal sparse-page policy:

1. preserve core relevance
2. allow more derived and inferred long-tail
3. do not backfill with OCR garbage
4. do not backfill with unsupported sales language
5. mark lower-confidence outputs through `quality_warning`

---

## 7. Ideal Locale Strategy

This needs to be explicit before implementation.

For example:

- product page language may be English
- target ad market may be Korean

The ideal service should support a policy like:

- `source_language`
- `market_language`
- `mixed_brand_mode`

Practical default:

- keep brand, product line, and model in source language
- localize generic, intent, and need-state terms to target market language

Without a locale policy, keyword quality will vary too much by market.

---

## 8. Ideal Count-Fill Policy

The service must always reach the requirement minimum when possible.
But it should not fill blindly.

The ideal fill order is:

1. direct brand and product terms
2. direct category and feature terms
3. derived commercial rewrites
4. inferred long-tail and need-state terms
5. tightly controlled competitor/comparison terms

The service should avoid filling with:

- unsupported sale/promo claims
- OCR junk
- near-duplicate intent
- overly broad head terms

---

## 9. Ideal Quality Controls

### Deduplication

The ideal service should perform:

- string dedup
- normalized-form dedup
- intent-cluster dedup

### Guardrails

The ideal service should explicitly block:

- unsupported discounts
- unsupported medical claims
- unsupported performance claims
- category mismatch terms

### Backfill Rules

If strong candidates are below target:

- widen long-tail first
- widen problem/need second
- widen comparison third
- widen season/occasion last

---

## 10. Ideal Modes

The ideal product should support two internal operating modes even if the API remains simple.

### Exploration Mode

- maximize breadth
- allow more inferred terms
- useful for planning and research

### Production Mode

- stricter evidence threshold
- tighter dedup
- stricter promo filtering
- safer for direct campaign use

This can be implemented internally without changing the requirement output schema.

---

## 11. Ideal Success Criteria

The ideal system is successful if:

- it always reaches `100+` where feasible
- category coverage is stable
- weak pages still produce useful outputs
- operators can understand why keywords were generated
- partial failures do not corrupt the full job
- generated outputs require refinement, not rescue

---

## 12. Recommended Product Decisions Before Build

These should be decided explicitly before implementation starts:

1. locale policy for English page -> Korean ad output
2. sparse-page classification thresholds
3. evidence-level rules
4. intent-dedup behavior
5. backfill order when evidence is thin
6. comparison-keyword aggressiveness
7. promo-claim blocking rules

---

## 13. Bottom Line

The ideal functionality is not:

- scrape page
- ask LLM for 100 terms
- dump output

The ideal functionality is:

- classify page quality
- build evidence hierarchy
- generate candidates by category
- filter by commercial relevance
- backfill intelligently
- emit fixed-schema output with controlled warnings

That is the version most likely to satisfy both the written requirement and real ad-ops use.
