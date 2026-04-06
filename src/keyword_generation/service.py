from __future__ import annotations

from typing import Any

from .bedrock_adapter import (
    generate_intents_via_bedrock,
    intents_to_rows,
    run_dedup_quality_pass,
    run_supplementation_pass,
    should_use_bedrock,
)
from .constants import (
    DEFAULT_SEASON_SEEDS,
    ELECTRONICS_SEASON_SEEDS,
    GOOGLE_ALLOWED_MATCHES,
    NAVER_ALLOWED_MATCHES,
    NEGATIVE_CATEGORY,
    NEGATIVE_KEYWORD_SEEDS,
    POSITIVE_CATEGORIES,
    POSITIVE_CATEGORY_TARGETS,
    PROMO_BANNED_TERMS,
    SKINCARE_SEASON_SEEDS,
    URGENCY_BANNED_TERMS,
)
from .models import CanonicalIntent, GenerationRequest, GenerationResult, KeywordRow, PlatformRender, ValidationReport
from .validation import validate_keyword_rows

SUPPORT_PAGE_CLASSES = {"support_spec_page", "document_download_heavy_support_page"}
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


def generate_keywords(request: GenerationRequest) -> GenerationResult:
    """Generate keyword rows from an evidence pack.

    In Bedrock mode: runs the 3-call LLM pipeline (generate → dedup+quality → supplement).
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
        except Exception:
            pass  # Fall through to deterministic fallback on any Bedrock error

    return _fallback_pipeline(request)


def _bedrock_pipeline(request: GenerationRequest) -> GenerationResult:
    """3-call LLM pipeline: A(generate) → B(dedup+quality) → C(supplement) → hard rules → floor check."""
    evidence_pack = request.evidence_pack
    quality_warning = bool(evidence_pack.get("quality_warning", False))

    # Step A: Over-generate candidates (initial_generation_target, e.g. 130)
    generation_target = request.initial_generation_target
    intents = generate_intents_via_bedrock(request, positive_target=generation_target)
    if not intents:
        raise ValueError("Bedrock returned no canonical intents")

    # Step B: LLM semantic dedup + quality evaluation
    dedup_report = run_dedup_quality_pass(
        intents,
        request=request,
        platform=request.requested_platform_mode,
        positive_floor=request.max_keywords_per_platform,
        positive_category_targets=POSITIVE_CATEGORY_TARGETS,
    )
    surviving_intents = dedup_report.surviving_keywords
    gap_report = dedup_report.gap_report

    # Step C: LLM supplementation — runs only when gaps remain, at most once
    supplementation_attempts = 0
    if gap_report.get("_total", 0) > 0 and request.supplementation_pass_limit >= 1:
        supplementation_attempts = 1
        surviving_summary = [
            {"intent_text": i.intent_text, "category": i.category}
            for i in surviving_intents
        ]
        supplement_intents = run_supplementation_pass(
            gap_report,
            request=request,
            platform=request.requested_platform_mode,
            surviving_summary=surviving_summary,
        )
        surviving_intents = surviving_intents + supplement_intents

    # Convert to rows
    all_rows = intents_to_rows(surviving_intents, request=request)

    # Step D: Hard rule pass — drop rows that violate compliance rules (promo/urgency/match labels)
    clean_rows = _hard_rule_pass(all_rows, requested_platform_mode=request.requested_platform_mode)

    # Step E: Final floor validation (count, category coverage, negative presence)
    final_report = validate_keyword_rows(
        clean_rows,
        requested_platform_mode=request.requested_platform_mode,
        quality_warning=quality_warning,
    )

    if final_report.status == "COMPLETED":
        return GenerationResult(
            status="COMPLETED",
            requested_platform_mode=request.requested_platform_mode,
            rows=clean_rows,
            intents=surviving_intents,
            supplementation_attempts=supplementation_attempts,
            validation_report=final_report,
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
    return failure


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
    )

    if report.status == "COMPLETED" and report_min_positive_count(report) >= target:
        return GenerationResult(
            status="COMPLETED",
            requested_platform_mode=request.requested_platform_mode,
            rows=rows,
            intents=intents,
            validation_report=report,
        )

    if request.supplementation_pass_limit < 1:
        failure = empty_failure_result(
            request,
            failure_code=report.failure_code or "generation_count_shortfall",
            failure_detail=report.failure_detail or "supplementation pass disabled",
        )
        failure.rows = rows
        failure.intents = intents
        failure.validation_report = report
        return failure

    repaired_target = min(target, feasible_positive_cap)
    intents, rows = _initial_generation(request, positive_target=repaired_target)
    report = validate_keyword_rows(
        rows,
        requested_platform_mode=request.requested_platform_mode,
        quality_warning=quality_warning,
    )

    if report.status != "COMPLETED" or report_min_positive_count(report) < target:
        failure = empty_failure_result(
            request,
            failure_code=report.failure_code or "generation_count_shortfall",
            failure_detail=report.failure_detail or f"unable to reach target {target} after supplementation",
        )
        failure.rows = rows
        failure.intents = intents
        failure.supplementation_attempts = 1
        if report.status != "COMPLETED":
            # Use validate's report only if it carries real failure info
            failure.validation_report = report
        return failure

    return GenerationResult(
        status="COMPLETED",
        requested_platform_mode=request.requested_platform_mode,
        rows=rows,
        intents=intents,
        supplementation_attempts=1,
        validation_report=report,
    )


def _hard_rule_pass(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: str,
) -> list[KeywordRow]:
    """Drop rows that violate hard compliance rules: banned terms and invalid match labels.

    Does NOT enforce count/category floors — those are the final validate_keyword_rows() gate.
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
                return intents, intents_to_rows(intents, request=request)
        except Exception:
            pass

    intents = _build_intents(
        request.evidence_pack,
        requested_platform_mode=request.requested_platform_mode,
        positive_target=positive_target,
    )
    return intents, intents_to_rows(intents, request=request)


def _build_rows(
    evidence_pack: dict[str, Any],
    *,
    requested_platform_mode: str,
    positive_target: int,
) -> list[KeywordRow]:
    product_name = str(evidence_pack.get("product_name") or evidence_pack.get("raw_url") or "product")
    raw_url = str(evidence_pack.get("raw_url") or evidence_pack.get("canonical_url") or "")
    quality_warning = bool(evidence_pack.get("quality_warning", False))
    phrase_bank = _build_refined_phrase_bank(evidence_pack)

    category_plan = _scaled_category_plan(positive_target)
    rows: list[KeywordRow] = []

    for category, target in category_plan.items():
        phrases = phrase_bank[category]
        for index, candidate in enumerate(phrases[:target]):
            naver_match, google_match = _match_labels(category, candidate["keyword"], requested_platform_mode)
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=category,
                    keyword=candidate["keyword"],
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
                naver_match=naver_match,
                google_match=google_match,
                reason=f"{product_name}와 무관하거나 전환 의도가 낮은 제외 키워드",
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
    phrase_bank = _build_refined_phrase_bank(evidence_pack)
    category_plan = _scaled_category_plan(positive_target)
    selected = _select_phrase_bank_candidates(
        phrase_bank,
        category_plan=category_plan,
    )
    selected = _top_up_selected_from_legacy(
        evidence_pack,
        selected=selected,
        category_plan=category_plan,
    )
    intents: list[CanonicalIntent] = []

    for category in POSITIVE_CATEGORIES:
        for candidate in selected.get(category, []):
            intents.append(
                _intent_from_candidate(
                    category=category,
                    keyword=candidate["keyword"],
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
                reason=f"{product_name}와 무관하거나 전환 의도가 낮은 제외 키워드",
                evidence_tier="inferred",
                requested_platform_mode=requested_platform_mode,
            )
        )

    return intents


def _intent_from_candidate(
    *,
    category: str,
    keyword: str,
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
        intent_text=keyword,
        reason=reason,
        evidence_tier=evidence_tier,
        allowed_platforms=allowed_platforms,
        naver_render=naver_render,
        google_render=google_render,
    )


def _build_phrase_bank(evidence_pack: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    facts = list(evidence_pack.get("facts", []))
    product_name = str(evidence_pack.get("product_name") or "product")
    brand = _first_fact_value(facts, "brand") or product_name.split()[0]
    category_value = _first_fact_value(facts, "product_category") or _infer_category_value(product_name)
    attributes = _fact_values_by_tags(facts, {"attribute", "spec", "benefit"})
    use_cases = _fact_values_by_types(facts, {"use_case"})
    concerns = _fact_values_by_tags(facts, {"problem_solution"})
    price = _first_fact_value(facts, "price")
    price_allowed = str(evidence_pack.get("page_class")) != "support_spec_page" and str(
        evidence_pack.get("sellability_state")
    ) == "sellable"

    season_seeds = _season_seeds(product_name, category_value)
    bank: dict[str, list[dict[str, str]]] = {
        "brand": _candidate_dicts(
            _unique_texts(
                [
                    product_name,
                    brand,
                    f"{brand} {category_value}",
                    f"{product_name} 추천",
                    f"{product_name} 후기",
                    f"{product_name} 리뷰",
                    f"{product_name} 비교",
                    f"{brand} {product_name}",
                    f"{product_name} 정품",
                    f"{product_name} 사용법",
                    f"{product_name} 특징",
                    f"{product_name} 효능",
                ]
            ),
            reason=f"{brand}와 제품명 직접 증거 기반",
            evidence_tier="derived",
        ),
        "generic_category": _candidate_dicts(
            _unique_texts(
                [
                    category_value,
                    f"{category_value} 추천",
                    f"{category_value} 비교",
                    f"{category_value} 후기",
                    f"{brand} {category_value}",
                    f"{product_name} 카테고리",
                    f"{category_value} 구매",
                    f"{category_value} 검색",
                    f"{category_value} 인기",
                    f"{category_value} 베스트",
                    f"{category_value} 선택",
                    f"{category_value} 가이드",
                    f"{product_name} {category_value}",
                ]
            ),
            reason=f"{category_value} 카테고리 증거 기반",
            evidence_tier="inferred",
        ),
        "feature_attribute": _candidate_dicts(
            _combinations(product_name, attributes, suffixes=("특징", "사양", "성분", "옵션", "정보")),
            reason=f"{product_name} 속성/사양 증거 기반",
            evidence_tier="direct",
        ),
        "competitor_comparison": _candidate_dicts(
            _unique_texts(
                [
                    f"{product_name} 비교",
                    f"{product_name} 대체",
                    f"{product_name} vs 동급 제품",
                    f"{brand} {category_value} 비교",
                    f"{category_value} 비교",
                    f"{product_name} 경쟁 제품",
                    f"{product_name} 선택 비교",
                    f"{product_name} 추천 비교",
                    f"{category_value} 대안",
                ]
            ),
            reason=f"{product_name} 비교 의도 확장",
            evidence_tier="inferred",
        ),
        "purchase_intent": _candidate_dicts(
            _unique_texts(
                [
                    f"{product_name} 구매",
                    f"{product_name} 추천",
                    f"{product_name} 후기",
                    f"{product_name} 리뷰",
                    f"{product_name} 순위",
                    f"{product_name} 정리",
                    f"{product_name} 선택",
                    f"{product_name} 사용 후기",
                    f"{category_value} 추천",
                    f"{category_value} 후기",
                    f"{brand} {category_value} 구매",
                    f"{product_name} 장단점",
                ]
            ),
            reason=f"{product_name} 구매 의도 확장",
            evidence_tier="derived",
        ),
        "long_tail": _candidate_dicts(
            _long_tail_phrases(product_name, category_value, attributes, use_cases, concerns),
            reason=f"{product_name} 고의도 조합 확장",
            evidence_tier="derived",
        ),
        "benefit_price": _candidate_dicts(
            _benefit_price_phrases(product_name, category_value, attributes, price, price_allowed),
            reason=f"{product_name} 효익/가격 탐색 의도",
            evidence_tier="derived" if price_allowed else "inferred",
        ),
        "season_event": _candidate_dicts(
            _unique_texts([f"{product_name} {seed}" for seed in season_seeds] + [f"{category_value} {seed}" for seed in season_seeds]),
            reason=f"{product_name} 시즌/상황 사용 맥락",
            evidence_tier="inferred",
        ),
        "problem_solution": _candidate_dicts(
            _problem_phrases(product_name, category_value, concerns, attributes),
            reason=f"{product_name} 문제 해결/니즈 맥락",
            evidence_tier="weak" if bool(evidence_pack.get("weak_backfill_used")) else "inferred",
        ),
    }

    _pad_phrase_bank(bank, positive_category_targets=POSITIVE_CATEGORY_TARGETS, product_name=product_name, category_value=category_value)

    if bool(evidence_pack.get("weak_backfill_used")) and "problem_solution" in bank:
        weak_budget = 20
        weak_assigned = 0
        for entry in bank["problem_solution"]:
            if weak_assigned >= weak_budget:
                entry["evidence_tier"] = "inferred"
            else:
                entry["evidence_tier"] = "weak"
                weak_assigned += 1

    return bank


def _scaled_category_plan(positive_target: int) -> dict[str, int]:
    total_default = sum(POSITIVE_CATEGORY_TARGETS.values())
    if positive_target <= 0:
        return {category: 0 for category in POSITIVE_CATEGORIES}

    plan = {
        category: max(1, round(base / total_default * positive_target))
        for category, base in POSITIVE_CATEGORY_TARGETS.items()
    }
    current_total = sum(plan.values())

    overflow_order = [
        "feature_attribute",
        "long_tail",
        "purchase_intent",
        "problem_solution",
        "generic_category",
    ]

    while current_total > positive_target:
        for category in reversed(overflow_order + list(POSITIVE_CATEGORIES)):
            if current_total <= positive_target:
                break
            if plan.get(category, 0) > 1:
                plan[category] -= 1
                current_total -= 1

    while current_total < positive_target:
        for category in overflow_order:
            if current_total >= positive_target:
                break
            plan[category] += 1
            current_total += 1

    return plan


def _candidate_dicts(keywords: list[str], *, reason: str, evidence_tier: str) -> list[dict[str, str]]:
    return [{"keyword": keyword, "reason": reason, "evidence_tier": evidence_tier} for keyword in keywords]


def _match_labels(category: str, keyword: str, requested_platform_mode: str) -> tuple[str, str]:
    if category == NEGATIVE_CATEGORY:
        if requested_platform_mode == "naver_sa":
            return "제외키워드", ""
        if requested_platform_mode == "google_sa":
            return "", "negative"
        return "제외키워드", "negative"

    if category in {"brand", "long_tail", "purchase_intent"}:
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
    lowered = product_name.lower()
    if "macbook" in lowered or "notebook" in lowered or "laptop" in lowered:
        return "노트북"
    if "mask" in lowered or "cream" in lowered or "sleeping" in lowered:
        return "스킨케어"
    if "earbud" in lowered or "이어버드" in product_name:
        return "무선 이어폰"
    return product_name


def _season_seeds(product_name: str, category_value: str) -> tuple[str, ...]:
    lowered = f"{product_name} {category_value}".lower()
    if "macbook" in lowered or "노트북" in category_value:
        return ELECTRONICS_SEASON_SEEDS
    if "mask" in lowered or "스킨케어" in category_value or "크림" in lowered:
        return SKINCARE_SEASON_SEEDS
    return DEFAULT_SEASON_SEEDS


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
                f"{product_name} {value} 추천",
                f"{product_name} {value} 정보",
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
    phrases = [
        f"{product_name} {category_value} 추천",
        f"{product_name} {category_value} 비교",
        f"{product_name} {category_value} 후기",
        f"{product_name} {category_value} 사용법",
    ]
    for attribute in attributes[:8]:
        phrases.append(f"{product_name} {attribute} {category_value}")
        phrases.append(f"{product_name} {attribute} 추천")
    for use_case in use_cases[:4]:
        phrases.append(f"{product_name} {use_case} 추천")
        phrases.append(f"{category_value} {use_case} 추천")
    for concern in concerns[:4]:
        phrases.append(f"{product_name} {concern} 관리")
        phrases.append(f"{category_value} {concern} 추천")
    return _unique_texts(phrases)


def _benefit_price_phrases(
    product_name: str,
    category_value: str,
    attributes: list[str],
    price: str | None,
    price_allowed: bool,
) -> list[str]:
    phrases = [
        f"{product_name} 효과",
        f"{product_name} 장점",
        f"{product_name} 효율",
        f"{category_value} 추천",
        f"{category_value} 만족도",
        f"{product_name} 가성비",
    ]
    if price_allowed and price:
        phrases.extend(
            [
                f"{product_name} 가격",
                f"{product_name} 가격 비교",
                f"{product_name} {price}",
            ]
        )
    for attribute in attributes[:3]:
        phrases.append(f"{product_name} {attribute} 장점")
    return _unique_texts(phrases)


def _problem_phrases(
    product_name: str,
    category_value: str,
    concerns: list[str],
    attributes: list[str],
) -> list[str]:
    phrases = [
        f"{product_name} 고민 해결",
        f"{category_value} 추천",
        f"{product_name} 필요할 때",
    ]
    for concern in concerns[:6]:
        phrases.append(f"{product_name} {concern}")
        phrases.append(f"{category_value} {concern}")
        phrases.append(f"{product_name} {concern} 추천")
    for attribute in attributes[:3]:
        phrases.append(f"{product_name} {attribute} 필요한 경우")
    return _unique_texts(phrases)


def _pad_phrase_bank(
    bank: dict[str, list[dict[str, str]]],
    *,
    positive_category_targets: dict[str, int],
    product_name: str,
    category_value: str,
) -> None:
    fillers = {
        "brand": "브랜드 탐색",
        "generic_category": "카테고리 탐색",
        "feature_attribute": "속성 탐색",
        "competitor_comparison": "비교 탐색",
        "purchase_intent": "구매 탐색",
        "long_tail": "세부 탐색",
        "benefit_price": "효익 탐색",
        "season_event": "상황 탐색",
        "problem_solution": "문제 해결",
    }
    for category, target in positive_category_targets.items():
        existing = bank[category]
        index = 1
        seen = {entry["keyword"].casefold() for entry in existing}
        while len(existing) < max(target, 24):
            filler = f"{product_name} {category_value} {fillers[category]} {index}"
            if filler.casefold() not in seen:
                seen.add(filler.casefold())
                existing.append(
                    {
                        "keyword": filler,
                        "reason": f"{product_name} {category} fallback fill",
                        "evidence_tier": "inferred",
                    }
                )
            index += 1


def _build_refined_phrase_bank(evidence_pack: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    facts = list(evidence_pack.get("facts", []))
    page_class = str(evidence_pack.get("page_class") or "")
    product_name = _canonical_product_name(evidence_pack)
    brand = _first_fact_value(facts, "brand") or product_name.split()[0]
    category_value = _first_fact_value(facts, "product_category") or _infer_category_value(product_name)
    short_name = _short_product_name(product_name, brand)
    feature_head = short_name if page_class in SUPPORT_PAGE_CLASSES else product_name
    attributes = _fact_values_for_generation(
        facts,
        types=ATTRIBUTE_FACT_TYPES,
        tags={"attribute", "spec", "benefit", "brand_technology"},
    )
    benefits = _fact_values_for_generation(
        facts,
        types=BENEFIT_FACT_TYPES,
        tags={"benefit", "social_proof"},
    )
    use_cases = _fact_values_for_generation(
        facts,
        types=USE_CASE_FACT_TYPES,
        tags={"use_case", "audience"},
    )
    concerns = _fact_values_for_generation(
        facts,
        types=CONCERN_FACT_TYPES,
        tags={"problem_solution"},
    )
    price = _first_fact_value(facts, "price")
    price_allowed = page_class not in SUPPORT_PAGE_CLASSES and str(evidence_pack.get("sellability_state")) == "sellable"
    season_seeds = _season_seeds(product_name, category_value)

    bank: dict[str, list[dict[str, str]]] = {
        "brand": _candidate_dicts(
            _unique_texts(
                [
                    product_name,
                    short_name,
                    brand,
                    f"{brand} {category_value}",
                    f"{brand} {short_name}",
                    f"{product_name} 정품",
                    f"{product_name} 공식",
                    f"{short_name} 정품",
                    f"{short_name} 공식",
                    f"{brand} 공식",
                ]
            ),
            reason=f"{brand} 제품명 직접 증거 기반",
            evidence_tier="direct",
        ),
        "generic_category": _candidate_dicts(
            _unique_texts(
                [
                    category_value,
                    f"{category_value} 추천",
                    f"{category_value} 비교",
                    f"{category_value} 후기",
                    f"{category_value} 리뷰",
                    f"{category_value} 구매",
                    f"{category_value} 선택",
                    f"{brand} {category_value}",
                    f"{brand} {category_value} 추천",
                    f"{short_name} 카테고리",
                    f"{category_value} 사용감",
                ]
            ),
            reason=f"{category_value} 카테고리 근거 기반",
            evidence_tier="inferred",
        ),
        "feature_attribute": _candidate_dicts(
            _attribute_phrases_refined(feature_head, attributes, benefits),
            reason=f"{feature_head} 속성 및 스펙 기반",
            evidence_tier="direct",
        ),
        "competitor_comparison": _candidate_dicts(
            _unique_texts(
                [
                    f"{short_name} 비교",
                    f"{short_name} 대안",
                    f"{short_name} 대체",
                    f"{short_name} 라인 비교",
                    f"{short_name} 옵션 비교",
                    f"{short_name} 선택 비교",
                    f"{short_name} vs 동급 제품",
                    f"{brand} {category_value} 비교",
                    f"{category_value} 브랜드 비교",
                    f"{category_value} 대안",
                ]
            ),
            reason=f"{short_name} 비교 탐색 의도",
            evidence_tier="inferred",
        ),
        "purchase_intent": _candidate_dicts(
            _unique_texts(
                [
                    f"{product_name} 구매",
                    f"{product_name} 추천",
                    f"{product_name} 후기",
                    f"{product_name} 리뷰",
                    f"{product_name} 사용 후기",
                    f"{product_name} 구매 후기",
                    f"{product_name} 만족도",
                    f"{product_name} 정품 추천",
                    f"{product_name} 공식 구매",
                    f"{short_name} 구매",
                    f"{short_name} 추천",
                    f"{brand} {category_value} 구매",
                ]
            ),
            reason=f"{product_name} 구매 탐색 의도",
            evidence_tier="derived",
        ),
        "long_tail": _candidate_dicts(
            _long_tail_phrases_refined(feature_head, category_value, attributes, use_cases, concerns),
            reason=f"{feature_head} 조합형 탐색 확장",
            evidence_tier="derived",
        ),
        "benefit_price": _candidate_dicts(
            _benefit_price_phrases_refined(feature_head, category_value, attributes, benefits, price, price_allowed),
            reason=f"{feature_head} 효익 및 가격 탐색",
            evidence_tier="derived" if price_allowed else "inferred",
        ),
        "season_event": _candidate_dicts(
            _unique_texts(
                [f"{feature_head} {seed}" for seed in season_seeds]
                + [f"{category_value} {seed}" for seed in season_seeds]
            ),
            reason=f"{feature_head} 시즌 및 상황 탐색",
            evidence_tier="inferred",
        ),
        "problem_solution": _candidate_dicts(
            _problem_phrases_refined(feature_head, category_value, concerns, benefits, use_cases),
            reason=f"{feature_head} 문제 해결 및 효익 탐색",
            evidence_tier="weak" if bool(evidence_pack.get("weak_backfill_used")) else "inferred",
        ),
    }

    _pad_refined_phrase_bank(
        bank,
        positive_category_targets=POSITIVE_CATEGORY_TARGETS,
        product_name=product_name,
        short_name=short_name,
        brand=brand,
        category_value=category_value,
        attributes=attributes,
        benefits=benefits,
        use_cases=use_cases,
        concerns=concerns,
        season_seeds=season_seeds,
        price=price,
        price_allowed=price_allowed,
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


def _attribute_phrases_refined(product_name: str, attributes: list[str], benefits: list[str]) -> list[str]:
    phrases: list[str] = []
    for attribute in attributes[:18]:
        phrases.extend(
            [
                f"{product_name} {attribute}",
                f"{product_name} {attribute} 특징",
                f"{product_name} {attribute} 스펙",
                f"{product_name} {attribute} 성능",
                f"{product_name} {attribute} 기능",
            ]
        )
    for benefit in benefits[:8]:
        phrases.extend(
            [
                f"{product_name} {benefit}",
                f"{product_name} {benefit} 사용감",
                f"{product_name} {benefit} 장점",
            ]
        )
    return _unique_texts(phrases)


def _long_tail_phrases_refined(
    product_name: str,
    category_value: str,
    attributes: list[str],
    use_cases: list[str],
    concerns: list[str],
) -> list[str]:
    phrases = [
        f"{product_name} {category_value} 추천",
        f"{product_name} {category_value} 비교",
        f"{product_name} {category_value} 후기",
        f"{product_name} {category_value} 사용감",
    ]
    for attribute in attributes[:10]:
        phrases.extend(
            [
                f"{product_name} {attribute} {category_value}",
                f"{product_name} {attribute} 추천",
                f"{product_name} {attribute} 사용감",
            ]
        )
    for use_case in use_cases[:6]:
        phrases.extend(
            [
                f"{product_name} {use_case}",
                f"{product_name} {use_case} 추천",
                f"{category_value} {use_case} 추천",
            ]
        )
    for concern in concerns[:6]:
        phrases.extend(
            [
                f"{product_name} {concern}",
                f"{product_name} {concern} 관리",
                f"{category_value} {concern} 추천",
            ]
        )
    return _unique_texts(phrases)


def _benefit_price_phrases_refined(
    product_name: str,
    category_value: str,
    attributes: list[str],
    benefits: list[str],
    price: str | None,
    price_allowed: bool,
) -> list[str]:
    phrases = [
        f"{product_name} 효과",
        f"{product_name} 장점",
        f"{product_name} 효익",
        f"{category_value} 추천",
        f"{category_value} 만족도",
        f"{product_name} 가성비",
    ]
    if price_allowed and price:
        phrases.extend(
            [
                f"{product_name} 가격",
                f"{product_name} 가격 비교",
                f"{product_name} {price}",
            ]
        )
    for attribute in attributes[:4]:
        phrases.append(f"{product_name} {attribute} 장점")
    for benefit in benefits[:6]:
        phrases.extend(
            [
                f"{product_name} {benefit}",
                f"{product_name} {benefit} 후기",
            ]
        )
    return _unique_texts(phrases)


def _problem_phrases_refined(
    product_name: str,
    category_value: str,
    concerns: list[str],
    benefits: list[str],
    use_cases: list[str],
) -> list[str]:
    phrases = [
        f"{product_name} 고민 해결",
        f"{category_value} 추천",
        f"{product_name} 필요할 때",
    ]
    for concern in concerns[:6]:
        phrases.extend(
            [
                f"{product_name} {concern}",
                f"{product_name} {concern} 추천",
                f"{product_name} {concern} 케어",
                f"{category_value} {concern}",
                f"{product_name} {concern} 선택",
                f"{product_name} {concern} 사용감",
            ]
        )
    for benefit in benefits[:4]:
        phrases.extend(
            [
                f"{product_name} {benefit} 필요할 때",
                f"{product_name} {benefit} 고민",
            ]
        )
    for use_case in use_cases[:4]:
        phrases.extend(
            [
                f"{product_name} {use_case} 고민",
                f"{product_name} {use_case} 해결",
                f"{category_value} {use_case} 고민",
            ]
        )
    return _unique_texts(phrases)


def _pad_refined_phrase_bank(
    bank: dict[str, list[dict[str, str]]],
    *,
    positive_category_targets: dict[str, int],
    product_name: str,
    short_name: str,
    brand: str,
    category_value: str,
    attributes: list[str],
    benefits: list[str],
    use_cases: list[str],
    concerns: list[str],
    season_seeds: tuple[str, ...],
    price: str | None,
    price_allowed: bool,
) -> None:
    backup_bank = {
        "brand": [
            f"{brand} 대표 {category_value}",
            f"{brand} {product_name}",
            f"{short_name} 브랜드",
            f"{product_name} 공식몰",
            f"{product_name} 브랜드",
            f"{short_name} 정식 제품",
        ],
        "generic_category": [
            f"{category_value} 정리",
            f"{category_value} 사용 후기",
            f"{category_value} 추천 제품",
            f"{brand} {category_value} 후기",
            f"{short_name} 관련 카테고리",
            f"{category_value} 선택 기준",
        ],
        "feature_attribute": _attribute_phrases_refined(
            short_name,
            attributes[2:] + benefits[:6] + use_cases[:3],
            benefits[2:] + concerns[:3],
        ),
        "competitor_comparison": [
            f"{short_name} 브랜드 비교",
            f"{short_name} 스펙 비교",
            f"{short_name} 후기 비교",
            f"{short_name} 선택 포인트",
            f"{category_value} 동급 비교",
            f"{category_value} 옵션 비교",
        ],
        "purchase_intent": [
            f"{short_name} 구매 가이드",
            f"{short_name} 구매 전 체크",
            f"{short_name} 선택 포인트",
            f"{product_name} 사용 후기",
            f"{product_name} 구매 만족도",
            f"{brand} {category_value} 추천 제품",
        ],
        "long_tail": _long_tail_phrases_refined(short_name, category_value, attributes[4:], use_cases[2:], concerns[2:]),
        "benefit_price": _benefit_price_phrases_refined(short_name, category_value, attributes[2:], benefits[2:], price, price_allowed),
        "season_event": [f"{short_name} {seed}" for seed in season_seeds] + [f"{category_value} {seed}" for seed in season_seeds],
        "problem_solution": _problem_phrases_refined(
            short_name,
            category_value,
            concerns + attributes[:4],
            benefits + concerns[:3],
            use_cases + benefits[:3],
        ),
    }
    for category, target in positive_category_targets.items():
        existing = bank[category]
        seen = {entry["keyword"].casefold() for entry in existing}
        for keyword in _unique_texts(backup_bank.get(category, [])):
            if len(existing) >= max(target + 8, 24):
                break
            lowered = keyword.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            existing.append(
                {
                    "keyword": keyword,
                    "reason": f"{product_name} {category} supplementation pool",
                    "evidence_tier": "inferred",
                }
            )


def _dedupe_candidate_dicts(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for entry in entries:
        keyword = " ".join(str(entry.get("keyword") or "").split()).strip()
        if not keyword:
            continue
        lowered = keyword.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append({**entry, "keyword": keyword})
    return deduped


def _select_phrase_bank_candidates(
    bank: dict[str, list[dict[str, str]]],
    *,
    category_plan: dict[str, int],
) -> dict[str, list[dict[str, str]]]:
    selected: dict[str, list[dict[str, str]]] = {}
    global_seen: set[str] = set()

    for category in POSITIVE_CATEGORIES:
        picked: list[dict[str, str]] = []
        local_seen: set[str] = set()
        for entry in bank.get(category, []):
            keyword = str(entry.get("keyword") or "").strip()
            if not keyword:
                continue
            lowered = keyword.casefold()
            if lowered in global_seen or lowered in local_seen:
                continue
            picked.append(entry)
            local_seen.add(lowered)
            global_seen.add(lowered)
            if len(picked) >= category_plan[category]:
                break
        selected[category] = picked

    return selected


def _top_up_selected_from_legacy(
    evidence_pack: dict[str, Any],
    *,
    selected: dict[str, list[dict[str, str]]],
    category_plan: dict[str, int],
) -> dict[str, list[dict[str, str]]]:
    if all(len(selected.get(category, [])) >= category_plan[category] for category in POSITIVE_CATEGORIES):
        return selected

    legacy_bank = _build_phrase_bank(evidence_pack)
    global_seen = {
        str(entry.get("keyword") or "").strip().casefold()
        for entries in selected.values()
        for entry in entries
        if str(entry.get("keyword") or "").strip()
    }

    for category in POSITIVE_CATEGORIES:
        local = selected.setdefault(category, [])
        local_seen = {
            str(entry.get("keyword") or "").strip().casefold()
            for entry in local
            if str(entry.get("keyword") or "").strip()
        }
        for candidate in legacy_bank.get(category, []):
            keyword = str(candidate.get("keyword") or "").strip()
            lowered = keyword.casefold()
            if not keyword or lowered in local_seen or lowered in global_seen:
                continue
            local.append(candidate)
            local_seen.add(lowered)
            global_seen.add(lowered)
            if len(local) >= category_plan[category]:
                break

    return selected


def _canonical_product_name(evidence_pack: dict[str, Any]) -> str:
    facts = list(evidence_pack.get("facts", []))
    page_class = str(evidence_pack.get("page_class") or "")
    if page_class in SUPPORT_PAGE_CLASSES:
        direct_name = _first_fact_value(facts, "product_name")
        if direct_name:
            return direct_name
    return str(
        evidence_pack.get("canonical_product_name")
        or evidence_pack.get("product_name")
        or _first_fact_value(facts, "product_name")
        or evidence_pack.get("raw_url")
        or "product"
    )


def _short_product_name(product_name: str, brand: str) -> str:
    tokens = product_name.split()
    if not tokens:
        return product_name
    if tokens[0].casefold() == brand.casefold() and len(tokens) > 1:
        return " ".join(tokens[1:])
    return product_name
