from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from src.keyword_generation import GenerationRequest, KeywordRow, generate_keywords, validate_keyword_rows

PROMO_BANNED_TERMS = ("할인", "쿠폰", "최저가", "특가", "무료배송")
URGENCY_BANNED_TERMS = ("즉시출고", "당일배송", "재고임박", "마감임박", "품절임박")


def test_no_promo_from_support_page(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_support_spec.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    rendered = " ".join(row.keyword for row in result.rows)
    for term in PROMO_BANNED_TERMS:
        assert term not in rendered


def test_out_of_stock_no_urgency(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = deepcopy(evidence_fixture_loader("evidence_commerce_pdp_rich.json"))
    fixture["stock_state"] = "OutOfStock"
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
        )
    )
    rendered = " ".join(row.keyword for row in result.rows)
    for term in URGENCY_BANNED_TERMS:
        assert term not in rendered


def test_weak_tier_cap_20pct() -> None:
    rows = [
        KeywordRow(
            url="https://example.com",
            product_name="Example Product",
            category="feature_attribute",
            keyword=f"example keyword {index}",
            naver_match="확장소재",
            google_match="broad",
            reason="fixture row",
            quality_warning=True,
            evidence_tier="weak" if index < 21 else "direct",
        )
        for index in range(100)
    ]
    rows.append(
        KeywordRow(
            url="https://example.com",
            product_name="Example Product",
            category="negative",
            keyword="중고",
            naver_match="제외키워드",
            google_match="negative",
            reason="negative fixture row",
            quality_warning=True,
            evidence_tier="inferred",
        )
    )
    report = validate_keyword_rows(
        rows,
        requested_platform_mode="both",
        quality_warning=True,
        evidence_pack={"canonical_product_name": "Example Product", "product_name": "Example Product", "facts": []},
    )
    assert report.status == "FAILED_GENERATION"
    assert report.failure_code == "generation_category_shortfall" or report.failure_code == "generation_rule_violation"


def test_quality_warning_set_correctly(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    expectations = {
        "evidence_commerce_pdp_rich.json": False,
        "evidence_support_spec.json": True,
        "evidence_borderline.json": True,
    }
    for fixture_name, expected_warning in expectations.items():
        fixture = evidence_fixture_loader(fixture_name)
        result = generate_keywords(
            GenerationRequest(
                evidence_pack=fixture,
                requested_platform_mode=fixture["requested_platform_mode"],
            )
        )
        assert result.rows
        assert {row.quality_warning for row in result.rows} == {expected_warning}


def test_skincare_generation_avoids_placeholder_product_and_business_fallback_terms(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = deepcopy(evidence_fixture_loader("evidence_commerce_pdp_rich.json"))
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    keywords = [row.keyword for row in result.rows if row.category != "negative"]

    assert all("제품" not in keyword for keyword in keywords)
    assert all("업무용" not in keyword for keyword in keywords)
    assert all("기본형" not in keyword for keyword in keywords)
    assert all("라인업" not in keyword for keyword in keywords)
