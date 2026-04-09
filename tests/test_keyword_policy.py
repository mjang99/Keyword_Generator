from __future__ import annotations

from src.keyword_generation.models import KeywordRow
from src.keyword_generation.policy import (
    filter_keyword_rows,
    generic_category_terms,
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
