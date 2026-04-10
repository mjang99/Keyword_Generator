from __future__ import annotations

from src.collection import FixtureHtmlFetcher
from src.exporting import NotificationTarget
from src.keyword_generation.models import GenerationResult, KeywordRow, ValidationReport
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


def _successful_generation_result(request) -> GenerationResult:
    raw_url = str(request.evidence_pack.get("raw_url") or request.evidence_pack.get("canonical_url") or "")
    product_name = str(
        request.evidence_pack.get("canonical_product_name")
        or request.evidence_pack.get("product_name")
        or "Example Product"
    )
    naver_match = "완전일치" if request.requested_platform_mode in {"naver_sa", "both"} else ""
    google_match = "exact" if request.requested_platform_mode in {"google_sa", "both"} else ""
    negative_naver_match = "제외키워드" if request.requested_platform_mode in {"naver_sa", "both"} else ""
    negative_google_match = "negative" if request.requested_platform_mode in {"google_sa", "both"} else ""
    rows = [
        KeywordRow(
            url=raw_url,
            product_name=product_name,
            category="brand",
            keyword=product_name,
            naver_match=naver_match,
            google_match=google_match,
            reason="stubbed runtime generation result",
            quality_warning=False,
        ),
        KeywordRow(
            url=raw_url,
            product_name=product_name,
            category="negative",
            keyword="중고",
            naver_match=negative_naver_match,
            google_match=negative_google_match,
            reason="stubbed runtime exclusion keyword",
            quality_warning=False,
        ),
    ]
    positive_counts = {}
    category_counts = {}
    weak_ratios = {}
    for platform in (["naver_sa", "google_sa"] if request.requested_platform_mode == "both" else [request.requested_platform_mode]):
        positive_counts[platform] = 100
        category_counts[platform] = {"brand": 100}
        weak_ratios[platform] = 0.0
    return GenerationResult(
        status="COMPLETED",
        requested_platform_mode=request.requested_platform_mode,
        rows=rows,
        supplementation_attempts=0,
        validation_report=ValidationReport(
            status="COMPLETED",
            requested_platform_mode=request.requested_platform_mode,
            positive_keyword_counts=positive_counts,
            category_counts=category_counts,
            weak_tier_ratio_by_platform=weak_ratios,
            quality_warning=False,
        ),
    )


def _failed_generation_result(request) -> GenerationResult:
    raw_url = str(request.evidence_pack.get("raw_url") or request.evidence_pack.get("canonical_url") or "")
    product_name = str(
        request.evidence_pack.get("canonical_product_name")
        or request.evidence_pack.get("product_name")
        or "Example Product"
    )
    naver_match = "확장소재" if request.requested_platform_mode in {"naver_sa", "both"} else ""
    rows = [
        KeywordRow(
            url=raw_url,
            product_name=product_name,
            category="generic_category",
            keyword=f"{product_name} 테스트",
            naver_match=naver_match,
            google_match="",
            reason="stubbed failed runtime generation result",
            quality_warning=False,
        )
    ]
    return GenerationResult(
        status="FAILED_GENERATION",
        requested_platform_mode=request.requested_platform_mode,
        rows=rows,
        supplementation_attempts=1,
        validation_report=ValidationReport(
            status="FAILED_GENERATION",
            requested_platform_mode=request.requested_platform_mode,
            positive_keyword_counts={"naver_sa": 74} if request.requested_platform_mode in {"naver_sa", "both"} else {},
            category_counts={"naver_sa": {"generic_category": 1}} if request.requested_platform_mode in {"naver_sa", "both"} else {},
            weak_tier_ratio_by_platform={"naver_sa": 0.0} if request.requested_platform_mode in {"naver_sa", "both"} else {},
            failure_code="generation_count_shortfall",
            failure_detail="naver_sa positive rows below 100",
            quality_warning=False,
        ),
    )


def test_runtime_partial_completion_writes_summary_and_single_notification(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.runtime.service.generate_keywords", _successful_generation_result)
    success_url = "https://www.laneige.com/kr/product/skincare/water-sleeping-mask"
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
    assert failures["items"][0]["failure_reason_hints"]

    status_payload = runtime.build_job_status_payload(job_id)
    assert status_payload["url_tasks"][1]["failure_reason_hints"]
    assert status_payload["url_tasks"][0]["fallback_used"] is False
    assert status_payload["url_tasks"][0]["preprocessing_source"] is None

    notifications = runtime.list_notification_records(job_id)
    assert len(notifications) == 1
    assert notifications[0].status == "PARTIAL_COMPLETED"
    assert notifications[0].payload["counts"] == {"submitted": 2, "succeeded": 1, "failed": 1}


def test_failed_generation_persists_partial_per_url_artifact_and_manifest_reference(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.runtime.service.generate_keywords", _failed_generation_result)
    url = "https://www.laneige.com/kr/product/skincare/water-sleeping-mask"
    runtime = _runtime_with_mapping(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        evidence_fixture_loader=evidence_fixture_loader,
        mapping={url: "evidence_commerce_pdp_rich.json"},
    )

    job_id = runtime.submit_job(urls=[url], requested_platform_mode="naver_sa")
    runtime.drain_all()

    job = runtime.get_job(job_id)
    task = runtime.get_url_tasks(job_id)[0]
    assert job["status"] == "FAILED"
    assert task["status"] == "FAILED_GENERATION"
    assert task["result_s3_key"].endswith("/result/per_url.json")
    assert task["failure_s3_key"].endswith("/result/failure.json")

    per_url = runtime.read_json_artifact(task["result_s3_key"])
    assert per_url["status"] == "FAILED_GENERATION"
    assert per_url["validation_report"]["failure_code"] == "generation_count_shortfall"
    assert per_url["rows"][0]["keyword"].endswith("테스트")

    failure = runtime.read_json_artifact(task["failure_s3_key"])
    assert failure["failure_code"] == "generation_count_shortfall"
    assert failure["failure_reason_hints"] == []
    assert failure["fallback_used"] is False
    assert failure["preprocessing_source"] is None

    manifest = runtime.read_json_artifact(f"jobs/{job_id}/summary/per_url_manifest.json")
    assert manifest["items"][0]["status"] == "FAILED_GENERATION"
    assert manifest["items"][0]["artifact"].endswith("/result/per_url.json")


def test_runtime_cache_hit_creates_completed_cached_task_and_skips_regeneration(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.runtime.service.generate_keywords", _successful_generation_result)
    url = "https://www.apple.com/kr/shop/product/MacBookPro14-M3Pro/spec?utm_source=test"
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
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.runtime.service.generate_keywords", _successful_generation_result)
    url = "https://www.apple.com/kr/shop/product/MacBookPro14-M3Pro/spec?utm_source=test"
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
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.runtime.service.generate_keywords", _successful_generation_result)
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
                "https://www.on.com/en-us/products/cloudmonster": "on_pdp_en.html",
                "https://smartstore.naver.com/blocked": "naver_smartstore_blocked.html",
            },
        ),
    )

    job_id = runtime.submit_job(
        urls=["https://www.on.com/en-us/products/cloudmonster", "https://smartstore.naver.com/blocked"],
        requested_platform_mode="naver_sa",
    )
    runtime.drain_all()

    job = runtime.get_job(job_id)
    tasks = runtime.get_url_tasks(job_id)

    assert job["status"] == "PARTIAL_COMPLETED"
    assert [task["status"] for task in tasks] == ["COMPLETED", "FAILED_COLLECTION"]
    assert tasks[0]["page_class"] in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert tasks[1]["page_class"] == "blocked_page"
