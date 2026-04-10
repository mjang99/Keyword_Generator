from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from src.collection.models import NormalizedPageSnapshot, PageClassification
from src.ocr.models import OcrDecision

COMMERCE_PAGE_CLASSES = {
    "commerce_pdp",
    "image_heavy_commerce_pdp",
    "marketing_only_pdp",
    "product_marketing_page",
}
SUPPORT_PAGE_CLASSES = {
    "support_spec_page",
    "document_download_heavy_support_page",
}

CATEGORY_HINTS = (
    ("wireless earbuds", ("airpods", "earbud", "earbuds", "wireless earbuds")),
    ("laptop", ("macbook", "laptop", "notebook")),
    ("running shoes", ("cloudtilt", "shoe", "shoes", "sneaker", "running")),
    ("skincare", ("mask", "cream", "retinol", "sleeping", "skincare", "moisturizer", "serum")),
)
SUPPORT_TITLE_MARKERS = (
    "apple support",
    "support",
    "tech specs",
    "specs",
    "spec",
    "technical specifications",
    "download",
    "manual",
)
STORE_SUFFIX_MARKERS = (
    "official store",
    "official",
    "online store",
    "korea",
    "kr",
)
MARKETPLACE_HOST_TOKENS = {
    "amazon",
    "coupang",
    "gmarket",
    "11st",
    "smartstore",
    "naver",
    "oliveyoung",
}
KNOWN_HOST_BRANDS = {
    "laneige": "Laneige",
    "aesop": "Aesop",
    "apple": "Apple",
    "drjart": "Dr.Jart+",
    "on": "On",
    "onrunning": "On",
}
GENERIC_ATTRIBUTE_TERMS = {"ingredient", "material", "volume", "battery", "compatibility", "cpu", "memory"}

MEASUREMENT_PATTERN = re.compile(r"\b\d+\s?(?:ml|g|kg|oz|inch|in|gb|tb|mah|hz|w)\b", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"(?:\$\s?\d[\d,]*|\b\d{2,3},\d{3}\b)(?:원)?")
ATTRIBUTE_PATTERNS = (
    (MEASUREMENT_PATTERN, "volume"),
    (re.compile(r"\b(?:cpu|memory|battery|compatibility|ingredient|material|volume|processor)\b", re.IGNORECASE), "attribute"),
)

INGREDIENT_PATTERNS = (
    re.compile(r"(?:\uc21c\ub3c4\s*\d+%?\s*)?(?:\ucd08\uc21c\uc218\s*)?(\ub808\ud2f0\ub180|retinol)", re.IGNORECASE),
    re.compile(r"(\ud2b8\ub9ac\ud39c\ud0c0\uc774\ub4dc|tripeptide)", re.IGNORECASE),
    re.compile(r"((?:\d+\s*d\s*)?(?:\ud788\uc54c\ub8e8\ub860\uc0b0|hyaluronic acid))", re.IGNORECASE),
    re.compile(r"(\uc138\ub77c\ub9c8\uc774\ub4dc|ceramide)", re.IGNORECASE),
    re.compile(r"(\ub098\uc774\uc544\uc2e0\uc544\ub9c8\uc774\ub4dc|niacinamide)", re.IGNORECASE),
    re.compile(r"(\uc2a4\ucfe0\uc54c\ub780|squalane)", re.IGNORECASE),
    re.compile(r"(\ucf5c\ub77c\uac90|collagen)", re.IGNORECASE),
    re.compile(r"(\ud39c\ud0c0\uc774\ub4dc|peptide)", re.IGNORECASE),
)
TECHNOLOGY_PATTERNS = (
    re.compile(r"\b([A-Za-z][A-Za-z0-9.+-]{3,}(?:\s?[A-Za-z0-9.+-]+){0,2})\b"),
    re.compile(r"((?:\d+\s*d\s*)?(?:\ud788\uc54c\ub8e8\ub860\uc0b0|hyaluronic acid))", re.IGNORECASE),
)
CATALOG_FORM_TOKENS = {
    "cleanser",
    "skin",
    "mist",
    "lotion",
    "emulsion",
    "serum",
    "essence",
    "gel",
    "cream",
    "mask",
    "toner",
}
CATALOG_BLOCK_MARKERS = {
    "view all",
    "by type",
    "category",
    "categories",
    "lineup",
}
BADGE_BLOCK_TOKENS = {
    "BEST SELLER",
    "NEW ARRIVAL",
    "AWARD WINNER",
    "INTERNATIONAL",
    "LBLL",
}
CATALOG_FORM_TOKENS.update(
    {
        "cleanser",
        "skin",
        "mist",
        "lotion",
        "emulsion",
        "serum",
        "essence",
        "gel",
        "cream",
        "mask",
        "toner",
    }
)
CATALOG_BLOCK_MARKERS.update(
    {
        "view all",
        "by type",
        "all products",
        "category",
        "categories",
        "lineup",
    }
)
BADGE_BLOCK_TOKENS.update(
    {
        "BESTSELLER",
        "LIMITED",
        "EXCLUSIVE",
    }
)
ALLOWED_FACT_LIFT_TYPES = {
    "benefit",
    "key_ingredient",
    "usage",
    "use_case",
    "problem_solution",
    "volume",
    "variant",
    "texture",
}
FACT_LIFT_SYSTEM_PROMPT = (
    "You extract evidence facts from grounded product-page text. "
    "Return JSON only. "
    "Schema: {\"facts\": [{\"type\": str, \"value\": str, \"source_field\": str, \"source_quote\": str}]}. "
    "Allowed types: benefit, key_ingredient, usage, use_case, problem_solution, volume, variant, texture. "
    "Use only exact text supported by the provided source field. "
    "Do not invent facts, normalize prices, or infer unsupported claims."
)


def build_evidence_pack(
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    ocr_decision: OcrDecision | None = None,
) -> dict[str, object]:
    admitted_ocr_blocks = list(getattr(ocr_decision, "admitted_blocks", [])) if ocr_decision else list(snapshot.ocr_text_blocks)
    ocr_line_groups = list(getattr(ocr_decision, "line_groups", [])) if ocr_decision else []
    ocr_direct_fact_candidates = list(getattr(ocr_decision, "direct_fact_candidates", [])) if ocr_decision else []
    ocr_used = bool(admitted_ocr_blocks)
    direct_text_chars = len(snapshot.decoded_text or "")
    ocr_chars = sum(len(str(block.get("text", ""))) for block in admitted_ocr_blocks)
    ocr_dominant = ocr_chars > 0 and direct_text_chars > 0 and (ocr_chars / max(direct_text_chars, 1)) > 0.30
    canonical_product_name = _canonicalize_product_name(snapshot, classification.page_class)
    facts = _assemble_facts(snapshot, classification, admitted_ocr_blocks, ocr_direct_fact_candidates)
    thin_pack = _is_thin_pack(facts, classification.page_class)

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
        "quality_warning": snapshot.quality_warning or ocr_dominant or thin_pack,
        "fallback_used": snapshot.fallback_used,
        "fallback_reason": snapshot.fallback_reason,
        "preprocessing_source": snapshot.preprocessing_source,
        "weak_backfill_used": snapshot.weak_backfill_used,
        "ocr_used": ocr_used,
        "facts": facts,
        "direct_fact_count": sum(1 for fact in facts if fact["evidence_tier"] == "direct"),
        "fact_group_count": len({fact["type"] for fact in facts}),
        "quality_warning_inputs": _quality_warning_inputs(snapshot, ocr_dominant, ocr_used, thin_pack),
        "ocr_text_blocks": admitted_ocr_blocks,
        "ocr_line_groups": ocr_line_groups,
        "ocr_direct_fact_candidates": ocr_direct_fact_candidates,
    }


def _assemble_facts(
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    admitted_ocr_blocks: list[dict[str, Any]],
    ocr_direct_fact_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_existing = [_normalize_fact(fact, snapshot.raw_url, index) for index, fact in enumerate(snapshot.facts, start=1)]
    candidates = list(normalized_existing)

    structured_facts, structured_context = _derive_structured_facts(snapshot, classification.page_class)
    for fact in structured_facts:
        if not _has_fact_value(candidates, str(fact["type"]), str(fact["normalized_value"])):
            candidates.append(fact)

    canonical_product_name = _canonicalize_product_name(snapshot, classification.page_class, structured_context=structured_context)
    if not _has_fact_type(candidates, "product_name"):
        product_name = canonical_product_name or snapshot.product_name or snapshot.title
        if product_name:
            candidates.append(
                _make_fact(
                    fact_type="product_name",
                    value=product_name,
                    normalized_value=product_name,
                    source="structured_data.name" if structured_context.get("product_name") else ("title" if snapshot.title else "snapshot"),
                    source_uri=snapshot.raw_url,
                    evidence_tier="direct",
                    admissibility_tags=["product_identity"],
                    confidence=0.96,
                )
            )

    brand = _derive_brand(snapshot, structured_context=structured_context)
    if brand and not _has_fact_value(candidates, "brand", brand):
        candidates.append(
            _make_fact(
                fact_type="brand",
                value=brand,
                normalized_value=brand,
                source="structured_data.brand" if structured_context.get("brand") else "title_or_host",
                source_uri=snapshot.raw_url,
                evidence_tier="direct",
                admissibility_tags=["product_identity"],
                confidence=0.9 if structured_context.get("brand") else 0.85,
            )
        )

    category_value = _derive_category(snapshot, classification.page_class, structured_context=structured_context)
    if category_value and not _has_fact_value(candidates, "product_category", category_value):
        candidates.append(
            _make_fact(
                fact_type="product_category",
                value=category_value,
                normalized_value=category_value,
                source="structured_data.category" if structured_context.get("category") else "category_heuristic",
                source_uri=snapshot.raw_url,
                evidence_tier="direct" if structured_context.get("category") else "inferred",
                admissibility_tags=["product_identity", "category"],
                confidence=0.93 if structured_context.get("category") else 0.82,
            )
        )

    price_text = _derive_price(snapshot, classification.page_class, structured_context=structured_context)
    if price_text and not _has_fact_type(candidates, "price"):
        candidates.append(
            _make_fact(
                fact_type="price",
                value=price_text,
                normalized_value=price_text,
                source="structured_data.offers.price" if structured_context.get("price") == price_text else "decoded_text",
                source_uri=snapshot.raw_url,
                evidence_tier="direct",
                admissibility_tags=["sellability", "commerce"],
                confidence=0.9 if structured_context.get("price") == price_text else 0.84,
            )
        )

    candidates.extend(
        _derive_textual_facts(
            snapshot,
            classification.page_class,
            admitted_ocr_blocks,
            ocr_direct_fact_candidates,
            structured_context,
        )
    )
    candidates = _dedupe_facts(candidates)

    fallback_facts = _derive_bedrock_fallback_facts(snapshot, classification, candidates, structured_context)
    if fallback_facts:
        candidates.extend(fallback_facts)
        candidates = _dedupe_facts(candidates)

    return candidates


def _derive_structured_facts(
    snapshot: NormalizedPageSnapshot,
    page_class: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    facts: list[dict[str, Any]] = []
    context: dict[str, str] = {}
    product_items = _structured_product_items(snapshot.structured_data)
    breadcrumb_items = _structured_breadcrumb_items(snapshot.structured_data)

    product_name = _structured_product_name(product_items)
    if product_name:
        context["product_name"] = product_name

    brand = _structured_brand_name(product_items)
    if brand:
        context["brand"] = brand
        facts.append(
            _make_fact(
                fact_type="brand",
                value=brand,
                normalized_value=brand,
                source="structured_data.brand",
                source_uri=snapshot.raw_url,
                evidence_tier="direct",
                admissibility_tags=["product_identity"],
                confidence=0.99,
            )
        )

    category = _structured_category_name(product_items, breadcrumb_items)
    if category:
        context["category"] = category

    price = _structured_price_value(product_items)
    if price:
        context["price"] = price

    descriptions = _structured_description_texts(product_items)
    if descriptions:
        context["description"] = "\n".join(descriptions)

    for description in descriptions:
        facts.extend(
            _derive_semantic_text_facts(
                description,
                source_name="structured_data.description",
                source_uri=snapshot.raw_url,
                page_class=page_class,
                tier="direct",
                confidence_bias=0.04,
            )
        )

    return facts, context


def _derive_textual_facts(
    snapshot: NormalizedPageSnapshot,
    page_class: str,
    admitted_ocr_blocks: list[dict[str, Any]],
    ocr_direct_fact_candidates: list[dict[str, Any]],
    structured_context: dict[str, str],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    decoded_blocks = _text_source_entries(snapshot, structured_context)
    source_entries = [
        ("title", snapshot.title or "", "direct", 0.06),
        ("meta_description", snapshot.meta_description or "", "direct", 0.05),
        ("structured_data.description", structured_context.get("description", ""), "direct", 0.04),
    ]
    source_entries.extend(decoded_blocks)
    if ocr_direct_fact_candidates:
        source_entries.extend(
            (f"ocr_direct:{index}", str(block.get("text", "")), "direct", -0.03)
            for index, block in enumerate(ocr_direct_fact_candidates, start=1)
        )
    else:
        source_entries.extend(
            (f"ocr:{index}", str(block.get("text", "")), "direct", -0.08)
            for index, block in enumerate(admitted_ocr_blocks, start=1)
        )

    for source_name, text, tier, confidence_bias in source_entries:
        if not text:
            continue
        facts.extend(
            _derive_semantic_text_facts(
                text,
                source_name=source_name,
                source_uri=snapshot.raw_url,
                page_class=page_class,
                tier=tier,
                confidence_bias=confidence_bias,
            )
        )

    return facts


def _text_source_entries(
    snapshot: NormalizedPageSnapshot,
    structured_context: dict[str, str],
) -> list[tuple[str, str, str, float]]:
    product_name = _canonicalize_product_name(snapshot, snapshot.page_class_hint or "commerce_pdp", structured_context=structured_context) or ""
    brand = _derive_brand(snapshot, structured_context=structured_context) or ""
    blocks = [block for block in snapshot.visible_text_blocks if str(block).strip()]
    had_candidate_blocks = bool(blocks)
    entries: list[tuple[str, str, str, float]] = []
    for index, block in enumerate(blocks, start=1):
        if _drop_text_block(block, product_name=product_name, brand=brand):
            continue
        entries.append((f"decoded_text:{index}", block, "direct", 0.0))
    if snapshot.decoded_text:
        if not had_candidate_blocks:
            entries.extend(_decoded_text_fallback_entries(snapshot.decoded_text, product_name=product_name, brand=brand))
        elif _visible_blocks_too_sparse(entries, snapshot.decoded_text):
            seen = {text for _, text, _, _ in entries}
            for fallback_entry in _decoded_text_fallback_entries(snapshot.decoded_text, product_name=product_name, brand=brand):
                if fallback_entry[1] in seen:
                    continue
                entries.append(fallback_entry)
                seen.add(fallback_entry[1])
    return entries


def _visible_blocks_too_sparse(
    entries: list[tuple[str, str, str, float]],
    decoded_text: str,
) -> bool:
    if not decoded_text.strip():
        return False
    if not entries:
        return True
    visible_chars = sum(len(text) for _, text, _, _ in entries)
    decoded_chars = len(decoded_text)
    if len(entries) <= 1 and decoded_chars >= 400:
        return True
    return visible_chars < min(180, max(80, decoded_chars // 10))


def _decoded_text_fallback_entries(
    decoded_text: str,
    *,
    product_name: str,
    brand: str,
) -> list[tuple[str, str, str, float]]:
    entries: list[tuple[str, str, str, float]] = []
    for index, block in enumerate((part.strip() for part in re.split(r"\s{2,}|\n+", decoded_text)), start=1):
        if not block:
            continue
        if _drop_text_block(block, product_name=product_name, brand=brand):
            continue
        entries.append((f"decoded_fallback:{index}", block, "direct", -0.02))
    if not entries:
        entries.append(("decoded_text", decoded_text, "direct", 0.0))
    return entries


def _drop_text_block(
    block: str,
    *,
    product_name: str,
    brand: str,
) -> bool:
    text = " ".join(str(block).split()).strip()
    if len(text) <= 1:
        return True
    if _looks_like_url_text(text):
        return True

    lowered = text.casefold()
    if any(token.casefold() in lowered for token in BADGE_BLOCK_TOKENS):
        return True
    if _all_caps_badge_block(text):
        return True

    catalog_hits = _catalog_form_token_count(text)
    has_scope = _has_product_scope(text, product_name=product_name, brand=brand)
    if any(marker.casefold() in lowered for marker in CATALOG_BLOCK_MARKERS):
        return True
    if catalog_hits >= 3 and not has_scope:
        return True
    if catalog_hits >= 5:
        return True
    return False


def _catalog_form_token_count(text: str) -> int:
    lowered = text.casefold()
    return sum(1 for token in CATALOG_FORM_TOKENS if token.casefold() in lowered)


def _has_product_scope(
    text: str,
    *,
    product_name: str,
    brand: str,
) -> bool:
    lowered = text.casefold()
    if brand and brand.casefold() in lowered:
        return True
    tokens = [
        token.casefold()
        for token in re.findall(r"[\\w.+-]+", product_name, flags=re.UNICODE)
        if len(token) >= 2
    ]
    return any(token in lowered for token in tokens)


def _all_caps_badge_block(text: str) -> bool:
    alpha_tokens = re.findall(r"[A-Za-z][A-Za-z0-9.+-]*", text)
    if not alpha_tokens or len(alpha_tokens) > 6:
        return False
    return all(token.upper() == token for token in alpha_tokens)


def _looks_like_url_text(text: str) -> bool:
    lowered = text.casefold()
    return bool(re.search(r"https?://|www\.|\.html(?:\b|$)", lowered))


def _derive_semantic_text_facts(
    text: str,
    *,
    source_name: str,
    source_uri: str,
    page_class: str,
    tier: str,
    confidence_bias: float,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    lowered = text.lower()

    measurements = _measurement_matches(text)
    if measurements:
        unique_measurements = _unique_texts(measurements)
        for measurement in unique_measurements[:4]:
            facts.append(
                _make_fact(
                    fact_type="volume",
                    value=measurement,
                    normalized_value=measurement,
                    source=source_name,
                    source_uri=source_uri,
                    evidence_tier=tier,
                    admissibility_tags=["attribute"],
                    confidence=_bounded_confidence(0.86 + confidence_bias),
                )
            )
        if len(unique_measurements) >= 2:
            variant_value = " / ".join(unique_measurements[:3])
            facts.append(
                _make_fact(
                    fact_type="variant",
                    value=variant_value,
                    normalized_value=variant_value,
                    source=source_name,
                    source_uri=source_uri,
                    evidence_tier=tier,
                    admissibility_tags=["attribute"],
                    confidence=_bounded_confidence(0.84 + confidence_bias),
                )
            )

    for phrase in _benefit_phrases_from_text(text):
        facts.append(
            _make_fact(
                fact_type="benefit",
                value=phrase,
                normalized_value=phrase,
                source=source_name,
                source_uri=source_uri,
                evidence_tier=tier,
                admissibility_tags=["benefit"],
                confidence=_bounded_confidence(0.84 + confidence_bias),
            )
        )

    for ingredient in _ingredient_matches(text):
        tags = ["attribute", "benefit"]
        if _looks_like_brand_technology(ingredient):
            tags = ["attribute", "brand_technology"]
        facts.append(
            _make_fact(
                fact_type="key_ingredient",
                value=ingredient,
                normalized_value=ingredient,
                source=source_name,
                source_uri=source_uri,
                evidence_tier=tier,
                admissibility_tags=tags,
                confidence=_bounded_confidence(0.86 + confidence_bias),
            )
        )

    for technology in _technology_matches(text):
        facts.append(
            _make_fact(
                fact_type="attribute",
                value=technology,
                normalized_value=technology,
                source=source_name,
                source_uri=source_uri,
                evidence_tier=tier,
                admissibility_tags=["attribute", "brand_technology"],
                confidence=_bounded_confidence(0.8 + confidence_bias),
            )
        )

    for match, fact_type in _attribute_matches(text):
        if fact_type == "attribute" and match.casefold() in GENERIC_ATTRIBUTE_TERMS:
            continue
        facts.append(
            _make_fact(
                fact_type=fact_type,
                value=match,
                normalized_value=match,
                source=source_name,
                source_uri=source_uri,
                evidence_tier=tier,
                admissibility_tags=["attribute"],
                confidence=_bounded_confidence(0.8 + confidence_bias),
            )
        )

    if page_class in SUPPORT_PAGE_CLASSES:
        facts = [fact for fact in facts if str(fact.get("type")) != "price"]
    return facts


def _derive_bedrock_fallback_facts(
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    facts: list[dict[str, Any]],
    structured_context: dict[str, str],
) -> list[dict[str, Any]]:
    if classification.page_class not in COMMERCE_PAGE_CLASSES:
        return []
    if not _is_thin_pack(facts, classification.page_class):
        return []

    from src.keyword_generation.bedrock_adapter import should_use_bedrock

    if not should_use_bedrock():
        return []

    source_map = {
        "title": snapshot.title or "",
        "meta_description": snapshot.meta_description or "",
        "structured_data.description": structured_context.get("description", ""),
        "decoded_text": snapshot.decoded_text or "",
    }
    source_map = {key: value for key, value in source_map.items() if value}
    if not source_map:
        return []

    prompt_payload = {
        "page_class": classification.page_class,
        "product_name": structured_context.get("product_name") or snapshot.product_name or snapshot.title,
        "brand": structured_context.get("brand") or _derive_brand(snapshot, structured_context=structured_context),
        "sources": source_map,
    }

    try:
        from src.clients.bedrock import BedrockRuntimeSettings, converse_text

        _, response_text = converse_text(
            json.dumps(prompt_payload, ensure_ascii=False),
            system_prompt=FACT_LIFT_SYSTEM_PROMPT,
            settings=BedrockRuntimeSettings.from_env(),
        )
        payload = json.loads(response_text)
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    derived: list[dict[str, Any]] = []
    for item in payload.get("facts") or []:
        if not isinstance(item, dict):
            continue
        fact_type = str(item.get("type") or "").strip()
        value = str(item.get("value") or "").strip()
        source_field = str(item.get("source_field") or "").strip()
        source_quote = str(item.get("source_quote") or value).strip()
        if fact_type not in ALLOWED_FACT_LIFT_TYPES or not value or source_field not in source_map:
            continue
        if source_quote.casefold() not in source_map[source_field].casefold():
            continue
        tags = (
            ["use_case"]
            if fact_type in {"usage", "use_case"}
            else ["benefit"]
            if fact_type == "benefit"
            else ["problem_solution"]
            if fact_type == "problem_solution"
            else ["attribute"]
        )
        derived.append(
            _make_fact(
                fact_type=fact_type,
                value=value,
                normalized_value=value,
                source=f"bedrock_fact_lift:{source_field}",
                source_uri=snapshot.raw_url,
                evidence_tier="direct",
                admissibility_tags=tags,
                confidence=0.72,
            )
        )
    return derived


def _measurement_matches(text: str) -> list[str]:
    return [" ".join(match.split()) for match in MEASUREMENT_PATTERN.findall(text)]


def _attribute_matches(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for pattern, fact_type in ATTRIBUTE_PATTERNS:
        for match in pattern.findall(text):
            value = match if isinstance(match, str) else " ".join(part for part in match if part)
            cleaned = " ".join(str(value).split()).strip()
            if cleaned:
                matches.append((cleaned, fact_type))
    return matches




def _benefit_phrases_from_text(text: str) -> list[str]:
    phrases: list[str] = []
    pattern = r"([\w\s,/+-]+?)\s*(?:\uac1c\uc120|\uc644\ud654|\ucf00\uc5b4|\ucee4\ubc84|improves?|supports?)"
    for match in re.findall(pattern, text, flags=re.IGNORECASE):
        for fragment in re.split(r"[,/]", match):
            cleaned = " ".join(fragment.split()).strip()
            if not cleaned or len(cleaned) <= 1:
                continue
            if cleaned.casefold() in {"my first", "skin", "product", "\ub098\uc758 \uccab", "\ud53c\ubd80", "\uc81c\ud488"}:
                continue
            if not cleaned.endswith(("\uac1c\uc120", "\uc644\ud654", "\ucf00\uc5b4", "\ucee4\ubc84")):
                if any(token in cleaned for token in ("\uc8fc\ub984", "\ubaa8\uacf5", "\ud0c4\ub825", "wrinkle", "pore", "firm")):
                    phrases.append(f"{cleaned} improvement")
                else:
                    phrases.append(cleaned)
    return _unique_texts(phrases)[:6]


def _ingredient_matches(text: str) -> list[str]:
    values: list[str] = []
    for pattern in INGREDIENT_PATTERNS:
        for match in pattern.findall(text):
            cleaned = " ".join(str(match).split()).strip()
            if cleaned:
                values.append(cleaned)
    return _unique_texts(values)[:6]

def _technology_matches(text: str) -> list[str]:
    values: list[str] = []
    for pattern in TECHNOLOGY_PATTERNS:
        for match in pattern.findall(text):
            cleaned = " ".join(str(match).split()).strip()
            if not cleaned:
                continue
            if not _looks_like_brand_technology(cleaned):
                continue
            values.append(cleaned)
    return _unique_texts(values)[:4]


def _looks_like_brand_technology(value: str) -> bool:
    lowered = value.casefold()
    if _looks_like_url_text(value):
        return False
    if any(token.casefold() in lowered for token in BADGE_BLOCK_TOKENS):
        return False
    if any(token in lowered for token in ("tox", "complex", "technology", "tech", "5d", "3d", "micro")):
        return True
    if len(value.split()) > 1 and _all_caps_badge_block(value):
        return False
    return bool(re.search(r"\b(?:[A-Z]{2,}[A-Za-z0-9.+-]*|\d+D)\b", value))


def _derive_brand(snapshot: NormalizedPageSnapshot, *, structured_context: dict[str, str] | None = None) -> str | None:
    context = structured_context or {}
    if context.get("brand"):
        return context["brand"]

    host_brand = _brand_from_url(snapshot.raw_url or snapshot.canonical_url or "")
    title_candidates = [snapshot.title or "", snapshot.product_name or ""]
    for candidate in title_candidates:
        for segment in _title_segments(candidate):
            cleaned = _strip_store_suffixes(segment)
            if not cleaned:
                continue
            tokens = re.findall(r"[\\w.+-]+", cleaned, flags=re.UNICODE)
            if not tokens:
                continue
            first = tokens[0]
            lowered = first.casefold()
            if len(first) <= 1 or lowered in {"kr", "korea"}:
                continue
            if host_brand and lowered == host_brand.casefold():
                return host_brand
            if lowered in {"apple", "aesop", "laneige", "dr.jart+", "drjart", "on"}:
                return first

    if host_brand:
        return host_brand
    return None


def _canonicalize_product_name(
    snapshot: NormalizedPageSnapshot,
    page_class: str,
    *,
    structured_context: dict[str, str] | None = None,
) -> str | None:
    context = structured_context or {}
    candidates = [
        _extract_direct_product_name(snapshot.facts),
        context.get("product_name"),
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
    cleaned = _strip_store_suffixes(cleaned)
    if page_class not in SUPPORT_PAGE_CLASSES:
        return cleaned

    lowered = cleaned.casefold()
    for marker in SUPPORT_TITLE_MARKERS:
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


def _title_segments(value: str) -> list[str]:
    if not value:
        return []
    normalized = " ".join(value.split())
    segments = [normalized]
    if "|" in normalized:
        segments.extend(part.strip() for part in normalized.split("|"))
    if " - " in normalized:
        segments.extend(part.strip() for part in normalized.split(" - "))
    return [segment for segment in segments if segment]


def _strip_store_suffixes(value: str) -> str:
    cleaned = " ".join(value.split()).strip(" -|/")
    if not cleaned:
        return ""

    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip(" -|/")

    parts = [part.strip() for part in cleaned.split(" - ") if part.strip()]
    if len(parts) > 1:
        retained: list[str] = []
        for part in parts:
            lowered = part.casefold()
            if any(marker in lowered for marker in SUPPORT_TITLE_MARKERS):
                break
            if any(lowered == marker.casefold() for marker in STORE_SUFFIX_MARKERS):
                break
            retained.append(part)
        if retained:
            cleaned = " - ".join(retained).strip(" -|/")

    lowered = cleaned.casefold()
    for marker in STORE_SUFFIX_MARKERS:
        suffix = marker.casefold()
        if lowered.endswith(f" {suffix}"):
            cleaned = cleaned[: -len(suffix)].strip(" -|/")
            lowered = cleaned.casefold()
    return cleaned


def _derive_category(
    snapshot: NormalizedPageSnapshot,
    page_class: str,
    *,
    structured_context: dict[str, str] | None = None,
) -> str | None:
    context = structured_context or {}
    if context.get("category") and not _looks_like_url_text(context["category"]):
        return context["category"]

    haystack = " ".join(
        part
        for part in (
            snapshot.product_name,
            snapshot.title,
            snapshot.meta_description,
            snapshot.canonical_url,
            page_class,
        )
        if part
    ).lower()
    for category, hints in CATEGORY_HINTS:
        if any(hint in haystack for hint in hints):
            return category
    if page_class in SUPPORT_PAGE_CLASSES:
        return "electronics"
    return None


def _derive_price(
    snapshot: NormalizedPageSnapshot,
    page_class: str,
    *,
    structured_context: dict[str, str] | None = None,
) -> str | None:
    if page_class in SUPPORT_PAGE_CLASSES:
        return None
    context = structured_context or {}
    if context.get("price"):
        return context["price"]
    if snapshot.sellability_state == "sellable" and snapshot.price_signals:
        return _extract_price_text(snapshot.decoded_text or "")
    return None


def _extract_price_text(text: str) -> str | None:
    match = PRICE_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).replace(" ", "").removesuffix("원")


def _structured_product_items(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for payload in payloads:
        for item in _iter_structured_items(payload):
            type_names = _type_names(item)
            if "product" in type_names:
                items.append(item)
    return items


def _structured_breadcrumb_items(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for payload in payloads:
        for item in _iter_structured_items(payload):
            if "breadcrumblist" in _type_names(item):
                items.append(item)
    return items


def _iter_structured_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items: list[dict[str, Any]] = []
        for item in payload:
            items.extend(_iter_structured_items(item))
        return items
    if not isinstance(payload, dict):
        return []

    items = [payload]
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            items.extend(_iter_structured_items(item))
    return items


def _type_names(item: dict[str, Any]) -> set[str]:
    raw = item.get("@type")
    if isinstance(raw, list):
        return {str(entry).casefold() for entry in raw}
    if isinstance(raw, str):
        return {raw.casefold()}
    return set()


def _structured_product_name(product_items: list[dict[str, Any]]) -> str | None:
    for item in product_items:
        name = " ".join(str(item.get("name") or "").split()).strip()
        if name:
            return name
    return None


def _structured_brand_name(product_items: list[dict[str, Any]]) -> str | None:
    for item in product_items:
        for key in ("brand", "manufacturer"):
            raw = item.get(key)
            name = _value_name(raw)
            if name:
                cleaned = _clean_brand_name(name)
                if cleaned:
                    return cleaned
    return None


def _structured_category_name(product_items: list[dict[str, Any]], breadcrumb_items: list[dict[str, Any]]) -> str | None:
    for item in product_items:
        category = " ".join(str(item.get("category") or "").split()).strip()
        if category and not _looks_like_url_text(category):
            return category

    for item in breadcrumb_items:
        element_list = item.get("itemListElement")
        if not isinstance(element_list, list):
            continue
        names = [
            _value_name(entry.get("item")) or " ".join(str(entry.get("name") or "").split()).strip()
            for entry in element_list
            if isinstance(entry, dict)
        ]
        names = [name for name in names if name and not _looks_like_url_text(name)]
        if names:
            return names[-1]
    return None


def _structured_price_value(product_items: list[dict[str, Any]]) -> str | None:
    for item in product_items:
        offers = item.get("offers")
        if isinstance(offers, list):
            offer_items = [offer for offer in offers if isinstance(offer, dict)]
        elif isinstance(offers, dict):
            offer_items = [offers]
        else:
            offer_items = []

        for offer in offer_items:
            price = _sanitize_price(offer.get("price"))
            if price:
                return price
    return None


def _structured_description_texts(product_items: list[dict[str, Any]]) -> list[str]:
    descriptions: list[str] = []
    for item in product_items:
        description = " ".join(str(item.get("description") or "").split()).strip()
        if description:
            descriptions.append(description)
    return _unique_texts(descriptions)


def _value_name(raw: Any) -> str:
    if isinstance(raw, dict):
        return " ".join(str(raw.get("name") or "").split()).strip()
    if isinstance(raw, str):
        return " ".join(raw.split()).strip()
    return ""


def _sanitize_price(raw: Any) -> str | None:
    if raw is None:
        return None
    text = re.sub(r"[^\d]", "", str(raw))
    if len(text) < 4 or len(text) > 6:
        return None
    return text


def _clean_brand_name(value: str) -> str:
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", value)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return ""
    return cleaned


def _brand_from_url(raw_url: str) -> str | None:
    host = urlparse(raw_url).hostname or ""
    parts = [part for part in host.casefold().split(".") if part and part != "www"]
    for part in parts:
        if part in KNOWN_HOST_BRANDS:
            return KNOWN_HOST_BRANDS[part]
    for part in parts:
        if part in MARKETPLACE_HOST_TOKENS:
            return None
    if not parts:
        return None
    candidate = parts[-2] if len(parts) >= 2 else parts[0]
    if candidate in MARKETPLACE_HOST_TOKENS:
        return None
    if candidate == "co" and len(parts) >= 3:
        candidate = parts[-3]
    if candidate in MARKETPLACE_HOST_TOKENS:
        return None
    return candidate.capitalize() if len(candidate) > 2 else candidate.upper()


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
    for fact in facts:
        fact_type = str(fact.get("type") or "").strip()
        normalized_value = str(fact.get("normalized_value") or fact.get("value") or "").strip()
        if not fact_type or not normalized_value:
            continue
        key = (fact_type.casefold(), normalized_value.casefold())
        if key in seen:
            continue
        seen.add(key)
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


def _is_thin_pack(facts: list[dict[str, Any]], page_class: str) -> bool:
    if page_class not in COMMERCE_PAGE_CLASSES:
        return False

    base_types = {"product_name", "brand", "product_category"}
    present_base = {str(fact.get("type")) for fact in facts if str(fact.get("type")) in base_types}
    if len(present_base) < len(base_types):
        return True

    rich_types = {
        str(fact.get("type"))
        for fact in facts
        if str(fact.get("type"))
        in {"benefit", "key_ingredient", "usage", "use_case", "problem_solution", "volume", "variant", "texture", "audience"}
    }
    return len(rich_types) < 2


def _quality_warning_inputs(
    snapshot: NormalizedPageSnapshot,
    ocr_dominant: bool,
    ocr_used: bool,
    thin_pack: bool,
) -> list[str]:
    inputs: list[str] = []
    if snapshot.fallback_used:
        inputs.append("fallback_used")
    if snapshot.fallback_reason:
        inputs.append(f"fallback_reason:{snapshot.fallback_reason}")
    if snapshot.preprocessing_source:
        inputs.append(f"preprocessing_source:{snapshot.preprocessing_source}")
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
    if thin_pack:
        inputs.append("thin_pack")
    return inputs


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _bounded_confidence(value: float) -> float:
    return max(0.55, min(value, 0.99))
