# On Cloudtilt Keyword Evaluation

> Evaluated on 2026-04-03 against [KEYWORD_100_CRITERIA.md](C:\Users\NHN\Repo\Keyword_Generator\docs\KEYWORD_100_CRITERIA.md).
> 대상 문서: [ON_CLOUDTILT_KEYWORD_DRAFT.md](C:\Users\NHN\Repo\Keyword_Generator\docs\ON_CLOUDTILT_KEYWORD_DRAFT.md)

---

## 1. Overall Assessment

- Overall grade: `conditional pass`
- Current draft is useful as a first-pass keyword pool.
- Current draft is **not yet ready for direct ad upload**.
- The pool covers the required breadth well, but a non-trivial share of keywords are too inferred, too generic, or missing operational metadata.

---

## 2. What Passes Well

Strong points in the current draft:

- Category coverage is good. The draft spans brand, generic, feature, comparison, purchase-intent, long-tail, price/promo, season/occasion, and problem/need.
- The core evidence is used well: `Cloudtilt`, `men`, `Pearl | Ice`, `ultra-cushioned`, `lightweight`, `all-day`, `Swiss engineering`, `CloudTec Phase`.
- Brand and product-line terms are strong.
- A meaningful long-tail layer exists instead of relying only on short head terms.
- The draft correctly avoided obviously unsupported claims like `waterproof`, `orthopedic`, and `trail`.

Best-performing sections:

- `Brand`
- `Generic / Category`
- `Feature / Attribute`
- The top half of `Long-tail`

---

## 3. Main Gaps

### Gap 1: Not Yet an Ad-Ready Output

The criteria document expects keyword rows to eventually include:

- `platform`
- `match_type`
- `reason`
- `evidence`
- `score_total`
- `risk_flag`

The current draft is only a text pool, so it is not yet in the shape the requirement set ultimately wants.

### Gap 2: Some Terms Are Over-Inferred

Several keywords go beyond what the page strongly supports.

Examples:

- `premium foam sneaker`
- `shock absorbing sneakers men`
- `smooth transition sneaker`
- `men's everyday sneaker for office casual`
- `men's lightweight sneaker for weekend travel`
- `sneakers for tired feet men`
- `men shoes for all day standing`

These are not necessarily wrong, but they are inference-heavy and should be marked `inferred` or dropped.

### Gap 3: Price / Promotion Section Is Weak

This section currently violates the spirit of the criteria in places.

Weak examples:

- `on cloudtilt sale`
- `comfortable premium sneaker sale`
- `best premium sneaker under budget`

Reason:

- The scraped page did not provide sale evidence.
- `under budget` is especially weak because it introduces a value judgment not grounded in the page.

### Gap 4: Comparison Terms Need Tighter Control

Comparison keywords are acceptable, but several are broad enough to waste spend unless tightly matched.

Examples:

- `cloudtilt vs hoka`
- `cloudtilt vs nike`
- `cloudtilt vs asics`
- `best alternative to hoka sneakers`

These should be lower-priority, tightly matched, and explicitly labeled as inferred comparison traffic.

### Gap 5: A Few Intent Duplicates Should Be Collapsed

The draft has some near-duplicate intent clusters that should be merged under normalization rules.

Examples:

- `men's sneaker`
- `mens sneakers`

Examples:

- `comfortable sneakers for long walking`
- `men sneakers for walking all day`
- `men's comfortable sneaker for long walks`

Examples:

- `on cloudtilt mens shoes`
- `cloudtilt shoes men`

These are not literal duplicates, but several collapse into the same commercial intent.

---

## 4. Section-by-Section Evaluation

| Section | Score | Assessment |
|---|---:|---|
| Brand | 9/10 | Strong, high relevance, high commercial value |
| Generic / Category | 8/10 | Useful, but a couple are broad |
| Feature / Attribute | 7/10 | Good coverage, but several claims are inference-heavy |
| Competitor / Comparison | 6/10 | Valid category, but should be tightened and deprioritized |
| Purchase Intent | 8/10 | Commercially useful overall |
| Long-tail | 7/10 | Strong base, but a few weak-inference phrases |
| Price / Promotion | 4/10 | Weakest section, needs rewrite |
| Season / Occasion | 6/10 | Some useful context, some speculative |
| Problem / Need | 6/10 | Good direction, but several phrases need evidence control |

---

## 5. Keep / Revise / Drop

### Keep

These are strong as-is:

- `on cloudtilt`
- `on running cloudtilt`
- `on cloudtilt pearl ice`
- `ultra cushioned sneaker`
- `lightweight cushioned sneaker`
- `cloudtec phase shoes`
- `swiss engineering sneakers`
- `all day comfort sneaker`
- `men's ultra cushioned daily sneaker`
- `men's lightweight city walking sneaker`
- `buy on cloudtilt`
- `on cloudtilt review`
- `on cloudtilt recommendation`
- `on cloudtilt price`

### Revise

These are usable after tightening or adding `risk_flag=inferred`:

- `premium foam sneaker`
- `shock absorbing sneakers men`
- `smooth transition sneaker`
- `best on running sneaker`
- `best cushioned sneaker men`
- `men's sneaker for city commute`
- `men's travel sneaker with cushioning`
- `airport sneakers men`
- `sneakers for tired feet men`
- `men shoes for all day standing`

### Drop Or Replace

These are the weakest:

- `on cloudtilt sale`
- `comfortable premium sneaker sale`
- `best premium sneaker under budget`
- `best alternative to hoka sneakers`
- `men's everyday sneaker for office casual`
- `men's lightweight sneaker for weekend travel`

---

## 6. Draft Readiness Against The Criteria

### Passes

- Relevance: mostly pass
- Commercial intent: mostly pass
- Coverage value: pass
- Policy safety: mostly pass

### Fails Or Needs More Work

- Normalization: partial fail
- Evidence grounding: partial fail
- Output schema completeness: fail
- Price/promotion discipline: fail

---

## 7. Recommended Next Step

Before this draft is treated as a real generation target, do the following:

1. Remove or rewrite weak price/promotion terms.
2. Collapse duplicate-intent phrases.
3. Mark inference-heavy keywords with `risk_flag=inferred`.
4. Assign `platform`, `match_type`, `reason`, and `evidence` per keyword.
5. Re-score each keyword and keep only rows at or above the acceptance threshold.

---

## 8. Bottom Line

The current 100-keyword draft is a good exploration artifact, not yet a production artifact.

- As a discovery draft: `good`
- As a directly usable ad-keyword output: `not ready yet`
- Estimated salvage rate after cleanup: `around 65-75 strong positives out of 100`, with the remaining slots better replaced by tighter long-tail and need-state terms
