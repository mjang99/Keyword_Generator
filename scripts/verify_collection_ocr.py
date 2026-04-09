from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import urllib.parse
import urllib.request
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collection import FixtureHtmlFetcher, HtmlFetchResult, HttpPageFetcher, classify_snapshot, collect_snapshot_from_html
from src.collection.models import NormalizedPageSnapshot
from src.evidence import build_evidence_pack
from src.ocr import OcrRunResult, create_subprocess_ocr_runner_from_env, run_ocr_policy


DEFAULT_FIXTURE_CASES = (
    {
        "label": "commerce_pdp",
        "url": "https://example.com/on-pdp",
        "fixture": "on_pdp_en.html",
        "expected_page_class": "commerce_pdp",
    },
    {
        "label": "support_spec_page",
        "url": "https://example.com/airpods-spec",
        "fixture": "apple_airpodspro3_specs_ko.html",
        "expected_page_class": "support_spec_page",
    },
    {
        "label": "blocked_control",
        "url": "https://example.com/naver-blocked",
        "fixture": "naver_smartstore_blocked.html",
        "expected_page_class": "blocked_page",
    },
)

DEFAULT_OCR_VENV_PYTHON = ROOT / ".venv-paddleocr" / "Scripts" / "python.exe"
OCR_VENV_SITE_PACKAGES = ROOT / ".venv-paddleocr" / "Lib" / "site-packages"


@dataclass(slots=True)
class VerificationResult:
    label: str
    input_url: str | None
    expected_page_class: str | None
    page_class: str | None
    supported_for_generation: bool | None
    checks: dict[str, bool]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "input_url": self.input_url,
            "expected_page_class": self.expected_page_class,
            "page_class": self.page_class,
            "supported_for_generation": self.supported_for_generation,
            "checks": dict(self.checks),
            "details": dict(self.details),
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify scraping/classification and OCR behavior without relying on final keyword floors."
    )
    parser.add_argument(
        "--fixture-suite",
        action="store_true",
        help="Run the built-in local fixture verification suite.",
    )
    parser.add_argument(
        "--fixture-case",
        action="append",
        default=[],
        help="Custom fixture case: label|url|fixture_html|expected_page_class",
    )
    parser.add_argument(
        "--live-case",
        action="append",
        default=[],
        help="Live scrape case: label|url|expected_page_class(optional)",
    )
    parser.add_argument(
        "--ocr-positive-image",
        help="Path or URL for a text-rich image that should produce admitted OCR text.",
    )
    parser.add_argument(
        "--ocr-negative-image",
        help="Path or URL for a control image that should not produce admitted OCR text.",
    )
    parser.add_argument(
        "--ocr-product-name",
        help="Product name used to evaluate OCR admission.",
    )
    parser.add_argument(
        "--ocr-product-token",
        action="append",
        default=[],
        help="Additional OCR product token used for OCR admission checks. Repeat for multiple tokens.",
    )
    parser.add_argument(
        "--ocr-python",
        default=str(_default_ocr_python()),
        help="Python executable with PaddleOCR installed. Default: inferred from .venv-paddleocr\\pyvenv.cfg",
    )
    parser.add_argument(
        "--ocr-min-positive-chars",
        type=int,
        default=30,
        help="Minimum OCR characters expected from the positive OCR image.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--run-page-ocr",
        action="store_true",
        help="Execute the OCR runner for ranked page images when OCR env flags are configured.",
    )
    parser.add_argument(
        "--allow-ocr-on-unsupported",
        action="store_true",
        help="Allow page-image OCR experiments even when page classification is unsupported.",
    )
    args = parser.parse_args()

    if not args.fixture_suite and not args.fixture_case and not args.live_case and not args.ocr_positive_image and not args.ocr_negative_image:
        parser.error(
            "enable at least one verification mode: --fixture-suite, --fixture-case, --live-case, or OCR image arguments"
        )
    if (args.ocr_positive_image or args.ocr_negative_image) and not (args.ocr_product_name or args.ocr_product_token):
        parser.error("OCR smoke needs --ocr-product-name or at least one --ocr-product-token for admission checks")
    return args


def _parse_fixture_case(spec: str) -> dict[str, str]:
    parts = spec.split("|")
    if len(parts) != 4:
        raise ValueError(f"invalid fixture case: {spec!r}")
    label, url, fixture_name, expected_page_class = [part.strip() for part in parts]
    return {
        "label": label,
        "url": url,
        "fixture": fixture_name,
        "expected_page_class": expected_page_class,
    }


def _default_ocr_python() -> Path:
    pyvenv_cfg = ROOT / ".venv-paddleocr" / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        for line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
            if not line.lower().startswith("executable = "):
                continue
            candidate = Path(line.split("=", 1)[1].strip())
            if candidate and candidate.exists():
                return candidate
    return DEFAULT_OCR_VENV_PYTHON


def _parse_live_case(spec: str) -> tuple[str, str, str | None]:
    parts = spec.split("|")
    if len(parts) not in {2, 3}:
        raise ValueError(f"invalid live case: {spec!r}")
    label = parts[0].strip()
    url = parts[1].strip()
    expected_page_class = parts[2].strip() if len(parts) == 3 and parts[2].strip() else None
    return label, url, expected_page_class


def _run_fixture_cases(
    case_specs: list[dict[str, str]],
    *,
    run_page_ocr: bool,
    allow_ocr_on_unsupported: bool,
) -> list[VerificationResult]:
    base_dir = ROOT / "artifacts" / "service_test_pages"
    url_to_file = {case["url"]: case["fixture"] for case in case_specs}
    fetcher = FixtureHtmlFetcher(base_dir=base_dir, url_to_file=url_to_file)
    return [
        _verify_fetch_result(
            case["label"],
            fetcher.fetch(case["url"]),
            case["expected_page_class"],
            run_page_ocr=run_page_ocr,
            allow_ocr_on_unsupported=allow_ocr_on_unsupported,
        )
        for case in case_specs
    ]


def _run_live_cases(
    case_specs: list[tuple[str, str, str | None]],
    *,
    run_page_ocr: bool,
    allow_ocr_on_unsupported: bool,
) -> list[VerificationResult]:
    fetcher = HttpPageFetcher()
    results: list[VerificationResult] = []
    for label, url, expected_page_class in case_specs:
        fetch_result = fetcher.fetch(url)
        results.append(
            _verify_fetch_result(
                label,
                fetch_result,
                expected_page_class,
                run_page_ocr=run_page_ocr,
                allow_ocr_on_unsupported=allow_ocr_on_unsupported,
            )
        )
    return results


def _verify_fetch_result(
    label: str,
    fetch_result: HtmlFetchResult,
    expected_page_class: str | None,
    *,
    run_page_ocr: bool,
    allow_ocr_on_unsupported: bool,
) -> VerificationResult:
    snapshot = collect_snapshot_from_html(fetch_result)
    classification = classify_snapshot(snapshot)
    ocr_result = run_ocr_policy(snapshot)
    page_ocr_executed = False
    if run_page_ocr:
        runner = create_subprocess_ocr_runner_from_env()
        can_run = classification.supported_for_generation or allow_ocr_on_unsupported
        if (
            runner is not None
            and can_run
            and not snapshot.ocr_text_blocks
            and ocr_result.ranked_image_candidates
            and "ocr_not_required" not in ocr_result.trigger_reasons
        ):
            runner_output = runner.run(snapshot, ocr_result.ranked_image_candidates)
            if isinstance(runner_output, OcrRunResult):
                snapshot.ocr_text_blocks = list(runner_output.blocks)
                snapshot.ocr_image_results = list(runner_output.image_results)
            else:
                snapshot.ocr_text_blocks = list(runner_output)
                snapshot.ocr_image_results = []
            ocr_result = run_ocr_policy(snapshot)
            page_ocr_executed = True
    evidence_pack: dict[str, Any] | None = None
    if classification.supported_for_generation:
        evidence_pack = build_evidence_pack(snapshot, classification, ocr_result)

    checks = {
        "scrape_has_text": bool(snapshot.decoded_text and len(snapshot.decoded_text) >= 50),
        "page_class_matches": expected_page_class is None or classification.page_class == expected_page_class,
        "supported_has_evidence": not classification.supported_for_generation
        or bool(evidence_pack and evidence_pack.get("facts")),
    }
    details = {
        "fetch_profile_used": fetch_result.fetch_profile_used,
        "http_status": fetch_result.http_status,
        "charset_selected": snapshot.charset_selected,
        "usable_text_chars": snapshot.usable_text_chars,
        "ocr_status": ocr_result.status,
        "ocr_trigger_reasons": list(ocr_result.trigger_reasons),
        "ocr_ranked_image_count": len(ocr_result.ranked_image_candidates),
        "ocr_admitted_block_count": len(ocr_result.admitted_blocks),
        "ocr_rejected_block_count": len(ocr_result.rejected_blocks),
        "ocr_image_results": list(ocr_result.image_results),
        "page_ocr_executed": page_ocr_executed,
        "fact_count": len(evidence_pack.get("facts", [])) if evidence_pack else 0,
        "quality_warning": evidence_pack.get("quality_warning") if evidence_pack else snapshot.quality_warning,
    }
    return VerificationResult(
        label=label,
        input_url=fetch_result.raw_url,
        expected_page_class=expected_page_class,
        page_class=classification.page_class,
        supported_for_generation=classification.supported_for_generation,
        checks=checks,
        details=details,
    )


def _run_ocr_smoke(
    *,
    ocr_python: str,
    product_name: str | None,
    product_tokens: list[str],
    positive_image: str | None,
    negative_image: str | None,
    min_positive_chars: int,
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    for label, image_source, expect_text in (
        ("ocr_positive", positive_image, True),
        ("ocr_negative", negative_image, False),
    ):
        if not image_source:
            continue
        with _materialize_image(image_source) as image_path:
            ocr_payload = _call_paddleocr(ocr_python=ocr_python, image_path=image_path)
            blocks = [{"text": block["text"], "source": "image"} for block in ocr_payload.get("blocks", [])]
            snapshot = _build_ocr_snapshot(
                image_path=image_path,
                product_name=product_name,
                product_tokens=product_tokens,
                blocks=blocks,
            )
            decision = run_ocr_policy(snapshot)
            raw_char_count = int(ocr_payload.get("char_count", 0))
            admitted_count = len(decision.admitted_blocks)
            checks = {
                "engine_invoked": bool(ocr_payload.get("engine_ok")),
                "raw_text_expectation": raw_char_count >= min_positive_chars if expect_text else True,
                "admission_expectation": admitted_count > 0 if expect_text else admitted_count == 0,
            }
            details = {
                "image_source": image_source,
                "resolved_image_path": str(image_path),
                "raw_char_count": raw_char_count,
                "raw_block_count": len(ocr_payload.get("blocks", [])),
                "raw_text_preview": ocr_payload.get("text_preview"),
                "ocr_python": ocr_python,
                "ocr_status": decision.status,
                "ocr_trigger_reasons": list(decision.trigger_reasons),
                "admitted_block_count": admitted_count,
                "rejected_block_count": len(decision.rejected_blocks),
                "error": ocr_payload.get("error"),
            }
            results.append(
                VerificationResult(
                    label=label,
                    input_url=image_source if _looks_like_url(image_source) else None,
                    expected_page_class="image_heavy_commerce_pdp",
                    page_class="image_heavy_commerce_pdp",
                    supported_for_generation=True,
                    checks=checks,
                    details=details,
                )
            )
    return results


def _call_paddleocr(*, ocr_python: str, image_path: Path) -> dict[str, Any]:
    inline = textwrap.dedent(
        """
        import json
        import sys

        def _texts_from_page(page):
            if page is None:
                return []
            if hasattr(page, "res"):
                return _texts_from_page(page.res)
            if isinstance(page, dict):
                for key in ("rec_texts", "texts"):
                    values = page.get(key)
                    if values:
                        return [str(value).strip() for value in values if str(value).strip()]
                if "dt_polys" in page and "rec_scores" in page:
                    return []
            if isinstance(page, (list, tuple)):
                if page and isinstance(page[0], (list, tuple)) and len(page[0]) >= 2:
                    texts = []
                    for item in page:
                        if len(item) < 2:
                            continue
                        value = item[1]
                        if isinstance(value, (list, tuple)) and value:
                            text = str(value[0]).strip()
                            if text:
                                texts.append(text)
                    return texts
                texts = []
                for item in page:
                    texts.extend(_texts_from_page(item))
                return texts
            return []

        payload = {
            "engine_ok": False,
            "blocks": [],
            "char_count": 0,
            "text_preview": "",
            "error": None,
        }
        try:
            from paddleocr import PaddleOCR

            ocr = PaddleOCR(
                lang="korean",
                use_textline_orientation=True,
                device="cpu",
                enable_mkldnn=False,
                enable_cinn=False,
                enable_hpi=False,
            )
            if hasattr(ocr, "predict"):
                result = ocr.predict(str(sys.argv[1]))
            else:
                result = ocr.ocr(str(sys.argv[1]))
            blocks = []
            for page in result or []:
                for text in _texts_from_page(page):
                    if text:
                        blocks.append({"text": text})
            joined = " ".join(block["text"] for block in blocks).strip()
            payload.update(
                {
                    "engine_ok": True,
                    "blocks": blocks,
                    "char_count": len(joined),
                    "text_preview": joined[:400],
                }
            )
        except Exception as exc:
            payload["error"] = str(exc)
        print(json.dumps(payload, ensure_ascii=False))
        """
    ).strip()
    process = subprocess.run(
        [ocr_python, "-c", inline, str(image_path)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "1",
            "PYTHONPATH": os.pathsep.join(
                [
                    str(OCR_VENV_SITE_PACKAGES),
                    os.environ.get("PYTHONPATH", ""),
                ]
            ).strip(os.pathsep),
        },
    )
    stdout = process.stdout.strip()
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {"engine_ok": False, "blocks": [], "char_count": 0, "text_preview": "", "error": stdout}
    else:
        payload = {"engine_ok": False, "blocks": [], "char_count": 0, "text_preview": "", "error": process.stderr.strip()}
    if process.returncode != 0 and not payload.get("error"):
        payload["error"] = process.stderr.strip() or f"paddleocr subprocess failed with exit code {process.returncode}"
    return payload


def _build_ocr_snapshot(
    *,
    image_path: Path,
    product_name: str | None,
    product_tokens: list[str],
    blocks: list[dict[str, Any]],
) -> NormalizedPageSnapshot:
    token_candidates = list(product_tokens)
    if product_name:
        token_candidates.extend(product_name.replace("/", " ").split())
    unique_tokens = []
    seen: set[str] = set()
    for token in token_candidates:
        normalized = token.strip()
        if len(normalized) < 2:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_tokens.append(normalized)
    return NormalizedPageSnapshot(
        raw_url=str(image_path),
        canonical_url=str(image_path),
        page_class_hint="image_heavy_commerce_pdp",
        final_url=str(image_path),
        http_status=200,
        content_type="image/png",
        fetch_profile_used="ocr_smoke",
        fetched_at=None,
        charset_selected="utf-8",
        charset_confidence=1.0,
        mojibake_flags=[],
        meta_locale="ko_KR",
        language_scores={"ko": 1.0, "en": 0.0},
        title=product_name or image_path.stem,
        meta_description=None,
        canonical_tag=None,
        decoded_text="",
        visible_text_blocks=[],
        breadcrumbs=[],
        structured_data=[],
        primary_product_tokens=unique_tokens,
        price_signals=[],
        buy_signals=[],
        stock_signals=[],
        promo_signals=[],
        support_signals=[],
        download_signals=[],
        blocker_signals=[],
        waiting_signals=[],
        image_candidates=[{"src": str(image_path), "alt": product_name or image_path.stem, "width": 1200, "height": 1200}],
        ocr_trigger_reasons=["manual_ocr_smoke"],
        single_product_confidence=0.95,
        sellability_confidence=0.7,
        support_density=0.0,
        download_density=0.0,
        promo_density=0.0,
        usable_text_chars=0,
        product_name=product_name,
        locale_detected="ko",
        market_locale="ko_KR",
        sellability_state="sellable",
        stock_state="Unknown",
        sufficiency_state="borderline",
        quality_warning=True,
        fallback_used=False,
        weak_backfill_used=False,
        facts=[],
        ocr_text_blocks=blocks,
    )


class _MaterializedImage:
    def __init__(self, source: str) -> None:
        self.source = source
        self.path: Path | None = None
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if _looks_like_url(self.source):
            suffix = Path(urllib.parse.urlsplit(self.source).path).suffix or ".img"
            self._temp_dir = tempfile.TemporaryDirectory()
            self.path = Path(self._temp_dir.name) / f"ocr_input{suffix}"
            urllib.request.urlretrieve(self.source, self.path)
            return self.path
        self.path = Path(self.source).resolve()
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()


def _materialize_image(source: str) -> _MaterializedImage:
    return _MaterializedImage(source)


def _looks_like_url(value: str) -> bool:
    parsed = urllib.parse.urlsplit(value)
    return parsed.scheme in {"http", "https"}


def _aggregate_results(results: list[VerificationResult]) -> dict[str, Any]:
    passed = sum(1 for result in results if all(result.checks.values()))
    failed = len(results) - passed
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
        },
        "results": [result.to_dict() for result in results],
    }


def _print_text(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("Verification summary")
    print(f"total: {summary['total']}")
    print(f"passed: {summary['passed']}")
    print(f"failed: {summary['failed']}")
    print()
    for result in payload["results"]:
        verdict = "PASS" if all(result["checks"].values()) else "FAIL"
        print(f"[{result['label']}] {verdict}")
        if result["input_url"]:
            print(f"  input: {result['input_url']}")
        if result["page_class"]:
            print(f"  page_class: {result['page_class']}")
        if result["expected_page_class"]:
            print(f"  expected_page_class: {result['expected_page_class']}")
        print(f"  supported_for_generation: {result['supported_for_generation']}")
        for key, value in result["checks"].items():
            print(f"  {key}: {value}")
        for key, value in result["details"].items():
            print(f"  {key}: {value}")
        print()


def main() -> None:
    args = _parse_args()
    results: list[VerificationResult] = []

    if args.fixture_suite or args.fixture_case:
        fixture_cases = list(DEFAULT_FIXTURE_CASES) if args.fixture_suite else []
        fixture_cases.extend(_parse_fixture_case(spec) for spec in args.fixture_case)
        results.extend(
            _run_fixture_cases(
                fixture_cases,
                run_page_ocr=args.run_page_ocr,
                allow_ocr_on_unsupported=args.allow_ocr_on_unsupported,
            )
        )

    if args.live_case:
        live_cases = [_parse_live_case(spec) for spec in args.live_case]
        results.extend(
            _run_live_cases(
                live_cases,
                run_page_ocr=args.run_page_ocr,
                allow_ocr_on_unsupported=args.allow_ocr_on_unsupported,
            )
        )

    if args.ocr_positive_image or args.ocr_negative_image:
        results.extend(
            _run_ocr_smoke(
                ocr_python=args.ocr_python,
                product_name=args.ocr_product_name,
                product_tokens=args.ocr_product_token,
                positive_image=args.ocr_positive_image,
                negative_image=args.ocr_negative_image,
                min_positive_chars=args.ocr_min_positive_chars,
            )
        )

    payload = _aggregate_results(results)
    if args.output == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(payload)
    raise SystemExit(0 if payload["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
