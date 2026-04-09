from __future__ import annotations

from src.keyword_generation import GenerationRequest, generate_keywords


def test_combined_skin_type_is_not_split_into_canonical_singles() -> None:
    evidence = {
        "raw_url": "https://example.com/mask",
        "canonical_url": "https://example.com/mask",
        "page_class": "commerce_pdp",
        "product_name": "테스트 마스크",
        "canonical_product_name": "테스트 마스크",
        "facts": [
            {
                "type": "brand",
                "value": "테스트",
                "normalized_value": "테스트",
                "source": "structured_data.brand",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_name",
                "value": "테스트 마스크",
                "normalized_value": "테스트 마스크",
                "source": "structured_data.name",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "skin_type",
                "value": "건성 복합성 피부",
                "normalized_value": "건성 복합성 피부",
                "source": "decoded_text",
                "evidence_tier": "direct",
                "admissibility_tags": ["attribute", "audience"],
            },
        ],
    }

    result = generate_keywords(
        GenerationRequest(evidence_pack=evidence, requested_platform_mode="naver_sa")
    )
    keywords = {row.keyword for row in result.rows}

    assert "건성 복합성 피부 마스크" not in keywords
    assert "건성 피부 마스크" not in keywords
    assert "복합성 피부 마스크" not in keywords


def test_audience_abbreviation_is_not_expanded_with_skin_suffix() -> None:
    evidence = {
        "raw_url": "https://example.com/serum",
        "canonical_url": "https://example.com/serum",
        "page_class": "commerce_pdp",
        "product_name": "테스트 세럼",
        "canonical_product_name": "테스트 세럼",
        "facts": [
            {
                "type": "brand",
                "value": "테스트",
                "normalized_value": "테스트",
                "source": "structured_data.brand",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_name",
                "value": "테스트 세럼",
                "normalized_value": "테스트 세럼",
                "source": "structured_data.name",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "audience",
                "value": "민감",
                "normalized_value": "민감",
                "source": "decoded_text",
                "evidence_tier": "direct",
                "admissibility_tags": ["audience"],
            },
        ],
    }

    result = generate_keywords(
        GenerationRequest(evidence_pack=evidence, requested_platform_mode="naver_sa")
    )
    keywords = {row.keyword for row in result.rows}

    assert not any("민감 피부" in keyword for keyword in keywords)


def test_usage_context_is_not_expanded_into_category_surface() -> None:
    evidence = {
        "raw_url": "https://example.com/cream",
        "canonical_url": "https://example.com/cream",
        "page_class": "commerce_pdp",
        "product_name": "테스트 크림",
        "canonical_product_name": "테스트 크림",
        "facts": [
            {
                "type": "brand",
                "value": "테스트",
                "normalized_value": "테스트",
                "source": "structured_data.brand",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_name",
                "value": "테스트 크림",
                "normalized_value": "테스트 크림",
                "source": "structured_data.name",
                "evidence_tier": "direct",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "use_case",
                "value": "취침 전",
                "normalized_value": "취침 전",
                "source": "decoded_text",
                "evidence_tier": "direct",
                "admissibility_tags": ["use_case"],
            },
        ],
    }

    result = generate_keywords(
        GenerationRequest(evidence_pack=evidence, requested_platform_mode="naver_sa")
    )
    keywords = {row.keyword for row in result.rows}

    assert "취침 전 크림" not in keywords
    assert "취침 전 테스트 크림" not in keywords
