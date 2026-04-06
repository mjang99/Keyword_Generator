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
PRODUCT_URL_PATTERNS = ("/products/", "/product/", "/shop/product/", "/display/event_detail")


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
    )


def collect_snapshot_from_html(fetch_result: HtmlFetchResult) -> NormalizedPageSnapshot:
    title = _extract_first_group(r"<title[^>]*>(.*?)</title>", fetch_result.html)
    meta_description = _extract_meta(fetch_result.html, "description")
    canonical_tag = _extract_canonical(fetch_result.html)
    meta_locale = _extract_meta(fetch_result.html, "og:locale", property_mode=True)
    lang = _extract_first_group(r"<html[^>]+lang=[\"']([^\"']+)[\"']", fetch_result.html)
    decoded_text = _extract_visible_text(fetch_result.html)
    visible_blocks = [block for block in re.split(r"\n+", decoded_text) if block][:20]
    image_candidates = _extract_image_candidates(fetch_result.html, fetch_result.final_url)
    structured_data = _extract_structured_data(fetch_result.html)

    lowered = f"{title} {meta_description} {decoded_text}".lower()
    price_signals = _find_matches(lowered, PRICE_PATTERNS, regex=True)
    buy_signals = _find_matches(lowered, BUY_PATTERNS)
    stock_signals = _find_matches(lowered, STOCK_PATTERNS)
    promo_signals = _find_matches(lowered, PROMO_PATTERNS)
    support_signals = _find_matches(lowered, SUPPORT_PATTERNS)
    download_signals = _find_matches(lowered, DOWNLOAD_PATTERNS)
    blocker_signals = _find_matches(lowered, BLOCKER_PATTERNS)
    waiting_signals = _find_matches(lowered, WAITING_PATTERNS)
    primary_tokens = _product_tokens(title, meta_description)
    usable_text_chars = len(decoded_text)
    support_density = _density(len(support_signals), usable_text_chars)
    download_density = _density(len(download_signals), usable_text_chars)
    promo_density = _density(len(promo_signals), usable_text_chars)
    single_product_confidence = _single_product_confidence(title, decoded_text, fetch_result.final_url)
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
        usable_text_chars=usable_text_chars,
    )
    quality_warning = page_class_hint in {"support_spec_page", "document_download_heavy_support_page", "image_heavy_commerce_pdp"}
    ocr_trigger_reasons = ["image_heavy_page"] if page_class_hint == "image_heavy_commerce_pdp" else []
    product_name = title or fetch_result.final_url
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
    excerpt = (snapshot.visible_text or "")[:800]
    if not title and not excerpt:
        return None

    user_prompt = f"Title: {title}\n\nText excerpt:\n{excerpt}"
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
    for match in re.finditer(r"<img[^>]+src=[\"'](.*?)[\"'][^>]*>", html_text, flags=re.IGNORECASE):
        tag = match.group(0)
        src = match.group(1)
        alt = _extract_first_group(r"alt=[\"'](.*?)[\"']", tag) or ""
        candidates.append({"src": urljoin(base_url, src), "alt": alt})
        if len(candidates) >= 10:
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


def _find_matches(text: str, patterns: tuple[str, ...], *, regex: bool = False) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        if regex:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matches.append(pattern)
        elif pattern.lower() in text:
            matches.append(pattern.lower())
    return matches


def _product_tokens(title: str | None, meta_description: str | None) -> list[str]:
    source = " ".join(part for part in (title, meta_description) if part)
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


def _single_product_confidence(title: str | None, decoded_text: str, final_url: str) -> float:
    title_text = (title or "").lower()
    score = 0.2
    if title and len(title.split()) >= 2:
        score += 0.25
    if any(part in final_url.lower() for part in PRODUCT_URL_PATTERNS[:2]):
        score += 0.25
    if re.search(r"\b(pro|mask|cream|cloudtilt|airpods|macbook)\b", title_text):
        score += 0.2
    if len(decoded_text) > 800:
        score += 0.1
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
    if promo_signals and single_product_confidence <= 0.6 and (is_landing_surface or len(promo_signals) >= 2):
        return "promo_heavy_commerce_landing"
    if has_support_context and support_signals and len(download_signals) >= 3:
        return "document_download_heavy_support_page"
    if has_support_context and support_signals:
        return "support_spec_page"
    if "__nuxt__={};" in lowered or usable_text_chars < 250 or lowered.count("/products/") > 8:
        return "non_product_page"
    if price_signals and buy_signals and usable_text_chars < 2500:
        return "image_heavy_commerce_pdp"
    if price_signals or buy_signals:
        return "commerce_pdp"
    if "/shop/" in fetch_result.final_url.lower() or "/product/" in fetch_result.final_url.lower():
        return "marketing_only_pdp"
    if title_lower:
        return "product_marketing_page"
    return "non_product_page"
