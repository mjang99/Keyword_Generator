from __future__ import annotations

import sys
from typing import Any

from src.runtime import LocalPipelineRuntime, create_html_collection_runtime_from_env

_RUNTIME: LocalPipelineRuntime | None = None


def ensure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            continue


ensure_utf8_stdio()


def get_runtime(*, fetcher: Any | None = None) -> LocalPipelineRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = create_html_collection_runtime_from_env(fetcher=fetcher)
    return _RUNTIME


def reset_runtime() -> None:
    global _RUNTIME
    _RUNTIME = None
