from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from src.clients.bedrock import BedrockRuntimeSettings, converse_text, converse_text_with_metadata

from .constants import NEGATIVE_CATEGORY, POSITIVE_CATEGORIES, POSITIVE_CATEGORY_TARGETS
from .models import CanonicalIntent, DedupQualityReport, GenerationRequest, KeywordRow, PlatformRender, SharedRender
from .policy import canonical_brand, canonical_product_name, competitor_brand_terms, generic_category_terms, resolve_product_types

SYSTEM_PROMPT = (
    "You generate paid-search keyword candidates as strict JSON only. "
    "Use only admitted evidence facts. Do not invent prices, discounts, urgency, or unsupported claims. "
    "Do not emit repeated phrases, broken exact-match fragments, placeholder units, or domain-mismatched negative keywords."
)

DEDUP_QUALITY_SYSTEM_PROMPT = (
    "You are a paid-search keyword quality reviewer. "
    "Return strict JSON only. "
    "Identify semantic duplicates and score keyword quality. "
    "Do not add new keywords."
)

SUPPLEMENTATION_SYSTEM_PROMPT = (
    "You generate additional paid-search keywords to fill identified gaps. "
    "Return strict JSON only. "
    "Use only admitted evidence facts. Do not invent prices, discounts, urgency, or unsupported claims. "
    "Do not emit repeated phrases, broken exact-match fragments, placeholder units, or domain-mismatched negative keywords."
)

_LANGUAGE_POLICY = {
    "allow_mixed": True,
    "brand_model_keep_original_language": True,
    "generic_terms_prefer_korean": True,
    "examples": [
        "나이키 슬리퍼",
        "Nike 슬리퍼",
        "아이폰 16 케이스",
        "iPhone 16 케이스",
        "나이키 에어맥스 남성",
        "Nike Air Max 남성용",
    ],
    "note": "Same concept in Korean and English counts as two distinct keywords and both are encouraged.",
}
_SUPPLEMENTATION_UNIT_TOKENS = {"ml", "g", "kg", "inch", "in", "gb", "tb", "mah", "hz", "w"}
_DIRECT_VALUE_SIGNAL_TERMS = (
    "가성비",
    "합리적 가격",
    "합리적인 가격",
    "경제적",
    "경제적인",
    "best value",
    "value for money",
)


def _unique_prompt_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _weak_category_prompt_examples(
    interpretation: dict[str, Any],
    *,
    target_categories: list[str],
) -> dict[str, dict[str, list[str]]]:
    canonical_category = " ".join(str(interpretation.get("canonical_category") or "").split()).strip()
    brand = " ".join(str(interpretation.get("brand") or "").split()).strip()
    product_name = " ".join(str(interpretation.get("product_name") or "").split()).strip()
    concerns = _unique_prompt_texts(list(interpretation.get("concerns") or []))
    usage_context = _unique_prompt_texts(list(interpretation.get("usage_context") or []))
    audience = _unique_prompt_texts(list(interpretation.get("audience") or []))
    grounded_event_terms = _unique_prompt_texts(list(interpretation.get("grounded_event_terms") or []))
    competitor_hints = _unique_prompt_texts(
        list((interpretation.get("comparison_policy") or {}).get("competitor_brand_hints") or [])
    )

    def with_category(values: list[str]) -> list[str]:
        if not canonical_category:
            return _unique_prompt_texts(values)
        return _unique_prompt_texts([f"{value} {canonical_category}" for value in values if value])

    examples: dict[str, dict[str, list[str]]] = {}
    for category in target_categories:
        if category == "problem_solution":
            positive = with_category(concerns[:3] or usage_context[:2])
            negative = _unique_prompt_texts(
                [
                    f"{product_name} 관리" if product_name else "",
                    f"{canonical_category} 해결" if canonical_category else "",
                    f"{product_name} 고민 해결" if product_name else "",
                ]
            )
        elif category == "season_event":
            seasonal_seed = grounded_event_terms[:2] or usage_context[:2]
            positive = with_category(seasonal_seed)
            negative = _unique_prompt_texts(
                [
                    f"무료배송 {canonical_category}" if canonical_category else "",
                    f"빠른배송 {canonical_category}" if canonical_category else "",
                    f"{product_name} 일상용" if product_name else "",
                ]
            )
        elif category == "long_tail":
            long_tail_seed = usage_context[:2] + audience[:2] + concerns[:1]
            positive = with_category(long_tail_seed)
            negative = _unique_prompt_texts(
                [
                    f"{product_name} 사용" if product_name else "",
                    f"{product_name} 추천" if product_name else "",
                    f"{canonical_category} 구매 이유" if canonical_category else "",
                ]
            )
        elif category == "competitor_comparison":
            positive = _unique_prompt_texts(
                [
                    f"{competitor} {canonical_category}"
                    for competitor in competitor_hints[:3]
                    if competitor and canonical_category
                ]
                + [
                    f"{competitor} {canonical_category} 비교"
                    for competitor in competitor_hints[:2]
                    if competitor and canonical_category
                ]
            )
            negative = _unique_prompt_texts(
                [
                    f"{brand} {canonical_category} 비교" if brand and canonical_category else "",
                    f"{product_name} 용량 비교" if product_name else "",
                    f"{canonical_category} 가격 비교" if canonical_category else "",
                ]
            )
        else:
            continue
        if positive or negative:
            examples[category] = {
                "good": positive[:5],
                "bad": negative[:5],
            }
    return examples


class BedrockResponseParseError(ValueError):
    def __init__(
        self,
        *,
        stage: str,
        message: str,
        model_id: str,
        response_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.model_id = model_id
        self.response_text = response_text
        self.metadata = dict(metadata or {})


def _direct_evidence_texts(facts: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for fact in facts:
        if str(fact.get("evidence_tier") or "").strip().lower() != "direct":
            continue
        for field in ("normalized_value", "value"):
            value = " ".join(str(fact.get(field) or "").split()).strip()
            if value:
                texts.append(value)
    seen: set[str] = set()
    unique: list[str] = []
    for text in texts:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _text_mentions_any(texts: list[str], needle: str) -> bool:
    lowered = needle.casefold()
    return any(lowered in text.casefold() for text in texts)


def _variant_measurements(specs: list[str]) -> list[str]:
    values: list[str] = []
    pattern = r"\d+(?:\.\d+)?\s?(?:ml|g|kg|oz|inch|in|gb|tb|mah|hz|w|형)"
    for spec in specs:
        values.extend(re.findall(pattern, spec, flags=re.IGNORECASE))
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _prompt_interpretation(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    product_name = canonical_product_name(evidence_pack)
    brand = canonical_brand(evidence_pack)
    category_terms = generic_category_terms(evidence_pack)
    canonical_category = category_terms[0] if category_terms else product_name
    product_types = sorted(resolve_product_types(evidence_pack))
    facts = list(evidence_pack.get("facts", []))

    def values_for_types(*fact_types: str) -> list[str]:
        values: list[str] = []
        for fact in facts:
            if str(fact.get("type") or "") not in fact_types:
                continue
            value = str(fact.get("normalized_value") or fact.get("value") or "").strip()
            if value:
                values.append(value)
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(value)
        return unique

    benefits = values_for_types("benefit")
    concerns = values_for_types("concern", "problem_solution")
    audience = values_for_types("skin_type", "audience")
    usage_context = values_for_types("usage", "use_case")
    ingredients = values_for_types("key_ingredient")
    technology = [
        str(f.get("normalized_value") or f.get("value") or "").strip()
        for f in facts
        if "brand_technology" in {str(tag) for tag in f.get("admissibility_tags", [])}
        and str(f.get("normalized_value") or f.get("value") or "").strip()
    ]
    form_factors = values_for_types("texture")
    specs = values_for_types("volume", "variant")
    direct_texts = _direct_evidence_texts(facts)
    variant_measurements = _variant_measurements(specs)
    value_terms = [term for term in _DIRECT_VALUE_SIGNAL_TERMS if _text_mentions_any(direct_texts, term)]
    competitor_hints = competitor_brand_terms(evidence_pack)
    generic_type_phrases = [canonical_category, *category_terms[1:4]]
    navigational_aliases = [product_name]
    if brand and brand != product_name:
        navigational_aliases.append(brand)
    if len(product_name.split()) >= 2:
        navigational_aliases.append(" ".join(product_name.split()[-2:]))
    problem_noun_phrases = [f"{concern} {canonical_category}" for concern in concerns[:4]]
    grounded_event_terms = [term for term in ("블랙프라이데이", "black friday", "사이버먼데이", "cyber monday") if _text_mentions_any(direct_texts, term)]
    price_band_candidates: list[str] = []
    for fact in facts:
        if str(fact.get("type") or "") != "price":
            continue
        digits = re.sub(r"[^0-9]", "", str(fact.get("normalized_value") or fact.get("value") or ""))
        if not digits:
            continue
        ten_thousand = max(1, int(digits) // 10000)
        price_band_candidates.append(f"{ten_thousand}만원대 {canonical_category}")
    return {
        "product_name": product_name,
        "brand": brand,
        "product_types": product_types,
        "canonical_category": canonical_category,
        "secondary_categories": category_terms[1:4],
        "generic_type_phrases": generic_type_phrases[:6],
        "navigational_aliases": navigational_aliases[:6],
        "benefits": benefits[:6],
        "concerns": concerns[:6],
        "problem_noun_phrases": problem_noun_phrases[:6],
        "audience": audience[:6],
        "usage_context": usage_context[:6],
        "ingredients": ingredients[:6],
        "technology": technology[:4],
        "form_factors": form_factors[:4],
        "specs": specs[:4],
        "grounded_event_terms": grounded_event_terms[:4],
        "price_band_candidates": price_band_candidates[:4],
        "comparison_policy": {
            "llm_first_discovery": True,
            "require_competitor_brand": True,
            "current_brand": brand,
            "competitor_brand_hints": competitor_hints[:6],
            "allowed_shapes": ["competitor_brand + product_type", "competitor_brand + product_type + 비교"],
            "disallowed_shapes": ["same-product measurement comparison", "generic comparison without competitor brand", "current-brand-only comparison"],
            "price_keyword_allowed": any(str(f.get("type") or "") == "price" for f in facts),
            "direct_value_terms": value_terms[:4],
            "forbid_without_competitor_brand": ["비교", "대안", "대체", "대체품", "옵션 비교", "라인 비교", "용량 비교"],
        },
    }


def build_keyword_generation_prompt(
    request: GenerationRequest,
    *,
    positive_target: int,
    positive_category_targets: dict[str, int] | None = None,
    interpretation_payload: dict[str, Any] | None = None,
    slot_plan: list[dict[str, Any]] | None = None,
    target_categories: list[str] | None = None,
    batch_name: str | None = None,
) -> str:
    evidence_pack = request.evidence_pack
    interpretation = interpretation_payload or _prompt_interpretation(evidence_pack)
    allowed_fields = {
        "raw_url": evidence_pack.get("raw_url"),
        "canonical_url": evidence_pack.get("canonical_url"),
        "page_class": evidence_pack.get("page_class"),
        "product_name": evidence_pack.get("product_name"),
        "locale_detected": evidence_pack.get("locale_detected"),
        "market_locale": evidence_pack.get("market_locale"),
        "sellability_state": evidence_pack.get("sellability_state"),
        "stock_state": evidence_pack.get("stock_state"),
        "sufficiency_state": evidence_pack.get("sufficiency_state"),
        "quality_warning": evidence_pack.get("quality_warning"),
        "facts": evidence_pack.get("facts", []),
        "interpretation": interpretation,
    }
    target_mix = positive_category_targets or POSITIVE_CATEGORY_TARGETS
    slot_plan = slot_plan or []
    target_categories = list(target_categories or POSITIVE_CATEGORIES)
    negative_required = NEGATIVE_CATEGORY in target_categories
    positive_categories = [category for category in target_categories if category != NEGATIVE_CATEGORY]
    category_enum = positive_categories + ([NEGATIVE_CATEGORY] if negative_required else [])
    weak_category_examples = _weak_category_prompt_examples(
        interpretation,
        target_categories=positive_categories,
    )
    instructions = {
        "requested_platform_mode": request.requested_platform_mode,
        "generation_mode": "category_slot_filling",
        "batch_name": batch_name or "default",
        "target_categories": target_categories,
        "positive_target_per_platform": positive_target,
        "required_positive_categories": positive_categories,
        "negative_category_required": negative_required,
        "positive_category_targets": target_mix,
        "slot_plan": slot_plan,
        "language_policy": _LANGUAGE_POLICY,
        "rendering_policy": {
            "quality_first": True,
            "drop_low_quality_even_if_shortfall": True,
            "anchor_on_canonical_category": True,
            "avoid_adjacent_category_drift": True,
            "forbid_verbose_surface_scaffolds": True,
            "llm_owns_category_completion": True,
            "shared_render_default": True,
            "fill_slots_not_freeform_lists": True,
        },
        "buyer_query_contract": [
            "Generate only keyword phrases that a real buyer of this exact product page would plausibly search.",
            "Prefer queries that this exact PDP can satisfy directly, not broad curiosity or adjacent product research.",
            "Prioritize model-specific queries over lineup-wide or brand-wide queries.",
            "Prioritize model plus price, storage, color, or shopper-facing variant queries over broad product-class phrases.",
            "Before finalizing each keyword, check whether a real buyer would type it and whether this PDP directly satisfies that query. Drop the keyword if either answer is no.",
            "If a category is weakly supported, emit fewer keywords instead of weak or filler variants.",
        ],
        "generic_category_contract": [
            "Generic-category keywords must be common shopper-facing product-class phrases, not arbitrary rewrites of attributes into category labels.",
            "Prefer broad product-class phrases that a buyer would naturally search, such as smartphone, phone case, or frozen chicken breast, only when the PDP directly supports that class.",
            "Do not create generic-category phrases by attaching colors, flavor names, pack sizes, storage amounts, or weak attributes to the product class unless that phrasing is itself a common shopper query.",
            "Do not turn storage, convenience, or preservation language into outing, travel, picnic, camping, or other situational category phrases unless those exact situations are explicitly grounded on the page.",
        ],
        "surface_form_prohibitions": [
            "Do not emit checklist or consultation scaffolds such as '구매 전 체크', '구매 준비', '구매 상담', '구매 문의', '구매 타이밍', or '결제 옵션'.",
            "Do not emit reason-to-buy scaffolds such as '필요 이유', '고민 해결', or generic '* 해결' phrasing.",
            "Prefer concise search surfaces over sentence-like templates.",
            "Do not emit product-name plus verb or action surfaces such as 'Apple Pencil 그림 그리기', 'Apple Pencil 메모', 'Apple Pencil 문서 주석 작성', 'buy cloudmonster shoes', or similar product-plus-action phrases.",
            "Do not emit informational or help-query surfaces on commerce PDPs such as '* 방법', '* 사용법', '* 가이드', setup, pairing, or how-to phrasing unless the page itself is a support/how-to page.",
            "Purchase-intent keywords must stay exact or navigational. Do not append 구매, 주문, 구입, buy, order, or shop to the product name.",
            "Do not emit unsupported promo-event surfaces such as Black Friday or Cyber Monday unless those exact events are grounded in admitted evidence.",
            "Price rows must be search-like noun phrases such as '<price band> + product type' or '<product name> 가격'. Do not emit raw exact price numbers such as '149000' or '149,000원'.",
            "Do not emit product-name plus purpose suffix surfaces such as 'Apple Pencil 그림용'. Use generic category-led phrasing only when it sounds like a real search query.",
            "Do not turn colors or weak attributes into generic product-class phrases such as '<color> smartphone' or similar color-plus-category surfaces.",
            "Feature-attribute rows must stay grounded in admitted specs, variants, ingredients, technology, or form-factor evidence. Do not emit ecosystem names, standalone services, or isolated standards as product features.",
            "Season-event rows must stay grounded in admitted event terms or explicit usage context. Do not turn logistics, shipping incentives, or generic merchandising language into season/event keywords.",
            "Problem-solution rows must stay grounded in admitted concern or use-case evidence. Do not infer hypothetical shortcomings or dissatisfaction from product specs alone.",
            "Competitor rows must include a non-current competitor brand and the product type; never emit same-product measurement comparisons.",
        ],
        "category_completion_contract": [
            "Every required positive category in target_categories must appear at least once in the final admitted set.",
            "Emit the negative category only when target_categories includes negative.",
            "Use slot_plan as a category-scoped guide: required slots are the primary way to cover a category, optional slots are diversity hints only when evidence supports them.",
            "Do not force a weak slot just to satisfy diversity. If an optional slot is thin, prefer a stronger keyword in the category's required slot.",
            "Fill the supplied slot_plan first; do not freewrite category lists without a slot.",
            "Return at least one admitted keyword for every target positive category.",
            "Use the positive_category_targets as the ideal mix for the final surviving set, but express that mix through slot completion.",
            "Do not skip a category just because deterministic defaults would be thin; synthesize commercially plausible noun-phrase search surfaces directly from admitted evidence facets.",
        ],
        "category_examples": weak_category_examples,
        "output_schema": {
            "items": [
                {
                    "category": f"{'|'.join(category_enum)}",
                    "keyword": "required search-like noun phrase keyword string",
                }
            ],
            "legacy_intents_supported": True,
            "legacy_rows_supported": True,
        },
    }
    return (
        "Return JSON only.\n"
        f"generation_instructions={json.dumps(instructions, ensure_ascii=False)}\n"
        f"evidence_pack={json.dumps(allowed_fields, ensure_ascii=False)}"
    )


def build_dedup_quality_prompt(
    candidates: list[CanonicalIntent],
    *,
    platform_mode: str,
    positive_floor: int = 100,
    positive_category_targets: dict[str, int] | None = None,
) -> str:
    """Build the dedup+quality evaluation prompt (step B of LLM pipeline)."""
    serialized = [
        {
            "intent_id": c.intent_id,
            "keyword": c.shared_render.keyword if c.shared_render else c.intent_text,
            "category": c.category,
            "slot_type": c.slot_type,
            "evidence_tier": c.evidence_tier,
        }
        for c in candidates
    ]
    instructions = {
        "task": "dedup_and_quality_evaluation",
        "platform_mode": platform_mode,
        "positive_floor_per_platform": positive_floor,
        "positive_category_targets": positive_category_targets or {},
        "required_positive_categories": list(POSITIVE_CATEGORIES),
        "negative_category_required": True,
        "dedup_rules": [
            "Identify groups of semantically equivalent keywords (same core search intent, different surface form).",
            "Examples of duplicates: 'mens sneaker' / 'men sneaker' / \"men's sneaker\" -> keep one.",
            "Examples of distinct: '나이키 슬리퍼' / '나이키 슬리퍼 남성' -> keep both (modifier changes intent).",
            "Prefer the representative that is most natural for Korean search behavior.",
            "Among ties prefer the candidate with stronger evidence_tier: direct > derived > inferred > weak.",
            "sensory: finish, texture, feel, absorption, or wear experience grounded in admitted evidence",
        ],
        "quality_rules": [
            "Score each surviving keyword: high / medium / low.",
            "low = generic filler with no product-specific grounding, vague intent, or unlikely search query.",
            "low = repeated phrases, placeholder-unit keywords, broken product fragments, or domain-mismatched negatives.",
            "low = category drift away from the canonical category head or product+head duplication.",
            "low = checklist, consultation, or reason-to-buy scaffolds such as '구매 전 체크', '구매 준비', '구매 상담', '결제 옵션', '필요 이유', '고민 해결', or '* 해결'.",
            "low = product-name plus verb or action surfaces such as 'Apple Pencil 그림 그리기', 'Apple Pencil 메모', 'Apple Pencil 문서 주석 작성', or 'buy cloudmonster shoes'.",
            "low = informational or how-to query surfaces on commerce PDPs such as '* 방법', '* 사용법', '* 가이드', setup, pairing, or help-style phrasing.",
            "low = unsupported promo-event surfaces such as Black Friday or Cyber Monday when those events are not grounded in admitted evidence.",
            "low = raw exact price-number surfaces such as '149000', '149,000원', or '<product> 15만원'; price rows should use price bands or '<product> 가격'.",
            "low = product-name plus purpose suffix surfaces such as 'Apple Pencil 그림용'.",
            "low = feature rows that are not grounded in admitted specs, variants, ingredients, technology, or form-factor evidence.",
            "low = season/event rows that are not grounded in admitted event terms or explicit usage context, including logistics or shipping incentive phrasing masquerading as seasonality.",
            "low = problem/solution rows that infer hypothetical shortcomings without admitted concern or use-case evidence.",
            "low = competitor rows without a non-current competitor brand, or same-product measurement comparisons.",
            "Set keep=false for low-quality keywords. This is a quality gate; do not lower the bar to meet count floors.",
            "Preserve category coverage: the surviving set should still keep all positive categories represented whenever valid candidates exist.",
        ],
        "output_schema": {
            "surviving": [
                {
                    "intent_id": "string",
                    "keyword": "string",
                    "category": "string",
                    "quality_score": "high|medium|low",
                    "quality_reason": "string",
                    "keep": True,
                }
            ],
            "dropped_duplicates": [
                {"intent_text": "string", "duplicate_of": "string", "reason": "string"}
            ],
            "dropped_low_quality": [
                {"intent_text": "string", "quality_score": "string", "reason": "string"}
            ],
            "slot_gap_report": {
                "<category:slot_type>": "<missing_count_int>",
                "_total": "<total_missing_int>",
            },
        },
    }
    return (
        "Return JSON only.\n"
        f"dedup_quality_instructions={json.dumps(instructions, ensure_ascii=False)}\n"
        f"candidates={json.dumps(serialized, ensure_ascii=False)}"
    )


def build_supplementation_prompt(
    gap_slots: dict[str, int],
    evidence_pack: dict[str, Any],
    *,
    platform_mode: str,
    surviving_summary: list[dict] | None = None,
    missing_categories: list[str] | None = None,
    interpretation_payload: dict[str, Any] | None = None,
    slot_plan: list[dict[str, Any]] | None = None,
) -> str:
    """Build the supplementation prompt (step C of LLM pipeline, runs only when gaps remain)."""
    interpretation = interpretation_payload or _prompt_interpretation(evidence_pack)
    allowed_fields = {
        "raw_url": evidence_pack.get("raw_url"),
        "canonical_url": evidence_pack.get("canonical_url"),
        "page_class": evidence_pack.get("page_class"),
        "product_name": evidence_pack.get("product_name"),
        "locale_detected": evidence_pack.get("locale_detected"),
        "sellability_state": evidence_pack.get("sellability_state"),
        "stock_state": evidence_pack.get("stock_state"),
        "facts": evidence_pack.get("facts", []),
        "interpretation": interpretation,
    }
    # Provide a summary of already-surviving keywords so the LLM avoids re-generating them.
    gap_slots = {k: v for k, v in gap_slots.items() if k != "_total" and v > 0}
    used_token_clusters = _used_token_clusters(surviving_summary or [], evidence_pack=evidence_pack)
    weak_target_categories = sorted({str(key).split(":", 1)[0] for key in gap_slots})
    weak_category_examples = _weak_category_prompt_examples(
        interpretation,
        target_categories=weak_target_categories,
    )
    instructions = {
        "task": "supplementation",
        "platform_mode": platform_mode,
        "language_policy": _LANGUAGE_POLICY,
        "missing_categories": missing_categories or [],
        "gap_slots": gap_slots,
        "slot_plan": slot_plan or [],
        "total_missing_slots": sum(gap_slots.values()),
        "expansion_axes": [
            "benefit: concrete user-facing benefit grounded in admitted evidence",
            "concern: problem or pain point the buyer is trying to solve",
            "audience: the user segment or need state the product targets",
            "situation: noun-phrase seasonal or purchase context grounded in evidence",
            "task_shape: noun-phrase tool or need-state phrasing without verbs",
        ],
        "sensory_axis": "finish, texture, feel, absorption, or wear experience grounded in admitted evidence and expressed as noun phrases only",
        "constraint": (
            "Fill missing_categories first using the category's required slot when possible. "
            "Then prefer uncovered optional slots only when evidence supports them. "
            "Generate ONLY keywords for the listed gap_slots. "
            "Do not regenerate keywords already in the surviving set. "
            "Do not invent promo, price-band, or urgency claims. "
            "Competitor rows are allowed only when they include a non-current competitor brand and the product type. "
            "Do not widen evidence ceilings. "
            "Never output repeated phrases, placeholder-unit keywords, broken exact fragments, or domain-mismatched negatives."
        ),
        "surface_cleanup_policy": {
            "drop_first": True,
            "canonical_category_locked": True,
            "forbid_adjacent_category_drift": True,
        },
        "supplementation_prohibitions": [
            "Do not emit weak comparison keywords without direct evidence.",
            "Do not regenerate surviving keywords with only cosmetic wording changes.",
            "Do not repeat product-name or brand-name fragments as filler.",
            "Do not echo placeholder, scaffold, or support-document phrasing.",
            "Do not widen to generic head terms without evidence or taxonomy support.",
            "Do not emit checklist, consultation, or reason-to-buy scaffolds such as '구매 전 체크', '구매 준비', '구매 상담', '구매 문의', '구매 타이밍', '결제 옵션', '필요 이유', '고민 해결', or '* 해결'.",
            "Do not emit product-name plus verb or action surfaces such as 'Apple Pencil 그림 그리기', 'Apple Pencil 메모', 'Apple Pencil 문서 주석 작성', 'buy cloudmonster shoes', or similar product-plus-action phrases.",
            "Do not emit informational or how-to query surfaces on commerce PDPs such as '* 방법', '* 사용법', '* 가이드', setup, pairing, or help-style phrasing.",
            "Purchase-intent keywords must stay exact or navigational. Do not append 구매, 주문, 구입, buy, order, or shop to the product name.",
            "Do not emit unsupported promo-event surfaces such as Black Friday or Cyber Monday unless those exact events are grounded in admitted evidence.",
            "Do not emit raw exact price-number surfaces such as '149000', '149,000원', or '<product> 15만원'; use price bands or '<product> 가격' only when evidence supports them.",
            "Do not emit product-name plus purpose suffix surfaces such as 'Apple Pencil 그림용'.",
            "Do not emit generic comparison rows without a competitor brand.",
            "Do not emit same-product measurement comparisons such as '70ml 25ml 비교' or '용량 비교'.",
        ],
        "category_examples": weak_category_examples,
        "already_overused_terms": used_token_clusters,
        "already_surviving_count": len(surviving_summary or []),
        "already_surviving_sample": (surviving_summary or [])[:20],
        "output_schema": {
            "items": [
                {
                    "category": "string",
                    "keyword": "string",
                }
            ]
        },
    }
    instructions["supplementation_prohibitions"].append("Do not drift into adjacent category heads that do not match the canonical category.")
    return (
        "Return JSON only.\n"
        f"supplementation_instructions={json.dumps(instructions, ensure_ascii=False)}\n"
        f"evidence_pack={json.dumps(allowed_fields, ensure_ascii=False)}"
    )


def _used_token_clusters(surviving_summary: list[dict], *, evidence_pack: dict[str, Any]) -> list[str]:
    excluded_tokens = set(_cluster_tokens(canonical_product_name(evidence_pack)))
    excluded_tokens.update(_cluster_tokens(canonical_brand(evidence_pack)))
    counts: dict[str, int] = {}
    for entry in surviving_summary:
        intent_text = str(entry.get("intent_text") or "").strip()
        if not intent_text:
            continue
        for token in _cluster_tokens(intent_text):
            if token in excluded_tokens or token in _SUPPLEMENTATION_UNIT_TOKENS or token.isdigit():
                continue
            if _is_single_hangul_token(token):
                continue
            counts[token] = counts.get(token, 0) + 1
    ordered = sorted(
        ((token, count) for token, count in counts.items() if count >= 2),
        key=lambda item: (-item[1], item[0]),
    )
    return [token for token, _ in ordered[:12]]


def _cluster_tokens(value: str) -> list[str]:
    pattern = r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[\u3131-\u318E\uAC00-\uD7A3]+"
    normalized = value.replace("\u2019", "'").replace("\u2018", "'")
    return [token.casefold() for token in re.findall(pattern, normalized)]


def _is_single_hangul_token(token: str) -> bool:
    return len(token) == 1 and bool(re.fullmatch(r"[\u3131-\u318E\uAC00-\uD7A3]", token))


def parse_intent_response(
    response_text: str,
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    payload = _load_response_payload(response_text)
    payload = _find_payload_container(payload, required_keys={"intents", "items", "rows", "keywords"})
    if not isinstance(payload, dict):
        raise ValueError("Bedrock response must be a JSON object")

    if isinstance(payload.get("intents"), list):
        return _parse_intents(payload["intents"], request=request)

    if isinstance(payload.get("items"), list):
        return _parse_items(payload["items"], request=request)

    if isinstance(payload.get("keywords"), list):
        return _parse_items(payload["keywords"], request=request)

    if isinstance(payload.get("rows"), list):
        return _upgrade_legacy_rows(payload["rows"], request=request)

    raise ValueError("Bedrock response must include items[] or keywords[] or intents[] or rows[]")


def parse_dedup_quality_response(
    response_text: str,
    *,
    platform: str,
    all_candidates: list[CanonicalIntent],
    request: GenerationRequest,
) -> DedupQualityReport:
    """Parse the JSON response from the dedup+quality Bedrock call."""
    payload = _load_response_payload(response_text)
    payload = _find_payload_container(
        payload,
        required_keys={"surviving", "dropped_duplicates", "dropped_low_quality", "slot_gap_report", "gap_report"},
    )
    if not isinstance(payload, dict):
        raise ValueError("Dedup quality response must be a JSON object")

    # Build a lookup from intent_text to original CanonicalIntent for surviving reconstruction.
    candidate_map = {c.intent_id or _intent_id_from_fields(c.category, c.intent_text): c for c in all_candidates}

    surviving_raw = payload.get("surviving") or []
    surviving: list[CanonicalIntent] = []
    for item in surviving_raw:
        if not isinstance(item, dict):
            continue
        keep = item.get("keep", True)
        if not keep:
            continue
        intent_id = str(item.get("intent_id") or "").strip()
        keyword = str(item.get("keyword") or item.get("intent_text") or "")
        original = candidate_map.get(intent_id) if intent_id else None
        if original is None and keyword:
            original = candidate_map.get(_intent_id_from_fields(str(item.get("category") or ""), keyword))
        if original is not None:
            original.quality_score = str(item.get("quality_score") or "").strip() or None
            original.quality_reason = str(item.get("quality_reason") or item.get("reason") or "").strip() or None
            surviving.append(original)
        else:
            # LLM may have slightly altered intent_text; do a best-effort match
            for candidate in candidate_map.values():
                candidate_text = candidate.intent_text
                if keyword and (keyword in candidate_text or candidate_text in keyword):
                    candidate.quality_score = str(item.get("quality_score") or "").strip() or None
                    candidate.quality_reason = str(item.get("quality_reason") or item.get("reason") or "").strip() or None
                    surviving.append(candidate)
                    break

    dropped_duplicates = [d for d in (payload.get("dropped_duplicates") or []) if isinstance(d, dict)]
    dropped_low_quality = [d for d in (payload.get("dropped_low_quality") or []) if isinstance(d, dict)]
    raw_slot_gap_report = payload.get("slot_gap_report")
    if not isinstance(raw_slot_gap_report, dict):
        raw_slot_gap_report = payload.get("gap_report") or {}
    slot_gap_report = {
        k: int(v)
        for k, v in raw_slot_gap_report.items()
        if isinstance(v, (int, float))
    }

    return DedupQualityReport(
        platform=platform,
        surviving_keywords=surviving,
        dropped_duplicates=dropped_duplicates,
        dropped_low_quality=dropped_low_quality,
        slot_gap_report=slot_gap_report,
    )


def parse_keyword_response(
    response_text: str,
    *,
    request: GenerationRequest,
) -> list[KeywordRow]:
    intents = parse_intent_response(response_text, request=request)
    return intents_to_rows(intents, request=request)


def should_use_bedrock() -> bool:
    return os.environ.get("KEYWORD_GENERATOR_GENERATION_MODE", "").strip().lower() == "bedrock"


def generate_intents_via_bedrock(
    request: GenerationRequest,
    *,
    positive_target: int,
    positive_category_targets: dict[str, int] | None = None,
    interpretation_payload: dict[str, Any] | None = None,
    slot_plan: list[dict[str, Any]] | None = None,
    target_categories: list[str] | None = None,
    batch_name: str | None = None,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
    return_metadata: bool = False,
) -> list[CanonicalIntent] | tuple[list[CanonicalIntent], dict[str, Any]]:
    prompt = build_keyword_generation_prompt(
        request,
        positive_target=positive_target,
        positive_category_targets=positive_category_targets,
        interpretation_payload=interpretation_payload,
        slot_plan=slot_plan,
        target_categories=target_categories,
        batch_name=batch_name,
    )
    model_id, text, metadata = converse_text_with_metadata(
        prompt,
        settings=settings,
        system_prompt=SYSTEM_PROMPT,
        client=client,
    )
    metadata = {**metadata, "model_id": model_id, "response_text": text}
    try:
        intents = parse_intent_response(text, request=request)
    except Exception as exc:
        raise BedrockResponseParseError(
            stage="generation",
            message=str(exc),
            model_id=model_id,
            response_text=text,
            metadata=metadata,
        ) from exc
    if return_metadata:
        return intents, metadata
    return intents


def run_dedup_quality_pass(
    candidates: list[CanonicalIntent],
    *,
    request: GenerationRequest,
    platform: str,
    positive_floor: int = 100,
    positive_category_targets: dict[str, int] | None = None,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
    return_metadata: bool = False,
) -> DedupQualityReport | tuple[DedupQualityReport, dict[str, Any]]:
    """Step B: LLM semantic dedup + quality evaluation."""
    prompt = build_dedup_quality_prompt(
        candidates,
        platform_mode=platform,
        positive_floor=positive_floor,
        positive_category_targets=positive_category_targets,
    )
    model_id, text, metadata = converse_text_with_metadata(
        prompt,
        settings=settings,
        system_prompt=DEDUP_QUALITY_SYSTEM_PROMPT,
        client=client,
    )
    metadata = {**metadata, "model_id": model_id}
    try:
        report = parse_dedup_quality_response(text, platform=platform, all_candidates=candidates, request=request)
    except Exception as exc:
        raise BedrockResponseParseError(
            stage="dedup_quality",
            message=str(exc),
            model_id=model_id,
            response_text=text,
            metadata={**metadata, "response_text": text},
        ) from exc
    if return_metadata:
        return report, metadata
    return report


def run_supplementation_pass(
    gap_slots: dict[str, int],
    *,
    request: GenerationRequest,
    platform: str,
    surviving_summary: list[dict] | None = None,
    missing_categories: list[str] | None = None,
    interpretation_payload: dict[str, Any] | None = None,
    slot_plan: list[dict[str, Any]] | None = None,
    batch_name: str | None = None,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
    return_metadata: bool = False,
) -> list[CanonicalIntent] | tuple[list[CanonicalIntent], dict[str, Any]]:
    """Step C: LLM targeted supplementation for gap categories (conditional)."""
    prompt = build_supplementation_prompt(
        gap_slots,
        request.evidence_pack,
        platform_mode=platform,
        surviving_summary=surviving_summary,
        missing_categories=missing_categories,
        interpretation_payload=interpretation_payload,
        slot_plan=slot_plan,
    )
    model_id, text, metadata = converse_text_with_metadata(
        prompt,
        settings=settings,
        system_prompt=SUPPLEMENTATION_SYSTEM_PROMPT,
        client=client,
    )
    metadata = {**metadata, "model_id": model_id, "response_text": text, "batch_name": batch_name or "supplementation"}
    try:
        intents = parse_intent_response(text, request=request)
    except Exception as exc:
        raise BedrockResponseParseError(
            stage="supplementation",
            message=str(exc),
            model_id=model_id,
            response_text=text,
            metadata=metadata,
        ) from exc
    if return_metadata:
        return intents, metadata
    return intents


def generate_rows_via_bedrock(
    request: GenerationRequest,
    *,
    positive_target: int,
    positive_category_targets: dict[str, int] | None = None,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
) -> list[KeywordRow]:
    intents = generate_intents_via_bedrock(
        request,
        positive_target=positive_target,
        positive_category_targets=positive_category_targets,
        client=client,
        settings=settings,
    )
    return intents_to_rows(intents, request=request)


def intents_to_rows(
    intents: list[CanonicalIntent],
    *,
    request: GenerationRequest,
) -> list[KeywordRow]:
    quality_warning = bool(request.evidence_pack.get("quality_warning", False))
    product_name = str(
        request.evidence_pack.get("canonical_product_name")
        or request.evidence_pack.get("product_name")
        or request.evidence_pack.get("raw_url")
        or "product"
    )
    raw_url = str(request.evidence_pack.get("raw_url") or request.evidence_pack.get("canonical_url") or "")

    rows: list[KeywordRow] = []
    for intent in intents:
        allowed_platforms = _resolve_allowed_platforms(
            intent.allowed_platforms,
            requested_platform_mode=request.requested_platform_mode,
            shared_render=intent.shared_render,
            naver_render=intent.naver_render,
            google_render=intent.google_render,
        )
        naver_render, google_render = _hydrate_platform_renders(
            category=intent.category,
            requested_platform_mode=request.requested_platform_mode,
            allowed_platforms=allowed_platforms,
            shared_render=intent.shared_render,
            naver_render=intent.naver_render,
            google_render=intent.google_render,
        )

        include_naver = bool(naver_render and naver_render.admitted and naver_render.keyword and naver_render.match_label)
        include_google = bool(google_render and google_render.admitted and google_render.keyword and google_render.match_label)
        reason = intent.reason or _default_reason_for_intent(intent)

        if include_naver and include_google and naver_render.keyword == google_render.keyword:
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=intent.category,
                    keyword=naver_render.keyword,
                    slot_type=intent.slot_type or None,
                    naver_match=naver_render.match_label,
                    google_match=google_render.match_label,
                    reason=reason,
                    quality_warning=quality_warning,
                    evidence_tier=intent.evidence_tier,
                    quality_score=intent.quality_score,
                    quality_reason=intent.quality_reason,
                    selection_score=intent.selection_score,
                    soft_penalties=intent.soft_penalties,
                )
            )
            continue

        if include_naver:
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=intent.category,
                    keyword=naver_render.keyword,
                    slot_type=intent.slot_type or None,
                    naver_match=naver_render.match_label,
                    google_match="",
                    reason=reason,
                    quality_warning=quality_warning,
                    evidence_tier=intent.evidence_tier,
                    quality_score=intent.quality_score,
                    quality_reason=intent.quality_reason,
                    selection_score=intent.selection_score,
                    soft_penalties=intent.soft_penalties,
                )
            )
        if include_google:
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=intent.category,
                    keyword=google_render.keyword,
                    slot_type=intent.slot_type or None,
                    naver_match="",
                    google_match=google_render.match_label,
                    reason=reason,
                    quality_warning=quality_warning,
                    evidence_tier=intent.evidence_tier,
                    quality_score=intent.quality_score,
                    quality_reason=intent.quality_reason,
                    selection_score=intent.selection_score,
                    soft_penalties=intent.soft_penalties,
                )
            )

    return rows


def _default_reason_for_intent(intent: CanonicalIntent) -> str:
    category_reasons = {
        "brand": "브랜드 및 제품명 직접 근거 기반",
        "generic_category": "제품 카테고리 직접 근거 기반",
        "feature_attribute": "제품 속성 및 스펙 근거 기반",
        "competitor_comparison": "동일 제품군 경쟁 브랜드 탐색 기반",
        "purchase_intent": "제품명 및 브랜드 탐색 의도 기반",
        "long_tail": "제품 특성 조합 확장 기반",
        "benefit_price": "가격 및 효익 탐색 기반",
        "season_event": "시즌 및 상황 탐색 기반",
        "problem_solution": "문제 해결 및 효익 탐색 기반",
        NEGATIVE_CATEGORY: "전환 의도가 낮은 제외 키워드 기반",
    }
    return category_reasons.get(intent.category, "근거 기반 키워드")


def _parse_intents(
    payload_intents: list[Any],
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    intents: list[CanonicalIntent] = []
    for raw_intent in payload_intents:
        if not isinstance(raw_intent, dict):
            continue
        category = str(raw_intent.get("category") or "")
        slot_type = str(raw_intent.get("slot_type") or "").strip()
        intent_text = str(raw_intent.get("intent_text") or "")
        naver_render = _parse_render(raw_intent.get("naver_render"))
        google_render = _parse_render(raw_intent.get("google_render"))
        shared_render = _parse_shared_render(raw_intent.get("shared_render"))
        if shared_render is None:
            shared_render = _infer_shared_render(naver_render, google_render)
        allowed_platforms = _resolve_allowed_platforms(
            [
            str(platform)
            for platform in raw_intent.get("allowed_platforms", [])
            if str(platform) in {"naver_sa", "google_sa"}
            ],
            requested_platform_mode=request.requested_platform_mode,
            shared_render=shared_render,
            naver_render=naver_render,
            google_render=google_render,
        )
        naver_render, google_render = _hydrate_platform_renders(
            category=str(raw_intent.get("category") or ""),
            requested_platform_mode=request.requested_platform_mode,
            allowed_platforms=allowed_platforms,
            shared_render=shared_render,
            naver_render=naver_render,
            google_render=google_render,
        )

        intents.append(
            CanonicalIntent(
                category=category,
                slot_type=slot_type,
                intent_text=intent_text,
                intent_id=str(raw_intent.get("intent_id") or "").strip() or _intent_id_from_fields(category, intent_text),
                reason=str(raw_intent.get("reason") or ""),
                evidence_tier=str(raw_intent.get("evidence_tier") or "") or None,
                quality_score=str(raw_intent.get("quality_score") or "").strip() or None,
                quality_reason=str(raw_intent.get("quality_reason") or raw_intent.get("reason") or "").strip() or None,
                allowed_platforms=allowed_platforms,
                shared_render=shared_render,
                naver_render=naver_render,
                google_render=google_render,
            )
        )
    return intents


def _parse_items(
    payload_items: list[Any],
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    intents: list[CanonicalIntent] = []
    for raw_item in payload_items:
        if not isinstance(raw_item, dict):
            continue
        category = str(raw_item.get("category") or "").strip()
        keyword = str(raw_item.get("keyword") or "").strip()
        if not category or not keyword:
            continue
        slot_type = str(raw_item.get("slot_type") or "").strip() or _default_legacy_slot_type(category)
        platform_scope = str(raw_item.get("platform_scope") or "").strip().lower()
        if platform_scope in {"all", "both"}:
            allowed_platforms = ["naver_sa", "google_sa"]
        elif platform_scope in {"naver_sa", "google_sa"}:
            allowed_platforms = [platform_scope]
        else:
            allowed_platforms = _requested_platforms(request.requested_platform_mode)
        shared_render = SharedRender(keyword=keyword, admitted=True)
        naver_render, google_render = _hydrate_platform_renders(
            category=category,
            requested_platform_mode=request.requested_platform_mode,
            allowed_platforms=allowed_platforms,
            shared_render=shared_render,
            naver_render=None,
            google_render=None,
        )
        intents.append(
            CanonicalIntent(
                category=category,
                slot_type=slot_type,
                intent_text=keyword,
                intent_id=_intent_id_from_fields(category, keyword),
                reason=str(raw_item.get("reason") or ""),
                evidence_tier=str(raw_item.get("evidence_tier") or "") or None,
                quality_score=str(raw_item.get("quality_score") or "").strip() or None,
                quality_reason=str(raw_item.get("quality_reason") or raw_item.get("reason") or "").strip() or None,
                allowed_platforms=allowed_platforms,
                shared_render=shared_render,
                naver_render=naver_render,
                google_render=google_render,
            )
        )
    return intents


def _parse_shared_render(render_payload: Any) -> SharedRender | None:
    if not isinstance(render_payload, dict):
        return None
    keyword = str(render_payload.get("keyword") or "").strip()
    admitted = bool(render_payload.get("admitted", True))
    if not keyword:
        return None
    return SharedRender(keyword=keyword, admitted=admitted)


def _parse_render(render_payload: Any) -> PlatformRender | None:
    if not isinstance(render_payload, dict):
        return None
    keyword = str(render_payload.get("keyword") or "")
    match_label = str(render_payload.get("match_label") or "")
    admitted = bool(render_payload.get("admitted", True))
    if not keyword or not match_label:
        return None
    return PlatformRender(keyword=keyword, match_label=match_label, admitted=admitted)


def _requested_platforms(platform_mode: str) -> list[str]:
    if platform_mode == "both":
        return ["naver_sa", "google_sa"]
    return [platform_mode]


def _resolve_allowed_platforms(
    raw_allowed_platforms: list[str],
    *,
    requested_platform_mode: str,
    shared_render: SharedRender | None,
    naver_render: PlatformRender | None,
    google_render: PlatformRender | None,
) -> list[str]:
    allowed_platforms = [platform for platform in raw_allowed_platforms if platform in {"naver_sa", "google_sa"}]
    if allowed_platforms:
        return allowed_platforms

    if naver_render:
        allowed_platforms.append("naver_sa")
    if google_render:
        allowed_platforms.append("google_sa")
    if allowed_platforms:
        return allowed_platforms

    if shared_render:
        return _requested_platforms(requested_platform_mode)
    return []


def _infer_shared_render(
    naver_render: PlatformRender | None,
    google_render: PlatformRender | None,
) -> SharedRender | None:
    if naver_render and google_render and naver_render.keyword == google_render.keyword:
        return SharedRender(keyword=naver_render.keyword, admitted=naver_render.admitted and google_render.admitted)
    if naver_render:
        return SharedRender(keyword=naver_render.keyword, admitted=naver_render.admitted)
    if google_render:
        return SharedRender(keyword=google_render.keyword, admitted=google_render.admitted)
    return None


def _default_match_label(category: str, platform: str) -> str:
    if category == NEGATIVE_CATEGORY:
        return "제외키워드" if platform == "naver_sa" else "negative"
    if platform == "naver_sa":
        return "완전일치" if category in {"brand", "purchase_intent"} else "확장소재"
    if category == "brand":
        return "exact"
    if category in {"long_tail", "purchase_intent", "problem_solution"}:
        return "phrase"
    return "broad"


def _hydrate_platform_renders(
    *,
    category: str,
    requested_platform_mode: str,
    allowed_platforms: list[str],
    shared_render: SharedRender | None,
    naver_render: PlatformRender | None,
    google_render: PlatformRender | None,
) -> tuple[PlatformRender | None, PlatformRender | None]:
    if shared_render and shared_render.admitted:
        if "naver_sa" in allowed_platforms and requested_platform_mode in {"naver_sa", "both"} and naver_render is None:
            naver_render = PlatformRender(
                keyword=shared_render.keyword,
                match_label=_default_match_label(category, "naver_sa"),
                admitted=True,
            )
        if "google_sa" in allowed_platforms and requested_platform_mode in {"google_sa", "both"} and google_render is None:
            google_render = PlatformRender(
                keyword=shared_render.keyword,
                match_label=_default_match_label(category, "google_sa"),
                admitted=True,
            )
    return naver_render, google_render


def _upgrade_legacy_rows(
    payload_rows: list[Any],
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    intents: list[CanonicalIntent] = []
    for raw_row in payload_rows:
        if not isinstance(raw_row, dict):
            continue
        naver_match = str(raw_row.get("naver_match") or "")
        google_match = str(raw_row.get("google_match") or "")
        keyword = str(raw_row.get("keyword") or "")
        allowed_platforms: list[str] = []
        naver_render = None
        google_render = None
        if keyword and naver_match:
            naver_render = PlatformRender(keyword=keyword, match_label=naver_match, admitted=True)
            allowed_platforms.append("naver_sa")
        if keyword and google_match:
            google_render = PlatformRender(keyword=keyword, match_label=google_match, admitted=True)
            allowed_platforms.append("google_sa")
        shared_render = SharedRender(keyword=keyword, admitted=True) if keyword else None
        category = str(raw_row.get("category") or "")
        slot_type = str(raw_row.get("slot_type") or "").strip() or _default_legacy_slot_type(category)
        intents.append(
            CanonicalIntent(
                category=category,
                slot_type=slot_type,
                intent_text=keyword,
                intent_id=_intent_id_from_fields(category, keyword),
                reason=str(raw_row.get("reason") or ""),
                evidence_tier=str(raw_row.get("evidence_tier") or "") or None,
                allowed_platforms=allowed_platforms,
                shared_render=shared_render,
                naver_render=naver_render,
                google_render=google_render,
            )
        )
    return intents


def _default_legacy_slot_type(category: str) -> str:
    defaults = {
        "brand": "product_name",
        "generic_category": "generic_type_phrase",
        "feature_attribute": "spec",
        "competitor_comparison": "competitor_brand_type",
        "purchase_intent": "navigational_alias",
        "long_tail": "use_case_phrase",
        "benefit_price": "product_price",
        "season_event": "seasonal_context",
        "problem_solution": "problem_noun_phrase",
        NEGATIVE_CATEGORY: "negative_exclusion",
    }
    return defaults.get(category, "surface")


def _load_response_payload(response_text: str) -> Any:
    candidates = [_strip_code_fences(response_text), response_text.strip()]
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        parsed = _try_json_load(candidate)
        if parsed is not None:
            return parsed
        parsed = _try_json_load(_extract_outer_json(candidate))
        if parsed is not None:
            return parsed
    raise ValueError("Bedrock response is not valid JSON")


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped.strip("`").strip()


def _extract_outer_json(text: str) -> str:
    start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not start_candidates:
        return text
    start = min(start_candidates)
    end_brace = text.rfind("}")
    end_bracket = text.rfind("]")
    end = max(end_brace, end_bracket)
    if end <= start:
        return text
    return text[start : end + 1]


def _try_json_load(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _find_payload_container(payload: Any, *, required_keys: set[str]) -> Any:
    visited: set[int] = set()

    def walk(node: Any) -> Any | None:
        node_id = id(node)
        if node_id in visited:
            return None
        visited.add(node_id)

        if isinstance(node, dict):
            if any(key in node for key in required_keys):
                return node
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        elif isinstance(node, str):
            candidate = node.strip()
            if candidate.startswith("{") or candidate.startswith("[") or candidate.startswith("```"):
                parsed = _try_json_load(_strip_code_fences(candidate))
                if parsed is None:
                    parsed = _try_json_load(_extract_outer_json(candidate))
                if parsed is not None:
                    found = walk(parsed)
                    if found is not None:
                        return found
        return None

    return walk(payload) or payload


def _intent_id_from_fields(category: str, intent_text: str) -> str:
    seed = f"{category}|{intent_text}".encode("utf-8")
    return hashlib.sha1(seed).hexdigest()[:16]




