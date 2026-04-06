from __future__ import annotations

from src.collection import FixtureHtmlFetcher, classify_snapshot, collect_snapshot_from_html


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
