from __future__ import annotations

import pytest

from src.collection import HttpPageFetcher, build_snapshot_from_fixture, classify_snapshot, collect_snapshot_from_html
from src.evidence import build_evidence_pack
from src.exporting import NotificationTarget
from src.keyword_generation.models import GenerationRequest
from src.keyword_generation.service import generate_keywords
from src.ocr import run_ocr_policy
from src.runtime import FixturePipeline, LocalPipelineRuntime, create_runtime_resources


pytestmark = pytest.mark.live_bedrock

REAL_URL_GENERATION_CASES = (
    (
        "apple_iphone16",
        "https://www.apple.com/kr/shop/buy-iphone/iphone-16/6.7%ED%98%95-%EB%94%94%EC%8A%A4%ED%94%8C%EB%A0%88%EC%9D%B4-512gb-%ED%8B%B8",
    ),
    (
        "samsung_s25_case",
        "https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/",
    ),
    (
        "rankingdak_chicken",
        "https://www.rankingdak.com/product/view?productCd=F000008814",
    ),
)


def _runtime_with_mapping(
    *,
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    mapping,
) -> LocalPipelineRuntime:
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


def _positive_rows(payload: dict) -> list[dict]:
    return [row for row in payload.get("rows", []) if row.get("category") != "negative"]


def _positive_keyword_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("category") != "negative"]


def test_live_bedrock_classifier_keeps_laneige_snapshot_supported(
    live_bedrock_guard,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    del live_bedrock_guard
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    snapshot = build_snapshot_from_fixture(evidence_fixture_loader("laneige_retinol_live_snapshot.json"))
    classification = classify_snapshot(snapshot)

    assert classification.supported_for_generation is True
    assert classification.page_class == "commerce_pdp"


def test_live_bedrock_thin_pack_fact_lift_enriches_laneige_snapshot(
    live_bedrock_guard,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    del live_bedrock_guard
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    snapshot = build_snapshot_from_fixture(evidence_fixture_loader("laneige_retinol_thin_snapshot.json"))
    classification = classify_snapshot(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification)

    assert classification.supported_for_generation is True
    assert "thin_pack" in evidence_pack["quality_warning_inputs"]
    assert any(
        str(fact.get("source", "")).startswith("bedrock_fact_lift:")
        for fact in evidence_pack["facts"]
    )


def test_live_bedrock_runtime_completes_laneige_generation(
    live_bedrock_guard,
    s3_client,
    dynamodb_client,
    sqs_client,
    evidence_fixture_loader,
    monkeypatch,
) -> None:
    del live_bedrock_guard
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    url = "https://www.laneige.com/kr/ko/skincare/perfect-renew-retinol.html"
    runtime = _runtime_with_mapping(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        evidence_fixture_loader=evidence_fixture_loader,
        mapping={url: "laneige_retinol_live_snapshot.json"},
    )

    job_id = runtime.submit_job(
        urls=[url],
        requested_platform_mode="naver_sa",
        notification_target=NotificationTarget(target_type="email", value="ops@example.com"),
    )
    runtime.drain_all()

    job = runtime.get_job(job_id)
    task = runtime.get_url_tasks(job_id)[0]

    assert job["status"] == "COMPLETED"
    assert task["status"] == "COMPLETED"

    per_url = runtime.read_json_artifact(task["result_s3_key"])
    positive_rows = _positive_rows(per_url)
    category_counts = per_url["validation_report"]["category_counts"]["naver_sa"]

    assert per_url["status"] == "COMPLETED"
    assert len(positive_rows) >= 100
    assert all(category_counts.get(category, 0) >= 1 for category in (
        "brand",
        "generic_category",
        "feature_attribute",
        "competitor_comparison",
        "purchase_intent",
        "long_tail",
        "benefit_price",
        "season_event",
        "problem_solution",
    ))


@pytest.mark.parametrize(("label", "url"), REAL_URL_GENERATION_CASES)
def test_live_bedrock_real_url_generation_smoke(
    live_bedrock_guard,
    monkeypatch,
    label: str,
    url: str,
) -> None:
    del live_bedrock_guard
    del label
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    fetcher = HttpPageFetcher()
    snapshot = collect_snapshot_from_html(fetcher.fetch(url))
    classification = classify_snapshot(snapshot)
    ocr_decision = run_ocr_policy(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification, ocr_decision)
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=evidence_pack,
            requested_platform_mode="naver_sa",
        )
    )

    assert classification.supported_for_generation is True
    assert classification.page_class == "commerce_pdp"
    assert result.validation_report is not None
    failure_detail = result.validation_report.failure_detail or ""
    assert "Not yet implemented" not in failure_detail

    if result.status == "COMPLETED":
        assert len(_positive_keyword_rows(result.rows)) >= 100
    else:
        assert "bedrock_pipeline_error" not in failure_detail
