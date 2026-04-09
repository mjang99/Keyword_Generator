from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.keyword_generation import GenerationRequest, generate_keywords


def test_fallback_fails_fast_on_shortfall(
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


def test_no_second_supplementation(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_borderline.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
            max_keywords_per_platform=120,
        )
    )
    assert result.status == "FAILED_GENERATION"
    assert result.supplementation_attempts == 0
    assert result.validation_report is not None
    assert result.validation_report.failure_code == "generation_count_shortfall"
