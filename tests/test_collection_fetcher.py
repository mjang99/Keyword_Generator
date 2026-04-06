from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError
from urllib.error import URLError

from src.collection import DEFAULT_FETCH_PROFILES, HttpPageFetcher


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
