from __future__ import annotations

from src.keyword_generation.models import KeywordRow
from src.quality_eval.core import (
    JobEvaluationInput,
    PerUrlEvaluationInput,
    _score_keyword_naturalness,
    evaluate_job_input,
    evaluate_per_url_input,
)


def _make_row(keyword: str, *, category: str = "long_tail") -> KeywordRow:
    return KeywordRow(
        url="https://example.com/p",
        product_name="Laneige Water Sleeping Mask",
        category=category,
        keyword=keyword,
        naver_match="완전일치",
        google_match="phrase",
        reason="supported by fixture evidence",
    )


def _keyword_suffix(index: int) -> str:
    return f"variant{index:03d}"


def test_semantic_uniqueness_flags_trivial_suffix_families() -> None:
    base_rows = [_make_row(f"라네즈 슬리핑 마스크 핵심 효능 {_keyword_suffix(index)}") for index in range(90)]
    duplicate_family = [
        _make_row("라네즈 슬리핑 마스크 추천"),
        _make_row("라네즈 슬리핑 마스크 후기"),
        _make_row("라네즈 슬리핑 마스크 리뷰"),
        _make_row("라네즈 슬리핑 마스크 비교"),
        _make_row("라네즈 슬리핑 마스크 구매"),
        _make_row("라네즈 슬리핑 마스크 정품"),
        _make_row("라네즈 슬리핑 마스크 공식"),
        _make_row("라네즈 슬리핑 마스크 가이드"),
        _make_row("라네즈 슬리핑 마스크 정보"),
        _make_row("라네즈 슬리핑 마스크 탐색"),
    ]
    result = evaluate_per_url_input(
        PerUrlEvaluationInput(
            url_task_id="ut_1",
            raw_url="https://example.com/p",
            page_class="commerce_rich_product_detail_page",
            requested_platform_mode="both",
            quality_warning=False,
            rows=base_rows + duplicate_family,
        ),
        platform="naver_sa",
    )

    assert result.metrics.exact_unique_ratio == 1.0
    assert result.metrics.semantic_unique_ratio < 1.0
    assert result.gate.pass_ is False
    assert "low_semantic_uniqueness" in result.gate.failure_reasons
    assert result.duplicate_families


def test_support_page_long_model_name_remains_natural() -> None:
    support_score = _score_keyword_naturalness(
        "MacBook Pro 14 M4 Pro 24GB 512GB",
        page_class="document_download_heavy_support_page",
    )
    commerce_score = _score_keyword_naturalness(
        "MacBook Pro 14 M4 Pro 24GB 512GB",
        page_class="commerce_rich_product_detail_page",
    )

    assert support_score >= 0.8
    assert support_score > commerce_score


def test_partial_job_keeps_job_pass_when_successful_urls_pass() -> None:
    rows = [_make_row(f"라네즈 슬리핑 마스크 보습 케어 {_keyword_suffix(index)}") for index in range(100)]
    job = JobEvaluationInput(
        job_id="job_1",
        requested_platform_mode="naver_sa",
        successes=[
            PerUrlEvaluationInput(
                url_task_id="ut_1",
                raw_url="https://example.com/p",
                page_class="commerce_rich_product_detail_page",
                requested_platform_mode="naver_sa",
                quality_warning=False,
                rows=rows,
            )
        ],
        failures=[{"url_task_id": "ut_2", "failure_code": "fetch_failed"}],
    )

    result = evaluate_job_input(job)

    assert result.gate.pass_ is True
    assert result.successful_url_coverage == 0.5
    assert len(result.url_results) == 1
