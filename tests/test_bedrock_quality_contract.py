from __future__ import annotations

from src.exporting.models import UrlExportResult
from src.exporting.service import build_per_url_json_payload
from src.keyword_generation.bedrock_adapter import parse_dedup_quality_response
from src.keyword_generation.constants import NEGATIVE_CATEGORY
from src.keyword_generation.models import (
    CanonicalIntent,
    GenerationRequest,
    GenerationResult,
    KeywordRow,
    PlatformRender,
    SharedRender,
    SlotPlanItem,
    ValidationReport,
)
from src.keyword_generation.service import (
    _build_slot_drop_report,
    _platform_category_gap_report,
    _platform_slot_gap_report,
    _supplementation_slot_targets,
    _surface_cleanup_rows,
    _surface_cleanup_rows_with_reasons,
)


def _request() -> GenerationRequest:
    return GenerationRequest(
        evidence_pack={
            "raw_url": "https://example.com/apple-pencil",
            "canonical_url": "https://example.com/apple-pencil",
            "page_class": "commerce_pdp",
            "product_name": "Apple Pencil",
            "canonical_product_name": "Apple Pencil",
            "quality_warning": True,
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
            ],
        },
        requested_platform_mode="both",
    )


def test_parse_dedup_quality_response_uses_intent_id_over_surface_text() -> None:
    candidate = CanonicalIntent(
        category="brand",
        slot_type="product_name",
        intent_text="apple pencil",
        intent_id="brand-001",
        reason="direct",
        evidence_tier="direct",
        allowed_platforms=["naver_sa", "google_sa"],
        shared_render=SharedRender(keyword="apple pencil"),
        naver_render=PlatformRender(keyword="apple pencil", match_label="완전일치"),
        google_render=PlatformRender(keyword="apple pencil", match_label="exact"),
    )

    report = parse_dedup_quality_response(
        '{"surviving":[{"intent_id":"brand-001","keyword":"apple pencil official","category":"brand","quality_score":"high","quality_reason":"good","keep":true}],"slot_gap_report":{"_total":0}}',
        platform="both",
        all_candidates=[candidate],
        request=_request(),
    )

    assert len(report.surviving_keywords) == 1
    assert report.surviving_keywords[0].intent_id == "brand-001"
    assert report.surviving_keywords[0].intent_text == "apple pencil"


def test_surface_cleanup_drops_product_plus_action_phrases() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="purchase_intent",
            slot_type="navigational_alias",
            keyword="Apple Pencil buy",
            naver_match="완전일치",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="feature_attribute",
            slot_type="core_attribute",
            keyword="Apple Pencil drawing",
            naver_match="확장소재",
            google_match="broad",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="long_tail",
            slot_type="use_case_phrase",
            keyword="Apple Pencil note taking",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="benefit_price",
            slot_type="product_price",
            keyword="Apple Pencil 가격",
            naver_match="확장소재",
            google_match="broad",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="generic_category",
            slot_type="generic_type_phrase",
            keyword="stylus pen",
            naver_match="확장소재",
            google_match="broad",
        ),
    ]

    cleaned = _surface_cleanup_rows(rows, evidence_pack=_request().evidence_pack)
    cleaned_keywords = {row.keyword for row in cleaned}

    assert "Apple Pencil buy" not in cleaned_keywords
    assert "Apple Pencil drawing" not in cleaned_keywords
    assert "Apple Pencil note taking" not in cleaned_keywords
    assert "Apple Pencil 가격" in cleaned_keywords
    assert "stylus pen" in cleaned_keywords


def test_platform_slot_gap_report_marks_missing_naver_slots() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="brand",
            slot_type="product_name",
            keyword="apple pencil",
            google_match="exact",
        )
    ]
    slot_plan = [
        SlotPlanItem(category="brand", slot_type="product_name", target_count=1),
    ]

    gap_report = _platform_slot_gap_report(
        rows,
        requested_platform_mode="both",
        slot_plan=slot_plan,
    )

    assert gap_report["platforms"]["naver_sa"]["brand:product_name"] == 1
    assert gap_report["aggregate"]["brand:product_name"] == 1


def test_per_url_payload_includes_slot_debug_section() -> None:
    result = UrlExportResult(
        url_task_id="ut_01",
        raw_url="https://example.com/apple-pencil",
        page_class="commerce_pdp",
        requested_platform_mode="both",
        generation_result=GenerationResult(
            status="FAILED_GENERATION",
            requested_platform_mode="both",
            rows=[],
            validation_report=ValidationReport(
                status="FAILED_GENERATION",
                requested_platform_mode="both",
                positive_keyword_counts={"naver_sa": 12},
                category_counts={"naver_sa": {"brand": 1}},
                weak_tier_ratio_by_platform={"naver_sa": 0.0},
                failure_code="generation_count_shortfall",
                failure_detail="naver_sa positive rows below 100",
                quality_warning=True,
            ),
            debug_payload={"generation": {"slot_gap_report": {"aggregate": {"brand:product_name": 1}}}},
        ),
    )

    payload = build_per_url_json_payload(result)

    assert payload["debug"]["generation"]["slot_gap_report"]["aggregate"]["brand:product_name"] == 1


def test_platform_slot_gap_report_defaults_missing_slot_type() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="brand",
            slot_type=None,
            keyword="apple pencil",
            naver_match="exact",
        )
    ]
    slot_plan = [SlotPlanItem(category="brand", slot_type="product_name", target_count=1, required=True)]

    gap_report = _platform_slot_gap_report(
        rows,
        requested_platform_mode="naver_sa",
        slot_plan=slot_plan,
    )

    assert gap_report["_total"] == 0


def test_supplementation_targets_prioritize_missing_categories_over_soft_slots() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="brand",
            slot_type="brand_with_type",
            keyword="Apple stylus pen",
            naver_match="exact",
        )
    ]
    slot_plan = [
        SlotPlanItem(category="brand", slot_type="product_name", target_count=2, required=True),
        SlotPlanItem(category="brand", slot_type="brand_with_type", target_count=1, required=False),
        SlotPlanItem(category="generic_category", slot_type="generic_type_phrase", target_count=2, required=True),
    ]

    category_gap_report = _platform_category_gap_report(
        rows,
        requested_platform_mode="naver_sa",
    )
    slot_gap_report = _platform_slot_gap_report(
        rows,
        requested_platform_mode="naver_sa",
        slot_plan=slot_plan,
    )

    targets = _supplementation_slot_targets(
        category_gap_report=category_gap_report,
        slot_gap_report=slot_gap_report,
        slot_plan=slot_plan,
        rows=rows,
        requested_platform_mode="naver_sa",
        positive_target=100,
    )

    assert targets["generic_category:generic_type_phrase"] >= 1
    assert targets["brand:product_name"] >= 1
    assert "brand:brand_with_type" not in targets


def test_slot_drop_report_contains_structured_reason_codes() -> None:
    policy_drops = [{"keyword": "Apple Pencil buy", "category": "purchase_intent", "issues": "low_information"}]
    pre_policy_intents = [
        CanonicalIntent(
            category="purchase_intent",
            slot_type="navigational_alias",
            intent_text="Apple Pencil buy",
            intent_id="buy-1",
            reason="direct",
            evidence_tier="direct",
            allowed_platforms=["naver_sa"],
            naver_render=PlatformRender(keyword="Apple Pencil buy", match_label="exact"),
        )
    ]
    _, surface_drops = _surface_cleanup_rows_with_reasons(
        [
            KeywordRow(
                url="https://example.com/apple-pencil",
                product_name="Apple Pencil",
                category="long_tail",
                slot_type="use_case_phrase",
                keyword="Apple Pencil drawing",
                naver_match="phrase",
            )
        ],
        evidence_pack=_request().evidence_pack,
    )

    report = _build_slot_drop_report(
        all_intents=pre_policy_intents,
        dedup_report=None,
        policy_drop_rows=policy_drops,
        surface_drop_rows=surface_drops,
    )

    assert any(entry["drop_reason_code"] == "dedup_low_quality" for entry in report)
    assert any(entry["drop_reason_code"] == "surface_product_action" for entry in report)


def test_supplementation_targets_expand_for_positive_count_shortfall() -> None:
    rows = [
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category="brand",
            slot_type="product_name",
            keyword="Apple Pencil",
            naver_match="완전일치",
        ),
        KeywordRow(
            url="https://example.com/apple-pencil",
            product_name="Apple Pencil",
            category=NEGATIVE_CATEGORY,
            slot_type="negative_exclusion",
            keyword="Apple Pencil manual",
            naver_match="제외키워드",
        ),
    ]
    slot_plan = [
        SlotPlanItem(category="brand", slot_type="product_name", target_count=12, required=True),
        SlotPlanItem(category="generic_category", slot_type="generic_type_phrase", target_count=12, required=True),
        SlotPlanItem(category="feature_attribute", slot_type="spec", target_count=12, required=True),
    ]

    targets = _supplementation_slot_targets(
        category_gap_report={"aggregate": {}, "_total": 0},
        slot_gap_report={"aggregate": {}, "_total": 0},
        slot_plan=slot_plan,
        rows=rows,
        requested_platform_mode="naver_sa",
        positive_target=100,
    )

    assert targets["_total"] > 3
    assert sum(
        value for key, value in targets.items() if key != "_total" and not key.startswith(f"{NEGATIVE_CATEGORY}:")
    ) >= 90
