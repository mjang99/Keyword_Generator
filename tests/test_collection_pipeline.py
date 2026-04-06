from __future__ import annotations

from src.collection import FixtureHtmlFetcher, build_snapshot_from_fixture, classify_snapshot
from src.evidence import build_evidence_pack
from src.ocr import run_ocr_policy
from src.runtime import FixturePipeline, HtmlCollectionPipeline, LocalResolvedFailure, LocalResolvedSuccess


def test_supported_fixture_flows_through_collection_and_evidence_builder(evidence_fixture_loader) -> None:
    payload = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    snapshot = build_snapshot_from_fixture(payload)
    classification = classify_snapshot(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification)
    ocr_result = run_ocr_policy(snapshot)

    assert classification.supported_for_generation is True
    assert classification.page_class == "commerce_pdp"
    assert evidence_pack["page_class"] == "commerce_pdp"
    assert evidence_pack["product_name"]
    assert evidence_pack["facts"]
    assert ocr_result.status == "SKIPPED"


def test_unsupported_fixture_pipeline_returns_terminal_failure(evidence_fixture_loader) -> None:
    pipeline = FixturePipeline(
        fixture_loader=evidence_fixture_loader,
        url_to_fixture={
            "https://example.com/promo": {
                "raw_url": "https://example.com/promo",
                "canonical_url": "https://example.com/promo",
                "page_class": "promo_heavy_commerce_landing",
                "quality_warning": False,
                "facts": [],
            }
        },
    )

    result = pipeline.resolve("https://example.com/promo")
    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "promo_heavy_commerce_landing"
    assert result.page_class == "promo_heavy_commerce_landing"


def test_fixture_pipeline_emits_evidence_pack_for_supported_url(evidence_fixture_loader) -> None:
    pipeline = FixturePipeline(
        fixture_loader=evidence_fixture_loader,
        url_to_fixture={"https://example.com/specs": "evidence_support_spec.json"},
    )

    result = pipeline.resolve("https://example.com/specs")
    assert isinstance(result, LocalResolvedSuccess)
    assert result.evidence_pack["page_class"] == "support_spec_page"
    assert result.evidence_pack["quality_warning"] is True
    assert result.ocr_result["status"] == "SKIPPED"


def test_html_collection_pipeline_emits_evidence_pack_for_supported_url(fixtures_dir) -> None:
    pipeline = HtmlCollectionPipeline(
        fetcher=FixtureHtmlFetcher(
            base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
            url_to_file={"https://example.com/on-pdp": "on_pdp_en.html"},
        )
    )

    result = pipeline.resolve("https://example.com/on-pdp")
    assert isinstance(result, LocalResolvedSuccess)
    assert result.classification["supported_for_generation"] is True
    assert result.evidence_pack["page_class"] in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert result.snapshot["fetch_profile_used"] == "fixture_html"


def test_html_collection_pipeline_returns_terminal_failure_for_blocked_page(fixtures_dir) -> None:
    pipeline = HtmlCollectionPipeline(
        fetcher=FixtureHtmlFetcher(
            base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
            url_to_file={"https://example.com/naver-blocked": "naver_smartstore_blocked.html"},
        )
    )

    result = pipeline.resolve("https://example.com/naver-blocked")
    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "blocked_page"
    assert result.page_class == "blocked_page"
