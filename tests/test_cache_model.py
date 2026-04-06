from __future__ import annotations

from src.runtime.service import _extract_platform_component, _merge_platform_components, build_cache_key


def _naver_payload() -> dict:
    return {
        "url_task_id": "ut_job_0001_01",
        "raw_url": "https://example.com/product",
        "page_class": "commerce_pdp",
        "requested_platform_mode": "naver_sa",
        "status": "COMPLETED",
        "cache_hit": False,
        "rows": [
            {"url": "https://example.com/product", "product_name": "테스트 제품", "category": "brand",
             "keyword": "테스트 제품", "naver_match": "완전일치", "google_match": "",
             "reason": "brand direct", "quality_warning": False},
        ],
        "validation_report": {
            "status": "COMPLETED",
            "positive_keyword_counts": {"naver_sa": 100},
            "category_counts": {"naver_sa": {"brand": 10}},
            "weak_tier_ratio_by_platform": {"naver_sa": 0.0},
            "quality_warning": False,
            "failure_code": None,
            "failure_detail": None,
        },
    }


def _google_payload() -> dict:
    return {
        "url_task_id": "ut_job_0001_01",
        "raw_url": "https://example.com/product",
        "page_class": "commerce_pdp",
        "requested_platform_mode": "google_sa",
        "status": "COMPLETED",
        "cache_hit": False,
        "rows": [
            {"url": "https://example.com/product", "product_name": "테스트 제품", "category": "brand",
             "keyword": "test product", "naver_match": "", "google_match": "exact",
             "reason": "brand direct", "quality_warning": False},
        ],
        "validation_report": {
            "status": "COMPLETED",
            "positive_keyword_counts": {"google_sa": 100},
            "category_counts": {"google_sa": {"brand": 10}},
            "weak_tier_ratio_by_platform": {"google_sa": 0.0},
            "quality_warning": False,
            "failure_code": None,
            "failure_detail": None,
        },
    }


def test_build_cache_key_uses_platform_component() -> None:
    naver_key = build_cache_key(
        canonical_url="https://example.com/product",
        platform_component="naver_sa",
        policy_version="v1",
        taxonomy_version="v1",
        generator_version="v1",
    )
    google_key = build_cache_key(
        canonical_url="https://example.com/product",
        platform_component="google_sa",
        policy_version="v1",
        taxonomy_version="v1",
        generator_version="v1",
    )

    assert "platform:naver_sa" in naver_key
    assert "platform:google_sa" in google_key
    assert naver_key != google_key
    # Same URL hash prefix
    assert naver_key.split(":")[1] == google_key.split(":")[1]


def test_extract_platform_component_filters_naver_rows() -> None:
    both_payload = {
        "rows": [
            {"keyword": "나이키 슬리퍼", "naver_match": "완전일치", "google_match": "exact"},
            {"keyword": "nike 슬리퍼", "naver_match": "", "google_match": "phrase"},
        ],
        "requested_platform_mode": "both",
    }

    naver = _extract_platform_component(both_payload, "naver_sa")
    google = _extract_platform_component(both_payload, "google_sa")

    assert naver["requested_platform_mode"] == "naver_sa"
    assert len(naver["rows"]) == 1
    assert naver["rows"][0]["naver_match"] == "완전일치"

    assert google["requested_platform_mode"] == "google_sa"
    assert len(google["rows"]) == 2
    assert google["rows"][0]["google_match"] == "exact"
    assert google["rows"][1]["google_match"] == "phrase"


def test_merge_platform_components_combines_rows_and_reports() -> None:
    merged = _merge_platform_components(_naver_payload(), _google_payload())

    assert merged["requested_platform_mode"] == "both"
    assert len(merged["rows"]) == 2  # 1 naver + 1 google
    assert merged["validation_report"]["status"] == "COMPLETED"
    assert "naver_sa" in merged["validation_report"]["positive_keyword_counts"]
    assert "google_sa" in merged["validation_report"]["positive_keyword_counts"]


def test_merge_platform_components_failed_if_either_failed() -> None:
    failed_naver = _naver_payload()
    failed_naver["validation_report"]["status"] = "FAILED_GENERATION"

    merged = _merge_platform_components(failed_naver, _google_payload())

    assert merged["validation_report"]["status"] == "FAILED_GENERATION"
