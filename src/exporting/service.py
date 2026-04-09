from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.keyword_generation.models import KeywordRow

from .models import JobArtifactUrls, NotificationTarget, UrlExportResult, UrlFailureResult


FIXED_SCHEMA_COLUMNS = (
    "url",
    "product_name",
    "category",
    "keyword",
    "naver_match",
    "google_match",
    "reason",
    "quality_warning",
)


def build_per_url_json_payload(result: UrlExportResult) -> dict[str, Any]:
    validation_report = result.generation_result.validation_report
    return {
        "url_task_id": result.url_task_id,
        "raw_url": result.raw_url,
        "page_class": result.page_class,
        "requested_platform_mode": result.requested_platform_mode,
        "status": result.generation_result.status,
        "cache_hit": result.cache_hit,
        "rows": [fixed_schema_row(row) for row in result.generation_result.rows],
        "debug": result.generation_result.debug_payload,
        "validation_report": {
            "status": validation_report.status if validation_report else None,
            "positive_keyword_counts": validation_report.positive_keyword_counts if validation_report else {},
            "category_counts": validation_report.category_counts if validation_report else {},
            "weak_tier_ratio_by_platform": validation_report.weak_tier_ratio_by_platform if validation_report else {},
            "quality_warning": validation_report.quality_warning if validation_report else False,
            "failure_code": validation_report.failure_code if validation_report else None,
            "failure_detail": validation_report.failure_detail if validation_report else None,
        },
    }


def build_combined_json_payload(
    *,
    job_id: str,
    requested_platform_mode: str,
    successes: list[UrlExportResult],
    failures: list[UrlFailureResult],
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "requested_platform_mode": requested_platform_mode,
        "successes": [build_per_url_json_payload(result) for result in successes],
        "failures": [asdict(failure) for failure in failures],
    }


def flatten_rows_for_csv(successes: list[UrlExportResult]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for success in successes:
        for row in success.generation_result.rows:
            flattened.append(fixed_schema_row(row))
    return flattened


def build_failures_manifest(failures: list[UrlFailureResult]) -> dict[str, Any]:
    return {
        "failure_count": len(failures),
        "items": [asdict(failure) for failure in failures],
    }


def aggregate_job_status(
    *,
    successes: list[UrlExportResult],
    failures: list[UrlFailureResult],
) -> str:
    if successes and failures:
        return "PARTIAL_COMPLETED"
    if successes:
        return "COMPLETED"
    return "FAILED"


def build_notification_payload(
    *,
    job_id: str,
    requested_platform_mode: str,
    notification_target: NotificationTarget,
    artifacts: JobArtifactUrls,
    successes: list[UrlExportResult],
    failures: list[UrlFailureResult],
) -> dict[str, Any]:
    status = aggregate_job_status(successes=successes, failures=failures)
    return {
        "job_id": job_id,
        "status": status,
        "requested_platform_mode": requested_platform_mode,
        "notification": {
            "target_type": notification_target.target_type,
            "value": notification_target.value,
        },
        "counts": {
            "submitted": len(successes) + len(failures),
            "succeeded": len(successes),
            "failed": len(failures),
        },
        "artifacts": {
            "result_manifest_url": artifacts.result_manifest_url,
            "combined_json_url": artifacts.combined_json_url,
            "combined_csv_url": artifacts.combined_csv_url,
            "failures_json_url": artifacts.failures_json_url,
        },
        "successful_url_task_ids": [result.url_task_id for result in successes],
        "failed_url_task_ids": [failure.url_task_id for failure in failures],
    }


def fixed_schema_row(row: KeywordRow) -> dict[str, Any]:
    return {
        "url": row.url,
        "product_name": row.product_name,
        "category": row.category,
        "keyword": row.keyword,
        "naver_match": row.naver_match,
        "google_match": row.google_match,
        "reason": row.reason,
        "quality_warning": row.quality_warning,
    }
