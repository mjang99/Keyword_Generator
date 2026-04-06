# Claude Design Brief

> Prepared on 2026-04-03.
> Purpose: give a design/planning model the minimum high-signal context needed before proposing architecture for the keyword generator service.

---

## 1. What Is Fixed

These points should be treated as fixed unless the user explicitly changes them.

### 1.1 Requirement-Level Constraints

- Input: up to 30 URLs per request
- Processing: async job model
- Output target: at least 100 keywords per URL
- Platforms: Naver SA and Google SA
- OCR: supported as part of content collection
- Execution environment: AWS only
- Cache: identical URL results cached for 7 days

### 1.2 Output Shape Is Fixed

Do not redesign the output schema.

The current downstream expectation is the CSV/JSON row shape already defined in the requirement:

- `url`
- `product_name`
- `category`
- `keyword`
- `naver_match`
- `google_match`
- `reason`
- `quality_warning`

The open design space is upstream generation policy, not output-schema invention.

### 1.3 Decisions Already Made

From the current docs and working decisions:

- `both` means each platform must independently satisfy the minimum keyword count
- negative keywords count toward the platform-level minimum
- same keyword may appear in both platform outputs
- notification is sent once per job when the job finishes
- service shape is standalone service with its own queue/storage components

---

## 2. What Testing Already Proved

The service cannot be designed around a single happy path.

Observed page types from testing:

- `commerce_pdp`
- `image_heavy_commerce_pdp`
- `marketing_only_pdp`
- `product_marketing_page`
- `support_spec_page`
- `document_download_page`
- `promo_heavy_commerce_landing`
- `non_product_page`
- `waiting_page`
- `blocked_page`

Representative evidence is summarized in:

- [SERVICE_TEST_MATRIX.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/SERVICE_TEST_MATRIX.md)
- [KEYWORD_SERVICE_TEST_FINDINGS.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_SERVICE_TEST_FINDINGS.md)

Important examples:

- rich English PDP: On, Dr.Jart
- rich Korean PDP: Aesop, Laneige, Allbirds
- marketing-only pseudo-PDP: Logitech shop page
- product marketing page: Apple product page
- support/spec success: Apple support, Logitech support
- support/spec blocked: Sony support
- promo-heavy commerce landing: Amoremall main/event surface
- marketplace blocked: Smartstore, Coupang
- gated/interstitial: Olive Young

---

## 3. Non-Negotiable Design Implications

Any serious design should account for these.

### 3.1 Page Classification Must Happen Before Generation

The system should classify the fetched input before keyword generation.

At minimum, generation behavior should differ for:

- sellable commerce PDP
- product marketing page
- support/spec page
- promo-heavy landing page
- blocked/waiting/non-product inputs

### 3.2 Evidence Must Be Tiered

Not all generated keywords are equally grounded.

The design should preserve evidence strength such as:

- direct
- derived
- inferred
- weak

Even if the final output schema stays fixed, the internal pipeline should track evidence strength.

### 3.3 Sparse-Page Handling Needs Its Own Policy

The real problem is not generating 100 strings.
The real problem is generating 100 usable keywords without unsupported filler.

The design needs an explicit backfill policy for thin evidence pages.

### 3.4 Promo Guardrails Are Required

Do not generate promo/discount language unless supported by admissible evidence.

This especially affects:

- `sale`
- `discount`
- `coupon`
- `cheap`
- `under budget`

### 3.5 Support Pages Need Explicit Treatment

Support/spec/docs pages are sometimes useful and sometimes blocked.

They cannot be treated as:

- always valid
- always invalid

The design needs a fallback policy for them.

### 3.6 Encoding Normalization Is Required

At least one successful Korean commerce fetch showed visible mojibake.

The collection pipeline should normalize charset before prompt assembly or extraction.

### 3.7 Structured Data Cannot Be Trusted Blindly

Structured data helped in many cases, but some pages also showed:

- buy language with empty pricing
- dynamic price placeholders
- inconsistent vendor/brand fields

The design should merge signals, not trust one source type unconditionally.

---

## 4. Highest-Value Open Decisions

These are the decisions a design doc should make explicit.

### 4.1 Locale Policy

When page language and market language differ:

- should output follow page language?
- should output follow target market language?
- should it be mixed?
- should brand/model stay source-language while generic intent localizes?

### 4.2 Promo Evidence Admissibility

If a PDP has weak promo evidence but the same domain has strong promo/event context:

- is promo evidence allowed from the exact URL only?
- from same-domain linked landings?
- from same-domain commerce context more broadly?

### 4.3 Support/Docs Fallback Policy

When commerce PDP access is weak:

- reject support/docs pages entirely
- use them as secondary evidence
- or elevate them to first-class fallback sources

### 4.4 Count-Fill Policy

When strong evidence runs out before 100:

- expand long-tail first?
- expand problem/need terms?
- allow weaker inferred terms?
- cap strong set and mark weaker tail more aggressively?

### 4.5 Stock-State Policy

Out-of-stock pages can still be valuable.

Need a rule for:

- whether generation proceeds
- how strongly purchase-intent phrasing is allowed
- whether warnings should be set

### 4.6 Category Semantics

Need clarity on:

- minimum per-category expectations, if any
- how negatives interact with category coverage
- how platform-specific category coverage should be validated

---

## 5. Recommended Design Posture

If Claude is producing a design, the safest posture is:

1. Keep the output schema unchanged.
2. Add strong internal classification and evidence tracking.
3. Separate collection quality from generation quality.
4. Design for partial completion and per-URL isolation from the start.
5. Treat sparse/gated/blocked pages as first-class cases, not exceptions.
6. Prefer explicit policy decisions over hidden prompting behavior.

---

## 6. Docs To Read First

Read these before proposing the system design:

- [REQUIREMENTS_KEYWORD_GENERATOR.md](/c:/Users/NHN/Repo/Keyword_Generator/artifacts/REQUIREMENTS_KEYWORD_GENERATOR.md)
- [SERVICE_TEST_MATRIX.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/SERVICE_TEST_MATRIX.md)
- [KEYWORD_SERVICE_TEST_FINDINGS.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/KEYWORD_SERVICE_TEST_FINDINGS.md)
- [OPEN_QUESTIONS.md](/c:/Users/NHN/Repo/Keyword_Generator/docs/OPEN_QUESTIONS.md)

If there is tension between a proposed design and the fixed output requirement, preserve the requirement and change the internal design instead.
