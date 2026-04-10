from __future__ import annotations

from typing import Any


FIXTURE_CASES = (
    {
        "label": "apple_airpodspro_fixture",
        "case_type": "fixture",
        "url": "https://www.apple.com/kr/shop/product/airpods-pro",
        "fixture_path": "artifacts/service_test_pages/apple_airpodspro_kr.html",
    },
    {
        "label": "apple_airpodspro3_specs_fixture",
        "case_type": "fixture",
        "url": "https://www.apple.com/kr/airpods-pro/specs/",
        "fixture_path": "artifacts/service_test_pages/apple_airpodspro3_specs_ko.html",
    },
)

LIVE_CASES = (
    {
        "label": "apple_iphone16",
        "case_type": "live",
        "url": "https://www.apple.com/kr/shop/buy-iphone/iphone-16/6.7%ED%98%95-%EB%94%94%EC%8A%A4%ED%94%8C%EB%A0%88%EC%9D%B4-512gb-%ED%8B%B8",
    },
    {
        "label": "samsung_s25_case",
        "case_type": "live",
        "url": "https://www.samsung.com/sec/mobile-accessories/silicone-case-for-galaxy-s-25-series/EF-PS931CREGKR/",
    },
    {
        "label": "rankingdak_chicken",
        "case_type": "live",
        "url": "https://www.rankingdak.com/product/view?productCd=F000008814",
    },
)


def _build_case_matrix() -> list[dict[str, Any]]:
    return [*FIXTURE_CASES, *LIVE_CASES]


def _summarize_sidecars(sidecars: dict[str, Any] | None) -> dict[str, Any]:
    payload = sidecars or {}
    media_summary = payload.get("media_summary") or {}
    return {
        "cleaned_html_present": bool(payload.get("cleaned_html")),
        "markdown_present": bool(payload.get("markdown")),
        "fit_markdown_present": bool(payload.get("fit_markdown")),
        "screenshot_available": bool(payload.get("screenshot_present")),
        "media_images": int(media_summary.get("images", 0) or 0),
        "media_videos": int(media_summary.get("videos", 0) or 0),
        "media_audios": int(media_summary.get("audios", 0) or 0),
    }


def _build_comparison_row(
    *,
    case: dict[str, Any],
    mode: str,
    final_url: str,
    http_status: int | None,
    blocker_waiting_compatible: bool,
    decoded_text_quality: str,
    visible_text_blocks_usefulness: str,
    usable_text_chars: int,
    structured_data_count: int,
    image_candidates_count: int,
    elapsed_seconds: float,
    custom_post_processing: str,
    sidecars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sidecar_summary = _summarize_sidecars(sidecars)
    return {
        "label": case["label"],
        "case_type": case["case_type"],
        "mode": mode,
        "url": case["url"],
        "final_url": final_url,
        "http_status": http_status,
        "blocker_waiting_compatible": blocker_waiting_compatible,
        "decoded_text_quality": decoded_text_quality,
        "visible_text_blocks_usefulness": visible_text_blocks_usefulness,
        "usable_text_chars": usable_text_chars,
        "structured_data_count": structured_data_count,
        "image_candidates_count": image_candidates_count,
        "screenshot_available": sidecar_summary["screenshot_available"],
        "elapsed_seconds": round(elapsed_seconds, 3),
        "custom_post_processing": custom_post_processing,
        **sidecar_summary,
    }
