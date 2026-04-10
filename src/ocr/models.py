from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OcrStatus = Literal["SKIPPED", "AVAILABLE"]


@dataclass(slots=True)
class OcrRunResult:
    blocks: list[dict[str, Any]] = field(default_factory=list)
    image_results: list[dict[str, Any]] = field(default_factory=list)
    line_groups: list[dict[str, Any]] = field(default_factory=list)
    direct_fact_candidates: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class OcrDecision:
    status: OcrStatus
    trigger_reasons: list[str] = field(default_factory=list)
    ranked_image_candidates: list[dict[str, Any]] = field(default_factory=list)
    admitted_blocks: list[dict[str, Any]] = field(default_factory=list)
    rejected_blocks: list[dict[str, Any]] = field(default_factory=list)
    contribution_chars: int = 0
    image_results: list[dict[str, Any]] = field(default_factory=list)
    line_groups: list[dict[str, Any]] = field(default_factory=list)
    direct_fact_candidates: list[dict[str, Any]] = field(default_factory=list)
    same_product_metrics: dict[str, Any] = field(default_factory=dict)
