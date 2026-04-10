from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError
from urllib.error import URLError

import pytest

from src.collection import Crawl4AiPageFetcher, DEFAULT_FETCH_PROFILES, HttpPageFetcher


class _FakeResponse:
    def __init__(self, *, body: bytes, url: str, headers: dict[str, str], status: int = 200) -> None:
        self._body = body
        self._url = url
        self.headers = headers
        self.status = status

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_http_page_fetcher_decodes_cp949_html() -> None:
    source = (
        "<html lang='ko'><head><meta charset='cp949'><title>라네즈 크림</title></head>"
        "<body>장바구니 가격 12,000원</body></html>"
    )
    body = source.encode("cp949")

    def fake_open(request, timeout):
        return _FakeResponse(
            body=body,
            url=request.full_url,
            headers={"Content-Type": "text/html"},
        )

    result = HttpPageFetcher(
        profiles=(DEFAULT_FETCH_PROFILES[0],),
        open_url=fake_open,
    ).fetch("https://example.com/laneige")

    assert "라네즈 크림" in result.html
    assert result.charset_selected == "cp949"
    assert result.fetch_profile_used == "desktop_chrome"
    assert result.charset_confidence is not None


def test_http_page_fetcher_retries_next_profile_on_url_error() -> None:
    calls: list[str] = []
    body = b"<html><head><title>Fallback</title></head><body>ok</body></html>"

    def fake_open(request, timeout):
        calls.append(request.headers.get("User-agent", ""))
        if len(calls) == 1:
            raise URLError("timed out")
        return _FakeResponse(
            body=body,
            url=request.full_url,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    result = HttpPageFetcher(open_url=fake_open).fetch("https://example.com/fallback")

    assert len(calls) == 2
    assert result.fetch_profile_used == "generic_html"
    assert "Fallback" in result.html


def test_http_page_fetcher_returns_html_from_http_error_body() -> None:
    body = b"<html><head><title>Denied</title></head><body>access denied</body></html>"

    def fake_open(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=403,
            msg="Forbidden",
            hdrs={"Content-Type": "text/html; charset=utf-8"},
            fp=BytesIO(body),
        )

    result = HttpPageFetcher(
        profiles=(DEFAULT_FETCH_PROFILES[0],),
        open_url=fake_open,
    ).fetch("https://example.com/blocked")

    assert result.http_status == 403
    assert "access denied" in result.html.lower()
    assert result.fetch_profile_used == "desktop_chrome"


def test_crawl4ai_page_fetcher_returns_rendered_html_in_html_fetch_result() -> None:
    def fake_crawl(raw_url: str) -> dict:
        assert raw_url == "https://example.com/rendered"
        return {
            "final_url": "https://example.com/rendered?variant=1",
            "html": "<html><head><title>Rendered</title></head><body><button>Buy now</button></body></html>",
            "content_type": "text/html; charset=utf-8",
            "http_status": 200,
            "response_headers": {"Content-Type": "text/html; charset=utf-8"},
            "sidecars": {
                "cleaned_html": "<html><body>Buy now</body></html>",
                "markdown": "Buy now",
                "fit_markdown": "Buy now",
                "screenshot_present": True,
                "media_summary": {"images": 2, "videos": 0, "audios": 0},
            },
        }

    fetcher = Crawl4AiPageFetcher(run_crawl=fake_crawl)

    result = fetcher.fetch("https://example.com/rendered")

    assert "Buy now" in result.html
    assert result.final_url == "https://example.com/rendered?variant=1"
    assert result.http_status == 200
    assert result.content_type == "text/html; charset=utf-8"
    assert result.fetch_profile_used == "crawl4ai_render"
    assert fetcher.last_sidecars == {
        "cleaned_html": "<html><body>Buy now</body></html>",
        "markdown": "Buy now",
        "fit_markdown": "Buy now",
        "screenshot_present": True,
        "media_summary": {"images": 2, "videos": 0, "audios": 0},
    }


def test_crawl4ai_page_fetcher_raises_runtime_error_on_crawl_failure() -> None:
    fetcher = Crawl4AiPageFetcher(run_crawl=lambda raw_url: (_ for _ in ()).throw(ValueError("crawl failed")))

    with pytest.raises(RuntimeError, match="failed to fetch https://example.com/fail: crawl failed"):
        fetcher.fetch("https://example.com/fail")
