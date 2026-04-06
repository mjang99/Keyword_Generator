from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from src.keyword_generation.constants import POSITIVE_CATEGORIES
from src.keyword_generation.models import KeywordRow

FILLER_SUFFIXES = (
    "특성 검색",
    "카테고리 검색",
    "브랜드 검색",
    "비교 검색",
    "구매 검색",
    "정보 검색",
    "효능 검색",
    "상황 검색",
    "문제 해결",
)
DOC_BOILERPLATE_TOKENS = {
    "지원",
    "사양",
    "기술",
    "download",
    "manual",
    "spec",
    "specs",
}
LIGHTWEIGHT_FILLER_TOKENS = {
    "검색",
    "정리",
    "가이드",
    "카테고리",
    "정보",
    "탐색",
}
MODIFIER_TOKENS = {
    "추천",
    "후기",
    "리뷰",
    "비교",
    "구매",
    "정리",
    "공식",
    "정품",
    "사용감",
    "효과",
    "장점",
    "효능",
    "선택",
    "가이드",
    "정보",
    "스펙",
    "특징",
    "성능",
    "기능",
    "필요",
    "해결",
    "체크",
    "대안",
    "대체",
    "옵션",
    "라인",
    "만족도",
}
SEMANTIC_DUPLICATE_SUFFIX_TOKENS = {
    "추천",
    "후기",
    "리뷰",
    "비교",
    "구매",
    "정품",
    "공식",
}
SUPPORT_PAGE_CLASSES = {
    "support_spec_page",
    "document_download_heavy_support_page",
}
IDEAL_CATEGORY_DISTRIBUTION = {
    "brand": 0.10,
    "generic_category": 0.12,
    "feature_attribute": 0.18,
    "competitor_comparison": 0.08,
    "purchase_intent": 0.12,
    "long_tail": 0.16,
    "benefit_price": 0.06,
    "season_event": 0.06,
    "problem_solution": 0.12,
}


@dataclass(slots=True)
class PerUrlEvaluationInput:
    url_task_id: str
    raw_url: str
    page_class: str
    requested_platform_mode: str
    quality_warning: bool
    rows: list[KeywordRow] = field(default_factory=list)
    status: str = "COMPLETED"


@dataclass(slots=True)
class JobEvaluationInput:
    job_id: str
    requested_platform_mode: str
    successes: list[PerUrlEvaluationInput] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class EvaluationGate:
    pass_: bool
    failure_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvaluationMetrics:
    total_rows: int
    filler_count: int
    filler_ratio: float
    avg_naturalness: float
    exact_unique_ratio: float
    semantic_unique_ratio: float
    reason_filled_ratio: float
    category_distribution_deviation: float
    auto_score: float


@dataclass(slots=True)
class PerUrlEvaluationResult:
    url_task_id: str
    page_class: str
    platform: str
    gate: EvaluationGate
    metrics: EvaluationMetrics
    quality_warning: bool
    duplicate_families: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["gate"]["pass"] = payload["gate"].pop("pass_")
        return payload


@dataclass(slots=True)
class JobEvaluationResult:
    job_id: str
    requested_platform_mode: str
    gate: EvaluationGate
    successful_url_coverage: float
    url_results: list[PerUrlEvaluationResult] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "requested_platform_mode": self.requested_platform_mode,
            "successful_url_coverage": self.successful_url_coverage,
            "url_results": [item.to_dict() for item in self.url_results],
            "failures": self.failures,
            "gate": {
                "pass": self.gate.pass_,
                "failure_reasons": list(self.gate.failure_reasons),
            },
        }


def compute_auto_scores(rows: list[KeywordRow], platform: str, evidence_pack: dict[str, Any]) -> dict[str, Any]:
    per_url = PerUrlEvaluationInput(
        url_task_id=str(evidence_pack.get("url_task_id") or "fixture"),
        raw_url=str(evidence_pack.get("raw_url") or ""),
        page_class=str(evidence_pack.get("page_class") or ""),
        requested_platform_mode=platform,
        quality_warning=bool(evidence_pack.get("quality_warning", False)),
        rows=list(rows),
    )
    result = evaluate_per_url_input(per_url, platform=platform)
    reference_pass = (
        result.metrics.total_rows >= 100
        and result.metrics.filler_ratio < 0.15
        and result.metrics.avg_naturalness >= 0.7
        and result.metrics.exact_unique_ratio >= 0.95
    )
    return {
        "platform": platform,
        "total_rows": result.metrics.total_rows,
        "filler_count": result.metrics.filler_count,
        "filler_ratio": round(result.metrics.filler_ratio, 3),
        "avg_naturalness": round(result.metrics.avg_naturalness, 3),
        "unique_ratio": round(result.metrics.exact_unique_ratio, 3),
        "exact_unique_ratio": round(result.metrics.exact_unique_ratio, 3),
        "semantic_unique_ratio": round(result.metrics.semantic_unique_ratio, 3),
        "reason_filled_ratio": round(result.metrics.reason_filled_ratio, 3),
        "category_distribution_deviation": round(result.metrics.category_distribution_deviation, 3),
        "auto_score": round(result.metrics.auto_score, 1),
        "pass": reference_pass,
        "failure_reasons": list(result.gate.failure_reasons),
    }


def evaluate_job_input(job: JobEvaluationInput) -> JobEvaluationResult:
    platforms = ["naver_sa", "google_sa"] if job.requested_platform_mode == "both" else [job.requested_platform_mode]
    url_results: list[PerUrlEvaluationResult] = []
    for item in job.successes:
        for platform in platforms:
            url_results.append(evaluate_per_url_input(item, platform=platform))

    failure_reasons = [
        f"{result.url_task_id}:{result.platform}:{','.join(result.gate.failure_reasons)}"
        for result in url_results
        if not result.gate.pass_
    ]
    submitted = len(job.successes) + len(job.failures)
    coverage = len(job.successes) / submitted if submitted else 0.0
    return JobEvaluationResult(
        job_id=job.job_id,
        requested_platform_mode=job.requested_platform_mode,
        gate=EvaluationGate(pass_=bool(url_results) and not failure_reasons, failure_reasons=failure_reasons),
        successful_url_coverage=round(coverage, 3),
        url_results=url_results,
        failures=list(job.failures),
    )


def evaluate_per_url_input(item: PerUrlEvaluationInput, *, platform: str) -> PerUrlEvaluationResult:
    platform_rows = [
        row
        for row in item.rows
        if row.category != "negative"
        and (
            (platform == "naver_sa" and bool(row.naver_match))
            or (platform == "google_sa" and bool(row.google_match))
            or (platform == "both" and (bool(row.naver_match) or bool(row.google_match)))
        )
    ]
    total = len(platform_rows)
    if total == 0:
        empty_metrics = EvaluationMetrics(
            total_rows=0,
            filler_count=0,
            filler_ratio=0.0,
            avg_naturalness=0.0,
            exact_unique_ratio=0.0,
            semantic_unique_ratio=0.0,
            reason_filled_ratio=0.0,
            category_distribution_deviation=1.0,
            auto_score=0.0,
        )
        return PerUrlEvaluationResult(
            url_task_id=item.url_task_id,
            page_class=item.page_class,
            platform=platform,
            gate=EvaluationGate(pass_=False, failure_reasons=["no_positive_rows"]),
            metrics=empty_metrics,
            quality_warning=item.quality_warning,
        )

    filler_count = sum(1 for row in platform_rows if _is_filler_keyword(row.keyword))
    naturalness_scores = [_score_keyword_naturalness(row.keyword, page_class=item.page_class) for row in platform_rows]
    avg_naturalness = sum(naturalness_scores) / total
    exact_unique_ratio = len({row.keyword.strip() for row in platform_rows}) / total

    semantic_families = _duplicate_families(platform_rows)
    semantic_unique_ratio = len(semantic_families) / total

    reason_filled_ratio = sum(1 for row in platform_rows if len(row.reason.strip()) > 5) / total
    category_counts: dict[str, int] = {}
    for row in platform_rows:
        category_counts[row.category] = category_counts.get(row.category, 0) + 1

    category_deviation = sum(
        abs(category_counts.get(category, 0) / total - target)
        for category, target in IDEAL_CATEGORY_DISTRIBUTION.items()
    ) / len(IDEAL_CATEGORY_DISTRIBUTION)

    filler_penalty = (filler_count / total) * 60
    naturalness_score = avg_naturalness * 30
    distribution_score = max(0.0, 10 - category_deviation * 100)
    uniqueness_score = semantic_unique_ratio * 10
    reason_score = reason_filled_ratio * 10
    auto_score = max(0.0, naturalness_score + distribution_score + uniqueness_score + reason_score - filler_penalty)

    failure_reasons: list[str] = []
    if total < 100:
        failure_reasons.append("insufficient_positive_rows")
    if filler_count / total >= 0.15:
        failure_reasons.append("high_filler_ratio")
    if avg_naturalness < 0.7:
        failure_reasons.append("low_naturalness")
    if semantic_unique_ratio < 0.95:
        failure_reasons.append("low_semantic_uniqueness")

    metrics = EvaluationMetrics(
        total_rows=total,
        filler_count=filler_count,
        filler_ratio=filler_count / total,
        avg_naturalness=avg_naturalness,
        exact_unique_ratio=exact_unique_ratio,
        semantic_unique_ratio=semantic_unique_ratio,
        reason_filled_ratio=reason_filled_ratio,
        category_distribution_deviation=category_deviation,
        auto_score=min(100.0, auto_score),
    )
    return PerUrlEvaluationResult(
        url_task_id=item.url_task_id,
        page_class=item.page_class,
        platform=platform,
        gate=EvaluationGate(pass_=not failure_reasons, failure_reasons=failure_reasons),
        metrics=metrics,
        quality_warning=item.quality_warning,
        duplicate_families=_render_duplicate_families(semantic_families),
    )


def _duplicate_families(rows: list[KeywordRow]) -> dict[str, list[str]]:
    families: dict[str, list[str]] = {}
    for row in rows:
        signature = _semantic_signature(row.keyword)
        families.setdefault(signature, []).append(row.keyword)
    return families


def _render_duplicate_families(families: dict[str, list[str]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for signature, keywords in families.items():
        if len(keywords) <= 1:
            continue
        rendered.append(
            {
                "signature": signature,
                "count": len(keywords),
                "keywords": keywords[:5],
            }
        )
    rendered.sort(key=lambda item: (-item["count"], item["signature"]))
    return rendered[:10]


def _semantic_signature(keyword: str) -> str:
    tokens = _tokens(keyword)
    normalized = list(tokens)
    while normalized and normalized[-1] in SEMANTIC_DUPLICATE_SUFFIX_TOKENS:
        normalized.pop()
    while normalized and normalized[-1] in LIGHTWEIGHT_FILLER_TOKENS:
        normalized.pop()
    if not normalized:
        normalized = tokens
    return " ".join(normalized)


def _tokens(keyword: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[A-Za-z0-9가-힣]+", keyword)]


def _is_filler_keyword(keyword: str) -> bool:
    if any(suffix in keyword for suffix in FILLER_SUFFIXES):
        return True
    parts = keyword.strip().split()
    if parts and parts[-1].isdigit():
        return True
    tokens = _tokens(keyword)
    if sum(1 for token in tokens if token in LIGHTWEIGHT_FILLER_TOKENS) >= 2:
        return True
    return False


def _score_keyword_naturalness(keyword: str, *, page_class: str) -> float:
    score = 1.0
    if _is_filler_keyword(keyword):
        score -= 0.6

    tokens = _tokens(keyword)
    if len(tokens) != len(set(tokens)):
        score -= 0.2
    if len(keyword.replace(" ", "")) <= 2:
        score -= 0.3
    if len(tokens) >= 9:
        score -= 0.1
    if len(tokens) >= 11:
        score -= 0.1
    if any(token in DOC_BOILERPLATE_TOKENS for token in tokens):
        score -= 0.4
    if page_class not in SUPPORT_PAGE_CLASSES and len(keyword) > 28:
        score -= 0.1

    modifier_count = sum(1 for token in tokens if token in MODIFIER_TOKENS)
    if modifier_count >= 4:
        score -= 0.15
    return max(0.0, score)
