from __future__ import annotations

from src.keyword_generation.constants import NEGATIVE_CATEGORY
from src.keyword_generation.bedrock_adapter import BedrockResponseParseError
from src.keyword_generation.models import (
    CanonicalIntent,
    DedupQualityReport,
    GenerationRequest,
    PlatformRender,
    ValidationReport,
)
from src.keyword_generation.service import _generation_batch_plans, generate_keywords


def _request() -> GenerationRequest:
    return GenerationRequest(
        evidence_pack={
            "raw_url": "https://example.com/apple-pencil",
            "canonical_url": "https://example.com/apple-pencil",
            "page_class": "commerce_pdp",
            "product_name": "Apple Pencil",
            "canonical_product_name": "Apple Pencil",
            "quality_warning": False,
            "facts": [
                {
                    "type": "brand",
                    "value": "Apple",
                    "normalized_value": "Apple",
                    "evidence_tier": "direct",
                    "admissibility_tags": ["product_identity"],
                },
                {
                    "type": "product_category",
                    "value": "stylus pen",
                    "normalized_value": "stylus pen",
                    "evidence_tier": "direct",
                },
                {
                    "type": "concern",
                    "value": "precision writing",
                    "normalized_value": "precision writing",
                    "evidence_tier": "direct",
                },
                {
                    "type": "usage",
                    "value": "note taking",
                    "normalized_value": "note taking",
                    "evidence_tier": "direct",
                },
            ],
        },
        requested_platform_mode="naver_sa",
    )


def _intent(category: str, keyword: str, *, slot_type: str = "") -> CanonicalIntent:
    return CanonicalIntent(
        category=category,
        slot_type=slot_type,
        intent_text=keyword,
        reason="direct fact",
        evidence_tier="direct",
        allowed_platforms=["naver_sa"],
        naver_render=PlatformRender(keyword=keyword, match_label="완전일치"),
    )


def test_generation_batch_plans_use_cluster_layout() -> None:
    request = _request()
    category_plan = {
        "brand": 10,
        "generic_category": 12,
        "feature_attribute": 16,
        "competitor_comparison": 6,
        "purchase_intent": 10,
        "long_tail": 12,
        "benefit_price": 8,
        "season_event": 6,
        "problem_solution": 10,
    }
    from src.keyword_generation.service import _build_product_interpretation, _build_slot_plan

    interpretation = _build_product_interpretation(request.evidence_pack)
    slot_plan = _build_slot_plan(interpretation, category_plan=category_plan)
    batches = _generation_batch_plans(category_plan=category_plan, slot_plan=slot_plan)

    batch_names = [batch["name"] for batch in batches]
    assert batch_names == ["cluster_a", "cluster_b", "cluster_c", "cluster_d"]
    assert batches[0]["categories"] == ("brand", "generic_category", "purchase_intent")
    assert batches[1]["categories"] == ("feature_attribute", "benefit_price")
    assert batches[2]["categories"] == ("long_tail", "problem_solution", "season_event")
    assert batches[3]["categories"] == ("competitor_comparison", NEGATIVE_CATEGORY)


def test_generate_keywords_uses_cluster_generation_and_splits_weak_clusters(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")
    call_log: list[tuple[str, tuple[str, ...]]] = []

    def fake_generate_intents(
        request,
        *,
        positive_target,
        positive_category_targets=None,
        interpretation_payload=None,
        slot_plan=None,
        target_categories=None,
        batch_name=None,
        client=None,
        settings=None,
        return_metadata=False,
    ):
        del request, positive_target, positive_category_targets, interpretation_payload, slot_plan, client, settings
        categories = tuple(target_categories or ())
        name = str(batch_name or "default")
        call_log.append((name, categories))
        if name == "cluster_c":
            intents = [_intent("long_tail", "Apple Pencil note taking", slot_type="use_case_phrase")]
        elif name == "cluster_c_split_1":
            intents = [
                _intent("long_tail", "Apple Pencil precision writing", slot_type="use_case_phrase"),
                _intent("problem_solution", "precision writing stylus pen", slot_type="problem_noun_phrase"),
            ]
        elif name == "cluster_c_split_2":
            intents = [_intent("season_event", "학생 필기 stylus pen", slot_type="seasonal_context")]
        else:
            intents = []
            for category in categories:
                if category == NEGATIVE_CATEGORY:
                    intents.append(_intent(NEGATIVE_CATEGORY, "Apple Pencil manual", slot_type="negative_exclusion"))
                else:
                    intents.append(_intent(category, f"{category} keyword", slot_type="product_name"))
        metadata = {"model_id": "fake", "response_text": '{"items":[]}', "usage": {}, "stop_reason": "end_turn"}
        if return_metadata:
            return intents, metadata
        return intents

    def fake_dedup(candidates, **kwargs):
        del kwargs
        return DedupQualityReport(platform="naver_sa", surviving_keywords=candidates, slot_gap_report={"_total": 0})

    def fake_supplement(*args, **kwargs):
        del args, kwargs
        return []

    def fake_validate(rows, **kwargs):
        del kwargs
        return ValidationReport(
            status="COMPLETED",
            requested_platform_mode="naver_sa",
            positive_keyword_counts={"naver_sa": len([row for row in rows if row.category != NEGATIVE_CATEGORY])},
            category_counts={"naver_sa": {}},
            weak_tier_ratio_by_platform={"naver_sa": 0.0},
            quality_warning=False,
        )

    monkeypatch.setattr("src.keyword_generation.service.generate_intents_via_bedrock", fake_generate_intents)
    monkeypatch.setattr("src.keyword_generation.service.run_dedup_quality_pass", fake_dedup)
    monkeypatch.setattr("src.keyword_generation.service.run_supplementation_pass", fake_supplement)
    monkeypatch.setattr("src.keyword_generation.service.validate_keyword_rows", fake_validate)
    monkeypatch.setattr("src.keyword_generation.service.filter_keyword_rows", lambda rows, evidence_pack=None: (rows, []))
    monkeypatch.setattr("src.keyword_generation.service._surface_cleanup_rows_with_reasons", lambda rows, evidence_pack=None: (rows, []))

    result = generate_keywords(_request())

    assert result.status == "COMPLETED"
    assert ("cluster_a", ("brand", "generic_category", "purchase_intent")) in call_log
    assert ("cluster_b", ("feature_attribute", "benefit_price")) in call_log
    assert ("cluster_c", ("long_tail", "problem_solution", "season_event")) in call_log
    assert ("cluster_d", ("competitor_comparison", NEGATIVE_CATEGORY)) in call_log
    assert ("cluster_c_split_1", ("long_tail", "problem_solution")) in call_log
    assert ("cluster_c_split_2", ("season_event",)) in call_log
    assert "cluster_c" in result.debug_payload["generation"]["split_batch_names"]


def test_generate_keywords_records_failed_batch_context_on_parse_error(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    def raise_parse_error(*args, **kwargs):
        del args, kwargs
        raise BedrockResponseParseError(
            stage="generation",
            message="Bedrock response must include items[] or intents[] or rows[]",
            model_id="fake-model",
            response_text='{"broken":"shape"}',
            metadata={"stop_reason": "end_turn", "usage": {"outputTokens": 7}},
        )

    monkeypatch.setattr("src.keyword_generation.service.generate_intents_via_bedrock", raise_parse_error)

    result = generate_keywords(_request())

    assert result.status == "FAILED_GENERATION"
    assert result.validation_report is not None
    assert result.validation_report.failure_code == "generation_rule_violation"
    error = result.debug_payload["generation"]["error"]
    assert error["batch_name"] == "cluster_a"
    assert error["categories"] == ["brand", "generic_category", "purchase_intent"]
    assert error["response_text"] == '{"broken":"shape"}'
