from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.evaluate_crawl4ai_preprocessing_benchmark import build_preprocessed_snapshot
from src.collection import Crawl4AiPageFetcher, HttpPageFetcher, classify_snapshot, collect_snapshot_from_html
from src.evidence import build_evidence_pack
from src.keyword_generation.models import GenerationRequest
from src.keyword_generation.service import generate_keywords
from src.ocr import run_ocr_policy


ARTIFACT_ROOT = Path("artifacts") / "live_generation_compare"


def _positive_rows(rows: list[Any]) -> list[Any]:
    return [row for row in rows if getattr(row, "category", "") != "negative"]


def _serialize_rows(rows: list[Any], *, limit: int = 30) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in _positive_rows(rows)[:limit]:
        payload.append(asdict(row))
    return payload


def _keyword_list(rows: list[Any], *, limit: int = 30) -> list[str]:
    return [str(getattr(row, "keyword", "")) for row in _positive_rows(rows)[:limit]]


def _run_pipeline(*, snapshot: Any, platform_mode: str) -> dict[str, Any]:
    classification = classify_snapshot(snapshot)
    ocr_decision = run_ocr_policy(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification, ocr_decision)
    started = time.perf_counter()
    generation = generate_keywords(
        GenerationRequest(
            evidence_pack=evidence_pack,
            requested_platform_mode=platform_mode,
        )
    )
    generation_elapsed = time.perf_counter() - started
    positive_rows = _positive_rows(generation.rows)
    return {
        "snapshot": {
            "title": snapshot.title,
            "product_name": snapshot.product_name,
            "page_class_hint": snapshot.page_class_hint,
            "decoded_text_chars": len(snapshot.decoded_text or ""),
            "visible_block_count": len(snapshot.visible_text_blocks),
            "structured_data_count": len(snapshot.structured_data),
            "image_candidate_count": len(snapshot.image_candidates),
            "usable_text_chars": snapshot.usable_text_chars,
        },
        "classification": asdict(classification),
        "ocr": {
            "trigger_reasons": list(ocr_decision.trigger_reasons),
            "admitted_block_count": len(ocr_decision.admitted_blocks),
            "admitted_block_sources": [block.source for block in ocr_decision.admitted_blocks[:10]],
        },
        "evidence": {
            "fact_count": len(evidence_pack.get("facts", [])),
            "fact_types": sorted({str(fact.get("type", "")) for fact in evidence_pack.get("facts", [])}),
            "quality_warning": bool(evidence_pack.get("quality_warning")),
            "quality_warning_inputs": list(evidence_pack.get("quality_warning_inputs", [])),
        },
        "generation": {
            "status": generation.status,
            "requested_platform_mode": generation.requested_platform_mode,
            "positive_row_count": len(positive_rows),
            "generation_elapsed_seconds": round(generation_elapsed, 3),
            "validation_report": asdict(generation.validation_report) if generation.validation_report else None,
            "top_keywords": _keyword_list(generation.rows),
            "top_rows": _serialize_rows(generation.rows),
            "debug_keys": sorted(generation.debug_payload.keys()),
        },
    }


def _write_summary(*, label: str, url: str, payload: dict[str, Any], output_dir: Path) -> None:
    runs = payload["runs"]
    baseline_keywords = set(runs["http_baseline"]["generation"]["top_keywords"])
    cleaned_keywords = set(runs["crawl4ai_cleaned_html"]["generation"]["top_keywords"])
    raw_keywords = set(runs["crawl4ai_raw_html"]["generation"]["top_keywords"])

    lines = [
        f"# Live Generation Compare: {label}",
        "",
        f"- URL: {url}",
        f"- Generated at: {payload['generated_at']}",
        "",
        "## Run Summary",
        "",
        "| path | page_class | supported | decoded_text_chars | evidence_fact_count | positive_rows | status |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, run in runs.items():
        lines.append(
            "| {name} | {page_class} | {supported} | {decoded} | {facts} | {rows} | {status} |".format(
                name=name,
                page_class=run["classification"]["page_class"],
                supported="yes" if run["classification"]["supported_for_generation"] else "no",
                decoded=run["snapshot"]["decoded_text_chars"],
                facts=run["evidence"]["fact_count"],
                rows=run["generation"]["positive_row_count"],
                status=run["generation"]["status"],
            )
        )
    lines.extend(
        [
            "",
            "## Keyword Overlap",
            "",
            f"- http_baseline ∩ crawl4ai_cleaned_html: {len(baseline_keywords & cleaned_keywords)}",
            f"- http_baseline only: {len(baseline_keywords - cleaned_keywords)}",
            f"- crawl4ai_cleaned_html only: {len(cleaned_keywords - baseline_keywords)}",
            f"- crawl4ai_raw_html ∩ crawl4ai_cleaned_html: {len(raw_keywords & cleaned_keywords)}",
            "",
            "## Sample Keywords",
            "",
        ]
    )
    for name, run in runs.items():
        lines.append(f"### {name}")
        for keyword in run["generation"]["top_keywords"][:15]:
            lines.append(f"- {keyword}")
        lines.append("")

    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--platform", default="naver_sa")
    args = parser.parse_args()

    output_dir = ARTIFACT_ROOT / args.label
    output_dir.mkdir(parents=True, exist_ok=True)

    http_fetcher = HttpPageFetcher()
    crawl_fetcher = Crawl4AiPageFetcher()

    http_fetch_result = http_fetcher.fetch(args.url)
    http_snapshot = collect_snapshot_from_html(http_fetch_result)

    crawl_fetch_result = crawl_fetcher.fetch(args.url)
    crawl_raw_snapshot = collect_snapshot_from_html(crawl_fetch_result)
    crawl_sidecars = dict(crawl_fetcher.last_sidecars or {})
    crawl_cleaned_snapshot, cleaned_note = build_preprocessed_snapshot(
        fetch_result=crawl_fetch_result,
        baseline_snapshot=crawl_raw_snapshot,
        candidate_source="cleaned_html",
        sidecars=crawl_sidecars,
    )

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "label": args.label,
        "url": args.url,
        "platform": args.platform,
        "crawl4ai_sidecars_present": {
            "cleaned_html": bool(crawl_sidecars.get("cleaned_html")),
            "markdown": bool(crawl_sidecars.get("markdown")),
            "fit_markdown": bool(crawl_sidecars.get("fit_markdown")),
            "fit_html": bool(crawl_sidecars.get("fit_html")),
            "screenshot_present": bool(crawl_sidecars.get("screenshot_present")),
            "media_summary": crawl_sidecars.get("media_summary"),
        },
        "notes": {
            "crawl4ai_cleaned_html": cleaned_note,
        },
        "runs": {
            "http_baseline": _run_pipeline(snapshot=http_snapshot, platform_mode=args.platform),
            "crawl4ai_raw_html": _run_pipeline(snapshot=crawl_raw_snapshot, platform_mode=args.platform),
            "crawl4ai_cleaned_html": _run_pipeline(snapshot=crawl_cleaned_snapshot, platform_mode=args.platform),
        },
    }

    (output_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_summary(label=args.label, url=args.url, payload=payload, output_dir=output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
