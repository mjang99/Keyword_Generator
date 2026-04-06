from __future__ import annotations

from typing import Any

from src.runtime import LocalPipelineRuntime, create_html_collection_runtime_from_env

_RUNTIME: LocalPipelineRuntime | None = None


def get_runtime(*, fetcher: Any | None = None) -> LocalPipelineRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = create_html_collection_runtime_from_env(fetcher=fetcher)
    return _RUNTIME


def reset_runtime() -> None:
    global _RUNTIME
    _RUNTIME = None
