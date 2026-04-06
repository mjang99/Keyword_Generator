from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PlatformMode = Literal["naver_sa", "google_sa", "both"]
TerminalGenerationStatus = Literal["COMPLETED", "FAILED_GENERATION"]


@dataclass(slots=True)
class KeywordRow:
    url: str
    product_name: str
    category: str
    keyword: str
    naver_match: str = ""
    google_match: str = ""
    reason: str = ""
    quality_warning: bool = False
    evidence_tier: str | None = None


@dataclass(slots=True)
class PlatformRender:
    keyword: str
    match_label: str
    admitted: bool = True


@dataclass(slots=True)
class CanonicalIntent:
    category: str
    reason: str
    evidence_tier: str | None = None
    intent_text: str = ""
    allowed_platforms: list[PlatformMode] = field(default_factory=list)
    naver_render: PlatformRender | None = None
    google_render: PlatformRender | None = None


@dataclass(slots=True)
class GenerationRequest:
    evidence_pack: dict[str, Any]
    requested_platform_mode: PlatformMode
    max_keywords_per_platform: int = 100
    # initial_generation_target: over-generate to absorb semantic dedup loss
    initial_generation_target: int = 130
    supplementation_pass_limit: int = 1

    @property
    def repair_pass_limit(self) -> int:
        return self.supplementation_pass_limit

    @repair_pass_limit.setter
    def repair_pass_limit(self, value: int) -> None:
        self.supplementation_pass_limit = value


@dataclass(slots=True)
class DedupQualityReport:
    """Output of Bedrock dedup+quality pass (step B in LLM pipeline)."""

    platform: str
    surviving_keywords: list[CanonicalIntent] = field(default_factory=list)
    dropped_duplicates: list[dict] = field(default_factory=list)
    dropped_low_quality: list[dict] = field(default_factory=list)
    # gap_report: {category: missing_count, "_total": N}
    gap_report: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationReport:
    status: TerminalGenerationStatus
    requested_platform_mode: PlatformMode
    positive_keyword_counts: dict[str, int] = field(default_factory=dict)
    category_counts: dict[str, dict[str, int]] = field(default_factory=dict)
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

    @property
    def repair_attempts(self) -> int:
        return self.supplementation_attempts

    @repair_attempts.setter
    def repair_attempts(self, value: int) -> None:
        self.supplementation_attempts = value
