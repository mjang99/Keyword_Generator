from __future__ import annotations

from src.keyword_generation.bedrock_adapter import (
    BedrockResponseParseError,
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
                },
                {
                    "fact_id": "f002",
                    "type": "product_category",
                    "value": "stylus pen",
                    "normalized_value": "stylus pen",
                    "source": "title",
                    "source_uri": "https://example.com/apple-pencil",
                    "page_scope": "exact",
                    "evidence_tier": "direct",
                    "admissibility_tags": ["product_identity"],
                    "confidence": 0.95,
                },
            ],
        },
        requested_platform_mode="naver_sa",
    )


def test_build_keyword_generation_prompt_contains_locked_fields() -> None:
    prompt = build_keyword_generation_prompt(_request(), positive_target=100)

    assert "generation_instructions=" in prompt
    assert "evidence_pack=" in prompt
    assert "interpretation" in prompt
    assert "canonical_category" in prompt
    assert "comparison_policy" in prompt
    assert "competitor_brand_hints" in prompt
    assert "require_competitor_brand" in prompt
    assert "required_positive_categories" in prompt
    assert "negative_category_required" in prompt
    assert "positive_category_targets" in prompt
    assert "slot_plan" in prompt
    assert '"items"' in prompt
    assert '"keyword"' in prompt
    assert "quality_warning" in prompt
    assert "buyer_query_contract" in prompt
    assert "real buyer of this exact product page would plausibly search" in prompt
    assert "generic_category_contract" in prompt
    assert "common shopper-facing product-class phrases" in prompt
    assert "Do not turn storage, convenience, or preservation language into outing, travel, picnic, camping" in prompt


def test_build_keyword_generation_prompt_includes_weak_category_examples_when_grounded() -> None:
    request = GenerationRequest(
        evidence_pack={
            "raw_url": "https://example.com/retinol-serum",
            "canonical_url": "https://example.com/retinol-serum",
            "page_class": "commerce_pdp",
            "product_name": "Retinol Serum",
            "canonical_product_name": "Retinol Serum",
            "facts": [
                {"type": "brand", "value": "Acme", "normalized_value": "Acme", "evidence_tier": "direct", "admissibility_tags": ["product_identity"]},
                {"type": "product_category", "value": "retinol serum", "normalized_value": "retinol serum", "evidence_tier": "direct"},
                {"type": "concern", "value": "wrinkle care", "normalized_value": "wrinkle care", "evidence_tier": "direct", "admissibility_tags": ["problem_solution"]},
                {"type": "use_case", "value": "night routine", "normalized_value": "night routine", "evidence_tier": "direct", "admissibility_tags": ["use_case"]},
            ],
        },
        requested_platform_mode="naver_sa",
    )

    prompt = build_keyword_generation_prompt(
        request,
        positive_target=20,
        target_categories=["long_tail", "season_event", "problem_solution"],
    )

    assert "category_examples" in prompt
    assert "night routine 레티놀 세럼" in prompt
    assert "wrinkle care 레티놀 세럼" in prompt
    assert "Retinol Serum 관리" in prompt


def test_parse_keyword_response_returns_keyword_rows() -> None:
    rows = parse_keyword_response(
        '{"rows":[{"category":"brand","slot_type":"product_name","keyword":"Apple Pencil","reason":"direct fact","evidence_tier":"direct","naver_match":"?꾩쟾?쇱튂"}]}',
        request=_request(),
    )

    assert len(rows) == 1
    assert rows[0].category == "brand"
    assert rows[0].slot_type == "product_name"
    assert rows[0].keyword == "Apple Pencil"
    assert rows[0].naver_match == "?꾩쟾?쇱튂"


def test_generate_rows_via_bedrock_uses_fake_client() -> None:
    class FakeClient:
        def converse(self, *, modelId, **kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {"text": '{"items":[{"category":"brand","keyword":"Apple Pencil"}]}'}
                        ]
                    }
                }
            }

    rows = generate_rows_via_bedrock(_request(), positive_target=100, client=FakeClient())

    assert len(rows) == 1
    assert rows[0].slot_type == "product_name"
    assert rows[0].keyword == "Apple Pencil"
    assert rows[0].reason


def test_generate_keywords_returns_failure_when_bedrock_pipeline_errors(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")
    monkeypatch.setattr(
        "src.keyword_generation.service.generate_intents_via_bedrock",
        lambda request, positive_target, positive_category_targets=None, **kwargs: (_ for _ in ()).throw(RuntimeError("bedrock down")),
    )

    result = generate_keywords(_request())

    assert result.status == "FAILED_GENERATION"
    assert result.validation_report is not None
    assert result.validation_report.failure_code == "generation_rule_violation"
    assert "bedrock_pipeline_error" in (result.validation_report.failure_detail or "")


def test_generate_keywords_preserves_bedrock_parse_failure_debug(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    def raise_parse_error(request, positive_target, positive_category_targets=None, **kwargs):
        del request, positive_target, positive_category_targets, kwargs
        raise BedrockResponseParseError(
            stage="generation",
            message="Bedrock response must include items[] or intents[] or rows[]",
            model_id="fake-model",
            response_text='{"oops":"shape"}',
            metadata={"stop_reason": "end_turn", "usage": {"outputTokens": 12}},
        )

    monkeypatch.setattr("src.keyword_generation.service.generate_intents_via_bedrock", raise_parse_error)

    result = generate_keywords(_request())

    assert result.status == "FAILED_GENERATION"
    assert result.validation_report is not None
    assert result.validation_report.failure_code == "generation_rule_violation"
    assert result.debug_payload["generation"]["error"]["stage"] == "generation"
    assert result.debug_payload["generation"]["error"]["model_id"] == "fake-model"
    assert result.debug_payload["generation"]["error"]["response_text"] == '{"oops":"shape"}'


def _sample_intent(keyword: str = "Apple Pencil", category: str = "brand") -> CanonicalIntent:
    return CanonicalIntent(
        category=category,
        slot_type="product_name",
        intent_text=keyword,
        reason="direct fact",
        evidence_tier="direct",
        allowed_platforms=["naver_sa"],
        naver_render=PlatformRender(keyword=keyword, match_label="?꾩쟾?쇱튂"),
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
    assert "Apple Pencil" in prompt
    assert "dedup_rules" in prompt
    assert "quality_rules" in prompt
    assert "slot_gap_report" in prompt
    assert "required_positive_categories" in prompt
    assert "negative_category_required" in prompt


def test_build_supplementation_prompt_contains_gap_and_evidence() -> None:
    gap_slots = {"brand:product_name": 3, "long_tail:use_case_phrase": 5, "_total": 8}
    evidence_pack = {
        "raw_url": "https://example.com/apple-pencil",
        "product_name": "Apple Pencil",
        "page_class": "commerce_pdp",
    }
    surviving = [{"intent_text": "Apple Pencil", "category": "brand", "slot_type": "product_name"}]
    prompt = build_supplementation_prompt(
        gap_slots,
        evidence_pack,
        platform_mode="naver_sa",
        surviving_summary=surviving,
    )

    assert "supplementation_instructions=" in prompt
    assert "gap_slots" in prompt
    assert "total_missing_slots" in prompt
    assert "slot_plan" in prompt
    assert "expansion_axes" in prompt
    assert "already_overused_terms" in prompt
    assert "surface_cleanup_policy" in prompt
    assert "interpretation" in prompt
    assert "canonical_category" in prompt
    assert "supplementation_prohibitions" in prompt
    assert "already_surviving_sample" in prompt
    assert "Apple Pencil" in prompt


def test_build_supplementation_prompt_includes_overused_terms_hint() -> None:
    gap_slots = {"long_tail:use_case_phrase": 4, "_total": 4}
    evidence_pack = {
        "raw_url": "https://example.com/laneige",
        "product_name": "Laneige Cream Skin",
        "canonical_product_name": "Laneige Cream Skin",
        "facts": [
            {
                "type": "brand",
                "value": "Laneige",
                "normalized_value": "Laneige",
                "admissibility_tags": ["product_identity"],
            }
        ],
    }
    surviving = [
        {"intent_text": "cream skin hydration toner", "category": "feature_attribute", "slot_type": "core_attribute"},
        {"intent_text": "cream skin hydration serum", "category": "feature_attribute", "slot_type": "core_attribute"},
        {"intent_text": "cream skin hydration routine", "category": "long_tail", "slot_type": "use_case_phrase"},
    ]

    prompt = build_supplementation_prompt(
        gap_slots,
        evidence_pack,
        platform_mode="google_sa",
        surviving_summary=surviving,
    )

    assert "already_overused_terms" in prompt
    assert "hydration" in prompt


def test_build_supplementation_prompt_includes_category_examples_for_gap_slots() -> None:
    gap_slots = {"competitor_comparison:competitor_brand_type": 3, "problem_solution:problem_noun_phrase": 2, "_total": 5}
    evidence_pack = {
        "raw_url": "https://example.com/retinol-serum",
        "canonical_url": "https://example.com/retinol-serum",
        "page_class": "commerce_pdp",
        "product_name": "Retinol Serum",
        "canonical_product_name": "Retinol Serum",
        "facts": [
            {"type": "brand", "value": "Acme", "normalized_value": "Acme", "evidence_tier": "direct", "admissibility_tags": ["product_identity"]},
            {"type": "product_category", "value": "retinol serum", "normalized_value": "retinol serum", "evidence_tier": "direct"},
            {"type": "concern", "value": "wrinkle care", "normalized_value": "wrinkle care", "evidence_tier": "direct", "admissibility_tags": ["problem_solution"]},
        ],
    }

    prompt = build_supplementation_prompt(
        gap_slots,
        evidence_pack,
        platform_mode="naver_sa",
        surviving_summary=[],
    )

    assert "category_examples" in prompt
    assert "wrinkle care 레티놀 세럼" in prompt
    assert "Retinol Serum 관리" in prompt


def test_run_dedup_quality_pass_returns_report_with_fake_client() -> None:
    class FakeClient:
        def converse(self, *, modelId, **kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"surviving":[{"intent_id":"brand-1","keyword":"Apple Pencil","category":"brand","quality_score":"high","quality_reason":"exact brand name","keep":true}],'
                                    '"dropped_duplicates":[],"dropped_low_quality":[],"slot_gap_report":{"_total":0}}'
                                )
                            }
                        ]
                    }
                }
            }

    candidates = [
        CanonicalIntent(
            category="brand",
            slot_type="product_name",
            intent_text="Apple Pencil",
            intent_id="brand-1",
            reason="direct fact",
            evidence_tier="direct",
            allowed_platforms=["naver_sa"],
            naver_render=PlatformRender(keyword="Apple Pencil", match_label="?꾩쟾?쇱튂"),
        )
    ]
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
                            {"text": '{"items":[{"category":"brand","keyword":"Apple Pencil Pro"}]}'}
                        ]
                    }
                }
            }

    gap_slots = {"brand:product_name": 2, "_total": 2}
    intents = run_supplementation_pass(
        gap_slots,
        request=_request(),
        platform="naver_sa",
        surviving_summary=[{"intent_text": "Apple Pencil", "category": "brand", "slot_type": "product_name"}],
        client=FakeClient(),
    )

    assert len(intents) == 1
    assert intents[0].intent_text == "Apple Pencil Pro"
    assert intents[0].slot_type == "product_name"
    assert intents[0].reason == ""


def test_parse_intent_response_accepts_canonical_intents() -> None:
    intents = parse_intent_response(
        '{"intents":[{"category":"brand","slot_type":"product_name","intent_text":"example product","reason":"direct fact","evidence_tier":"direct","allowed_platforms":["naver_sa","google_sa"],"naver_render":{"keyword":"example product","match_label":"?꾩쟾?쇱튂","admitted":true},"google_render":{"keyword":"example product","match_label":"exact","admitted":true}}]}',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].slot_type == "product_name"
    assert intents[0].naver_render is not None
    assert intents[0].google_render is not None


def test_parse_intent_response_defaults_slot_type_for_legacy_rows() -> None:
    intents = parse_intent_response(
        '{"rows":[{"category":"brand","keyword":"Apple Pencil","reason":"direct fact","evidence_tier":"direct","naver_match":"exact"}]}',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].category == "brand"
    assert intents[0].slot_type == "product_name"


def test_parse_intent_response_accepts_lightweight_items() -> None:
    intents = parse_intent_response(
        '{"items":[{"category":"feature_attribute","keyword":"Apple Pencil 1?몃?"}]}',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].category == "feature_attribute"
    assert intents[0].slot_type == "spec"
    assert intents[0].intent_text == "Apple Pencil 1?몃?"


def test_parse_intent_response_unwraps_fenced_wrapper_payload() -> None:
    intents = parse_intent_response(
        '```json\n{"result":{"items":[{"category":"brand","keyword":"Apple Pencil"}]}}\n```',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].category == "brand"
    assert intents[0].intent_text == "Apple Pencil"


def test_parse_intent_response_accepts_lightweight_keywords_array() -> None:
    intents = parse_intent_response(
        '{"keywords":[{"category":"purchase_intent","keyword":"Apple Pencil 1"}]}',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].category == "purchase_intent"
    assert intents[0].slot_type == "navigational_alias"
    assert intents[0].intent_text == "Apple Pencil 1"


def test_parse_intent_response_unwraps_nested_keywords_payload() -> None:
    intents = parse_intent_response(
        '{"result":{"keywords":[{"category":"brand","keyword":"Apple Pencil"}]}}',
        request=_request(),
    )

    assert len(intents) == 1
    assert intents[0].category == "brand"
    assert intents[0].intent_text == "Apple Pencil"

