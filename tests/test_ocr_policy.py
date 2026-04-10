from __future__ import annotations

from src.collection.models import NormalizedPageSnapshot, PageClassification
from src.evidence import build_evidence_pack
from src.ocr import run_ocr_policy


def _snapshot(**overrides) -> NormalizedPageSnapshot:
    base = NormalizedPageSnapshot(
        raw_url="https://example.com/product",
        canonical_url="https://example.com/product",
        page_class_hint="commerce_pdp",
        decoded_text="라네즈 워터 슬리핑 마스크 제품 상세 설명과 주요 성분 소개",
        usable_text_chars=2200,
        charset_confidence=0.98,
        product_name="라네즈 워터 슬리핑 마스크",
        primary_product_tokens=["라네즈", "워터", "슬리핑", "마스크"],
        image_candidates=[],
        ocr_text_blocks=[],
        facts=[],
        locale_detected="ko",
        market_locale="ko_KR",
        sellability_state="sellable",
        stock_state="InStock",
        sufficiency_state="sufficient",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_ocr_skips_when_not_required() -> None:
    decision = run_ocr_policy(_snapshot())

    assert decision.status == "SKIPPED"
    assert decision.trigger_reasons == ["ocr_not_required"]
    assert decision.admitted_blocks == []


def test_ocr_ranks_images_and_filters_blocks_for_image_heavy_page() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=900,
        image_candidates=[
            {"src": "https://cdn.example.com/logo.png", "alt": "laneige logo", "width": 128, "height": 128},
            {"src": "https://cdn.example.com/hero-spec.jpg", "alt": "라네즈 워터 슬리핑 마스크 주요 성분", "width": 1200, "height": 1200},
        ],
        ocr_text_blocks=[
            {"text": "라네즈 워터 슬리핑 마스크 피부 보습 진정 케어 판테놀 히알루론산", "source": "image"},
            {"text": "AMORE AMORE AMORE", "source": "image"},
            {"text": "12345 67890 12345 67890", "source": "image"},
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.status == "AVAILABLE"
    assert "image_heavy_page" in decision.trigger_reasons
    assert len(decision.ranked_image_candidates) == 1
    assert decision.ranked_image_candidates[0]["src"].endswith("hero-spec.jpg")
    assert len(decision.admitted_blocks) == 1
    assert "판테놀" in decision.admitted_blocks[0]["text"]
    assert {block["rejection_reason"] for block in decision.rejected_blocks} == {
        "brand_only_repetition",
        "mostly_numeric_junk",
    }


def test_build_evidence_pack_uses_admitted_ocr_blocks_and_sets_warning_when_dominant() -> None:
    snapshot = _snapshot(
        decoded_text="짧은 설명",
        usable_text_chars=4,
        page_class_hint="image_heavy_commerce_pdp",
        image_candidates=[{"src": "https://cdn.example.com/spec.jpg", "alt": "라네즈 워터 슬리핑 마스크 성분표"}],
        ocr_text_blocks=[
            {"text": "라네즈 워터 슬리핑 마스크 피부 보습 진정 케어 판테놀 히알루론산 세라마이드", "source": "image"}
        ],
    )
    classification = PageClassification(
        page_class="image_heavy_commerce_pdp",
        supported_for_generation=True,
        confidence=0.9,
    )

    decision = run_ocr_policy(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification, decision)

    assert decision.status == "AVAILABLE"
    assert evidence_pack["ocr_used"] is True
    assert len(evidence_pack["ocr_text_blocks"]) == 1
    assert evidence_pack["quality_warning"] is True


def test_ocr_promotes_hidden_detail_assets_even_when_html_text_is_sufficient() -> None:
    snapshot = _snapshot(
        page_class_hint="commerce_pdp",
        usable_text_chars=4800,
        image_candidates=[
            {"src": "https://cdn.example.com/product-hero.jpg", "alt": "제품 메인", "width": 1200, "height": 1200, "attribute": "src"},
            {
                "src": "https://aprilskin.com/web/upload/webp/skin/260119_centella1_03_result.webp",
                "alt": "진정 레시피",
                "attribute": "ec-data-src",
                "detail_hint": True,
            },
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.status == "SKIPPED"
    assert "detail_image_candidate" in decision.trigger_reasons
    assert "no_ocr_blocks_available" in decision.trigger_reasons
    assert decision.ranked_image_candidates[0]["src"].endswith("260119_centella1_03_result.webp")


def test_ocr_keeps_broad_candidate_sweep_for_quality_first_mode() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=900,
        image_candidates=[
            {
                "src": f"https://cdn.example.com/detail_{index:02d}.jpg",
                "alt": f"제품 상세 {index}",
                "width": 1200,
                "height": 1200,
                "attribute": "src",
            }
            for index in range(12)
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert len(decision.ranked_image_candidates) == 12


def test_ocr_marks_table_like_candidates_for_structured_pipeline() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=700,
        product_name="Shade Chart 5N 7GB",
        primary_product_tokens=["shade", "chart", "5n", "7gb"],
        image_candidates=[
            {
                "src": "https://cdn.example.com/shade-chart-5n-7gb.png",
                "alt": "shade comparison table 5N 7GB",
                "width": 1200,
                "height": 1200,
                "attribute": "src",
            }
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.ranked_image_candidates[0]["candidate_type"] == "table_like_image"
    assert decision.ranked_image_candidates[0]["ocr_pipeline_type"] == "structured_table"


def test_ocr_aggregates_image_level_metadata_from_runner_output() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=700,
        product_name="Shade Chart 5N 7GB",
        primary_product_tokens=["shade", "chart", "5n", "7gb"],
        image_candidates=[
            {
                "src": "https://cdn.example.com/shade-chart-5n-7gb.png",
                "alt": "shade comparison table 5N 7GB",
                "width": 1200,
                "height": 1200,
                "attribute": "src",
            }
        ],
        ocr_text_blocks=[
            {
                "text": "5N 7GB 8R neutral ash beige",
                "source": "image",
                "image_src": "https://cdn.example.com/shade-chart-5n-7gb.png",
                "pipeline_type": "structured_table",
                "engine_used": "PPStructureV3",
            },
            {
                "text": "12345 67890 12345 67890",
                "source": "image",
                "image_src": "https://cdn.example.com/shade-chart-5n-7gb.png",
                "pipeline_type": "structured_table",
                "engine_used": "PPStructureV3",
            },
        ],
        ocr_image_results=[
            {
                "image_src": "https://cdn.example.com/shade-chart-5n-7gb.png",
                "image_attribute": "src",
                "image_score": 1.9,
                "candidate_type": "table_like_image",
                "pipeline_type": "structured_table",
                "engine_used": "PPStructureV3",
                "raw_block_count": 2,
                "raw_char_count": 48,
                "status": "completed",
                "error": None,
            }
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.status == "AVAILABLE"
    assert decision.image_results[0]["pipeline_type"] == "structured_table"
    assert decision.image_results[0]["engine_used"] == "PPStructureV3"
    assert decision.image_results[0]["admitted_block_count"] == 1
    assert decision.image_results[0]["rejected_block_count"] == 1
    assert decision.line_groups
    assert decision.direct_fact_candidates


def test_ocr_rejects_decorative_runtime_assets_before_live_sweep() -> None:
    snapshot = _snapshot(
        page_class_hint="commerce_pdp",
        usable_text_chars=4800,
        image_candidates=[
            {"src": "https://aprilskin.com/web/upload/images/ico_10000.png", "alt": "", "height": 30, "detail_hint": True},
            {"src": "https://aprilskin.com/web/upload/images/header_scope_renew.svg", "alt": "", "detail_hint": True},
            {"src": "https://aprilskin.com/web/upload/images/251111_gift_40000won.png", "alt": "", "detail_hint": True},
            {"src": "https://img.echosting.cafe24.com/design/skin/mono/product/btn_basketDown.gif", "alt": ""},
            {"src": "https://aprilskin.com/product/'+stickImgSrc+'", "alt": ""},
            {
                "src": "https://aprilskin.com/web/product/extra/big/202601/6da5ab56bdeb115fd38c54a36ff61760.png",
                "alt": "calming serum detail",
                "width": 1200,
                "height": 1200,
                "attribute": "src",
            },
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert [candidate["src"] for candidate in decision.ranked_image_candidates] == [
        "https://aprilskin.com/web/product/extra/big/202601/6da5ab56bdeb115fd38c54a36ff61760.png"
    ]


def test_ocr_preserves_short_detail_lines_for_downstream_filtering() -> None:
    snapshot = _snapshot(
        page_class_hint="commerce_pdp",
        usable_text_chars=4800,
        product_name="APRILSKIN Mugwort Centella Calming Serum",
        primary_product_tokens=["aprilskin", "mugwort", "centella", "calming", "serum"],
        image_candidates=[
            {
                "src": "https://aprilskin.com/web/product/extra/big/202601/6da5ab56bdeb115fd38c54a36ff61760.png",
                "alt": "calming serum detail",
                "width": 1200,
                "height": 1200,
                "attribute": "src",
            }
        ],
        ocr_text_blocks=[
            {
                "text": "MUGWORT",
                "source": "image",
                "image_src": "https://aprilskin.com/web/product/extra/big/202601/6da5ab56bdeb115fd38c54a36ff61760.png",
            },
            {
                "text": "CALMING SERUM",
                "source": "image",
                "image_src": "https://aprilskin.com/web/product/extra/big/202601/6da5ab56bdeb115fd38c54a36ff61760.png",
            },
            {
                "text": "Niacinamide",
                "source": "image",
                "image_src": "https://aprilskin.com/web/product/extra/big/202601/6da5ab56bdeb115fd38c54a36ff61760.png",
            },
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.status == "AVAILABLE"
    assert [block["text"] for block in decision.admitted_blocks] == [
        "CALMING SERUM",
        "MUGWORT",
        "Niacinamide",
    ]
    assert decision.direct_fact_candidates


def test_ocr_marks_long_detail_banners_for_tiling() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=600,
        image_candidates=[
            {
                "src": "https://cdn.example.com/long-detail-banner.jpg",
                "alt": "product detail banner ingredient guide",
                "width": 900,
                "height": 3200,
                "attribute": "src",
                "detail_hint": True,
            }
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.ranked_image_candidates[0]["candidate_type"] == "long_detail_banner"
    assert decision.ranked_image_candidates[0]["needs_tiling"] is True


def test_ocr_promotes_explicit_product_field_lines_without_name_overlap() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=400,
        product_name="Kgen Korean Product Labels 1005 11",
        primary_product_tokens=["kgen", "1005", "11"],
        image_candidates=[
            {
                "src": "https://cdn.example.com/korean-label.jpg",
                "alt": "product package label",
                "width": 1536,
                "height": 2048,
                "detail_hint": True,
            }
        ],
        ocr_text_blocks=[
            {
                "text": "제품명: 공룡 티링이 키링 가격: 8000원",
                "source": "image",
                "image_src": "https://cdn.example.com/korean-label.jpg",
                "candidate_type": "general_detail_image",
            }
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.status == "AVAILABLE"
    assert decision.admitted_blocks[0]["same_product_score"] >= 0.28
    assert decision.direct_fact_candidates


def test_ocr_line_group_can_promote_explicit_field_cluster_to_direct_candidate() -> None:
    snapshot = _snapshot(
        page_class_hint="image_heavy_commerce_pdp",
        usable_text_chars=400,
        product_name="Kgen Korean Product Labels 1005 11",
        primary_product_tokens=["kgen", "1005", "11"],
        image_candidates=[
            {
                "src": "https://cdn.example.com/korean-label.jpg",
                "alt": "product package label",
                "width": 1536,
                "height": 2048,
                "detail_hint": True,
            }
        ],
        ocr_text_blocks=[
            {
                "text": "제품명: 공룡 티링이 키링",
                "source": "image",
                "image_src": "https://cdn.example.com/korean-label.jpg",
                "candidate_type": "general_detail_image",
            },
            {
                "text": "재질:아크릴,금속",
                "source": "image",
                "image_src": "https://cdn.example.com/korean-label.jpg",
                "candidate_type": "general_detail_image",
            },
            {
                "text": "가격:8000원",
                "source": "image",
                "image_src": "https://cdn.example.com/korean-label.jpg",
                "candidate_type": "general_detail_image",
            },
        ],
    )

    decision = run_ocr_policy(snapshot)

    assert decision.line_groups
    assert decision.line_groups[0]["direct_evidence_eligible"] is True
    assert decision.direct_fact_candidates
