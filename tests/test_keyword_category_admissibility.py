from __future__ import annotations

from src.keyword_generation.models import KeywordRow
from src.keyword_generation.service import _annotate_selection_scores, _surface_cleanup_rows


def test_selection_scoring_penalizes_ungrounded_feature_attribute_evidence() -> None:
    evidence_pack = {
        "raw_url": "https://example.com/phone-x",
        "canonical_url": "https://example.com/phone-x",
        "page_class": "commerce_pdp",
        "product_name": "Phone X",
        "canonical_product_name": "Phone X",
        "sellability_state": "sellable",
        "facts": [
            {"type": "brand", "value": "Acme", "normalized_value": "Acme", "evidence_tier": "direct", "admissibility_tags": ["product_identity"]},
            {"type": "product_category", "value": "smartphone", "normalized_value": "smartphone", "evidence_tier": "direct"},
            {"type": "variant", "value": "512GB", "normalized_value": "512GB", "evidence_tier": "direct"},
        ],
    }
    rows = [
        KeywordRow(
            url="https://example.com/phone-x",
            product_name="Phone X",
            category="feature_attribute",
            keyword="512GB smartphone",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/phone-x",
            product_name="Phone X",
            category="feature_attribute",
            keyword="CDMA smartphone",
            naver_match="확장소재",
            google_match="phrase",
        ),
    ]

    scored = _annotate_selection_scores(rows, evidence_pack=evidence_pack)

    assert [row.keyword for row in _surface_cleanup_rows(rows, evidence_pack=evidence_pack)] == [
        "512GB smartphone",
        "CDMA smartphone",
    ]
    assert scored[0].selection_score is not None
    assert scored[1].selection_score is not None
    assert scored[0].selection_score > scored[1].selection_score
    assert "surface_ungrounded_feature" in scored[1].soft_penalties


def test_selection_scoring_penalizes_ungrounded_season_event_or_usage_context() -> None:
    evidence_pack = {
        "raw_url": "https://example.com/mask",
        "canonical_url": "https://example.com/mask",
        "page_class": "commerce_pdp",
        "product_name": "Sleep Mask",
        "canonical_product_name": "Sleep Mask",
        "sellability_state": "sellable",
        "facts": [
            {"type": "brand", "value": "Acme", "normalized_value": "Acme", "evidence_tier": "direct", "admissibility_tags": ["product_identity"]},
            {"type": "product_category", "value": "mask", "normalized_value": "mask", "evidence_tier": "direct"},
            {"type": "use_case", "value": "night routine", "normalized_value": "night routine", "evidence_tier": "direct", "admissibility_tags": ["use_case"]},
        ],
    }
    rows = [
        KeywordRow(
            url="https://example.com/mask",
            product_name="Sleep Mask",
            category="season_event",
            keyword="night routine mask",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/mask",
            product_name="Sleep Mask",
            category="season_event",
            keyword="free shipping mask",
            naver_match="확장소재",
            google_match="phrase",
        ),
    ]

    scored = _annotate_selection_scores(rows, evidence_pack=evidence_pack)

    assert [row.keyword for row in _surface_cleanup_rows(rows, evidence_pack=evidence_pack)] == [
        "night routine mask",
        "free shipping mask",
    ]
    assert scored[0].selection_score is not None
    assert scored[1].selection_score is not None
    assert scored[0].selection_score > scored[1].selection_score
    assert "surface_ungrounded_season" in scored[1].soft_penalties


def test_selection_scoring_penalizes_ungrounded_problem_solution_evidence() -> None:
    evidence_pack = {
        "raw_url": "https://example.com/phone-x",
        "canonical_url": "https://example.com/phone-x",
        "page_class": "commerce_pdp",
        "product_name": "Phone X",
        "canonical_product_name": "Phone X",
        "sellability_state": "sellable",
        "facts": [
            {"type": "brand", "value": "Acme", "normalized_value": "Acme", "evidence_tier": "direct", "admissibility_tags": ["product_identity"]},
            {"type": "product_category", "value": "smartphone", "normalized_value": "smartphone", "evidence_tier": "direct"},
            {"type": "concern", "value": "battery drain", "normalized_value": "battery drain", "evidence_tier": "direct", "admissibility_tags": ["problem_solution"]},
        ],
    }
    rows = [
        KeywordRow(
            url="https://example.com/phone-x",
            product_name="Phone X",
            category="problem_solution",
            keyword="battery drain smartphone",
            naver_match="확장소재",
            google_match="phrase",
        ),
        KeywordRow(
            url="https://example.com/phone-x",
            product_name="Phone X",
            category="problem_solution",
            keyword="storage shortage smartphone",
            naver_match="확장소재",
            google_match="phrase",
        ),
    ]

    scored = _annotate_selection_scores(rows, evidence_pack=evidence_pack)

    assert [row.keyword for row in _surface_cleanup_rows(rows, evidence_pack=evidence_pack)] == [
        "battery drain smartphone",
        "storage shortage smartphone",
    ]
    assert scored[0].selection_score is not None
    assert scored[1].selection_score is not None
    assert scored[0].selection_score > scored[1].selection_score
    assert "surface_ungrounded_problem" in scored[1].soft_penalties
