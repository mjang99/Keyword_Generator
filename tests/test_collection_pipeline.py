from __future__ import annotations

from src.collection import FixtureHtmlFetcher, HtmlFetchResult, build_snapshot_from_fixture, classify_snapshot
from src.evidence import build_evidence_pack
from src.ocr import OcrRunResult, run_ocr_policy
from src.runtime import FixturePipeline, HtmlCollectionPipeline, LocalResolvedFailure, LocalResolvedSuccess


def test_supported_fixture_flows_through_collection_and_evidence_builder(evidence_fixture_loader) -> None:
    payload = evidence_fixture_loader("evidence_commerce_pdp_rich.json")
    snapshot = build_snapshot_from_fixture(payload)
    classification = classify_snapshot(snapshot)
    evidence_pack = build_evidence_pack(snapshot, classification)
    ocr_result = run_ocr_policy(snapshot)

    assert classification.supported_for_generation is True
    assert classification.page_class == "commerce_pdp"
    assert evidence_pack["page_class"] == "commerce_pdp"
    assert evidence_pack["product_name"]
    assert evidence_pack["facts"]
    assert ocr_result.status == "SKIPPED"


def test_unsupported_fixture_pipeline_returns_terminal_failure(evidence_fixture_loader) -> None:
    pipeline = FixturePipeline(
        fixture_loader=evidence_fixture_loader,
        url_to_fixture={
            "https://example.com/promo": {
                "raw_url": "https://example.com/promo",
                "canonical_url": "https://example.com/promo",
                "page_class": "promo_heavy_commerce_landing",
                "quality_warning": False,
                "facts": [],
            }
        },
    )

    result = pipeline.resolve("https://example.com/promo")
    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "promo_heavy_commerce_landing"
    assert result.page_class == "promo_heavy_commerce_landing"


def test_fixture_pipeline_emits_evidence_pack_for_supported_url(evidence_fixture_loader) -> None:
    pipeline = FixturePipeline(
        fixture_loader=evidence_fixture_loader,
        url_to_fixture={"https://example.com/specs": "evidence_support_spec.json"},
    )

    result = pipeline.resolve("https://example.com/specs")
    assert isinstance(result, LocalResolvedSuccess)
    assert result.evidence_pack["page_class"] == "support_spec_page"
    assert result.evidence_pack["quality_warning"] is True
    assert result.ocr_result["status"] == "SKIPPED"


def test_html_collection_pipeline_emits_evidence_pack_for_supported_url(fixtures_dir) -> None:
    pipeline = HtmlCollectionPipeline(
        fetcher=FixtureHtmlFetcher(
            base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
            url_to_file={"https://example.com/on-pdp": "on_pdp_en.html"},
        )
    )

    result = pipeline.resolve("https://example.com/on-pdp")
    assert isinstance(result, LocalResolvedSuccess)
    assert result.classification["supported_for_generation"] is True
    assert result.evidence_pack["page_class"] in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert result.snapshot["fetch_profile_used"] == "fixture_html"


def test_html_collection_pipeline_returns_terminal_failure_for_blocked_page(fixtures_dir) -> None:
    pipeline = HtmlCollectionPipeline(
        fetcher=FixtureHtmlFetcher(
            base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
            url_to_file={"https://example.com/naver-blocked": "naver_smartstore_blocked.html"},
        )
    )

    result = pipeline.resolve("https://example.com/naver-blocked")
    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "blocked_page"
    assert result.page_class == "blocked_page"


def test_classify_snapshot_bedrock_gate_uses_visible_blocks_or_decoded_text(monkeypatch) -> None:
    snapshot = build_snapshot_from_fixture(
        {
            "raw_url": "https://example.com/rankingdak-product",
            "canonical_url": "https://example.com/rankingdak-product",
            "page_class": "promo_heavy_commerce_landing",
            "title": "[맛있닭] 소스 닭가슴살",
            "product_name": "[맛있닭] 소스 닭가슴살",
            "meta_description": "장바구니 구매하기 23,900원",
            "decoded_text": "장바구니 구매하기 23,900원 맛있닭 소스 닭가슴살 상세 설명이 충분히 길게 이어집니다.",
            "visible_text_blocks": [" ", "  ", "\t"],
            "structured_data": [],
        }
    )
    captured: dict[str, str] = {}

    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")
    def _fake_converse(user_prompt, **kwargs):
        captured["prompt"] = user_prompt
        return "apac.anthropic.claude-3-5-sonnet-20241022-v2:0", '{"is_product_sales_page": true, "reason": "supported product page"}'

    monkeypatch.setattr("src.clients.bedrock.converse_text", _fake_converse)

    classification = classify_snapshot(snapshot)

    assert classification.page_class == "promo_heavy_commerce_landing"
    assert "Product name: [맛있닭] 소스 닭가슴살" in captured["prompt"]
    assert "장바구니 구매하기 23,900원" in captured["prompt"]


def test_classify_snapshot_bedrock_gate_does_not_override_waiting_page(monkeypatch) -> None:
    snapshot = build_snapshot_from_fixture(
        {
            "raw_url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000183208",
            "canonical_url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000183208",
            "page_class": "waiting_page",
            "title": "잠시만 기다려 주세요 - 올리브영",
            "decoded_text": "잠시만 기다려 주세요",
            "visible_text_blocks": ["잠시만 기다려 주세요"],
        }
    )
    called = {"value": False}

    monkeypatch.setenv("KEYWORD_GENERATOR_GENERATION_MODE", "bedrock")

    def _fake_converse(*args, **kwargs):
        called["value"] = True
        return "apac.anthropic.claude-3-5-sonnet-20241022-v2:0", '{"is_product_sales_page": false, "reason": "waiting page"}'

    monkeypatch.setattr("src.clients.bedrock.converse_text", _fake_converse)

    classification = classify_snapshot(snapshot)

    assert classification.page_class == "waiting_page"
    assert classification.supported_for_generation is False
    assert called["value"] is False


def test_html_collection_pipeline_runs_ocr_runner_for_hidden_detail_assets() -> None:
    class _Fetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            html = """
            <html lang="ko">
              <head>
                <title>APRILSKIN Mugwort Centella Calming Serum</title>
                <meta name="description" content="Mugwort Centella Calming Serum 110g" />
              </head>
                  <body>
                    <button>add to cart</button>
                    <div>38,000</div>
                    <div>110g</div>
                    <p>
                      Mugwort Centella Calming Serum soothes visible redness, supports the skin barrier,
                      delivers lightweight hydration, and is designed for sensitive trouble-prone skin.
                      Mugwort Centella Calming Serum includes product detail storytelling so the page stays
                      above the minimum visible text threshold used by the classifier.
                    </p>
                    <img src="/images/product-hero.jpg" alt="제품 메인" width="1200" height="1200" />
                    <img ec-data-src="/web/upload/webp/skin/260119_centella1_05_result.webp" alt="3초컷 진정 카밍앰플" />
                  </body>
            </html>
            """
            return HtmlFetchResult(raw_url=raw_url, final_url=raw_url, html=html)

    class _Runner:
        def run(self, snapshot, candidates):
            assert candidates
            assert candidates[0]["src"].endswith("260119_centella1_05_result.webp")
            return [{"text": "Mugwort Centella Calming Serum 3초컷 진정 카밍앰플 쑥잎수 50% 병풀잎수 40%", "source": "image"}]

    pipeline = HtmlCollectionPipeline(fetcher=_Fetcher(), ocr_runner=_Runner())

    result = pipeline.resolve("https://aprilskin.com/product/detail.html?product_no=1448")

    assert isinstance(result, LocalResolvedSuccess)
    assert result.ocr_result["status"] == "AVAILABLE"
    assert len(result.ocr_result["admitted_blocks"]) == 1
    assert result.evidence_pack["ocr_used"] is True


def test_html_collection_pipeline_does_not_run_ocr_runner_for_unsupported_page() -> None:
    class _Fetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            html = """
            <html lang="en">
              <head>
                <title>Spring Sale Event</title>
              </head>
              <body>
                <section>coupon event benefit promotion sale</section>
                <img ec-data-src="/web/upload/webp/event/spec-table.webp" alt="comparison table 5N 7GB" />
              </body>
            </html>
            """
            return HtmlFetchResult(raw_url=raw_url, final_url=raw_url, html=html)

    class _Runner:
        def __init__(self) -> None:
            self.called = False

        def run(self, snapshot, candidates):
            self.called = True
            return OcrRunResult()

    runner = _Runner()
    pipeline = HtmlCollectionPipeline(fetcher=_Fetcher(), ocr_runner=runner)

    result = pipeline.resolve("https://example.com/promo-event")

    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "promo_heavy_commerce_landing"
    assert runner.called is False
    assert result.ocr_result["status"] == "SKIPPED"


def test_html_collection_pipeline_can_run_ocr_runner_for_unsupported_when_explicitly_enabled() -> None:
    class _Fetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            html = """
            <html lang="en">
              <head>
                <title>Spring Sale Event</title>
              </head>
              <body>
                <section>coupon event benefit promotion sale</section>
                <img ec-data-src="/web/upload/webp/event/spec-table.webp" alt="comparison table 5N 7GB" />
              </body>
            </html>
            """
            return HtmlFetchResult(raw_url=raw_url, final_url=raw_url, html=html)

    class _Runner:
        def __init__(self) -> None:
            self.called = False

        def run(self, snapshot, candidates):
            self.called = True
            return OcrRunResult(
                blocks=[],
                image_results=[
                    {
                        "image_src": candidates[0]["src"],
                        "image_attribute": candidates[0]["attribute"],
                        "image_score": candidates[0]["score"],
                        "candidate_type": candidates[0]["candidate_type"],
                        "pipeline_type": candidates[0]["ocr_pipeline_type"],
                        "engine_used": "PPStructureV3",
                        "raw_block_count": 0,
                        "raw_char_count": 0,
                        "status": "completed_no_text",
                        "error": None,
                    }
                ],
            )

    runner = _Runner()
    pipeline = HtmlCollectionPipeline(fetcher=_Fetcher(), ocr_runner=runner, allow_ocr_for_unsupported=True)

    result = pipeline.resolve("https://example.com/promo-event")

    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "promo_heavy_commerce_landing"
    assert runner.called is True
    assert result.ocr_result["image_results"][0]["pipeline_type"] == "structured_table"
