from __future__ import annotations

import json

from src.collection import FixtureHtmlFetcher, classify_snapshot, collect_snapshot_from_html
from src.collection.models import NormalizedPageSnapshot
from src.evidence import build_evidence_pack
from src.ocr import run_ocr_policy


def _snapshot(**overrides) -> NormalizedPageSnapshot:
    base = NormalizedPageSnapshot(
        raw_url="https://example.com/product",
        canonical_url="https://example.com/product",
        page_class_hint="commerce_pdp",
        title="Example Product",
        meta_description="Example Product",
        decoded_text="",
        product_name="Example Product",
        locale_detected="ko",
        market_locale="ko_KR",
        sellability_state="sellable",
        stock_state="InStock",
        sufficiency_state="sufficient",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_evidence_builder_preserves_fixture_facts(evidence_fixture_loader) -> None:
    fixture = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    snapshot = _snapshot(
        raw_url=fixture["raw_url"],
        canonical_url=fixture["canonical_url"],
        page_class_hint=fixture["page_class"],
        title=fixture["product_name"],
        meta_description=fixture["product_name"],
        product_name=fixture["product_name"],
        locale_detected=fixture["locale_detected"],
        market_locale=fixture["market_locale"],
        sellability_state=fixture["sellability_state"],
        stock_state=fixture["stock_state"],
        sufficiency_state=fixture["sufficiency_state"],
        quality_warning=fixture["quality_warning"],
        fallback_used=fixture["fallback_used"],
        weak_backfill_used=fixture["weak_backfill_used"],
        facts=fixture["facts"],
    )
    classification = type("Classification", (), {"page_class": fixture["page_class"]})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert len(evidence_pack["facts"]) >= len(fixture["facts"])
    assert any(fact["type"] == "brand" for fact in evidence_pack["facts"])
    assert evidence_pack["direct_fact_count"] >= 1


def test_evidence_builder_surfaces_fallback_reason_and_preprocessing_source() -> None:
    snapshot = _snapshot(
        decoded_text="상품명 23,900원 장바구니",
        visible_text_blocks=["상품명", "23,900원", "장바구니"],
        fallback_used=True,
        fallback_reason="thin_product_evidence",
        preprocessing_source="cleaned_html",
    )
    classification = type("Classification", (), {"page_class": "commerce_pdp"})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert evidence_pack["fallback_used"] is True
    assert evidence_pack["fallback_reason"] == "thin_product_evidence"
    assert evidence_pack["preprocessing_source"] == "cleaned_html"
    assert "fallback_reason:thin_product_evidence" in evidence_pack["quality_warning_inputs"]
    assert "preprocessing_source:cleaned_html" in evidence_pack["quality_warning_inputs"]


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
    snapshot = _snapshot(
        raw_url=fixture["raw_url"],
        canonical_url=fixture["canonical_url"],
        page_class_hint=fixture["page_class"],
        title="MacBook Pro 14 기술 사양 - Apple 지원 (KR)",
        meta_description=fixture["product_name"],
        product_name=fixture["product_name"],
        locale_detected=fixture["locale_detected"],
        market_locale=fixture["market_locale"],
        sellability_state=fixture["sellability_state"],
        stock_state=fixture["stock_state"],
        sufficiency_state=fixture["sufficiency_state"],
        quality_warning=fixture["quality_warning"],
        fallback_used=fixture["fallback_used"],
        weak_backfill_used=fixture["weak_backfill_used"],
        facts=fixture["facts"],
    )
    classification = type("Classification", (), {"page_class": fixture["page_class"]})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert evidence_pack["canonical_product_name"] == "MacBook Pro 14"
    assert evidence_pack["product_name"] == "MacBook Pro 14"
    assert evidence_pack["display_product_name"] == fixture["product_name"]


def test_evidence_builder_uses_structured_data_and_meta_to_enrich_commerce_snapshot() -> None:
    description = (
        "순도 95% 초순수 레티놀과 트리펩타이드로 주름, 모공탄력 개선, "
        "5D히알루론산으로 수분 까지 커버해 주는 나의 첫 레티놀 크림"
    )
    snapshot = _snapshot(
        raw_url="https://www.laneige.com/kr/ko/skincare/perfect-renew-retinol.html",
        canonical_url="https://www.laneige.com/kr/ko/skincare/perfect-renew-retinol.html",
        title="퍼펙트 리뉴 레티놀 | 라네즈 한국",
        meta_description=description,
        product_name="퍼펙트 리뉴 레티놀 | 라네즈 한국",
        decoded_text="구매하기 15ml 47,000원 30ml 75,000원 " + description,
        price_signals=["price"],
        buy_signals=["buy"],
        structured_data=[
            {
                "@type": "Product",
                "brand": {"name": "라네즈 (LANEIGE)"},
                "name": "퍼펙트 리뉴 레티놀",
                "description": description,
                "offers": {"price": "4700075000", "priceCurrency": "KRW"},
            }
        ],
    )
    classification = type("Classification", (), {"page_class": "commerce_pdp"})()

    evidence_pack = build_evidence_pack(snapshot, classification)
    assert any(fact["type"] == "brand" and fact["normalized_value"] == "라네즈" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "product_name" and fact["normalized_value"] == "퍼펙트 리뉴 레티놀" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "volume" and fact["normalized_value"] == "15ml" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "volume" and fact["normalized_value"] == "30ml" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "variant" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "key_ingredient" and "레티놀" in fact["normalized_value"] for fact in evidence_pack["facts"])
    assert any(fact["type"] == "benefit" and "주름" in fact["normalized_value"] for fact in evidence_pack["facts"])
    assert any(fact["type"] == "benefit" and "수분" in fact["normalized_value"] for fact in evidence_pack["facts"])
    assert not any(fact["type"] == "brand" and fact["normalized_value"] == "퍼펙트" for fact in evidence_pack["facts"])
    assert "thin_pack" not in evidence_pack["quality_warning_inputs"]


def test_evidence_builder_drops_nav_and_badge_blocks_before_fact_promotion() -> None:
    description = (
        "Retinol cream with tripeptide improves wrinkles and pores while 5D hyaluronic acid supports hydration."
    )
    snapshot = _snapshot(
        raw_url="https://www.example.com/skincare/retinol-cream.html",
        canonical_url="https://www.example.com/skincare/retinol-cream.html",
        title="Retinol Cream | Laneige Korea",
        meta_description=description,
        product_name="Retinol Cream | Laneige Korea",
        decoded_text=" ".join(
            [
                "Retinol Cream 50ml 47,000",
                "View all by type cleanser skin mist lotion emulsion serum essence gel cream mask",
                "BEST SELLER INTERNATIONAL",
            ]
        ),
        visible_text_blocks=[
            "Retinol Cream with retinol and tripeptide for wrinkle care hydration 50ml 47,000",
            "View all by type cleanser skin mist lotion emulsion serum essence gel cream mask",
            "BEST SELLER INTERNATIONAL",
        ],
        structured_data=[
            {
                "@type": "Product",
                "brand": {"name": "Laneige"},
                "name": "Retinol Cream",
                "description": description,
                "offers": {"price": "47000", "priceCurrency": "KRW"},
            }
        ],
    )
    classification = type("Classification", (), {"page_class": "commerce_pdp"})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert any(fact["type"] == "brand" and fact["normalized_value"] == "Laneige" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "volume" and fact["normalized_value"] == "50ml" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "price" and fact["normalized_value"] == "47000" for fact in evidence_pack["facts"])
    assert not any("best seller" in fact["normalized_value"].casefold() for fact in evidence_pack["facts"])
    assert not any("international" in fact["normalized_value"].casefold() for fact in evidence_pack["facts"])
    assert not any("view all" in fact["normalized_value"].casefold() for fact in evidence_pack["facts"])
    assert not any("cleanser" in fact["normalized_value"].casefold() for fact in evidence_pack["facts"])
    assert not any(
        "http" in fact["normalized_value"].casefold() for fact in evidence_pack["facts"] if fact["type"] == "product_category"
    )


def test_evidence_builder_falls_back_to_decoded_text_when_visible_blocks_are_sparse() -> None:
    description = "Retinol cream with tripeptide improves wrinkles and pores while 5D hyaluronic acid supports hydration."
    snapshot = _snapshot(
        raw_url="https://www.laneige.com/kr/ko/skincare/perfect-renew-retinol.html",
        canonical_url="https://www.laneige.com/kr/ko/skincare/perfect-renew-retinol.html",
        title="퍼펙트 리뉴 레티놀 | 라네즈 한국",
        meta_description=description,
        product_name="퍼펙트 리뉴 레티놀 | 라네즈 한국",
        decoded_text="\n".join(
            [
                "퍼펙트 리뉴 레티놀 | 라네즈 한국",
                "순도 95% 초순수 레티놀과 트리펩타이드로 주름, 모공탄력 개선",
                "15ml / 30ml",
                "47,000원 / 75,000원",
                "피부가 적응하기 전 3주간 1일 1회 저녁에만 사용해주세요.",
                "민감 피부도 부담 없이 사용할 수 있는 첫 레티놀 크림",
            ]
        ),
        visible_text_blocks=[
            "퍼펙트 리뉴 레티놀 | 라네즈 한국",
            " ",
            " ",
        ],
        structured_data=[
            {
                "@type": "Product",
                "brand": {"name": "라네즈"},
                "name": "퍼펙트 리뉴 레티놀",
                "description": description,
                "offers": {"price": "4700075000", "priceCurrency": "KRW"},
            }
        ],
    )
    classification = type("Classification", (), {"page_class": "commerce_pdp"})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert any(fact["type"] == "volume" and fact["normalized_value"] == "15ml" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "volume" and fact["normalized_value"] == "30ml" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "variant" and "15ml" in fact["normalized_value"] for fact in evidence_pack["facts"])


def test_support_page_does_not_emit_price_fact_even_when_structured_data_contains_offer() -> None:
    snapshot = _snapshot(
        raw_url="https://support.apple.com/kb/macbook-pro-14",
        canonical_url="https://support.apple.com/kb/macbook-pro-14",
        page_class_hint="support_spec_page",
        title="MacBook Pro 14 기술 사양 - Apple 지원",
        meta_description="MacBook Pro 14 기술 사양",
        product_name="MacBook Pro 14 기술 사양",
        decoded_text="14-inch 16GB 512GB 1,990,000원",
        price_signals=["price"],
        structured_data=[
            {
                "@type": "Product",
                "brand": {"name": "Apple"},
                "name": "MacBook Pro 14",
                "offers": {"price": "1990000", "priceCurrency": "KRW"},
            }
        ],
    )
    classification = type("Classification", (), {"page_class": "support_spec_page"})()

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert not any(fact["type"] == "price" for fact in evidence_pack["facts"])
    assert any(fact["type"] == "brand" and fact["normalized_value"] == "Apple" for fact in evidence_pack["facts"])


def test_evidence_builder_does_not_promote_generic_skincare_terms_on_airpods_page() -> None:
    snapshot = _snapshot(
        raw_url="https://www.apple.com/kr/airpods-pro/",
        canonical_url="https://www.apple.com/kr/airpods-pro/",
        title="AirPods Pro 3 - Apple (KR)",
        meta_description="AirPods Pro 3 — 세계 최고의 인이어 액티브 노이즈 캔슬링, 운동 중 심박수 측정 기능.",
        product_name="AirPods Pro 3 - Apple (KR)",
        decoded_text="\n".join(
            [
                "AirPods Pro 3",
                "세계 최고의 인이어 액티브 노이즈 캔슬링.",
                "더욱 향상된 청력 건강 경험.",
                "큰 소음에의 노출을 줄이는 법.",
                "400,000원",
            ]
        ),
        visible_text_blocks=["AirPods Pro 3 - Apple (KR)", " ", " "],
        structured_data=[
            {
                "@type": "Product",
                "brand": {"name": "Apple"},
                "name": "AirPods Pro 3",
                "description": "AirPods Pro 3 — 세계 최고의 인이어 액티브 노이즈 캔슬링, 운동 중 심박수 측정 기능.",
            }
        ],
    )
    classification = type("Classification", (), {"page_class": "commerce_pdp"})()

    evidence_pack = build_evidence_pack(snapshot, classification)
    leaked_terms = {"보습", "건조", "장벽", "야간", "수면", "피부"}

    assert not any(
        fact["type"] in {"benefit", "problem_solution", "use_case", "usage", "audience"}
        and any(term in str(fact["normalized_value"]) for term in leaked_terms)
        for fact in evidence_pack["facts"]
    )


def test_evidence_builder_merges_admitted_ocr_blocks_into_facts() -> None:
    snapshot = _snapshot(
        raw_url="https://example.com/laneige",
        canonical_url="https://example.com/laneige",
        page_class_hint="image_heavy_commerce_pdp",
        product_name="라네즈 워터 슬리핑 마스크",
        title="라네즈 워터 슬리핑 마스크",
        decoded_text="제품 소개",
        primary_product_tokens=["라네즈", "워터", "슬리핑", "마스크"],
    )
    classification = type("Classification", (), {"page_class": "image_heavy_commerce_pdp"})()
    ocr_decision = type(
        "OcrDecision",
        (),
        {
            "admitted_blocks": [{"text": "라네즈 워터 슬리핑 마스크 크림 타입 보습 진정 케어", "source": "image"}],
            "line_groups": [{"text": "라네즈 워터 슬리핑 마스크 크림 타입 보습 진정 케어", "source_type": "ocr_line_group"}],
            "direct_fact_candidates": [{"text": "라네즈 워터 슬리핑 마스크 크림 타입 보습 진정 케어", "source_type": "ocr_line_group"}],
        },
    )()

    evidence_pack = build_evidence_pack(snapshot, classification, ocr_decision)

    assert evidence_pack["ocr_used"] is True
    assert evidence_pack["ocr_direct_fact_candidates"]
    assert any(fact["source"].startswith("ocr_direct:") for fact in evidence_pack["facts"])
    assert any(fact["type"] in {"texture", "use_case", "benefit"} for fact in evidence_pack["facts"])


def test_bedrock_fact_lift_runs_only_for_thin_packs(monkeypatch) -> None:
    import src.clients.bedrock as bedrock_client
    import src.keyword_generation.bedrock_adapter as bedrock_adapter

    snapshot = _snapshot(
        raw_url="https://www.laneige.com/kr/ko/skincare/example.html",
        canonical_url="https://www.laneige.com/kr/ko/skincare/example.html",
        title="퍼펙트 리뉴 레티놀 | 라네즈 한국",
        meta_description="나의 첫 레티놀 크림",
        product_name="퍼펙트 리뉴 레티놀 | 라네즈 한국",
        decoded_text="구매하기",
        buy_signals=["buy"],
        structured_data=[
            {
                "@type": "Product",
                "brand": {"name": "라네즈"},
                "name": "퍼펙트 리뉴 레티놀",
            }
        ],
    )
    classification = type("Classification", (), {"page_class": "commerce_pdp"})()

    monkeypatch.setattr(bedrock_adapter, "should_use_bedrock", lambda: True)
    monkeypatch.setattr(
        bedrock_client,
        "converse_text",
        lambda *args, **kwargs: (
            "model",
            json.dumps(
                {
                    "facts": [
                        {
                            "type": "benefit",
                            "value": "레티놀 크림",
                            "source_field": "meta_description",
                            "source_quote": "레티놀 크림",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        ),
    )

    evidence_pack = build_evidence_pack(snapshot, classification)

    assert any(fact["source"].startswith("bedrock_fact_lift:") for fact in evidence_pack["facts"])
    assert any(fact["type"] == "benefit" and fact["normalized_value"] == "레티놀 크림" for fact in evidence_pack["facts"])
