from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quality_eval import (
    build_job_input_from_combined_payload,
    evaluate_job_input,
    load_combined_payload_from_job,
    load_json_from_source,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deployed keyword-generation artifacts.")
    parser.add_argument("--job-id", help="Job id to resolve through the deployed API")
    parser.add_argument("--api-base", help="API base URL, required with --job-id")
    parser.add_argument("--combined-json", help="Combined artifact source: local path, URL, or s3:// URI")
    parser.add_argument("--region", help="AWS region for s3:// artifact reads")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if bool(args.job_id) == bool(args.combined_json):
        parser.error("provide exactly one of --job-id or --combined-json")
    if args.job_id and not args.api_base:
        parser.error("--api-base is required with --job-id")
    return args


def _load_job_result(args: argparse.Namespace) -> tuple[dict, dict]:
    if args.job_id:
        status_payload, combined_payload = load_combined_payload_from_job(
            api_base=args.api_base,
            job_id=args.job_id,
            timeout=args.timeout,
            region_name=args.region,
        )
        return status_payload, combined_payload

    combined_payload = load_json_from_source(
        args.combined_json,
        api_base=args.api_base,
        timeout=args.timeout,
        region_name=args.region,
    )
    status_payload = {
        "job_id": combined_payload.get("job_id"),
        "status": "UNKNOWN",
        "requested_platform_mode": combined_payload.get("requested_platform_mode"),
    }
    return status_payload, combined_payload


def _print_text_report(status_payload: dict, result: dict) -> None:
    print("Deployed evaluator")
    print(f"job_id: {status_payload.get('job_id')}")
    print(f"job_status: {status_payload.get('status')}")
    print(f"requested_platform_mode: {result['requested_platform_mode']}")
    print(f"successful_url_coverage: {result['successful_url_coverage']:.3f}")
    print(f"job_verdict: {'PASS' if result['gate']['pass'] else 'REWORK'}")
    if result["gate"]["failure_reasons"]:
        print(f"job_failure_reasons: {', '.join(result['gate']['failure_reasons'])}")
    print()

    for item in result["url_results"]:
        metrics = item["metrics"]
        gate = item["gate"]
        print(f"[{item['url_task_id']}::{item['platform']}] {'PASS' if gate['pass'] else 'REWORK'}")
        print(f"  page_class: {item['page_class']}")
        print(f"  total_rows: {metrics['total_rows']}")
        print(f"  filler_ratio: {metrics['filler_ratio']:.3f}")
        print(f"  avg_naturalness: {metrics['avg_naturalness']:.3f}")
        print(f"  semantic_unique_ratio: {metrics['semantic_unique_ratio']:.3f}")
        print(f"  exact_unique_ratio: {metrics['exact_unique_ratio']:.3f}")
        print(f"  auto_score: {metrics['auto_score']:.1f}")
        print(f"  quality_warning: {item['quality_warning']}")
        if gate["failure_reasons"]:
            print(f"  failure_reasons: {', '.join(gate['failure_reasons'])}")
        if item["duplicate_families"]:
            top_family = item["duplicate_families"][0]
            print(f"  top_duplicate_family: {top_family['signature']} x{top_family['count']}")
        print()


def main() -> None:
    args = _parse_args()
    status_payload, combined_payload = _load_job_result(args)
    job_input = build_job_input_from_combined_payload(combined_payload)
    evaluation = evaluate_job_input(job_input).to_dict()

    if args.output == "json":
        print(
            json.dumps(
                {
                    "job_status_payload": status_payload,
                    "evaluation": evaluation,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_text_report(status_payload, evaluation)

    raise SystemExit(0 if evaluation["gate"]["pass"] else 1)


if __name__ == "__main__":
    main()
