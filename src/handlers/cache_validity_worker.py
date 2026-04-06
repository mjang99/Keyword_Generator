from __future__ import annotations

import os
from typing import Any

from src.runtime.service import LocalPipelineRuntime
from .runtime_factory import get_runtime

_VALIDITY_CHECK_MIN_AGE_DAYS = int(os.environ.get("CACHE_VALIDITY_MIN_AGE_DAYS", "7"))


def cache_validity_worker_handler(
    event: dict[str, Any],
    _context: Any,
    *,
    runtime: LocalPipelineRuntime | None = None,
    min_age_days: int = _VALIDITY_CHECK_MIN_AGE_DAYS,
) -> dict[str, Any]:
    """EventBridge-scheduled Lambda: scan cache/, HEAD-check URLs, delete dead entries.

    Triggered daily. Complements the S3 30-day lifecycle policy with active
    content-change invalidation.
    """
    resolved_runtime = runtime or get_runtime()
    result = resolved_runtime.run_cache_validity_sweep(min_age_days=min_age_days)
    return result
