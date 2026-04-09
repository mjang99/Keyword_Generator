from __future__ import annotations

import json

from src.handlers import (
    aggregation_worker_handler,
    collection_worker_handler,
    get_job_handler,
    notification_worker_handler,
    submit_job_handler,
)
from src.handlers import api as api_module
from src.handlers import workers as workers_module
from src.keyword_generation.models import GenerationResult, KeywordRow, ValidationReport
from src.runtime import FixturePipeline, LocalPipelineRuntime, create_runtime_resources
from src.runtime.service import load_runtime_resources_from_env


def _receive_sqs_event(sqs_client, queue_url: str) -> dict:
    response = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=0,
    )
    messages = response.get("Messages", [])
    return {
        "Records": [
            {
                "messageId": message["MessageId"],
                "receiptHandle": message["ReceiptHandle"],
                "body": message["Body"],
            }
            for message in messages
        ]
    }


def _successful_generation_result(request) -> GenerationResult:
    raw_url = str(request.evidence_pack.get("raw_url") or request.evidence_pack.get("canonical_url") or "")
    product_name = str(
        request.evidence_pack.get("canonical_product_name")
        or request.evidence_pack.get("product_name")
        or "Example Product"
    )
    rows = [
        KeywordRow(
            url=raw_url,
            product_name=product_name,
            category="brand",
            keyword=product_name,
            naver_match="완전일치" if request.requested_platform_mode in {"naver_sa", "both"} else "",
            google_match="exact" if request.requested_platform_mode in {"google_sa", "both"} else "",
            reason="stubbed handler generation result",
            quality_warning=False,
        ),
        KeywordRow(
            url=raw_url,
            product_name=product_name,
            category="negative",
            keyword="중고",
            naver_match="제외키워드" if request.requested_platform_mode in {"naver_sa", "both"} else "",
            google_match="negative" if request.requested_platform_mode in {"google_sa", "both"} else "",
            reason="stubbed handler exclusion keyword",
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


def test_submit_and_get_job_handlers_return_expected_payload(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
) -> None:
    resources = create_runtime_resources(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        bucket_name="handler-bucket-a",
        table_name="handler-table-a",
        collection_queue_name="handler-collection-a",
        aggregation_queue_name="handler-aggregation-a",
        notification_queue_name="handler-notification-a",
    )
    runtime = LocalPipelineRuntime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        resolver=FixturePipeline(
            fixture_loader=evidence_fixture_loader,
            url_to_fixture={"https://www.laneige.com/kr/product/skincare/water-sleeping-mask": "evidence_commerce_pdp_rich.json"},
        ).resolve,
    )

    submit_response = submit_job_handler(
        {
            "body": json.dumps(
                {
                    "urls": ["https://www.laneige.com/kr/product/skincare/water-sleeping-mask"],
                    "requested_platform_mode": "both",
                    "notification_target": {"email": "ops@example.com"},
                }
            )
        },
        None,
        runtime=runtime,
    )
    assert submit_response["statusCode"] == 202
    submit_body = json.loads(submit_response["body"])
    assert submit_body["status"] == "RECEIVED"
    assert submit_body["submitted_count"] == 1
    assert submit_body["cached_count"] == 0

    job_id = submit_body["job_id"]
    get_response = get_job_handler({"pathParameters": {"job_id": job_id}}, None, runtime=runtime)
    assert get_response["statusCode"] == 200
    get_body = json.loads(get_response["body"])
    assert get_body["job_id"] == job_id
    assert get_body["counts"]["submitted"] == 1
    assert get_body["notification"]["target_type"] == "email"


def test_worker_handlers_drive_job_to_terminal_state(
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    monkeypatch.setattr("src.runtime.service.generate_keywords", _successful_generation_result)
    resources = create_runtime_resources(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        bucket_name="handler-bucket-b",
        table_name="handler-table-b",
        collection_queue_name="handler-collection-b",
        aggregation_queue_name="handler-aggregation-b",
        notification_queue_name="handler-notification-b",
    )
    runtime = LocalPipelineRuntime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        resolver=FixturePipeline(
            fixture_loader=evidence_fixture_loader,
            url_to_fixture={
                "https://www.laneige.com/kr/product/skincare/water-sleeping-mask": "evidence_commerce_pdp_rich.json",
                "https://example.com/fail": {
                    "raw_url": "https://example.com/fail",
                    "canonical_url": "https://example.com/fail",
                    "page_class": "promo_heavy_commerce_landing",
                    "quality_warning": False,
                    "facts": [],
                },
            },
        ).resolve,
    )

    submit_response = submit_job_handler(
        {
            "body": {
                "urls": ["https://www.laneige.com/kr/product/skincare/water-sleeping-mask", "https://example.com/fail"],
                "requested_platform_mode": "both",
                "notification_target": {"webhook": "https://example.com/hook"},
            }
        },
        None,
        runtime=runtime,
    )
    job_id = json.loads(submit_response["body"])["job_id"]

    collection_event = _receive_sqs_event(sqs_client, resources.collection_queue_url)
    assert collection_worker_handler(collection_event, None, runtime=runtime) == {"processed": 2}

    aggregation_event = _receive_sqs_event(sqs_client, resources.aggregation_queue_url)
    assert aggregation_worker_handler(aggregation_event, None, runtime=runtime) == {"processed": 2}

    notification_event = _receive_sqs_event(sqs_client, resources.notification_queue_url)
    assert notification_worker_handler(notification_event, None, runtime=runtime) == {"processed": 1}

    status_response = get_job_handler({"pathParameters": {"job_id": job_id}}, None, runtime=runtime)
    status_body = json.loads(status_response["body"])
    assert status_body["status"] == "PARTIAL_COMPLETED"
    assert status_body["counts"] == {"submitted": 2, "cached": 0, "succeeded": 1, "failed": 1}
    assert status_body["notification"]["sent"] is True


def test_load_runtime_resources_from_env(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_BUCKET", "bucket-a")
    monkeypatch.setenv("KEYWORD_GENERATOR_TABLE", "table-a")
    monkeypatch.setenv("KEYWORD_GENERATOR_COLLECTION_QUEUE_URL", "queue://collection")
    monkeypatch.setenv("KEYWORD_GENERATOR_AGGREGATION_QUEUE_URL", "queue://aggregation")
    monkeypatch.setenv("KEYWORD_GENERATOR_NOTIFICATION_QUEUE_URL", "queue://notification")

    resources = load_runtime_resources_from_env()

    assert resources.bucket_name == "bucket-a"
    assert resources.table_name == "table-a"
    assert resources.collection_queue_url == "queue://collection"
    assert resources.aggregation_queue_url == "queue://aggregation"
    assert resources.notification_queue_url == "queue://notification"


def test_handlers_use_runtime_factory_when_runtime_not_passed(monkeypatch) -> None:
    runtime = type(
        "Runtime",
        (),
        {
            "submit_job": lambda self, **kwargs: "job_9999",
            "build_job_status_payload": lambda self, job_id: {
                "job_id": job_id,
                "counts": {"submitted": 1, "cached": 0},
            },
            "process_collection_records": lambda self, records: len(records),
            "process_aggregation_records": lambda self, records: len(records),
            "process_notification_records": lambda self, records: len(records),
        },
    )()
    monkeypatch.setattr(api_module, "get_runtime", lambda: runtime)
    monkeypatch.setattr(workers_module, "get_runtime", lambda: runtime)

    submit_response = submit_job_handler(
        {"body": {"urls": ["https://example.com/a"], "requested_platform_mode": "naver_sa"}},
        None,
    )
    submit_body = json.loads(submit_response["body"])
    assert submit_response["statusCode"] == 202
    assert submit_body["job_id"] == "job_9999"

    collection_result = collection_worker_handler({"Records": [{"body": "{}"}]}, None)
    aggregation_result = aggregation_worker_handler({"Records": [{"body": "{}"}]}, None)
    notification_result = notification_worker_handler({"Records": [{"body": "{}"}]}, None)

    assert collection_result == {"processed": 1}
    assert aggregation_result == {"processed": 1}
    assert notification_result == {"processed": 1}
