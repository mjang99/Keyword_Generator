from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable

from src.collection import (
    build_snapshot_from_fixture,
    classify_snapshot,
    collect_snapshot_from_html,
    collect_snapshot_from_preprocessed_html,
)
from src.evidence import build_evidence_pack
from src.ocr import OcrRunResult, OcrRunner, run_ocr_policy

from .models import LocalResolvedFailure, LocalResolvedSuccess

if TYPE_CHECKING:
    from src.collection.models import NormalizedPageSnapshot, PageClassification


@dataclass(slots=True)
class FixturePipeline:
    fixture_loader: Callable[[str], dict]
    url_to_fixture: dict[str, str | dict]

    def resolve(self, raw_url: str) -> LocalResolvedSuccess | LocalResolvedFailure:
        if raw_url not in self.url_to_fixture:
            return LocalResolvedFailure(
                failure_code="collection_fixture_missing",
                failure_detail=f"no fixture configured for {raw_url}",
                failure_reason_hints=["fixture mapping is missing for this URL in the local collection runtime"],
            )
        source = self.url_to_fixture[raw_url]
        payload = self.fixture_loader(source) if isinstance(source, str) else dict(source)
        payload.setdefault("raw_url", raw_url)
        payload.setdefault("canonical_url", raw_url)

        snapshot = build_snapshot_from_fixture(payload)
        classification = classify_snapshot(snapshot)
        ocr_result = run_ocr_policy(snapshot)
        if not classification.supported_for_generation:
            return LocalResolvedFailure(
                failure_code=classification.failure_code_candidate or "unsupported_page",
                failure_detail=f"{classification.page_class} is unsupported for generation",
                failure_reason_hints=_classification_failure_hints(snapshot, classification),
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
                ocr_result=asdict(ocr_result),
            )
        return LocalResolvedSuccess(
            evidence_pack=build_evidence_pack(snapshot, classification, ocr_result),
            snapshot=asdict(snapshot),
            classification=asdict(classification),
            ocr_result=asdict(ocr_result),
        )


@dataclass(slots=True)
class HtmlCollectionPipeline:
    fetcher: Callable[[str], Any] | Any
    fallback_fetcher: Callable[[str], Any] | Any | None = None
    ocr_runner: OcrRunner | None = None
    allow_ocr_for_unsupported: bool = False
    fallback_min_usable_text_chars: int = 1200

    def resolve(self, raw_url: str) -> LocalResolvedSuccess | LocalResolvedFailure:
        try:
            fetch_result = self.fetcher.fetch(raw_url)
        except Exception as error:
            if self.fallback_fetcher is not None:
                return self._resolve_via_fallback(
                    raw_url=raw_url,
                    fallback_reason="baseline_fetch_failed",
                    baseline_error=error,
                )
            return LocalResolvedFailure(
                failure_code="collection_fetch_failed",
                failure_detail=str(error),
                failure_reason_hints=_fetch_failure_hints(raw_url=raw_url, fetcher=self.fetcher, error=error),
            )

        try:
            snapshot = collect_snapshot_from_html(fetch_result)
        except Exception as error:
            return LocalResolvedFailure(
                failure_code="collection_snapshot_failed",
                failure_detail=str(error),
                failure_reason_hints=_snapshot_failure_hints(fetch_result=fetch_result, error=error),
            )

        classification = classify_snapshot(snapshot)
        use_fallback, fallback_reason = self._should_use_crawl4ai_fallback(snapshot, classification)
        if use_fallback and self.fallback_fetcher is not None and fallback_reason:
            return self._resolve_via_fallback(
                raw_url=raw_url,
                fallback_reason=fallback_reason,
                baseline_snapshot=snapshot,
                baseline_classification=classification,
            )
        try:
            ocr_result = self._resolve_ocr(snapshot, classification)
        except Exception as error:
            return LocalResolvedFailure(
                failure_code="collection_ocr_failed",
                failure_detail=str(error),
                failure_reason_hints=_ocr_failure_hints(error=error),
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
            )
        if not classification.supported_for_generation:
            return LocalResolvedFailure(
                failure_code=classification.failure_code_candidate or "unsupported_page",
                failure_detail=f"{classification.page_class} is unsupported for generation",
                failure_reason_hints=_classification_failure_hints(snapshot, classification),
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
                ocr_result=asdict(ocr_result),
            )
        return LocalResolvedSuccess(
            evidence_pack=build_evidence_pack(snapshot, classification, ocr_result),
            snapshot=asdict(snapshot),
            classification=asdict(classification),
            ocr_result=asdict(ocr_result),
        )

    def _resolve_via_fallback(
        self,
        *,
        raw_url: str,
        fallback_reason: str,
        baseline_snapshot: "NormalizedPageSnapshot" | None = None,
        baseline_classification: "PageClassification" | None = None,
        baseline_error: Exception | None = None,
    ) -> LocalResolvedSuccess | LocalResolvedFailure:
        assert self.fallback_fetcher is not None
        try:
            fetch_result = self.fallback_fetcher.fetch(raw_url)
            sidecars = dict(getattr(self.fallback_fetcher, "last_sidecars", {}) or {})
        except Exception as error:
            hints = _fetch_failure_hints(raw_url=raw_url, fetcher=self.fallback_fetcher, error=error)
            hints.append(f"Crawl4AI fallback was triggered because `{fallback_reason}`")
            if baseline_error is not None:
                hints.extend(_fetch_failure_hints(raw_url=raw_url, fetcher=self.fetcher, error=baseline_error))
            return LocalResolvedFailure(
                failure_code="collection_fetch_failed",
                failure_detail=_fallback_failure_detail(
                    fallback_reason=fallback_reason,
                    baseline_snapshot=baseline_snapshot,
                    baseline_classification=baseline_classification,
                    baseline_error=baseline_error,
                    fallback_error=error,
                ),
                failure_reason_hints=_dedupe_hints(hints),
                page_class=baseline_classification.page_class if baseline_classification is not None else None,
                quality_warning=baseline_snapshot.quality_warning if baseline_snapshot is not None else None,
                snapshot=asdict(baseline_snapshot) if baseline_snapshot is not None else None,
                classification=asdict(baseline_classification) if baseline_classification is not None else None,
            )

        try:
            snapshot = collect_snapshot_from_preprocessed_html(
                fetch_result,
                sidecars=sidecars,
                preferred_source="cleaned_html",
                fallback_reason=fallback_reason,
                fallback_used=True,
            )
        except Exception as error:
            return LocalResolvedFailure(
                failure_code="collection_snapshot_failed",
                failure_detail=f"Crawl4AI fallback snapshot normalization failed after `{fallback_reason}`: {error}",
                failure_reason_hints=_dedupe_hints(
                    [
                        *_snapshot_failure_hints(fetch_result=fetch_result, error=error),
                        f"Crawl4AI fallback was triggered because `{fallback_reason}`",
                    ]
                ),
                page_class=baseline_classification.page_class if baseline_classification is not None else None,
                quality_warning=baseline_snapshot.quality_warning if baseline_snapshot is not None else None,
                snapshot=asdict(baseline_snapshot) if baseline_snapshot is not None else None,
                classification=asdict(baseline_classification) if baseline_classification is not None else None,
            )

        classification = classify_snapshot(snapshot)
        try:
            ocr_result = self._resolve_ocr(snapshot, classification)
        except Exception as error:
            return LocalResolvedFailure(
                failure_code="collection_ocr_failed",
                failure_detail=str(error),
                failure_reason_hints=_dedupe_hints(
                    [
                        *_ocr_failure_hints(error=error),
                        f"Crawl4AI fallback was triggered because `{fallback_reason}`",
                    ]
                ),
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
            )
        if not classification.supported_for_generation:
            return LocalResolvedFailure(
                failure_code=classification.failure_code_candidate or "unsupported_page",
                failure_detail=f"{classification.page_class} is unsupported for generation after Crawl4AI fallback",
                failure_reason_hints=_dedupe_hints(
                    [
                        *_classification_failure_hints(snapshot, classification),
                        f"Crawl4AI fallback was triggered because `{fallback_reason}`",
                    ]
                ),
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
                ocr_result=asdict(ocr_result),
            )
        return LocalResolvedSuccess(
            evidence_pack=build_evidence_pack(snapshot, classification, ocr_result),
            snapshot=asdict(snapshot),
            classification=asdict(classification),
            ocr_result=asdict(ocr_result),
        )

    def _resolve_ocr(self, snapshot, classification):
        ocr_result = run_ocr_policy(snapshot)
        if self.ocr_runner is None:
            return ocr_result
        if not classification.supported_for_generation and not self.allow_ocr_for_unsupported:
            return ocr_result
        if snapshot.ocr_text_blocks:
            return ocr_result
        if not ocr_result.ranked_image_candidates:
            return ocr_result
        if "ocr_not_required" in ocr_result.trigger_reasons:
            return ocr_result

        runner_output = self.ocr_runner.run(snapshot, ocr_result.ranked_image_candidates)
        if isinstance(runner_output, OcrRunResult):
            snapshot.ocr_text_blocks = list(runner_output.blocks)
            snapshot.ocr_image_results = list(runner_output.image_results)
        else:
            snapshot.ocr_text_blocks = list(runner_output)
            snapshot.ocr_image_results = []
        if not snapshot.ocr_text_blocks:
            return run_ocr_policy(snapshot)
        return run_ocr_policy(snapshot)

    def _should_use_crawl4ai_fallback(
        self,
        snapshot: "NormalizedPageSnapshot",
        classification: "PageClassification",
    ) -> tuple[bool, str | None]:
        if snapshot.fetch_profile_used == "crawl4ai_render":
            return False, None
        if classification.page_class in {"blocked_page", "waiting_page"}:
            return True, "blocked_or_waiting_surface"
        if not classification.supported_for_generation and classification.page_class in {
            "non_product_page",
            "promo_heavy_commerce_landing",
        }:
            if not snapshot.structured_data and not snapshot.price_signals and not snapshot.buy_signals:
                return True, "client_side_render_suspected"
            return True, "thin_product_evidence"
        usable_text_chars = int(snapshot.usable_text_chars or 0)
        if (
            usable_text_chars < self.fallback_min_usable_text_chars
            and not snapshot.structured_data
            and (not snapshot.price_signals or not snapshot.buy_signals)
        ):
            return True, "thin_product_evidence"
        return False, None


def _dedupe_hints(hints: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for hint in hints:
        normalized = hint.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _fetch_failure_hints(*, raw_url: str, fetcher: Any, error: Exception) -> list[str]:
    text = str(error).lower()
    hints: list[str] = []
    fetcher_name = type(fetcher).__name__.lower()

    if "timed out" in text or "timeout" in text:
        hints.append("page response or browser render exceeded the collector timeout")
    if any(token in text for token in ("forbidden", "access denied", "captcha", "challenge", "blocked")):
        hints.append("origin likely returned a blocker, WAF challenge, or anti-bot interstitial")
    if any(token in text for token in ("ssl", "tls", "certificate")):
        hints.append("TLS or certificate negotiation failed before HTML could be collected")
    if any(token in text for token in ("getaddrinfo", "name or service not known", "temporary failure in name resolution", "dns")):
        hints.append("DNS resolution failed for the target host")
    if any(token in text for token in ("connection refused", "connection reset", "remote end closed", "reset by peer")):
        hints.append("origin connection failed before the collector could read the page")
    if "empty html" in text:
        hints.append("browser render returned no usable DOM; a cookie wall, JS app shell, or bot interstitial is likely")
    if "no module named 'crawl4ai'" in text or "pydantic_core" in text:
        hints.append("Crawl4AI runtime environment is misconfigured or missing binary dependencies")
    if "crawl4ai" in fetcher_name:
        hints.append("this URL is on the browser-render fallback path; Playwright or the browser runtime may be the failing dependency")
    else:
        hints.append("if the page depends on client-side rendering, retry it through the Crawl4AI fallback collector")
    return _dedupe_hints(hints)


def _snapshot_failure_hints(*, fetch_result: Any, error: Exception) -> list[str]:
    del error
    hints: list[str] = [
        "collected HTML could not be normalized into snapshot fields",
    ]
    if getattr(fetch_result, "mojibake_flags", None):
        hints.append("the response shows charset or mojibake flags, so decoded text may be corrupted")
    if getattr(fetch_result, "http_status", 200) and int(getattr(fetch_result, "http_status", 200)) >= 400:
        hints.append("the collector received an HTTP error page instead of a normal product page")
    return _dedupe_hints(hints)


def _ocr_failure_hints(*, error: Exception) -> list[str]:
    text = str(error).lower()
    hints: list[str] = ["OCR execution failed after collection completed"]
    if "timeout" in text:
        hints.append("the OCR image sweep exceeded the configured timeout")
    if any(token in text for token in ("paddle", "ocr", "subprocess")):
        hints.append("the PaddleOCR subprocess or OCR runtime dependency likely failed")
    if any(token in text for token in ("not found", "no such file", "cannot find")):
        hints.append("the configured OCR python runtime or dependency path may be missing")
    return _dedupe_hints(hints)


def _classification_failure_hints(snapshot: "NormalizedPageSnapshot", classification: "PageClassification") -> list[str]:
    page_class = classification.page_class
    hints: list[str] = []
    if page_class == "blocked_page":
        hints.append("the collector reached a blocker or challenge page instead of product content")
        hints.append("retry through the Crawl4AI fallback profile only if this domain is known to require browser rendering")
    elif page_class == "waiting_page":
        hints.append("the page is behind a queue or waiting-room interstitial")
        hints.append("retry later or with a session-authenticated fetch if that path is allowed")
    elif page_class == "promo_heavy_commerce_landing":
        hints.append("single-product identity was not proven strongly enough from product, price, and buy-intent signals")
        hints.append("the URL looks closer to a promo landing page or listing than a single PDP")
    elif page_class == "non_product_page":
        hints.append("product-name, price, or buy-intent signals were too weak for a sellable PDP")
    else:
        hints.append(f"{page_class} is currently outside the supported generation path")
    if not snapshot.structured_data:
        hints.append("no structured product data was admitted on this page")
    if not snapshot.buy_signals:
        hints.append("buy-intent signals were missing from the collected page text")
    return _dedupe_hints(hints)


def _fallback_failure_detail(
    *,
    fallback_reason: str,
    baseline_snapshot: "NormalizedPageSnapshot" | None,
    baseline_classification: "PageClassification" | None,
    baseline_error: Exception | None,
    fallback_error: Exception,
) -> str:
    if baseline_error is not None:
        return (
            f"baseline fetch failed and Crawl4AI fallback also failed after `{fallback_reason}`: "
            f"baseline={baseline_error}; fallback={fallback_error}"
        )
    page_class = baseline_classification.page_class if baseline_classification is not None else None
    usable_text_chars = int(baseline_snapshot.usable_text_chars or 0) if baseline_snapshot is not None else 0
    return (
        f"Crawl4AI fallback failed after `{fallback_reason}` "
        f"(baseline_page_class={page_class or 'unknown'}, usable_text_chars={usable_text_chars}): {fallback_error}"
    )
