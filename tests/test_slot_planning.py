from __future__ import annotations

from src.keyword_generation.service import _build_product_interpretation, _build_slot_plan


def _apple_pencil_evidence() -> dict:
    return {
        "raw_url": "https://example.com/apple-pencil",
        "canonical_url": "https://example.com/apple-pencil",
        "page_class": "commerce_pdp",
        "product_name": "Apple Pencil",
        "canonical_product_name": "Apple Pencil",
        "sellability_state": "sellable",
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
                "type": "price",
                "value": "149000",
                "normalized_value": "149000",
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
            {
                "type": "attribute",
                "value": "Black Friday launch event",
                "normalized_value": "Black Friday launch event",
                "evidence_tier": "direct",
            },
            {
                "type": "variant",
                "value": "1st gen",
                "normalized_value": "1st gen",
                "evidence_tier": "direct",
            },
        ],
    }


def test_product_interpretation_exposes_slot_friendly_facets() -> None:
    interpretation = _build_product_interpretation(_apple_pencil_evidence())

    assert "stylus pen" in interpretation.generic_type_phrases
    assert "Apple Pencil" in interpretation.navigational_aliases
    assert "precision writing stylus pen" in interpretation.problem_noun_phrases
    assert interpretation.grounded_event_terms
    assert interpretation.price_band_candidates


def test_product_interpretation_keeps_raw_audience_and_problem_slots_concern_only(
    evidence_fixture_loader,
) -> None:
    interpretation = _build_product_interpretation(
        evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    )

    assert "건성 복합성 피부" in interpretation.audience
    assert "건성 피부" not in interpretation.audience
    assert "복합성 피부" not in interpretation.audience
    assert "수분 부족 슬리핑 마스크" in interpretation.problem_noun_phrases
    assert "수면 중 피부 당김 슬리핑 마스크" in interpretation.problem_noun_phrases
    assert all("건성 복합성 피부" not in phrase for phrase in interpretation.problem_noun_phrases)
    assert all("취침 전" not in phrase for phrase in interpretation.problem_noun_phrases)


def test_slot_plan_expands_category_targets_into_slot_targets() -> None:
    interpretation = _build_product_interpretation(_apple_pencil_evidence())

    slot_plan = _build_slot_plan(
        interpretation,
        category_plan={
            "brand": 2,
            "benefit_price": 2,
            "problem_solution": 2,
        },
    )

    slot_keys = {(slot.category, slot.slot_type) for slot in slot_plan}
    required_slots = {(slot.category, slot.slot_type) for slot in slot_plan if slot.required}

    assert ("brand", "product_name") in slot_keys
    assert ("benefit_price", "product_price") in slot_keys
    assert ("problem_solution", "problem_noun_phrase") in slot_keys
    assert ("brand", "product_name") in required_slots
    assert ("benefit_price", "product_price") in required_slots
