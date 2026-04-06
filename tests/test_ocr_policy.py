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
