# Service Test Matrix

> Drafted on 2026-04-03.
> Goal: broaden pre-implementation testing across language, page richness, and failure modes.

---

## 1. Matrix

| Case ID | URL Type | Language | Fetch Result | Observed Shape | Service Meaning |
|---|---|---|---|---|---|
| T1 | On Cloudtilt PDP | English | success | rich product detail page with structured data and feature copy | best-case PDP |
| T2 | On category page | English | success | CSR shell / non-product page | unsupported input or low-value input |
| T3 | Olive Young lotion PDP | Korean | direct fetch gated, search snippet usable | product detail with Korean title, promo labels, price, shipping, but limited direct raw HTML access | Korean PDP with acquisition friction |
| T4 | Olive Young mask PDP | Korean | waiting page | gated / queue page | anti-bot or interstitial handling needed |
| T5 | Coupang shampoo PDP | Korean | access denied | blocked | blocked_page handling needed |
| T6 | Naver Smartstore PDP | Korean | error page | blocked / unstable access | blocked_page handling needed |
| T7 | Aesop barrier cream PDP | Korean | success | direct D2C PDP with title, price, tabs, structured product data, and stock state | Korean commerce PDP |
| T8 | Logitech MX Keys S page | Korean | success | `shop` URL and buy-oriented copy, but variant status is `marketingonly` and pricing is effectively empty | marketing-only pseudo-PDP |
| T9 | Apple AirPods Pro page | Korean | success | product marketing page with dynamic pricing placeholders, deep feature copy, and bag/store chrome | product marketing page, not clean commerce PDP |
| T10 | Dr.Jart hydro mask PDP | English | success | rich beauty PDP with product JSON, reviews, claims, price, and stock state | claim-heavy commerce PDP |
| T11 | Allbirds runner slip-on PDP | Korean | success | Shopify PDP with price, sizes, product object, and image-heavy footwear detail | Korean commerce PDP with strong metadata and lighter copy |
| T12 | Laneige retinol PDP | Korean | success | Korean beauty PDP with price, award badges, review volume, and hashtag-style claim language | Korean claim-heavy commerce PDP |
| T13 | Apple AirPods Pro tech specs page | Korean | success | support/spec page with product-specific technical details, dimensions, battery, compatibility, and legal product info | support/spec page, not commerce PDP |
| T14 | Sony WH-1000XM5 support page | Korean | access denied | blocked support page | support-page blocking case |
| T15 | Apple AirPods docs/downloads page | Korean | success | asset-heavy support page centered on manuals, downloads, and linked documents | document/download-heavy product support page |
| T16 | Logitech MX Keys S support specs page | Korean | success | successful support article with product specs outside the commerce domain | support-source success case |
| T17 | Amoremall home/event surface | Korean | success | promo-heavy commerce landing with benefits and event links, but weak direct product grounding and visible encoding noise in raw fetch | promo-rich commerce landing, not PDP |

---

## 2. Case Notes

### T1: On Cloudtilt PDP

- strongest direct evidence among tested pages
- enough text to generate a disciplined 100-keyword pool
- useful for testing:
  - structured-data extraction
  - OCR as secondary signal
  - long-tail expansion

### T2: On category page

- technically fetchable, but not a valid product detail page
- useful for testing:
  - URL validation
  - non-product-page detection
  - early fail / skip behavior

### T3: Olive Young lotion PDP

- Korean product page content is visible in search results
- direct raw fetch appears gated or inconsistent
- useful for testing:
  - Korean keyword generation
  - mixed evidence acquisition
  - promotion and merchandising language control

### T4: Olive Young waiting page

- direct fetch returns a waiting/interstitial page
- useful for testing:
  - interstitial detection
  - retry policy
  - browser-based acquisition fallback

### T5: Coupang access denied

- clean blocked case
- useful for testing:
  - blocked_page classification
  - per-URL failure isolation
  - user-facing reason messaging

### T6: Smartstore error page

- another blocked / unstable marketplace case
- useful for testing:
  - marketplace-specific failure handling
  - avoiding wasted retries on known hostile sources

### T7: Aesop barrier cream PDP

- strongest Korean direct-fetch commerce PDP so far
- includes title, price, tabs, product group JSON, and explicit `OutOfStock`
- useful for testing:
  - Korean keyword generation from first-party PDP HTML
  - stock-state handling
  - long-form tab extraction

### T8: Logitech MX Keys S page

- looks like a normal PDP at first glance:
  - `shop` URL
  - buy-oriented title/description
  - structured offer fields
- but variant payload marks the item as `marketingonly` and pricing is empty / zeroed
- useful for testing:
  - sellable vs non-sellable PDP classification
  - distrust of misleading `buy` language
  - structured-data consistency checks

### T9: Apple AirPods Pro page

- clearly product-specific and rich in feature copy
- includes bag/store affordances and dynamic pricing placeholders, but not a clean embedded commerce offer object
- useful for testing:
  - product-marketing-page detection
  - price placeholder detection
  - deciding whether non-commerce product pages are allowed inputs

### T10: Dr.Jart hydro mask PDP

- very strong English beauty PDP
- includes price, stock state, reviews, claims, ingredients, usage, and many product images
- useful for testing:
  - claim-heavy beauty extraction
  - review/rating signal handling
  - long-description compression

### T11: Allbirds runner slip-on PDP

- direct-fetch Korean Shopify PDP succeeded on retry
- strong commerce metadata:
  - product object
  - size variants
  - price
  - SKU
- useful for testing:
  - Shopify-specific extraction
  - image-heavy footwear pages with lighter descriptive copy
  - variant normalization

### T12: Laneige retinol PDP

- strong Korean beauty commerce case
- includes:
  - price
  - awards
  - review volume
  - hashtag-like problem/benefit language
- useful for testing:
  - Korean beauty keyword generation
  - review/award claim normalization
  - promo-adjacent commercial phrasing without actual discount claims

### T13: Apple AirPods Pro tech specs page

- clearly product-specific, but this is a support/spec page rather than a commerce page
- contains dense structured technical detail:
  - battery
  - dimensions
  - compatibility
  - legal product info
- useful for testing:
  - support/spec-page detection
  - whether non-commerce product support pages are valid fallback evidence
  - technical-term compression

### T14: Sony WH-1000XM5 support page

- support-page fetch returned `Access Denied`
- useful for testing:
  - support-page blocking as a distinct failure mode
  - whether support sources should be retried differently from marketplace blocks

### T15: Apple AirPods docs/downloads page

- strongly centered on manuals and downloads rather than inline product selling copy
- useful for testing:
  - document/download-heavy page detection
  - whether linked-document pages should count as sufficient evidence
  - support content extraction without commerce fields

### T16: Logitech MX Keys S support specs page

- support source succeeded even though another support source failed
- useful for testing:
  - per-domain support-source behavior
  - product-spec extraction outside commerce PDPs
  - avoiding over-generalization from one blocked support brand

### T17: Amoremall home/event surface

- direct fetch succeeded and exposed many commerce-promo signals:
  - event links
  - coupon/benefit labels
  - promo-forward navigation
- but it is not a product detail page, and raw fetch showed visible encoding noise
- useful for testing:
  - promo-rich landing-page detection
  - source-of-promo policy
  - charset/encoding normalization

---

## 3. What This Matrix Proves
The service must be designed for more than one happy path.

The service must be designed for more than one “happy path”.

At minimum, it needs to handle:

- rich commerce PDPs
- image-heavy commerce PDPs
- Korean-language pages
- English-language pages
- category/non-product pages
- waiting/interstitial pages
- access-denied pages
- marketplace-blocked pages
- marketing-only pseudo-PDPs
- product marketing pages that look product-specific but are not clean commerce pages
- support/spec pages
- document/download-heavy support pages
- blocked support pages
- promo-heavy commerce landing pages

---

## 4. Product Decisions Now Clearly Required

1. How to detect and reject non-product pages early.
2. How to classify waiting pages vs true blocked pages.
3. Whether search-snippet-derived evidence is allowed as fallback.
4. How Korean output should behave when direct page acquisition is weak.
5. How to distinguish:
   - sellable commerce PDP
   - marketing-only PDP
   - product marketing page
   - support/spec page
   - promo-heavy landing page
6. How stock state should affect generation:
   - `InStock`
   - `OutOfStock`
   - unknown / dynamic
7. How retries differ between:
   - temporary queue pages
   - hard access denied
   - marketplace anti-bot failures
   - blocked support pages
8. Whether promo signals from home/event/landing pages are admissible when PDP promo evidence is weak.
9. How to normalize encoding when fetched HTML contains visible mojibake or charset mismatch.

---

## 5. Recommended Next Internal Test Set

Covered now:

1. Korean PDP with direct fetch success.
2. English PDP with direct fetch success.
3. Korean blocked marketplace PDP.
4. One non-product page.
5. One image-heavy footwear PDP.
6. One product marketing page.
7. One marketing-only pseudo-PDP.
8. One support/spec page.
9. One blocked support page.
10. One document/download-heavy support page.
11. One promo-heavy commerce landing page.

Still worth adding:

1. One Korean PDP with direct fetch success and strong explicit promo labels.
2. One more multilingual page where page language and target market language diverge.
3. One direct-fetch success case from a Korean marketplace or brand-hosted marketplace.
