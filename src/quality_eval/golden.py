from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.keyword_generation.models import KeywordRow


@dataclass(slots=True)
class GoldenPlatformExpectation:
    must_keep: list[str] = field(default_factory=list)
    must_not_emit: list[str] = field(default_factory=list)
    forbidden_substrings: list[str] = field(default_factory=list)
    required_categories: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GoldenSetCase:
    case_id: str
    source_path: str
    requested_platform_mode: str
    notes: str = ""
    platform_expectations: dict[str, GoldenPlatformExpectation] = field(default_factory=dict)


@dataclass(slots=True)
class GoldenPlatformResult:
    platform: str
    observed_positive_count: int
    missing_must_keep: list[str] = field(default_factory=list)
    emitted_forbidden_keywords: list[str] = field(default_factory=list)
    emitted_forbidden_substrings: list[str] = field(default_factory=list)
    missing_categories: list[str] = field(default_factory=list)

    @property
    def pass_(self) -> bool:
        return not (
            self.missing_must_keep
            or self.emitted_forbidden_keywords
            or self.emitted_forbidden_substrings
            or self.missing_categories
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pass"] = self.pass_
        return payload


@dataclass(slots=True)
class GoldenSetEvaluation:
    case_id: str
    source_path: str
    requested_platform_mode: str
    generation_status: str
    platform_results: list[GoldenPlatformResult] = field(default_factory=list)

    @property
    def pass_(self) -> bool:
        return bool(self.platform_results) and all(item.pass_ for item in self.platform_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_path": self.source_path,
            "requested_platform_mode": self.requested_platform_mode,
            "generation_status": self.generation_status,
            "pass": self.pass_,
            "platform_results": [item.to_dict() for item in self.platform_results],
        }


def load_golden_set_case(path: str | Path) -> GoldenSetCase:
    case_path = Path(path)
    with case_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    expectations: dict[str, GoldenPlatformExpectation] = {}
    for platform, config in (payload.get("platform_expectations") or {}).items():
        expectations[str(platform)] = GoldenPlatformExpectation(
            must_keep=[str(value) for value in config.get("must_keep", [])],
            must_not_emit=[str(value) for value in config.get("must_not_emit", [])],
            forbidden_substrings=[str(value) for value in config.get("forbidden_substrings", [])],
            required_categories=[str(value) for value in config.get("required_categories", [])],
        )

    return GoldenSetCase(
        case_id=str(payload.get("case_id") or case_path.stem),
        source_path=str(payload["source_path"]),
        requested_platform_mode=str(payload.get("requested_platform_mode") or "both"),
        notes=str(payload.get("notes") or ""),
        platform_expectations=expectations,
    )


def load_golden_source_payload(case: GoldenSetCase, *, repo_root: str | Path) -> dict[str, Any]:
    source_path = Path(repo_root) / case.source_path
    with source_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_golden_set(
    case: GoldenSetCase,
    *,
    rows: list[KeywordRow],
    generation_status: str,
) -> GoldenSetEvaluation:
    platforms = ["naver_sa", "google_sa"] if case.requested_platform_mode == "both" else [case.requested_platform_mode]
    platform_results: list[GoldenPlatformResult] = []

    for platform in platforms:
        expectation = case.platform_expectations.get(platform) or GoldenPlatformExpectation()
        platform_rows = _positive_rows_for_platform(rows, platform)
        normalized_keywords = {_normalize_keyword(row.keyword): row.keyword for row in platform_rows}
        categories = {row.category for row in platform_rows}

        missing_must_keep = [
            keyword for keyword in expectation.must_keep if _normalize_keyword(keyword) not in normalized_keywords
        ]
        emitted_forbidden_keywords = [
            row.keyword
            for row in platform_rows
            if _normalize_keyword(row.keyword) in {_normalize_keyword(keyword) for keyword in expectation.must_not_emit}
        ]
        emitted_forbidden_substrings = [
            row.keyword
            for row in platform_rows
            if any(
                _normalize_keyword(fragment) in _normalize_keyword(row.keyword)
                for fragment in expectation.forbidden_substrings
            )
        ]
        missing_categories = [category for category in expectation.required_categories if category not in categories]

        platform_results.append(
            GoldenPlatformResult(
                platform=platform,
                observed_positive_count=len(platform_rows),
                missing_must_keep=missing_must_keep,
                emitted_forbidden_keywords=_unique_texts(emitted_forbidden_keywords),
                emitted_forbidden_substrings=_unique_texts(emitted_forbidden_substrings),
                missing_categories=missing_categories,
            )
        )

    return GoldenSetEvaluation(
        case_id=case.case_id,
        source_path=case.source_path,
        requested_platform_mode=case.requested_platform_mode,
        generation_status=generation_status,
        platform_results=platform_results,
    )


def _positive_rows_for_platform(rows: list[KeywordRow], platform: str) -> list[KeywordRow]:
    if platform == "naver_sa":
        return [row for row in rows if row.category != "negative" and bool(row.naver_match)]
    return [row for row in rows if row.category != "negative" and bool(row.google_match)]


def _normalize_keyword(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("|", " ").replace("/", " ").replace("_", " ")
    return " ".join(normalized.casefold().split())


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = _normalize_keyword(value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
