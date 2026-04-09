from __future__ import annotations

from src.collection import FixtureHtmlFetcher, HtmlFetchResult, classify_snapshot, collect_snapshot_from_html


def test_html_fixture_fetcher_loads_local_service_page(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/on-pdp": "on_pdp_en.html"},
    )
    result = fetcher.fetch("https://example.com/on-pdp")
    assert result.http_status == 200
    assert "Cloudtilt" in result.html


def test_html_collection_classifies_commerce_pdp(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/on-pdp": "on_pdp_en.html"},
    )
    snapshot = collect_snapshot_from_html(fetcher.fetch("https://example.com/on-pdp"))
    classification = classify_snapshot(snapshot)

    assert snapshot.title
    assert snapshot.price_signals
    assert (snapshot.sellability_confidence or 0) >= 0.4
    assert classification.page_class in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert classification.supported_for_generation is True


def test_html_collection_classifies_non_product_listing(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/on-category": "on_category_en.html"},
    )
    snapshot = collect_snapshot_from_html(fetcher.fetch("https://example.com/on-category"))
    classification = classify_snapshot(snapshot)

    assert classification.page_class == "non_product_page"
    assert classification.supported_for_generation is False


def test_html_collection_classifies_support_spec_page(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/airpods-spec": "apple_airpodspro3_specs_ko.html"},
    )
    snapshot = collect_snapshot_from_html(fetcher.fetch("https://example.com/airpods-spec"))
    classification = classify_snapshot(snapshot)

    assert "기술 사양" in (snapshot.title or "")
    assert snapshot.support_signals
    assert classification.page_class == "support_spec_page"
    assert classification.supported_for_generation is True


def test_html_collection_classifies_blocked_page(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/naver-blocked": "naver_smartstore_blocked.html"},
    )
    snapshot = collect_snapshot_from_html(fetcher.fetch("https://example.com/naver-blocked"))
    classification = classify_snapshot(snapshot)

    assert snapshot.blocker_signals
    assert classification.page_class == "blocked_page"
    assert classification.supported_for_generation is False


def test_html_collection_classifies_promo_heavy_landing(fixtures_dir) -> None:
    fetcher = FixtureHtmlFetcher(
        base_dir=fixtures_dir.parent.parent / "artifacts" / "service_test_pages",
        url_to_file={"https://example.com/amore-home": "amoremall_home_ko.html"},
    )
    snapshot = collect_snapshot_from_html(fetcher.fetch("https://example.com/amore-home"))
    classification = classify_snapshot(snapshot)

    assert snapshot.promo_signals
    assert classification.page_class == "promo_heavy_commerce_landing"
    assert classification.supported_for_generation is False


def test_html_collection_extracts_hidden_detail_image_candidates() -> None:
    html = """
    <html lang="ko">
      <head><title>APRILSKIN Mugwort Centella Calming Serum</title></head>
      <body>
        <img src="/images/product-hero.jpg" alt="제품 메인" width="1200" height="1200" />
        <img ec-data-src="/web/upload/webp/skin/260119_centella1_01_result.webp" alt="고민부위까지 진정" />
        <img data-src="/web/upload/skin/260119_centella1_03_result.jpg" alt="진정 레시피" />
      </body>
    </html>
    """
    snapshot = collect_snapshot_from_html(
        HtmlFetchResult(
            raw_url="https://aprilskin.com/product/detail.html?product_no=1448",
            final_url="https://aprilskin.com/product/detail.html?product_no=1448",
            html=html,
        )
    )

    assert len(snapshot.image_candidates) == 3
    assert any(candidate["attribute"] == "ec-data-src" for candidate in snapshot.image_candidates)
    assert any(candidate["attribute"] == "data-src" for candidate in snapshot.image_candidates)
    assert any(candidate["detail_hint"] for candidate in snapshot.image_candidates)


def test_html_collection_keeps_promo_heavy_pdp_supported_when_product_evidence_is_strong() -> None:
    html = """
    <html lang="ko">
      <head>
        <title>갤럭시 S25 실리콘 케이스 (레드) | EF-PS931CREGKR | Samsung 대한민국</title>
        <meta name="description" content="이벤트 혜택 할인 쿠폰과 함께 구매할 수 있는 갤럭시 S25 실리콘 케이스." />
        <meta property="og:title" content="갤럭시 S25 실리콘 케이스" />
        <meta property="og:description" content="장바구니 구매하기 39,000원 실리콘 케이스" />
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product","name":"갤럭시 S25 실리콘 케이스","brand":{"@type":"Brand","name":"Samsung"}}
        </script>
      </head>
      <body>
        <button>장바구니</button>
        <button>구매하기</button>
        <div>39,000</div>
        <section>이벤트 혜택 할인 쿠폰 프로모션</section>
      </body>
    </html>
    """
    snapshot = collect_snapshot_from_html(
        HtmlFetchResult(
            raw_url="https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/",
            final_url="https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/",
            html=html,
        )
    )
    classification = classify_snapshot(snapshot)

    assert snapshot.product_name == "갤럭시 S25 실리콘 케이스"
    assert snapshot.page_class_hint in {"commerce_pdp", "image_heavy_commerce_pdp"}
    assert classification.supported_for_generation is True


def test_html_collection_uses_og_title_when_html_title_is_generic() -> None:
    html = """
    <html lang="ko">
      <head>
        <title>랭킹닭컴</title>
        <meta property="og:title" content="[맛있닭] 소스 닭가슴살" />
        <meta property="og:description" content="장바구니 구매하기 23,900원" />
      </head>
      <body>
        <button>장바구니</button>
        <button>구매하기</button>
        <div>23,900</div>
      </body>
    </html>
    """
    snapshot = collect_snapshot_from_html(
        HtmlFetchResult(
            raw_url="https://www.rankingdak.com/product/view?productCd=F000008814",
            final_url="https://www.rankingdak.com/product/view?productCd=F000008814",
            html=html,
        )
    )

    assert snapshot.title == "[맛있닭] 소스 닭가슴살"
    assert snapshot.product_name == "[맛있닭] 소스 닭가슴살"
    assert "F000008814" not in snapshot.product_name
    assert snapshot.page_class_hint in {"commerce_pdp", "image_heavy_commerce_pdp"}


def test_html_collection_classifies_waf_challenge_as_blocked_page() -> None:
    html = """
    <html lang="en">
      <head><title></title></head>
      <body>
        <script>
          window.awsWafCookieDomainList = [];
          window.gokuProps = {"key": "abc"};
        </script>
      </body>
    </html>
    """
    snapshot = collect_snapshot_from_html(
        HtmlFetchResult(
            raw_url="https://www.gentlemonster.com/kr/en/item/VGNJIZ4ANR8I/loloe01",
            final_url="https://www.gentlemonster.com/kr/en/item/VGNJIZ4ANR8I/loloe01",
            html=html,
            http_status=202,
        )
    )
    classification = classify_snapshot(snapshot)

    assert snapshot.blocker_signals
    assert classification.page_class == "blocked_page"
    assert classification.supported_for_generation is False
