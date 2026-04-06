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

    assert result.status == "COMPLETED"
    naver_scores = compute_auto_scores(result.rows, "naver_sa", fixture)
    google_scores = compute_auto_scores(result.rows, "google_sa", fixture)

    for scores in (naver_scores, google_scores):
        assert scores["filler_ratio"] < 0.05
        assert scores["avg_naturalness"] >= 0.8
        assert scores["unique_ratio"] >= 0.95
        assert scores["pass"] is True


def test_support_fixture_uses_canonical_product_name_and_passes_quality(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_support_spec.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )

    assert result.status == "COMPLETED"
    assert result.rows
    assert {row.product_name for row in result.rows} == {"MacBook Pro 14"}

    naver_scores = compute_auto_scores(result.rows, "naver_sa", fixture)
    google_scores = compute_auto_scores(result.rows, "google_sa", fixture)

    for scores in (naver_scores, google_scores):
        assert scores["filler_ratio"] < 0.05
        assert scores["avg_naturalness"] >= 0.8
        assert scores["unique_ratio"] >= 0.95
        assert scores["pass"] is True


def test_borderline_fixture_keeps_floor_and_quality_after_supplementation(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_borderline.json")

    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
        )
    )

    assert result.status == "COMPLETED"
    assert result.supplementation_attempts == 1
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["naver_sa"] >= 100

    scores = compute_auto_scores(result.rows, "naver_sa", fixture)
    assert scores["filler_ratio"] < 0.05
    assert scores["avg_naturalness"] >= 0.8
    assert scores["unique_ratio"] >= 0.95
    assert scores["pass"] is True
