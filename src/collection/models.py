from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NormalizedPageSnapshot:
    raw_url: str
    canonical_url: str
    page_class_hint: str
    final_url: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    fetch_profile_used: str | None = None
    fetched_at: str | None = None
    charset_selected: str | None = None
    charset_confidence: float | None = None
    mojibake_flags: list[str] = field(default_factory=list)
    meta_locale: str | None = None
    language_scores: dict[str, float] = field(default_factory=dict)
    title: str | None = None
    meta_description: str | None = None
    canonical_tag: str | None = None
    decoded_text: str | None = None
    visible_text_blocks: list[str] = field(default_factory=list)
    breadcrumbs: list[str] = field(default_factory=list)
    structured_data: list[dict[str, Any]] = field(default_factory=list)
    primary_product_tokens: list[str] = field(default_factory=list)
    price_signals: list[str] = field(default_factory=list)
    buy_signals: list[str] = field(default_factory=list)
    stock_signals: list[str] = field(default_factory=list)
    promo_signals: list[str] = field(default_factory=list)
    support_signals: list[str] = field(default_factory=list)
    download_signals: list[str] = field(default_factory=list)
    blocker_signals: list[str] = field(default_factory=list)
    waiting_signals: list[str] = field(default_factory=list)
    image_candidates: list[dict[str, Any]] = field(default_factory=list)
    ocr_trigger_reasons: list[str] = field(default_factory=list)
    single_product_confidence: float | None = None
    sellability_confidence: float | None = None
    support_density: float | None = None
    download_density: float | None = None
    promo_density: float | None = None
    usable_text_chars: int | None = None
    product_name: str | None = None
    locale_detected: str | None = None
    market_locale: str | None = None
    sellability_state: str | None = None
    stock_state: str | None = None
    sufficiency_state: str | None = None
    quality_warning: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    preprocessing_source: str | None = None
    weak_backfill_used: bool = False
    facts: list[dict[str, Any]] = field(default_factory=list)
    ocr_text_blocks: list[dict[str, Any]] = field(default_factory=list)
    ocr_image_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PageClassification:
    page_class: str
    supported_for_generation: bool
    confidence: float
    decisive_signals: list[str] = field(default_factory=list)
    failure_code_candidate: str | None = None
    bedrock_gate_override: bool = False
