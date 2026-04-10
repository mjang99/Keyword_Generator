from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .constants import INITIAL_GENERATION_TARGET

PlatformMode = Literal["naver_sa", "google_sa", "both"]
TerminalGenerationStatus = Literal["COMPLETED", "FAILED_GENERATION"]


@dataclass(slots=True)
class KeywordRow:
    url: str
    product_name: str
    category: str
    keyword: str
    slot_type: str | None = None
    naver_match: str = ""
    google_match: str = ""
    reason: str = ""
    quality_warning: bool = False
    evidence_tier: str | None = None
    quality_score: str | None = None
    quality_reason: str | None = None
    selection_score: float | None = None
    soft_penalties: tuple[str, ...] = ()


@dataclass(slots=True)
class PlatformRender:
    keyword: str
    match_label: str
    admitted: bool = True


@dataclass(slots=True)
class SharedRender:
    keyword: str
    admitted: bool = True


@dataclass(slots=True)
class CanonicalIntent:
    category: str
    reason: str
    slot_type: str = ""
    evidence_tier: str | None = None
    quality_score: str | None = None
    quality_reason: str | None = None
    selection_score: float | None = None
    soft_penalties: tuple[str, ...] = ()
    intent_text: str = ""
    intent_id: str = ""
    allowed_platforms: list[PlatformMode] = field(default_factory=list)
    shared_render: SharedRender | None = None
    naver_render: PlatformRender | None = None
    google_render: PlatformRender | None = None


@dataclass(slots=True)
class GenerationRequest:
    evidence_pack: dict[str, Any]
    requested_platform_mode: PlatformMode
    max_keywords_per_platform: int = 100
    # initial_generation_target: over-generate to absorb semantic dedup loss
    initial_generation_target: int = INITIAL_GENERATION_TARGET
    supplementation_pass_limit: int = 2

    @property
    def repair_pass_limit(self) -> int:
        return self.supplementation_pass_limit

    @repair_pass_limit.setter
    def repair_pass_limit(self, value: int) -> None:
        self.supplementation_pass_limit = value


@dataclass(slots=True)
class SlotPlanItem:
    category: str
    slot_type: str
    target_count: int
    required: bool = False
    seed_phrases: list[str] = field(default_factory=list)
    allowed_shapes: list[str] = field(default_factory=list)
    forbidden_shapes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DedupQualityReport:
    """Output of Bedrock dedup+quality pass (step B in LLM pipeline)."""

    platform: str
    surviving_keywords: list[CanonicalIntent] = field(default_factory=list)
    dropped_duplicates: list[dict] = field(default_factory=list)
    dropped_low_quality: list[dict] = field(default_factory=list)
    # slot_gap_report: {"category:slot_type": missing_count, "_total": N}
    slot_gap_report: dict[str, int] = field(default_factory=dict)

    @property
    def gap_report(self) -> dict[str, int]:
        return self.slot_gap_report


@dataclass(slots=True)
class ValidationReport:
    status: TerminalGenerationStatus
    requested_platform_mode: PlatformMode
    positive_keyword_counts: dict[str, int] = field(default_factory=dict)
    category_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    missing_positive_categories: dict[str, list[str]] = field(default_factory=dict)
    weak_tier_ratio_by_platform: dict[str, float] = field(default_factory=dict)
    failure_code: str | None = None
    failure_detail: str | None = None
    quality_warning: bool = False


@dataclass(slots=True)
class GenerationResult:
    status: TerminalGenerationStatus
    requested_platform_mode: PlatformMode
    rows: list[KeywordRow] = field(default_factory=list)
    intents: list[CanonicalIntent] = field(default_factory=list)
    supplementation_attempts: int = 0
    validation_report: ValidationReport | None = None
    debug_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def repair_attempts(self) -> int:
        return self.supplementation_attempts

    @repair_attempts.setter
    def repair_attempts(self, value: int) -> None:
        self.supplementation_attempts = value
