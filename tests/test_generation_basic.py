from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.keyword_generation import GenerationRequest, generate_keywords


def test_naver_sa_hits_100(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
        )
    )
    assert result.status == "COMPLETED"
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["naver_sa"] >= 100


def test_google_sa_hits_100(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="google_sa",
        )
    )
    assert result.status == "COMPLETED"
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["google_sa"] >= 100


def test_both_hits_100_each(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    assert result.status == "COMPLETED"
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["naver_sa"] >= 100
    assert result.validation_report.positive_keyword_counts["google_sa"] >= 100


def test_all_10_categories_present(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    categories = {row.category for row in result.rows}
    assert categories == {
        "brand",
        "generic_category",
        "feature_attribute",
        "competitor_comparison",
        "purchase_intent",
        "long_tail",
        "benefit_price",
        "season_event",
        "problem_solution",
        "negative",
    }
