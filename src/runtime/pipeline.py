from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any
from typing import Callable

from src.collection import build_snapshot_from_fixture, classify_snapshot, collect_snapshot_from_html
from src.evidence import build_evidence_pack
from src.ocr import OcrRunResult, OcrRunner, run_ocr_policy

from .models import LocalResolvedFailure, LocalResolvedSuccess


@dataclass(slots=True)
class FixturePipeline:
    fixture_loader: Callable[[str], dict]
    url_to_fixture: dict[str, str | dict]

    def resolve(self, raw_url: str) -> LocalResolvedSuccess | LocalResolvedFailure:
        if raw_url not in self.url_to_fixture:
            return LocalResolvedFailure(
                failure_code="collection_fixture_missing",
                failure_detail=f"no fixture configured for {raw_url}",
            )
        source = self.url_to_fixture[raw_url]
        payload = self.fixture_loader(source) if isinstance(source, str) else dict(source)
        payload.setdefault("raw_url", raw_url)
        payload.setdefault("canonical_url", raw_url)

        snapshot = build_snapshot_from_fixture(payload)
        classification = classify_snapshot(snapshot)
        ocr_result = run_ocr_policy(snapshot)
        if not classification.supported_for_generation:
            return LocalResolvedFailure(
                failure_code=classification.failure_code_candidate or "unsupported_page",
                failure_detail=f"{classification.page_class} is unsupported for generation",
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
                ocr_result=asdict(ocr_result),
            )
        return LocalResolvedSuccess(
            evidence_pack=build_evidence_pack(snapshot, classification, ocr_result),
            snapshot=asdict(snapshot),
            classification=asdict(classification),
            ocr_result=asdict(ocr_result),
        )


@dataclass(slots=True)
class HtmlCollectionPipeline:
    fetcher: Callable[[str], Any] | Any
    ocr_runner: OcrRunner | None = None
    allow_ocr_for_unsupported: bool = False

    def resolve(self, raw_url: str) -> LocalResolvedSuccess | LocalResolvedFailure:
        try:
            fetch_result = self.fetcher.fetch(raw_url)
        except Exception as error:
            return LocalResolvedFailure(
                failure_code="collection_fetch_failed",
                failure_detail=str(error),
            )

        snapshot = collect_snapshot_from_html(fetch_result)
        classification = classify_snapshot(snapshot)
        ocr_result = self._resolve_ocr(snapshot, classification)
        if not classification.supported_for_generation:
            return LocalResolvedFailure(
                failure_code=classification.failure_code_candidate or "unsupported_page",
                failure_detail=f"{classification.page_class} is unsupported for generation",
                page_class=classification.page_class,
                quality_warning=snapshot.quality_warning,
                snapshot=asdict(snapshot),
                classification=asdict(classification),
                ocr_result=asdict(ocr_result),
            )
        return LocalResolvedSuccess(
            evidence_pack=build_evidence_pack(snapshot, classification, ocr_result),
            snapshot=asdict(snapshot),
            classification=asdict(classification),
            ocr_result=asdict(ocr_result),
        )

    def _resolve_ocr(self, snapshot, classification):
        ocr_result = run_ocr_policy(snapshot)
        if self.ocr_runner is None:
            return ocr_result
        if not classification.supported_for_generation and not self.allow_ocr_for_unsupported:
            return ocr_result
        if snapshot.ocr_text_blocks:
            return ocr_result
        if not ocr_result.ranked_image_candidates:
            return ocr_result
        if "ocr_not_required" in ocr_result.trigger_reasons:
            return ocr_result

        runner_output = self.ocr_runner.run(snapshot, ocr_result.ranked_image_candidates)
        if isinstance(runner_output, OcrRunResult):
            snapshot.ocr_text_blocks = list(runner_output.blocks)
            snapshot.ocr_image_results = list(runner_output.image_results)
        else:
            snapshot.ocr_text_blocks = list(runner_output)
            snapshot.ocr_image_results = []
        if not snapshot.ocr_text_blocks:
            return run_ocr_policy(snapshot)
        return run_ocr_policy(snapshot)
