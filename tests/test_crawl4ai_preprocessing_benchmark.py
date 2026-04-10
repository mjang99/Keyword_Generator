from __future__ import annotations

import scripts.evaluate_crawl4ai_preprocessing_benchmark as preprocessing_benchmark
from scripts.evaluate_crawl4ai_preprocessing_benchmark import (
    PREPROCESSING_BENCHMARK_COLUMNS,
    _resolve_ocr_decision,
    build_preprocessed_snapshot,
    build_preprocessing_benchmark_row,
    build_snapshot_parity_report,
)
from src.collection import HtmlFetchResult, classify_snapshot, collect_snapshot_from_html
from src.collection.models import PageClassification
from src.evidence import build_evidence_pack
from src.ocr.models import OcrRunResult
from src.ocr.models import OcrDecision
from src.ocr.service import run_ocr_policy


def _sample_fetch_result() -> HtmlFetchResult:
    return HtmlFetchResult(
        raw_url="https://example.com/product",
        final_url="https://example.com/product",
        html="""
        <html lang="en">
          <head>
            <title>Example Serum</title>
            <meta name="description" content="Example Serum buy now 39,000 barrier care" />
            <script type="application/ld+json">
              {"@context":"https://schema.org","@type":"Product","name":"Example Serum"}
            </script>
          </head>
          <body>
            <h1>Example Serum</h1>
            <button>Buy now</button>
            <p>Barrier care serum with enough product copy to keep classification stable.</p>
            <img src="/images/example-serum-detail.jpg" alt="Example Serum detail" width="1200" height="1200" />
          </body>
        </html>
        """,
        content_type="text/html; charset=utf-8",
        http_status=200,
        fetch_profile_used="crawl4ai_render",
    )


def test_build_preprocessed_snapshot_keeps_rendered_html_fields_for_cleaned_html_candidate() -> None:
    fetch_result = _sample_fetch_result()
    baseline_snapshot = collect_snapshot_from_html(fetch_result)

    candidate_snapshot, source_loss_notes = build_preprocessed_snapshot(
        fetch_result=fetch_result,
        baseline_snapshot=baseline_snapshot,
        candidate_source="cleaned_html",
        sidecars={
            "cleaned_html": """
            <main>
              <h1>Example Serum</h1>
              <p>Cleaner body copy focused on barrier care and hydration.</p>
            </main>
            """
        },
    )

    assert candidate_snapshot.title == baseline_snapshot.title
    assert candidate_snapshot.meta_description == baseline_snapshot.meta_description
    assert candidate_snapshot.structured_data == baseline_snapshot.structured_data
    assert candidate_snapshot.image_candidates == baseline_snapshot.image_candidates
    assert "Cleaner body copy" in (candidate_snapshot.decoded_text or "")
    assert source_loss_notes == "rendered DOM metadata preserved from raw_html"


def test_build_preprocessed_snapshot_converts_markdown_to_plain_text() -> None:
    fetch_result = _sample_fetch_result()
    baseline_snapshot = collect_snapshot_from_html(fetch_result)

    candidate_snapshot, source_loss_notes = build_preprocessed_snapshot(
        fetch_result=fetch_result,
        baseline_snapshot=baseline_snapshot,
        candidate_source="markdown",
        sidecars={
            "markdown": "# Example Serum\n- Barrier care\n- [Hydration](https://example.com/hydration)\n`Buy now`"
        },
    )

    assert "# Example Serum" not in (candidate_snapshot.decoded_text or "")
    assert "Barrier care" in (candidate_snapshot.decoded_text or "")
    assert "Hydration" in (candidate_snapshot.decoded_text or "")
    assert candidate_snapshot.visible_text_blocks
    assert "DOM block structure is approximated" in source_loss_notes


def test_build_preprocessing_benchmark_row_uses_exact_required_columns() -> None:
    fetch_result = _sample_fetch_result()
    snapshot = collect_snapshot_from_html(fetch_result)
    classification = classify_snapshot(snapshot)
    ocr_decision = run_ocr_policy(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification, ocr_decision)

    row = build_preprocessing_benchmark_row(
        case_id="example_case",
        case_type="fixture",
        candidate_source="raw_html",
        fetch_mode=fetch_result.fetch_profile_used,
        fetch_result=fetch_result,
        snapshot=snapshot,
        classification=classification,
        ocr_decision=ocr_decision,
        evidence_pack=evidence_pack,
        elapsed_seconds=1.23456,
        source_loss_notes="",
        recommendation_flag="candidate",
    )

    assert tuple(row.keys()) == PREPROCESSING_BENCHMARK_COLUMNS
    assert row["case_id"] == "example_case"
    assert row["candidate_source"] == "raw_html"
    assert row["elapsed_seconds"] == 1.235


def test_build_snapshot_parity_report_flags_classification_and_evidence_regressions() -> None:
    fetch_result = _sample_fetch_result()
    baseline_snapshot = collect_snapshot_from_html(fetch_result)
    candidate_snapshot = collect_snapshot_from_html(fetch_result)
    candidate_snapshot.page_class_hint = "non_product_page"

    baseline_classification = PageClassification(
        page_class="commerce_pdp",
        supported_for_generation=True,
        confidence=0.95,
        decisive_signals=["commerce_pdp"],
    )
    candidate_classification = PageClassification(
        page_class="non_product_page",
        supported_for_generation=False,
        confidence=0.95,
        decisive_signals=["non_product_page"],
        failure_code_candidate="non_product_page",
    )
    baseline_ocr_decision = OcrDecision(status="SKIPPED", trigger_reasons=["thin_visible_text"], admitted_blocks=[])
    candidate_ocr_decision = OcrDecision(status="SKIPPED", trigger_reasons=["low_charset_confidence"], admitted_blocks=[])
    baseline_evidence_pack = {"facts": [{"type": "product_name"}, {"type": "brand"}]}
    candidate_evidence_pack = {"facts": [{"type": "brand"}]}

    parity = build_snapshot_parity_report(
        case_id="example_case",
        candidate_source="markdown",
        baseline_snapshot=baseline_snapshot,
        candidate_snapshot=candidate_snapshot,
        baseline_classification=baseline_classification,
        candidate_classification=candidate_classification,
        baseline_ocr_decision=baseline_ocr_decision,
        candidate_ocr_decision=candidate_ocr_decision,
        baseline_evidence_pack=baseline_evidence_pack,
        candidate_evidence_pack=candidate_evidence_pack,
    )

    assert parity["page_class_changed"] is True
    assert parity["supported_changed"] is True
    assert "classification" in parity["regression_stages"]
    assert "ocr_trigger" in parity["regression_stages"]
    assert "evidence" in parity["regression_stages"]
    assert parity["evidence_types_removed"] == ["product_name"]


def test_resolve_ocr_decision_eligible_all_temporarily_expands_runner_cap(monkeypatch) -> None:
    fetch_result = _sample_fetch_result()
    snapshot = collect_snapshot_from_html(fetch_result)
    classification = PageClassification(
        page_class="commerce_pdp",
        supported_for_generation=True,
        confidence=0.95,
        decisive_signals=["commerce_pdp"],
    )
    ranked_candidates = [
        {"src": "https://example.com/detail-1.jpg"},
        {"src": "https://example.com/detail-2.jpg"},
        {"src": "https://example.com/detail-3.jpg"},
    ]
    first_decision = OcrDecision(
        status="AVAILABLE",
        trigger_reasons=["thin_visible_text"],
        ranked_image_candidates=ranked_candidates,
    )
    second_decision = OcrDecision(
        status="AVAILABLE",
        trigger_reasons=["thin_visible_text"],
        ranked_image_candidates=ranked_candidates,
        admitted_blocks=[{"text": "spec"} for _ in ranked_candidates],
    )
    policy_calls = {"count": 0}

    def fake_run_ocr_policy(_snapshot):
        policy_calls["count"] += 1
        if policy_calls["count"] == 1:
            return first_decision
        return second_decision

    class FakeRunner:
        def __init__(self) -> None:
            self.max_images = 1
            self.seen_max_images: int | None = None
            self.seen_candidate_count: int | None = None

        def run(self, _snapshot, candidates):
            self.seen_max_images = self.max_images
            self.seen_candidate_count = len(candidates)
            return OcrRunResult(
                blocks=[{"text": f"ocr-{index}"} for index, _candidate in enumerate(candidates, start=1)],
                image_results=[],
            )

    monkeypatch.setattr(preprocessing_benchmark, "run_ocr_policy", fake_run_ocr_policy)
    runner = FakeRunner()

    decision = _resolve_ocr_decision(
        snapshot=snapshot,
        classification=classification,
        ocr_runner=runner,
        ocr_mode="eligible_all",
    )

    assert runner.seen_max_images == len(ranked_candidates)
    assert runner.seen_candidate_count == len(ranked_candidates)
    assert runner.max_images == 1
    assert len(snapshot.ocr_text_blocks) == len(ranked_candidates)
    assert len(decision.admitted_blocks) == len(ranked_candidates)
