from __future__ import annotations

import json
import os
from typing import Any

from src.clients.bedrock import BedrockRuntimeSettings, converse_text

from .models import CanonicalIntent, DedupQualityReport, GenerationRequest, KeywordRow, PlatformRender

SYSTEM_PROMPT = (
    "You generate paid-search keyword candidates as strict JSON only. "
    "Use only admitted evidence facts. Do not invent prices, discounts, urgency, or unsupported claims."
)

DEDUP_QUALITY_SYSTEM_PROMPT = (
    "You are a paid-search keyword quality reviewer. "
    "Return strict JSON only. "
    "Identify semantic duplicates and score keyword quality. "
    "Do not add new keywords."
)

SUPPLEMENTATION_SYSTEM_PROMPT = (
    "You generate additional paid-search keywords to fill identified gaps. "
    "Return strict JSON only. "
    "Use only admitted evidence facts. Do not invent prices, discounts, urgency, or unsupported claims."
)

_LANGUAGE_POLICY = {
    "allow_mixed": True,
    "brand_model_keep_original_language": True,
    "generic_terms_prefer_korean": True,
    "examples": [
        "나이키 슬리퍼",
        "Nike 슬리퍼",
        "아이폰 16 케이스",
        "iPhone 16 케이스",
        "나이키 에어맥스 남성",
        "Nike Air Max 남성용",
    ],
    "note": "Same concept in Korean and English counts as two distinct keywords and both are encouraged.",
}


def build_keyword_generation_prompt(
    request: GenerationRequest,
    *,
    positive_target: int,
) -> str:
    evidence_pack = request.evidence_pack
    allowed_fields = {
        "raw_url": evidence_pack.get("raw_url"),
        "canonical_url": evidence_pack.get("canonical_url"),
        "page_class": evidence_pack.get("page_class"),
        "product_name": evidence_pack.get("product_name"),
        "locale_detected": evidence_pack.get("locale_detected"),
        "market_locale": evidence_pack.get("market_locale"),
        "sellability_state": evidence_pack.get("sellability_state"),
        "stock_state": evidence_pack.get("stock_state"),
        "sufficiency_state": evidence_pack.get("sufficiency_state"),
        "quality_warning": evidence_pack.get("quality_warning"),
        "facts": evidence_pack.get("facts", []),
    }
    instructions = {
        "requested_platform_mode": request.requested_platform_mode,
        "positive_target_per_platform": positive_target,
        "language_policy": _LANGUAGE_POLICY,
        "output_schema": {
            "intents": [
                {
                    "category": "brand|generic_category|feature_attribute|competitor_comparison|purchase_intent|long_tail|benefit_price|season_event|problem_solution|negative",
                    "intent_text": "platform-neutral intent string",
                    "reason": "string",
                    "evidence_tier": "direct|derived|inferred|weak",
                    "allowed_platforms": ["naver_sa", "google_sa"],
                    "naver_render": {
                        "keyword": "optional string",
                        "match_label": "optional string",
                        "admitted": True,
                    },
                    "google_render": {
                        "keyword": "optional string",
                        "match_label": "optional string",
                        "admitted": True,
                    },
                }
            ],
            "legacy_rows_supported": True,
        },
    }
    return (
        "Return JSON only.\n"
        f"generation_instructions={json.dumps(instructions, ensure_ascii=False)}\n"
        f"evidence_pack={json.dumps(allowed_fields, ensure_ascii=False)}"
    )


def build_dedup_quality_prompt(
    candidates: list[CanonicalIntent],
    *,
    platform_mode: str,
    positive_floor: int = 100,
    positive_category_targets: dict[str, int] | None = None,
) -> str:
    """Build the dedup+quality evaluation prompt (step B of LLM pipeline)."""
    serialized = [
        {
            "intent_text": c.intent_text,
            "category": c.category,
            "evidence_tier": c.evidence_tier,
            "reason": c.reason,
            "naver_keyword": c.naver_render.keyword if c.naver_render else None,
            "google_keyword": c.google_render.keyword if c.google_render else None,
        }
        for c in candidates
    ]
    instructions = {
        "task": "dedup_and_quality_evaluation",
        "platform_mode": platform_mode,
        "positive_floor_per_platform": positive_floor,
        "positive_category_targets": positive_category_targets or {},
        "dedup_rules": [
            "Identify groups of semantically equivalent keywords (same core search intent, different surface form).",
            "Examples of duplicates: 'mens sneaker' / 'men sneaker' / \"men's sneaker\" -> keep one.",
            "Examples of distinct: '나이키 슬리퍼' / '나이키 슬리퍼 남성' -> keep both (modifier changes intent).",
            "Prefer the representative that is most natural for Korean search behavior.",
            "Among ties prefer the candidate with stronger evidence_tier: direct > derived > inferred > weak.",
        ],
        "quality_rules": [
            "Score each surviving keyword: high / medium / low.",
            "low = generic filler with no product-specific grounding, vague intent, or unlikely search query.",
            "Set keep=false for low-quality keywords. This is a quality gate; do not lower the bar to meet count floors.",
        ],
        "output_schema": {
            "surviving": [
                {
                    "intent_text": "string",
                    "category": "string",
                    "evidence_tier": "string",
                    "quality_score": "high|medium|low",
                    "quality_reason": "string",
                    "keep": True,
                }
            ],
            "dropped_duplicates": [
                {"intent_text": "string", "duplicate_of": "string", "reason": "string"}
            ],
            "dropped_low_quality": [
                {"intent_text": "string", "quality_score": "string", "reason": "string"}
            ],
            "gap_report": {
                "<category_name>": "<missing_count_int>",
                "_total": "<total_missing_int>",
            },
        },
    }
    return (
        "Return JSON only.\n"
        f"dedup_quality_instructions={json.dumps(instructions, ensure_ascii=False)}\n"
        f"candidates={json.dumps(serialized, ensure_ascii=False)}"
    )


def build_supplementation_prompt(
    gap_report: dict[str, int],
    evidence_pack: dict[str, Any],
    *,
    platform_mode: str,
    surviving_summary: list[dict] | None = None,
) -> str:
    """Build the supplementation prompt (step C of LLM pipeline, runs only when gaps remain)."""
    allowed_fields = {
        "raw_url": evidence_pack.get("raw_url"),
        "canonical_url": evidence_pack.get("canonical_url"),
        "page_class": evidence_pack.get("page_class"),
        "product_name": evidence_pack.get("product_name"),
        "locale_detected": evidence_pack.get("locale_detected"),
        "sellability_state": evidence_pack.get("sellability_state"),
        "stock_state": evidence_pack.get("stock_state"),
        "facts": evidence_pack.get("facts", []),
    }
    # Provide a summary of already-surviving keywords so the LLM avoids re-generating them.
    gap_categories = {k: v for k, v in gap_report.items() if k != "_total" and v > 0}
    instructions = {
        "task": "supplementation",
        "platform_mode": platform_mode,
        "language_policy": _LANGUAGE_POLICY,
        "gap_categories": gap_categories,
        "total_missing": gap_report.get("_total", 0),
        "constraint": (
            "Generate ONLY keywords for the listed gap categories. "
            "Do not regenerate keywords already in the surviving set. "
            "Do not invent promo, price-band, urgency, or competitor claims. "
            "Do not widen evidence ceilings."
        ),
        "already_surviving_count": len(surviving_summary or []),
        "already_surviving_sample": (surviving_summary or [])[:20],
        "output_schema": {
            "intents": [
                {
                    "category": "string",
                    "intent_text": "string",
                    "reason": "string",
                    "evidence_tier": "direct|derived|inferred|weak",
                    "allowed_platforms": ["naver_sa", "google_sa"],
                    "naver_render": {"keyword": "string", "match_label": "string", "admitted": True},
                    "google_render": {"keyword": "string", "match_label": "string", "admitted": True},
                }
            ]
        },
    }
    return (
        "Return JSON only.\n"
        f"supplementation_instructions={json.dumps(instructions, ensure_ascii=False)}\n"
        f"evidence_pack={json.dumps(allowed_fields, ensure_ascii=False)}"
    )


def parse_intent_response(
    response_text: str,
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise ValueError("Bedrock response must be a JSON object")

    if isinstance(payload.get("intents"), list):
        return _parse_intents(payload["intents"], request=request)

    if isinstance(payload.get("rows"), list):
        return _upgrade_legacy_rows(payload["rows"], request=request)

    raise ValueError("Bedrock response must include intents[] or rows[]")


def parse_dedup_quality_response(
    response_text: str,
    *,
    platform: str,
    all_candidates: list[CanonicalIntent],
    request: GenerationRequest,
) -> DedupQualityReport:
    """Parse the JSON response from the dedup+quality Bedrock call."""
    payload = json.loads(response_text)
    if not isinstance(payload, dict):
        raise ValueError("Dedup quality response must be a JSON object")

    # Build a lookup from intent_text to original CanonicalIntent for surviving reconstruction.
    candidate_map = {c.intent_text: c for c in all_candidates}

    surviving_raw = payload.get("surviving") or []
    surviving: list[CanonicalIntent] = []
    for item in surviving_raw:
        if not isinstance(item, dict):
            continue
        keep = item.get("keep", True)
        if not keep:
            continue
        intent_text = str(item.get("intent_text") or "")
        original = candidate_map.get(intent_text)
        if original is not None:
            surviving.append(original)
        else:
            # LLM may have slightly altered intent_text; do a best-effort match
            for key, candidate in candidate_map.items():
                if intent_text and intent_text in key or key in intent_text:
                    surviving.append(candidate)
                    break

    dropped_duplicates = [d for d in (payload.get("dropped_duplicates") or []) if isinstance(d, dict)]
    dropped_low_quality = [d for d in (payload.get("dropped_low_quality") or []) if isinstance(d, dict)]
    gap_report = {k: int(v) for k, v in (payload.get("gap_report") or {}).items() if isinstance(v, (int, float))}

    return DedupQualityReport(
        platform=platform,
        surviving_keywords=surviving,
        dropped_duplicates=dropped_duplicates,
        dropped_low_quality=dropped_low_quality,
        gap_report=gap_report,
    )


def parse_keyword_response(
    response_text: str,
    *,
    request: GenerationRequest,
) -> list[KeywordRow]:
    intents = parse_intent_response(response_text, request=request)
    return intents_to_rows(intents, request=request)


def should_use_bedrock() -> bool:
    return os.environ.get("KEYWORD_GENERATOR_GENERATION_MODE", "").strip().lower() == "bedrock"


def generate_intents_via_bedrock(
    request: GenerationRequest,
    *,
    positive_target: int,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
) -> list[CanonicalIntent]:
    prompt = build_keyword_generation_prompt(request, positive_target=positive_target)
    _, text = converse_text(
        prompt,
        settings=settings,
        system_prompt=SYSTEM_PROMPT,
        client=client,
    )
    return parse_intent_response(text, request=request)


def run_dedup_quality_pass(
    candidates: list[CanonicalIntent],
    *,
    request: GenerationRequest,
    platform: str,
    positive_floor: int = 100,
    positive_category_targets: dict[str, int] | None = None,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
) -> DedupQualityReport:
    """Step B: LLM semantic dedup + quality evaluation."""
    prompt = build_dedup_quality_prompt(
        candidates,
        platform_mode=platform,
        positive_floor=positive_floor,
        positive_category_targets=positive_category_targets,
    )
    _, text = converse_text(
        prompt,
        settings=settings,
        system_prompt=DEDUP_QUALITY_SYSTEM_PROMPT,
        client=client,
    )
    return parse_dedup_quality_response(text, platform=platform, all_candidates=candidates, request=request)


def run_supplementation_pass(
    gap_report: dict[str, int],
    *,
    request: GenerationRequest,
    platform: str,
    surviving_summary: list[dict] | None = None,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
) -> list[CanonicalIntent]:
    """Step C: LLM targeted supplementation for gap categories (conditional)."""
    prompt = build_supplementation_prompt(
        gap_report,
        request.evidence_pack,
        platform_mode=platform,
        surviving_summary=surviving_summary,
    )
    _, text = converse_text(
        prompt,
        settings=settings,
        system_prompt=SUPPLEMENTATION_SYSTEM_PROMPT,
        client=client,
    )
    return parse_intent_response(text, request=request)


def generate_rows_via_bedrock(
    request: GenerationRequest,
    *,
    positive_target: int,
    client: Any | None = None,
    settings: BedrockRuntimeSettings | None = None,
) -> list[KeywordRow]:
    intents = generate_intents_via_bedrock(
        request,
        positive_target=positive_target,
        client=client,
        settings=settings,
    )
    return intents_to_rows(intents, request=request)


def intents_to_rows(
    intents: list[CanonicalIntent],
    *,
    request: GenerationRequest,
) -> list[KeywordRow]:
    quality_warning = bool(request.evidence_pack.get("quality_warning", False))
    product_name = str(
        request.evidence_pack.get("canonical_product_name")
        or request.evidence_pack.get("product_name")
        or request.evidence_pack.get("raw_url")
        or "product"
    )
    raw_url = str(request.evidence_pack.get("raw_url") or request.evidence_pack.get("canonical_url") or "")

    rows: list[KeywordRow] = []
    for intent in intents:
        naver_render = intent.naver_render
        google_render = intent.google_render

        include_naver = bool(naver_render and naver_render.admitted and naver_render.keyword and naver_render.match_label)
        include_google = bool(google_render and google_render.admitted and google_render.keyword and google_render.match_label)

        if include_naver and include_google and naver_render.keyword == google_render.keyword:
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=intent.category,
                    keyword=naver_render.keyword,
                    naver_match=naver_render.match_label,
                    google_match=google_render.match_label,
                    reason=intent.reason,
                    quality_warning=quality_warning,
                    evidence_tier=intent.evidence_tier,
                )
            )
            continue

        if include_naver:
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=intent.category,
                    keyword=naver_render.keyword,
                    naver_match=naver_render.match_label,
                    google_match="",
                    reason=intent.reason,
                    quality_warning=quality_warning,
                    evidence_tier=intent.evidence_tier,
                )
            )
        if include_google:
            rows.append(
                KeywordRow(
                    url=raw_url,
                    product_name=product_name,
                    category=intent.category,
                    keyword=google_render.keyword,
                    naver_match="",
                    google_match=google_render.match_label,
                    reason=intent.reason,
                    quality_warning=quality_warning,
                    evidence_tier=intent.evidence_tier,
                )
            )

    return rows


def _parse_intents(
    payload_intents: list[Any],
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    intents: list[CanonicalIntent] = []
    for raw_intent in payload_intents:
        if not isinstance(raw_intent, dict):
            continue
        naver_render = _parse_render(raw_intent.get("naver_render"))
        google_render = _parse_render(raw_intent.get("google_render"))
        allowed_platforms = [
            str(platform)
            for platform in raw_intent.get("allowed_platforms", [])
            if str(platform) in {"naver_sa", "google_sa"}
        ]
        if not allowed_platforms:
            if naver_render:
                allowed_platforms.append("naver_sa")
            if google_render:
                allowed_platforms.append("google_sa")

        intents.append(
            CanonicalIntent(
                category=str(raw_intent.get("category") or ""),
                intent_text=str(raw_intent.get("intent_text") or ""),
                reason=str(raw_intent.get("reason") or ""),
                evidence_tier=str(raw_intent.get("evidence_tier") or "") or None,
                allowed_platforms=allowed_platforms,
                naver_render=naver_render,
                google_render=google_render,
            )
        )
    return intents


def _parse_render(render_payload: Any) -> PlatformRender | None:
    if not isinstance(render_payload, dict):
        return None
    keyword = str(render_payload.get("keyword") or "")
    match_label = str(render_payload.get("match_label") or "")
    admitted = bool(render_payload.get("admitted", True))
    if not keyword or not match_label:
        return None
    return PlatformRender(keyword=keyword, match_label=match_label, admitted=admitted)


def _upgrade_legacy_rows(
    payload_rows: list[Any],
    *,
    request: GenerationRequest,
) -> list[CanonicalIntent]:
    intents: list[CanonicalIntent] = []
    for raw_row in payload_rows:
        if not isinstance(raw_row, dict):
            continue
        naver_match = str(raw_row.get("naver_match") or "")
        google_match = str(raw_row.get("google_match") or "")
        keyword = str(raw_row.get("keyword") or "")
        allowed_platforms: list[str] = []
        naver_render = None
        google_render = None
        if keyword and naver_match:
            naver_render = PlatformRender(keyword=keyword, match_label=naver_match, admitted=True)
            allowed_platforms.append("naver_sa")
        if keyword and google_match:
            google_render = PlatformRender(keyword=keyword, match_label=google_match, admitted=True)
            allowed_platforms.append("google_sa")
        intents.append(
            CanonicalIntent(
                category=str(raw_row.get("category") or ""),
                intent_text=keyword,
                reason=str(raw_row.get("reason") or ""),
                evidence_tier=str(raw_row.get("evidence_tier") or "") or None,
                allowed_platforms=allowed_platforms,
                naver_render=naver_render,
                google_render=google_render,
            )
        )
    return intents
