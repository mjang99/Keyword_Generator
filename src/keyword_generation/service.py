from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any

from .bedrock_adapter import (
    BedrockResponseParseError,
    generate_intents_via_bedrock,
    intents_to_rows,
    run_dedup_quality_pass,
    run_supplementation_pass,
    should_use_bedrock,
)
from .constants import (
    GOOGLE_ALLOWED_MATCHES,
    NAVER_ALLOWED_MATCHES,
    NEGATIVE_CATEGORY,
    NEGATIVE_KEYWORD_SEEDS,
    POSITIVE_CATEGORIES,
    POSITIVE_CATEGORY_TARGETS,
    PROMO_BANNED_TERMS,
    URGENCY_BANNED_TERMS,
)
from .models import (
    CanonicalIntent,
    GenerationRequest,
    GenerationResult,
    KeywordRow,
    PlatformRender,
    SharedRender,
    SlotPlanItem,
    ValidationReport,
)
from .policy import (
    canonical_brand as resolved_policy_brand,
    competitor_brand_terms,
    filter_keyword_rows,
    generic_category_terms,
    is_low_information_keyword as policy_is_low_information_keyword,
    resolve_product_types,
    taxonomy_terms,
)
from .validation import validate_keyword_rows

SUPPORT_PAGE_CLASSES = {"support_spec_page", "document_download_heavy_support_page"}
SHALLOW_SUFFIX_TOKENS = {
    "추천",
    "후기",
    "리뷰",
    "비교",
    "정품",
    "공식",
    "사용법",
    "가이드",
    "브랜드",
    "공식몰",
    "카테고리",
}
STORE_SUFFIX_TOKENS = {
    "한국",
    "대한민국",
    "kr",
    "korea",
    "공식몰",
    "공식",
    "온라인",
    "스토어",
    "support",
    "지원",
}
LOW_INFORMATION_TOKENS = {
    "검색",
    "정리",
    "탐색",
    "후기",
    "베스트",
    "카테고리",
    "정식",
}
DIRECT_VALUE_SIGNAL_TERMS = (
    "가성비",
    "합리적 가격",
    "합리적인 가격",
    "경제적",
    "경제적인",
    "best value",
    "value for money",
)
ATTRIBUTE_FACT_TYPES = {
    "attribute",
    "volume",
    "feature",
    "variant",
    "chip",
    "cpu",
    "gpu",
    "memory",
    "storage",
    "display",
    "battery_life",
    "weight",
    "connectivity",
    "compatibility",
    "key_ingredient",
    "texture",
    "skin_type",
    "free_from",
}
BENEFIT_FACT_TYPES = {"benefit", "award"}
USE_CASE_FACT_TYPES = {"use_case", "usage", "audience"}
CONCERN_FACT_TYPES = {"concern", "problem_solution"}
VERBOSE_SURFACE_ENV = "KEYWORD_GENERATOR_ENABLE_VERBOSE_SEARCH_SURFACES"
PURCHASE_SUFFIX_TOKENS = ("구매", "주문", "구입", "buy", "order", "shop")
VERBISH_SURFACE_TOKENS = (
    "그림 그리기",
    "메모",
    "문서 주석 작성",
    "주석 작성",
    "drawing",
    "note taking",
    "taking notes",
    "annotation",
    "annotating",
    "auto pairing",
)
INFORMATIONAL_SURFACE_TOKENS = (
    "방법",
    "사용법",
    "가이드",
    "guide",
    "how to",
    "tutorial",
    "설정",
    "세팅",
    "연결",
    "pairing",
    "호환 방법",
)
PROMO_EVENT_TOKENS = (
    "블랙프라이데이",
    "black friday",
    "사이버먼데이",
    "cyber monday",
    "프라임데이",
    "prime day",
    "boxing day",
    "광군제",
    "11.11",
)


def _allow_verbose_search_surfaces() -> bool:
    return os.environ.get(VERBOSE_SURFACE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProductInterpretation:
    product_name: str
    brand: str
    canonical_category: str
    secondary_categories: list[str]
    generic_type_phrases: list[str]
    navigational_aliases: list[str]
    form_factors: list[str]
    audience: list[str]
    benefits: list[str]
    concerns: list[str]
    problem_noun_phrases: list[str]
    usage_context: list[str]
    ingredients: list[str]
    technology: list[str]
    specs: list[str]
    grounded_event_terms: list[str]
    price_band_candidates: list[str]
    commerce_facts: dict[str, Any]


_CATEGORY_SLOT_SHAPES: dict[str, dict[str, list[str]]] = {
    "brand": {
        "product_name": ["제품명", "브랜드+제품명"],
        "brand_with_type": ["브랜드+제품유형"],
        "navigational_alias": ["짧은 모델 alias", "브랜드 축약 탐색형"],
    },
    "generic_category": {
        "generic_type_phrase": ["상위 제품유형", "일반 탐색형 제품유형"],
    },
    "feature_attribute": {
        "spec": ["용량", "세대", "규격", "핵심 spec"],
        "core_attribute": ["성분", "기술", "제형 기반 noun phrase"],
    },
    "purchase_intent": {
        "navigational_alias": ["정확 제품명", "짧은 모델 alias"],
        "brand_with_type": ["브랜드+제품유형 탐색"],
    },
    "long_tail": {
        "use_case_phrase": ["용도형 noun phrase", "조합형 탐색 surface"],
        "audience_phrase": ["사용자군+제품유형"],
    },
    "benefit_price": {
        "product_price": ["<제품명> 가격"],
        "price_band": ["<price band> + 제품유형"],
    },
    "season_event": {
        "grounded_event": ["근거 있는 이벤트+제품유형"],
        "seasonal_context": ["시즌/상황 noun phrase"],
    },
    "problem_solution": {
        "problem_noun_phrase": ["문제+제품유형", "용도형 noun phrase"],
    },
    "competitor_comparison": {
        "competitor_brand_type": ["경쟁 브랜드+제품유형"],
    },
    NEGATIVE_CATEGORY: {
        "negative_exclusion": ["광고 제외 탐색어"],
    },
}

_CATEGORY_SLOT_FORBIDDENS: dict[str, dict[str, list[str]]] = {
    "brand": {
        "product_name": ["정보성/how-to", "product+purpose suffix"],
        "brand_with_type": ["raw exact price", "unsupported promo event"],
        "navigational_alias": ["verb/action suffix", "방법/사용법"],
    },
    "generic_category": {
        "generic_type_phrase": ["product+action", "정보성/how-to"],
    },
    "feature_attribute": {
        "spec": ["benefit sentence", "raw exact price"],
        "core_attribute": ["방법/가이드", "product+purpose suffix"],
    },
    "purchase_intent": {
        "navigational_alias": ["구매/주문 suffix", "product+action"],
        "brand_with_type": ["방법/가이드", "raw exact price"],
    },
    "long_tail": {
        "use_case_phrase": ["정보성/how-to", "product+action"],
        "audience_phrase": ["raw exact price", "unsupported promo event"],
    },
    "benefit_price": {
        "product_price": ["raw exact price number only"],
        "price_band": ["unsupported promo event", "product+purpose suffix"],
    },
    "season_event": {
        "grounded_event": ["unsupported promo event"],
        "seasonal_context": ["product+purpose suffix", "방법/가이드"],
    },
    "problem_solution": {
        "problem_noun_phrase": ["정보성/how-to", "product+purpose suffix"],
    },
    "competitor_comparison": {
        "competitor_brand_type": ["same-product measurement comparison", "generic comparison without competitor brand"],
    },
    NEGATIVE_CATEGORY: {
        "negative_exclusion": ["domain-mismatched negative"],
    },
}


def _slot_key(category: str, slot_type: str) -> str:
    return f"{category}:{slot_type}"


def _allowed_shapes(category: str, slot_type: str) -> list[str]:
    return list(_CATEGORY_SLOT_SHAPES.get(category, {}).get(slot_type, []))


def _forbidden_shapes(category: str, slot_type: str) -> list[str]:
    return list(_CATEGORY_SLOT_FORBIDDENS.get(category, {}).get(slot_type, []))


def _serialize_interpretation(interpretation: ProductInterpretation) -> dict[str, Any]:
    return {
        "product_name": interpretation.product_name,
        "brand": interpretation.brand,
        "canonical_category": interpretation.canonical_category,
        "secondary_categories": interpretation.secondary_categories,
        "generic_type_phrases": interpretation.generic_type_phrases,
        "navigational_aliases": interpretation.navigational_aliases,
        "form_factors": interpretation.form_factors,
        "audience": interpretation.audience,
        "benefits": interpretation.benefits,
        "concerns": interpretation.concerns,
        "problem_noun_phrases": interpretation.problem_noun_phrases,
        "usage_context": interpretation.usage_context,
        "ingredients": interpretation.ingredients,
        "technology": interpretation.technology,
        "specs": interpretation.specs,
        "grounded_event_terms": interpretation.grounded_event_terms,
        "price_band_candidates": interpretation.price_band_candidates,
        "commerce_facts": interpretation.commerce_facts,
    }


def _serialize_slot_plan(slot_plan: list[SlotPlanItem]) -> list[dict[str, Any]]:
    return [
        {
            "category": item.category,
            "slot_type": item.slot_type,
            "target_count": item.target_count,
            "required": item.required,
            "seed_phrases": item.seed_phrases,
            "allowed_shapes": item.allowed_shapes,
            "forbidden_shapes": item.forbidden_shapes,
        }
        for item in slot_plan
    ]


def _primary_slot_type_for_category(category: str, active_slot_types: list[str]) -> str | None:
    preferred_order = {
        "brand": ["product_name", "brand_with_type", "navigational_alias"],
        "generic_category": ["generic_type_phrase"],
        "feature_attribute": ["spec", "core_attribute"],
        "competitor_comparison": ["competitor_brand_type"],
        "purchase_intent": ["navigational_alias", "brand_with_type"],
        "long_tail": ["use_case_phrase", "audience_phrase"],
        "benefit_price": ["product_price", "price_band"],
        "season_event": ["grounded_event", "seasonal_context"],
        "problem_solution": ["problem_noun_phrase"],
        NEGATIVE_CATEGORY: ["negative_exclusion"],
    }
    for slot_type in preferred_order.get(category, []):
        if slot_type in active_slot_types:
            return slot_type
    return active_slot_types[0] if active_slot_types else None


def _distribute_preferred_slot_targets(
    total: int,
    seed_groups: list[list[str]],
    *,
    primary_index: int,
) -> list[int]:
    if total <= 0 or not seed_groups:
        return [0 for _ in seed_groups]

    targets = [0 for _ in seed_groups]
    primary_index = max(0, min(primary_index, len(seed_groups) - 1))
    targets[primary_index] = 1
    remaining = max(0, total - 1)
    if remaining == 0:
        return targets

    weights = [max(1, len(group)) for group in seed_groups]
    weight_sum = sum(weights)
    if weight_sum <= 0:
        targets[primary_index] += remaining
        return targets

    allocated = 0
    for index, weight in enumerate(weights):
        extra = int((remaining * weight) / weight_sum)
        targets[index] += extra
        allocated += extra

    remainder = remaining - allocated
    if remainder > 0:
        ranked = sorted(range(len(weights)), key=lambda index: (weights[index], index == primary_index), reverse=True)
        for index in ranked[:remainder]:
            targets[index] += 1

    return targets


def _build_slot_plan(
    interpretation: ProductInterpretation,
    *,
    category_plan: dict[str, int],
) -> list[SlotPlanItem]:
    slot_plan: list[SlotPlanItem] = []

    slot_sources: dict[str, list[tuple[str, list[str]]]] = {
        "brand": [
            ("product_name", _unique_texts([interpretation.product_name, *interpretation.navigational_aliases[:2]])),
            ("brand_with_type", _unique_texts([f"{interpretation.brand} {term}" for term in interpretation.generic_type_phrases[:3] if interpretation.brand])),
            ("navigational_alias", interpretation.navigational_aliases[:4]),
        ],
        "generic_category": [
            ("generic_type_phrase", interpretation.generic_type_phrases[:6]),
        ],
        "feature_attribute": [
            ("spec", interpretation.specs[:6]),
            ("core_attribute", _unique_texts([*interpretation.ingredients[:4], *interpretation.technology[:4], *interpretation.form_factors[:4]])),
        ],
        "purchase_intent": [
            ("navigational_alias", interpretation.navigational_aliases[:6]),
            ("brand_with_type", _unique_texts([f"{interpretation.brand} {term}" for term in interpretation.generic_type_phrases[:3] if interpretation.brand])),
        ],
        "long_tail": [
            ("use_case_phrase", _unique_texts([*interpretation.problem_noun_phrases[:4], *interpretation.usage_context[:4]])),
            ("audience_phrase", _unique_texts([f"{audience} {term}" for audience in interpretation.audience[:3] for term in interpretation.generic_type_phrases[:2]])),
        ],
        "benefit_price": [
            ("product_price", [f"{interpretation.product_name} 가격"] if interpretation.commerce_facts.get("price_allowed") else []),
            ("price_band", interpretation.price_band_candidates[:4]),
        ],
        "season_event": [
            ("grounded_event", _unique_texts([f"{term} {type_phrase}" for term in interpretation.grounded_event_terms[:3] for type_phrase in interpretation.generic_type_phrases[:2]])),
            ("seasonal_context", _unique_texts([f"{context} {type_phrase}" for context in interpretation.usage_context[:3] for type_phrase in interpretation.generic_type_phrases[:2]])),
        ],
        "problem_solution": [
            ("problem_noun_phrase", interpretation.problem_noun_phrases[:8]),
        ],
        "competitor_comparison": [
            ("competitor_brand_type", _unique_texts([f"{brand} {type_phrase}" for brand in interpretation.commerce_facts.get("competitor_brand_hints", [])[:6] for type_phrase in interpretation.generic_type_phrases[:2]])),
        ],
        NEGATIVE_CATEGORY: [
            ("negative_exclusion", NEGATIVE_KEYWORD_SEEDS[:6]),
        ],
    }

    for category, total_target in {**category_plan, NEGATIVE_CATEGORY: 1}.items():
        if total_target <= 0:
            continue
        raw_specs = slot_sources.get(category, [])
        active_specs = [(slot_type, seeds) for slot_type, seeds in raw_specs if seeds]
        if not active_specs:
            continue
        primary_slot_type = _primary_slot_type_for_category(
            category,
            [slot_type for slot_type, _ in active_specs],
        )
        if primary_slot_type is None:
            continue
        primary_index = next(
            index
            for index, (slot_type, _) in enumerate(active_specs)
            if slot_type == primary_slot_type
        )
        targets = _distribute_preferred_slot_targets(
            total_target,
            [seeds for _, seeds in active_specs],
            primary_index=primary_index,
        )
        for (slot_type, seeds), slot_target in zip(active_specs, targets, strict=False):
            if slot_target <= 0:
                continue
            slot_plan.append(
                SlotPlanItem(
                    category=category,
                    slot_type=slot_type,
                    target_count=slot_target,
                    required=slot_type == primary_slot_type,
                    seed_phrases=seeds[:8],
                    allowed_shapes=_allowed_shapes(category, slot_type),
                    forbidden_shapes=_forbidden_shapes(category, slot_type),
                )
            )

    return slot_plan


def _default_slot_type(category: str) -> str:
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


def _infer_slot_type_for_keyword(
    category: str,
    keyword: str,
    interpretation: ProductInterpretation,
) -> str:
    normalized = " ".join(keyword.split()).strip()
    lowered = normalized.casefold()

    if category == "brand":
        if normalized in interpretation.navigational_aliases:
            return "navigational_alias"
        if interpretation.brand and interpretation.brand.casefold() in lowered and any(
            term.casefold() in lowered for term in interpretation.generic_type_phrases
        ):
            return "brand_with_type"
        return "product_name"

    if category == "generic_category":
        return "generic_type_phrase"

    if category == "feature_attribute":
        if _is_measurementish_term(normalized):
            return "spec"
        if any(value.casefold() in lowered for value in [*interpretation.ingredients, *interpretation.technology, *interpretation.form_factors]):
            return "core_attribute"
        return "spec"

    if category == "purchase_intent":
        if normalized in interpretation.navigational_aliases or _is_short_model_alias_surface(
            normalized, product_name=interpretation.product_name
        ):
            return "navigational_alias"
        return "brand_with_type"

    if category == "long_tail":
        if any(audience.casefold() in lowered for audience in interpretation.audience):
            return "audience_phrase"
        return "use_case_phrase"

    if category == "benefit_price":
        if _is_price_band_surface(normalized):
            return "price_band"
        return "product_price"

    if category == "season_event":
        if any(term.casefold() in lowered for term in interpretation.grounded_event_terms):
            return "grounded_event"
        return "seasonal_context"

    if category == "problem_solution":
        return "problem_noun_phrase"

    if category == "competitor_comparison":
        return "competitor_brand_type"

    if category == NEGATIVE_CATEGORY:
        return "negative_exclusion"

    return _default_slot_type(category)


def generate_keywords(request: GenerationRequest) -> GenerationResult:
    """Generate keyword rows from an evidence pack.

    In Bedrock mode: runs the 3-call LLM pipeline (generate ??dedup+quality ??supplement).
    In fallback mode: uses the deterministic generator (local testing path).
    """
    if request.requested_platform_mode not in {"naver_sa", "google_sa", "both"}:
        raise ValueError(f"Unsupported platform mode: {request.requested_platform_mode}")

    if not request.evidence_pack:
        raise ValueError("evidence_pack is required")

    request.evidence_pack.setdefault("canonical_product_name", _canonical_product_name(request.evidence_pack))

    if should_use_bedrock():
        try:
            return _bedrock_pipeline(request)
        except Exception as exc:
            failure = empty_failure_result(
                request,
                failure_code="generation_rule_violation",
                failure_detail=f"bedrock_pipeline_error: {type(exc).__name__}: {exc}",
            )
            failure.debug_payload = _pipeline_error_debug_payload(exc)
            return failure

    return _fallback_pipeline(request)


def _bedrock_pipeline(request: GenerationRequest) -> GenerationResult:
    """Adaptive LLM pipeline: batched generate -> dedup+quality -> batched supplement -> hard rules."""
    evidence_pack = request.evidence_pack
    quality_warning = bool(evidence_pack.get("quality_warning", False))
    generation_target = request.initial_generation_target
    generation_category_plan = _llm_category_plan(generation_target)
    final_category_plan = _llm_category_plan(request.max_keywords_per_platform)
    interpretation = _build_product_interpretation(evidence_pack)
    interpretation_payload = _serialize_interpretation(interpretation)
    generation_slot_plan = _build_slot_plan(interpretation, category_plan=generation_category_plan)
    generation_slot_plan_payload = _serialize_slot_plan(generation_slot_plan)
    supplementation_slot_plan = _build_slot_plan(interpretation, category_plan=final_category_plan)
    supplementation_slot_plan_payload = _serialize_slot_plan(supplementation_slot_plan)
    debug_payload: dict[str, Any] = {"generation": {}}

    # Step A: cluster-first generation, then split only weak clusters
    initial_batch_plans = _generation_batch_plans(
        category_plan=generation_category_plan,
        slot_plan=generation_slot_plan,
    )
    generated_intents: list[CanonicalIntent] = []
    batch_debug: list[dict[str, Any]] = []
    split_batch_debug: list[dict[str, Any]] = []
    split_batch_names: set[str] = set()
    for batch_plan in initial_batch_plans:
        batch_intents, batch_result = _run_generation_batch(
            request=request,
            batch_plan=batch_plan,
            interpretation_payload=interpretation_payload,
        )
        generated_intents.extend(batch_intents)
        batch_debug.append(batch_result)
        if batch_result["weak_reasons"] and batch_plan["split_groups"]:
            split_batch_names.add(str(batch_plan["name"]))
            for split_plan in _split_generation_batch_plans(
                batch_plan=batch_plan,
                category_plan=generation_category_plan,
                slot_plan=generation_slot_plan,
            ):
                split_intents, split_result = _run_generation_batch(
                    request=request,
                    batch_plan=split_plan,
                    interpretation_payload=interpretation_payload,
                )
                generated_intents.extend(split_intents)
                split_batch_debug.append(split_result)

    intents = generated_intents
    if not intents:
        raise ValueError("Bedrock returned no canonical intents")
    debug_payload["generation"] = {
        "slot_plan": generation_slot_plan_payload,
        "supplementation_slot_plan": supplementation_slot_plan_payload,
        "generation_batches": batch_debug,
        "split_batches": split_batch_debug,
        "split_batch_names": sorted(split_batch_names),
        "raw_generation_intents": [_intent_debug_payload(intent) for intent in intents],
    }

    # Step B: LLM semantic dedup + quality evaluation
    dedup_result = run_dedup_quality_pass(
        intents,
        request=request,
        platform=request.requested_platform_mode,
        positive_floor=request.max_keywords_per_platform,
        positive_category_targets=final_category_plan,
        return_metadata=True,
    )
    dedup_report, dedup_meta = _with_optional_metadata(dedup_result)
    surviving_intents = dedup_report.surviving_keywords
    debug_payload["generation"]["dedup_report"] = _dedup_report_payload(dedup_report)
    debug_payload["generation"]["bedrock_dedup_metadata"] = dedup_meta
    surviving_rows = intents_to_rows(surviving_intents, request=request)
    slot_gap_report = _platform_slot_gap_report(
        surviving_rows,
        requested_platform_mode=request.requested_platform_mode,
        slot_plan=supplementation_slot_plan,
    )
    category_gap_report = _platform_category_gap_report(
        surviving_rows,
        requested_platform_mode=request.requested_platform_mode,
    )
    debug_payload["generation"]["pre_policy_slot_gap_report"] = slot_gap_report
    debug_payload["generation"]["pre_policy_category_gap_report"] = category_gap_report

    # Step C: LLM supplementation ??runs only when gaps remain, at most once
    supplementation_attempts = 0
    supplement_targets = _supplementation_slot_targets(
        category_gap_report=category_gap_report,
        slot_gap_report=slot_gap_report,
        slot_plan=supplementation_slot_plan,
        rows=surviving_rows,
        requested_platform_mode=request.requested_platform_mode,
        positive_target=request.max_keywords_per_platform,
    )
    debug_payload["generation"]["supplement_targets"] = dict(supplement_targets)
    if supplement_targets.get("_total", 0) > 0 and supplementation_attempts < request.supplementation_pass_limit:
        supplementation_attempts += 1
        supplement_batches = _supplementation_batch_plans(
            gap_slots=supplement_targets,
            missing_categories=sorted(
                category
                for category, missing in (category_gap_report.get("aggregate") or {}).items()
                if int(missing) > 0
            ),
            category_plan=final_category_plan,
            slot_plan=supplementation_slot_plan,
            split_batch_names=split_batch_names,
        )
        debug_payload["generation"]["supplementation_batches"] = []
        supplement_intents: list[CanonicalIntent] = []
        for batch_plan in supplement_batches:
            batch_intents, batch_result = _run_supplementation_batch(
                request=request,
                batch_plan=batch_plan,
                gap_slots=batch_plan["gap_slots"],
                missing_categories=batch_plan["missing_categories"],
                surviving_intents=surviving_intents,
                interpretation_payload=interpretation_payload,
            )
            supplement_intents.extend(batch_intents)
            debug_payload["generation"]["supplementation_batches"].append(batch_result)
        surviving_intents = surviving_intents + supplement_intents

    # Convert to rows
    all_rows = intents_to_rows(surviving_intents, request=request)
    debug_payload["generation"]["pre_policy_rows"] = [_row_debug_payload(row) for row in all_rows]

    # Step D: Hard rule pass ??drop rows that violate compliance rules (promo/urgency/match labels)
    clean_rows = _hard_rule_pass(all_rows, requested_platform_mode=request.requested_platform_mode)
    clean_rows, policy_drop_rows = filter_keyword_rows(clean_rows, evidence_pack=evidence_pack)
    clean_rows, surface_drop_rows = _surface_cleanup_rows_with_reasons(clean_rows, evidence_pack=evidence_pack)
    surviving_intents = _rows_to_intents(clean_rows, requested_platform_mode=request.requested_platform_mode)
    debug_payload["generation"]["post_policy_rows"] = [_row_debug_payload(row) for row in clean_rows]
    debug_payload["generation"]["dropped_rows"] = _dropped_row_payload(all_rows, clean_rows)
    debug_payload["generation"]["slot_drop_report"] = _build_slot_drop_report(
        all_intents=intents + _rows_to_intents(all_rows, requested_platform_mode=request.requested_platform_mode),
        dedup_report=dedup_report,
        policy_drop_rows=policy_drop_rows,
        surface_drop_rows=surface_drop_rows,
    )

    post_filter_gap_report = _platform_slot_gap_report(
        clean_rows,
        requested_platform_mode=request.requested_platform_mode,
        slot_plan=supplementation_slot_plan,
    )
    post_filter_category_gap_report = _platform_category_gap_report(
        clean_rows,
        requested_platform_mode=request.requested_platform_mode,
    )
    debug_payload["generation"]["slot_gap_report"] = post_filter_gap_report
    debug_payload["generation"]["category_gap_report"] = post_filter_category_gap_report

    repair_targets = _supplementation_slot_targets(
        category_gap_report=post_filter_category_gap_report,
        slot_gap_report=post_filter_gap_report,
        slot_plan=supplementation_slot_plan,
        rows=clean_rows,
        requested_platform_mode=request.requested_platform_mode,
        positive_target=request.max_keywords_per_platform,
    )
    debug_payload["generation"]["repair_supplement_targets"] = dict(repair_targets)
    if repair_targets.get("_total", 0) > 0 and supplementation_attempts < request.supplementation_pass_limit:
        supplementation_attempts += 1
        repair_batches = _supplementation_batch_plans(
            gap_slots=repair_targets,
            missing_categories=sorted(
                category
                for category, missing in (post_filter_category_gap_report.get("aggregate") or {}).items()
                if int(missing) > 0
            ),
            category_plan=final_category_plan,
            slot_plan=supplementation_slot_plan,
            split_batch_names=split_batch_names,
        )
        debug_payload["generation"]["repair_batches"] = []
        repair_intents: list[CanonicalIntent] = []
        for batch_plan in repair_batches:
            batch_intents, batch_result = _run_supplementation_batch(
                request=request,
                batch_plan=batch_plan,
                gap_slots=batch_plan["gap_slots"],
                missing_categories=batch_plan["missing_categories"],
                surviving_intents=surviving_intents,
                interpretation_payload=interpretation_payload,
            )
            repair_intents.extend(batch_intents)
            debug_payload["generation"]["repair_batches"].append(batch_result)
        surviving_intents = surviving_intents + repair_intents
        all_rows = intents_to_rows(surviving_intents, request=request)
        clean_rows = _hard_rule_pass(all_rows, requested_platform_mode=request.requested_platform_mode)
        clean_rows, repair_policy_drop_rows = filter_keyword_rows(clean_rows, evidence_pack=evidence_pack)
        clean_rows, repair_surface_drop_rows = _surface_cleanup_rows_with_reasons(clean_rows, evidence_pack=evidence_pack)
        surviving_intents = _rows_to_intents(clean_rows, requested_platform_mode=request.requested_platform_mode)
        debug_payload["generation"]["pre_policy_rows_after_repair"] = [_row_debug_payload(row) for row in all_rows]
        debug_payload["generation"]["post_policy_rows_after_repair"] = [_row_debug_payload(row) for row in clean_rows]
        debug_payload["generation"]["dropped_rows_after_repair"] = _dropped_row_payload(all_rows, clean_rows)
        debug_payload["generation"]["slot_drop_report_after_repair"] = _build_slot_drop_report(
            all_intents=_rows_to_intents(all_rows, requested_platform_mode=request.requested_platform_mode),
            dedup_report=None,
            policy_drop_rows=repair_policy_drop_rows,
            surface_drop_rows=repair_surface_drop_rows,
        )
        debug_payload["generation"]["slot_gap_report_after_repair"] = _platform_slot_gap_report(
            clean_rows,
            requested_platform_mode=request.requested_platform_mode,
            slot_plan=supplementation_slot_plan,
        )
        debug_payload["generation"]["category_gap_report_after_repair"] = _platform_category_gap_report(
            clean_rows,
            requested_platform_mode=request.requested_platform_mode,
        )

    # Step E: Final floor validation (count, category coverage, negative presence)
    final_report = validate_keyword_rows(
        clean_rows,
        requested_platform_mode=request.requested_platform_mode,
        quality_warning=quality_warning,
        evidence_pack=evidence_pack,
    )

    if final_report.status == "COMPLETED":
        return GenerationResult(
            status="COMPLETED",
            requested_platform_mode=request.requested_platform_mode,
            rows=clean_rows,
            intents=surviving_intents,
            supplementation_attempts=supplementation_attempts,
            validation_report=final_report,
            debug_payload=debug_payload,
        )

    failure = empty_failure_result(
        request,
        failure_code=final_report.failure_code or "generation_count_shortfall",
        failure_detail=final_report.failure_detail or "LLM pipeline failed final floor check",
    )
    failure.rows = clean_rows
    failure.intents = surviving_intents
    failure.supplementation_attempts = supplementation_attempts
    failure.validation_report = final_report
    failure.debug_payload = debug_payload
    return failure


def _llm_category_plan(positive_target: int) -> dict[str, int]:
    if positive_target <= 0:
        return {category: 0 for category in POSITIVE_CATEGORIES}

    total_default = sum(POSITIVE_CATEGORY_TARGETS.values())
    if positive_target == total_default:
        return dict(POSITIVE_CATEGORY_TARGETS)

    categories = list(POSITIVE_CATEGORIES)
    plan = {category: 1 for category in categories}
    remaining = max(0, positive_target - len(categories))
    if remaining == 0:
        return plan

    scaled_targets: dict[str, float] = {}
    for category, target in POSITIVE_CATEGORY_TARGETS.items():
        scaled_targets[category] = max(0.0, (target / total_default) * remaining)

    allocated = 0
    for category in categories:
        extra = int(scaled_targets[category])
        plan[category] += extra
        allocated += extra

    remainder = remaining - allocated
    if remainder > 0:
        ranked = sorted(
            categories,
            key=lambda category: (scaled_targets[category] - int(scaled_targets[category]), POSITIVE_CATEGORY_TARGETS[category]),
            reverse=True,
        )
        for category in ranked[:remainder]:
            plan[category] += 1

    return plan


def _generation_batch_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "name": "cluster_a",
            "categories": ("brand", "generic_category", "purchase_intent"),
            "split_groups": (("brand", "generic_category"), ("purchase_intent",)),
        },
        {
            "name": "cluster_b",
            "categories": ("feature_attribute", "benefit_price"),
            "split_groups": (("feature_attribute",), ("benefit_price",)),
        },
        {
            "name": "cluster_c",
            "categories": ("long_tail", "problem_solution", "season_event"),
            "split_groups": (("long_tail", "problem_solution"), ("season_event",)),
        },
        {
            "name": "cluster_d",
            "categories": ("competitor_comparison", NEGATIVE_CATEGORY),
            "split_groups": (("competitor_comparison",), (NEGATIVE_CATEGORY,)),
        },
    ]


def _build_batch_plan(
    *,
    name: str,
    categories: tuple[str, ...],
    split_groups: tuple[tuple[str, ...], ...],
    category_plan: dict[str, int],
    slot_plan: list[SlotPlanItem],
) -> dict[str, Any] | None:
    batch_slot_plan = [slot for slot in slot_plan if slot.category in categories]
    category_targets = {
        category: int(category_plan.get(category, 0))
        for category in categories
        if category != NEGATIVE_CATEGORY and int(category_plan.get(category, 0)) > 0
    }
    include_negative = NEGATIVE_CATEGORY in categories
    if not batch_slot_plan and not category_targets and not include_negative:
        return None
    target_count = sum(category_targets.values()) + (1 if include_negative else 0)
    return {
        "name": name,
        "categories": categories,
        "split_groups": split_groups,
        "category_targets": category_targets,
        "slot_plan": batch_slot_plan,
        "target_count": target_count,
    }


def _generation_batch_plans(
    *,
    category_plan: dict[str, int],
    slot_plan: list[SlotPlanItem],
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for blueprint in _generation_batch_blueprints():
        plan = _build_batch_plan(
            name=str(blueprint["name"]),
            categories=tuple(blueprint["categories"]),
            split_groups=tuple(blueprint["split_groups"]),
            category_plan=category_plan,
            slot_plan=slot_plan,
        )
        if plan is not None:
            plans.append(plan)
    return plans


def _split_generation_batch_plans(
    *,
    batch_plan: dict[str, Any],
    category_plan: dict[str, int],
    slot_plan: list[SlotPlanItem],
) -> list[dict[str, Any]]:
    split_plans: list[dict[str, Any]] = []
    for index, categories in enumerate(batch_plan.get("split_groups") or [], start=1):
        plan = _build_batch_plan(
            name=f"{batch_plan['name']}_split_{index}",
            categories=tuple(categories),
            split_groups=(),
            category_plan=category_plan,
            slot_plan=slot_plan,
        )
        if plan is not None:
            split_plans.append(plan)
    return split_plans


def _batch_category_hits(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: str,
    categories: tuple[str, ...],
) -> dict[str, int]:
    hits = {category: 0 for category in categories}
    for row in rows:
        if row.category not in hits:
            continue
        if requested_platform_mode == "naver_sa" and not row.naver_match:
            continue
        if requested_platform_mode == "google_sa" and not row.google_match:
            continue
        if requested_platform_mode == "both" and not (row.naver_match or row.google_match):
            continue
        hits[row.category] += 1
    return hits


def _weak_generation_batch_reasons(
    *,
    batch_plan: dict[str, Any],
    rows: list[KeywordRow],
    requested_platform_mode: str,
) -> list[str]:
    category_hits = _batch_category_hits(
        rows,
        requested_platform_mode=requested_platform_mode,
        categories=tuple(batch_plan["categories"]),
    )
    required_categories = [
        category for category in batch_plan["categories"] if category in POSITIVE_CATEGORIES or category == NEGATIVE_CATEGORY
    ]
    missing_categories = [category for category in required_categories if category_hits.get(category, 0) <= 0]
    reasons: list[str] = []
    if missing_categories:
        reasons.append("missing_categories:" + ",".join(missing_categories))

    row_count = sum(category_hits.values())
    minimum_expected = max(len(required_categories), int(max(1, batch_plan["target_count"]) * 0.35))
    if row_count < minimum_expected:
        reasons.append(f"low_volume:{row_count}<{minimum_expected}")
    return reasons


def _run_generation_batch(
    *,
    request: GenerationRequest,
    batch_plan: dict[str, Any],
    interpretation_payload: dict[str, Any],
) -> tuple[list[CanonicalIntent], dict[str, Any]]:
    slot_plan_payload = _serialize_slot_plan(batch_plan["slot_plan"])
    try:
        generation_result = generate_intents_via_bedrock(
            request,
            positive_target=max(1, int(batch_plan["target_count"])),
            positive_category_targets=batch_plan["category_targets"],
            interpretation_payload=interpretation_payload,
            slot_plan=slot_plan_payload,
            target_categories=list(batch_plan["categories"]),
            batch_name=str(batch_plan["name"]),
            return_metadata=True,
        )
    except BedrockResponseParseError as exc:
        exc.debug_payload = {
            "generation": {
                "error": {
                    "stage": exc.stage,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "batch_name": batch_plan["name"],
                    "categories": list(batch_plan["categories"]),
                    "target_count": batch_plan["target_count"],
                    "category_targets": dict(batch_plan["category_targets"]),
                    "slot_plan": slot_plan_payload,
                    "model_id": exc.model_id,
                    "metadata": dict(exc.metadata),
                    "response_text": exc.response_text,
                }
            }
        }
        raise
    intents, metadata = _with_optional_metadata(generation_result)
    rows = intents_to_rows(intents, request=request)
    category_hits = _batch_category_hits(
        rows,
        requested_platform_mode=request.requested_platform_mode,
        categories=tuple(batch_plan["categories"]),
    )
    weak_reasons = _weak_generation_batch_reasons(
        batch_plan=batch_plan,
        rows=rows,
        requested_platform_mode=request.requested_platform_mode,
    )
    return intents, {
        "name": batch_plan["name"],
        "categories": list(batch_plan["categories"]),
        "target_count": batch_plan["target_count"],
        "category_targets": dict(batch_plan["category_targets"]),
        "slot_plan": slot_plan_payload,
        "parsed_intent_count": len(intents),
        "category_hits": category_hits,
        "weak_reasons": weak_reasons,
        "metadata": metadata,
    }


def _supplementation_batch_plans(
    *,
    gap_slots: dict[str, int],
    missing_categories: list[str],
    category_plan: dict[str, int],
    slot_plan: list[SlotPlanItem],
    split_batch_names: set[str],
) -> list[dict[str, Any]]:
    active_plans: list[dict[str, Any]] = []
    for blueprint in _generation_batch_blueprints():
        base_plan = _build_batch_plan(
            name=str(blueprint["name"]),
            categories=tuple(blueprint["categories"]),
            split_groups=tuple(blueprint["split_groups"]),
            category_plan=category_plan,
            slot_plan=slot_plan,
        )
        if base_plan is None:
            continue
        if str(blueprint["name"]) in split_batch_names:
            active_plans.extend(
                _split_generation_batch_plans(
                    batch_plan=base_plan,
                    category_plan=category_plan,
                    slot_plan=slot_plan,
                )
            )
        else:
            active_plans.append(base_plan)

    batch_plans: list[dict[str, Any]] = []
    for plan in active_plans:
        relevant_gap_slots = {
            key: int(value)
            for key, value in gap_slots.items()
            if key != "_total" and str(key).split(":", 1)[0] in plan["categories"] and int(value) > 0
        }
        relevant_missing_categories = [category for category in missing_categories if category in plan["categories"]]
        if not relevant_gap_slots and not relevant_missing_categories:
            continue
        batch_plans.append(
            {
                **plan,
                "gap_slots": relevant_gap_slots,
                "missing_categories": relevant_missing_categories,
            }
        )

    batch_plans.sort(
        key=lambda plan: (
            -sum(plan["gap_slots"].values()),
            -len(plan["missing_categories"]),
            str(plan["name"]),
        )
    )
    return batch_plans


def _run_supplementation_batch(
    *,
    request: GenerationRequest,
    batch_plan: dict[str, Any],
    gap_slots: dict[str, int],
    missing_categories: list[str],
    surviving_intents: list[CanonicalIntent],
    interpretation_payload: dict[str, Any],
) -> tuple[list[CanonicalIntent], dict[str, Any]]:
    surviving_summary = [
        {
            "intent_id": intent.intent_id,
            "intent_text": intent.intent_text,
            "category": intent.category,
            "slot_type": intent.slot_type,
        }
        for intent in surviving_intents
        if intent.category in batch_plan["categories"]
    ]
    slot_plan_payload = _serialize_slot_plan(batch_plan["slot_plan"])
    try:
        supplementation_result = run_supplementation_pass(
            gap_slots,
            request=request,
            platform=request.requested_platform_mode,
            surviving_summary=surviving_summary,
            missing_categories=missing_categories,
            interpretation_payload=interpretation_payload,
            slot_plan=slot_plan_payload,
            batch_name=str(batch_plan["name"]),
            return_metadata=True,
        )
    except BedrockResponseParseError as exc:
        exc.debug_payload = {
            "generation": {
                "error": {
                    "stage": exc.stage,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "batch_name": batch_plan["name"],
                    "categories": list(batch_plan["categories"]),
                    "gap_slots": dict(gap_slots),
                    "missing_categories": list(missing_categories),
                    "slot_plan": slot_plan_payload,
                    "model_id": exc.model_id,
                    "metadata": dict(exc.metadata),
                    "response_text": exc.response_text,
                }
            }
        }
        raise
    intents, metadata = _with_optional_metadata(supplementation_result)
    rows = intents_to_rows(intents, request=request)
    category_hits = _batch_category_hits(
        rows,
        requested_platform_mode=request.requested_platform_mode,
        categories=tuple(batch_plan["categories"]),
    )
    return intents, {
        "name": batch_plan["name"],
        "categories": list(batch_plan["categories"]),
        "gap_slots": dict(gap_slots),
        "missing_categories": list(missing_categories),
        "parsed_intent_count": len(intents),
        "category_hits": category_hits,
        "metadata": metadata,
    }


def _with_optional_metadata(result: Any) -> tuple[Any, dict[str, Any]]:
    if (
        isinstance(result, tuple)
        and len(result) == 2
        and isinstance(result[1], dict)
    ):
        return result[0], result[1]
    return result, {}


def _pipeline_error_debug_payload(exc: Exception) -> dict[str, Any]:
    debug_payload = getattr(exc, "debug_payload", None)
    if isinstance(debug_payload, dict):
        return debug_payload
    if isinstance(exc, BedrockResponseParseError):
        return {
            "generation": {
                "error": {
                    "stage": exc.stage,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "model_id": exc.model_id,
                    "metadata": dict(exc.metadata),
                    "response_text": exc.response_text,
                }
            }
        }
    return {}


def _category_gap_report(
    intents: list[CanonicalIntent],
    *,
    category_plan: dict[str, int],
) -> dict[str, int]:
    counts = {category: 0 for category in POSITIVE_CATEGORIES}
    for intent in intents:
        if intent.category in counts:
            counts[intent.category] += 1

    gap_report: dict[str, int] = {}
    total_missing = 0
    for category in POSITIVE_CATEGORIES:
        target = max(1, int(category_plan.get(category, 0)))
        missing = max(0, target - counts.get(category, 0))
        if missing > 0:
            gap_report[category] = missing
            total_missing += missing
    gap_report["_total"] = total_missing
    return gap_report


def _platform_slot_gap_report(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: str,
    slot_plan: list[SlotPlanItem],
) -> dict[str, Any]:
    platforms = ["naver_sa", "google_sa"] if requested_platform_mode == "both" else [requested_platform_mode]
    per_platform: dict[str, dict[str, int]] = {platform: {} for platform in platforms}
    aggregate: dict[str, int] = {}
    by_category: dict[str, int] = {}
    total_missing = 0

    for platform in platforms:
        slot_counts: dict[str, int] = {}
        for row in rows:
            if platform == "naver_sa" and not row.naver_match:
                continue
            if platform == "google_sa" and not row.google_match:
                continue
            slot_type = str(row.slot_type or "").strip() or _default_slot_type(row.category)
            key = _slot_key(row.category, slot_type)
            slot_counts[key] = slot_counts.get(key, 0) + 1

        platform_gap: dict[str, int] = {}
        for slot in slot_plan:
            key = _slot_key(slot.category, slot.slot_type)
            missing = max(0, slot.target_count - slot_counts.get(key, 0))
            if missing <= 0:
                continue
            platform_gap[key] = missing
            aggregate[key] = max(aggregate.get(key, 0), missing)
            by_category[slot.category] = by_category.get(slot.category, 0) + missing
        total_missing += sum(platform_gap.values())
        per_platform[platform] = platform_gap

    return {
        "platforms": per_platform,
        "aggregate": aggregate,
        "by_category": by_category,
        "_total": total_missing,
    }


def _platform_category_gap_report(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: str,
    category_plan: dict[str, int] | None = None,
) -> dict[str, Any]:
    platforms = ["naver_sa", "google_sa"] if requested_platform_mode == "both" else [requested_platform_mode]
    per_platform: dict[str, dict[str, int]] = {platform: {} for platform in platforms}
    aggregate: dict[str, int] = {}
    total_missing = 0

    for platform in platforms:
        counts = {category: 0 for category in POSITIVE_CATEGORIES}
        negative_count = 0
        for row in rows:
            if platform == "naver_sa" and not row.naver_match:
                continue
            if platform == "google_sa" and not row.google_match:
                continue
            if row.category == NEGATIVE_CATEGORY:
                negative_count += 1
                continue
            if row.category in counts:
                counts[row.category] += 1

        platform_gap: dict[str, int] = {}
        for category in POSITIVE_CATEGORIES:
            target = 1
            missing = max(0, target - counts.get(category, 0))
            if missing > 0:
                platform_gap[category] = missing
                aggregate[category] = max(aggregate.get(category, 0), missing)
        if negative_count == 0:
            platform_gap[NEGATIVE_CATEGORY] = 1
            aggregate[NEGATIVE_CATEGORY] = max(aggregate.get(NEGATIVE_CATEGORY, 0), 1)
        total_missing += sum(platform_gap.values())
        per_platform[platform] = platform_gap

    return {
        "platforms": per_platform,
        "aggregate": aggregate,
        "_total": total_missing,
    }


def _supplementation_slot_targets(
    *,
    category_gap_report: dict[str, Any],
    slot_gap_report: dict[str, Any],
    slot_plan: list[SlotPlanItem],
    rows: list[KeywordRow],
    requested_platform_mode: str,
    positive_target: int,
) -> dict[str, int]:
    targets: dict[str, int] = {}
    missing_categories = {
        category
        for category, missing in (category_gap_report.get("aggregate") or {}).items()
        if category != NEGATIVE_CATEGORY and int(missing) > 0
    }
    category_slots: dict[str, list[SlotPlanItem]] = {}
    for slot in slot_plan:
        category_slots.setdefault(slot.category, []).append(slot)

    for category, missing in (category_gap_report.get("aggregate") or {}).items():
        if int(missing) <= 0:
            continue
        candidate_slots = category_slots.get(category) or []
        required_slot = next((slot for slot in candidate_slots if slot.required), None)
        selected = required_slot or (candidate_slots[0] if candidate_slots else None)
        slot_type = selected.slot_type if selected is not None else _default_slot_type(category)
        targets[_slot_key(category, slot_type)] = int(missing)

    for key, missing in (slot_gap_report.get("aggregate") or {}).items():
        if int(missing) <= 0:
            continue
        category = str(key).split(":", 1)[0]
        if category in missing_categories:
            continue
        targets.setdefault(key, 1)

    positive_shortfall = _aggregate_positive_count_shortfall(
        rows,
        requested_platform_mode=requested_platform_mode,
        positive_target=positive_target,
    )
    targeted_positive = sum(
        value
        for key, value in targets.items()
        if key != "_total" and str(key).split(":", 1)[0] != NEGATIVE_CATEGORY
    )
    remaining_positive_shortfall = max(0, positive_shortfall - targeted_positive)
    if remaining_positive_shortfall > 0:
        weighted_slots = [
            slot
            for slot in slot_plan
            if slot.category != NEGATIVE_CATEGORY and slot.required
        ]
        total_weight = sum(max(1, slot.target_count) for slot in weighted_slots)
        allocated = 0
        for slot in weighted_slots:
            key = _slot_key(slot.category, slot.slot_type)
            extra = max(1, int((remaining_positive_shortfall * max(1, slot.target_count)) / max(1, total_weight)))
            targets[key] = targets.get(key, 0) + extra
            allocated += extra
        overflow = allocated - remaining_positive_shortfall
        if overflow > 0:
            for slot in reversed(weighted_slots):
                key = _slot_key(slot.category, slot.slot_type)
                current = targets.get(key, 0)
                if current <= 1:
                    continue
                reduce_by = min(overflow, current - 1)
                targets[key] = current - reduce_by
                overflow -= reduce_by
                if overflow <= 0:
                    break

    if targets:
        targets["_total"] = sum(targets.values())
    return targets


def _aggregate_positive_count_shortfall(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: str,
    positive_target: int,
) -> int:
    platforms = ["naver_sa", "google_sa"] if requested_platform_mode == "both" else [requested_platform_mode]
    shortfalls: list[int] = []
    for platform in platforms:
        positive_count = 0
        for row in rows:
            if row.category == NEGATIVE_CATEGORY:
                continue
            if platform == "naver_sa" and not row.naver_match:
                continue
            if platform == "google_sa" and not row.google_match:
                continue
            positive_count += 1
        shortfalls.append(max(0, positive_target - positive_count))
    return max(shortfalls, default=0)


def _intent_debug_payload(intent: CanonicalIntent) -> dict[str, Any]:
    return {
        "intent_id": intent.intent_id,
        "category": intent.category,
        "slot_type": intent.slot_type,
        "intent_text": intent.intent_text,
        "reason": intent.reason,
        "evidence_tier": intent.evidence_tier,
        "shared_render": intent.shared_render.keyword if intent.shared_render else None,
        "naver_render": intent.naver_render.keyword if intent.naver_render else None,
        "google_render": intent.google_render.keyword if intent.google_render else None,
    }


def _row_debug_payload(row: KeywordRow) -> dict[str, Any]:
    return {
        "category": row.category,
        "slot_type": row.slot_type,
        "keyword": row.keyword,
        "naver_match": row.naver_match,
        "google_match": row.google_match,
        "reason": row.reason,
    }


def _dedup_report_payload(report: Any) -> dict[str, Any]:
    return {
        "platform": report.platform,
        "surviving_intents": [_intent_debug_payload(intent) for intent in report.surviving_keywords],
        "dropped_duplicates": list(report.dropped_duplicates),
        "dropped_low_quality": list(report.dropped_low_quality),
        "slot_gap_report": dict(report.slot_gap_report),
    }


def _dropped_row_payload(before_rows: list[KeywordRow], after_rows: list[KeywordRow]) -> list[dict[str, Any]]:
    surviving_keys = {
        (row.category, row.keyword, row.naver_match, row.google_match)
        for row in after_rows
    }
    dropped: list[dict[str, Any]] = []
    for row in before_rows:
        key = (row.category, row.keyword, row.naver_match, row.google_match)
        if key in surviving_keys:
            continue
        dropped.append(_row_debug_payload(row))
    return dropped


def _intent_lookup(
    intents: list[CanonicalIntent],
) -> dict[tuple[str, str], CanonicalIntent]:
    lookup: dict[tuple[str, str], CanonicalIntent] = {}
    for intent in intents:
        lookup.setdefault((intent.category, intent.intent_text), intent)
        if intent.shared_render is not None:
            lookup.setdefault((intent.category, intent.shared_render.keyword), intent)
        if intent.naver_render is not None:
            lookup.setdefault((intent.category, intent.naver_render.keyword), intent)
        if intent.google_render is not None:
            lookup.setdefault((intent.category, intent.google_render.keyword), intent)
    return lookup


def _slot_drop_entry(
    *,
    keyword: str,
    category: str,
    slot_type: str,
    drop_stage: str,
    drop_reason_code: str,
    drop_reason_detail: str,
) -> dict[str, str]:
    return {
        "keyword": keyword,
        "category": category,
        "slot_type": slot_type,
        "drop_stage": drop_stage,
        "drop_reason_code": drop_reason_code,
        "drop_reason_detail": drop_reason_detail,
    }


def _reason_code_from_policy_issue(issue: str) -> str:
    mapping = {
        "invalid_competitor": "invalid_competitor",
        "invalid_negative": "invalid_negative",
        "low_information": "dedup_low_quality",
    }
    return mapping.get(issue, issue)


def _slot_drop_report_from_dedup(
    *,
    intents: list[CanonicalIntent],
    dedup_report: Any,
) -> list[dict[str, str]]:
    if dedup_report is None:
        return []
    lookup = _intent_lookup(intents)
    dropped: list[dict[str, str]] = []
    for item in list(dedup_report.dropped_duplicates):
        keyword = str(item.get("intent_text") or "").strip()
        category = str(item.get("category") or "")
        matched = lookup.get((category, keyword)) if category else None
        if matched is None:
            matched = next((candidate for (candidate_category, candidate_keyword), candidate in lookup.items() if candidate_keyword == keyword), None)
        dropped.append(
            _slot_drop_entry(
                keyword=keyword,
                category=matched.category if matched is not None else category,
                slot_type=matched.slot_type if matched is not None else "",
                drop_stage="dedup_quality",
                drop_reason_code="semantic_duplicate",
                drop_reason_detail=str(item.get("reason") or "semantic duplicate"),
            )
        )
    for item in list(dedup_report.dropped_low_quality):
        keyword = str(item.get("intent_text") or "").strip()
        category = str(item.get("category") or "")
        matched = lookup.get((category, keyword)) if category else None
        if matched is None:
            matched = next((candidate for (candidate_category, candidate_keyword), candidate in lookup.items() if candidate_keyword == keyword), None)
        quality_score = str(item.get("quality_score") or "").strip()
        detail = str(item.get("reason") or item.get("quality_reason") or "low quality")
        dropped.append(
            _slot_drop_entry(
                keyword=keyword,
                category=matched.category if matched is not None else category,
                slot_type=matched.slot_type if matched is not None else "",
                drop_stage="dedup_quality",
                drop_reason_code="low_quality" if quality_score == "low" else "dedup_low_quality",
                drop_reason_detail=detail,
            )
        )
    return dropped


def _slot_drop_report_from_policy_rows(
    *,
    intents: list[CanonicalIntent],
    policy_drop_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    lookup = _intent_lookup(intents)
    dropped: list[dict[str, str]] = []
    for item in policy_drop_rows:
        keyword = str(item.get("keyword") or "").strip()
        category = str(item.get("category") or "").strip()
        issues = [
            str(issue).strip()
            for issue in str(item.get("issues") or "").split(",")
            if str(issue).strip()
        ]
        matched = lookup.get((category, keyword))
        slot_type = matched.slot_type if matched is not None else ""
        for issue in issues or ["policy_drop"]:
            dropped.append(
                _slot_drop_entry(
                    keyword=keyword,
                    category=category,
                    slot_type=slot_type,
                    drop_stage="policy_filter",
                    drop_reason_code=_reason_code_from_policy_issue(issue),
                    drop_reason_detail=issue,
                )
            )
    return dropped


def _build_slot_drop_report(
    *,
    all_intents: list[CanonicalIntent],
    dedup_report: Any | None,
    policy_drop_rows: list[dict[str, str]],
    surface_drop_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    report = _slot_drop_report_from_dedup(intents=all_intents, dedup_report=dedup_report)
    report.extend(_slot_drop_report_from_policy_rows(intents=all_intents, policy_drop_rows=policy_drop_rows))
    report.extend(surface_drop_rows)
    return report


def _fallback_pipeline(request: GenerationRequest) -> GenerationResult:
    """Deterministic fallback pipeline used when Bedrock is disabled (local testing)."""
    evidence_pack = request.evidence_pack
    target = request.max_keywords_per_platform
    quality_warning = bool(evidence_pack.get("quality_warning", False))
    feasible_positive_cap = _feasible_positive_cap(evidence_pack)

    initial_target = target
    if str(evidence_pack.get("sufficiency_state")) == "borderline":
        initial_target = max(0, min(target, feasible_positive_cap) - 4)

    intents, rows = _initial_generation(request, positive_target=initial_target)
    report = validate_keyword_rows(
        rows,
        requested_platform_mode=request.requested_platform_mode,
        quality_warning=quality_warning,
        evidence_pack=request.evidence_pack,
    )

    if report.status == "COMPLETED" and report_min_positive_count(report) >= target:
        return GenerationResult(
            status="COMPLETED",
            requested_platform_mode=request.requested_platform_mode,
            rows=rows,
            intents=intents,
            validation_report=report,
        )

    failure = empty_failure_result(
        request,
        failure_code=report.failure_code or "generation_count_shortfall",
        failure_detail=report.failure_detail or f"unable to reach target {target} without fallback top-up",
    )
    failure.rows = rows
    failure.intents = intents
    failure.validation_report = report
    return failure


def _hard_rule_pass(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: str,
) -> list[KeywordRow]:
    """Drop rows that violate hard compliance rules: banned terms and invalid match labels.

    Does NOT enforce count/category floors ??those are the final validate_keyword_rows() gate.
    """
    banned_terms = (*PROMO_BANNED_TERMS, *URGENCY_BANNED_TERMS)
    platforms = ["naver_sa", "google_sa"] if requested_platform_mode == "both" else [requested_platform_mode]

    clean: list[KeywordRow] = []
    for row in rows:
        haystack = " ".join(part for part in (row.keyword, row.reason) if part)
        if any(term in haystack for term in banned_terms):
            continue

        rejected = False
        if "naver_sa" in platforms and row.naver_match and row.naver_match not in NAVER_ALLOWED_MATCHES:
            rejected = True
        if "google_sa" in platforms and row.google_match and row.google_match not in GOOGLE_ALLOWED_MATCHES:
            rejected = True
        if not rejected:
            clean.append(row)

    return clean


def empty_failure_result(
    request: GenerationRequest,
    *,
    failure_code: str,
    failure_detail: str,
) -> GenerationResult:
    return GenerationResult(
        status="FAILED_GENERATION",
        requested_platform_mode=request.requested_platform_mode,
        rows=[],
        supplementation_attempts=0,
        validation_report=ValidationReport(
            status="FAILED_GENERATION",
            requested_platform_mode=request.requested_platform_mode,
            failure_code=failure_code,
            failure_detail=failure_detail,
            quality_warning=bool(request.evidence_pack.get("quality_warning", False)),
        ),
    )


def report_min_positive_count(report: ValidationReport) -> int:
    if not report.positive_keyword_counts:
        return 0
    return min(report.positive_keyword_counts.values())


def _feasible_positive_cap(evidence_pack: dict[str, Any]) -> int:
    if str(evidence_pack.get("sufficiency_state")) == "borderline":
        return 100
    return 140


def _initial_generation(
    request: GenerationRequest,
    *,
    positive_target: int,
) -> tuple[list[CanonicalIntent], list[KeywordRow]]:
    if should_use_bedrock():
        try:
            intents = generate_intents_via_bedrock(request, positive_target=positive_target)
            if intents:
                rows = intents_to_rows(intents, request=request)
                rows, _ = filter_keyword_rows(rows, evidence_pack=request.evidence_pack)
                rows = _surface_cleanup_rows(rows, evidence_pack=request.evidence_pack)
                return _rows_to_intents(rows, requested_platform_mode=request.requested_platform_mode), rows
        except Exception:
            pass

    intents = _build_intents(
        request.evidence_pack,
        requested_platform_mode=request.requested_platform_mode,
        positive_target=positive_target,
    )
    rows = intents_to_rows(intents, request=request)
    rows, _ = filter_keyword_rows(rows, evidence_pack=request.evidence_pack)
    rows = _surface_cleanup_rows(rows, evidence_pack=request.evidence_pack)
    return _rows_to_intents(rows, requested_platform_mode=request.requested_platform_mode), rows


def _build_rows(
    evidence_pack: dict[str, Any],
    *,
    requested_platform_mode: str,
    positive_target: int,
) -> list[KeywordRow]:
    product_name = _canonical_product_name(evidence_pack)
    raw_url = str(evidence_pack.get("raw_url") or evidence_pack.get("canonical_url") or "")
    quality_warning = bool(evidence_pack.get("quality_warning", False))
    interpretation = _build_product_interpretation(evidence_pack)
    phrase_bank = _build_refined_phrase_bank(evidence_pack, interpretation=interpretation)
    category_plan = _scaled_category_plan(positive_target, phrase_bank=phrase_bank, interpretation=interpretation)
    selected = _select_phrase_bank_candidates(
        phrase_bank,
        category_plan=category_plan,
        interpretation=interpretation,
    )
    rows: list[KeywordRow] = []

    for category in POSITIVE_CATEGORIES:
        for candidate in selected.get(category, []):
            naver_match, google_match = _match_labels(category, candidate["keyword"], requested_platform_mode)
            slot_type = str(candidate.get("slot_type") or _infer_slot_type_for_keyword(category, candidate["keyword"], interpretation))
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=category,
                    keyword=candidate["keyword"],
                    slot_type=slot_type,
                    naver_match=naver_match,
                    google_match=google_match,
                    reason=candidate["reason"],
                    quality_warning=quality_warning,
                    evidence_tier=candidate["evidence_tier"],
                )
            )

    for negative_term in _negative_terms(evidence_pack)[:10]:
        naver_match, google_match = _match_labels(NEGATIVE_CATEGORY, negative_term, requested_platform_mode)
        rows.append(
            KeywordRow(
                url=raw_url,
                product_name=product_name,
                category=NEGATIVE_CATEGORY,
                keyword=negative_term,
                slot_type="negative_exclusion",
                naver_match=naver_match,
                google_match=google_match,
                reason=f"{product_name}에 무관한 전환 의도가 낮은 제외 키워드",
                quality_warning=quality_warning,
                evidence_tier="inferred",
            )
        )

    return rows


def _build_intents(
    evidence_pack: dict[str, Any],
    *,
    requested_platform_mode: str,
    positive_target: int,
) -> list[CanonicalIntent]:
    product_name = _canonical_product_name(evidence_pack)
    interpretation = _build_product_interpretation(evidence_pack)
    phrase_bank = _build_refined_phrase_bank(evidence_pack, interpretation=interpretation)
    category_plan = _scaled_category_plan(positive_target, phrase_bank=phrase_bank, interpretation=interpretation)
    selected = _select_phrase_bank_candidates(
        phrase_bank,
        category_plan=category_plan,
        interpretation=interpretation,
    )
    intents: list[CanonicalIntent] = []

    for category in POSITIVE_CATEGORIES:
        for candidate in selected.get(category, []):
            intents.append(
                _intent_from_candidate(
                    category=category,
                    keyword=candidate["keyword"],
                    slot_type=str(candidate.get("slot_type") or _infer_slot_type_for_keyword(category, candidate["keyword"], interpretation)),
                    reason=candidate["reason"],
                    evidence_tier=candidate["evidence_tier"],
                    requested_platform_mode=requested_platform_mode,
                )
            )

    for negative_term in _negative_terms(evidence_pack)[:10]:
        intents.append(
            _intent_from_candidate(
                category=NEGATIVE_CATEGORY,
                keyword=negative_term,
                slot_type="negative_exclusion",
                reason=f"{product_name}에 무관한 전환 의도가 낮은 제외 키워드",
                evidence_tier="inferred",
                requested_platform_mode=requested_platform_mode,
            )
        )

    return intents


def _intent_from_candidate(
    *,
    category: str,
    keyword: str,
    slot_type: str,
    reason: str,
    evidence_tier: str,
    requested_platform_mode: str,
) -> CanonicalIntent:
    naver_match, google_match = _match_labels(category, keyword, "both")
    allowed_platforms: list[str] = []
    naver_render = None
    google_render = None

    if requested_platform_mode in {"naver_sa", "both"} and naver_match:
        allowed_platforms.append("naver_sa")
        naver_render = PlatformRender(keyword=keyword, match_label=naver_match, admitted=True)
    if requested_platform_mode in {"google_sa", "both"} and google_match:
        allowed_platforms.append("google_sa")
        google_render = PlatformRender(keyword=keyword, match_label=google_match, admitted=True)

    return CanonicalIntent(
        category=category,
        slot_type=slot_type,
        intent_text=keyword,
        intent_id=f"{category}:{keyword}",
        reason=reason,
        evidence_tier=evidence_tier,
        allowed_platforms=allowed_platforms,
        shared_render=SharedRender(keyword=keyword, admitted=True),
        naver_render=naver_render,
        google_render=google_render,
    )


def _rows_to_intents(rows: list[KeywordRow], *, requested_platform_mode: str) -> list[CanonicalIntent]:
    return [
        _intent_from_candidate(
            category=row.category,
            keyword=row.keyword,
            slot_type=str(row.slot_type or _default_slot_type(row.category)),
            reason=row.reason,
            evidence_tier=row.evidence_tier or "inferred",
            requested_platform_mode=requested_platform_mode,
        )
        for row in rows
    ]


def _build_phrase_bank(evidence_pack: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    legacy_bank = _build_refined_phrase_bank(evidence_pack)
    return {
        category: [dict(entry) for entry in entries]
        for category, entries in legacy_bank.items()
    }


def _pad_phrase_bank(
    bank: dict[str, list[dict[str, str]]],
    *,
    positive_category_targets: dict[str, int],
    product_name: str,
    category_value: str,
) -> None:
    return None


def _scaled_category_plan(
    positive_target: int,
    *,
    phrase_bank: dict[str, list[dict[str, str]]],
    interpretation: ProductInterpretation,
) -> dict[str, int]:
    if positive_target <= 0:
        return {category: 0 for category in POSITIVE_CATEGORIES}

    available = {
        category: len([entry for entry in phrase_bank.get(category, []) if str(entry.get("keyword") or "").strip()])
        for category in POSITIVE_CATEGORIES
    }
    strengths = _category_strengths(interpretation)
    active = [category for category in POSITIVE_CATEGORIES if available.get(category, 0) > 0]
    if not active:
        return {category: 0 for category in POSITIVE_CATEGORIES}

    plan = {category: 0 for category in POSITIVE_CATEGORIES}
    if positive_target < len(active):
        ranked = sorted(active, key=lambda category: (-strengths.get(category, 1.0), -POSITIVE_CATEGORY_TARGETS[category], category))
        for category in ranked[:positive_target]:
            plan[category] = 1
        return plan

    for category in active:
        plan[category] = 1
    remaining = positive_target - len(active)
    while remaining > 0:
        candidates = [category for category in active if plan[category] < available[category]]
        if not candidates:
            break
        chosen = max(
            candidates,
            key=lambda category: (
                (POSITIVE_CATEGORY_TARGETS[category] * strengths.get(category, 1.0)) / (plan[category] + 0.5),
                available[category] - plan[category],
                POSITIVE_CATEGORY_TARGETS[category],
            ),
        )
        plan[chosen] += 1
        remaining -= 1
    return plan


def _category_strengths(interpretation: ProductInterpretation) -> dict[str, float]:
    typed_attribute_count = len(
        _unique_texts(
            [
                *interpretation.specs,
                *interpretation.ingredients,
                *interpretation.technology,
                *interpretation.form_factors,
            ]
        )
    )
    seasonal_signal = any(token in " ".join(interpretation.usage_context) for token in ("야간", "수면", "취침", "밤"))
    return {
        "brand": 1.05 if interpretation.brand else 0.75,
        "generic_category": 1.15 + min(0.25, 0.05 * len(interpretation.secondary_categories)),
        "feature_attribute": 1.1 + min(0.45, 0.06 * typed_attribute_count),
        "competitor_comparison": 0.2 + min(0.5, 0.08 * len(interpretation.commerce_facts.get("competitor_brand_hints") or [])),
        "purchase_intent": 0.55 + (0.15 if interpretation.commerce_facts.get("price") else 0.0),
        "long_tail": 1.15 + min(0.45, 0.04 * sum(len(values) for values in (interpretation.audience, interpretation.benefits, interpretation.concerns, interpretation.usage_context))),
        "benefit_price": 0.85 + min(0.35, 0.05 * len(interpretation.benefits)) + (0.15 if interpretation.commerce_facts.get("price") else 0.0),
        "season_event": 0.8 + (0.25 if seasonal_signal else 0.0),
        "problem_solution": 0.8 + min(0.35, 0.07 * len(interpretation.concerns)) + min(0.15, 0.03 * len(interpretation.audience)),
    }


def _candidate_dicts(
    keywords: list[str],
    *,
    reason: str,
    evidence_tier: str,
    slot_type: str | None = None,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for keyword in keywords:
        entry = {"keyword": keyword, "reason": reason, "evidence_tier": evidence_tier}
        if slot_type:
            entry["slot_type"] = slot_type
        entries.append(entry)
    return entries


def _match_labels(category: str, keyword: str, requested_platform_mode: str) -> tuple[str, str]:
    if category == NEGATIVE_CATEGORY:
        if requested_platform_mode == "naver_sa":
            return "제외키워드", ""
        if requested_platform_mode == "google_sa":
            return "", "negative"
        return "제외키워드", "negative"

    if category in {"brand", "purchase_intent"}:
        naver_match = "완전일치"
    else:
        naver_match = "확장소재"

    if category == "brand":
        google_match = "exact"
    elif category in {"long_tail", "purchase_intent", "problem_solution"}:
        google_match = "phrase"
    else:
        google_match = "broad"

    if requested_platform_mode == "naver_sa":
        return naver_match, ""
    if requested_platform_mode == "google_sa":
        return "", google_match
    return naver_match, google_match


def _negative_terms(evidence_pack: dict[str, Any]) -> list[str]:
    taxonomy_backed = taxonomy_terms("negative_seed", evidence_pack)
    if taxonomy_backed:
        return taxonomy_backed
    product_name = _canonical_product_name(evidence_pack)
    return [f"{product_name} {seed}" if index < 4 else seed for index, seed in enumerate(NEGATIVE_KEYWORD_SEEDS)]


def _first_fact_value(facts: list[dict[str, Any]], fact_type: str) -> str | None:
    for fact in facts:
        if fact.get("type") == fact_type:
            return str(fact.get("normalized_value") or fact.get("value") or "").strip()
    return None


def _fact_values_by_tags(facts: list[dict[str, Any]], tags: set[str]) -> list[str]:
    values: list[str] = []
    for fact in facts:
        if tags.intersection(set(fact.get("admissibility_tags", []))):
            values.append(str(fact.get("normalized_value") or fact.get("value") or "").strip())
    return _unique_texts(values)


def _fact_values_by_types(facts: list[dict[str, Any]], types: set[str]) -> list[str]:
    values = [
        str(fact.get("normalized_value") or fact.get("value") or "").strip()
        for fact in facts
        if fact.get("type") in types
    ]
    return _unique_texts(values)


def _infer_category_value(product_name: str) -> str:
    return product_name


def _is_placeholder_category_value(value: str) -> bool:
    lowered = " ".join(str(value or "").split()).strip().casefold()
    return lowered in {"제품", "상품", "product", "products", "item", "items", "goods"}


def _is_broad_category_value(value: str) -> bool:
    lowered = " ".join(str(value or "").split()).strip().casefold()
    if lowered in {"스킨케어", "화장품", "코스메틱", "제품", "상품", "general", "product", "products"}:
        return True
    return _category_head(lowered) in {"스킨케어", "화장품", "코스메틱", "제품", "상품"}


def _resolved_category_value(
    *,
    raw_category: str,
    product_name: str,
    short_name: str,
    category_terms: list[str],
    evidence_texts: list[str] | None = None,
) -> str:
    cleaned_raw = " ".join(str(raw_category or "").split()).strip()
    preferred_term = _preferred_category_term(category_terms, evidence_texts=evidence_texts or [])
    if (
        cleaned_raw
        and cleaned_raw != product_name
        and not _is_placeholder_category_value(cleaned_raw)
        and not _is_broad_category_value(cleaned_raw)
    ):
        return cleaned_raw
    if preferred_term:
        return preferred_term
    if cleaned_raw and cleaned_raw != product_name and not _is_placeholder_category_value(cleaned_raw):
        return cleaned_raw
    for term in category_terms:
        cleaned_term = " ".join(str(term or "").split()).strip()
        if cleaned_term and cleaned_term != product_name and not _is_placeholder_category_value(cleaned_term):
            return cleaned_term
    if short_name and short_name != product_name and not _is_placeholder_category_value(short_name):
        return short_name
    return product_name


def _preferred_category_term(category_terms: list[str], *, evidence_texts: list[str]) -> str:
    joined = " ".join(text for text in evidence_texts if text).casefold()
    best_term = ""
    best_score = -1
    for term in category_terms:
        cleaned = " ".join(str(term or "").split()).strip()
        if not cleaned or _is_placeholder_category_value(cleaned):
            continue
        score = 0
        head = _category_head(cleaned)
        lowered = cleaned.casefold()
        if not _is_broad_category_value(cleaned):
            score += 3
        if " " in cleaned:
            score += 1
        if lowered in joined:
            score += 5
        elif head.casefold() in joined:
            score += 2
        if score > best_score:
            best_term = cleaned
            best_score = score
    return best_term


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _combinations(product_name: str, values: list[str], *, suffixes: tuple[str, ...]) -> list[str]:
    phrases: list[str] = []
    for value in values:
        phrases.extend(
            [
                f"{product_name} {value}",
                f"{product_name} {value} 異붿쿇",
                f"{product_name} {value} ?뺣낫",
            ]
        )
        for suffix in suffixes:
            phrases.append(f"{product_name} {value} {suffix}")
    return _unique_texts(phrases)


def _long_tail_phrases(
    product_name: str,
    category_value: str,
    attributes: list[str],
    use_cases: list[str],
    concerns: list[str],
) -> list[str]:
    return _long_tail_phrases_refined(
        product_name,
        category_value,
        audience=[],
        benefits=[],
        concerns=concerns,
        usage_context=use_cases,
        ingredients=attributes,
        form_factors=[],
        specs=[],
    )


def _benefit_price_phrases(
    product_name: str,
    category_value: str,
    attributes: list[str],
    price: str | None,
    price_allowed: bool,
) -> list[str]:
    return _benefit_price_phrases_refined(
        product_name,
        category_value,
        benefits=[],
        ingredients=attributes,
        price_present=bool(price),
        price_comparison_allowed=False,
        value_terms=[],
    )


def _problem_phrases(
    product_name: str,
    category_value: str,
    concerns: list[str],
    attributes: list[str],
) -> list[str]:
    return _problem_phrases_refined(
        product_name,
        category_value,
        concerns=concerns,
        benefits=[],
        audience=[],
        usage_context=[],
    )


def _pad_phrase_bank(
    bank: dict[str, list[dict[str, str]]],
    *,
    positive_category_targets: dict[str, int],
    product_name: str,
    category_value: str,
) -> None:
    return None


def _build_refined_phrase_bank(
    evidence_pack: dict[str, Any],
    *,
    interpretation: ProductInterpretation | None = None,
) -> dict[str, list[dict[str, str]]]:
    facts = list(evidence_pack.get("facts", []))
    page_class = str(evidence_pack.get("page_class") or "")
    interpretation = interpretation or _build_product_interpretation(evidence_pack)
    product_name = interpretation.product_name
    brand = interpretation.brand
    brand_aliases = _brand_aliases(product_name, brand)
    short_name = _short_product_name(product_name, brand)
    feature_head = short_name if page_class in SUPPORT_PAGE_CLASSES else product_name
    category_value = interpretation.canonical_category
    category_terms = [category_value, *interpretation.secondary_categories]
    typed_attributes = [
        *interpretation.specs,
        *interpretation.ingredients,
        *interpretation.technology,
        *interpretation.form_factors,
    ]
    problem_terms = _unique_texts(interpretation.concerns)
    price_present = bool(str(interpretation.commerce_facts.get("price") or "").strip())
    price_comparison_allowed = bool(interpretation.commerce_facts.get("price_comparison_allowed"))
    value_terms = list(interpretation.commerce_facts.get("value_terms") or [])
    competitor_brands = list(interpretation.commerce_facts.get("competitor_brand_hints") or [])

    brand_terms = []
    if brand:
        brand_terms.extend(
            [
                brand,
                f"{brand} {category_value}",
                *[f"{brand} {term}" for term in interpretation.secondary_categories[:3]],
                *[f"{alias} {category_value}" for alias in brand_aliases[:2]],
                *[f"{alias} {term}" for alias in brand_aliases[:2] for term in interpretation.secondary_categories[:3]],
            ]
        )
    if not brand_terms:
        brand_terms.extend([product_name, short_name])

    generic_category_keywords = _unique_texts(
        [
            category_value,
            *interpretation.secondary_categories,
            *_category_aliases(category_value),
                    *([f"{brand} {category_value}"] if brand else []),
                    *([f"{short_name} {category_value}"] if short_name not in {category_value, product_name} else []),
        ]
    )

    bank: dict[str, list[dict[str, str]]] = {
        "brand": _candidate_dicts(
            _unique_texts(brand_terms),
            reason=f"{(brand or product_name)} 제품명 직접 증거 기반",
            evidence_tier="direct",
            slot_type="product_name",
        ),
        "generic_category": _candidate_dicts(
            generic_category_keywords,
            reason=f"{category_value} 카테고리 근거 기반",
            evidence_tier="inferred",
            slot_type="generic_type_phrase",
        ),
        "feature_attribute": _candidate_dicts(
            _attribute_phrases_refined(
                feature_head,
                specs=interpretation.specs,
                ingredients=interpretation.ingredients,
                technology=interpretation.technology,
                form_factors=interpretation.form_factors,
                benefits=interpretation.benefits,
            ),
            reason=f"{feature_head} 속성 및 스펙 기반",
            evidence_tier="direct",
            slot_type="spec",
        ),
        "competitor_comparison": _candidate_dicts(
            _comparison_phrases_refined(
                canonical_category=category_value,
                secondary_categories=interpretation.secondary_categories,
                competitor_brands=competitor_brands,
            ),
            reason=f"{category_value} 동일 제품군 경쟁 브랜드 탐색",
            evidence_tier="weak",
            slot_type="competitor_brand_type",
        ),
        "purchase_intent": _candidate_dicts(
            _purchase_intent_phrases(
                product_name=product_name,
                short_name=short_name,
                brand=brand,
                category_value=category_value,
            ),
            reason=f"{product_name} 제품명 및 브랜드 탐색 의도",
            evidence_tier="derived",
            slot_type="navigational_alias",
        ),
        "long_tail": _candidate_dicts(
            _long_tail_phrases_refined(
                feature_head,
                category_value,
                audience=interpretation.audience,
                benefits=interpretation.benefits,
                concerns=problem_terms,
                usage_context=interpretation.usage_context,
                ingredients=interpretation.ingredients,
                form_factors=interpretation.form_factors,
                specs=interpretation.specs,
            ),
            reason=f"{feature_head} 조합 확장",
            evidence_tier="derived",
            slot_type="use_case_phrase",
        ),
        "benefit_price": _candidate_dicts(
            _benefit_price_phrases_refined(
                feature_head,
                category_value,
                benefits=interpretation.benefits,
                ingredients=interpretation.ingredients,
                price_present=price_present,
                price_comparison_allowed=price_comparison_allowed,
                value_terms=value_terms,
            ),
            reason=f"{feature_head} 직접 근거 기반 효익 및 가격 탐색",
            evidence_tier="direct" if (price_present or value_terms) else "derived",
            slot_type="product_price",
        ),
        "season_event": _candidate_dicts(
            _seasonal_context_phrases(category_value, interpretation=interpretation),
            reason=f"{feature_head} 시즌 및 상황 탐색",
            evidence_tier="inferred",
            slot_type="seasonal_context",
        ),
        "problem_solution": _candidate_dicts(
            _problem_phrases_refined(
                feature_head,
                category_value,
                concerns=problem_terms,
                benefits=interpretation.benefits,
                audience=interpretation.audience,
                usage_context=interpretation.usage_context,
            ),
            reason=f"{feature_head} 문제 해결 및 효익 탐색",
            evidence_tier="weak" if bool(evidence_pack.get("weak_backfill_used")) else "inferred",
            slot_type="problem_noun_phrase",
        ),
    }

    _pad_refined_phrase_bank(
        bank,
        positive_category_targets=POSITIVE_CATEGORY_TARGETS,
        product_name=product_name,
        short_name=short_name,
        brand=brand,
        category_value=category_value,
        category_terms=category_terms,
        interpretation=interpretation,
    )

    if bool(evidence_pack.get("weak_backfill_used")) and "problem_solution" in bank:
        weak_budget = 20
        weak_assigned = 0
        for entry in bank["problem_solution"]:
            if weak_assigned >= weak_budget:
                entry["evidence_tier"] = "inferred"
            else:
                entry["evidence_tier"] = "weak"
                weak_assigned += 1

    return {category: _dedupe_candidate_dicts(entries) for category, entries in bank.items()}


def _fact_values_for_generation(
    facts: list[dict[str, Any]],
    *,
    types: set[str],
    tags: set[str],
) -> list[str]:
    values = _fact_values_by_types(facts, types) + _fact_values_by_tags(facts, tags)
    return _unique_texts(values)


def _direct_evidence_texts(facts: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for fact in facts:
        if str(fact.get("evidence_tier") or "").strip().lower() != "direct":
            continue
        for field in ("normalized_value", "value"):
            value = " ".join(str(fact.get(field) or "").split()).strip()
            if value:
                texts.append(value)
    return _unique_texts(texts)


def _text_mentions_any(texts: list[str], needle: str) -> bool:
    lowered = needle.casefold()
    return any(lowered in text.casefold() for text in texts)


def _direct_value_terms(texts: list[str]) -> list[str]:
    return _unique_texts([term for term in DIRECT_VALUE_SIGNAL_TERMS if _text_mentions_any(texts, term)])


def _direct_comparison_terms(texts: list[str], *, taxonomy_candidates: list[str]) -> list[str]:
    matched: list[str] = []
    for term in taxonomy_candidates:
        if "가격" in term:
            continue
        if _text_mentions_any(texts, term):
            matched.append(term)
    return _unique_texts(matched)


def _variant_measurements(specs: list[str]) -> list[str]:
    values: list[str] = []
    pattern = r"\d+(?:\.\d+)?\s?(?:ml|g|kg|oz|inch|in|gb|tb|mah|hz|w|형)"
    for spec in specs:
        values.extend(re.findall(pattern, spec, flags=re.IGNORECASE))
    return _unique_texts(values)


def _build_product_interpretation(evidence_pack: dict[str, Any]) -> ProductInterpretation:
    facts = list(evidence_pack.get("facts", []))
    page_class = str(evidence_pack.get("page_class") or "")
    product_name = _canonical_product_name(evidence_pack)
    brand = resolved_policy_brand(evidence_pack)
    short_name = _short_product_name(product_name, brand)
    category_terms = generic_category_terms(evidence_pack)
    direct_texts = _direct_evidence_texts(facts)
    raw_category = _first_fact_value(facts, "product_category") or _infer_category_value(product_name)
    canonical_category = _resolved_category_value(
        raw_category=raw_category,
        product_name=product_name,
        short_name=short_name,
        category_terms=category_terms,
        evidence_texts=[product_name, short_name, *direct_texts],
    )

    benefits = _fact_values_for_generation(
        facts,
        types=BENEFIT_FACT_TYPES,
        tags={"benefit", "social_proof"},
    )
    concerns = _fact_values_for_generation(
        facts,
        types=CONCERN_FACT_TYPES,
        tags={"problem_solution"},
    )
    audience = _audience_facet_values(facts)
    usage_context = _usage_context_values(facts)
    ingredients, technology, form_factors, specs = _typed_attribute_facets(facts)
    price = _first_fact_value(facts, "price")
    price_allowed = page_class not in SUPPORT_PAGE_CLASSES and str(evidence_pack.get("sellability_state")) == "sellable"
    value_terms = _direct_value_terms(direct_texts)
    measurement_terms = _variant_measurements(specs)
    variant_comparison_allowed = len(measurement_terms) >= 2
    competitor_brand_hints = competitor_brand_terms(evidence_pack)
    grounded_event_terms = _grounded_event_terms(direct_texts)
    secondary_categories = _secondary_category_terms(
        canonical_category,
        category_terms=category_terms,
        benefits=benefits,
        usage_context=usage_context,
    )
    generic_type_phrases = _generic_type_phrases(
        canonical_category,
        secondary_categories=secondary_categories,
        product_name=product_name,
    )
    navigational_aliases = _navigational_aliases(
        product_name=product_name,
        brand=brand,
        short_name=short_name,
        generic_type_phrases=generic_type_phrases,
    )
    problem_noun_phrases = _problem_noun_phrase_values(
        canonical_category,
        concerns=concerns,
    )
    price_band_candidates = _price_band_candidates(
        price=price,
        generic_type_phrases=generic_type_phrases,
        price_allowed=price_allowed,
    )
    price_comparison_allowed = price_allowed and (
        _text_mentions_any(direct_texts, "가격 비교")
        or _text_mentions_any(direct_texts, "price comparison")
        or variant_comparison_allowed
    )

    return ProductInterpretation(
        product_name=product_name,
        brand=brand,
        canonical_category=canonical_category,
        secondary_categories=secondary_categories,
        generic_type_phrases=generic_type_phrases,
        navigational_aliases=navigational_aliases,
        form_factors=form_factors,
        audience=audience,
        benefits=benefits,
        concerns=concerns,
        problem_noun_phrases=problem_noun_phrases,
        usage_context=usage_context,
        ingredients=ingredients,
        technology=technology,
        specs=specs,
        grounded_event_terms=grounded_event_terms,
        price_band_candidates=price_band_candidates,
        commerce_facts={
            "price": price,
            "price_allowed": price_allowed,
            "price_comparison_allowed": price_comparison_allowed,
            "variant_comparison_allowed": variant_comparison_allowed,
            "competitor_brand_hints": competitor_brand_hints,
            "value_terms": value_terms,
            "measurement_terms": measurement_terms,
            "page_class": page_class,
            "direct_texts": direct_texts,
            "grounded_event_terms": grounded_event_terms,
            "price_band_candidates": price_band_candidates,
            "navigational_aliases": navigational_aliases,
            "problem_noun_phrases": problem_noun_phrases,
            "generic_type_phrases": generic_type_phrases,
        },
    )


def _grounded_event_terms(texts: list[str]) -> list[str]:
    grounded: list[str] = []
    corpus = " ".join(texts).casefold()
    for term in PROMO_EVENT_TOKENS:
        if term.casefold() in corpus:
            grounded.append(term)
    return _unique_texts(grounded)


def _generic_type_phrases(
    canonical_category: str,
    *,
    secondary_categories: list[str],
    product_name: str,
) -> list[str]:
    return _unique_texts(
        [
            canonical_category,
            *secondary_categories,
            *_category_aliases(canonical_category),
            *[term for term in secondary_categories if term != product_name],
        ]
    )


def _navigational_aliases(
    *,
    product_name: str,
    brand: str,
    short_name: str,
    generic_type_phrases: list[str],
) -> list[str]:
    aliases = [product_name]
    if short_name and short_name not in aliases:
        aliases.append(short_name)
    if brand and brand not in aliases:
        aliases.append(brand)
    if brand and short_name and short_name != product_name:
        aliases.append(f"{brand} {short_name}")
    aliases.extend(_short_model_aliases(product_name))
    aliases.extend([f"{brand} {term}" for term in generic_type_phrases[:2] if brand])
    return _unique_texts(aliases)


def _short_model_aliases(product_name: str) -> list[str]:
    tokens = product_name.split()
    aliases: list[str] = []
    if len(tokens) < 2:
        return aliases
    tail = tokens[-1]
    if re.fullmatch(r"[0-9A-Za-z-]{1,6}", tail):
        aliases.append(f"{' '.join(tokens[:-1])} {tail}".strip())
    return _unique_texts(aliases)


def _problem_noun_phrase_values(
    canonical_category: str,
    *,
    concerns: list[str],
) -> list[str]:
    phrases = [f"{concern} {canonical_category}" for concern in concerns]
    return _unique_texts(phrases)


def _price_band_candidates(
    *,
    price: str | None,
    generic_type_phrases: list[str],
    price_allowed: bool,
) -> list[str]:
    if not price_allowed or not price:
        return []
    bands = _price_bands_from_value(price)
    if not bands:
        return []
    return _unique_texts(
        [f"{band} {type_phrase}" for band in bands for type_phrase in generic_type_phrases[:2]]
    )


def _price_bands_from_value(price: str) -> list[str]:
    digits = re.sub(r"[^0-9]", "", str(price))
    if not digits:
        return []
    numeric = int(digits)
    if numeric <= 0:
        return []
    ten_thousand = numeric // 10000
    if ten_thousand <= 0:
        return []
    lower_band = max(1, ten_thousand) * 10000
    upper_band = lower_band + 90000
    bands = [f"{ten_thousand}만원대"]
    if upper_band > lower_band:
        bands.append(f"{lower_band:,}원대")
    return _unique_texts(bands)


def _brand_aliases(product_name: str, brand: str) -> list[str]:
    aliases: list[str] = []
    first_token = product_name.split()[0] if product_name.split() else ""
    if first_token and first_token.casefold() != brand.casefold():
        aliases.append(first_token)
    return _unique_texts(aliases)


def _typed_attribute_facets(facts: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str], list[str]]:
    ingredients: list[str] = []
    technology: list[str] = []
    form_factors: list[str] = []
    specs: list[str] = []

    for fact in facts:
        value = str(fact.get("normalized_value") or fact.get("value") or "").strip()
        if not value:
            continue
        fact_type = str(fact.get("type") or "")
        tags = {str(tag) for tag in fact.get("admissibility_tags", [])}
        if fact_type in {"volume", "variant"} or _is_measurementish_term(value):
            specs.append(value)
        elif fact_type == "texture" or any(token in value for token in ("타입", "제형", "텍스처", "질감")):
            form_factors.append(value)
        elif "brand_technology" in tags:
            technology.append(value)
        elif fact_type == "key_ingredient":
            ingredients.append(value)

    return (
        _unique_texts(ingredients),
        _unique_texts(technology),
        _unique_texts(form_factors),
        _unique_texts(specs),
    )


def _audience_facet_values(facts: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for fact in facts:
        fact_type = str(fact.get("type") or "")
        tags = {str(tag) for tag in fact.get("admissibility_tags", [])}
        if fact_type not in {"skin_type", "audience"} and "audience" not in tags:
            continue
        value = " ".join(str(fact.get("normalized_value") or fact.get("value") or "").split()).strip()
        if not value:
            continue
        values.append(value)
    return _unique_texts(values)


def _usage_context_values(facts: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for fact in facts:
        fact_type = str(fact.get("type") or "")
        tags = {str(tag) for tag in fact.get("admissibility_tags", [])}
        if fact_type not in {"usage", "use_case"} and "use_case" not in tags:
            continue
        if "audience" in tags:
            continue
        value = str(fact.get("normalized_value") or fact.get("value") or "").strip()
        if not value:
            continue
        values.extend(_normalize_usage_context(value))
    return _unique_texts(values)


def _normalize_usage_context(value: str) -> list[str]:
    cleaned = " ".join(value.split()).strip()
    return [cleaned] if cleaned else []


def _secondary_category_terms(
    canonical_category: str,
    *,
    category_terms: list[str],
    benefits: list[str],
    usage_context: list[str],
) -> list[str]:
    del benefits
    del usage_context
    secondary = [term for term in category_terms if _is_category_faithful(term, canonical_category)]
    return [term for term in _unique_texts(secondary) if term != canonical_category]


def _category_head(category: str) -> str:
    parts = category.split()
    return parts[-1] if parts else category


def _category_aliases(category: str) -> list[str]:
    del category
    return []


def _is_category_faithful(term: str, canonical_category: str) -> bool:
    return _category_head(term) == _category_head(canonical_category)


def _seasonal_context_phrases(feature_head: str, *, interpretation: ProductInterpretation) -> list[str]:
    phrases: list[str] = []
    category_value = feature_head
    head = _category_head(category_value)
    aliases = _category_aliases(category_value)
    event_terms = [term for term in interpretation.grounded_event_terms if term]
    if not event_terms:
        return []
    for term in event_terms:
        normalized_term = " ".join(str(term or "").split()).strip()
        if not normalized_term:
            continue
        phrases.extend([f"{normalized_term} {head}", f"{normalized_term} {category_value}"])
        phrases.extend([f"{normalized_term} {alias}" for alias in aliases])
    return _unique_texts(phrases)


def _attribute_phrases_refined(
    product_name: str,
    *,
    specs: list[str],
    ingredients: list[str],
    technology: list[str],
    form_factors: list[str],
    benefits: list[str],
) -> list[str]:
    phrases: list[str] = []
    for measurement in _variant_measurements(specs)[:6]:
        phrases.append(f"{product_name} {measurement}")
    return _unique_texts(phrases)


def _long_tail_phrases_refined(
    product_name: str,
    category_value: str,
    *,
    audience: list[str],
    benefits: list[str],
    concerns: list[str],
    usage_context: list[str],
    ingredients: list[str],
    form_factors: list[str],
    specs: list[str],
) -> list[str]:
    del audience
    del benefits
    del concerns
    del usage_context
    del form_factors
    phrases: list[str] = []
    for attribute in ingredients[:4]:
        phrases.append(f"{attribute} {category_value}")
        phrases.append(f"{attribute} {_category_head(category_value)}")
    for spec in specs[:2]:
        phrases.extend([f"{product_name} {spec}", f"{category_value} {spec}"])
    return _unique_texts(phrases)


def _benefit_price_phrases_refined(
    product_name: str,
    category_value: str,
    *,
    benefits: list[str],
    ingredients: list[str],
    price_present: bool,
    price_comparison_allowed: bool,
    value_terms: list[str],
) -> list[str]:
    phrases: list[str] = []
    if price_present:
        phrases.extend(
            [
                f"{product_name} 가격",
                f"{category_value} 가격",
            ]
        )
    if price_comparison_allowed and _allow_verbose_search_surfaces():
        phrases.append(f"{product_name} 가격 비교")
    for value_term in value_terms[:4]:
        phrases.extend([f"{product_name} {value_term}", f"{category_value} {value_term}"])
    return _unique_texts(phrases)


def _purchase_intent_phrases(
    *,
    product_name: str,
    short_name: str,
    brand: str,
    category_value: str,
) -> list[str]:
    alias_tokens = _brand_aliases(product_name, brand)
    navigational_brand = alias_tokens[0] if alias_tokens else brand
    navigational_short_name = short_name
    if navigational_short_name == product_name and alias_tokens:
        alias = alias_tokens[0]
        prefix = f"{alias} "
        if product_name.startswith(prefix):
            navigational_short_name = product_name[len(prefix) :].strip()

    phrases = [product_name]
    if navigational_short_name and navigational_short_name != product_name:
        phrases.append(navigational_short_name)
    if navigational_brand:
        phrases.extend(
            [
                f"{navigational_brand} {_category_head(category_value)}",
                f"{navigational_brand} {category_value}",
            ]
        )
        if navigational_short_name and navigational_short_name != product_name:
            phrases.append(f"{navigational_brand} {navigational_short_name}")
    if _allow_verbose_search_surfaces():
        phrases.extend(
            [
                f"{product_name} 공식몰",
                *([f"{navigational_brand} 공식몰"] if navigational_brand else []),
            ]
        )
    return _unique_texts(phrases)


def _comparison_phrases_refined(
    *,
    canonical_category: str,
    secondary_categories: list[str],
    competitor_brands: list[str],
) -> list[str]:
    phrases: list[str] = []
    type_surface = _competitor_type_surface(canonical_category, secondary_categories=secondary_categories)
    for brand in competitor_brands[:4]:
        phrases.extend(
            [
                f"{brand} {type_surface}",
                f"{brand} {type_surface} 비교",
            ]
        )
    return _unique_texts(phrases)


def _competitor_type_surface(canonical_category: str, *, secondary_categories: list[str]) -> str:
    blocked = {"스킨케어", "제품", "상품", "카테고리"}
    for candidate in _unique_texts([canonical_category, *secondary_categories, *_category_aliases(canonical_category)]):
        if candidate in blocked:
            continue
        return candidate
    return canonical_category


def _surface_cleanup_rows(rows: list[KeywordRow], *, evidence_pack: dict[str, Any]) -> list[KeywordRow]:
    cleaned, _ = _surface_cleanup_rows_with_reasons(rows, evidence_pack=evidence_pack)
    return cleaned


def _surface_cleanup_rows_with_reasons(
    rows: list[KeywordRow],
    *,
    evidence_pack: dict[str, Any],
) -> tuple[list[KeywordRow], list[dict[str, str]]]:
    interpretation = _build_product_interpretation(evidence_pack)
    cleaned: list[KeywordRow] = []
    dropped: list[dict[str, str]] = []
    for row in rows:
        keyword = " ".join(row.keyword.split()).strip()
        if not keyword:
            continue
        reason = _surface_policy_reason(keyword, row.category, interpretation=interpretation)
        if reason is not None:
            code, detail = reason
            dropped.append(
                _slot_drop_entry(
                    keyword=keyword,
                    category=row.category,
                    slot_type=str(row.slot_type or ""),
                    drop_stage="surface_cleanup",
                    drop_reason_code=code,
                    drop_reason_detail=detail,
                )
            )
            continue
        cleaned.append(row)
    return cleaned, dropped


def _keyword_rejected_by_surface_policy(
    keyword: str,
    category: str,
    *,
    interpretation: ProductInterpretation,
) -> bool:
    return _surface_policy_reason(keyword, category, interpretation=interpretation) is not None


def _surface_policy_reason(
    keyword: str,
    category: str,
    *,
    interpretation: ProductInterpretation,
) -> tuple[str, str] | None:
    product_name = interpretation.product_name
    canonical_category = interpretation.canonical_category
    category_head = _category_head(canonical_category)
    verbose_surfaces = _allow_verbose_search_surfaces()
    bare_suffixes = set(
        _unique_texts(
            [
                canonical_category,
                *interpretation.secondary_categories,
                *interpretation.audience,
                *interpretation.concerns,
                *interpretation.usage_context,
                "장벽",
                "건조",
            ]
        )
    )

    if not verbose_surfaces and category in {"purchase_intent", "problem_solution", "benefit_price"}:
        if any(
            token in keyword
            for token in (
                "구매 전 체크",
                "구매 준비",
                "구매 상담",
                "구매 문의",
                "구매 타이밍",
                "결제 옵션",
                "고민 해결",
                "필요 이유",
                " 효익",
                "만족도",
                " 해결",
                "구매처",
                "판매처",
                "재고",
                "배송",
            )
        ):
            return ("surface_scaffold", "verbose purchase/problem scaffold")

    lowered_keyword = keyword.casefold()
    page_class = str(interpretation.commerce_facts.get("page_class") or "")
    grounded_event_terms = [
        str(term).casefold() for term in interpretation.commerce_facts.get("grounded_event_terms", [])
    ]
    if any(token.casefold() in lowered_keyword for token in VERBISH_SURFACE_TOKENS):
        return ("surface_product_action", "product plus action surface")

    if page_class not in SUPPORT_PAGE_CLASSES and _looks_informational_surface(lowered_keyword):
        return ("surface_informational", "informational/help-query surface on commerce page")

    if category == "purchase_intent" and any(token.casefold() in lowered_keyword for token in PURCHASE_SUFFIX_TOKENS):
        return ("surface_purchase_suffix", "purchase suffix appended to product name")

    if not verbose_surfaces and category != "brand":
        if any(token in keyword for token in ("베스트셀러", "어워드 위너", "신상품")):
            return ("surface_merchandising", "merchandising scaffold surface")

    if category == "feature_attribute":
        if any(token in keyword for token in (" 특징", " 장점", " 효과")):
            return ("surface_feature_scaffold", "feature/benefit sentence scaffold")
        if keyword.startswith(f"{product_name} "):
            suffix = keyword[len(product_name) :].strip()
            allowed_specs = set(_variant_measurements(interpretation.specs))
            if suffix not in allowed_specs:
                return ("surface_product_prefix", "feature keyword keeps product-name prefix without spec")
        if not _is_grounded_feature_attribute_surface(keyword, interpretation=interpretation):
            return ("surface_ungrounded_feature", "feature keyword lacks grounded attribute/spec evidence")

    if category == "benefit_price":
        if not _is_price_search_surface(keyword):
            return ("surface_price_shape", "benefit_price must stay a search-like noun phrase")
        if _contains_exact_price_surface(keyword):
            return ("surface_raw_price", "raw exact price surface")

    if category == "season_event":
        if keyword.startswith(f"{product_name} "):
            return ("surface_product_prefix", "season/event keyword keeps product-name prefix")
        if any(token in keyword for token in ("데일리 루틴", "건조한 날씨")):
            return ("surface_season_scaffold", "season/event filler surface")
        if _contains_promo_event_surface(lowered_keyword) and not _event_surface_is_grounded(
            lowered_keyword, grounded_event_terms
        ):
            return ("surface_unsupported_event", "promo event not grounded in evidence")
        if not _is_grounded_season_event_surface(keyword, interpretation=interpretation):
            return ("surface_ungrounded_season", "season/event keyword lacks grounded event or usage context")

    if keyword == f"{product_name} {canonical_category}":
        return ("surface_product_prefix", "product plus canonical-category duplication")

    if keyword.startswith(f"{product_name} "):
        suffix = keyword[len(product_name) :].strip()
        if suffix in bare_suffixes:
            return ("surface_product_purpose_suffix", "bare suffix after product name")

    if category in {"purchase_intent", "long_tail", "problem_solution"} and keyword.startswith(f"{product_name} "):
        if category == "purchase_intent" and _is_short_model_alias_surface(keyword, product_name=product_name):
            return None
        return ("surface_product_prefix", "product-prefixed search surface")

    if category == "problem_solution" and not _is_grounded_problem_solution_surface(
        keyword, interpretation=interpretation
    ):
        return ("surface_ungrounded_problem", "problem keyword lacks grounded concern or use-case evidence")

    if _is_product_prefixed_purpose_surface(keyword, product_name=product_name):
        return ("surface_product_purpose_suffix", "product-name plus purpose suffix")

    if category == "competitor_comparison":
        if keyword.endswith(f"대체 {category_head}"):
            return ("surface_competitor_shape", "generic competitor alternative suffix")
        if any(token in keyword for token in ("용량 비교", "가격 비교", "옵션 비교", "라인 비교")):
            return ("surface_competitor_shape", "generic comparison without competitor brand")

    if category == "season_event" and any(keyword.endswith(token) for token in ("입문용", "일상용")):
        return ("surface_product_purpose_suffix", "season/event purpose suffix")

    return None


def _looks_informational_surface(lowered_keyword: str) -> bool:
    return any(token.casefold() in lowered_keyword for token in INFORMATIONAL_SURFACE_TOKENS)


def _contains_promo_event_surface(lowered_keyword: str) -> bool:
    return any(token.casefold() in lowered_keyword for token in PROMO_EVENT_TOKENS)


def _event_surface_is_grounded(lowered_keyword: str, grounded_event_terms: list[str]) -> bool:
    return any(token in lowered_keyword for token in grounded_event_terms)


def _is_grounded_feature_attribute_surface(
    keyword: str,
    *,
    interpretation: ProductInterpretation,
) -> bool:
    grounded_terms = _unique_texts(
        [
            *_variant_measurements(interpretation.specs),
            *interpretation.specs,
            *interpretation.ingredients,
            *interpretation.technology,
            *interpretation.form_factors,
        ]
    )
    return _has_grounded_term_overlap(keyword, grounded_terms)


def _is_grounded_season_event_surface(
    keyword: str,
    *,
    interpretation: ProductInterpretation,
) -> bool:
    lowered = keyword.casefold()
    if any(term.casefold() in lowered for term in interpretation.grounded_event_terms if term):
        return True
    return _has_grounded_term_overlap(keyword, interpretation.usage_context)


def _is_grounded_problem_solution_surface(
    keyword: str,
    *,
    interpretation: ProductInterpretation,
) -> bool:
    grounded_terms = _unique_texts(
        [
            *interpretation.concerns,
            *interpretation.usage_context,
        ]
    )
    return _has_grounded_term_overlap(keyword, grounded_terms)


def _has_grounded_term_overlap(keyword: str, terms: list[str]) -> bool:
    lowered = keyword.casefold()
    keyword_tokens = {token for token in lowered.split() if len(token) >= 2}
    for term in terms:
        normalized_term = " ".join(str(term or "").split()).strip()
        if not normalized_term:
            continue
        lowered_term = normalized_term.casefold()
        if lowered_term in lowered or lowered in lowered_term:
            return True
        term_tokens = {token for token in lowered_term.split() if len(token) >= 2}
        if keyword_tokens and term_tokens and keyword_tokens.intersection(term_tokens):
            return True
    return False


def _is_product_prefixed_purpose_surface(keyword: str, *, product_name: str) -> bool:
    if not keyword.startswith(f"{product_name} "):
        return False
    suffix = keyword[len(product_name) :].strip()
    if not suffix:
        return False
    if _is_measurementish_term(suffix) or _contains_exact_price_surface(suffix) or _is_price_band_surface(suffix):
        return False
    return suffix.endswith("용")


def _is_short_model_alias_surface(keyword: str, *, product_name: str) -> bool:
    if not keyword.startswith(f"{product_name} "):
        return False
    suffix = keyword[len(product_name) :].strip()
    if not suffix or " " in suffix:
        return False
    lowered = suffix.casefold()
    if re.fullmatch(r"\d{1,2}", lowered):
        return True
    if re.fullmatch(r"\d{1,2}(?:세대|gen)", lowered):
        return True
    return False


def _is_price_search_surface(keyword: str) -> bool:
    return "가격" in keyword or _is_price_band_surface(keyword)


def _is_price_band_surface(keyword: str) -> bool:
    return bool(re.search(r"\b\d+\s*(?:원|만원|천원|달러|usd|유로)대\b", keyword.casefold()))


def _contains_exact_price_surface(keyword: str) -> bool:
    lowered = keyword.casefold()
    if _is_price_band_surface(lowered):
        return False
    exact_price_patterns = (
        r"\b\d{1,3}(?:,\d{3})+(?:원)?\b",
        r"\b\d{4,}(?:원)?\b",
        r"\b\d+\s*(?:만원|천원|달러|usd|유로)(?!대)\b",
    )
    return any(re.search(pattern, lowered) for pattern in exact_price_patterns)


def _problem_phrases_refined(
    product_name: str,
    category_value: str,
    *,
    concerns: list[str],
    benefits: list[str],
    audience: list[str],
    usage_context: list[str],
) -> list[str]:
    del product_name
    del benefits
    del audience
    del usage_context
    head = _category_head(category_value)
    phrases: list[str] = []
    for concern in concerns[:6]:
        normalized_concern = " ".join(concern.split()).strip()
        if not normalized_concern:
            continue
        phrases.append(f"{normalized_concern} {head}")
        if head != category_value:
            phrases.append(f"{normalized_concern} {category_value}")
    return _unique_texts(phrases)


def _pad_refined_phrase_bank(
    bank: dict[str, list[dict[str, str]]],
    *,
    positive_category_targets: dict[str, int],
    product_name: str,
    short_name: str,
    brand: str,
    category_value: str,
    category_terms: list[str],
    interpretation: ProductInterpretation,
) -> None:
    backup_bank = {
        "brand": [
            f"{brand} {category_value}",
            *[f"{brand} {term}" for term in category_terms[:3]],
        ],
        "generic_category": [
            f"{brand} {category_value}",
            *([f"{short_name} {category_value}"] if short_name != category_value else []),
        ],
        "feature_attribute": _attribute_phrases_refined(
            short_name,
            specs=interpretation.specs,
            ingredients=interpretation.ingredients,
            technology=interpretation.technology,
            form_factors=interpretation.form_factors,
            benefits=interpretation.benefits[2:] + interpretation.concerns[:3],
        ),
        "competitor_comparison": _comparison_phrases_refined(
            canonical_category=category_value,
            secondary_categories=interpretation.secondary_categories,
            competitor_brands=list(interpretation.commerce_facts.get("competitor_brand_hints") or []),
        ),
        "purchase_intent": _purchase_intent_phrases(
            product_name=product_name,
            short_name=short_name,
            brand=brand,
            category_value=category_value,
        ),
        "long_tail": _long_tail_phrases_refined(
            short_name,
            category_value,
            audience=interpretation.audience,
            benefits=interpretation.benefits,
            concerns=interpretation.concerns,
            usage_context=interpretation.usage_context,
            ingredients=interpretation.ingredients,
            form_factors=interpretation.form_factors,
            specs=interpretation.specs,
        ),
        "benefit_price": _benefit_price_phrases_refined(
            short_name,
            category_value,
            benefits=interpretation.benefits[2:] + interpretation.usage_context[:2],
            ingredients=interpretation.ingredients,
            price_present=bool(str(interpretation.commerce_facts.get("price") or "").strip()),
            price_comparison_allowed=bool(interpretation.commerce_facts.get("price_comparison_allowed")),
            value_terms=list(interpretation.commerce_facts.get("value_terms") or []),
        ),
        "season_event": _seasonal_context_phrases(category_value, interpretation=interpretation),
        "problem_solution": _problem_phrases_refined(
            short_name,
            category_value,
            concerns=interpretation.concerns,
            benefits=interpretation.benefits,
            audience=interpretation.audience,
            usage_context=interpretation.usage_context,
        ),
    }
    for category, target in positive_category_targets.items():
        existing = bank[category]
        seen = {entry["keyword"].casefold() for entry in existing}
        seen_signatures = {_keyword_signature(entry["keyword"]) for entry in existing}
        for keyword in _unique_texts(backup_bank.get(category, [])):
            if len(existing) >= max(target + 8, 24):
                break
            lowered = keyword.casefold()
            signature = _keyword_signature(keyword)
            if lowered in seen or signature in seen_signatures or _is_low_information_keyword(keyword):
                continue
            seen.add(lowered)
            seen_signatures.add(signature)
            existing.append(
                {
                    "keyword": keyword,
                    "reason": f"{product_name} {category} supplementation pool",
                    "evidence_tier": "inferred",
                }
            )

def _dedupe_candidate_dicts(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    seen_signatures: set[str] = set()
    deduped: list[dict[str, str]] = []
    for entry in entries:
        keyword = " ".join(str(entry.get("keyword") or "").split()).strip()
        if not keyword:
            continue
        lowered = keyword.casefold()
        signature = _keyword_signature(keyword)
        if lowered in seen or signature in seen_signatures:
            continue
        seen.add(lowered)
        seen_signatures.add(signature)
        deduped.append({**entry, "keyword": keyword})
    return deduped


def _select_phrase_bank_candidates(
    bank: dict[str, list[dict[str, str]]],
    *,
    category_plan: dict[str, int],
    interpretation: ProductInterpretation | None = None,
) -> dict[str, list[dict[str, str]]]:
    selected: dict[str, list[dict[str, str]]] = {}
    global_seen: set[str] = set()
    global_signatures: set[str] = set()

    for category in POSITIVE_CATEGORIES:
        picked: list[dict[str, str]] = []
        local_seen: set[str] = set()
        local_signatures: set[str] = set()
        for entry in bank.get(category, []):
            keyword = str(entry.get("keyword") or "").strip()
            if not keyword:
                continue
            if interpretation is not None and _keyword_rejected_by_surface_policy(keyword, category, interpretation=interpretation):
                continue
            lowered = keyword.casefold()
            signature = _keyword_signature(keyword)
            if (
                lowered in global_seen
                or lowered in local_seen
                or signature in global_signatures
                or signature in local_signatures
            ):
                continue
            picked.append(entry)
            local_seen.add(lowered)
            local_signatures.add(signature)
            global_seen.add(lowered)
            global_signatures.add(signature)
            if len(picked) >= category_plan[category]:
                break
        selected[category] = picked

    target_total = sum(category_plan.values())
    current_total = sum(len(entries) for entries in selected.values())
    strengths = _category_strengths(interpretation) if interpretation is not None else {category: 1.0 for category in POSITIVE_CATEGORIES}
    refill_order = sorted(
        POSITIVE_CATEGORIES,
        key=lambda category: (
            -(len(bank.get(category, [])) - len(selected.get(category, []))),
            -strengths.get(category, 1.0),
            -POSITIVE_CATEGORY_TARGETS[category],
        ),
    )
    while current_total < target_total:
        added = False
        for category in refill_order:
            for entry in bank.get(category, []):
                keyword = str(entry.get("keyword") or "").strip()
                if not keyword:
                    continue
                if interpretation is not None and _keyword_rejected_by_surface_policy(keyword, category, interpretation=interpretation):
                    continue
                lowered = keyword.casefold()
                signature = _keyword_signature(keyword)
                if (
                    lowered in global_seen
                    or signature in global_signatures
                    or lowered in {str(item.get("keyword") or "").strip().casefold() for item in selected.get(category, [])}
                ):
                    continue
                selected.setdefault(category, []).append(entry)
                global_seen.add(lowered)
                global_signatures.add(signature)
                current_total += 1
                added = True
                break
            if current_total >= target_total:
                break
        if not added:
            break

    return selected


def _canonical_product_name(evidence_pack: dict[str, Any]) -> str:
    facts = list(evidence_pack.get("facts", []))
    page_class = str(evidence_pack.get("page_class") or "")
    raw_value = str(
        evidence_pack.get("canonical_product_name")
        or evidence_pack.get("product_name")
        or _first_fact_value(facts, "product_name")
        or evidence_pack.get("raw_url")
        or "product"
    )
    if page_class in SUPPORT_PAGE_CLASSES:
        direct_name = _first_fact_value(facts, "product_name")
        if direct_name:
            raw_value = direct_name
    return _clean_product_title(raw_value, page_class=page_class)


def _short_product_name(product_name: str, brand: str) -> str:
    tokens = product_name.split()
    if not tokens:
        return product_name
    if tokens[0].casefold() == brand.casefold() and len(tokens) > 1:
        return " ".join(tokens[1:])
    return product_name


def _is_measurementish_term(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?\s?(?:ml|g|kg|inch|in|gb|tb|mah|hz|w|형)", value.strip(), flags=re.IGNORECASE))


def _clean_product_title(value: str, *, page_class: str) -> str:
    cleaned = " ".join(str(value or "").split()).strip(" -|/")
    if not cleaned:
        return "product"
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip(" -|/")

    if page_class in SUPPORT_PAGE_CLASSES and " - " in cleaned:
        retained: list[str] = []
        for part in (piece.strip() for piece in cleaned.split(" - ")):
            lowered = part.casefold()
            if any(token in lowered for token in STORE_SUFFIX_TOKENS):
                break
            retained.append(part)
        if retained:
            cleaned = " - ".join(retained).strip(" -|/")

    tokens = cleaned.split()
    while tokens and tokens[-1].casefold() in STORE_SUFFIX_TOKENS:
        tokens.pop()
    cleaned = " ".join(tokens).strip(" -|/")
    return cleaned or "product"


def _keyword_signature(keyword: str) -> str:
    normalized = keyword.replace("|", " ")
    tokens = [
        token.casefold()
        for token in normalized.split()
        if token and token.casefold() not in STORE_SUFFIX_TOKENS
    ]
    while tokens and tokens[-1] in SHALLOW_SUFFIX_TOKENS:
        tokens.pop()
    deduped: list[str] = []
    for token in tokens:
        if deduped and deduped[-1] == token:
            continue
        deduped.append(token)
    return " ".join(deduped)


def _is_low_information_keyword(keyword: str) -> bool:
    return policy_is_low_information_keyword(keyword)
