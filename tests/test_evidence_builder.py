from __future__ import annotations

from src.collection import FixtureHtmlFetcher, classify_snapshot, collect_snapshot_from_html
from src.evidence import build_evidence_pack
from src.ocr import run_ocr_policy


def test_evidence_builder_preserves_fixture_facts(evidence_fixture_loader) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    snapshot = type(
        "Snapshot",
        (),
        {
            "raw_url": fixture["raw_url"],
            "canonical_url": fixture["canonical_url"],
            "page_class_hint": fixture["page_class"],
            "product_name": fixture["product_name"],
            "title": fixture["product_name"],
            "meta_description": fixture["product_name"],
            "locale_detected": fixture["locale_detected"],
            "market_locale": fixture["market_locale"],
            "sellability_state": fixture["sellability_state"],
            "stock_state": fixture["stock_state"],
            "sufficiency_state": fixture["sufficiency_state"],
            "quality_warning": fixture["quality_warning"],
            "fallback_used": fixture["fallback_used"],
            "weak_backfill_used": fixture["weak_backfill_used"],
            "facts": fixture["facts"],
            "decoded_text": "",
            "ocr_text_blocks": [],
            "price_signals": [],
            "buy_signals": [],
            "support_signals": [],
            "download_signals": [],
            "primary_product_tokens": [],
        },
    )()
    classification = type("Classification", (), {"page_class": fixture["page_class"]})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert len(evidence_pack["facts"]) >= len(fixture["facts"])
    assert any(fact["type"] == "brand" for fact in evidence_pack["facts"])
    assert evidence_pack["direct_fact_count"] >= 1


def test_evidence_builder_derives_facts_from_html_snapshot(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/on-pdp": "on_pdp_en.html"},
    )
    snapshot = collect_snapshot_from_html(fetcher.fetch("https://example.com/on-pdp"))
    classification = classify_snapshot(snapshot)
    ocr_decision = run_ocr_policy(snapshot)

    evidence_pack = build_evidence_pack(snapshot, classification, ocr_decision)
    fact_types = {fact["type"] for fact in evidence_pack["facts"]}

    assert classification.supported_for_generation is True
    assert "product_name" in fact_types
    assert "brand" in fact_types
    assert "product_category" in fact_types
    assert evidence_pack["fact_group_count"] >= 3


def test_evidence_builder_canonicalizes_support_product_name(evidence_fixture_loader) -> None:
    fixture = evidence_fixture_loader("evidence_support_spec.json")
    snapshot = type(
        "Snapshot",
        (),
        {
            "raw_url": fixture["raw_url"],
            "canonical_url": fixture["canonical_url"],
            "page_class_hint": fixture["page_class"],
            "product_name": fixture["product_name"],
            "title": "MacBook Pro 14 기술 사양 - Apple 지원 (KR)",
            "meta_description": fixture["product_name"],
            "locale_detected": fixture["locale_detected"],
            "market_locale": fixture["market_locale"],
            "sellability_state": fixture["sellability_state"],
            "stock_state": fixture["stock_state"],
            "sufficiency_state": fixture["sufficiency_state"],
            "quality_warning": fixture["quality_warning"],
            "fallback_used": fixture["fallback_used"],
            "weak_backfill_used": fixture["weak_backfill_used"],
            "facts": fixture["facts"],
            "decoded_text": "",
            "ocr_text_blocks": [],
            "price_signals": [],
            "buy_signals": [],
            "support_signals": [],
            "download_signals": [],
            "primary_product_tokens": [],
        },
    )()
    classification = type("Classification", (), {"page_class": fixture["page_class"]})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert evidence_pack["canonical_product_name"] == "MacBook Pro 14"
    assert evidence_pack["product_name"] == "MacBook Pro 14"
    assert evidence_pack["display_product_name"] == fixture["product_name"]


def test_evidence_builder_merges_admitted_ocr_blocks_into_facts() -> None:
    snapshot = type(
        "Snapshot",
        (),
        {
            "raw_url": "https://example.com/laneige",
            "canonical_url": "https://example.com/laneige",
            "page_class_hint": "image_heavy_commerce_pdp",
            "product_name": "라네즈 워터 슬리핑 마스크",
            "title": "라네즈 워터 슬리핑 마스크",
            "meta_description": None,
            "locale_detected": "ko",
            "market_locale": "ko_KR",
            "sellability_state": "sellable",
            "stock_state": "InStock",
            "sufficiency_state": "sufficient",
            "quality_warning": False,
            "fallback_used": False,
            "weak_backfill_used": False,
            "facts": [],
            "decoded_text": "짧은 제품 소개",
            "ocr_text_blocks": [],
            "price_signals": [],
            "buy_signals": [],
            "support_signals": [],
            "download_signals": [],
            "primary_product_tokens": ["라네즈", "워터", "슬리핑", "마스크"],
        },
    )()
    classification = type("Classification", (), {"page_class": "image_heavy_commerce_pdp"})()
    ocr_decision = type(
        "OcrDecision",
        (),
        {
            "admitted_blocks": [
                {"text": "라네즈 워터 슬리핑 마스크 판테놀 세라마이드 보습 진정 케어", "source": "image"}
            ]
        },
    )()

    evidence_pack = build_evidence_pack(snapshot, classification, ocr_decision)

    assert evidence_pack["ocr_used"] is True
    assert any(fact["source"].startswith("ocr:") for fact in evidence_pack["facts"])
    assert any(fact["type"] in {"attribute", "use_case"} for fact in evidence_pack["facts"])
