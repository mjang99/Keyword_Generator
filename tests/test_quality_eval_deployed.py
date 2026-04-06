from __future__ import annotations

import json
from pathlib import Path

from src.quality_eval import build_job_input_from_combined_payload, load_json_from_source


def test_build_job_input_from_combined_payload_maps_successes() -> None:
    payload = {
        "job_id": "job_123",
        "requested_platform_mode": "both",
        "successes": [
            {
                "url_task_id": "ut_1",
                "raw_url": "https://example.com/p",
                "page_class": "commerce_rich_product_detail_page",
                "requested_platform_mode": "both",
                "status": "COMPLETED",
                "rows": [
                    {
                        "url": "https://example.com/p",
                        "product_name": "Laneige Water Sleeping Mask",
                        "category": "brand",
                        "keyword": "라네즈 워터 슬리핑 마스크",
                        "naver_match": "완전일치",
                        "google_match": "phrase",
                        "reason": "brand observed in evidence",
                        "quality_warning": False,
                    }
                ],
                "validation_report": {
                    "status": "COMPLETED",
                    "quality_warning": True,
                },
            }
        ],
        "failures": [{"url_task_id": "ut_2", "failure_code": "fetch_failed"}],
    }

    result = build_job_input_from_combined_payload(payload)

    assert result.job_id == "job_123"
    assert result.requested_platform_mode == "both"
    assert len(result.successes) == 1
    assert result.successes[0].quality_warning is True
    assert result.successes[0].rows[0].keyword == "라네즈 워터 슬리핑 마스크"
    assert result.failures == [{"url_task_id": "ut_2", "failure_code": "fetch_failed"}]


def test_load_json_from_source_reads_local_file() -> None:
    artifact_path = Path("tests/fixtures/evidence_commerce_pdp_rich.json")
    loaded = load_json_from_source(str(artifact_path))

    assert loaded["page_class"] == "commerce_pdp"


def test_load_json_from_source_reads_s3_uri(s3_client: object) -> None:
    bucket_name = "quality-eval-test"
    s3_client.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"},
    )
    payload = {"job_id": "job_s3", "successes": [], "failures": []}
    s3_client.put_object(
        Bucket=bucket_name,
        Key="jobs/job_s3/summary/combined.json",
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )

    loaded = load_json_from_source(
        f"s3://{bucket_name}/jobs/job_s3/summary/combined.json",
        region_name="ap-northeast-2",
    )

    assert loaded == payload
