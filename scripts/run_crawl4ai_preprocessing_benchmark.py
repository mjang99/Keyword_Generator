from __future__ import annotations

import argparse
import json
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from scripts.evaluate_collection_fetch_benchmark import FIXTURE_CASES, LIVE_CASES
from scripts.evaluate_crawl4ai_preprocessing_benchmark import (
    PREPROCESSING_CANDIDATE_SOURCES,
    evaluate_candidate_outputs,
)
from src.collection import Crawl4AiPageFetcher, HtmlFetchResult, classify_snapshot, collect_snapshot_from_html
from src.evidence import build_evidence_pack
from src.ocr import create_subprocess_ocr_runner_from_env, run_ocr_policy

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "artifacts" / "service_test_pages"
DEFAULT_OUTPUT_PATH = ROOT / "artifacts" / "crawl4ai_quality_tuning" / "quality_tuning_latest.json"

FETCH_PROFILE_SPECS: dict[str, dict[str, Any]] = {
    "baseline_render": {},
    "wait_images_render": {"wait_for_images": True},
    "interaction_render": {"simulate_user": True, "remove_overlay_elements": True},
    "magic_render": {"magic": True, "override_navigator": True},
    "stealth_render": {"enable_stealth": True, "magic": True},
    "text_rich_render": {
        "wait_for_images": True,
        "simulate_user": True,
        "remove_overlay_elements": True,
        "magic": True,
    },
}


class _QuietHttpHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Crawl4AI preprocessing source benchmark.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="JSON artifact path for benchmark output.",
    )
    parser.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Run only the fixed fixture cases.",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Run only the fixed live URL cases.",
    )
    parser.add_argument(
        "--page-timeout-seconds",
        type=float,
        default=30.0,
        help="Crawl4AI page timeout in seconds.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=tuple(FETCH_PROFILE_SPECS),
        help="Named Crawl4AI tuning profile. Repeat to select multiple. Defaults to all profiles.",
    )
    parser.add_argument(
        "--ocr-mode",
        choices=("policy_only", "eligible_all"),
        default="eligible_all",
        help="OCR benchmark mode. 'eligible_all' runs OCR on all filtered eligible images when OCR env is enabled.",
    )
    return parser.parse_args()


def _selected_cases(*, fixtures_only: bool, live_only: bool) -> list[dict[str, Any]]:
    if fixtures_only and live_only:
        raise ValueError("cannot set both --fixtures-only and --live-only")
    if fixtures_only:
        return list(FIXTURE_CASES)
    if live_only:
        return list(LIVE_CASES)
    return [*FIXTURE_CASES, *LIVE_CASES]


def _selected_profiles(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(FETCH_PROFILE_SPECS)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in selected:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


@contextmanager
def _fixture_server(directory: Path) -> Iterator[str]:
    handler = partial(_QuietHttpHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _build_markdown_generator() -> Any:
    from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter

    return DefaultMarkdownGenerator(content_filter=PruningContentFilter())


def _build_fetcher(*, page_timeout_seconds: float) -> Crawl4AiPageFetcher:
    return Crawl4AiPageFetcher(
        markdown_generator=_build_markdown_generator(),
        page_timeout_ms=int(page_timeout_seconds * 1000),
        wait_until="domcontentloaded",
        delay_before_return_html=0.2,
        wait_for_images=False,
        screenshot=False,
        verbose=False,
    )


def _build_fetcher_for_profile(*, profile_name: str, page_timeout_seconds: float) -> Crawl4AiPageFetcher:
    return Crawl4AiPageFetcher(
        markdown_generator=_build_markdown_generator(),
        page_timeout_ms=int(page_timeout_seconds * 1000),
        wait_until="domcontentloaded",
        delay_before_return_html=0.2,
        screenshot=False,
        verbose=False,
        **FETCH_PROFILE_SPECS[profile_name],
    )


def _prepare_fetch_result(
    *,
    fetcher: Crawl4AiPageFetcher,
    case: dict[str, Any],
    fixture_base_url: str | None,
) -> tuple[HtmlFetchResult, float, dict[str, Any]]:
    request_url = case["url"]
    if case["case_type"] == "fixture":
        if fixture_base_url is None:
            raise ValueError("fixture_base_url is required for fixture cases")
        request_url = f"{fixture_base_url}/{Path(case['fixture_path']).name}"

    started = perf_counter()
    fetch_result = fetcher.fetch(request_url)
    fetch_elapsed_seconds = perf_counter() - started
    sidecars = dict(fetcher.last_sidecars or {})

    if case["case_type"] == "fixture":
        fetch_result = HtmlFetchResult(
            raw_url=case["url"],
            final_url=case["url"],
            html=fetch_result.html,
            content_type=fetch_result.content_type,
            http_status=fetch_result.http_status,
            fetch_profile_used=fetch_result.fetch_profile_used,
            response_headers=fetch_result.response_headers,
            charset_selected=fetch_result.charset_selected,
            charset_confidence=fetch_result.charset_confidence,
            mojibake_flags=fetch_result.mojibake_flags,
        )
    return fetch_result, fetch_elapsed_seconds, sidecars


def _evaluate_case(
    *,
    fetcher: Crawl4AiPageFetcher,
    case: dict[str, Any],
    fixture_base_url: str | None,
    profile_name: str,
    ocr_mode: str,
    ocr_runner: Any | None,
) -> dict[str, Any]:
    fetch_result, fetch_elapsed_seconds, sidecars = _prepare_fetch_result(
        fetcher=fetcher,
        case=case,
        fixture_base_url=fixture_base_url,
    )
    baseline_snapshot = collect_snapshot_from_html(fetch_result)
    baseline_classification = classify_snapshot(baseline_snapshot)
    baseline_ocr_decision = run_ocr_policy(baseline_snapshot)
    baseline_evidence_pack = build_evidence_pack(baseline_snapshot, baseline_classification, baseline_ocr_decision)

    rows: list[dict[str, Any]] = []
    parity_reports: list[dict[str, Any]] = []
    for candidate_source in PREPROCESSING_CANDIDATE_SOURCES:
        started = perf_counter()
        row, parity = evaluate_candidate_outputs(
            case_id=case["label"],
            case_type=case["case_type"],
            fetch_result=fetch_result,
            baseline_snapshot=baseline_snapshot,
            baseline_classification=baseline_classification,
            candidate_source=candidate_source,
            sidecars=sidecars,
            elapsed_seconds=0.0,
            ocr_runner=ocr_runner,
            ocr_mode=ocr_mode,
        )
        row["elapsed_seconds"] = round(perf_counter() - started, 3)
        row["fetch_mode"] = profile_name
        rows.append(row)
        parity_reports.append(parity)

    return {
        "label": case["label"],
        "case_type": case["case_type"],
        "profile_name": profile_name,
        "ocr_mode": ocr_mode,
        "input_url": case["url"],
        "fetch_elapsed_seconds": round(fetch_elapsed_seconds, 3),
        "sidecars_present": {
            "cleaned_html": bool(sidecars.get("cleaned_html")),
            "markdown": bool(sidecars.get("markdown")),
            "fit_markdown": bool(sidecars.get("fit_markdown")),
        },
        "baseline": {
            "snapshot": {
                "page_class_hint": baseline_snapshot.page_class_hint,
                "decoded_text_chars": len(baseline_snapshot.decoded_text or ""),
                "visible_block_count": len(baseline_snapshot.visible_text_blocks),
                "structured_data_count": len(baseline_snapshot.structured_data),
                "image_candidate_count": len(baseline_snapshot.image_candidates),
            },
            "classification": asdict(baseline_classification),
            "ocr": {
                "status": baseline_ocr_decision.status,
                "trigger_reasons": list(baseline_ocr_decision.trigger_reasons),
                "admitted_block_count": len(baseline_ocr_decision.admitted_blocks),
            },
            "evidence": {
                "fact_count": len(baseline_evidence_pack.get("facts", [])),
                "quality_warning": bool(baseline_evidence_pack.get("quality_warning")),
            },
        },
        "rows": rows,
        "parity_reports": parity_reports,
    }


def _summarize_payload(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {
        source: {
            "rows": 0,
            "candidate": 0,
            "keep_testing": 0,
            "reject": 0,
            "classification_regressions": 0,
            "evidence_regressions": 0,
        }
        for source in PREPROCESSING_CANDIDATE_SOURCES
    }
    by_profile: dict[str, dict[str, Any]] = {}
    for result in results:
        profile_summary = by_profile.setdefault(
            str(result.get("profile_name", "unknown")),
            {
                "rows": 0,
                "candidate": 0,
                "keep_testing": 0,
                "reject": 0,
                "classification_regressions": 0,
                "evidence_regressions": 0,
                "ocr_mode": str(result.get("ocr_mode", "policy_only")),
            },
        )
        for row, parity in zip(result["rows"], result["parity_reports"], strict=True):
            summary = by_source[row["candidate_source"]]
            summary["rows"] += 1
            summary[row["recommendation_flag"]] += 1
            profile_summary["rows"] += 1
            profile_summary[row["recommendation_flag"]] += 1
            if "classification" in parity["regression_stages"]:
                summary["classification_regressions"] += 1
                profile_summary["classification_regressions"] += 1
            if "evidence" in parity["regression_stages"]:
                summary["evidence_regressions"] += 1
                profile_summary["evidence_regressions"] += 1
    return {
        "by_source": by_source,
        "by_profile": by_profile,
    }


def _print_summary(payload: dict[str, Any]) -> None:
    print("Crawl4AI preprocessing benchmark")
    print(f"generated_at: {payload['generated_at']}")
    print(f"output_path: {payload['output_path']}")
    print()
    for source, summary in payload["summary"]["by_source"].items():
        print(f"[{source}]")
        print(f"  rows: {summary['rows']}")
        print(f"  candidate: {summary['candidate']}")
        print(f"  keep_testing: {summary['keep_testing']}")
        print(f"  reject: {summary['reject']}")
        print(f"  classification_regressions: {summary['classification_regressions']}")
        print(f"  evidence_regressions: {summary['evidence_regressions']}")
        print()
    for profile_name, summary in payload["summary"]["by_profile"].items():
        print(f"[profile:{profile_name}]")
        print(f"  ocr_mode: {summary['ocr_mode']}")
        print(f"  rows: {summary['rows']}")
        print(f"  candidate: {summary['candidate']}")
        print(f"  keep_testing: {summary['keep_testing']}")
        print(f"  reject: {summary['reject']}")
        print(f"  classification_regressions: {summary['classification_regressions']}")
        print(f"  evidence_regressions: {summary['evidence_regressions']}")
        print()


def main() -> None:
    args = _parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cases = _selected_cases(fixtures_only=args.fixtures_only, live_only=args.live_only)
    profiles = _selected_profiles(args.profile)
    ocr_runner = create_subprocess_ocr_runner_from_env()

    with _fixture_server(FIXTURE_ROOT) as fixture_base_url:
        results = []
        for profile_name in profiles:
            fetcher = _build_fetcher_for_profile(
                profile_name=profile_name,
                page_timeout_seconds=args.page_timeout_seconds,
            )
            for case in cases:
                results.append(
                    _evaluate_case(
                        fetcher=fetcher,
                        case=case,
                        fixture_base_url=fixture_base_url,
                        profile_name=profile_name,
                        ocr_mode=args.ocr_mode,
                        ocr_runner=ocr_runner,
                    )
                )

    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "output_path": str(args.output),
        "cases": [case["label"] for case in cases],
        "profiles": profiles,
        "ocr_mode": args.ocr_mode,
        "results": results,
        "summary": _summarize_payload(results),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(payload)


if __name__ == "__main__":
    main()
