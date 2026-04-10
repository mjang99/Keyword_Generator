from __future__ import annotations

import re
from typing import Any

from src.collection.models import NormalizedPageSnapshot

from .models import OcrDecision

PROMO_TOKENS = ("sale", "offer", "benefit", "promo", "coupon", "event", "discount")
SPEC_TOKENS = (
    "spec",
    "specification",
    "battery",
    "memory",
    "cpu",
    "ingredient",
    "ingredients",
    "material",
    "volume",
    "capacity",
    "compare",
    "comparison",
    "shade",
    "size",
)
EXPLICIT_PRODUCT_FIELD_TOKENS = (
    "제품명",
    "품질표시사항",
    "품질 표시 사항",
    "재질",
    "제조국",
    "원산지",
    "수입원",
    "판매원",
    "제조",
    "판매",
    "가격",
    "소비자가격",
    "권장소비자가",
    "용량",
    "중량",
    "규격",
    "성분",
    "전성분",
    "원재료",
    "재료",
    "ingredient",
    "ingredients",
    "material",
    "made in",
    "price",
    "volume",
    "capacity",
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
FRONT_LABEL_TOKENS = (
    "label",
    "front",
    "package",
    "packaging",
    "bottle",
    "box",
    "ingredient",
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
MEASUREMENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?(?:ml|g|kg|oz|inch|in|gb|tb|mah|hz|w|cm|mm)\b", re.IGNORECASE)
CODELIKE_PATTERN = re.compile(r"\b(?:[a-z]{1,3}\d+[a-z0-9]*|\d+[a-z]{1,3}[a-z0-9]*)\b", re.IGNORECASE)
TEXT_TERM_PATTERN = re.compile(r"[A-Za-z\uac00-\ud7a3]{4,}")


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
            line_groups=[],
            direct_fact_candidates=[],
            same_product_metrics={"mean_same_product_score": 0.0, "mean_text_quality_score": 0.0, "direct_candidate_count": 0},
        )

    admitted_blocks.sort(
        key=lambda item: (
            0 if item.get("direct_evidence_eligible") else 1,
            -float(item.get("score", 0.0)),
            item.get("text", ""),
        )
    )
    line_groups = _build_line_groups(admitted_blocks)
    direct_fact_candidates = _extract_direct_fact_candidates(line_groups)
    image_results = _apply_block_counts(image_results, admitted_blocks, rejected_blocks, line_groups, direct_fact_candidates)
    same_product_metrics = _same_product_metrics(admitted_blocks, direct_fact_candidates)
    return OcrDecision(
        status="AVAILABLE",
        trigger_reasons=trigger_reasons or ["fixture_ocr_blocks_present"],
        ranked_image_candidates=ranked_candidates,
        admitted_blocks=admitted_blocks,
        rejected_blocks=rejected_blocks,
        contribution_chars=sum(len(str(block.get("text", ""))) for block in admitted_blocks),
        image_results=image_results,
        line_groups=line_groups,
        direct_fact_candidates=direct_fact_candidates,
        same_product_metrics=same_product_metrics,
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
        candidate_type = _candidate_type(lower_src, lower_alt, width=width, height=height, detail_hint=bool(candidate.get("detail_hint")))
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

        reason_codes: list[str] = []
        score = 0.0
        if width and height:
            area = width * height
            if area >= 300 * 300:
                score += min(area / 1_000_000, 1.5)
                reason_codes.append("area")
        else:
            score += 0.25
            reason_codes.append("unknown_size")

        if any(token in lower_src or token in lower_alt for token in PRIORITY_IMAGE_TOKENS):
            score += 0.35
            reason_codes.append("priority_token")
        if candidate.get("detail_hint") or any(token in lower_src for token in DETAIL_IMAGE_PATH_HINTS):
            score += 1.4
            reason_codes.append("detail_hint")
        if str(candidate.get("attribute", "")).lower() != "src":
            score += 0.2
            reason_codes.append("lazy_attribute")
        if lower_src.endswith(".webp"):
            score += 0.15
            reason_codes.append("webp")

        token_overlap = len(_matching_tokens(tokens, f"{lower_alt} {lower_src}"))
        if token_overlap:
            score += min(token_overlap * 0.18, 0.72)
            reason_codes.append("token_overlap")
        score += max(0.0, 0.15 - index * 0.02)

        estimated_text_density = _estimated_text_density(candidate_type, lower_src, lower_alt, width=width, height=height)
        score += estimated_text_density * 0.45
        if estimated_text_density >= 0.5:
            reason_codes.append("text_density")
        if candidate_type == "long_detail_banner":
            score += 0.45
            reason_codes.append("long_detail_banner")
        elif candidate_type == "table_like_image":
            score += 0.55
            reason_codes.append("table_like")
        elif candidate_type == "front_label_closeup":
            score += 0.25
            reason_codes.append("front_label")

        normalized["score"] = round(score, 4)
        normalized["candidate_type"] = candidate_type
        normalized["estimated_text_density"] = round(estimated_text_density, 4)
        normalized["needs_tiling"] = candidate_type == "long_detail_banner"
        normalized["selection_reason_codes"] = reason_codes
        normalized["ocr_pipeline_type"] = "structured_table" if candidate_type == "table_like_image" else "plain_text"
        ranked.append(normalized)

    ranked.sort(key=lambda item: (-float(item["score"]), str(item.get("src", ""))))
    for priority_rank, candidate in enumerate(ranked, start=1):
        candidate["same_page_priority_rank"] = priority_rank
    return ranked


def _estimated_text_density(
    candidate_type: str,
    lower_src: str,
    lower_alt: str,
    *,
    width: int | None,
    height: int | None,
) -> float:
    density = 0.15
    combined = f"{lower_src} {lower_alt}"
    if candidate_type == "table_like_image":
        density += 0.55
    elif candidate_type == "long_detail_banner":
        density += 0.35
    elif candidate_type == "front_label_closeup":
        density += 0.25
    if any(token in combined for token in SPEC_TOKENS):
        density += 0.2
    if any(token in combined for token in FRONT_LABEL_TOKENS):
        density += 0.12
    if width and height and min(width, height) >= 900:
        density += 0.08
    return min(density, 1.0)


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


def _candidate_type(
    lower_src: str,
    lower_alt: str,
    *,
    width: int | None,
    height: int | None,
    detail_hint: bool,
) -> str:
    combined = f"{lower_src} {lower_alt}"
    if width and height and height >= max(width * 2.2, 1200):
        return "long_detail_banner"
    if any(token in combined for token in TABLE_IMAGE_TOKENS):
        return "table_like_image"
    if len(CODELIKE_PATTERN.findall(combined)) >= 2:
        return "table_like_image"
    if any(token in combined for token in FRONT_LABEL_TOKENS):
        return "front_label_closeup"
    if width and height and detail_hint and max(width, height) <= 1100:
        return "front_label_closeup"
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
                "selection_reason_codes": list(result.get("selection_reason_codes", candidate.get("selection_reason_codes", []))),
                "estimated_text_density": result.get("estimated_text_density", candidate.get("estimated_text_density")),
                "needs_tiling": bool(result.get("needs_tiling", candidate.get("needs_tiling", False))),
                "pipeline_type": result.get("pipeline_type", candidate.get("ocr_pipeline_type", "plain_text")),
                "engine_used": result.get("engine_used"),
                "recognizer_lang": result.get("recognizer_lang"),
                "preprocessing_variant": result.get("preprocessing_variant"),
                "tile_mode": result.get("tile_mode"),
                "tile_count": int(result.get("tile_count", 1) or 1),
                "ocr_passes": list(result.get("ocr_passes", [])),
                "status": result.get("status", "pending"),
                "raw_block_count": int(result.get("raw_block_count", 0) or 0),
                "raw_char_count": int(result.get("raw_char_count", 0) or 0),
                "admitted_block_count": int(result.get("admitted_block_count", 0) or 0),
                "rejected_block_count": int(result.get("rejected_block_count", 0) or 0),
                "line_group_count": int(result.get("line_group_count", 0) or 0),
                "direct_fact_candidate_count": int(result.get("direct_fact_candidate_count", 0) or 0),
                "mean_same_product_score": float(result.get("mean_same_product_score", 0.0) or 0.0),
                "runtime_ms": int(result.get("runtime_ms", 0) or 0),
                "error": result.get("error"),
            }
        )
    return image_results


def _apply_block_counts(
    image_results: list[dict[str, Any]],
    admitted_blocks: list[dict[str, Any]],
    rejected_blocks: list[dict[str, Any]],
    line_groups: list[dict[str, Any]],
    direct_fact_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    admitted_by_src: dict[str, int] = {}
    rejected_by_src: dict[str, int] = {}
    group_by_src: dict[str, int] = {}
    direct_by_src: dict[str, int] = {}
    same_product_scores: dict[str, list[float]] = {}
    for block in admitted_blocks:
        src = str(block.get("image_src", "")).strip()
        if src:
            admitted_by_src[src] = admitted_by_src.get(src, 0) + 1
            same_product_scores.setdefault(src, []).append(float(block.get("same_product_score", 0.0) or 0.0))
    for block in rejected_blocks:
        src = str(block.get("image_src", "")).strip()
        if src:
            rejected_by_src[src] = rejected_by_src.get(src, 0) + 1
    for group in line_groups:
        src = str(group.get("image_src", "")).strip()
        if src:
            group_by_src[src] = group_by_src.get(src, 0) + 1
    for group in direct_fact_candidates:
        src = str(group.get("image_src", "")).strip()
        if src:
            direct_by_src[src] = direct_by_src.get(src, 0) + 1

    normalized_results: list[dict[str, Any]] = []
    for result in image_results:
        updated = dict(result)
        src = str(updated.get("image_src", "")).strip()
        scores = same_product_scores.get(src, [])
        updated["admitted_block_count"] = admitted_by_src.get(src, 0)
        updated["rejected_block_count"] = rejected_by_src.get(src, 0)
        updated["line_group_count"] = group_by_src.get(src, 0)
        updated["direct_fact_candidate_count"] = direct_by_src.get(src, 0)
        updated["mean_same_product_score"] = round(sum(scores) / len(scores), 4) if scores else 0.0
        normalized_results.append(updated)
    return normalized_results


def _admit_block(block: dict[str, Any], snapshot: NormalizedPageSnapshot) -> tuple[bool, dict[str, Any]]:
    normalized = dict(block)
    text = _extract_block_text(block)
    normalized["text"] = text
    tokens = _token_set(snapshot)
    matched_tokens = _matching_tokens(tokens, text.lower())
    text_quality_score = round(_text_quality_score(text, matched_tokens, block), 4)
    same_product_score = round(_same_product_score(text, matched_tokens, snapshot, block), 4)
    layout_trust_score = round(_layout_trust_score(block), 4)
    normalized["matched_tokens"] = matched_tokens
    normalized["text_quality_score"] = text_quality_score
    normalized["same_product_score"] = same_product_score
    normalized["layout_trust_score"] = layout_trust_score
    normalized["score"] = round((text_quality_score * 0.45) + (same_product_score * 0.35) + (layout_trust_score * 0.2), 4)

    if not text:
        normalized["rejection_reason"] = "empty_text"
        normalized["direct_evidence_eligible"] = False
        return False, normalized
    if _mostly_numeric_junk(text):
        normalized["rejection_reason"] = "mostly_numeric_junk"
        normalized["direct_evidence_eligible"] = False
        return False, normalized
    if _mostly_brand_repetition(text, snapshot):
        normalized["rejection_reason"] = "brand_only_repetition"
        normalized["direct_evidence_eligible"] = False
        return False, normalized
    if _duplicate_of_html_text(text, snapshot.decoded_text or ""):
        normalized["rejection_reason"] = "duplicate_of_direct_html"
        normalized["direct_evidence_eligible"] = False
        return False, normalized

    has_minimum_content = (
        len(text) >= 30
        or len(matched_tokens) >= 2
        or _has_explicit_product_field(text)
        or _should_preserve_short_image_block(text, matched_tokens, block)
    )
    if not has_minimum_content:
        normalized["rejection_reason"] = "too_short_without_product_tokens"
        normalized["direct_evidence_eligible"] = False
        return False, normalized

    if _contains_unrelated_product_names(text, matched_tokens, snapshot, block):
        normalized["rejection_reason"] = "unrelated_product_names"
        normalized["direct_evidence_eligible"] = False
        return False, normalized

    if any(token in text.lower() for token in PROMO_TOKENS) and not matched_tokens:
        normalized["rejection_reason"] = "promo_not_tied_to_product"
        normalized["direct_evidence_eligible"] = False
        return False, normalized

    normalized["direct_evidence_eligible"] = _direct_evidence_eligible(normalized)
    return True, normalized


def _extract_block_text(block: dict[str, Any]) -> str:
    for key in ("text", "content", "value", "ocr_text"):
        value = block.get(key)
        if value:
            return " ".join(str(value).split()).strip()
    return ""


def _text_quality_score(text: str, matched_tokens: list[str], block: dict[str, Any]) -> float:
    lowered = text.lower()
    score = min(len(text) / 120.0, 0.55)
    score += min(len(matched_tokens) * 0.14, 0.28)
    if any(token in lowered for token in SPEC_TOKENS):
        score += 0.12
    if MEASUREMENT_PATTERN.search(text):
        score += 0.12
    alpha_terms = TEXT_TERM_PATTERN.findall(text)
    if len(alpha_terms) >= 2:
        score += 0.08
    if block.get("pipeline_type") == "structured_table":
        score += 0.08
    if block.get("preprocessing_variant") not in {None, "", "original"}:
        score += 0.03
    return min(score, 1.0)


def _same_product_score(
    text: str,
    matched_tokens: list[str],
    snapshot: NormalizedPageSnapshot,
    block: dict[str, Any],
) -> float:
    lowered = text.lower()
    score = 0.0
    if matched_tokens:
        score += min(0.3 + len(matched_tokens) * 0.18, 0.72)
    product_name = str(snapshot.product_name or "").strip().lower()
    if product_name and product_name in lowered:
        score += 0.25
    product_terms = [term for term in re.findall(r"[A-Za-z0-9\uac00-\ud7a3.+-]{2,}", product_name) if len(term) >= 4]
    overlapping_terms = sum(1 for term in product_terms if term.lower() in lowered)
    if overlapping_terms:
        score += min(overlapping_terms * 0.08, 0.2)
    if _has_explicit_product_field(text):
        score += 0.28
        if snapshot.page_class_hint in {"commerce_pdp", "image_heavy_commerce_pdp"}:
            score += 0.08
        candidate_type = str(block.get("candidate_type", "") or "")
        if candidate_type in {"front_label_closeup", "long_detail_banner", "table_like_image"}:
            score += 0.06
    return min(score, 1.0)


def _layout_trust_score(block: dict[str, Any]) -> float:
    candidate_type = str(block.get("candidate_type", "general_detail_image") or "general_detail_image")
    if candidate_type == "table_like_image":
        score = 0.85
    elif candidate_type == "long_detail_banner":
        score = 0.74
    elif candidate_type == "front_label_closeup":
        score = 0.8
    else:
        score = 0.66
    if block.get("pipeline_type") == "structured_table":
        score += 0.08
    if block.get("tile_mode") == "vertical":
        score += 0.05
    if block.get("preprocessing_variant") not in {None, "", "original"}:
        score += 0.03
    return min(score, 1.0)


def _direct_evidence_eligible(block: dict[str, Any]) -> bool:
    same_product_score = float(block.get("same_product_score", 0.0) or 0.0)
    text_quality_score = float(block.get("text_quality_score", 0.0) or 0.0)
    layout_trust_score = float(block.get("layout_trust_score", 0.0) or 0.0)
    text = str(block.get("text", ""))
    candidate_type = str(block.get("candidate_type", "") or "")
    if same_product_score >= 0.45 and text_quality_score >= 0.35 and layout_trust_score >= 0.6:
        return True
    if _has_explicit_product_field(text) and same_product_score >= 0.28 and text_quality_score >= 0.18 and layout_trust_score >= 0.6:
        return True
    if candidate_type == "table_like_image" and layout_trust_score >= 0.8 and (MEASUREMENT_PATTERN.search(text) or any(token in text.lower() for token in SPEC_TOKENS)):
        return True
    return False


def _build_line_groups(admitted_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not admitted_blocks:
        return []
    ordered = sorted(
        admitted_blocks,
        key=lambda item: (
            str(item.get("image_src", "")),
            int(item.get("tile_index", 0) or 0),
            int(item.get("block_order", 0) or 0),
        ),
    )
    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for block in ordered:
        if not current:
            current = [block]
            continue
        if _should_merge_into_group(current, block):
            current.append(block)
            continue
        groups.append(_make_line_group(current))
        current = [block]
    if current:
        groups.append(_make_line_group(current))
    return groups


def _should_merge_into_group(current: list[dict[str, Any]], block: dict[str, Any]) -> bool:
    first = current[0]
    if str(first.get("image_src", "")) != str(block.get("image_src", "")):
        return False
    if int(first.get("tile_index", 0) or 0) != int(block.get("tile_index", 0) or 0):
        return False
    if str(first.get("candidate_type", "")) == "table_like_image":
        return False
    if len(current) >= 3:
        return False
    current_text = " ".join(str(item.get("text", "")) for item in current).strip()
    next_text = str(block.get("text", ""))
    if len(current_text) + len(next_text) > 96:
        return False
    shortish_current = all(len(str(item.get("text", ""))) <= 32 for item in current)
    return shortish_current and len(next_text) <= 32


def _make_line_group(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(str(block.get("text", "")).strip() for block in blocks if str(block.get("text", "")).strip()).strip()
    matched_tokens = sorted(
        {
            token
            for block in blocks
            for token in block.get("matched_tokens", [])
            if isinstance(token, str) and token.strip()
        }
    )
    group_like_block = {
        "pipeline_type": blocks[0].get("pipeline_type"),
        "preprocessing_variant": blocks[0].get("preprocessing_variant"),
    }
    text_quality_score = max(
        max(float(block.get("text_quality_score", 0.0) or 0.0) for block in blocks),
        _text_quality_score(text, matched_tokens, group_like_block),
    )
    same_product_score = max(float(block.get("same_product_score", 0.0) or 0.0) for block in blocks)
    layout_trust_score = max(float(block.get("layout_trust_score", 0.0) or 0.0) for block in blocks)
    group = {
        "text": text,
        "image_src": blocks[0].get("image_src"),
        "candidate_type": blocks[0].get("candidate_type"),
        "pipeline_type": blocks[0].get("pipeline_type"),
        "block_count": len(blocks),
        "matched_tokens": matched_tokens,
        "text_quality_score": round(text_quality_score, 4),
        "same_product_score": round(same_product_score, 4),
        "layout_trust_score": round(layout_trust_score, 4),
    }
    group["direct_evidence_eligible"] = any(bool(block.get("direct_evidence_eligible")) for block in blocks) or _direct_evidence_eligible(group)
    return group


def _extract_direct_fact_candidates(line_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, group in enumerate(line_groups, start=1):
        if not group.get("direct_evidence_eligible"):
            continue
        text = str(group.get("text", "")).strip()
        lowered = text.lower()
        if not text:
            continue
        if any(token in lowered for token in PROMO_TOKENS) and not group.get("matched_tokens"):
            continue
        if float(group.get("same_product_score", 0.0) or 0.0) < 0.45 and not (
            str(group.get("candidate_type", "")) == "table_like_image"
            and (MEASUREMENT_PATTERN.search(text) or any(token in lowered for token in SPEC_TOKENS))
        ) and not (
            _has_explicit_product_field(text)
            and float(group.get("same_product_score", 0.0) or 0.0) >= 0.28
        ):
            continue
        candidates.append(
            {
                **dict(group),
                "candidate_id": f"ocr_direct_{index:03d}",
                "source_type": "ocr_line_group",
            }
        )
    return candidates


def _same_product_metrics(
    admitted_blocks: list[dict[str, Any]],
    direct_fact_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not admitted_blocks:
        return {
            "mean_same_product_score": 0.0,
            "mean_text_quality_score": 0.0,
            "direct_candidate_count": len(direct_fact_candidates),
        }
    same_product_scores = [float(block.get("same_product_score", 0.0) or 0.0) for block in admitted_blocks]
    text_quality_scores = [float(block.get("text_quality_score", 0.0) or 0.0) for block in admitted_blocks]
    return {
        "mean_same_product_score": round(sum(same_product_scores) / len(same_product_scores), 4),
        "mean_text_quality_score": round(sum(text_quality_scores) / len(text_quality_scores), 4),
        "direct_candidate_count": len(direct_fact_candidates),
    }


def _has_explicit_product_field(text: str) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in EXPLICIT_PRODUCT_FIELD_TOKENS)


def _mostly_numeric_junk(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text)
    if not stripped:
        return True
    alnum = re.findall(r"[A-Za-z0-9\uac00-\ud7a3]", stripped)
    if not alnum:
        return True
    digit_ratio = sum(char.isdigit() for char in alnum) / len(alnum)
    return digit_ratio > 0.85 or (digit_ratio > 0.7 and len(set(alnum)) <= max(6, len(alnum) // 2))


def _mostly_brand_repetition(text: str, snapshot: NormalizedPageSnapshot) -> bool:
    words = re.findall(r"[A-Za-z0-9\uac00-\ud7a3]+", text.lower())
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
    alpha_terms = TEXT_TERM_PATTERN.findall(text)
    if len(alpha_terms) >= 2:
        return True
    if len(alpha_terms) == 1 and len(alpha_terms[0]) >= 8:
        return True
    if MEASUREMENT_PATTERN.search(text):
        return True
    if block.get("candidate_type") == "table_like_image" and CODELIKE_PATTERN.search(text):
        return True
    return False


def _token_set(snapshot: NormalizedPageSnapshot) -> set[str]:
    seeds = list(snapshot.primary_product_tokens)
    if snapshot.product_name:
        seeds.extend(re.findall(r"[A-Za-z0-9\uac00-\ud7a3.+-]{2,}", snapshot.product_name))
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
