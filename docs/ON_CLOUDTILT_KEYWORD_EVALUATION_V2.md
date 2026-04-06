# On Cloudtilt Keyword Evaluation V2

> Evaluated on 2026-04-03 against [KEYWORD_100_CRITERIA.md](C:\Users\NHN\Repo\Keyword_Generator\docs\KEYWORD_100_CRITERIA.md).
> 대상 문서: [ON_CLOUDTILT_KEYWORD_DRAFT_V2.md](C:\Users\NHN\Repo\Keyword_Generator\docs\ON_CLOUDTILT_KEYWORD_DRAFT_V2.md)

---

## 1. Overall Assessment

- Overall grade: `strong conditional pass`
- For requirement-level testing, this draft is good enough.
- For direct ad upload, this draft is still not finished.
- V2 is materially better than V1 because it removed unsupported promo language and reduced the most obvious low-value fillers.

---

## 2. What Improved From V1

V2 made real progress in the right places:

- Unsupported sale-style terms were mostly removed.
- The weakest price/promo claims were tightened.
- The keyword pool is more conservative and less noisy.
- OCR-driven garbage did not leak into the draft.
- Several weak-inference phrases from V1 were replaced by safer comfort, walking, and daily-use language.

Net effect:

- V1 felt like a broad exploration pool.
- V2 feels like a more disciplined service-test pool.

---

## 3. What Passes Well

### Strong sections

- `Brand`
- `Generic / Category`
- `Feature / Attribute`
- `Long-tail`

Why they pass:

- They stay close to visible source evidence.
- They preserve commercial intent.
- They give enough breadth to test category balancing logic.
- They are less likely to produce obviously bad outputs in production.

Best examples:

- `on cloudtilt`
- `on running cloudtilt`
- `on cloudtilt pearl ice`
- `ultra cushioned sneaker`
- `lightweight cushioned sneaker`
- `cloudtec phase sneaker`
- `swiss engineering sneaker`
- `all day comfort sneaker`
- `men's ultra cushioned daily sneaker`
- `men's lightweight city walking sneaker`
- `men's cushioned sneaker for all day wear`

---

## 4. Remaining Gaps

### Gap 1: Still Not An Ad-Ready Output

The draft still does not include:

- `platform`
- `match_type`
- `reason`
- `evidence`
- `score_total`
- `risk_flag`

So it is still a keyword pool, not a final service output.

### Gap 2: Intent Duplication Still Exists

V2 is cleaner than V1, but intent-level duplicates remain.

Examples:

- `men's sneaker`
- `mens sneakers`

Examples:

- `on cloudtilt men`
- `cloudtilt shoes men`
- `cloudtilt mens sneaker`

Examples:

- `comfortable sneakers for long walking`
- `men's sneakers for walking all day`
- `men's lightweight shoes for long walks`

These are acceptable for exploration, but not ideal for production.

### Gap 3: Comparison Terms Are Still Risky

The comparison section is still one of the weakest sections.

Examples:

- `on cloudtilt vs hoka`
- `on cloudtilt vs nike`
- `on cloudtilt vs asics`
- `on running alternative to hoka`

These are not invalid, but they should carry lower confidence and tighter match control.

### Gap 4: A Few Purchase-Intent Phrases Are Still Too Subjective

Examples:

- `best on cloudtilt color`
- `best cushioned sneaker men`
- `best daily sneaker for men`
- `best lifestyle sneaker for men`

These are commercially useful, but not strongly evidenced by the page.
They should be treated as inferred expansions, not direct-evidence terms.

### Gap 5: Season / Occasion Is Still Mostly Derived

Examples:

- `spring men's sneakers`
- `summer lightweight sneakers men`
- `airport walking shoes men`
- `weekend outing sneakers men`

These are plausible, but mostly inferred from product type rather than directly supported.

---

## 5. Section-by-Section Evaluation

| Section | Score | Assessment |
|---|---:|---|
| Brand | 9/10 | Strong and highly relevant |
| Generic / Category | 8/10 | Good for breadth and testing |
| Feature / Attribute | 8/10 | Better grounded than V1 |
| Competitor / Comparison | 6/10 | Still useful, still risky |
| Purchase Intent | 7/10 | Commercially good, but includes subjective superlatives |
| Long-tail | 8/10 | Good balance of specificity and relevance |
| Price / Promotion | 7/10 | Much improved from V1 |
| Season / Occasion | 6/10 | Usable for exploration, weak for final output |
| Problem / Need | 7/10 | Better aligned to comfort/walking use cases |

---

## 6. Keep / Revise / Drop

### Keep

- `on cloudtilt`
- `on running cloudtilt`
- `on cloudtilt pearl ice`
- `men's comfort sneakers`
- `men's walking sneakers`
- `ultra cushioned sneaker`
- `lightweight cushioned sneaker`
- `cloudtec phase sneaker`
- `swiss engineering sneaker`
- `all day comfort sneaker`
- `men's cushioned sneaker for all day wear`
- `men's lifestyle sneaker with soft cushioning`
- `on cloudtilt price`
- `on cloudtilt korea price`
- `comfortable sneakers for long walking`

### Revise

- `mens sneakers`
- `cloudtilt shoes men`
- `cloudtilt mens sneaker`
- `best on cloudtilt color`
- `best cushioned sneaker men`
- `best daily sneaker for men`
- `best lifestyle sneaker for men`
- `airport walking shoes men`
- `weekend outing sneakers men`
- `on running alternative to hoka`

### Drop Or Deprioritize

- `on cloudtilt vs nike`
- `on cloudtilt vs asics`
- `comfort sneaker alternative to hoka`

These may still be useful in exploration mode, but they should not be treated as strong default positives.

---

## 7. Readiness Against The Criteria

### Requirement-Level Readiness

- `100 keywords generated`: pass
- category spread: pass
- source-grounded core coverage: pass

### Quality-Level Readiness

- relevance: pass
- commercial intent: pass
- policy safety: mostly pass
- normalization: partial pass
- evidence grounding: partial pass
- final output shape: fail

---

## 8. Comparison To V1

| Area | V1 | V2 |
|---|---|---|
| Promo discipline | weak | improved |
| OCR noise control | acceptable | improved |
| Intent duplication | moderate issue | still present, but reduced |
| Long-tail quality | mixed | improved |
| Sparse-page suitability | exploratory | better for service testing |
| Final upload readiness | no | still no |

---

## 9. Bottom Line

V2 is the better draft for pre-implementation testing.

- As a service test artifact: `good`
- As a production keyword output: `still incomplete`
- Estimated strong-salvage range: `75-85 keywords out of 100`

If the goal is to pressure-test the service design, V2 is sufficient to reveal the remaining product decisions.
If the goal is final campaign upload, another transformation layer is still required.
