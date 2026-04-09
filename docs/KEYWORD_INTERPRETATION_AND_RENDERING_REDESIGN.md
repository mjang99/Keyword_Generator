# Keyword Interpretation And Rendering Redesign

> Prepared on 2026-04-07.
> Scope: internal generation redesign only. External API, job lifecycle, and fixed export schema remain unchanged.

## 1. Problem Statement

Current generation quality issues are no longer dominated by obvious garbage top-up such as placeholder rows or repeated phrases. Those regressions were reduced by shared policy filtering and fallback fail-fast behavior.

The remaining problem is structural:

- category identity is not fixed early enough
- `attributes` mixes incompatible fact types
- phrase-bank generation renders raw facts directly instead of first deciding what the product is
- the generator expands into adjacent category heads (`보습 크림`, `장벽 크림`, `페이스 크림`) even when the product identity is `슬리핑 마스크`
- floor pressure encourages weak commerce and comparison phrases instead of failing cleanly

This is a design problem, not just a validation-gap problem.

## 2. Design Principle

Keyword generation should be split into two stages:

1. `Product Interpretation`
2. `Keyword Rendering`

The interpretation stage decides what the product means. The rendering stage decides how that meaning can be expressed as search queries.

Quality-first rule:

- low-quality rows are dropped even if that causes shortfall
- `FAILED_GENERATION` is preferable to filler or category drift
- `>=100` remains an operational target, not a license to emit weak rows

## 3. Stage 1: Product Interpretation

Stage 1 does not emit keywords. It produces a structured `ProductInterpretation` object.

### 3.1 Required fields

```text
ProductInterpretation
- product_name
- brand
- domain
- canonical_category
- secondary_categories[]
- form_factor[]
- audience[]
- benefits[]
- concerns[]
- usage_context[]
- ingredients[]
- technology[]
- specs[]
- commerce_facts
```

### 3.2 Field semantics

#### `product_name`

The canonical product identity used for exact/brand rendering.

Example:
- `라네즈 워터 슬리핑 마스크`

#### `brand`

Normalized brand identity.

Example:
- `LANEIGE`

#### `domain`

Top-level product domain used for category safety and taxonomy filtering.

Examples:
- `cosmetics`
- `electronics`
- `fashion`

#### `canonical_category`

The single primary product head that all category-sensitive rendering must anchor to.

Examples:
- `슬리핑 마스크`
- `앰플`
- `노트북`

Rules:
- exactly one primary category
- chosen from strongest admitted evidence
- used as the default head for category, benefit, concern, audience, and usage rendering

#### `secondary_categories[]`

Alternative but still product-faithful category heads that can be used only when they do not drift away from `canonical_category`.

Examples:
- `수면 마스크`
- `보습 마스크`

Non-examples:
- `보습 크림`
- `장벽 크림`

Those may describe adjacent skincare demand, but they are not category-faithful if the product is fundamentally a mask.

#### `form_factor[]`

Product format or texture.

Examples:
- `젤 크림 타입`

#### `audience[]`

Who the product is for.

Examples:
- `건성 피부`
- `복합성 피부`

`skin_type` should land here, not inside a generic `attributes` bucket.

#### `benefits[]`

What the product provides.

Examples:
- `수면 중 집중 보습`
- `수분 장벽 강화`

#### `concerns[]`

What problem the user is trying to solve.

Examples:
- `수분 부족`
- `수면 중 피부 당김`

#### `usage_context[]`

When or how the product is used.

Examples:
- `야간 케어`
- `취침 전 마지막 단계`

#### `ingredients[]`

User-recognizable ingredients or composition markers.

Examples:
- `스쿠알란`
- `하이드로 이온화 미네랄 워터`

#### `technology[]`

Brand-owned technology or formulation branding.

Examples:
- `슬립톡스`

These should be handled more conservatively than ordinary ingredients.

#### `specs[]`

Pure numeric or packaging specs.

Examples:
- `70ml`
- `25ml`

Specs are not free-form keyword material. They should be used only where search behavior makes sense.

#### `commerce_facts`

Commercial facts used for purchase rendering and gating.

Examples:
- price
- stock
- official-sellability
- purchase availability

## 4. Why Current `attributes` Must Be Split

The current generator groups all of the following together:

- volume
- ingredient
- brand technology
- texture/form factor
- skin type
- variant

That causes the renderer to treat incompatible facts as interchangeable expansions.

Examples of current bad patterns:

- `라네즈 워터 슬리핑 마스크 건성 복합성 피부 특징`
- `라네즈 워터 슬리핑 마스크 70ml 장점`
- `라네즈 워터 슬리핑 마스크 슬립톡스 사용`

These are awkward because:

- `건성 복합성 피부` is audience, not a spec
- `70ml` is packaging, not a benefit
- `슬립톡스` is branded technology, not a general user-intent phrase

The redesign removes the broad `attributes` concept from rendering logic and replaces it with typed facets.

## 5. Stage 2: Keyword Rendering

Rendering consumes `ProductInterpretation` and emits candidate queries.

This stage should not reinterpret the product. It should only render allowed combinations.

### 5.1 Rendering families

#### Identity

- `제품명`
- `브랜드 + 제품명`
- `브랜드 + canonical_category`

Examples:
- `라네즈 워터 슬리핑 마스크`
- `laneige 라네즈 워터 슬리핑 마스크`
- `laneige 슬리핑 마스크`

#### Category

Only category-faithful heads are allowed.

Examples:
- `슬리핑 마스크`
- `수면 마스크`
- `보습 마스크`

Forbidden examples:
- `보습 크림`
- `장벽 크림`
- `페이스 크림`

Those are category drift unless the interpretation stage explicitly selects them as valid secondary categories.

#### Benefit

Use `canonical_category` as the head and convert benefit language into realistic search form.

Examples:
- `수면 보습 마스크`
- `장벽 강화 마스크`
- `보습 슬리핑 마스크`

Preferred over:
- `슬리핑 마스크 보습`

The current surface form is mechanically compositional. Rendering should prefer natural Korean search order.

#### Concern

Examples:
- `건조한 피부 마스크`
- `수분 부족 케어 마스크`
- `피부 당김 케어 마스크`

#### Audience

Examples:
- `건성 피부 슬리핑 마스크`
- `복합성 피부 마스크`

Preferred over:
- `건성 복합성 피부 특징`

#### Usage Context

Examples:
- `야간 케어 마스크`
- `취침 전 마스크`
- `수면팩 루틴`

Preferred over:
- `취침 전 마지막 단계 도포 비교`

#### Ingredient

Examples:
- `스쿠알란 슬리핑 마스크`
- `스쿠알란 보습 마스크`

Ingredient rendering is allowed only when the ingredient is commonly user-facing.

#### Technology

Technology terms should be conservative and evidence-gated.

Examples:
- `슬립톡스 슬리핑 마스크`

Only render when:
- direct evidence is strong
- the term appears user-facing on page
- it survives quality review

#### Specs

Use only in narrow contexts.

Examples:
- `라네즈 워터 슬리핑 마스크 70ml`
- `라네즈 워터 슬리핑 마스크 25ml`

Avoid:
- `70ml 장점`
- raw price literals
- free combination with benefits or audience

#### Purchase

Examples:
- `라네즈 워터 슬리핑 마스크 온라인 구매`
- `라네즈 워터 슬리핑 마스크 재고 확인`
- `라네즈 워터 슬리핑 마스크 공식몰 구매`

### 5.2 Forbidden rendering patterns

The renderer must never emit:

- category drift from adjacent but unproven heads
- raw usage instructions copied as search queries
- weak comparison placeholders
- low-information commerce phrases
- direct raw price numbers as standalone demand proxies

Examples to reject:

- `보습 크림`
- `장벽 크림`
- `옵션 비교`
- `라인 비교`
- `가성비`
- `38000`
- `취침 전 마지막 단계 도포 비교`

## 6. Responsibility Split

### Interpretation stage

Best implemented as a structured decision layer.

Responsibility:
- normalize facts
- choose canonical category
- split facts into typed facets
- decide which facets are admissible for rendering

Execution model:
- deterministic-first extraction
- Bedrock allowed as classifier or structured interpreter when evidence is ambiguous

### Rendering stage

Best implemented as candidate generation plus strict filtering.

Responsibility:
- render allowed facet combinations
- generate multiple natural surface forms
- respect product domain and category safety

Execution model:
- Bedrock is suitable for high-quality surface-form generation
- deterministic code should own template safety, hard exclusions, and floor validation

## 7. Quality-First Floor Policy

This redesign keeps the current external contract, but the internal priority order changes.

Priority order:

1. product-faithful interpretation
2. human-acceptable keyword quality
3. category coverage
4. platform floor

Operational rule:

- if a candidate is weak, awkward, or category-drifting, drop it
- if the remaining set is below floor, emit shortfall
- do not backfill with weak templates just to hit `100`

## 8. Migration Plan

### Phase 1

Introduce `ProductInterpretation` as an internal object and populate it from current evidence facts.

This can be done without changing the external API or export format.

### Phase 2

Change deterministic phrase-bank generation to consume typed facets instead of broad `attributes` and generic category expansions.

First targets:
- `generic_category`
- `benefit_price`
- `competitor_comparison`
- `long_tail`

### Phase 3

Move Bedrock generation prompts from raw evidence facts to the structured interpretation object.

Bedrock should generate from:
- canonical category
- allowed secondary categories
- typed benefits
- typed concerns
- typed audience
- typed usage context

### Phase 4

Tighten policy and evaluator around category drift and weak commerce phrasing.

New diagnostics should explicitly count:
- category drift rows
- weak comparison rows
- raw price rows
- awkward usage-instruction rows

## 9. Acceptance Criteria

The redesign is working when:

- a `슬리핑 마스크` product no longer expands into generic `크림` heads unless explicitly admitted
- typed audience rendering produces phrases like `건성 피부 슬리핑 마스크`
- typed benefit rendering produces phrases like `수면 보습 마스크`
- raw fact copying such as `취침 전 마지막 단계 도포 비교` disappears
- low-quality rows are dropped even when that causes shortfall

## 10. Immediate Next Step

Before changing Bedrock prompts or the full allocator, implement the interpretation split locally in deterministic generation for cosmetics fixtures first.

The first concrete code change should:

- replace the broad `attributes` bucket with typed facet buckets
- lock `canonical_category`
- stop `generic_category` from expanding into adjacent heads without explicit admission
