from __future__ import annotations

from typing import Any

from src.runtime.service import LocalPipelineRuntime
from .runtime_factory import get_runtime


def collection_worker_handler(event: dict[str, Any], _context: Any, *, runtime: LocalPipelineRuntime | None = None) -> dict[str, Any]:
    resolved_runtime = runtime or get_runtime()
    processed = resolved_runtime.process_collection_records(_records(event))
    return {"processed": processed}


def aggregation_worker_handler(event: dict[str, Any], _context: Any, *, runtime: LocalPipelineRuntime | None = None) -> dict[str, Any]:
    resolved_runtime = runtime or get_runtime()
    processed = resolved_runtime.process_aggregation_records(_records(event))
    return {"processed": processed}


def notification_worker_handler(event: dict[str, Any], _context: Any, *, runtime: LocalPipelineRuntime | None = None) -> dict[str, Any]:
    resolved_runtime = runtime or get_runtime()
    processed = resolved_runtime.process_notification_records(_records(event))
    return {"processed": processed}


def _records(event: dict[str, Any]) -> list[dict[str, Any]]:
    records = event.get("Records")
    if not isinstance(records, list):
        return []
    return records
