from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.keyword_generation import GenerationRequest, generate_keywords
from tests.evaluate_quality import compute_auto_scores


def test_commerce_fixture_meets_quality_thresholds(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    naver_scores = compute_auto_scores(result.rows, "naver_sa", fixture)
    google_scores = compute_auto_scores(result.rows, "google_sa", fixture)

    for scores in (naver_scores, google_scores):
        assert scores["filler_ratio"] < 0.05
        assert scores["avg_naturalness"] >= 0.8
        assert scores["unique_ratio"] >= 0.95
        assert scores["malformed_positive_count"] == 0
        assert scores["invalid_negative_count"] == 0


def test_commerce_fixture_locks_mask_category_and_drops_weak_comparison(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    keywords = {row.keyword for row in result.rows}

    assert "보습 크림" not in keywords
    assert "탄력 크림" not in keywords
    assert "페이스 크림" not in keywords
    assert "라네즈 워터 슬리핑 마스크 옵션 비교" not in keywords
    assert "라네즈 워터 슬리핑 마스크 라인 비교" not in keywords
    assert "라네즈 워터 슬리핑 마스크 가성비" not in keywords
    assert "라네즈 워터 슬리핑 마스크 38000" not in keywords
    assert "슬리핑 마스크" in keywords
    assert "건성 복합성 피부 마스크" not in keywords
    assert "건성 피부 마스크" not in keywords
    assert "복합성 피부 마스크" not in keywords


def test_support_fixture_uses_canonical_product_name_and_fails_fast_on_shortfall(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_support_spec.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    assert result.status == "FAILED_GENERATION"
    assert result.rows
    assert {row.product_name for row in result.rows} == {"MacBook Pro 14"}
    assert result.validation_report is not None
    assert result.validation_report.failure_code == "generation_count_shortfall"


def test_borderline_fixture_fails_fast_without_garbage_top_up(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_borderline.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
        )
    )

    assert result.status == "FAILED_GENERATION"
    assert result.supplementation_attempts == 0
    assert result.validation_report is not None
    assert result.validation_report.failure_code == "generation_count_shortfall"


def test_generation_defaults_to_compact_surface_templates(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    forbidden_tokens = (
        "구매",
        "주문",
        "공식몰",
        "구매 전 체크",
        "구매 준비",
        "구매 상담",
        "구매 문의",
        "구매 타이밍",
        "결제 옵션",
        "필요 이유",
        "고민 해결",
        "효능",
        "만족도",
        "해결",
        "구매처",
        "판매처",
        "광고",
        "배송",
    )
    for row in result.rows:
        if row.category not in {"purchase_intent", "problem_solution", "benefit_price"}:
            continue
        assert not any(token in row.keyword for token in forbidden_tokens)


def test_purchase_intent_uses_exact_or_navigational_queries(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    purchase_keywords = [row.keyword for row in result.rows if row.category == "purchase_intent"]
    assert purchase_keywords == [
        "라네즈 워터 슬리핑 마스크",
        "워터 슬리핑 마스크",
        "라네즈 마스크",
    ]


def test_feature_attribute_is_spec_only(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    feature_keywords = [row.keyword for row in result.rows if row.category == "feature_attribute"]
    assert feature_keywords == [
        "라네즈 워터 슬리핑 마스크 70ml",
        "라네즈 워터 슬리핑 마스크 25ml",
    ]


def test_benefit_price_is_price_only(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    benefit_price_keywords = [row.keyword for row in result.rows if row.category == "benefit_price"]
    assert benefit_price_keywords == [
        "라네즈 워터 슬리핑 마스크 가격",
        "슬리핑 마스크 가격",
    ]


def test_season_event_does_not_invent_usage_context_scaffolds(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    season_keywords = [row.keyword for row in result.rows if row.category == "season_event"]
    assert season_keywords == []


def test_generic_or_long_tail_keeps_ingredient_search_heads(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    keywords = {row.keyword for row in result.rows}
    assert "하이드로 이온화 미네랄 워터 슬리핑 마스크" in keywords
    assert "스쿠알란 슬리핑 마스크" in keywords


def test_problem_solution_drops_product_prefixed_care_templates(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    problem_keywords = [row.keyword for row in result.rows if row.category == "problem_solution"]
    assert all(not keyword.startswith("라네즈 워터 슬리핑 마스크") for keyword in problem_keywords)
    assert "수분 부족 마스크" in problem_keywords
    assert "수면 중 피부 당김 마스크" in problem_keywords
    assert all("케어" not in keyword for keyword in problem_keywords)
    assert all("민감 피부" not in keyword for keyword in problem_keywords)
    assert all("건조 피부" not in keyword for keyword in problem_keywords)
    assert all("피부 장벽" not in keyword for keyword in problem_keywords)
    assert all("피부 탄력" not in keyword for keyword in problem_keywords)


def test_competitor_comparison_drops_generic_category_volume_queries(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    comparison_keywords = [row.keyword for row in result.rows if row.category == "competitor_comparison"]
    assert comparison_keywords == [
        "이니스프리 슬리핑 마스크",
        "메디힐 슬리핑 마스크",
        "닥터자르트 슬리핑 마스크",
        "에스트라 슬리핑 마스크",
    ]
    assert all("용량 비교" not in keyword for keyword in comparison_keywords)
    assert all("70ml" not in keyword and "25ml" not in keyword for keyword in comparison_keywords)


def test_audio_page_does_not_invent_season_or_problem_keywords() -> None:
    evidence = {
        "raw_url": "https://www.apple.com/kr/airpods-pro/",
        "canonical_url": "https://www.apple.com/kr/airpods-pro/",
        "page_class": "commerce_pdp",
        "product_name": "AirPods Pro 3 - Apple (KR)",
        "canonical_product_name": "AirPods Pro 3 - Apple (KR)",
        "facts": [
            {
                "type": "brand",
                "value": "Apple",
                "normalized_value": "Apple",
                "source": "structured_data.brand",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_name",
                "value": "AirPods Pro 3 - Apple (KR)",
                "normalized_value": "AirPods Pro 3 - Apple (KR)",
                "source": "structured_data.name",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_category",
                "value": "wireless earbuds",
                "normalized_value": "wireless earbuds",
                "source": "structured_data.category",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity", "category"],
            },
            {
                "type": "price",
                "value": "400000",
                "normalized_value": "400000",
                "source": "structured_data.offer",
                "evidence_tier": "direct",
                "admissibility_tags": ["sellability", "commerce"],
            },
        ],
    }

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=evidence,
            requested_platform_mode="both",
        )
    )

    assert not [row for row in result.rows if row.category == "season_event"]
    assert not [row for row in result.rows if row.category == "problem_solution"]
