from __future__ import annotations

import re
from collections import Counter
from typing import Any

from src.collection.models import NormalizedPageSnapshot, PageClassification
from src.ocr.models import OcrDecision

CATEGORY_HINTS = (
    ("무선 이어버드", ("airpods", "이어버드", "earbud", "earbuds")),
    ("노트북", ("macbook", "laptop", "notebook")),
    ("러닝화", ("cloudtilt", "shoe", "shoes", "sneaker", "running")),
    ("스킨케어", ("mask", "cream", "retinol", "sleeping", "skincare", "moisturizer", "serum")),
)

ATTRIBUTE_PATTERNS = (
    (r"\b\d+\s?(ml|g|kg|inch|in|gb|tb|mah|hz|w)\b", "attribute"),
    (r"(cpu|memory|battery|호환|성분|재질|용량|배터리|프로세서)", "attribute"),
)
USE_CASE_PATTERNS = (
    "night care",
    "overnight",
    "수면",
    "보습",
    "진정",
    "러닝",
    "운동",
    "작업",
    "업무",
)
PROBLEM_PATTERNS = (
    "건조",
    "민감",
    "피부 장벽",
    "problem",
    "solution",
    "트러블",
    "호환",
    "배터리",
)


def build_evidence_pack(
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    ocr_decision: OcrDecision | None = None,
) -> dict[str, object]:
    admitted_ocr_blocks = list(ocr_decision.admitted_blocks) if ocr_decision else list(snapshot.ocr_text_blocks)
    ocr_used = bool(admitted_ocr_blocks)
    direct_text_chars = len(snapshot.decoded_text or "")
    ocr_chars = sum(len(str(block.get("text", ""))) for block in admitted_ocr_blocks)
    ocr_dominant = ocr_chars > 0 and direct_text_chars > 0 and (ocr_chars / max(direct_text_chars, 1)) > 0.30
    canonical_product_name = _canonicalize_product_name(snapshot, classification.page_class)
    facts = _assemble_facts(snapshot, classification, admitted_ocr_blocks)

    return {
        "raw_url": snapshot.raw_url,
        "canonical_url": snapshot.canonical_url,
        "page_class": classification.page_class,
        "product_name": canonical_product_name or snapshot.product_name or snapshot.raw_url,
        "display_product_name": snapshot.product_name or snapshot.title or snapshot.raw_url,
        "canonical_product_name": canonical_product_name or snapshot.product_name or snapshot.raw_url,
        "locale_detected": snapshot.locale_detected,
        "market_locale": snapshot.market_locale,
        "sellability_state": snapshot.sellability_state,
        "stock_state": snapshot.stock_state,
        "sufficiency_state": snapshot.sufficiency_state,
        "quality_warning": snapshot.quality_warning or ocr_dominant,
        "fallback_used": snapshot.fallback_used,
        "weak_backfill_used": snapshot.weak_backfill_used,
        "ocr_used": ocr_used,
        "facts": facts,
        "direct_fact_count": sum(1 for fact in facts if fact["evidence_tier"] == "direct"),
        "fact_group_count": len({fact["type"] for fact in facts}),
        "quality_warning_inputs": _quality_warning_inputs(snapshot, ocr_dominant, ocr_used),
        "ocr_text_blocks": admitted_ocr_blocks,
    }


def _assemble_facts(
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    admitted_ocr_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_existing = [_normalize_fact(fact, snapshot.raw_url, index) for index, fact in enumerate(snapshot.facts, start=1)]
    candidates = list(normalized_existing)
    canonical_product_name = _canonicalize_product_name(snapshot, classification.page_class)

    if not _has_fact_type(candidates, "product_name"):
        product_name = canonical_product_name or snapshot.product_name or snapshot.title
        if product_name:
            candidates.append(
                _make_fact(
                    fact_type="product_name",
                    value=product_name,
                    normalized_value=product_name,
                    source="title" if snapshot.title else "snapshot",
                    source_uri=snapshot.raw_url,
                    evidence_tier="direct",
                    admissibility_tags=["product_identity"],
                    confidence=0.96,
                )
            )

    brand = _derive_brand(snapshot)
    if brand and not _has_fact_value(candidates, "brand", brand):
        candidates.append(
            _make_fact(
                fact_type="brand",
                value=brand,
                normalized_value=brand,
                source="title_tokens",
                source_uri=snapshot.raw_url,
                evidence_tier="direct",
                admissibility_tags=["product_identity"],
                confidence=0.88,
            )
        )

    category_value = _derive_category(snapshot, classification.page_class)
    if category_value and not _has_fact_value(candidates, "product_category", category_value):
        candidates.append(
            _make_fact(
                fact_type="product_category",
                value=category_value,
                normalized_value=category_value,
                source="page_class",
                source_uri=snapshot.raw_url,
                evidence_tier="inferred",
                admissibility_tags=["category"],
                confidence=0.82,
            )
        )

    if snapshot.price_signals and snapshot.sellability_state == "sellable" and not _has_fact_type(candidates, "price"):
        price_text = _extract_price_text(snapshot.decoded_text or "")
        if price_text:
            candidates.append(
                _make_fact(
                    fact_type="price",
                    value=price_text,
                    normalized_value=price_text,
                    source="decoded_text",
                    source_uri=snapshot.raw_url,
                    evidence_tier="direct",
                    admissibility_tags=["sellability", "commerce"],
                    confidence=0.84,
                )
            )

    candidates.extend(_derive_textual_facts(snapshot, admitted_ocr_blocks))
    return _dedupe_facts(candidates)


def _derive_textual_facts(snapshot: NormalizedPageSnapshot, admitted_ocr_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    sources = [
        ("decoded_text", snapshot.decoded_text or "", "direct"),
        *[(f"ocr:{index}", str(block.get("text", "")), "direct") for index, block in enumerate(admitted_ocr_blocks, start=1)],
    ]

    for source_name, text, tier in sources:
        if not text:
            continue
        for match, fact_type in _attribute_matches(text):
            facts.append(
                _make_fact(
                    fact_type="attribute" if fact_type == "attribute" else fact_type,
                    value=match,
                    normalized_value=match,
                    source=source_name,
                    source_uri=snapshot.raw_url,
                    evidence_tier=tier,
                    admissibility_tags=["attribute"] if fact_type == "attribute" else [fact_type],
                    confidence=0.74 if source_name.startswith("ocr:") else 0.82,
                )
            )
        for phrase in _keyword_hits(text, USE_CASE_PATTERNS):
            facts.append(
                _make_fact(
                    fact_type="use_case",
                    value=phrase,
                    normalized_value=phrase,
                    source=source_name,
                    source_uri=snapshot.raw_url,
                    evidence_tier=tier if source_name == "decoded_text" else "inferred",
                    admissibility_tags=["use_case"],
                    confidence=0.7 if source_name.startswith("ocr:") else 0.78,
                )
            )
        for phrase in _keyword_hits(text, PROBLEM_PATTERNS):
            facts.append(
                _make_fact(
                    fact_type="problem_solution",
                    value=phrase,
                    normalized_value=phrase,
                    source=source_name,
                    source_uri=snapshot.raw_url,
                    evidence_tier="inferred",
                    admissibility_tags=["problem_solution"],
                    confidence=0.68 if source_name.startswith("ocr:") else 0.76,
                )
            )
    return facts


def _attribute_matches(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    lowered = text.lower()
    for pattern, fact_type in ATTRIBUTE_PATTERNS:
        for match in re.findall(pattern, lowered, flags=re.IGNORECASE):
            value = match if isinstance(match, str) else " ".join(part for part in match if part)
            cleaned = " ".join(str(value).split()).strip()
            if cleaned:
                matches.append((cleaned, fact_type))
    return matches


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    hits = [keyword for keyword in keywords if keyword.lower() in lowered]
    return hits[:4]


def _derive_brand(snapshot: NormalizedPageSnapshot) -> str | None:
    if not snapshot.product_name:
        return None
    tokens = re.findall(r"[A-Za-z가-힣0-9]+", snapshot.product_name)
    if not tokens:
        return None
    first = tokens[0]
    if len(first) <= 1:
        return None
    return first


def _canonicalize_product_name(snapshot: NormalizedPageSnapshot, page_class: str) -> str | None:
    candidates = [
        _extract_direct_product_name(snapshot.facts),
        snapshot.product_name,
        snapshot.title,
    ]
    for candidate in candidates:
        cleaned = _clean_product_name(str(candidate or ""), page_class)
        if cleaned:
            return cleaned
    return None


def _extract_direct_product_name(facts: list[dict[str, Any]]) -> str | None:
    for fact in facts:
        if str(fact.get("type")) != "product_name":
            continue
        if str(fact.get("evidence_tier") or "direct") != "direct":
            continue
        value = str(fact.get("normalized_value") or fact.get("value") or "").strip()
        if value:
            return value
    return None


def _clean_product_name(value: str, page_class: str) -> str:
    cleaned = " ".join(value.split()).strip(" -|/")
    if not cleaned:
        return ""
    if page_class not in {"support_spec_page", "document_download_heavy_support_page"}:
        return cleaned

    lowered = cleaned.casefold()
    support_markers = (
        "apple 지원",
        "지원",
        "기술 사양",
        "사양",
        "specs",
        "spec",
        "tech specs",
        "technical specifications",
        "download",
        "manual",
    )
    for marker in support_markers:
        index = lowered.find(marker.casefold())
        if index > 0:
            cleaned = cleaned[:index].strip(" -|/")
            lowered = cleaned.casefold()

    patterns = (
        r"(?i)\bapple\s+(macbook\s+(?:pro|air)\s+\d{2})\b",
        r"(?i)\b(macbook\s+(?:pro|air)\s+\d{2})\b",
        r"(?i)\b(airpods(?:\s+pro)?(?:\s+\d+)?)\b",
        r"(?i)\b(ipad\s+(?:pro|air|mini)?(?:\s+\d+(?:th)?\s*gen)?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return " ".join(match.group(1).split())

    tokens = cleaned.split()
    if len(tokens) > 4:
        return " ".join(tokens[:4])
    return cleaned


def _derive_category(snapshot: NormalizedPageSnapshot, page_class: str) -> str | None:
    haystack = " ".join(
        part
        for part in (
            snapshot.product_name,
            snapshot.title,
            snapshot.meta_description,
            page_class,
        )
        if part
    ).lower()
    for category, hints in CATEGORY_HINTS:
        if any(hint in haystack for hint in hints):
            return category
    if "support" in page_class or "spec" in page_class:
        return "전자기기"
    return None


def _extract_price_text(text: str) -> str | None:
    match = re.search(r"(₩\s?\d[\d,]*|\$\s?\d[\d,]*|\b\d{2,3},\d{3}\b)", text)
    if not match:
        return None
    return match.group(1).replace(" ", "")


def _normalize_fact(fact: dict[str, Any], source_uri: str, ordinal: int) -> dict[str, Any]:
    normalized = dict(fact)
    normalized.setdefault("fact_id", f"f{ordinal:03d}")
    normalized.setdefault("normalized_value", normalized.get("value"))
    normalized.setdefault("source_uri", source_uri)
    normalized.setdefault("page_scope", "exact")
    normalized.setdefault("evidence_tier", "direct")
    normalized.setdefault("admissibility_tags", [])
    normalized.setdefault("confidence", 0.8)
    return normalized


def _make_fact(
    *,
    fact_type: str,
    value: str,
    normalized_value: str,
    source: str,
    source_uri: str,
    evidence_tier: str,
    admissibility_tags: list[str],
    confidence: float,
) -> dict[str, Any]:
    return {
        "type": fact_type,
        "value": value,
        "normalized_value": normalized_value,
        "source": source,
        "source_uri": source_uri,
        "page_scope": "exact",
        "evidence_tier": evidence_tier,
        "admissibility_tags": admissibility_tags,
        "confidence": round(confidence, 2),
    }


def _dedupe_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    counters: Counter[str] = Counter()
    for fact in facts:
        fact_type = str(fact.get("type") or "").strip()
        normalized_value = str(fact.get("normalized_value") or fact.get("value") or "").strip()
        if not fact_type or not normalized_value:
            continue
        key = (fact_type.casefold(), normalized_value.casefold())
        if key in seen:
            continue
        seen.add(key)
        counters[fact_type] += 1
        enriched = dict(fact)
        enriched["fact_id"] = f"f{len(deduped) + 1:03d}"
        deduped.append(enriched)
    deduped.sort(key=lambda item: (item["type"], item["fact_id"]))
    return deduped


def _has_fact_type(facts: list[dict[str, Any]], fact_type: str) -> bool:
    return any(str(fact.get("type")) == fact_type for fact in facts)


def _has_fact_value(facts: list[dict[str, Any]], fact_type: str, value: str) -> bool:
    target = value.casefold()
    return any(
        str(fact.get("type")) == fact_type
        and str(fact.get("normalized_value") or fact.get("value") or "").casefold() == target
        for fact in facts
    )


def _quality_warning_inputs(snapshot: NormalizedPageSnapshot, ocr_dominant: bool, ocr_used: bool) -> list[str]:
    inputs: list[str] = []
    if snapshot.fallback_used:
        inputs.append("fallback_used")
    if snapshot.weak_backfill_used:
        inputs.append("weak_backfill_used")
    if snapshot.sufficiency_state == "borderline":
        inputs.append("borderline_sufficiency")
    if snapshot.page_class_hint in {"image_heavy_commerce_pdp", "support_spec_page", "document_download_heavy_support_page"}:
        inputs.append(f"page_class:{snapshot.page_class_hint}")
    if ocr_used:
        inputs.append("ocr_used")
    if ocr_dominant:
        inputs.append("ocr_dominant")
    return inputs
