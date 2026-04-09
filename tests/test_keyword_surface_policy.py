from __future__ import annotations

from src.keyword_generation.models import KeywordRow
from src.keyword_generation.service import _surface_cleanup_rows


def _commerce_evidence(*, extra_facts: list[dict] | None = None) -> dict:
    facts = [
        {
            "type": "brand",
            "value": "Apple",
            "normalized_value": "Apple",
            "evidence_tier": "direct",
            "admissibility_tags": ["product_identity"],
        },
        {
            "type": "product_category",
            "value": "태블릿 펜",
            "normalized_value": "태블릿 펜",
            "evidence_tier": "direct",
        },
        {
            "type": "price",
            "value": "149,000",
            "normalized_value": "149,000",
            "evidence_tier": "direct",
        },
    ]
    facts.extend(extra_facts or [])
    return {
        "raw_url": "https://example.com/apple-pencil",
        "canonical_url": "https://example.com/apple-pencil",
        "page_class": "commerce_pdp",
        "product_name": "Apple Pencil",
        "canonical_product_name": "Apple Pencil",
        "sellability_state": "sellable",
        "facts": facts,
    }


def test_surface_cleanup_drops_informational_event_and_raw_price_surfaces() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="long_tail",
            keyword="Apple Pencil 충전방법",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="long_tail",
            keyword="Apple Pencil 그림용",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="season_event",
            keyword="블랙프라이데이 태블릿 펜",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="benefit_price",
            keyword="Apple Pencil 149000",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="benefit_price",
            keyword="10만원대 태블릿 펜",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="purchase_intent",
            keyword="Apple Pencil 1",
            naver_match="완전일치",
            google_match="exact",
        ),
    ]

    cleaned = _surface_cleanup_rows(rows, evidence_pack=_commerce_evidence())
    cleaned_keywords = {row.keyword for row in cleaned}

    assert "Apple Pencil 충전방법" not in cleaned_keywords
    assert "Apple Pencil 그림용" not in cleaned_keywords
    assert "블랙프라이데이 태블릿 펜" not in cleaned_keywords
    assert "Apple Pencil 149000" not in cleaned_keywords
    assert "10만원대 태블릿 펜" in cleaned_keywords
    assert "Apple Pencil 1" in cleaned_keywords


def test_surface_cleanup_allows_grounded_promo_event_surface() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="season_event",
            keyword="블랙프라이데이 태블릿 펜",
            naver_match="확장소재",
            google_match="phrase",
        )
    ]

    evidence_pack = _commerce_evidence(
        extra_facts=[
            {
                "type": "attribute",
                "value": "블랙프라이데이 한정 혜택",
                "normalized_value": "블랙프라이데이 한정 혜택",
                "evidence_tier": "direct",
            }
        ]
    )

    cleaned = _surface_cleanup_rows(rows, evidence_pack=evidence_pack)

    assert [row.keyword for row in cleaned] == ["블랙프라이데이 태블릿 펜"]
