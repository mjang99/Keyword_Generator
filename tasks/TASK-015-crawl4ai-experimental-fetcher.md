# TASK-015 Crawl4AI Experimental Fetcher

- status: done
- owner: Codex
- priority: high
- depends_on: TASK-014

## Goal

Add an experimental browser-backed fetcher behind the existing `HtmlFetchResult` seam without changing downstream collection, classification, OCR, or evidence contracts.

## Scope

- Implement a new `Crawl4AiPageFetcher` alongside `HttpPageFetcher`.
- Keep `fetch(raw_url) -> HtmlFetchResult` unchanged.
- Keep `HtmlFetchResult` stable for the prototype.
- Wire the new fetcher through the existing runtime fetcher injection path.
- Keep Crawl4AI-specific artifacts such as cleaned HTML, markdown, screenshot presence, and media inventory as sidecar measurements only.
- Keep `src/` focused and do not alter `tests/` semantics beyond new seam coverage if needed later.

## Done When

- The new fetcher can return rendered HTML through the existing result model.
- The prototype fetcher can be injected through the runtime seam.
- The downstream collection pipeline still builds the same snapshot contract from the fetch result.

## Notes

- The goal is a non-invasive prototype, not a permanent contract expansion.
- Any screenshot or media persistence decision belongs to the later adoption gate.
- Prototype implementation landed as `Crawl4AiPageFetcher` behind the existing `HtmlFetchResult` seam.
- Crawl4AI-only outputs currently stay in `last_sidecars` for benchmark/debug use and do not widen the stable snapshot contract.
