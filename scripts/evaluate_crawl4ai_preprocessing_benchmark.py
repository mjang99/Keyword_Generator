from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from scripts.evaluate_collection_fetch_benchmark import _build_case_matrix
from src.collection import Crawl4AiPageFetcher, FixtureHtmlFetcher, collect_snapshot_from_html
from src.collection.models import NormalizedPageSnapshot, PageClassification
from src.collection.service import (
    BLOCKER_HTML_PATTERNS,
    BLOCKER_PATTERNS,
    BUY_PATTERNS,
    DOWNLOAD_PATTERNS,
    PRICE_PATTERNS,
    PROMO_PATTERNS,
    STOCK_PATTERNS,
    SUPPORT_PATTERNS,
    SUPPORTED_PAGE_CLASSES,
    WAITING_PATTERNS,
    HtmlFetchResult,
    classify_snapshot,
    _classify_html,
    _dedupe_strings,
    _density,
    _extract_visible_text,
    _find_matches,
    _language_scores,
    _meaningful_visible_blocks_v2,
    _product_tokens,
    _sellability_confidence,
    _single_product_confidence,
)
from src.evidence.service import build_evidence_pack
from src.ocr import OcrRunResult
from src.ocr.models import OcrDecision
from src.ocr.service import run_ocr_policy


PREPROCESSING_CANDIDATE_SOURCES = (
    "raw_html",
    "cleaned_html",
    "markdown",
    "fit_markdown",
)

PREPROCESSING_BENCHMARK_COLUMNS = (
    "case_id",
    "case_type",
    "candidate_source",
    "fetch_mode",
    "final_url",
    "http_status",
    "page_class",
    "supported_for_generation",
    "decoded_text_chars",
    "visible_block_count",
    "structured_data_count",
    "image_candidate_count",
    "ocr_trigger_reasons",
    "evidence_fact_count",
    "quality_warning",
    "elapsed_seconds",
    "source_loss_notes",
    "recommendation_flag",
)

ARTIFACTS_DIR = Path("artifacts") / "crawl4ai_preprocessing_benchmark"


def build_preprocessed_snapshot(
    *,
    fetch_result: HtmlFetchResult,
    baseline_snapshot: NormalizedPageSnapshot,
    candidate_source: str,
    sidecars: dict[str, Any] | None,
) -> tuple[NormalizedPageSnapshot, str]:
    if candidate_source not in PREPROCESSING_CANDIDATE_SOURCES:
        raise ValueError(f"unsupported candidate_source: {candidate_source}")

    decoded_text, source_loss_notes = _resolved_candidate_text(
        fetch_result=fetch_result,
        baseline_snapshot=baseline_snapshot,
        candidate_source=candidate_source,
        sidecars=sidecars,
    )
    visible_text_blocks = _meaningful_visible_blocks_v2(decoded_text)
    lowered = " ".join(
        part for part in (baseline_snapshot.title or "", baseline_snapshot.meta_description or "", decoded_text) if part
    ).lower()

    price_signals = _find_matches(lowered, PRICE_PATTERNS, regex=True)
    buy_signals = _find_matches(lowered, BUY_PATTERNS)
    stock_signals = _find_matches(lowered, STOCK_PATTERNS)
    promo_signals = _find_matches(lowered, PROMO_PATTERNS)
    support_signals = _find_matches(lowered, SUPPORT_PATTERNS)
    download_signals = _find_matches(lowered, DOWNLOAD_PATTERNS)
    blocker_signals = _dedupe_strings(
        [
            *_find_matches(lowered, BLOCKER_PATTERNS),
            *_find_matches(fetch_result.html.lower(), BLOCKER_HTML_PATTERNS),
        ]
    )
    waiting_signals = _find_matches(lowered, WAITING_PATTERNS)
    primary_product_tokens = _product_tokens(
        baseline_snapshot.title,
        baseline_snapshot.meta_description,
        baseline_snapshot.product_name,
    )
    usable_text_chars = len(decoded_text)
    support_density = _density(len(support_signals), usable_text_chars)
    download_density = _density(len(download_signals), usable_text_chars)
    promo_density = _density(len(promo_signals), usable_text_chars)
    single_product_confidence = _single_product_confidence(
        title=baseline_snapshot.title,
        product_name=baseline_snapshot.product_name,
        decoded_text=decoded_text,
        final_url=fetch_result.final_url,
        price_signals=price_signals,
        buy_signals=buy_signals,
        primary_product_tokens=primary_product_tokens,
        has_structured_product=bool(baseline_snapshot.structured_data),
    )
    sellability_confidence = _sellability_confidence(price_signals, buy_signals, stock_signals)
    page_class_hint = _classify_html(
        title=baseline_snapshot.title,
        lowered=lowered,
        fetch_result=fetch_result,
        support_signals=support_signals,
        download_signals=download_signals,
        promo_signals=promo_signals,
        blocker_signals=blocker_signals,
        waiting_signals=waiting_signals,
        price_signals=price_signals,
        buy_signals=buy_signals,
        single_product_confidence=single_product_confidence,
        has_structured_product=bool(baseline_snapshot.structured_data),
        usable_text_chars=usable_text_chars,
    )
    quality_warning = page_class_hint in {"support_spec_page", "document_download_heavy_support_page", "image_heavy_commerce_pdp"}
    ocr_trigger_reasons = ["image_heavy_page"] if page_class_hint == "image_heavy_commerce_pdp" else []
    sellability_state = "sellable" if price_signals or buy_signals else "non_sellable"
    stock_state = "Unknown"
    if any("out of stock" in signal or "품절" in signal for signal in stock_signals):
        stock_state = "OutOfStock"
    elif stock_signals:
        stock_state = "InStock"

    snapshot = replace(
        baseline_snapshot,
        page_class_hint=page_class_hint,
        language_scores=_language_scores(baseline_snapshot.locale_detected, decoded_text),
        decoded_text=decoded_text,
        visible_text_blocks=visible_text_blocks,
        primary_product_tokens=primary_product_tokens,
        price_signals=price_signals,
        buy_signals=buy_signals,
        stock_signals=stock_signals,
        promo_signals=promo_signals,
        support_signals=support_signals,
        download_signals=download_signals,
        blocker_signals=blocker_signals,
        waiting_signals=waiting_signals,
        ocr_trigger_reasons=ocr_trigger_reasons,
        single_product_confidence=single_product_confidence,
        sellability_confidence=sellability_confidence,
        support_density=support_density,
        download_density=download_density,
        promo_density=promo_density,
        usable_text_chars=usable_text_chars,
        sellability_state=sellability_state,
        stock_state=stock_state,
        sufficiency_state="sufficient" if usable_text_chars >= 400 else "borderline",
        quality_warning=quality_warning,
    )
    return snapshot, source_loss_notes


def run_preprocessing_benchmark(
    *,
    include_live: bool = True,
    include_fixtures: bool = True,
) -> dict[str, Any]:
    cases = [
        case
        for case in _build_case_matrix()
        if (include_live or case["case_type"] != "live") and (include_fixtures or case["case_type"] != "fixture")
    ]
    live_fetcher = Crawl4AiPageFetcher()
    rows: list[dict[str, Any]] = []
    parity_reports: list[dict[str, Any]] = []
    case_errors: list[dict[str, Any]] = []

    for case in cases:
        fetch_started = time.perf_counter()
        try:
            fetch_result, sidecars = _fetch_case(case=case, live_fetcher=live_fetcher)
        except Exception as error:
            elapsed_seconds = time.perf_counter() - fetch_started
            case_errors.append(
                {
                    "case_id": case["label"],
                    "case_type": case["case_type"],
                    "error": str(error),
                    "elapsed_seconds": round(elapsed_seconds, 3),
                }
            )
            rows.extend(_failed_case_rows(case=case, error=str(error), elapsed_seconds=elapsed_seconds))
            continue

        baseline_snapshot = collect_snapshot_from_html(fetch_result)
        baseline_classification = _classify_without_bedrock(baseline_snapshot)
        elapsed_seconds = time.perf_counter() - fetch_started

        for candidate_source in PREPROCESSING_CANDIDATE_SOURCES:
            row, parity = evaluate_candidate_outputs(
                case_id=case["label"],
                case_type=case["case_type"],
                fetch_result=fetch_result,
                baseline_snapshot=baseline_snapshot,
                baseline_classification=baseline_classification,
                candidate_source=candidate_source,
                sidecars=sidecars,
                elapsed_seconds=elapsed_seconds,
            )
            rows.append(row)
            parity_reports.append(parity)

        _write_case_artifacts(
            case=case,
            fetch_result=fetch_result,
            baseline_snapshot=baseline_snapshot,
            sidecars=sidecars,
        )

    summary = _summarize_benchmark(rows=rows, parity_reports=parity_reports, case_errors=case_errors)
    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cases": cases,
        "rows": rows,
        "parity_reports": parity_reports,
        "case_errors": case_errors,
        "summary": summary,
    }
    _write_benchmark_artifacts(result)
    return result


def build_preprocessing_benchmark_row(
    *,
    case_id: str,
    case_type: str,
    candidate_source: str,
    fetch_mode: str,
    fetch_result: HtmlFetchResult,
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    ocr_decision: OcrDecision,
    evidence_pack: dict[str, Any],
    elapsed_seconds: float,
    source_loss_notes: str,
    recommendation_flag: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_type": case_type,
        "candidate_source": candidate_source,
        "fetch_mode": fetch_mode,
        "final_url": fetch_result.final_url,
        "http_status": fetch_result.http_status,
        "page_class": classification.page_class,
        "supported_for_generation": classification.supported_for_generation,
        "decoded_text_chars": len(snapshot.decoded_text or ""),
        "visible_block_count": len(snapshot.visible_text_blocks),
        "structured_data_count": len(snapshot.structured_data),
        "image_candidate_count": len(snapshot.image_candidates),
        "ocr_trigger_reasons": list(ocr_decision.trigger_reasons),
        "evidence_fact_count": len(evidence_pack.get("facts", [])),
        "quality_warning": bool(evidence_pack.get("quality_warning", snapshot.quality_warning)),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "source_loss_notes": source_loss_notes,
        "recommendation_flag": recommendation_flag,
    }


def build_snapshot_parity_report(
    *,
    case_id: str,
    candidate_source: str,
    baseline_snapshot: NormalizedPageSnapshot,
    candidate_snapshot: NormalizedPageSnapshot,
    baseline_classification: PageClassification,
    candidate_classification: PageClassification,
    baseline_ocr_decision: OcrDecision,
    candidate_ocr_decision: OcrDecision,
    baseline_evidence_pack: dict[str, Any],
    candidate_evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    baseline_fact_types = {str(fact.get("type", "")) for fact in baseline_evidence_pack.get("facts", [])}
    candidate_fact_types = {str(fact.get("type", "")) for fact in candidate_evidence_pack.get("facts", [])}
    regression_stages: list[str] = []

    if baseline_classification.page_class != candidate_classification.page_class or (
        baseline_classification.supported_for_generation != candidate_classification.supported_for_generation
    ):
        regression_stages.append("classification")
    if list(baseline_ocr_decision.trigger_reasons) != list(candidate_ocr_decision.trigger_reasons):
        regression_stages.append("ocr_trigger")
    if len(baseline_ocr_decision.admitted_blocks) != len(candidate_ocr_decision.admitted_blocks):
        regression_stages.append("ocr_admission")
    if baseline_fact_types != candidate_fact_types or len(baseline_evidence_pack.get("facts", [])) != len(
        candidate_evidence_pack.get("facts", [])
    ):
        regression_stages.append("evidence")

    return {
        "case_id": case_id,
        "candidate_source": candidate_source,
        "decoded_text_chars_delta": len(candidate_snapshot.decoded_text or "") - len(baseline_snapshot.decoded_text or ""),
        "visible_block_count_delta": len(candidate_snapshot.visible_text_blocks) - len(baseline_snapshot.visible_text_blocks),
        "page_class_changed": baseline_classification.page_class != candidate_classification.page_class,
        "supported_changed": (
            baseline_classification.supported_for_generation != candidate_classification.supported_for_generation
        ),
        "ocr_trigger_delta": _sorted_string_delta(
            baseline_ocr_decision.trigger_reasons,
            candidate_ocr_decision.trigger_reasons,
        ),
        "admitted_ocr_block_delta": len(candidate_ocr_decision.admitted_blocks) - len(baseline_ocr_decision.admitted_blocks),
        "evidence_fact_count_delta": len(candidate_evidence_pack.get("facts", []))
        - len(baseline_evidence_pack.get("facts", [])),
        "evidence_types_added": sorted(candidate_fact_types - baseline_fact_types),
        "evidence_types_removed": sorted(baseline_fact_types - candidate_fact_types),
        "regression_stages": regression_stages,
    }


def evaluate_candidate_outputs(
    *,
    case_id: str,
    case_type: str,
    fetch_result: HtmlFetchResult,
    baseline_snapshot: NormalizedPageSnapshot,
    baseline_classification: PageClassification,
    candidate_source: str,
    sidecars: dict[str, Any] | None,
    elapsed_seconds: float,
    ocr_runner: Any | None = None,
    ocr_mode: str = "policy_only",
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_ocr_decision = _resolve_ocr_decision(
        snapshot=baseline_snapshot,
        classification=baseline_classification,
        ocr_runner=ocr_runner,
        ocr_mode=ocr_mode,
    )
    baseline_evidence_pack = build_evidence_pack(
        baseline_snapshot,
        baseline_classification,
        baseline_ocr_decision,
    )
    candidate_snapshot, source_loss_notes = build_preprocessed_snapshot(
        fetch_result=fetch_result,
        baseline_snapshot=baseline_snapshot,
        candidate_source=candidate_source,
        sidecars=sidecars,
    )
    candidate_classification = _classify_without_bedrock(candidate_snapshot)
    candidate_ocr_decision = _resolve_ocr_decision(
        snapshot=candidate_snapshot,
        classification=candidate_classification,
        ocr_runner=ocr_runner,
        ocr_mode=ocr_mode,
    )
    candidate_evidence_pack = build_evidence_pack(candidate_snapshot, candidate_classification, candidate_ocr_decision)
    recommendation_flag = recommend_candidate_source(
        candidate_source=candidate_source,
        baseline_snapshot=baseline_snapshot,
        baseline_classification=baseline_classification,
        candidate_snapshot=candidate_snapshot,
        candidate_classification=candidate_classification,
        baseline_evidence_fact_count=len(baseline_evidence_pack.get("facts", [])),
        candidate_evidence_fact_count=len(candidate_evidence_pack.get("facts", [])),
    )
    row = build_preprocessing_benchmark_row(
        case_id=case_id,
        case_type=case_type,
        candidate_source=candidate_source,
        fetch_mode=fetch_result.fetch_profile_used,
        fetch_result=fetch_result,
        snapshot=candidate_snapshot,
        classification=candidate_classification,
        ocr_decision=candidate_ocr_decision,
        evidence_pack=candidate_evidence_pack,
        elapsed_seconds=elapsed_seconds,
        source_loss_notes=source_loss_notes,
        recommendation_flag=recommendation_flag,
    )
    parity = build_snapshot_parity_report(
        case_id=case_id,
        candidate_source=candidate_source,
        baseline_snapshot=baseline_snapshot,
        candidate_snapshot=candidate_snapshot,
        baseline_classification=baseline_classification,
        candidate_classification=candidate_classification,
        baseline_ocr_decision=baseline_ocr_decision,
        candidate_ocr_decision=candidate_ocr_decision,
        baseline_evidence_pack=baseline_evidence_pack,
        candidate_evidence_pack=candidate_evidence_pack,
    )
    return row, parity


def recommend_candidate_source(
    *,
    candidate_source: str,
    baseline_snapshot: NormalizedPageSnapshot,
    baseline_classification: PageClassification,
    candidate_snapshot: NormalizedPageSnapshot,
    candidate_classification: PageClassification,
    baseline_evidence_fact_count: int,
    candidate_evidence_fact_count: int,
) -> str:
    if baseline_classification.page_class != candidate_classification.page_class:
        return "reject"
    if baseline_classification.supported_for_generation != candidate_classification.supported_for_generation:
        return "reject"
    if candidate_snapshot.page_class_hint not in SUPPORTED_PAGE_CLASSES and baseline_snapshot.page_class_hint in SUPPORTED_PAGE_CLASSES:
        return "reject"
    if candidate_snapshot.visible_text_blocks and baseline_snapshot.visible_text_blocks:
        if len(candidate_snapshot.visible_text_blocks) * 2 < len(baseline_snapshot.visible_text_blocks):
            return "reject"
    if candidate_source == "fit_markdown" and candidate_evidence_fact_count <= baseline_evidence_fact_count:
        return "keep_testing"
    if len(candidate_snapshot.decoded_text or "") > len(baseline_snapshot.decoded_text or ""):
        return "candidate"
    return "keep_testing"


def _fetch_case(
    *,
    case: dict[str, Any],
    live_fetcher: Crawl4AiPageFetcher,
) -> tuple[HtmlFetchResult, dict[str, Any] | None]:
    if case["case_type"] == "fixture":
        fixture_fetcher = FixtureHtmlFetcher(
            base_dir=Path.cwd(),
            url_to_file={case["url"]: case["fixture_path"]},
        )
        return fixture_fetcher.fetch(case["url"]), None

    fetch_result = live_fetcher.fetch(case["url"])
    return fetch_result, dict(live_fetcher.last_sidecars or {})


def _failed_case_rows(*, case: dict[str, Any], error: str, elapsed_seconds: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate_source in PREPROCESSING_CANDIDATE_SOURCES:
        rows.append(
            {
                "case_id": case["label"],
                "case_type": case["case_type"],
                "candidate_source": candidate_source,
                "fetch_mode": "crawl4ai" if case["case_type"] == "live" else "fixture_html",
                "final_url": case["url"],
                "http_status": None,
                "page_class": "collection_fetch_failed",
                "supported_for_generation": False,
                "decoded_text_chars": 0,
                "visible_block_count": 0,
                "structured_data_count": 0,
                "image_candidate_count": 0,
                "ocr_trigger_reasons": ["collection_fetch_failed"],
                "evidence_fact_count": 0,
                "quality_warning": True,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "source_loss_notes": error,
                "recommendation_flag": "reject",
            }
        )
    return rows


def _write_case_artifacts(
    *,
    case: dict[str, Any],
    fetch_result: HtmlFetchResult,
    baseline_snapshot: NormalizedPageSnapshot,
    sidecars: dict[str, Any] | None,
) -> None:
    case_dir = ARTIFACTS_DIR / case["label"] / "collection"
    case_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": {
            "fetch_backend": "crawl4ai" if case["case_type"] == "live" else "fixture_html",
            "raw_url": fetch_result.raw_url,
            "final_url": fetch_result.final_url,
            "http_status": fetch_result.http_status,
            "content_type": fetch_result.content_type,
            "fetch_profile_used": fetch_result.fetch_profile_used,
        },
        "canonical_inputs": {
            "rendered_html": fetch_result.html,
            "preferred_text_source": "raw_html",
            "cleaned_html": (sidecars or {}).get("cleaned_html"),
        },
        "sidecars": {
            "markdown": (sidecars or {}).get("markdown"),
            "fit_markdown": (sidecars or {}).get("fit_markdown"),
            "fit_html": (sidecars or {}).get("fit_html"),
            "media_inventory": (sidecars or {}).get("media_summary"),
            "screenshot": {
                "available": bool((sidecars or {}).get("screenshot_present")),
            },
        },
        "decisions": {
            "decoded_text_source": "raw_html",
            "image_candidate_seed": "rendered_html_dom",
            "baseline_page_class": baseline_snapshot.page_class_hint,
        },
    }
    (case_dir / "preprocessed_page.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _summarize_benchmark(
    *,
    rows: list[dict[str, Any]],
    parity_reports: list[dict[str, Any]],
    case_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    live_rows = [row for row in rows if row["case_type"] == "live"]
    candidate_rows = [row for row in live_rows if row["recommendation_flag"] == "candidate"]
    regression_counts: dict[str, int] = {}
    for report in parity_reports:
        for stage in report["regression_stages"]:
            regression_counts[stage] = regression_counts.get(stage, 0) + 1
    return {
        "row_count": len(rows),
        "live_row_count": len(live_rows),
        "candidate_rows": len(candidate_rows),
        "case_error_count": len(case_errors),
        "regression_counts": regression_counts,
        "best_live_candidates": _best_candidate_rows(live_rows),
    }


def _best_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_case: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row["case_id"]
        current = best_by_case.get(case_id)
        rank = {"candidate": 2, "keep_testing": 1, "reject": 0}[str(row["recommendation_flag"])]
        current_rank = {"candidate": 2, "keep_testing": 1, "reject": 0}[str(current["recommendation_flag"])] if current else -1
        if current is None or rank > current_rank:
            best_by_case[case_id] = row
            continue
        if rank == current_rank and row["decoded_text_chars"] > current["decoded_text_chars"]:
            best_by_case[case_id] = row
    return [best_by_case[key] for key in sorted(best_by_case)]


def _write_benchmark_artifacts(result: dict[str, Any]) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACTS_DIR / "summary.md").write_text(_render_summary_markdown(result), encoding="utf-8")


def _resolved_candidate_text(
    *,
    fetch_result: HtmlFetchResult,
    baseline_snapshot: NormalizedPageSnapshot,
    candidate_source: str,
    sidecars: dict[str, Any] | None,
) -> tuple[str, str]:
    payload = sidecars or {}
    if candidate_source == "raw_html":
        return (baseline_snapshot.decoded_text or _extract_visible_text(fetch_result.html), "")
    if candidate_source == "cleaned_html":
        cleaned_html = str(payload.get("cleaned_html") or "").strip()
        if not cleaned_html:
            return "", "missing cleaned_html sidecar"
        return _extract_visible_text(cleaned_html), "rendered DOM metadata preserved from raw_html"
    markdown_key = "markdown" if candidate_source == "markdown" else "fit_markdown"
    markdown_text = str(payload.get(markdown_key) or "").strip()
    if not markdown_text:
        return "", f"missing {markdown_key} sidecar"
    return _markdown_to_text(markdown_text), "markdown converted to plain text; DOM block structure is approximated"


def _markdown_to_text(markdown_text: str) -> str:
    text = markdown_text
    text = re.sub(r"```.*?```", "\n", text, flags=re.DOTALL)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[>#*\-\d.\s]+", "", text, flags=re.MULTILINE)
    text = text.replace("`", "")
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _sorted_string_delta(baseline: list[str], candidate: list[str]) -> dict[str, list[str]]:
    baseline_set = {str(item) for item in baseline}
    candidate_set = {str(item) for item in candidate}
    return {
        "added": sorted(candidate_set - baseline_set),
        "removed": sorted(baseline_set - candidate_set),
    }


def _classify_without_bedrock(snapshot: NormalizedPageSnapshot) -> PageClassification:
    previous = os.environ.pop("KEYWORD_GENERATOR_GENERATION_MODE", None)
    try:
        return classify_snapshot(snapshot)
    finally:
        if previous is not None:
            os.environ["KEYWORD_GENERATOR_GENERATION_MODE"] = previous


def _render_summary_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Crawl4AI Preprocessing Benchmark",
        "",
        f"- Generated at: `{result['generated_at']}`",
        f"- Rows: `{summary['row_count']}`",
        f"- Live rows: `{summary['live_row_count']}`",
        f"- Case errors: `{summary['case_error_count']}`",
        "",
        "## Best Live Candidates",
        "",
    ]
    for row in summary["best_live_candidates"]:
        lines.append(
            f"- `{row['case_id']}`: `{row['candidate_source']}` / `{row['recommendation_flag']}` / chars `{row['decoded_text_chars']}` / page `{row['page_class']}`"
        )
    if not summary["best_live_candidates"]:
        lines.append("- none")
    lines.extend(["", "## Regression Counts", ""])
    if summary["regression_counts"]:
        for stage, count in sorted(summary["regression_counts"].items()):
            lines.append(f"- `{stage}`: `{count}`")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _resolve_ocr_decision(
    *,
    snapshot: NormalizedPageSnapshot,
    classification: PageClassification,
    ocr_runner: Any | None,
    ocr_mode: str,
) -> OcrDecision:
    ocr_decision = run_ocr_policy(snapshot)
    if ocr_runner is None or ocr_mode == "policy_only":
        return ocr_decision
    if ocr_mode != "eligible_all":
        raise ValueError(f"unsupported ocr_mode: {ocr_mode}")
    if not classification.supported_for_generation:
        return ocr_decision
    if snapshot.ocr_text_blocks:
        return ocr_decision
    if not ocr_decision.ranked_image_candidates:
        return ocr_decision
    if "ocr_not_required" in ocr_decision.trigger_reasons:
        return ocr_decision

    requested_candidates = list(ocr_decision.ranked_image_candidates)
    original_max_images = getattr(ocr_runner, "max_images", None)
    if original_max_images is not None:
        setattr(ocr_runner, "max_images", len(requested_candidates))
    try:
        runner_output = ocr_runner.run(snapshot, requested_candidates)
    finally:
        if original_max_images is not None:
            setattr(ocr_runner, "max_images", original_max_images)

    if isinstance(runner_output, OcrRunResult):
        snapshot.ocr_text_blocks = list(runner_output.blocks)
        snapshot.ocr_image_results = list(runner_output.image_results)
    else:
        snapshot.ocr_text_blocks = list(runner_output)
        snapshot.ocr_image_results = []
    return run_ocr_policy(snapshot)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--live-only", action="store_true")
    args = parser.parse_args()

    result = run_preprocessing_benchmark(
        include_live=not args.fixtures_only,
        include_fixtures=not args.live_only,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
