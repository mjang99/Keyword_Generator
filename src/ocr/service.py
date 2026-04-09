from __future__ import annotations

import re
from typing import Any

from src.collection.models import NormalizedPageSnapshot

from .models import OcrDecision

PROMO_TOKENS = ("할인", "쿠폰", "혜택", "이벤트", "sale", "offer", "benefit", "promo")
SPEC_TOKENS = (
    "spec",
    "specification",
    "기술",
    "사양",
    "호환",
    "배터리",
    "battery",
    "memory",
    "cpu",
    "재질",
    "용량",
    "성분",
)
REJECT_IMAGE_TOKENS = ("logo", "icon", "sprite", "badge", "thumbnail", "favicon")
PRIORITY_IMAGE_TOKENS = ("hero", "gallery", "detail", "spec", "product", "slide", "main")
TABLE_IMAGE_TOKENS = (
    "table",
    "spec",
    "specification",
    "chart",
    "grid",
    "compare",
    "comparison",
    "matrix",
    "guide",
    "size",
    "shade",
    "swatch",
)
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
REJECT_IMAGE_EXTENSIONS = (".svg", ".gif", ".ico")
REJECT_IMAGE_HOST_TOKENS = ("echosting.cafe24.com",)
REJECT_IMAGE_PATH_TOKENS = (
    "/web/upload/images/",
    "/web/product/small/",
    "header_scope",
    "ico_",
    "icn-",
)
REJECT_IMAGE_TEMPLATE_TOKENS = ("'+", "+'", "${", "{{", "}}")


def run_ocr_policy(snapshot: NormalizedPageSnapshot) -> OcrDecision:
    trigger_reasons = _trigger_reasons(snapshot)
    ranked_candidates = _rank_image_candidates(snapshot)
    source_blocks = list(snapshot.ocr_text_blocks or [])
    image_results = _build_image_results(snapshot, ranked_candidates)

    if not trigger_reasons and not source_blocks:
        return OcrDecision(status="SKIPPED", trigger_reasons=["ocr_not_required"], image_results=image_results)

    admitted_blocks: list[dict[str, Any]] = []
    rejected_blocks: list[dict[str, Any]] = []
    for block in source_blocks:
        accepted, normalized = _admit_block(block, snapshot)
        if accepted:
            admitted_blocks.append(normalized)
        else:
            rejected_blocks.append(normalized)

    if not source_blocks:
        return OcrDecision(
            status="SKIPPED",
            trigger_reasons=trigger_reasons + ["no_ocr_blocks_available"],
            ranked_image_candidates=ranked_candidates,
            rejected_blocks=[],
            contribution_chars=0,
            image_results=image_results,
        )

    admitted_blocks.sort(key=lambda item: (-float(item.get("score", 0.0)), item.get("text", "")))
    image_results = _apply_block_counts(image_results, admitted_blocks, rejected_blocks)
    return OcrDecision(
        status="AVAILABLE",
        trigger_reasons=trigger_reasons or ["fixture_ocr_blocks_present"],
        ranked_image_candidates=ranked_candidates,
        admitted_blocks=admitted_blocks,
        rejected_blocks=rejected_blocks,
        contribution_chars=sum(len(str(block.get("text", ""))) for block in admitted_blocks),
        image_results=image_results,
    )


def _trigger_reasons(snapshot: NormalizedPageSnapshot) -> list[str]:
    reasons = list(snapshot.ocr_trigger_reasons or [])
    usable_text_chars = snapshot.usable_text_chars or 0
    charset_confidence = snapshot.charset_confidence or 1.0
    if usable_text_chars < 1500:
        reasons.append("thin_visible_text")
    if charset_confidence < 0.80:
        reasons.append("low_charset_confidence")
    if snapshot.page_class_hint == "image_heavy_commerce_pdp":
        reasons.append("image_heavy_page")
    if _image_alt_suggests_text(snapshot):
        reasons.append("image_alt_product_text")
    if _detail_image_candidate_present(snapshot):
        reasons.append("detail_image_candidate")
    return _dedupe(reasons)


def _image_alt_suggests_text(snapshot: NormalizedPageSnapshot) -> bool:
    if not snapshot.image_candidates:
        return False
    tokens = _token_set(snapshot)
    for candidate in snapshot.image_candidates:
        alt = str(candidate.get("alt", "")).lower()
        if not alt:
            continue
        if len(_matching_tokens(tokens, alt)) >= 2 or any(token in alt for token in SPEC_TOKENS):
            return True
    return False


def _rank_image_candidates(snapshot: NormalizedPageSnapshot) -> list[dict[str, Any]]:
    tokens = _token_set(snapshot)
    ranked: list[dict[str, Any]] = []
    for index, candidate in enumerate(snapshot.image_candidates or []):
        normalized = dict(candidate)
        src = str(candidate.get("src", ""))
        alt = str(candidate.get("alt", ""))
        width = _int_value(candidate.get("width"))
        height = _int_value(candidate.get("height"))
        lower_src = src.lower()
        lower_alt = alt.lower()
        candidate_type = _candidate_type(lower_src, lower_alt)
        rejected_reason = _reject_image_reason(
            src=src,
            alt=alt,
            width=width,
            height=height,
            detail_hint=bool(candidate.get("detail_hint")),
            candidate_type=candidate_type,
        )
        if rejected_reason:
            continue

        score = 0.0
        if width and height:
            area = width * height
            if area >= 300 * 300:
                score += min(area / 1_000_000, 1.5)
        else:
            score += 0.25

        if any(token in lower_src or token in lower_alt for token in PRIORITY_IMAGE_TOKENS):
            score += 0.35
        if candidate.get("detail_hint") or any(token in lower_src for token in DETAIL_IMAGE_PATH_HINTS):
            score += 1.4
        if str(candidate.get("attribute", "")).lower() != "src":
            score += 0.2
        if lower_src.endswith(".webp"):
            score += 0.15

        token_overlap = len(_matching_tokens(tokens, f"{lower_alt} {lower_src}"))
        score += min(token_overlap * 0.18, 0.72)
        score += max(0.0, 0.15 - index * 0.02)

        normalized["score"] = round(score, 4)
        normalized["candidate_type"] = candidate_type
        normalized["ocr_pipeline_type"] = "structured_table" if candidate_type == "table_like_image" else "plain_text"
        ranked.append(normalized)

    ranked.sort(key=lambda item: (-float(item["score"]), str(item.get("src", ""))))
    return ranked


def _reject_image_reason(
    *,
    src: str,
    alt: str,
    width: int | None,
    height: int | None,
    detail_hint: bool,
    candidate_type: str,
) -> str | None:
    lower = f"{src} {alt}".lower()
    if any(token in lower for token in REJECT_IMAGE_TOKENS):
        return "decorative_asset"
    if any(token in lower for token in REJECT_IMAGE_TEMPLATE_TOKENS):
        return "templated_asset_url"
    if src.lower().endswith(REJECT_IMAGE_EXTENSIONS):
        return "non_ocr_image_format"
    if any(token in lower for token in REJECT_IMAGE_HOST_TOKENS):
        return "remote_ui_asset"
    if "/web/upload/images/" in src.lower() and candidate_type != "table_like_image":
        return "decorative_path_asset"
    if any(token in src.lower() for token in REJECT_IMAGE_PATH_TOKENS):
        if candidate_type != "table_like_image" and not detail_hint:
            return "decorative_path_asset"
    if width is not None and height is not None and (width < 300 or height < 300):
        return "below_min_dimensions"
    if width is not None and height is None and width < 80:
        return "below_min_known_dimension"
    if height is not None and width is None and height < 80:
        return "below_min_known_dimension"
    return None


def _detail_image_candidate_present(snapshot: NormalizedPageSnapshot) -> bool:
    for candidate in snapshot.image_candidates or []:
        if candidate.get("detail_hint"):
            return True
        lower_src = str(candidate.get("src", "")).lower()
        if any(token in lower_src for token in DETAIL_IMAGE_PATH_HINTS):
            return True
    return False


def _candidate_type(lower_src: str, lower_alt: str) -> str:
    combined = f"{lower_src} {lower_alt}"
    if any(token in combined for token in TABLE_IMAGE_TOKENS):
        return "table_like_image"
    if len(re.findall(r"\b(?:[a-z]{1,3}\d+[a-z0-9]*|\d+[a-z]{1,3}[a-z0-9]*)\b", combined, re.IGNORECASE)) >= 2:
        return "table_like_image"
    return "general_detail_image"


def _build_image_results(
    snapshot: NormalizedPageSnapshot,
    ranked_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = {
        str(item.get("image_src", "")): dict(item)
        for item in (snapshot.ocr_image_results or [])
        if str(item.get("image_src", "")).strip()
    }
    image_results: list[dict[str, Any]] = []
    for candidate in ranked_candidates:
        src = str(candidate.get("src", "")).strip()
        if not src:
            continue
        result = existing.get(src, {})
        image_results.append(
            {
                "image_src": src,
                "image_attribute": result.get("image_attribute", candidate.get("attribute")),
                "image_score": result.get("image_score", candidate.get("score")),
                "candidate_type": result.get("candidate_type", candidate.get("candidate_type", "general_detail_image")),
                "pipeline_type": result.get("pipeline_type", candidate.get("ocr_pipeline_type", "plain_text")),
                "engine_used": result.get("engine_used"),
                "status": result.get("status", "pending"),
                "raw_block_count": int(result.get("raw_block_count", 0) or 0),
                "raw_char_count": int(result.get("raw_char_count", 0) or 0),
                "admitted_block_count": int(result.get("admitted_block_count", 0) or 0),
                "rejected_block_count": int(result.get("rejected_block_count", 0) or 0),
                "error": result.get("error"),
            }
        )
    return image_results


def _apply_block_counts(
    image_results: list[dict[str, Any]],
    admitted_blocks: list[dict[str, Any]],
    rejected_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    admitted_by_src: dict[str, int] = {}
    rejected_by_src: dict[str, int] = {}
    for block in admitted_blocks:
        src = str(block.get("image_src", "")).strip()
        if src:
            admitted_by_src[src] = admitted_by_src.get(src, 0) + 1
    for block in rejected_blocks:
        src = str(block.get("image_src", "")).strip()
        if src:
            rejected_by_src[src] = rejected_by_src.get(src, 0) + 1

    normalized_results: list[dict[str, Any]] = []
    for result in image_results:
        updated = dict(result)
        src = str(updated.get("image_src", "")).strip()
        updated["admitted_block_count"] = admitted_by_src.get(src, 0)
        updated["rejected_block_count"] = rejected_by_src.get(src, 0)
        normalized_results.append(updated)
    return normalized_results


def _admit_block(block: dict[str, Any], snapshot: NormalizedPageSnapshot) -> tuple[bool, dict[str, Any]]:
    normalized = dict(block)
    text = _extract_block_text(block)
    normalized["text"] = text
    normalized["score"] = round(_block_score(text, snapshot, block), 4)

    if not text:
        normalized["rejection_reason"] = "empty_text"
        return False, normalized
    if _mostly_numeric_junk(text):
        normalized["rejection_reason"] = "mostly_numeric_junk"
        return False, normalized
    if _mostly_brand_repetition(text, snapshot):
        normalized["rejection_reason"] = "brand_only_repetition"
        return False, normalized
    if _duplicate_of_html_text(text, snapshot.decoded_text or ""):
        normalized["rejection_reason"] = "duplicate_of_direct_html"
        return False, normalized

    tokens = _token_set(snapshot)
    matched_tokens = _matching_tokens(tokens, text.lower())
    has_minimum_content = (
        len(text) >= 30
        or len(matched_tokens) >= 2
        or _should_preserve_short_image_block(text, matched_tokens, block)
    )
    if not has_minimum_content:
        normalized["rejection_reason"] = "too_short_without_product_tokens"
        return False, normalized

    if _contains_unrelated_product_names(text, matched_tokens, snapshot, block):
        normalized["rejection_reason"] = "unrelated_product_names"
        return False, normalized

    if any(token in text.lower() for token in PROMO_TOKENS) and not matched_tokens:
        normalized["rejection_reason"] = "promo_not_tied_to_product"
        return False, normalized

    normalized["matched_tokens"] = matched_tokens
    return True, normalized


def _extract_block_text(block: dict[str, Any]) -> str:
    for key in ("text", "content", "value", "ocr_text"):
        value = block.get(key)
        if value:
            return " ".join(str(value).split()).strip()
    return ""


def _block_score(text: str, snapshot: NormalizedPageSnapshot, block: dict[str, Any]) -> float:
    lowered = text.lower()
    matched_tokens = _matching_tokens(_token_set(snapshot), lowered)
    score = min(len(text) / 120.0, 0.8)
    score += min(len(matched_tokens) * 0.2, 1.0)
    if any(token in lowered for token in SPEC_TOKENS):
        score += 0.25
    if block.get("source") == "screenshot":
        score += 0.1
    return score


def _mostly_numeric_junk(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text)
    if not stripped:
        return True
    alnum = re.findall(r"[A-Za-z0-9가-힣]", stripped)
    if not alnum:
        return True
    digit_ratio = sum(char.isdigit() for char in alnum) / len(alnum)
    return digit_ratio > 0.85 or (digit_ratio > 0.7 and len(set(alnum)) <= max(6, len(alnum) // 2))


def _mostly_brand_repetition(text: str, snapshot: NormalizedPageSnapshot) -> bool:
    words = re.findall(r"[A-Za-z0-9가-힣]+", text.lower())
    if len(words) < 3:
        return False
    unique_words = set(words)
    if len(unique_words) == 1:
        return True
    if len(unique_words) > 2:
        return False
    tokens = _token_set(snapshot)
    return bool(unique_words.intersection(tokens))


def _duplicate_of_html_text(text: str, decoded_text: str) -> bool:
    normalized_text = " ".join(text.lower().split())
    normalized_html = " ".join(decoded_text.lower().split())
    return len(normalized_text) >= 24 and normalized_text in normalized_html


def _contains_unrelated_product_names(
    text: str,
    matched_tokens: list[str],
    snapshot: NormalizedPageSnapshot,
    block: dict[str, Any],
) -> bool:
    if block.get("source") == "image":
        return False
    candidate_names = {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{2,}", text)
        if token.lower() not in _token_set(snapshot)
    }
    if matched_tokens:
        return False
    return len(candidate_names) >= 2


def _should_preserve_short_image_block(
    text: str,
    matched_tokens: list[str],
    block: dict[str, Any],
) -> bool:
    if block.get("source") != "image":
        return False
    if matched_tokens:
        return True
    alpha_terms = re.findall(r"[A-Za-z\uac00-\ud7a3]{4,}", text)
    if len(alpha_terms) >= 2:
        return True
    if len(alpha_terms) == 1 and len(alpha_terms[0]) >= 8:
        return True
    if block.get("candidate_type") == "table_like_image" and re.search(
        r"\b(?:[a-z]{1,3}\d+[a-z0-9]*|\d+[a-z]{1,3}[a-z0-9]*)\b",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


def _token_set(snapshot: NormalizedPageSnapshot) -> set[str]:
    seeds = list(snapshot.primary_product_tokens)
    if snapshot.product_name:
        seeds.extend(re.findall(r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣.+-]{1,}", snapshot.product_name))
    tokens = {
        token.lower()
        for token in seeds
        if len(token) >= 2 and token.lower() not in {"with", "for", "and", "the"}
    }
    return tokens


def _matching_tokens(tokens: set[str], text: str) -> list[str]:
    return sorted(token for token in tokens if token and token in text)


def _int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
