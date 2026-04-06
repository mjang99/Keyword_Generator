# Keyword Service Test Findings

> Findings from pre-implementation service testing across multiple PDP and non-PDP page types on 2026-04-03.

This document captures service-design considerations exposed during pre-implementation testing.

---

## 1. Main Finding

The service cannot treat `100 keywords generated` as the same thing as `100 useful ad keywords generated`.

For sparse product pages, the hard part is not reaching 100.
The hard part is reaching 100 without filling the tail with unsupported or duplicate intent.

---

## 2. Missing Considerations Exposed By Testing

### 1. Locale Strategy Is Missing

The tested page is English, but the target market in the requirement context is Korean search advertising.

Questions the service must answer:

- Should output follow page language?
- Should output follow market language?
- Should the service generate Korean only, English only, or mixed keywords?
- Should brand and model stay in English while generic intent is localized to Korean?

This is a major product decision, not a small implementation detail.

### 2. Need Evidence Strength Tiers

Not every generated keyword is equally grounded.
The system needs explicit evidence grades such as:

- `direct`
- `derived`
- `inferred`
- `weak`

Without this, the service cannot explain or filter weak terms.

### 3. Need A Sparse-Page Mode

This page is image-heavy and text-poor.
The service should classify pages before generation:

- `rich_text_page`
- `balanced_page`
- `sparse_page`
- `blocked_page`

Generation behavior should change by page class.

### 4. Need A Promo-Claim Guardrail

Pages often do not contain real discount or promo information.
The generator needs a rule:

- do not generate `sale`, `discount`, `coupon`, `cheap`, `under budget` unless the page provides evidence

### 5. Need Intent-Level Deduplication

String dedup is not enough.
The service needs intent dedup, because these may be effectively the same:

- `men's sneaker`
- `mens sneakers`
- `cloudtilt shoes men`
- `on cloudtilt mens shoes`

### 6. Need Count-Fill Policy

When strong evidence is limited, how should the system reach 100?

Possible strategies:

- expand more into problem/need
- expand more into long-tail
- expand more into competitor/comparison
- allow weaker inferred terms
- stop at fewer strong terms and backfill with `inferred` labels

This policy should be explicit.

### 7. Need Output Modes

The service should likely support at least two modes:

- `exploration mode`: maximize breadth, allow more inferred terms
- `production mode`: stricter evidence, tighter duplicates, safer for upload

Testing showed these are not the same output.

### 8. Need Category Count Semantics

The requirement says at least 100 and also references 10 categories.
The service needs exact semantics for:

- whether negatives count toward category coverage
- whether every category needs a minimum count
- whether platform-specific outputs must each independently satisfy the mix

### 9. Need Platform-Specific Rewrite Rules

A platform-agnostic keyword pool is useful, but final delivery should likely be platform-shaped.

Examples:

- Naver may tolerate broader Korean commercial phrasing differently
- Google requires stronger explicit match-type strategy
- competitor/comparison terms may be handled differently by platform

### 10. Need Confidence-Aware Backfill

When the generator gets near 100, it should prefer:

- adding lower-risk long-tail variants

instead of:

- adding unsupported promo terms
- adding noisy OCR fragments
- repeating near-identical intent

### 11. Need Sellability Classification

Broader testing showed that `product page` is still too broad.

The service needs to distinguish at least:

- `commerce_pdp`
- `marketing_only_pdp`
- `product_marketing_page`
- `non_product_page`

This matters because all four can mention a specific product name, but they do not provide the same quality of commercial evidence.

### 12. Need Stock-State Policy

Some strong PDPs were `OutOfStock` but still rich enough to generate useful keywords.

The service needs an explicit rule:

- still generate keywords from out-of-stock pages
- but avoid implying immediate purchase urgency unless stock evidence supports it

### 13. Need Structured-Data Trust Rules

New cases showed that structured data is helpful but not always trustworthy at face value.

Examples:

- `buy` language with effectively empty pricing
- dynamic pricing placeholders
- inconsistent vendor / brand fields

The service should merge signals, not blindly trust one field.

### 14. Need Claim Compression For Beauty Pages

Beauty PDPs can include long descriptions full of claims, percentages, tests, ingredient lists, and exclusions.

Without compression rules, the generator will over-index on:

- clinically phrased claims
- ingredient spam
- repeated benefit language

The service needs to normalize this into a smaller set of grounded commercial intents.

### 15. Need Review And Award Signal Policy

Some Korean beauty pages include strong merchandising signals such as:

- award badges
- review volume
- satisfaction percentages
- hashtag-style problem labels

These are commercially useful, but they are not the same as first-party product facts.

The service needs rules for how heavily these signals should influence keyword generation.

### 16. Need Support/Specs Page Policy

Broader testing showed that product-specific support pages can also be rich sources.

Examples:

- technical specifications
- compatibility
- legal product info
- included items

The service needs an explicit decision:

- reject support/spec pages as non-target inputs
- or allow them as fallback evidence when commerce PDP access is weak

### 17. Need Support-Source Failure Classification

Support pages do not behave the same way across brands.

In this test set:

- Apple support/spec pages fetched successfully
- Sony support page returned `Access Denied`

So `support source` should not be treated as uniformly safe or unsafe.

### 18. Need Promo-Source Policy

Broader testing suggests strong promo language may appear more on:

- home pages
- event pages
- campaign landings

than on the PDP itself.

The service needs a rule for whether promo evidence is allowed to flow from:

- the exact product URL only
- the same-domain commerce context
- explicitly linked event pages

Without this, promo keyword generation will either be too weak or too risky.

### 19. Need Charset And Encoding Normalization

At least one Korean commerce page fetched successfully but displayed visible mojibake in raw HTML inspection.

That means the collection pipeline cannot assume:

- UTF-8 is always handled correctly
- raw fetched text is immediately safe for prompt input

The service should normalize charset and verify decoded text quality before extraction and generation.

### 20. Need Linked-Document Policy

Some product-specific pages are mostly gateways to:

- manuals
- downloads
- quick-start guides
- support documents

The service needs a rule for whether these count as:

- unsupported inputs
- secondary evidence
- or first-class fallback sources when PDP access is weak

---

## 3. Recommended Product Decisions

1. Separate `generation success` from `quality tier`.
2. Add `risk_flag` and `evidence_level` to every keyword row.
3. Add page classification before keyword generation.
4. Add locale policy before implementation starts.
5. Support `exploration` and `production` generation modes.
6. Define how the service should backfill to 100 when source evidence is thin.
7. Add page-type classification that separates commerce from marketing.
8. Add stock-state handling rules before keyword phrasing is finalized.

---

## 4. Bottom Line

This test suggests the service is feasible, but the requirement set still needs a few product decisions before implementation:

- locale policy
- sparse-page behavior
- evidence grading
- intent dedup policy
- output mode separation

If these are left implicit, the implementation will still generate 100 keywords, but the quality will swing too much by page type.
