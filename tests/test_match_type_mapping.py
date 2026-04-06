from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.keyword_generation import GenerationRequest, generate_keywords

NAVER_ALLOWED = {"완전일치", "확장소재", "제외키워드"}
GOOGLE_ALLOWED = {"exact", "phrase", "broad", "negative"}


def test_naver_match_labels(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    labels = {row.naver_match for row in result.rows if row.naver_match}
    assert labels <= NAVER_ALLOWED


def test_google_match_labels(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="both",
        )
    )
    labels = {row.google_match for row in result.rows if row.google_match}
    assert labels <= GOOGLE_ALLOWED


def test_naver_sa_google_match_blank(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="naver_sa",
        )
    )
    assert all(row.google_match == "" for row in result.rows)


def test_google_sa_naver_match_blank(
    evidence_fixture_loader: Callable[[str], dict[str, Any]],
) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=fixture,
            requested_platform_mode="google_sa",
        )
    )
    assert all(row.naver_match == "" for row in result.rows)
