from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.keyword_generation.models import GenerationResult

NotificationTargetType = Literal["email", "webhook"]
JobTerminalStatus = Literal["COMPLETED", "PARTIAL_COMPLETED", "FAILED"]


@dataclass(slots=True)
class NotificationTarget:
    target_type: NotificationTargetType
    value: str


@dataclass(slots=True)
class JobArtifactUrls:
    result_manifest_url: str | None = None
    combined_json_url: str | None = None
    combined_csv_url: str | None = None
    failures_json_url: str | None = None


@dataclass(slots=True)
class UrlExportResult:
    url_task_id: str
    raw_url: str
    page_class: str
    requested_platform_mode: str
    generation_result: GenerationResult
    cache_hit: bool = False


@dataclass(slots=True)
class UrlFailureResult:
    url_task_id: str
    raw_url: str
    page_class: str | None
    requested_platform_mode: str
    failure_code: str
    failure_detail: str
    quality_warning: bool | None = None
