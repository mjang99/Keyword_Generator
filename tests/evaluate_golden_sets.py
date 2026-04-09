from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.keyword_generation import GenerationRequest, generate_keywords
from src.quality_eval import evaluate_golden_set, load_golden_set_case, load_golden_source_payload

GOLDEN_SETS_DIR = ROOT / "tests" / "golden_sets"


def iter_case_paths(selected_case: str | None) -> list[Path]:
    if selected_case:
        return [GOLDEN_SETS_DIR / f"{selected_case}.json"]
    return sorted(GOLDEN_SETS_DIR.glob("*.json"))


def run_case(case_path: Path) -> dict:
    case = load_golden_set_case(case_path)
    evidence_pack = load_golden_source_payload(case, repo_root=ROOT)
    result = generate_keywords(
        GenerationRequest(
            evidence_pack=evidence_pack,
            requested_platform_mode=case.requested_platform_mode,
        )
    )
    return evaluate_golden_set(
        case,
        rows=result.rows,
        generation_status=result.status,
    ).to_dict()


def print_report(report: dict) -> bool:
    case_pass = bool(report["pass"])
    print(f"[{report['case_id']}] {'PASS' if case_pass else 'REWORK'}")
    print(f"  source: {report['source_path']}")
    print(f"  generation_status: {report['generation_status']}")
    for item in report["platform_results"]:
        print(f"  - {item['platform']}: {'PASS' if item['pass'] else 'REWORK'}")
        print(f"    observed_positive_count: {item['observed_positive_count']}")
        if item["missing_must_keep"]:
            print(f"    missing_must_keep: {', '.join(item['missing_must_keep'])}")
        if item["emitted_forbidden_keywords"]:
            print(f"    emitted_forbidden_keywords: {', '.join(item['emitted_forbidden_keywords'])}")
        if item["emitted_forbidden_substrings"]:
            print(f"    emitted_forbidden_substrings: {', '.join(item['emitted_forbidden_substrings'])}")
        if item["missing_categories"]:
            print(f"    missing_categories: {', '.join(item['missing_categories'])}")
    print()
    return case_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden-set quality evaluator for local keyword tuning.")
    parser.add_argument("--case", help="Golden set case id without .json suffix")
    parser.add_argument("--output", default="text", choices=["text", "json"])
    args = parser.parse_args()

    reports = [run_case(case_path) for case_path in iter_case_paths(args.case)]
    if args.output == "json":
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        passed = all(bool(report["pass"]) for report in reports)
    else:
        passed = all(print_report(report) for report in reports)

    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
