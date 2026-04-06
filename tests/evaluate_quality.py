from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.keyword_generation import GenerationRequest, generate_keywords
from src.quality_eval import PerUrlEvaluationInput, compute_auto_scores, evaluate_per_url_input

FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_fixture(name: str) -> dict:
    fixture_path = FIXTURES_DIR / name
    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_reference_evaluation(*, fixture_name: str, platform: str) -> dict:
    evidence_pack = load_fixture(fixture_name)
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=evidence_pack,
            requested_platform_mode=platform,
        )
    )

    platforms = ["naver_sa", "google_sa"] if platform == "both" else [platform]
    per_platform: list[dict] = []
    for target_platform in platforms:
        per_platform.append(compute_auto_scores(result.rows, target_platform, evidence_pack))

    return {
        "mode": "reference",
        "fixture": fixture_name,
        "requested_platform_mode": platform,
        "generation_status": result.status,
        "supplementation_attempts": result.supplementation_attempts,
        "platform_results": per_platform,
    }


def _print_reference_report(report: dict) -> bool:
    print("Reference evaluator")
    print("This is a local regression check, not the deployed acceptance gate.")
    print(f"fixture: {report['fixture']}")
    print(f"generation_status: {report['generation_status']}")
    print(f"supplementation_attempts: {report['supplementation_attempts']}")
    print()

    all_pass = True
    for item in report["platform_results"]:
        platform_pass = bool(item["pass"])
        all_pass = all_pass and platform_pass
        print(f"[{item['platform']}] {'PASS' if platform_pass else 'REWORK'}")
        print(f"  total_rows: {item['total_rows']}")
        print(f"  filler_ratio: {item['filler_ratio']:.3f}")
        print(f"  avg_naturalness: {item['avg_naturalness']:.3f}")
        print(f"  semantic_unique_ratio: {item['semantic_unique_ratio']:.3f}")
        print(f"  exact_unique_ratio: {item['exact_unique_ratio']:.3f}")
        print(f"  auto_score: {item['auto_score']:.1f}")
        if item["failure_reasons"]:
            print(f"  failure_reasons: {', '.join(item['failure_reasons'])}")
        print()

    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reference-only keyword quality evaluator for local fixture regression checks."
    )
    parser.add_argument("--fixture", required=True, help="Fixture file name under tests/fixtures")
    parser.add_argument("--platform", default="both", choices=["naver_sa", "google_sa", "both"])
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Accepted for compatibility. The reference evaluator no longer performs LLM judging.",
    )
    args = parser.parse_args()

    report = run_reference_evaluation(fixture_name=args.fixture, platform=args.platform)
    if args.output == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        all_pass = all(item["pass"] for item in report["platform_results"])
    else:
        all_pass = _print_reference_report(report)

    raise SystemExit(0 if all_pass else 1)


__all__ = [
    "PerUrlEvaluationInput",
    "compute_auto_scores",
    "evaluate_per_url_input",
    "load_fixture",
    "run_reference_evaluation",
]


if __name__ == "__main__":
    main()
