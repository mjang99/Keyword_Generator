from __future__ import annotations

from src.exporting import (
    JobArtifactUrls,
    NotificationTarget,
    UrlExportResult,
    UrlFailureResult,
    aggregate_job_status,
    build_combined_json_payload,
    build_failures_manifest,
    build_notification_payload,
    build_per_url_json_payload,
    flatten_rows_for_csv,
)
from src.keyword_generation.models import GenerationResult, KeywordRow, ValidationReport


def _sample_generation_result() -> GenerationResult:
    rows = [
        KeywordRow(
            url="https://example.com/product-1",
            product_name="Example Product",
            category="brand",
            keyword="example product",
            naver_match="완전일치",
            google_match="exact",
            reason="brand and product identity observed on page",
            quality_warning=False,
        ),
        KeywordRow(
            url="https://example.com/product-1",
            product_name="Example Product",
            category="long_tail",
            keyword="example product review",
            naver_match="완전일치",
            google_match="",
            reason="platform-specific render only admitted for Naver",
            quality_warning=False,
        ),
        KeywordRow(
            url="https://example.com/product-1",
            product_name="Example Product",
            category="negative",
            keyword="중고",
            naver_match="",
            google_match="negative",
            reason="exclude used-product traffic",
            quality_warning=False,
        ),
    ]
    return GenerationResult(
        status="COMPLETED",
        requested_platform_mode="both",
        rows=rows,
        supplementation_attempts=0,
        validation_report=ValidationReport(
            status="COMPLETED",
            requested_platform_mode="both",
            positive_keyword_counts={"naver_sa": 100, "google_sa": 100},
            category_counts={"naver_sa": {"brand": 1}, "google_sa": {"brand": 1}},
            weak_tier_ratio_by_platform={"naver_sa": 0.0, "google_sa": 0.0},
            quality_warning=False,
        ),
    )


def test_both_mode_flatten_preserves_shared_and_single_platform_rows() -> None:
    success = UrlExportResult(
        url_task_id="ut_001",
        raw_url="https://example.com/product-1",
        page_class="commerce_pdp",
        requested_platform_mode="both",
        generation_result=_sample_generation_result(),
    )
    rows = flatten_rows_for_csv([success])
    assert len(rows) == 3
    assert rows[0]["naver_match"] == "완전일치"
    assert rows[0]["google_match"] == "exact"
    assert rows[1]["naver_match"] == "완전일치"
    assert rows[1]["google_match"] == ""
    assert rows[2]["naver_match"] == ""
    assert rows[2]["google_match"] == "negative"


def test_per_url_json_preserves_fixed_schema_rows() -> None:
    success = UrlExportResult(
        url_task_id="ut_001",
        raw_url="https://example.com/product-1",
        page_class="commerce_pdp",
        requested_platform_mode="both",
        generation_result=_sample_generation_result(),
        cache_hit=True,
    )
    payload = build_per_url_json_payload(success)
    assert payload["url_task_id"] == "ut_001"
    assert payload["cache_hit"] is True
    assert set(payload["rows"][0].keys()) == {
        "url",
        "product_name",
        "category",
        "keyword",
        "naver_match",
        "google_match",
        "reason",
        "quality_warning",
    }
    assert payload["rows"][0]["reason"] == "brand and product identity observed on page"
    assert payload["rows"][0]["quality_warning"] is False


def test_failures_manifest_and_partial_completion_status() -> None:
    success = UrlExportResult(
        url_task_id="ut_001",
        raw_url="https://example.com/product-1",
        page_class="commerce_pdp",
        requested_platform_mode="both",
        generation_result=_sample_generation_result(),
    )
    failure = UrlFailureResult(
        url_task_id="ut_002",
        raw_url="https://example.com/product-2",
        page_class="promo_heavy_commerce_landing",
        requested_platform_mode="both",
        failure_code="promo_heavy_commerce_landing",
        failure_detail="single-product identity not proven",
        quality_warning=None,
    )
    manifest = build_failures_manifest([failure])
    assert manifest["failure_count"] == 1
    assert manifest["items"][0]["failure_code"] == "promo_heavy_commerce_landing"
    assert aggregate_job_status(successes=[success], failures=[failure]) == "PARTIAL_COMPLETED"


def test_notification_payload_contains_one_terminal_summary() -> None:
    success = UrlExportResult(
        url_task_id="ut_001",
        raw_url="https://example.com/product-1",
        page_class="commerce_pdp",
        requested_platform_mode="both",
        generation_result=_sample_generation_result(),
    )
    payload = build_notification_payload(
        job_id="job_001",
        requested_platform_mode="both",
        notification_target=NotificationTarget(target_type="email", value="user@example.com"),
        artifacts=JobArtifactUrls(
            result_manifest_url="/jobs/job_001/results/per_url_manifest",
            combined_json_url="/jobs/job_001/results/combined_json",
            combined_csv_url="/jobs/job_001/results/combined_csv",
            failures_json_url="/jobs/job_001/results/failures_json",
        ),
        successes=[success],
        failures=[],
    )
    assert payload["status"] == "COMPLETED"
    assert payload["notification"]["target_type"] == "email"
    assert payload["counts"] == {"submitted": 1, "succeeded": 1, "failed": 0}
    assert payload["artifacts"]["combined_csv_url"] == "/jobs/job_001/results/combined_csv"
