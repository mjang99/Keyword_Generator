from __future__ import annotations

from pathlib import Path

from src.keyword_generation.models import KeywordRow
from src.quality_eval.golden import (
    GoldenPlatformExpectation,
    GoldenSetCase,
    evaluate_golden_set,
    load_golden_set_case,
    load_golden_source_payload,
)


def test_evaluate_golden_set_flags_missing_keep_and_forbidden_substring() -> None:
    case = GoldenSetCase(
        case_id="synthetic",
        source_path="tests/fixtures/evidence_commerce_pdp_rich.json",
        requested_platform_mode="both",
        platform_expectations={
            "naver_sa": GoldenPlatformExpectation(
                must_keep=["라네즈 워터 슬리핑 마스크"],
                forbidden_substrings=["구매 전 체크"],
                required_categories=["brand", "generic_category"],
            ),
            "google_sa": GoldenPlatformExpectation(
                must_keep=["라네즈 워터 슬리핑 마스크"],
                required_categories=["brand"],
            ),
        },
    )

    rows = [
        KeywordRow(
            url="https://example.com",
            product_name="라네즈 워터 슬리핑 마스크",
            category="brand",
            keyword="라네즈 워터 슬리핑 마스크",
            naver_match="완전일치",
            google_match="exact",
        ),
        KeywordRow(
            url="https://example.com",
            product_name="라네즈 워터 슬리핑 마스크",
            category="purchase_intent",
            keyword="라네즈 워터 슬리핑 마스크 구매 전 체크",
            naver_match="완전일치",
            google_match="phrase",
        ),
    ]

    report = evaluate_golden_set(case, rows=rows, generation_status="COMPLETED")
    naver = next(item for item in report.platform_results if item.platform == "naver_sa")
    google = next(item for item in report.platform_results if item.platform == "google_sa")

    assert not report.pass_
    assert naver.missing_categories == ["generic_category"]
    assert naver.emitted_forbidden_substrings == ["라네즈 워터 슬리핑 마스크 구매 전 체크"]
    assert google.pass_


def test_load_golden_set_case_and_source_payload() -> None:
    case_path = Path("tests/golden_sets/laneige_retinol_live.json")

    case = load_golden_set_case(case_path)
    payload = load_golden_source_payload(case, repo_root=Path.cwd())

    assert case.case_id == "laneige_retinol_live"
    assert case.requested_platform_mode == "both"
    assert "naver_sa" in case.platform_expectations
    assert payload["product_name"]


def test_load_iphone16_golden_set_case() -> None:
    case = load_golden_set_case(Path("tests/golden_sets/iphone16_live.json"))

    assert case.case_id == "iphone16_live"
    assert case.requested_platform_mode == "naver_sa"
    expectation = case.platform_expectations["naver_sa"]
    assert "아이폰16 가격" in expectation.must_keep
    assert "CDMA 아이폰16" in expectation.must_not_emit
    assert "benefit_price" in expectation.required_categories
