from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.exporting.models import NotificationTarget

UrlTaskTerminalStatus = Literal[
    "COMPLETED",
    "COMPLETED_CACHED",
    "FAILED_COLLECTION",
    "FAILED_GENERATION",
]
JobLifecycleStatus = Literal["RECEIVED", "PROCESSING", "COMPLETED", "PARTIAL_COMPLETED", "FAILED"]


@dataclass(slots=True)
class LocalResolvedSuccess:
    evidence_pack: dict[str, Any]
    snapshot: dict[str, Any] | None = None
    classification: dict[str, Any] | None = None
    ocr_result: dict[str, Any] | None = None


@dataclass(slots=True)
class LocalResolvedFailure:
    failure_code: str
    failure_detail: str
    failure_reason_hints: list[str] | None = None
    page_class: str | None = None
    quality_warning: bool | None = None
    snapshot: dict[str, Any] | None = None
    classification: dict[str, Any] | None = None
    ocr_result: dict[str, Any] | None = None


@dataclass(slots=True)
class RuntimeNotificationRecord:
    job_id: str
    status: str
    payload: dict[str, Any]
    target: NotificationTarget
