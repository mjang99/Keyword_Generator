from __future__ import annotations

from src.keyword_generation.bedrock_adapter import (
    build_dedup_quality_prompt,
    build_keyword_generation_prompt,
    build_supplementation_prompt,
    generate_rows_via_bedrock,
    parse_intent_response,
    parse_keyword_response,
    run_dedup_quality_pass,
    run_supplementation_pass,
)
from src.keyword_generation.constants import POSITIVE_CATEGORY_TARGETS
from src.keyword_generation.models import CanonicalIntent, DedupQualityReport, GenerationRequest, PlatformRender
from src.keyword_generation.service import generate_keywords


def _request() -> GenerationRequest:
    return GenerationRequest(
        evidence_pack={
            "raw_url": "https://example.com/laneige",
            "canonical_url": "https://example.com/laneige",
            "page_class": "commerce_pdp",
            "product_name": "라네즈 워터 슬리핑 마스크",
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
                    "value": "라네즈",
                    "normalized_value": "라네즈",
                    "source": "title",
                    "source_uri": "https://example.com/laneige",
                    "page_scope": "exact",
                    "evidence_tier": "direct",
                    "admissibility_tags": ["product_identity"],
                    "confidence": 0.99,
                }
            ],
        },
        requested_platform_mode="naver_sa",
    )


def test_build_keyword_generation_prompt_contains_locked_fields() -> None:
    prompt = build_keyword_generation_prompt(_request(), positive_target=100)

    assert "generation_instructions=" in prompt
    assert "evidence_pack=" in prompt
    assert "라네즈 워터 슬리핑 마스크" in prompt
    assert "quality_warning" in prompt


def test_parse_keyword_response_returns_keyword_rows() -> None:
    rows = parse_keyword_response(
        '{"rows":[{"category":"brand","keyword":"라네즈 워터 슬리핑 마스크","reason":"direct fact","evidence_tier":"direct","naver_match":"완전일치"}]}',
        request=_request(),
    )

    assert len(rows) == 1
    assert rows[0].category == "brand"
    assert rows[0].keyword == "라네즈 워터 슬리핑 마스크"
    assert rows[0].naver_match == "완전일치"


def test_generate_rows_via_bedrock_uses_fake_client() -> None:
    class FakeClient:
        def converse(self, *, modelId, **kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": '{"rows":[{"category":"brand","keyword":"라네즈 워터 슬리핑 마스크","reason":"direct fact","evidence_tier":"direct","naver_match":"완전일치"}]}'
                            }
                        ]
                    }
                }
            }

    rows = generate_rows_via_bedrock(_request(), positive_target=100, client=FakeClient())

    assert len(rows) == 1
    assert rows[0].keyword == "라네즈 워터 슬리핑 마스크"


def test_generate_keywords_falls_back_when_bedrock_rows_are_invalid(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")
    monkeypatch.setattr(
        "src.keyword_generation.service.generate_intents_via_bedrock",
        lambda request, positive_target: [],
    )

    result = generate_keywords(_request())

    assert result.status == "COMPLETED"
    assert result.validation_report is not None
    assert result.validation_report.positive_keyword_counts["naver_sa"] >= 100


def _sample_intent(keyword: str = "라네즈 워터 슬리핑 마스크", category: str = "brand") -> CanonicalIntent:
    return CanonicalIntent(
        category=category,
        intent_text=keyword,
        reason="direct fact",
        evidence_tier="direct",
        allowed_platforms=["naver_sa"],
        naver_render=PlatformRender(keyword=keyword, match_label="완전일치"),
        google_render=None,
    )


def test_build_dedup_quality_prompt_contains_required_fields() -> None:
    candidates = [_sample_intent()]
    prompt = build_dedup_quality_prompt(
        candidates,
        platform_mode="naver_sa",
        positive_floor=100,
        positive_category_targets=POSITIVE_CATEGORY_TARGETS,
    )

    assert "dedup_quality_instructions=" in prompt
    assert "candidates=" in prompt
    assert "라네즈 워터 슬리핑 마스크" in prompt
    assert "dedup_rules" in prompt
    assert "quality_rules" in prompt
    assert "gap_report" in prompt


def test_build_supplementation_prompt_contains_gap_and_evidence() -> None:
    gap_report = {"brand": 3, "long_tail": 5, "_total": 8}
    evidence_pack = {
        "raw_url": "https://example.com/laneige",
        "product_name": "라네즈 워터 슬리핑 마스크",
        "page_class": "commerce_pdp",
    }
    surviving = [{"intent_text": "라네즈 워터 슬리핑 마스크", "category": "brand"}]
    prompt = build_supplementation_prompt(
        gap_report,
        evidence_pack,
        platform_mode="naver_sa",
        surviving_summary=surviving,
    )

    assert "supplementation_instructions=" in prompt
    assert "gap_categories" in prompt
    assert "total_missing" in prompt
    assert "already_surviving_sample" in prompt
    assert "라네즈 워터 슬리핑 마스크" in prompt


def test_run_dedup_quality_pass_returns_report_with_fake_client() -> None:
    class FakeClient:
        def converse(self, *, modelId, **kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"surviving":[{"intent_text":"라네즈 워터 슬리핑 마스크",'
                                    '"category":"brand","evidence_tier":"direct",'
                                    '"quality_score":"high","quality_reason":"exact brand name","keep":true}],'
                                    '"dropped_duplicates":[],"dropped_low_quality":[],'
                                    '"gap_report":{"_total":0}}'
                                )
                            }
                        ]
                    }
                }
            }

    candidates = [_sample_intent()]
    report = run_dedup_quality_pass(
        candidates,
        request=_request(),
        platform="naver_sa",
        positive_floor=100,
        positive_category_targets=POSITIVE_CATEGORY_TARGETS,
        client=FakeClient(),
    )

    assert isinstance(report, DedupQualityReport)
    assert report.platform == "naver_sa"
    assert len(report.surviving_keywords) == 1
    assert report.gap_report.get("_total", 0) == 0


def test_run_supplementation_pass_returns_intents_with_fake_client() -> None:
    class FakeClient:
        def converse(self, *, modelId, **kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"intents":[{"category":"brand","intent_text":"라네즈 슬리핑 마스크 추천",'
                                    '"reason":"gap fill","evidence_tier":"inferred",'
                                    '"allowed_platforms":["naver_sa"],'
                                    '"naver_render":{"keyword":"라네즈 슬리핑 마스크 추천","match_label":"완전일치","admitted":true},'
                                    '"google_render":null}]}'
                                )
                            }
                        ]
                    }
                }
            }

    gap_report = {"brand": 2, "_total": 2}
    intents = run_supplementation_pass(
        gap_report,
        request=_request(),
        platform="naver_sa",
        surviving_summary=[{"intent_text": "라네즈 워터 슬리핑 마스크", "category": "brand"}],
        client=FakeClient(),
    )

    assert len(intents) == 1
    assert intents[0].intent_text == "라네즈 슬리핑 마스크 추천"


def test_parse_intent_response_accepts_canonical_intents() -> None:
    intents = parse_intent_response(
        '{"intents":[{"category":"brand","intent_text":"example product","reason":"direct fact","evidence_tier":"direct","allowed_platforms":["naver_sa","google_sa"],"naver_render":{"keyword":"example product","match_label":"?꾩쟾?쇱튂","admitted":true},"google_render":{"keyword":"example product","match_label":"exact","admitted":true}}]}',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].naver_render is not None
    assert intents[0].google_render is not None
