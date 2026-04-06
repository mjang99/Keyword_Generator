# Keyword 100 Criteria

> Drafted on 2026-04-03 from the current requirement set and a live product-page scrape of On Cloudtilt.
> Scope: one product URL, Korean search-ad use case, positive keywords first and negative keywords as a separate output.

---

## 1. Recommendation

- Default target: `100 positive keywords per URL per platform`
- When platform is `both`: generate `100 for Naver SA` and `100 for Google SA`
- Generate `negative keywords` separately and do not count them toward the 100
- OCR text is a supporting signal only; page title, structured product data, product description, breadcrumbs, and visible labels are primary signals

---

## 2. Pass Criteria

A keyword should be included only if it passes all of the following:

1. It is clearly tied to the actual product, product family, or a realistic buyer need.
2. It has usable commercial intent for search ads.
3. It is not obviously misleading for the scraped page.
4. It is not a duplicate after normalization.
5. It can be mapped to at least one category and one generation reason.

---

## 3. Normalization Rules

- Lower importance punctuation is removed or normalized: `/`, `|`, `_`, repeated spaces
- English keywords are case-normalized
- Singular/plural and spacing variants are collapsed when intent is identical
- Color-order swaps are collapsed when meaning is identical
- Match-type variants are allowed, but text duplicates are not
- Brand misspellings are excluded unless they are intentionally handled as expansion candidates with clear evidence

---

## 4. Quality Bar

Each positive keyword should be scored on a 5-point rubric:

- `Relevance`: directly grounded in product/page evidence
- `Specificity`: not overly generic for the product
- `Commercial Intent`: likely to be used in shopping/search-ad contexts
- `Coverage Value`: adds a new angle instead of repeating the same idea
- `Policy Safety`: avoids restricted, misleading, or unverifiable claims

Recommended threshold:

- Keep by default if total score is `18/25` or above
- Keep conditionally if `15-17/25` and needed for category coverage
- Drop if `14/25` or below

---

## 5. Category Mix For 100 Positive Keywords

This mix is the recommended default for a single product URL:

| Category | Target Count | Purpose |
|---|---:|---|
| Brand | 10 | Capture direct brand and line intent |
| Generic / Category | 12 | Capture non-brand category demand |
| Feature / Attribute | 18 | Capture material, cushioning, comfort, use-case signals |
| Competitor / Comparison | 8 | Capture substitution and comparison traffic |
| Purchase Intent | 12 | Capture buy, review, ranking, recommendation intent |
| Long-tail | 16 | Capture specific high-intent multi-token queries |
| Price / Promotion | 6 | Capture sale and affordability intent without inventing discounts |
| Season / Occasion | 6 | Capture use context and seasonal demand |
| Problem / Need | 12 | Capture pain-point or desired-outcome demand |
| Total | 100 | Positive keywords only |

Negative keywords:

- Generate `10-30` separately
- Do not include in the positive 100

---

## 6. Evidence Priority

Use source evidence in this order:

1. Structured product data
2. Product title
3. Product description / feature copy
4. Breadcrumbs and category labels
5. Variant metadata such as gender, color, SKU family
6. OCR text from detail or hero images
7. Inferred but defensible shopping intent expansions

Inference rules:

- Strong inference is allowed for obvious category expansions such as `men's sneaker`, `walking shoes`, `daily sneakers`
- Weak inference is not allowed for unsupported claims such as `best running shoe`, `medical foot support`, `waterproof` if the page does not support them

---

## 7. Match-Type Guidance

### Naver SA

- Exact-like / tight terms: brand, product-line, high-intent long-tail
- Expanded terms: generic, feature, problem, seasonal
- Avoid over-expanding short ambiguous head terms without qualifiers

### Google SA

- `exact`: brand-line, SKU-like, strong purchase intent, top long-tail
- `phrase`: generic-plus-feature, comparison, moderate-intent queries
- `broad`: broader category and need-state coverage with clear product relevance

---

## 8. What To Exclude

Drop keywords that are:

- Unsupported by page evidence
- Too broad to be efficient, such as bare `shoes`
- Misleading on use-case, such as `trail running shoes` if not supported
- Pure noise from OCR artifacts
- Non-commercial or non-product informational queries
- Clearly navigational to third-party marketplaces unless that is intentional

---

## 9. Recommended Output Schema

Each keyword row should include:

- `keyword`
- `platform`
- `category`
- `match_type`
- `reason`
- `evidence`
- `score_total`
- `risk_flag`

Recommended `risk_flag` values:

- `none`
- `inferred`
- `weak_evidence`
- `policy_review`

---

## 10. Practical Rule For Weak Pages

When a page is image-heavy and text-poor:

- Keep the 100-keyword target
- Lower OCR influence, not the quality bar
- Lean more on category, purchase-intent, long-tail, and problem/need expansions
- Mark inference-heavy keywords explicitly
- Do not fill count with low-signal OCR garbage

For pages like the current On Cloudtilt PDP, the main usable signals are:

- `Men's Cloudtilt`
- `Pearl | Ice`
- `ultra-cushioned sneaker`
- `lightweight`
- `all-day city adventures`
- `Swiss engineering`
- `CloudTec Phase`
