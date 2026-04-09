from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request
from urllib.request import urlopen

from .models import NormalizedPageSnapshot, PageClassification

SUPPORTED_PAGE_CLASSES = {
    "commerce_pdp",
    "image_heavy_commerce_pdp",
    "marketing_only_pdp",
    "product_marketing_page",
    "support_spec_page",
    "document_download_heavy_support_page",
}

BLOCKER_PATTERNS = ("access denied", "captcha", "forbidden", "system error", "시스템오류", "challenge-platform")
WAITING_PATTERNS = ("waiting room", "queue", "잠시만", "대기열", "접속자가 많")
SUPPORT_PATTERNS = ("기술 사양", "specifications", "지원", "battery life", "cpu", "memory", "호환")
DOWNLOAD_PATTERNS = ("download", "manual", "pdf", "설명서", "다운로드")
PROMO_PATTERNS = ("이벤트", "혜택", "쿠폰", "benefit", "sale", "offer", "프로모션", "할인")
BUY_PATTERNS = ("장바구니", "구매하기", "add to cart", "buy now", "cart", "checkout")
STOCK_PATTERNS = ("in stock", "재고", "품절", "out of stock")
PRICE_PATTERNS = (r"₩\s?\d", r"\$\s?\d", r"\b\d{2,3},\d{3}\b", r"\b\d{4,6}\b")
PRODUCT_URL_PATTERNS = (
    "/products/",
    "/product/",
    "/shop/product/",
    "/display/event_detail",
    "/shop/buy-",
    "/mobile-accessories/",
    "goodsdetail.do",
    "/product/view",
    "productcd=",
    "goodsno=",
)
IMAGE_SOURCE_ATTRIBUTES = ("src", "data-src", "data-lazy-src", "data-original", "ec-data-src", "srcset")
DETAIL_IMAGE_PATH_HINTS = (
    "/web/upload/webp/",
    "/web/upload/",
    "/web/product/extra/",
    "/editor/",
    "/detail/",
    "/content/",
    "_detail",
    "_result",
)

BLOCKER_HTML_PATTERNS = ("window.awswafcookiedomainlist", "gokuprops", "__cf_bm", "cf-chl-", "challenge-form")


@dataclass(slots=True)
class HtmlFetchResult:
    raw_url: str
    final_url: str
    html: str
    content_type: str = "text/html"
    http_status: int = 200
    fetch_profile_used: str = "fixture_html"
    response_headers: dict[str, str] | None = None
    charset_selected: str | None = None
    charset_confidence: float | None = None
    mojibake_flags: list[str] | None = None


@dataclass(frozen=True, slots=True)
class FetchProfile:
    name: str
    headers: dict[str, str]


DEFAULT_FETCH_PROFILES = (
    FetchProfile(
        name="desktop_chrome",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
        },
    ),
    FetchProfile(
        name="generic_html",
        headers={
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "ko,en;q=0.8",
            "User-Agent": "KeywordGeneratorCollector/0.1",
        },
    ),
)


class HttpPageFetcher:
    def __init__(
        self,
        *,
        profiles: tuple[FetchProfile, ...] = DEFAULT_FETCH_PROFILES,
        timeout_seconds: float = 15.0,
        open_url: Any = None,
    ) -> None:
        self.profiles = profiles
        self.timeout_seconds = timeout_seconds
        self.open_url = open_url or urlopen

    def fetch(self, raw_url: str) -> HtmlFetchResult:
        last_error: Exception | None = None
        for profile in self.profiles:
            request = Request(raw_url, headers=profile.headers)
            try:
                with self.open_url(request, timeout=self.timeout_seconds) as response:
                    body = response.read()
                    headers = _headers_to_dict(response.headers)
                    content_type = headers.get("Content-Type", "text/html")
                    html_text, charset_selected, charset_confidence, mojibake_flags = _decode_html_bytes(body, content_type)
                    return HtmlFetchResult(
                        raw_url=raw_url,
                        final_url=response.geturl(),
                        html=html_text,
                        content_type=content_type,
                        http_status=getattr(response, "status", 200),
                        fetch_profile_used=profile.name,
                        response_headers=headers,
                        charset_selected=charset_selected,
                        charset_confidence=charset_confidence,
                        mojibake_flags=mojibake_flags,
                    )
            except HTTPError as error:
                body = error.read()
                headers = _headers_to_dict(error.headers)
                content_type = headers.get("Content-Type", "text/html")
                if body:
                    html_text, charset_selected, charset_confidence, mojibake_flags = _decode_html_bytes(body, content_type)
                    return HtmlFetchResult(
                        raw_url=raw_url,
                        final_url=error.geturl(),
                        html=html_text,
                        content_type=content_type,
                        http_status=error.code,
                        fetch_profile_used=profile.name,
                        response_headers=headers,
                        charset_selected=charset_selected,
                        charset_confidence=charset_confidence,
                        mojibake_flags=mojibake_flags,
                    )
                last_error = error
            except URLError as error:
                last_error = error

        detail = str(last_error) if last_error else "unknown fetch failure"
        raise RuntimeError(f"failed to fetch {raw_url}: {detail}") from last_error


class FixtureHtmlFetcher:
    def __init__(self, *, base_dir: str | Path, url_to_file: dict[str, str]) -> None:
        self.base_dir = Path(base_dir)
        self.url_to_file = url_to_file

    def fetch(self, raw_url: str) -> HtmlFetchResult:
        relative = self.url_to_file[raw_url]
        fixture_path = self.base_dir / relative
        html_text = fixture_path.read_text(encoding="utf-8", errors="ignore")
        return HtmlFetchResult(raw_url=raw_url, final_url=raw_url, html=html_text)


def build_snapshot_from_fixture(payload: dict[str, Any]) -> NormalizedPageSnapshot:
    payload = {key: value for key, value in payload.items() if key != "_test_notes"}
    return NormalizedPageSnapshot(
        raw_url=str(payload.get("raw_url") or payload.get("canonical_url") or ""),
        canonical_url=str(payload.get("canonical_url") or payload.get("raw_url") or ""),
        page_class_hint=str(payload.get("page_class") or ""),
        final_url=_optional_str(payload.get("final_url")),
        http_status=payload.get("http_status"),
        content_type=_optional_str(payload.get("content_type")),
        fetch_profile_used=_optional_str(payload.get("fetch_profile_used")),
        fetched_at=_optional_str(payload.get("fetched_at")),
        charset_selected=_optional_str(payload.get("charset_selected")),
        charset_confidence=payload.get("charset_confidence"),
        mojibake_flags=list(payload.get("mojibake_flags", [])),
        meta_locale=_optional_str(payload.get("meta_locale")),
        language_scores=dict(payload.get("language_scores", {})),
        title=_optional_str(payload.get("title")),
        meta_description=_optional_str(payload.get("meta_description")),
        canonical_tag=_optional_str(payload.get("canonical_tag")),
        decoded_text=_optional_str(payload.get("decoded_text")),
        visible_text_blocks=list(payload.get("visible_text_blocks", [])),
        breadcrumbs=list(payload.get("breadcrumbs", [])),
        structured_data=list(payload.get("structured_data", [])),
        primary_product_tokens=list(payload.get("primary_product_tokens", [])),
        price_signals=list(payload.get("price_signals", [])),
        buy_signals=list(payload.get("buy_signals", [])),
        stock_signals=list(payload.get("stock_signals", [])),
        promo_signals=list(payload.get("promo_signals", [])),
        support_signals=list(payload.get("support_signals", [])),
        download_signals=list(payload.get("download_signals", [])),
        blocker_signals=list(payload.get("blocker_signals", [])),
        waiting_signals=list(payload.get("waiting_signals", [])),
        image_candidates=list(payload.get("image_candidates", [])),
        ocr_trigger_reasons=list(payload.get("ocr_trigger_reasons", [])),
        single_product_confidence=payload.get("single_product_confidence"),
        sellability_confidence=payload.get("sellability_confidence"),
        support_density=payload.get("support_density"),
        download_density=payload.get("download_density"),
        promo_density=payload.get("promo_density"),
        usable_text_chars=payload.get("usable_text_chars"),
        product_name=_derive_product_name(payload),
        locale_detected=_optional_str(payload.get("locale_detected")),
        market_locale=_optional_str(payload.get("market_locale")),
        sellability_state=_optional_str(payload.get("sellability_state")),
        stock_state=_optional_str(payload.get("stock_state")),
        sufficiency_state=_optional_str(payload.get("sufficiency_state")),
        quality_warning=bool(payload.get("quality_warning", False)),
        fallback_used=bool(payload.get("fallback_used", False)),
        weak_backfill_used=bool(payload.get("weak_backfill_used", False)),
        facts=list(payload.get("facts", [])),
        ocr_text_blocks=list(payload.get("ocr_text_blocks", [])),
        ocr_image_results=list(payload.get("ocr_image_results", [])),
    )


def collect_snapshot_from_html(fetch_result: HtmlFetchResult) -> NormalizedPageSnapshot:
    raw_title = _extract_first_group(r"<title[^>]*>(.*?)</title>", fetch_result.html)
    og_title = _extract_meta(fetch_result.html, "og:title", property_mode=True)
    raw_meta_description = _extract_meta(fetch_result.html, "description")
    og_meta_description = _extract_meta(fetch_result.html, "og:description", property_mode=True)
    canonical_tag = _extract_canonical(fetch_result.html)
    meta_locale = _extract_meta(fetch_result.html, "og:locale", property_mode=True)
    lang = _extract_first_group(r"<html[^>]+lang=[\"']([^\"']+)[\"']", fetch_result.html)
    decoded_text = _extract_visible_text(fetch_result.html)
    visible_blocks = _meaningful_visible_blocks_v2(decoded_text)
    image_candidates = _extract_image_candidates(fetch_result.html, fetch_result.final_url)
    structured_data = _extract_structured_data(fetch_result.html)
    structured_product = _extract_structured_product_signals_v2(structured_data)
    title = _resolve_primary_title_v2(raw_title, og_title, structured_product["product_name"])
    meta_description = _first_non_empty_v2(raw_meta_description, og_meta_description, structured_product["description"])
    product_name = _resolve_product_name_v2(title, og_title, structured_product["product_name"], fetch_result.final_url)

    lowered = f"{title} {meta_description} {decoded_text}".lower()
    price_signals = _find_matches(lowered, PRICE_PATTERNS, regex=True)
    buy_signals = _find_matches(lowered, BUY_PATTERNS)
    stock_signals = _find_matches(lowered, STOCK_PATTERNS)
    promo_signals = _find_matches(lowered, PROMO_PATTERNS)
    support_signals = _find_matches(lowered, SUPPORT_PATTERNS)
    download_signals = _find_matches(lowered, DOWNLOAD_PATTERNS)
    blocker_signals = _dedupe_strings(
        [
            *_find_matches(lowered, BLOCKER_PATTERNS),
            *_find_matches(fetch_result.html.lower(), BLOCKER_HTML_PATTERNS),
        ]
    )
    waiting_signals = _find_matches(lowered, WAITING_PATTERNS)
    primary_tokens = _product_tokens(title, meta_description, product_name, structured_product["brand"])
    usable_text_chars = len(decoded_text)
    support_density = _density(len(support_signals), usable_text_chars)
    download_density = _density(len(download_signals), usable_text_chars)
    promo_density = _density(len(promo_signals), usable_text_chars)
    single_product_confidence = _single_product_confidence(
        title=title,
        product_name=product_name,
        decoded_text=decoded_text,
        final_url=fetch_result.final_url,
        price_signals=price_signals,
        buy_signals=buy_signals,
        primary_product_tokens=primary_tokens,
        has_structured_product=structured_product["has_product_schema"],
    )
    sellability_confidence = _sellability_confidence(price_signals, buy_signals, stock_signals)

    page_class_hint = _classify_html(
        title=title,
        lowered=lowered,
        fetch_result=fetch_result,
        support_signals=support_signals,
        download_signals=download_signals,
        promo_signals=promo_signals,
        blocker_signals=blocker_signals,
        waiting_signals=waiting_signals,
        price_signals=price_signals,
        buy_signals=buy_signals,
        single_product_confidence=single_product_confidence,
        has_structured_product=structured_product["has_product_schema"],
        usable_text_chars=usable_text_chars,
    )
    quality_warning = page_class_hint in {"support_spec_page", "document_download_heavy_support_page", "image_heavy_commerce_pdp"}
    ocr_trigger_reasons = ["image_heavy_page"] if page_class_hint == "image_heavy_commerce_pdp" else []
    sellability_state = "sellable" if price_signals or buy_signals else "non_sellable"
    stock_state = "Unknown"
    if any("out of stock" in signal or "품절" in signal for signal in stock_signals):
        stock_state = "OutOfStock"
    elif stock_signals:
        stock_state = "InStock"

    return NormalizedPageSnapshot(
        raw_url=fetch_result.raw_url,
        canonical_url=fetch_result.raw_url,
        page_class_hint=page_class_hint,
        final_url=fetch_result.final_url,
        http_status=fetch_result.http_status,
        content_type=fetch_result.content_type,
        fetch_profile_used=fetch_result.fetch_profile_used,
        fetched_at=datetime.now(tz=UTC).isoformat(),
        charset_selected=fetch_result.charset_selected or "utf-8",
        charset_confidence=fetch_result.charset_confidence or 1.0,
        mojibake_flags=list(fetch_result.mojibake_flags or []),
        meta_locale=meta_locale,
        language_scores=_language_scores(lang, decoded_text),
        title=title,
        meta_description=meta_description,
        canonical_tag=canonical_tag,
        decoded_text=decoded_text,
        visible_text_blocks=visible_blocks,
        breadcrumbs=[],
        structured_data=structured_data,
        primary_product_tokens=primary_tokens,
        price_signals=price_signals,
        buy_signals=buy_signals,
        stock_signals=stock_signals,
        promo_signals=promo_signals,
        support_signals=support_signals,
        download_signals=download_signals,
        blocker_signals=blocker_signals,
        waiting_signals=waiting_signals,
        image_candidates=image_candidates,
        ocr_trigger_reasons=ocr_trigger_reasons,
        single_product_confidence=single_product_confidence,
        sellability_confidence=sellability_confidence,
        support_density=support_density,
        download_density=download_density,
        promo_density=promo_density,
        usable_text_chars=usable_text_chars,
        product_name=product_name,
        locale_detected=lang or ("ko" if "ko" in (meta_locale or "").lower() else "en"),
        market_locale=(meta_locale or lang or "en"),
        sellability_state=sellability_state,
        stock_state=stock_state,
        sufficiency_state="sufficient" if usable_text_chars >= 400 else "borderline",
        quality_warning=quality_warning,
        fallback_used=False,
        weak_backfill_used=False,
        facts=[],
        ocr_text_blocks=[],
        ocr_image_results=[],
    )


def classify_snapshot(snapshot: NormalizedPageSnapshot) -> PageClassification:
    """Classify a page snapshot, with an optional LLM product-gate override.

    When KEYWORD_GENERATOR_GENERATION_MODE=bedrock is set, a mandatory first gate
    asks the LLM "Is this a product sales page?" before finalizing the class.
    The gate can override to 'non_product_page' or 'support_spec_page'.
    """
    from src.keyword_generation.bedrock_adapter import should_use_bedrock

    page_class = snapshot.page_class_hint
    decisive_signals = [page_class] if page_class else []

    if page_class in SUPPORTED_PAGE_CLASSES:
        rule_result = PageClassification(
            page_class=page_class,
            supported_for_generation=True,
            confidence=0.95,
            decisive_signals=decisive_signals,
        )
    else:
        rule_result = PageClassification(
            page_class=page_class or "non_product_page",
            supported_for_generation=False,
            confidence=0.95,
            decisive_signals=decisive_signals,
            failure_code_candidate=page_class or "non_product_page",
        )

    if not should_use_bedrock():
        return rule_result
    if page_class in {"blocked_page", "waiting_page", "support_spec_page", "document_download_heavy_support_page"}:
        return rule_result

    override_class = _bedrock_product_gate(snapshot)
    if override_class is None:
        return rule_result

    # Gate overrides the rule result
    supported = override_class in SUPPORTED_PAGE_CLASSES
    return PageClassification(
        page_class=override_class,
        supported_for_generation=supported,
        confidence=0.90,
        decisive_signals=[*decisive_signals, "bedrock_product_gate"],
        failure_code_candidate=None if supported else override_class,
        bedrock_gate_override=True,
    )


_PRODUCT_GATE_SYSTEM_PROMPT = (
    "You are a page classifier. Given a page title and a short text excerpt, "
    "answer with a JSON object only — no explanation.\n"
    "Schema: {\"is_product_sales_page\": true|false, \"reason\": \"one-sentence reason\"}\n"
    "Rules:\n"
    "- is_product_sales_page = true when the page's primary purpose is to sell or enable "
    "purchase of a specific physical or digital product.\n"
    "- is_product_sales_page = false for support pages, spec pages, blog posts, landing "
    "pages without a buy action, or pages with no identifiable product."
)


def _bedrock_product_gate(snapshot: NormalizedPageSnapshot) -> str | None:
    """Call Bedrock to confirm whether this page is a product sales page.

    Returns an overriding page_class string, or None to keep the rule-based result.
    Only returns a non-None value when the LLM definitively disagrees with the rule result.
    """
    import json as _json

    from src.clients.bedrock import BedrockRuntimeSettings, converse_text

    title = (snapshot.title or "")[:200]
    product_name = (snapshot.product_name or "")[:200]
    meta_description = (snapshot.meta_description or "")[:240]
    excerpt_source = _bedrock_excerpt_source_v2(snapshot)
    excerpt = excerpt_source[:800]
    if not title and not product_name and not excerpt:
        return None

    user_prompt = (
        f"Rule-based page hint: {snapshot.page_class_hint or 'unknown'}\n"
        f"Product name: {product_name}\n"
        f"Title: {title}\n"
        f"Meta description: {meta_description}\n\n"
        f"Text excerpt:\n{excerpt}"
    )
    try:
        _, response_text = converse_text(
            user_prompt,
            system_prompt=_PRODUCT_GATE_SYSTEM_PROMPT,
            settings=BedrockRuntimeSettings.from_env(),
        )
        # Extract JSON from response
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        gate = _json.loads(response_text[start:end])
        is_sales_page = bool(gate.get("is_product_sales_page", True))
    except Exception:
        return None

    # Only override if LLM says it is NOT a sales page
    if not is_sales_page:
        if snapshot.page_class_hint in {"support_spec_page", "document_download_heavy_support_page"}:
            return "support_spec_page"
        return "non_product_page"

    # LLM confirms it is a sales page — no override needed
    return None


def _derive_product_name(payload: dict[str, Any]) -> str | None:
    product_name = payload.get("product_name")
    if product_name:
        return str(product_name)
    for fact in payload.get("facts", []):
        if fact.get("type") == "product_name":
            return str(fact.get("normalized_value") or fact.get("value") or "").strip() or None
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_first_group(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return " ".join(html.unescape(match.group(1)).split()).strip() or None


def _extract_meta(html_text: str, name: str, *, property_mode: bool = False) -> str | None:
    attribute = "property" if property_mode else "name"
    pattern = rf"<meta[^>]+{attribute}=[\"']{re.escape(name)}[\"'][^>]+content=[\"'](.*?)[\"']"
    return _extract_first_group(pattern, html_text)


def _extract_canonical(html_text: str) -> str | None:
    return _extract_first_group(r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"'](.*?)[\"']", html_text)


def _extract_visible_text(html_text: str) -> str:
    stripped = re.sub(r"<!--.*?-->", " ", html_text, flags=re.DOTALL)
    stripped = re.sub(r"<script.*?>.*?</script>", " ", stripped, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(r"<style.*?>.*?</style>", " ", stripped, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(r"<noscript.*?>.*?</noscript>", " ", stripped, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(r"<[^>]+>", "\n", stripped)
    stripped = html.unescape(stripped)
    stripped = stripped.replace("\r", "\n")
    stripped = re.sub(r"[ \t]+", " ", stripped)
    stripped = re.sub(r"\n{2,}", "\n", stripped)
    return stripped.strip()


def _headers_to_dict(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key): str(value) for key, value in headers.items()}
    return {}


def _decode_html_bytes(body: bytes, content_type: str) -> tuple[str, str | None, float | None, list[str]]:
    candidates = _charset_candidates(body, content_type)
    scored: list[tuple[float, str, str, list[str]]] = []
    for encoding in candidates:
        try:
            decoded = body.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        mojibake_flags = _mojibake_flags(decoded)
        score = _decoded_text_score(decoded, mojibake_flags)
        if encoding == candidates[0]:
            score += 0.15
        scored.append((score, encoding, decoded, mojibake_flags))

    if not scored:
        decoded = body.decode("utf-8", errors="replace")
        mojibake_flags = _mojibake_flags(decoded)
        return decoded, "utf-8", 0.2, mojibake_flags or ["replacement_characters"]

    score, encoding, decoded, mojibake_flags = max(scored, key=lambda item: item[0])
    confidence = min(max(score, 0.2), 1.0)
    return decoded, encoding, round(confidence, 4), mojibake_flags


def _charset_candidates(body: bytes, content_type: str) -> list[str]:
    header_charset = _extract_charset_from_content_type(content_type)
    meta_probe = body[:4096].decode("latin-1", errors="ignore")
    meta_charset = _extract_first_group(r"<meta[^>]+charset=[\"']?([A-Za-z0-9._-]+)", meta_probe)

    candidates: list[str] = []
    for candidate in (header_charset, meta_charset, "utf-8", "cp949", "euc-kr", "iso-8859-1"):
        if not candidate:
            continue
        normalized = candidate.lower()
        if normalized in candidates:
            continue
        candidates.append(normalized)
    return candidates


def _extract_charset_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _mojibake_flags(decoded: str) -> list[str]:
    flags: list[str] = []
    if "\ufffd" in decoded:
        flags.append("replacement_characters")
    if any(marker in decoded for marker in ("Ã", "Â", "ð", "ì", "ë")):
        flags.append("utf8_latin1_mojibake")
    return flags


def _decoded_text_score(decoded: str, mojibake_flags: list[str]) -> float:
    if not decoded:
        return 0.0
    markup_hits = decoded.lower().count("<html") + decoded.lower().count("</title>") + decoded.lower().count("<body")
    printable = len(re.findall(r"[\w\s<>/=:;,.!?\"'()\-\u00C0-\u024F\u3131-\uD79D]", decoded))
    printable_ratio = printable / max(len(decoded), 1)
    penalty = 0.15 * len(mojibake_flags)
    bonus = min(markup_hits * 0.08, 0.24)
    return printable_ratio + bonus - penalty


def _extract_image_candidates(html_text: str, base_url: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, match in enumerate(re.finditer(r"<img\b[^>]*>", html_text, flags=re.IGNORECASE)):
        attributes = _parse_tag_attributes(match.group(0))
        alt = attributes.get("alt", "")
        width = _safe_int(attributes.get("width"))
        height = _safe_int(attributes.get("height"))
        for attribute_name in IMAGE_SOURCE_ATTRIBUTES:
            raw_value = attributes.get(attribute_name)
            if not raw_value:
                continue
            src = _normalize_image_source(raw_value)
            if not src:
                continue
            resolved_src = urljoin(base_url, src)
            if resolved_src in seen:
                continue
            seen.add(resolved_src)
            lower_src = resolved_src.lower()
            detail_hint = attribute_name != "src" or any(token in lower_src for token in DETAIL_IMAGE_PATH_HINTS)
            candidates.append(
                {
                    "src": resolved_src,
                    "alt": alt,
                    "attribute": attribute_name,
                    "dom_index": index,
                    "detail_hint": detail_hint,
                    "width": width,
                    "height": height,
                }
            )
            break
        if len(candidates) >= 30:
            break
    return candidates


def _extract_structured_data(html_text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for match in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        payloads.append(payload)
    return payloads


def _parse_tag_attributes(tag: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for name, _, value in re.findall(r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*([\"'])(.*?)\2", tag, flags=re.DOTALL):
        attributes[name.lower()] = html.unescape(value).strip()
    return attributes


def _normalize_image_source(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    if "," in candidate and ("srcset" in candidate or " " in candidate):
        candidate = candidate.split(",", 1)[0]
    if " " in candidate:
        candidate = candidate.split(" ", 1)[0]
    candidate = candidate.strip()
    if candidate.startswith("data:"):
        return None
    return candidate or None


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _find_matches(text: str, patterns: tuple[str, ...], *, regex: bool = False) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        if regex:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matches.append(pattern)
        elif pattern.lower() in text:
            matches.append(pattern.lower())
    return matches


def _product_tokens(*parts: str | None) -> list[str]:
    source = " ".join(part for part in parts if part)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]{2,}", source)
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(token)
    return unique[:12]


def _density(signal_count: int, usable_text_chars: int) -> float:
    if usable_text_chars <= 0:
        return 0.0
    return round(signal_count / usable_text_chars, 6)


def _single_product_confidence(
    *,
    title: str | None,
    product_name: str | None,
    decoded_text: str,
    final_url: str,
    price_signals: list[str],
    buy_signals: list[str],
    primary_product_tokens: list[str],
    has_structured_product: bool,
) -> float:
    source_text = " ".join(part for part in (title, product_name) if part).lower()
    score = 0.15
    if title and len(re.findall(r"[A-Za-z0-9가-힣]+", title)) >= 2:
        score += 0.12
    if product_name and product_name != title:
        score += 0.08
    if any(part in final_url.lower() for part in PRODUCT_URL_PATTERNS):
        score += 0.18
    if has_structured_product:
        score += 0.25
    if primary_product_tokens:
        score += 0.1
    if re.search(r"\b(pro|mask|cream|cloudtilt|airpods|macbook|iphone|galaxy|case|retinol|keyboard|pencil)\b", source_text):
        score += 0.12
    if price_signals and buy_signals:
        score += 0.15
    elif price_signals or buy_signals:
        score += 0.08
    if len(decoded_text) > 800:
        score += 0.05
    return min(score, 0.95)


def _sellability_confidence(price_signals: list[str], buy_signals: list[str], stock_signals: list[str]) -> float:
    score = 0.0
    if price_signals:
        score += 0.45
    if buy_signals:
        score += 0.35
    if stock_signals:
        score += 0.1
    return min(score, 0.95)


def _language_scores(lang: str | None, decoded_text: str) -> dict[str, float]:
    korean_chars = len(re.findall(r"[가-힣]", decoded_text))
    latin_chars = len(re.findall(r"[A-Za-z]", decoded_text))
    total = max(korean_chars + latin_chars, 1)
    scores = {
        "ko": round(korean_chars / total, 4),
        "en": round(latin_chars / total, 4),
    }
    if lang and lang.startswith("ko"):
        scores["ko"] = max(scores["ko"], 0.6)
    return scores


def _classify_html(
    *,
    title: str | None,
    lowered: str,
    fetch_result: HtmlFetchResult,
    support_signals: list[str],
    download_signals: list[str],
    promo_signals: list[str],
    blocker_signals: list[str],
    waiting_signals: list[str],
    price_signals: list[str],
    buy_signals: list[str],
    single_product_confidence: float,
    has_structured_product: bool,
    usable_text_chars: int,
) -> str:
    title_lower = (title or "").lower()
    final_url_lower = fetch_result.final_url.lower()
    has_support_context = any(token in title_lower for token in ("기술 사양", "specifications", "support", "지원")) or (
        "support.apple.com" in final_url_lower
    )
    is_landing_surface = any(
        token in final_url_lower
        for token in ("/display/main", "/display/event", "/display/live", "/display/rank", "/display/giftrecommend")
    )
    if blocker_signals:
        return "blocked_page"
    if waiting_signals:
        return "waiting_page"
    if has_support_context and support_signals and len(download_signals) >= 3:
        return "document_download_heavy_support_page"
    if has_support_context and support_signals:
        return "support_spec_page"
    strong_commerce_evidence = (
        single_product_confidence >= 0.65
        or bool(has_structured_product and (price_signals or buy_signals))
        or bool(price_signals and buy_signals and single_product_confidence >= 0.55 and not is_landing_surface)
    )
    if strong_commerce_evidence and price_signals and buy_signals and usable_text_chars < 2500:
        return "image_heavy_commerce_pdp"
    if strong_commerce_evidence and (price_signals or buy_signals):
        return "commerce_pdp"
    if promo_signals and not strong_commerce_evidence and (is_landing_surface or len(promo_signals) >= 2):
        return "promo_heavy_commerce_landing"
    if "__nuxt__={};" in lowered or usable_text_chars < 250 or lowered.count("/products/") > 8:
        return "non_product_page"
    if "/shop/" in fetch_result.final_url.lower() or "/product/" in fetch_result.final_url.lower():
        return "marketing_only_pdp"
    if title_lower:
        return "product_marketing_page"
    return "non_product_page"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _meaningful_visible_blocks(decoded_text: str) -> list[str]:
    blocks: list[str] = []
    for block in re.split(r"\n+", decoded_text):
        cleaned = " ".join(block.split()).strip()
        if not cleaned:
            continue
        if not re.search(r"[A-Za-z0-9가-힣]", cleaned):
            continue
        blocks.append(cleaned)
        if len(blocks) >= 20:
            break
    return blocks


def _first_non_empty(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _resolve_primary_title(
    raw_title: str | None,
    og_title: str | None,
    structured_product_name: str | None,
) -> str | None:
    if raw_title and not _looks_generic_title(raw_title):
        return raw_title
    return _first_non_empty(og_title, structured_product_name, raw_title)


def _resolve_product_name(
    title: str | None,
    og_title: str | None,
    structured_product_name: str | None,
    final_url: str,
) -> str | None:
    return _first_non_empty(structured_product_name, og_title, title, final_url)


def _looks_generic_title(title: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣.+&-]*", title)
    if not tokens:
        return True
    if any(token in title.lower() for token in ("waiting room", "잠시만", "captcha", "forbidden", "access denied")):
        return False
    if any(char.isdigit() for char in title):
        return False
    return len(tokens) <= 2


def _extract_structured_product_signals(structured_data: list[dict[str, Any]]) -> dict[str, str | bool | None]:
    signals: dict[str, str | bool | None] = {
        "has_product_schema": False,
        "product_name": None,
        "brand": None,
        "description": None,
    }
    for node in _iter_structured_nodes(structured_data):
        node_type = node.get("@type")
        if isinstance(node_type, list):
            type_names = [str(value) for value in node_type]
        elif node_type is None:
            type_names = []
        else:
            type_names = [str(node_type)]
        if "Product" not in type_names:
            continue
        signals["has_product_schema"] = True
        signals["product_name"] = signals["product_name"] or _optional_str(node.get("name"))
        signals["description"] = signals["description"] or _optional_str(node.get("description"))
        brand_value = node.get("brand")
        if isinstance(brand_value, dict):
            signals["brand"] = signals["brand"] or _optional_str(brand_value.get("name"))
        elif brand_value:
            signals["brand"] = signals["brand"] or _optional_str(brand_value)
    return signals


def _iter_structured_nodes(structured_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    pending: list[Any] = list(structured_data)
    while pending:
        current = pending.pop(0)
        if isinstance(current, list):
            pending[0:0] = current
            continue
        if not isinstance(current, dict):
            continue
        graph = current.get("@graph")
        if isinstance(graph, list):
            pending[0:0] = graph
        nodes.append(current)
    return nodes


def _bedrock_excerpt_source(snapshot: NormalizedPageSnapshot) -> str:
    visible_excerpt = "\n".join(_meaningful_visible_blocks("\n".join(snapshot.visible_text_blocks or [])))
    if len(visible_excerpt) >= 120:
        return visible_excerpt
    return "\n".join(part for part in (snapshot.meta_description or "", snapshot.decoded_text or "") if part)


def _meaningful_visible_blocks_v2(decoded_text: str) -> list[str]:
    blocks: list[str] = []
    for block in re.split(r"\n+", decoded_text):
        cleaned = " ".join(block.split()).strip()
        if not cleaned:
            continue
        if not re.search(r"[A-Za-z0-9\u3131-\uD79D]", cleaned):
            continue
        blocks.append(cleaned)
        if len(blocks) >= 20:
            break
    return blocks


def _first_non_empty_v2(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _looks_generic_title_v2(title: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9\u3131-\uD79D][A-Za-z0-9\u3131-\uD79D.+&-]*", title)
    if not tokens:
        return True
    if any(token in title.lower() for token in ("waiting room", "captcha", "forbidden", "access denied")):
        return False
    if any(char.isdigit() for char in title):
        return False
    return len(tokens) <= 2


def _resolve_primary_title_v2(
    raw_title: str | None,
    og_title: str | None,
    structured_product_name: str | None,
) -> str | None:
    if raw_title and not _looks_generic_title_v2(raw_title):
        return raw_title
    return _first_non_empty_v2(og_title, structured_product_name, raw_title)


def _resolve_product_name_v2(
    title: str | None,
    og_title: str | None,
    structured_product_name: str | None,
    final_url: str,
) -> str | None:
    return _first_non_empty_v2(structured_product_name, og_title, title, final_url)


def _extract_structured_product_signals_v2(structured_data: list[dict[str, Any]]) -> dict[str, str | bool | None]:
    signals: dict[str, str | bool | None] = {
        "has_product_schema": False,
        "product_name": None,
        "brand": None,
        "description": None,
    }
    for node in _iter_structured_nodes_v2(structured_data):
        node_type = node.get("@type")
        if isinstance(node_type, list):
            type_names = [str(value) for value in node_type]
        elif node_type is None:
            type_names = []
        else:
            type_names = [str(node_type)]
        if "Product" not in type_names:
            continue
        signals["has_product_schema"] = True
        signals["product_name"] = signals["product_name"] or _optional_str(node.get("name"))
        signals["description"] = signals["description"] or _optional_str(node.get("description"))
        brand_value = node.get("brand")
        if isinstance(brand_value, dict):
            signals["brand"] = signals["brand"] or _optional_str(brand_value.get("name"))
        elif brand_value:
            signals["brand"] = signals["brand"] or _optional_str(brand_value)
    return signals


def _iter_structured_nodes_v2(structured_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    pending: list[Any] = list(structured_data)
    while pending:
        current = pending.pop(0)
        if isinstance(current, list):
            pending[0:0] = current
            continue
        if not isinstance(current, dict):
            continue
        graph = current.get("@graph")
        if isinstance(graph, list):
            pending[0:0] = graph
        nodes.append(current)
    return nodes


def _bedrock_excerpt_source_v2(snapshot: NormalizedPageSnapshot) -> str:
    visible_excerpt = "\n".join(_meaningful_visible_blocks_v2("\n".join(snapshot.visible_text_blocks or [])))
    if len(visible_excerpt) >= 120:
        return visible_excerpt
    return "\n".join(part for part in (snapshot.meta_description or "", snapshot.decoded_text or "") if part)
