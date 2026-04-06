from __future__ import annotations

from src.collection import FixtureHtmlFetcher
from src.exporting import NotificationTarget
from src.runtime import (
    FixturePipeline,
    create_html_collection_runtime,
    LocalPipelineRuntime,
    create_runtime_resources,
)


def _runtime_with_mapping(
    *,
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    mapping,
):
    resources = create_runtime_resources(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
    )

    return LocalPipelineRuntime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        resolver=FixturePipeline(
            fixture_loader=evidence_fixture_loader,
            url_to_fixture=mapping,
        ).resolve,
    )


def test_runtime_partial_completion_writes_summary_and_single_notification(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
) -> None:
    success_url = "https://example.com/laneige"
    failed_url = "https://example.com/promo-landing"
    runtime = _runtime_with_mapping(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        evidence_fixture_loader=evidence_fixture_loader,
        mapping={
            success_url: "evidence_commerce_pdp_rich.json",
            failed_url: {
                "raw_url": failed_url,
                "canonical_url": failed_url,
                "page_class": "promo_heavy_commerce_landing",
                "quality_warning": False,
                "facts": [],
            },
        },
    )

    job_id = runtime.submit_job(
        urls=[success_url, failed_url],
        requested_platform_mode="both",
        notification_target=NotificationTarget(target_type="email", value="ops@example.com"),
    )
    runtime.drain_all()

    job = runtime.get_job(job_id)
    assert job["status"] == "PARTIAL_COMPLETED"
    assert job["submitted_count"] == 2
    assert job["succeeded_count"] == 1
    assert job["failed_count"] == 1

    tasks = runtime.get_url_tasks(job_id)
    assert [task["status"] for task in tasks] == ["COMPLETED", "FAILED_COLLECTION"]
    success_task, failed_task = tasks

    snapshot = runtime.read_json_artifact(success_task["collection_snapshot_s3_key"])
    assert snapshot["page_class_hint"] == "commerce_pdp"
    classification = runtime.read_json_artifact(success_task["classification_s3_key"])
    assert classification["supported_for_generation"] is True
    ocr_result = runtime.read_json_artifact(success_task["ocr_s3_key"])
    assert ocr_result["status"] == "SKIPPED"
    evidence_pack = runtime.read_json_artifact(success_task["evidence_s3_key"])
    assert evidence_pack["page_class"] == "commerce_pdp"

    failed_classification = runtime.read_json_artifact(failed_task["classification_s3_key"])
    assert failed_classification["supported_for_generation"] is False
    assert failed_classification["page_class"] == "promo_heavy_commerce_landing"
    failed_ocr = runtime.read_json_artifact(failed_task["ocr_s3_key"])
    assert failed_ocr["status"] == "SKIPPED"

    combined = runtime.read_json_artifact(f"jobs/{job_id}/summary/combined.json")
    assert combined["job_id"] == job_id
    assert len(combined["successes"]) == 1
    assert len(combined["failures"]) == 1

    failures = runtime.read_json_artifact(f"jobs/{job_id}/summary/failures.json")
    assert failures["failure_count"] == 1
    assert failures["items"][0]["failure_code"] == "promo_heavy_commerce_landing"

    notifications = runtime.list_notification_records(job_id)
    assert len(notifications) == 1
    assert notifications[0].status == "PARTIAL_COMPLETED"
    assert notifications[0].payload["counts"] == {"submitted": 2, "succeeded": 1, "failed": 1}


def test_runtime_cache_hit_creates_completed_cached_task_and_skips_regeneration(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
) -> None:
    url = "https://example.com/macbook?utm_source=test"
    resolver_calls = {"count": 0}

    def loader(name: str):
        resolver_calls["count"] += 1
        return evidence_fixture_loader(name)

    resources = create_runtime_resources(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
    )
    runtime = LocalPipelineRuntime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        resolver=FixturePipeline(
            fixture_loader=loader,
            url_to_fixture={url: "evidence_support_spec.json"},
        ).resolve,
    )

    first_job_id = runtime.submit_job(urls=[url], requested_platform_mode="google_sa")
    runtime.drain_all()
    first_job = runtime.get_job(first_job_id)
    assert first_job["status"] == "COMPLETED"
    assert resolver_calls["count"] == 1

    second_job_id = runtime.submit_job(urls=[url], requested_platform_mode="google_sa")
    runtime.drain_all()
    second_job = runtime.get_job(second_job_id)
    second_task = runtime.get_url_tasks(second_job_id)[0]

    assert second_job["status"] == "COMPLETED"
    assert second_task["status"] == "COMPLETED_CACHED"
    assert resolver_calls["count"] == 1

    per_url = runtime.read_json_artifact(second_task["result_s3_key"])
    assert per_url["cache_hit"] is True
    assert per_url["requested_platform_mode"] == "google_sa"


def test_cache_cross_mode_reuse_both_from_separate_components(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
) -> None:
    url = "https://example.com/macbook?utm_source=test"
    resolver_calls = {"count": 0}

    def loader(name: str):
        resolver_calls["count"] += 1
        return evidence_fixture_loader(name)

    resources = create_runtime_resources(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
    )
    runtime = LocalPipelineRuntime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        resolver=FixturePipeline(
            fixture_loader=loader,
            url_to_fixture={url: "evidence_support_spec.json"},
        ).resolve,
    )

    first_job_id = runtime.submit_job(urls=[url], requested_platform_mode="google_sa")
    runtime.drain_all()
    assert runtime.get_job(first_job_id)["status"] == "COMPLETED"
    assert resolver_calls["count"] == 1

    second_job_id = runtime.submit_job(urls=[url], requested_platform_mode="naver_sa")
    runtime.drain_all()
    assert runtime.get_job(second_job_id)["status"] == "COMPLETED"
    assert resolver_calls["count"] == 2

    third_job_id = runtime.submit_job(urls=[url], requested_platform_mode="both")
    runtime.drain_all()

    third_job = runtime.get_job(third_job_id)
    third_task = runtime.get_url_tasks(third_job_id)[0]
    per_url = runtime.read_json_artifact(third_task["result_s3_key"])

    assert third_job["status"] == "COMPLETED"
    assert third_task["status"] == "COMPLETED_CACHED"
    assert resolver_calls["count"] == 2
    assert per_url["cache_hit"] is True
    assert per_url["requested_platform_mode"] == "both"
    assert "naver_sa" in per_url["validation_report"]["positive_keyword_counts"]
    assert "google_sa" in per_url["validation_report"]["positive_keyword_counts"]


def test_runtime_with_html_collection_runtime_helper_processes_fixture_html(
    s3_client,
    dynamodb_client,
    sqs_client,
    fixtures_dir,
) -> None:
    resources = create_runtime_resources(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        bucket_name="runtime-bucket-html",
        table_name="runtime-table-html",
        collection_queue_name="runtime-collection-html",
        aggregation_queue_name="runtime-aggregation-html",
        notification_queue_name="runtime-notification-html",
    )
    runtime = create_html_collection_runtime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        fetcher=FixtureHtmlFetcher(
            base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
            url_to_file={
                "https://example.com/on-pdp": "on_pdp_en.html",
                "https://example.com/naver-blocked": "naver_smartstore_blocked.html",
            },
        ),
    )

    job_id = runtime.submit_job(
        urls=["https://example.com/on-pdp", "https://example.com/naver-blocked"],
        requested_platform_mode="naver_sa",
    )
    runtime.drain_all()

    job = runtime.get_job(job_id)
    tasks = runtime.get_url_tasks(job_id)

    assert job["status"] == "PARTIAL_COMPLETED"
    assert [task["status"] for task in tasks] == ["COMPLETED", "FAILED_COLLECTION"]
    assert tasks[0]["page_class"] in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert tasks[1]["page_class"] == "blocked_page"
