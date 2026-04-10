from __future__ import annotations

from src.collection import Crawl4AiPageFetcher, FixtureHtmlFetcher, HtmlFetchResult, build_snapshot_from_fixture, classify_snapshot
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
    assert "the collector reached a blocker or challenge page instead of product content" in (
        result.failure_reason_hints or []
    )


def test_html_collection_pipeline_fetch_failure_returns_predicted_reason_hints() -> None:
    class _Fetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            raise RuntimeError(f"failed to fetch {raw_url}: timed out waiting for response")

    pipeline = HtmlCollectionPipeline(fetcher=_Fetcher())

    result = pipeline.resolve("https://example.com/slow-product")

    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "collection_fetch_failed"
    assert "page response or browser render exceeded the collector timeout" in (result.failure_reason_hints or [])
    assert "if the page depends on client-side rendering, retry it through the Crawl4AI fallback collector" in (
        result.failure_reason_hints or []
    )


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


def test_html_collection_pipeline_with_crawl4ai_fetcher_preserves_snapshot_contract() -> None:
    def fake_crawl(raw_url: str) -> dict:
        assert raw_url == "https://www.on.com/en-us/products/cloudmonster"
        return {
            "final_url": raw_url,
            "html": """
            <html lang="en">
              <head>
                <title>On Cloudmonster</title>
                <meta name="description" content="On Cloudmonster running shoe buy now 229,000" />
              </head>
              <body>
                <h1>On Cloudmonster</h1>
                <button>Add to cart</button>
                <div>229,000</div>
                <p>
                  On Cloudmonster running shoe with max cushioning, forward rolling comfort,
                  and enough visible copy to keep the collection classifier in supported commerce.
                  Shop now for a single product detail page with checkout intent and price visibility.
                </p>
                <img src="/images/cloudmonster-detail.jpg" alt="On Cloudmonster detail" />
              </body>
            </html>
            """,
            "content_type": "text/html; charset=utf-8",
            "http_status": 200,
            "response_headers": {"Content-Type": "text/html; charset=utf-8"},
            "sidecars": {"screenshot_present": True},
        }

    pipeline = HtmlCollectionPipeline(fetcher=Crawl4AiPageFetcher(run_crawl=fake_crawl))

    result = pipeline.resolve("https://www.on.com/en-us/products/cloudmonster")

    assert isinstance(result, LocalResolvedSuccess)
    assert result.classification["supported_for_generation"] is True
    assert result.classification["page_class"] in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert result.snapshot["fetch_profile_used"] == "crawl4ai_render"
    assert result.snapshot["product_name"] == "On Cloudmonster"
    assert result.snapshot["preprocessing_source"] == "raw_html"


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


def test_html_collection_pipeline_returns_reason_hints_when_ocr_runner_raises(fixtures_dir) -> None:
    del fixtures_dir

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
                <img ec-data-src="/web/upload/webp/skin/260119_centella1_05_result.webp" alt="3초만에 진정 피부결 변화" />
              </body>
            </html>
            """
            return HtmlFetchResult(raw_url=raw_url, final_url=raw_url, html=html)

    class _Runner:
        def run(self, snapshot, candidates):
            del snapshot
            del candidates
            raise RuntimeError("OCR subprocess timeout after 30 seconds")

    pipeline = HtmlCollectionPipeline(
        fetcher=_Fetcher(),
        ocr_runner=_Runner(),
    )

    result = pipeline.resolve("https://example.com/aprilskin-pdp")

    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "collection_ocr_failed"
    assert "OCR execution failed after collection completed" in (result.failure_reason_hints or [])
    assert "the OCR image sweep exceeded the configured timeout" in (result.failure_reason_hints or [])


def test_html_collection_pipeline_uses_crawl4ai_cleaned_html_as_fallback_source() -> None:
    class _BaselineFetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            return HtmlFetchResult(
                raw_url=raw_url,
                final_url=raw_url,
                html="""
                <html lang="ko">
                  <head><title>Promo Landing</title></head>
                  <body><section>coupon event benefit sale</section></body>
                </html>
                """,
                fetch_profile_used="desktop_chrome",
            )

    def _fallback_crawl(raw_url: str) -> dict:
        return {
            "final_url": raw_url,
            "html": """
            <html lang="ko">
              <head>
                <title>Rankingdak Chicken Breast</title>
                <meta name="description" content="닭가슴살 23,900원 장바구니 구매하기" />
              </head>
              <body>
                <h1>Rankingdak Chicken Breast</h1>
                <button>장바구니</button>
                <div>23,900원</div>
                <p>
                  닭가슴살 상세 본문과 실제 구매 문맥이 있는 단일 상품 페이지입니다.
                  냉장 보관 제품 안내와 구매 설명, 중량 정보, 배송 정보가 본문에 함께 포함됩니다.
                  단일 상품 페이지로서 실제 장바구니 구매 흐름과 가격 정보가 명확하게 드러납니다.
                </p>
                <script type="application/ld+json">
                {"@type":"Product","name":"Rankingdak Chicken Breast","offers":{"price":"23900","priceCurrency":"KRW"}}
                </script>
              </body>
            </html>
            """,
                "sidecars": {
                    "cleaned_html": """
                    <html><body>
                    Rankingdak Chicken Breast
                    장바구니 구매하기
                    23,900원
                    단일 상품 페이지
                    냉장 보관 제품 안내와 구매 설명
                    중량 정보와 배송 정보
                    실제 장바구니 구매 흐름
                    </body></html>
                    """
                },
            }

    pipeline = HtmlCollectionPipeline(
        fetcher=_BaselineFetcher(),
        fallback_fetcher=Crawl4AiPageFetcher(run_crawl=_fallback_crawl),
    )

    result = pipeline.resolve("https://example.com/product/rankingdak-chicken")

    assert isinstance(result, LocalResolvedSuccess)
    assert result.snapshot["fallback_used"] is True
    assert result.snapshot["fallback_reason"] == "client_side_render_suspected"
    assert result.snapshot["preprocessing_source"] == "cleaned_html"
    assert result.classification["supported_for_generation"] is True


def test_html_collection_pipeline_falls_back_to_rendered_raw_html_when_cleaned_html_is_too_thin() -> None:
    class _BaselineFetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            return HtmlFetchResult(
                raw_url=raw_url,
                final_url=raw_url,
                html="<html><head><title>Promo Landing</title></head><body>coupon event sale</body></html>",
                fetch_profile_used="desktop_chrome",
            )

    def _fallback_crawl(raw_url: str) -> dict:
        return {
            "final_url": raw_url,
            "html": """
            <html lang="ko">
              <head>
                <title>APRILSKIN Serum</title>
                <meta name="description" content="세럼 38,000원 장바구니 구매하기" />
              </head>
              <body>
                <h1>APRILSKIN Serum</h1>
                <button>장바구니</button>
                <div>38,000원</div>
                <p>
                  충분한 본문이 있는 실제 상품 페이지입니다.
                  피부 진정과 보습에 대한 상세 설명, 사용 방법, 용량과 배송 안내가 함께 제공됩니다.
                  구매 버튼과 가격 정보가 명확하게 보이는 단일 상품 상세 페이지입니다.
                </p>
                <script type="application/ld+json">
                {"@type":"Product","name":"APRILSKIN Serum","offers":{"price":"38000","priceCurrency":"KRW"}}
                </script>
              </body>
            </html>
            """,
            "sidecars": {"cleaned_html": "<html><body>세럼</body></html>"},
        }

    pipeline = HtmlCollectionPipeline(
        fetcher=_BaselineFetcher(),
        fallback_fetcher=Crawl4AiPageFetcher(run_crawl=_fallback_crawl),
    )

    result = pipeline.resolve("https://example.com/product/aprilskin-serum")

    assert isinstance(result, LocalResolvedSuccess)
    assert result.snapshot["fallback_used"] is True
    assert result.snapshot["preprocessing_source"] == "raw_html"


def test_html_collection_pipeline_returns_root_cause_when_baseline_and_fallback_both_fail() -> None:
    class _BaselineFetcher:
        def fetch(self, raw_url: str) -> HtmlFetchResult:
            raise RuntimeError(f"failed to fetch {raw_url}: timed out waiting for response")

    def _fallback_crawl(raw_url: str) -> dict:
        raise RuntimeError(f"failed to fetch {raw_url}: Crawl4AI returned empty html")

    pipeline = HtmlCollectionPipeline(
        fetcher=_BaselineFetcher(),
        fallback_fetcher=Crawl4AiPageFetcher(run_crawl=_fallback_crawl),
    )

    result = pipeline.resolve("https://example.com/dynamic-product")

    assert isinstance(result, LocalResolvedFailure)
    assert result.failure_code == "collection_fetch_failed"
    assert "baseline fetch failed and Crawl4AI fallback also failed" in result.failure_detail
    assert "Crawl4AI fallback was triggered because `baseline_fetch_failed`" in (result.failure_reason_hints or [])
