from __future__ import annotations

from src.keyword_generation.models import KeywordRow
from src.keyword_generation.policy import (
    filter_keyword_rows,
    generic_category_terms,
    is_valid_competitor_keyword,
    keyword_policy_issues,
    taxonomy_terms,
)
from src.keyword_generation.validation import validate_keyword_rows
from src.quality_eval.core import PerUrlEvaluationInput, evaluate_per_url_input


def _skincare_pack() -> dict[str, object]:
    return {
        "page_class": "commerce_pdp",
        "raw_url": "https://www.laneige.com/kr/ko/skincare/perfect-renew-retinol.html",
        "product_name": "\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
        "canonical_product_name": "\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
        "sellability_state": "sellable",
        "facts": [
            {
                "type": "product_name",
                "value": "\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
                "normalized_value": "\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "brand",
                "value": "Laneige",
                "normalized_value": "Laneige",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_category",
                "value": "\uc81c\ud488",
                "normalized_value": "\uc81c\ud488",
                "admissibility_tags": ["category"],
            },
            {
                "type": "attribute",
                "value": "\ub808\ud2f0\ub180",
                "normalized_value": "\ub808\ud2f0\ub180",
                "admissibility_tags": ["attribute"],
            },
            {
                "type": "benefit",
                "value": "\ubcf4\uc2b5",
                "normalized_value": "\ubcf4\uc2b5",
                "admissibility_tags": ["benefit"],
            },
            {
                "type": "concern",
                "value": "\ubbfc\uac10",
                "normalized_value": "\ubbfc\uac10",
                "admissibility_tags": ["problem_solution"],
            },
        ],
    }


def _smartphone_pack() -> dict[str, object]:
    return {
        "page_class": "commerce_pdp",
        "raw_url": "https://www.apple.com/kr/shop/buy-iphone/iphone-16",
        "product_name": "iPhone 16",
        "canonical_product_name": "iPhone 16",
        "sellability_state": "sellable",
        "facts": [
            {
                "type": "product_name",
                "value": "iPhone 16",
                "normalized_value": "iPhone 16",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "brand",
                "value": "Apple",
                "normalized_value": "Apple",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_category",
                "value": "smartphone",
                "normalized_value": "smartphone",
                "admissibility_tags": ["category"],
            },
        ],
    }


def _phone_case_pack() -> dict[str, object]:
    return {
        "page_class": "commerce_pdp",
        "raw_url": "https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/",
        "product_name": "Galaxy S25 Silicone Case",
        "canonical_product_name": "Galaxy S25 Silicone Case",
        "sellability_state": "sellable",
        "facts": [
            {
                "type": "product_name",
                "value": "Galaxy S25 Silicone Case",
                "normalized_value": "Galaxy S25 Silicone Case",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "brand",
                "value": "Samsung",
                "normalized_value": "Samsung",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_category",
                "value": "케이스",
                "normalized_value": "케이스",
                "admissibility_tags": ["category"],
            },
        ],
    }


def _protein_food_pack() -> dict[str, object]:
    return {
        "page_class": "commerce_pdp",
        "raw_url": "https://www.rankingdak.com/product/view?productCd=F000008814",
        "product_name": "맛있닭 소스 닭가슴살",
        "canonical_product_name": "맛있닭 소스 닭가슴살",
        "sellability_state": "sellable",
        "facts": [
            {
                "type": "product_name",
                "value": "맛있닭 소스 닭가슴살",
                "normalized_value": "맛있닭 소스 닭가슴살",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "brand",
                "value": "맛있닭",
                "normalized_value": "맛있닭",
                "admissibility_tags": ["product_identity"],
            },
            {
                "type": "product_category",
                "value": "닭가슴살",
                "normalized_value": "닭가슴살",
                "admissibility_tags": ["category"],
            },
        ],
    }


def test_skincare_taxonomy_uses_curated_negative_terms() -> None:
    negatives = taxonomy_terms("negative_seed", _skincare_pack())

    assert "\uc911\uace0" in negatives
    assert "\ub3c4\ub9e4" in negatives
    assert "download" not in negatives
    assert "manual" not in negatives


def test_generic_category_terms_are_specific_not_placeholder() -> None:
    terms = generic_category_terms(_skincare_pack())

    assert terms
    assert "\uc81c\ud488" not in terms
    assert any("retinol" in term.casefold() or "\ub808\ud2f0\ub180" in term for term in terms)


def test_policy_filters_malformed_exact_invalid_negative_and_placeholder_rows() -> None:
    evidence_pack = _skincare_pack()
    rows = [
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="brand",
            keyword="\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180 \ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
            google_match="exact",
            reason="fixture",
        ),
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="negative",
            keyword="download",
            google_match="negative",
            reason="fixture",
        ),
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="generic_category",
            keyword="\uc81c\ud488 \uae30\ubcf8\ud615",
            google_match="broad",
            reason="fixture",
        ),
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="generic_category",
            keyword="\ub808\ud2f0\ub180 \uc138\ub7fc",
            google_match="broad",
            reason="fixture",
        ),
    ]

    kept, dropped = filter_keyword_rows(rows, evidence_pack=evidence_pack)

    assert [row.keyword for row in kept] == ["\ub808\ud2f0\ub180 \uc138\ub7fc"]
    assert {item["keyword"] for item in dropped} == {
        "\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180 \ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
        "download",
        "\uc81c\ud488 \uae30\ubcf8\ud615",
    }


def test_validation_rejects_invalid_exact_row() -> None:
    evidence_pack = _skincare_pack()
    rows = [
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="generic_category",
            keyword=f"\ub808\ud2f0\ub180 \uc138\ub7fc {index}",
            google_match="broad",
            reason="fixture",
            evidence_tier="direct",
        )
        for index in range(99)
    ]
    rows.append(
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="brand",
            keyword="\ud37c\ud399\ud2b8",
            google_match="exact",
            reason="fixture",
            evidence_tier="direct",
        )
    )
    rows.append(
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="negative",
            keyword="\uc911\uace0",
            google_match="negative",
            reason="fixture",
        )
    )

    report = validate_keyword_rows(
        rows,
        requested_platform_mode="google_sa",
        quality_warning=False,
        evidence_pack=evidence_pack,
    )

    assert report.status == "FAILED_GENERATION"
    assert report.failure_code == "generation_rule_violation"
    assert "invalid_exact" in (report.failure_detail or "")


def test_quality_eval_flags_malformed_positive_keywords() -> None:
    evidence_pack = _skincare_pack()
    rows = [
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="generic_category",
            keyword=f"\ub808\ud2f0\ub180 \uc138\ub7fc {index}",
            google_match="broad",
            reason="fixture",
        )
        for index in range(99)
    ]
    rows.append(
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="brand",
            keyword="\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180 \ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
            google_match="exact",
            reason="fixture",
        )
    )
    rows.append(
        KeywordRow(
            url="https://example.com/p",
            product_name=evidence_pack["canonical_product_name"],
            category="negative",
            keyword="\uc911\uace0",
            google_match="negative",
            reason="fixture",
        )
    )

    result = evaluate_per_url_input(
        PerUrlEvaluationInput(
            url_task_id="ut-1",
            raw_url="https://example.com/p",
            page_class="commerce_pdp",
            requested_platform_mode="google_sa",
            quality_warning=False,
            rows=rows,
            evidence_pack=evidence_pack,
        ),
        platform="google_sa",
    )

    assert result.gate.pass_ is False
    assert "malformed_positive_keywords" in result.gate.failure_reasons
    assert result.metrics.malformed_positive_count == 1
    assert result.metrics.invalid_negative_count == 0


def test_keyword_policy_issues_allow_curated_skincare_negative() -> None:
    row = KeywordRow(
        url="https://example.com/p",
        product_name="\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
        category="negative",
        keyword="\uc911\uace0",
        google_match="negative",
        reason="fixture",
    )

    assert keyword_policy_issues(row, evidence_pack=_skincare_pack()) == []


def test_keyword_policy_flags_placeholder_product_term_and_skincare_domain_mismatch() -> None:
    placeholder = KeywordRow(
        url="https://example.com/p",
        product_name="Example Product",
        category="generic_category",
        keyword="\uc81c\ud488 \uae30\ubcf8\ud615",
        google_match="broad",
        reason="fixture",
    )
    domain_mismatch = KeywordRow(
        url="https://example.com/p",
        product_name="Example Product",
        category="feature_attribute",
        keyword="Example Product \uae30\ubcf8 \uc0ac\uc591",
        google_match="broad",
        reason="fixture",
    )

    assert "placeholder_product_term" in keyword_policy_issues(placeholder, evidence_pack=_skincare_pack())
    assert "domain_mismatch_phrase" in keyword_policy_issues(domain_mismatch, evidence_pack=_skincare_pack())


def test_competitor_policy_allows_grounded_smartphone_comparison_shape() -> None:
    assert is_valid_competitor_keyword("아이폰16 갤럭시 비교", evidence_pack=_smartphone_pack()) is True


def test_competitor_policy_allows_grounded_smartphone_brand_plus_identity_shape() -> None:
    assert is_valid_competitor_keyword("갤럭시 아이폰16", evidence_pack=_smartphone_pack()) is True


def test_competitor_policy_allows_grounded_case_brand_plus_type_shape() -> None:
    assert is_valid_competitor_keyword("스피젠 갤럭시 S25 케이스", evidence_pack=_phone_case_pack()) is True


def test_competitor_policy_allows_grounded_food_comparison_shape() -> None:
    assert is_valid_competitor_keyword("하림 소스 닭가슴살 vs 맛있닭", evidence_pack=_protein_food_pack()) is True


def test_competitor_policy_still_rejects_attribute_only_skincare_competitor() -> None:
    assert is_valid_competitor_keyword("이니스프리 레티놀", evidence_pack=_skincare_pack()) is False


def test_keyword_policy_flags_non_adjacent_repeated_phrase_pattern() -> None:
    repeated = KeywordRow(
        url="https://example.com/p",
        product_name="\ud37c\ud399\ud2b8 \ub9ac\ub274 \ub808\ud2f0\ub180",
        category="generic_category",
        keyword="\ubcf4\uc2b5 \ud06c\ub9bc \ubcf4\uc2b5",
        google_match="broad",
        reason="fixture",
    )

    assert "repeated_phrase" in keyword_policy_issues(repeated, evidence_pack=_skincare_pack())
