# Crawl4AI Product Extraction Architecture - 2026-04-10

## 1. Decision Summary

- Adopt Crawl4AI only as a browser-backed collection and preprocessing substrate.
- Do not let raw Crawl4AI outputs bypass repo-owned normalization.
- Keep `NormalizedPageSnapshot` as the stable downstream contract for classification, OCR policy, and evidence assembly.
- Prefer a repo-owned intermediate artifact, `collection/preprocessed_page.json`, over widening `HtmlFetchResult` with every Crawl4AI field.
- Promote Crawl4AI outputs into canonical inputs only when they directly improve a known snapshot or extraction field and preserve existing downstream behavior.

## 2. Canonical vs Sidecar Rules

### 2.1 Canonical Inputs Allowed

These Crawl4AI-derived values may become canonical inputs to repo-owned normalization or extraction:

| Crawl4AI output | Canonical status | Allowed consumer | Rule |
| --- | --- | --- | --- |
| Rendered final HTML (`html`) | Yes | `collect_snapshot_from_html()` and product extraction | This is the primary browser-rendered DOM source when Crawl4AI fetch is used. |
| Final URL / resolved URL | Yes | snapshot metadata | Same role as current `HtmlFetchResult.final_url`. |
| Response metadata derivable from crawl result | Yes | snapshot metadata | Limited to stable fetch metadata such as content type, status when derivable, headers when available. |
| `cleaned_html` | Conditional | repo-owned text extraction only | May become the preferred text input for `decoded_text` or product-attribute extraction if benchmarks show material quality gains without classification regressions. It does not replace rendered HTML as the source of truth. |

### 2.2 Must Stay Sidecars

These outputs must not become direct snapshot contract fields in the first migration:

| Crawl4AI output | Required status | Why |
| --- | --- | --- |
| Markdown | Sidecar only | Too lossy and formatting-dependent for canonical snapshot shaping. |
| `fit_markdown` | Sidecar only | Useful for comparison and audit, but too opinionated for core extraction inputs. |
| Screenshot bytes or screenshot metadata | Sidecar only | Useful for debugging and future OCR workflows, but not part of the current snapshot seam. |
| Media inventory | Sidecar only | May help seed image discovery, but repo code must still derive normalized `image_candidates[]`. |
| Console, network, or anti-bot traces | Sidecar only | Operational/debug data, not stable content contract. |

## 3. Preferred Intermediate Artifact

### 3.1 Artifact Choice

The preferred widening target is a repo-owned intermediate artifact:

- Path: `collection/preprocessed_page.json`
- Purpose: persist Crawl4AI preprocessing outputs without forcing them into `HtmlFetchResult` or `NormalizedPageSnapshot`
- Ownership: repo-defined schema, not raw Crawl4AI response passthrough

### 3.2 Preferred Shape

```json
{
  "source": {
    "fetch_backend": "crawl4ai",
    "raw_url": "https://example.com/pdp",
    "final_url": "https://example.com/pdp",
    "http_status": 200,
    "content_type": "text/html"
  },
  "canonical_inputs": {
    "rendered_html": "<html>...</html>",
    "preferred_text_source": "cleaned_html",
    "cleaned_html": "<main>...</main>"
  },
  "sidecars": {
    "markdown": "...",
    "fit_markdown": "...",
    "media_inventory": [],
    "screenshot": {
      "available": true,
      "path": "collection/raw/screenshot.png"
    }
  },
  "decisions": {
    "decoded_text_source": "cleaned_html",
    "image_candidate_seed": "rendered_html_dom"
  }
}
```

### 3.3 Why This Artifact Is Preferred

- It keeps `HtmlFetchResult` narrow and fetch-oriented.
- It lets the repo record multiple preprocessing candidates without immediately promoting them into canonical fields.
- It provides an explicit promotion record, so benchmark-driven changes are reviewable.
- It keeps downstream consumers stable while the extraction strategy evolves.

## 4. Snapshot Promotion Rules

### 4.1 `decoded_text`

- Preferred intermediate source: `cleaned_html`, if benchmarked text quality is better.
- Fallback: text derived from rendered HTML.
- Explicitly disallowed: markdown or `fit_markdown` as the primary source for `decoded_text`.

### 4.2 `visible_text_blocks`

- Must remain repo-extracted.
- Source material may come from rendered HTML and, if justified, cleaned HTML fragments.
- Explicitly disallowed: direct adoption of markdown block boundaries as canonical `visible_text_blocks`.

### 4.3 `structured_data`

- Must remain repo-extracted from rendered HTML / embedded scripts.
- Crawl4AI preprocessing does not replace the repo's structured-data extraction logic.

### 4.4 `image_candidates[]`

- Must remain a repo-owned normalized field.
- Crawl4AI media inventory may be used as a candidate seed or comparison sidecar.
- Directly copying media inventory into snapshot `image_candidates[]` is disallowed.

## 5. Product Extraction Implications

If product-detail extraction is added after preprocessing migration:

- `core` fields should still prefer deterministic selectors and repo-owned parsing over LLM extraction.
- `attributes` may consume `cleaned_html` as an input candidate if benchmarked recall is better.
- `raw_text` should be derived from the chosen canonical text input and stored in the extraction artifact, not sourced from markdown by default.

Recommended extraction artifact:

```json
{
  "core": {
    "name": "iPhone 16",
    "price": 1250000
  },
  "attributes": {
    "shipping": "free",
    "stock": "in stock"
  },
  "raw_text": "...",
  "extraction_meta": {
    "core_source": "selector",
    "attribute_source": "hybrid",
    "decoded_text_source": "cleaned_html"
  }
}
```

## 6. Contract Guidance

### 6.1 `HtmlFetchResult`

Keep `HtmlFetchResult` narrow unless there is a measured need for promotion:

- Keep: `raw_url`, `final_url`, `html`, `content_type`, `http_status`, `fetch_profile_used`, response metadata.
- Avoid adding: markdown, `fit_markdown`, screenshot metadata, media inventory, or extraction-stage fields.

### 6.2 `NormalizedPageSnapshot`

Do not widen `NormalizedPageSnapshot` for raw Crawl4AI artifacts.

Allowed change:

- only indirect changes in how existing fields are computed, for example `decoded_text` preferring cleaned HTML when justified

Disallowed change in this phase:

- adding markdown fields
- adding screenshot fields
- adding raw media inventory fields
- adding Crawl4AI-specific transport fields

## 7. Migration Sequence

1. Use Crawl4AI fetch to obtain rendered HTML.
2. Persist `collection/preprocessed_page.json`.
3. Let repo code choose the canonical text input from that artifact.
4. Build the existing `NormalizedPageSnapshot`.
5. Run classification, OCR policy, and evidence assembly unchanged.
6. Only after benchmark proof, promote additional preprocessing inputs through the intermediate artifact rules above.

## 8. Final Recommendation

- Immediate recommendation: proceed with Crawl4AI as a browser-backed collector only.
- Runtime recommendation: keep `HttpPageFetcher` as the default collector and route only JS-heavy, interaction-heavy, or fetch-failed URLs to the Crawl4AI fallback path.
- Preferred contract strategy: add `collection/preprocessed_page.json`, not a wide fetch result.
- Canonical promotion policy:
  - promote rendered HTML immediately
  - allow `cleaned_html` only as a text-input candidate for fallback experiments, not as the default generation input
  - keep markdown, `fit_markdown`, screenshot data, and media inventory as sidecars until a later benchmark proves a specific downstream need
