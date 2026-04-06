from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any
from typing import Callable

from src.collection import build_snapshot_from_fixture, classify_snapshot, collect_snapshot_from_html
from src.evidence import build_evidence_pack
from src.ocr import run_ocr_policy

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
