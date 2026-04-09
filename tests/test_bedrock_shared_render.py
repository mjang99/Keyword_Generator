from __future__ import annotations

from src.keyword_generation.bedrock_adapter import (
    build_keyword_generation_prompt,
    parse_intent_response,
    parse_keyword_response,
)
from src.keyword_generation.models import GenerationRequest


def _request(platform: str = "both") -> GenerationRequest:
    return GenerationRequest(
        evidence_pack={
            "raw_url": "https://example.com/apple-pencil",
            "canonical_url": "https://example.com/apple-pencil",
            "page_class": "commerce_pdp",
            "product_name": "Apple Pencil",
            "canonical_product_name": "Apple Pencil",
            "locale_detected": "ko",
            "market_locale": "ko_KR",
            "sellability_state": "sellable",
            "stock_state": "InStock",
            "sufficiency_state": "sufficient",
            "quality_warning": False,
            "facts": [
                {
                    "fact_id": "f001",
                    "type": "brand",
                    "value": "Apple",
                    "normalized_value": "Apple",
                    "source": "title",
                    "source_uri": "https://example.com/apple-pencil",
                    "page_scope": "exact",
                    "evidence_tier": "direct",
                    "admissibility_tags": ["product_identity"],
                    "confidence": 0.99,
                }
            ],
        },
        requested_platform_mode=platform,
    )


def test_generation_prompt_describes_shared_render_default() -> None:
    prompt = build_keyword_generation_prompt(_request("both"), positive_target=100)

    assert "shared_render_default" in prompt
    assert "slot_plan" in prompt
    assert '"items"' in prompt
    assert "legacy_intents_supported" in prompt
    assert "legacy_rows_supported" in prompt


def test_parse_intent_response_hydrates_both_platform_renders_from_shared_render() -> None:
    intents = parse_intent_response(
        '{"intents":[{"category":"brand","slot_type":"product_name","intent_text":"apple pencil","reason":"direct fact","evidence_tier":"direct","allowed_platforms":["naver_sa","google_sa"],"shared_render":{"keyword":"apple pencil","admitted":true}}]}',
        request=_request("both"),
    )

    assert len(intents) == 1
    assert intents[0].shared_render is not None
    assert intents[0].slot_type == "product_name"
    assert intents[0].naver_render is not None
    assert intents[0].google_render is not None
    assert intents[0].naver_render.keyword == "apple pencil"
    assert intents[0].google_render.keyword == "apple pencil"
    assert intents[0].naver_render.match_label == "완전일치"
    assert intents[0].google_render.match_label == "exact"


def test_parse_keyword_response_merges_shared_render_into_dual_platform_row() -> None:
    rows = parse_keyword_response(
        '{"intents":[{"category":"purchase_intent","slot_type":"navigational_alias","intent_text":"apple pencil","reason":"direct fact","evidence_tier":"direct","allowed_platforms":["naver_sa","google_sa"],"shared_render":{"keyword":"apple pencil","admitted":true}}]}',
        request=_request("both"),
    )

    assert len(rows) == 1
    assert rows[0].keyword == "apple pencil"
    assert rows[0].slot_type == "navigational_alias"
    assert rows[0].naver_match == "완전일치"
    assert rows[0].google_match == "phrase"
