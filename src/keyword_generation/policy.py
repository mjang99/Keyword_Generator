from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import KeywordRow

DOC_BOILERPLATE_TOKENS = {
    "설명서",
    "매뉴얼",
    "다운로드",
    "download",
    "manual",
    "spec",
    "specs",
}
LOW_INFORMATION_TOKENS = {
    "검색",
    "정리",
    "탐색",
    "베스트",
    "카테고리",
    "정식",
    "중심",
    "기반",
}
EXACT_MATCH_LABELS = {"완전일치", "exact"}
UNIT_TOKENS = {"ml", "g", "kg", "inch", "in", "gb", "tb", "mah", "hz", "w"}
GENERIC_PRODUCT_TOKENS = {"제품", "상품", "product", "products", "item", "items", "goods"}
MARKETPLACE_HOST_TOKENS = {
    "amazon",
    "coupang",
    "ebay",
    "gmarket",
    "naver",
    "smartstore",
    "tmall",
    "wconcept",
    "11st",
}
PRODUCT_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "skincare": ("retinol", "레티놀", "serum", "cream", "mask", "sleeping", "moisturizer", "hydrator", "스킨케어", "세럼", "크림", "마스크", "보습"),
    "electronics": ("macbook", "laptop", "notebook", "노트북", "맥북", "spec", "manual"),
    "audio": ("airpods", "earbud", "이어버드", "이어폰", "헤드폰"),
    "footwear": ("shoe", "shoes", "sneaker", "running", "러닝화", "스니커즈", "신발"),
}
SKINCARE_BLOCKED_PHRASES = {
    "업무용",
    "기본형",
    "기본 사양",
    "기본 성능",
    "기본 기능",
    "대표 모델",
    "라인업",
    "시리즈",
    "퍼포먼스",
    "트레이닝",
    "라이프스타일",
}
GENERIC_PRODUCT_TYPE_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "skincare": {
        "retinol": ("레티놀 세럼", "레티놀 크림", "민감 피부 레티놀", "레티놀 스킨케어"),
        "레티놀": ("레티놀 세럼", "레티놀 크림", "민감 피부 레티놀", "레티놀 스킨케어"),
        "serum": ("세럼", "보습 세럼", "스킨케어 세럼"),
        "세럼": ("세럼", "보습 세럼", "스킨케어 세럼"),
        "cream": ("보습 크림", "장벽 크림", "페이스 크림"),
        "크림": ("보습 크림", "장벽 크림", "페이스 크림"),
        "mask": ("슬리핑 마스크", "보습 마스크", "수분 마스크"),
        "마스크": ("슬리핑 마스크", "보습 마스크", "수분 마스크"),
        "default": ("스킨케어", "보습 케어", "민감 피부 케어"),
    },
    "electronics": {
        "macbook": ("노트북", "프로 노트북", "업무용 노트북"),
        "default": ("전자기기", "디지털 기기"),
    },
    "audio": {
        "earbud": ("무선 이어폰", "블루투스 이어폰", "노이즈캔슬링 이어폰"),
        "default": ("오디오 기기", "무선 오디오"),
    },
    "footwear": {
        "running": ("러닝화", "데일리 러닝화", "쿠셔닝 러닝화"),
        "default": ("신발", "데일리 슈즈", "라이프스타일 슈즈"),
    },
}
COMPETITOR_BRAND_SEEDS: dict[str, tuple[str, ...]] = {
    "skincare": ("이니스프리", "메디힐", "닥터자르트", "에스트라", "아이오페"),
    "footwear": ("살로몬", "콜롬비아", "머렐", "블랙야크", "호카"),
    "audio": ("소니", "보스", "JBL", "삼성", "애플"),
    "electronics": ("삼성", "LG", "레노버", "델", "HP", "ASUS", "애플"),
    "general": (),
}


def filter_keyword_rows(
    rows: list[KeywordRow],
    *,
    evidence_pack: dict[str, Any],
) -> tuple[list[KeywordRow], list[dict[str, str]]]:
    kept: list[KeywordRow] = []
    dropped: list[dict[str, str]] = []
    for row in rows:
        issues = keyword_policy_issues(row, evidence_pack=evidence_pack)
        if issues:
            dropped.append(
                {
                    "keyword": row.keyword,
                    "category": row.category,
                    "issues": ", ".join(issues),
                }
            )
            continue
        kept.append(row)
    return kept, dropped


def keyword_policy_issues(row: KeywordRow, *, evidence_pack: dict[str, Any]) -> list[str]:
    keyword = " ".join(row.keyword.split()).strip()
    if not keyword:
        return ["empty_keyword"]

    issues: list[str] = []
    tokens = _tokens(keyword)
    product_name = canonical_product_name(evidence_pack)
    brand = canonical_brand(evidence_pack)
    short_name = short_product_name(product_name, brand)
    exact_like = row.naver_match in EXACT_MATCH_LABELS or row.google_match in EXACT_MATCH_LABELS

    if has_repeated_phrase(keyword):
        issues.append("repeated_phrase")
    if has_placeholder_unit(keyword):
        issues.append("placeholder_unit")
    if contains_doc_boilerplate(keyword) and str(evidence_pack.get("page_class") or "") == "commerce_pdp":
        issues.append("doc_boilerplate")
    if exact_like and is_invalid_exact_keyword(
        keyword,
        category=row.category,
        product_name=product_name,
        short_name=short_name,
        brand=brand,
    ):
        issues.append("invalid_exact")
    if row.category == "negative" and not is_allowed_negative_keyword(keyword, evidence_pack=evidence_pack, product_name=product_name):
        issues.append("invalid_negative")
    if row.category == "competitor_comparison" and not is_valid_competitor_keyword(keyword, evidence_pack=evidence_pack):
        issues.append("invalid_competitor")
    if row.category != "negative" and contains_placeholder_product_term(keyword):
        issues.append("placeholder_product_term")
    if row.category != "negative" and contains_domain_mismatch_phrase(keyword, evidence_pack=evidence_pack):
        issues.append("domain_mismatch_phrase")
    if row.category != "negative" and is_low_information_keyword(keyword):
        issues.append("low_information")
    return issues


def is_low_information_keyword(keyword: str) -> bool:
    lowered = keyword.casefold()
    if any(token in lowered for token in LOW_INFORMATION_TOKENS):
        return True
    if contains_doc_boilerplate(keyword):
        return True
    if has_placeholder_unit(keyword):
        return True
    tokens = lowered.split()
    if len(tokens) >= 2 and tokens[0] == tokens[1]:
        return True
    return bool(re.search(r"\b탐색\s*\d+\b", keyword))


def contains_doc_boilerplate(keyword: str) -> bool:
    lowered = keyword.casefold()
    return any(token in lowered for token in DOC_BOILERPLATE_TOKENS)


def contains_placeholder_product_term(keyword: str) -> bool:
    return any(token in GENERIC_PRODUCT_TOKENS for token in _tokens(keyword))


def contains_domain_mismatch_phrase(keyword: str, *, evidence_pack: dict[str, Any]) -> bool:
    product_types = resolve_product_types(evidence_pack)
    if "skincare" in product_types:
        return any(phrase in keyword for phrase in SKINCARE_BLOCKED_PHRASES)
    return False


def has_placeholder_unit(keyword: str) -> bool:
    return any(token in UNIT_TOKENS for token in _tokens(keyword))


def has_repeated_phrase(keyword: str) -> bool:
    tokens = _tokens(keyword)
    if len(tokens) >= 4 and len(tokens) % 2 == 0:
        midpoint = len(tokens) // 2
        if tokens[:midpoint] == tokens[midpoint:]:
            return True
    deduped: list[str] = []
    for token in tokens:
        if deduped and deduped[-1] == token and not token.isdigit():
            return True
        deduped.append(token)
    non_digit_tokens = [token for token in tokens if not token.isdigit()]
    if len(non_digit_tokens) >= 3:
        repeated_counts: dict[str, int] = {}
        for token in non_digit_tokens:
            repeated_counts[token] = repeated_counts.get(token, 0) + 1
            if repeated_counts[token] >= 3:
                return True
        if non_digit_tokens[0] == non_digit_tokens[-1]:
            return True
    return False


def is_invalid_exact_keyword(
    keyword: str,
    *,
    category: str,
    product_name: str,
    short_name: str,
    brand: str,
) -> bool:
    allowed_exacts = {
        value.casefold()
        for value in {product_name, short_name, brand, f"{brand} {short_name}".strip()}
        if value
    }
    lowered = keyword.casefold()
    if lowered in allowed_exacts:
        return False

    tokens = _tokens(keyword)
    if not tokens:
        return True

    if len(tokens) != len(set(tokens)):
        return True
    if product_name and lowered.count(product_name.casefold()) > 1:
        return True
    if short_name and short_name != product_name and lowered.count(short_name.casefold()) > 1:
        return True
    if _contains_measurement_token(keyword):
        return True

    if len(tokens) == 1:
        if not brand:
            return False
        return lowered != brand.casefold()
    if category == "brand" and brand and brand.casefold() not in lowered and len(tokens) <= 2:
        return True
    return False


def is_allowed_negative_keyword(
    keyword: str,
    *,
    evidence_pack: dict[str, Any],
    product_name: str,
) -> bool:
    keyword = " ".join(keyword.split()).strip()
    allowed_terms = set(taxonomy_terms("negative_seed", evidence_pack))
    if keyword in allowed_terms:
        return True
    if keyword.startswith(f"{product_name} "):
        suffix = keyword[len(product_name) :].strip()
        return suffix in allowed_terms
    return False


def taxonomy_terms(group_name: str, evidence_pack: dict[str, Any]) -> list[str]:
    product_types = resolve_product_types(evidence_pack)
    anchor_tags = resolve_anchor_tags(evidence_pack)
    terms: list[str] = []
    for entry in _load_taxonomy_group(group_name):
        allowed_types = set(entry.get("allowed_product_types") or [])
        required_tags = set(entry.get("required_anchor_tags") or [])
        if allowed_types and "*" not in allowed_types and not product_types.intersection(allowed_types):
            continue
        if required_tags and not required_tags.issubset(anchor_tags):
            continue
        term = str(entry.get("term") or "").strip()
        if term:
            terms.append(term)
    return terms


def generic_category_terms(evidence_pack: dict[str, Any]) -> list[str]:
    all_text = _evidence_text(evidence_pack)
    product_types = resolve_product_types(evidence_pack)
    terms: list[str] = []
    for product_type in product_types:
        profile = GENERIC_PRODUCT_TYPE_TERMS.get(product_type, {})
        matched = False
        for hint, candidates in profile.items():
            if hint == "default":
                continue
            if hint in all_text:
                terms.extend(candidates)
                matched = True
        if not matched:
            terms.extend(profile.get("default", ()))
    return _unique_terms(terms)


def competitor_brand_terms(evidence_pack: dict[str, Any]) -> list[str]:
    product_types = resolve_product_types(evidence_pack)
    current_brand = canonical_brand(evidence_pack).casefold()
    host_brand = _brand_from_url(str(evidence_pack.get("raw_url") or evidence_pack.get("canonical_url") or "")).casefold()
    blocked = {value for value in (current_brand, host_brand) if value}
    terms: list[str] = []
    for product_type in product_types:
        terms.extend(COMPETITOR_BRAND_SEEDS.get(product_type, ()))
    return _unique_terms([term for term in terms if term.casefold() not in blocked])


def resolve_product_types(evidence_pack: dict[str, Any]) -> set[str]:
    all_text = _evidence_text(evidence_pack)
    resolved = {
        product_type
        for product_type, hints in PRODUCT_TYPE_HINTS.items()
        if any(hint in all_text for hint in hints)
    }
    return resolved or {"general"}


def resolve_anchor_tags(evidence_pack: dict[str, Any]) -> set[str]:
    tags = {
        str(tag)
        for fact in evidence_pack.get("facts", [])
        for tag in fact.get("admissibility_tags", [])
        if str(tag).strip()
    }
    page_class = str(evidence_pack.get("page_class") or "")
    if page_class == "commerce_pdp":
        tags.add("commerce")
    if str(evidence_pack.get("sellability_state") or "") == "sellable":
        tags.add("sellability")
    return tags


def canonical_product_name(evidence_pack: dict[str, Any]) -> str:
    for key in ("canonical_product_name", "product_name", "display_product_name"):
        value = str(evidence_pack.get(key) or "").strip()
        if value:
            return " ".join(value.split())
    return "product"


def canonical_brand(evidence_pack: dict[str, Any]) -> str:
    fact_brand = ""
    for fact in evidence_pack.get("facts", []):
        if str(fact.get("type")) == "brand":
            brand = str(fact.get("normalized_value") or fact.get("value") or "").strip()
            if brand:
                fact_brand = brand
                break

    host_brand = _brand_from_url(str(evidence_pack.get("raw_url") or evidence_pack.get("canonical_url") or ""))
    if (
        host_brand
        and host_brand.casefold() not in MARKETPLACE_HOST_TOKENS
        and fact_brand
        and fact_brand.casefold() != host_brand.casefold()
    ):
        product_tokens = canonical_product_name(evidence_pack).casefold().split()
        if product_tokens and fact_brand.casefold() == product_tokens[0]:
            return host_brand

    return fact_brand or host_brand


def short_product_name(product_name: str, brand: str) -> str:
    tokens = product_name.split()
    if tokens and brand and tokens[0].casefold() == brand.casefold() and len(tokens) > 1:
        return " ".join(tokens[1:])
    return product_name


def is_valid_competitor_keyword(keyword: str, *, evidence_pack: dict[str, Any]) -> bool:
    lowered = " ".join(keyword.split()).strip().casefold()
    if not lowered:
        return False
    if _contains_measurement_token(keyword):
        return False
    if any(token in lowered for token in ("용량 비교", "옵션 비교", "라인 비교", "가격 비교")):
        return False
    competitor_terms = competitor_brand_terms(evidence_pack)
    matched_brand = next((term for term in competitor_terms if term.casefold() in lowered), "")
    if not matched_brand:
        return False
    current_brand = canonical_brand(evidence_pack).casefold()
    if current_brand and current_brand in lowered and matched_brand.casefold() == current_brand:
        return False
    if len(_tokens(keyword)) < 2:
        return False
    generic_categories = generic_category_terms(evidence_pack)
    if generic_categories and not any(category.casefold() in lowered for category in generic_categories):
        return False
    return True


def malformed_positive_row_count(rows: list[KeywordRow], *, evidence_pack: dict[str, Any], platform: str) -> int:
    count = 0
    for row in rows:
        if row.category == "negative":
            continue
        if platform == "naver_sa" and not row.naver_match:
            continue
        if platform == "google_sa" and not row.google_match:
            continue
        if keyword_policy_issues(row, evidence_pack=evidence_pack):
            count += 1
    return count


def invalid_negative_row_count(rows: list[KeywordRow], *, evidence_pack: dict[str, Any], platform: str) -> int:
    count = 0
    for row in rows:
        if row.category != "negative":
            continue
        if platform == "naver_sa" and row.naver_match != "제외키워드":
            continue
        if platform == "google_sa" and row.google_match != "negative":
            continue
        if keyword_policy_issues(row, evidence_pack=evidence_pack):
            count += 1
    return count


@lru_cache(maxsize=8)
def _load_taxonomy_group(group_name: str) -> list[dict[str, Any]]:
    path = _taxonomy_dir() / f"{group_name}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"taxonomy group {group_name} must be a list")
    return [entry for entry in payload if isinstance(entry, dict)]


def _taxonomy_dir() -> Path:
    return Path(__file__).resolve().parent / "taxonomy_data"


def _evidence_text(evidence_pack: dict[str, Any]) -> str:
    parts = [
        canonical_product_name(evidence_pack),
        str(evidence_pack.get("page_class") or ""),
        str(evidence_pack.get("raw_url") or evidence_pack.get("canonical_url") or ""),
    ]
    parts.extend(
        str(fact.get("normalized_value") or fact.get("value") or "")
        for fact in evidence_pack.get("facts", [])
    )
    return " ".join(parts).casefold()


def _tokens(keyword: str) -> list[str]:
    normalized = keyword.replace("’", "'")
    pattern = r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[가-힣]+"
    return [token.casefold() for token in re.findall(pattern, normalized)]


def _tokens(keyword: str) -> list[str]:
    normalized = keyword.replace("ĄŻ", "'")
    pattern = r"[A-Za-z0-9가-힣]+(?:'[A-Za-z0-9가-힣]+)?"
    return [token.casefold() for token in re.findall(pattern, normalized)]


def _contains_measurement_token(keyword: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s?(?:ml|g|kg|inch|in|gb|tb|mah|hz|w)\b", keyword, flags=re.IGNORECASE))


def _unique_terms(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            continue
        lowered = cleaned.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(cleaned)
    return unique


def _brand_from_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    host = urlparse(raw_url).hostname or ""
    labels = [label for label in host.split(".") if label and label not in {"www", "m", "kr", "ko", "com", "co"}]
    if not labels:
        return ""
    return labels[0]
