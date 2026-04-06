from .models import NormalizedPageSnapshot, PageClassification
from .service import (
    DEFAULT_FETCH_PROFILES,
    FetchProfile,
    SUPPORTED_PAGE_CLASSES,
    FixtureHtmlFetcher,
    HtmlFetchResult,
    HttpPageFetcher,
    build_snapshot_from_fixture,
    classify_snapshot,
    collect_snapshot_from_html,
)

__all__ = [
    "DEFAULT_FETCH_PROFILES",
    "FetchProfile",
    "FixtureHtmlFetcher",
    "HtmlFetchResult",
    "HttpPageFetcher",
    "NormalizedPageSnapshot",
    "PageClassification",
    "SUPPORTED_PAGE_CLASSES",
    "build_snapshot_from_fixture",
    "classify_snapshot",
    "collect_snapshot_from_html",
]
