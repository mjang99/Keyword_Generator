from __future__ import annotations

from scripts.evaluate_collection_fetch_benchmark import (
    _build_case_matrix,
    _build_comparison_row,
    _summarize_sidecars,
)


def test_build_case_matrix_includes_fixed_fixture_and_live_cases() -> None:
    matrix = _build_case_matrix()
    labels = {case["label"] for case in matrix}

    assert "apple_airpodspro_fixture" in labels
    assert "apple_airpodspro3_specs_fixture" in labels
    assert "apple_iphone16" in labels
    assert "samsung_s25_case" in labels
    assert "rankingdak_chicken" in labels


def test_build_comparison_row_emits_required_columns() -> None:
    row = _build_comparison_row(
        case={
            "label": "apple_iphone16",
            "case_type": "live",
            "url": "https://www.apple.com/kr/shop/buy-iphone/iphone-16/example",
        },
        mode="crawl4ai_rendered_html",
        final_url="https://www.apple.com/kr/shop/buy-iphone/iphone-16/example",
        http_status=200,
        blocker_waiting_compatible=True,
        decoded_text_quality="better",
        visible_text_blocks_usefulness="preserved",
        usable_text_chars=1240,
        structured_data_count=2,
        image_candidates_count=8,
        elapsed_seconds=1.23456,
        custom_post_processing="image ranking still custom",
        sidecars={"screenshot_present": True},
    )

    assert row["label"] == "apple_iphone16"
    assert row["mode"] == "crawl4ai_rendered_html"
    assert row["final_url"].startswith("https://www.apple.com/")
    assert row["http_status"] == 200
    assert row["blocker_waiting_compatible"] is True
    assert row["decoded_text_quality"] == "better"
    assert row["visible_text_blocks_usefulness"] == "preserved"
    assert row["usable_text_chars"] == 1240
    assert row["structured_data_count"] == 2
    assert row["image_candidates_count"] == 8
    assert row["screenshot_available"] is True
    assert row["elapsed_seconds"] == 1.235
    assert row["custom_post_processing"] == "image ranking still custom"


def test_summarize_crawl4ai_sidecars_marks_cleaned_html_markdown_and_screenshot_presence() -> None:
    summary = _summarize_sidecars(
        {
            "cleaned_html": "<html><body>Buy now</body></html>",
            "markdown": "Buy now",
            "fit_markdown": "Buy now",
            "screenshot_present": True,
            "media_summary": {"images": 3, "videos": 1, "audios": 0},
        }
    )

    assert summary == {
        "cleaned_html_present": True,
        "markdown_present": True,
        "fit_markdown_present": True,
        "screenshot_available": True,
        "media_images": 3,
        "media_videos": 1,
        "media_audios": 0,
    }
