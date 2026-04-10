from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.keyword_generation import GenerationRequest, generate_keywords


def test_naver_sa_returns_quality_first_rows_even_when_floor_is_missed(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
        )
    )
    assert result.status in {"COMPLETED", "FAILED_GENERATION"}
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["naver_sa"] > 0
    assert result.validation_report.positive_keyword_counts["naver_sa"] <= 100
    assert result.rows


def test_google_sa_returns_quality_first_rows_even_when_floor_is_missed(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="google_sa",
        )
    )
    assert result.status in {"COMPLETED", "FAILED_GENERATION"}
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["google_sa"] > 0
    assert result.validation_report.positive_keyword_counts["google_sa"] <= 100
    assert result.rows


def test_both_returns_quality_first_rows_even_when_floor_is_missed(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    assert result.status in {"COMPLETED", "FAILED_GENERATION"}
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["naver_sa"] > 0
    assert result.validation_report.positive_keyword_counts["naver_sa"] <= 100
    google_count = result.validation_report.positive_keyword_counts.get("google_sa")
    if google_count is not None:
        assert google_count > 0
        assert google_count <= 100
    assert result.rows


def test_soft_category_coverage_is_reported_without_hard_failure(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    assert result.validation_report is not None
    missing = result.validation_report.missing_positive_categories
    assert missing
    assert result.validation_report.failure_code != "generation_category_shortfall"
