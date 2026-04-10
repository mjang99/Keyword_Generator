from __future__ import annotations

from collections import defaultdict

from .constants import (
    GOOGLE_ALLOWED_MATCHES,
    NAVER_ALLOWED_MATCHES,
    NEGATIVE_CATEGORY,
    POSITIVE_CATEGORIES,
    PROMO_BANNED_TERMS,
    URGENCY_BANNED_TERMS,
)
from .models import KeywordRow, PlatformMode, ValidationReport
from .policy import keyword_hard_policy_issues


def validate_keyword_rows(
    rows: list[KeywordRow],
    *,
    requested_platform_mode: PlatformMode,
    quality_warning: bool,
    evidence_pack: dict | None = None,
) -> ValidationReport:
    """Validate generated rows against the TASK-008 contract.

    This is the stable validator entrypoint for runtime work. The real
    implementation should enforce the policy decisions already locked in the
    service design document.
    """

    if requested_platform_mode not in {"naver_sa", "google_sa", "both"}:
        raise ValueError(f"Unsupported platform mode: {requested_platform_mode}")

    if rows is None:
        raise ValueError("rows is required")

    positive_counts: dict[str, int] = {}
    category_counts: dict[str, dict[str, int]] = {}
    missing_positive_categories: dict[str, list[str]] = {}
    weak_ratios: dict[str, float] = {}

    platforms = ["naver_sa", "google_sa"] if requested_platform_mode == "both" else [requested_platform_mode]

    for platform in platforms:
        positive_rows = _positive_rows_for_platform(rows, platform)
        negative_rows = _negative_rows_for_platform(rows, platform)

        invalid_match = _find_invalid_match_label(rows, platform)
        if invalid_match is not None:
            return ValidationReport(
                status="FAILED_GENERATION",
                requested_platform_mode=requested_platform_mode,
                failure_code="generation_rule_violation",
                failure_detail=f"invalid {platform} match label: {invalid_match}",
                quality_warning=quality_warning,
            )

        banned_term = _find_banned_term(positive_rows + negative_rows)
        if banned_term is not None:
            return ValidationReport(
                status="FAILED_GENERATION",
                requested_platform_mode=requested_platform_mode,
                failure_code="generation_rule_violation",
                failure_detail=f"banned term emitted: {banned_term}",
                quality_warning=quality_warning,
            )

        if evidence_pack is not None:
            invalid_row = _find_policy_violation(positive_rows + negative_rows, evidence_pack=evidence_pack)
            if invalid_row is not None:
                return ValidationReport(
                    status="FAILED_GENERATION",
                    requested_platform_mode=requested_platform_mode,
                    failure_code="generation_rule_violation",
                    failure_detail=invalid_row,
                    quality_warning=quality_warning,
                )

        per_category = defaultdict(int)
        weak_count = 0
        for row in positive_rows:
            per_category[row.category] += 1
            if row.evidence_tier == "weak":
                weak_count += 1

        positive_counts[platform] = len(positive_rows)
        category_counts[platform] = dict(per_category)
        missing_positive_categories[platform] = [
            category for category in POSITIVE_CATEGORIES if per_category.get(category, 0) < 1
        ]
        weak_ratios[platform] = weak_count / len(positive_rows) if positive_rows else 0.0

        if len(positive_rows) < 100:
            return ValidationReport(
                status="FAILED_GENERATION",
                requested_platform_mode=requested_platform_mode,
                positive_keyword_counts=positive_counts,
                category_counts=category_counts,
                missing_positive_categories=missing_positive_categories,
                weak_tier_ratio_by_platform=weak_ratios,
                failure_code="generation_count_shortfall",
                failure_detail=f"{platform} positive rows below 100",
                quality_warning=quality_warning,
            )

        if not negative_rows:
            return ValidationReport(
                status="FAILED_GENERATION",
                requested_platform_mode=requested_platform_mode,
                positive_keyword_counts=positive_counts,
                category_counts=category_counts,
                missing_positive_categories=missing_positive_categories,
                weak_tier_ratio_by_platform=weak_ratios,
                failure_code="generation_rule_violation",
                failure_detail=f"{platform} missing negative rows",
                quality_warning=quality_warning,
            )

        if weak_ratios[platform] > 0.2:
            return ValidationReport(
                status="FAILED_GENERATION",
                requested_platform_mode=requested_platform_mode,
                positive_keyword_counts=positive_counts,
                category_counts=category_counts,
                missing_positive_categories=missing_positive_categories,
                weak_tier_ratio_by_platform=weak_ratios,
                failure_code="generation_rule_violation",
                failure_detail=f"{platform} weak-tier ratio exceeded 20%",
                quality_warning=quality_warning,
            )

    return ValidationReport(
        status="COMPLETED",
        requested_platform_mode=requested_platform_mode,
        positive_keyword_counts=positive_counts,
        category_counts=category_counts,
        missing_positive_categories=missing_positive_categories,
        weak_tier_ratio_by_platform=weak_ratios,
        quality_warning=quality_warning,
    )


def _positive_rows_for_platform(rows: list[KeywordRow], platform: PlatformMode) -> list[KeywordRow]:
    if platform == "naver_sa":
        return [row for row in rows if row.category != NEGATIVE_CATEGORY and row.naver_match]
    return [row for row in rows if row.category != NEGATIVE_CATEGORY and row.google_match]


def _negative_rows_for_platform(rows: list[KeywordRow], platform: PlatformMode) -> list[KeywordRow]:
    if platform == "naver_sa":
        return [row for row in rows if row.category == NEGATIVE_CATEGORY and row.naver_match == "제외키워드"]
    return [row for row in rows if row.category == NEGATIVE_CATEGORY and row.google_match == "negative"]


def _find_invalid_match_label(rows: list[KeywordRow], platform: PlatformMode) -> str | None:
    if platform == "naver_sa":
        for row in rows:
            if row.naver_match and row.naver_match not in NAVER_ALLOWED_MATCHES:
                return row.naver_match
        return None
    for row in rows:
        if row.google_match and row.google_match not in GOOGLE_ALLOWED_MATCHES:
            return row.google_match
    return None


def _find_banned_term(rows: list[KeywordRow]) -> str | None:
    banned_terms = (*PROMO_BANNED_TERMS, *URGENCY_BANNED_TERMS)
    for row in rows:
        haystack = " ".join(part for part in (row.keyword, row.reason) if part)
        for term in banned_terms:
            if term in haystack:
                return term
    return None


def _find_policy_violation(rows: list[KeywordRow], *, evidence_pack: dict) -> str | None:
    for row in rows:
        issues = keyword_hard_policy_issues(row, evidence_pack=evidence_pack)
        if issues:
            return f"{row.category}:{row.keyword}:{', '.join(issues)}"
    return None
