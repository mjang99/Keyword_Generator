from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from src.exporting import NotificationTarget
from src.runtime.service import LocalPipelineRuntime
from .runtime_factory import get_runtime


def submit_job_handler(event: dict[str, Any], _context: Any, *, runtime: LocalPipelineRuntime | None = None) -> dict[str, Any]:
    resolved_runtime = runtime or get_runtime()
    body = _json_body(event)
    urls = body.get("urls")
    if not isinstance(urls, list) or not urls:
        return _json_response(400, {"error": "urls must be a non-empty list"})
    if len(urls) > 30:
        return _json_response(422, {"error": "urls must contain at most 30 entries"})

    requested_platform_mode = body.get("requested_platform_mode", "both")
    if requested_platform_mode not in {"naver_sa", "google_sa", "both"}:
        return _json_response(422, {"error": "unsupported requested_platform_mode"})

    try:
        notification_target = _parse_notification_target(body.get("notification_target"))
    except ValueError as exc:
        return _json_response(400, {"error": str(exc)})

    job_id = resolved_runtime.submit_job(
        urls=[str(url) for url in urls],
        requested_platform_mode=requested_platform_mode,
        notification_target=notification_target,
    )
    payload = resolved_runtime.build_job_status_payload(job_id)
    return _json_response(
        202,
        {
            "job_id": job_id,
            "status": "RECEIVED",
            "requested_platform_mode": requested_platform_mode,
            "submitted_count": payload["counts"]["submitted"],
            "cached_count": payload["counts"]["cached"],
            "status_url": f"/jobs/{job_id}",
            "result_manifest_url": f"/jobs/{job_id}/results/per_url_manifest",
        },
    )


def get_job_handler(event: dict[str, Any], _context: Any, *, runtime: LocalPipelineRuntime | None = None) -> dict[str, Any]:
    resolved_runtime = runtime or get_runtime()
    job_id = ((event.get("pathParameters") or {}).get("job_id") or "").strip()
    if not job_id:
        return _json_response(400, {"error": "job_id is required"})
    try:
        payload = resolved_runtime.build_job_status_payload(job_id)
    except KeyError:
        return _json_response(404, {"error": "job not found"})
    return _json_response(200, payload)


def _parse_notification_target(raw_target: Any) -> NotificationTarget | None:
    if raw_target is None:
        return None
    if not isinstance(raw_target, dict):
        raise ValueError("notification_target must be an object")
    email = raw_target.get("email")
    webhook = raw_target.get("webhook")
    if bool(email) == bool(webhook):
        raise ValueError("notification_target must include exactly one of email or webhook")
    if email:
        return NotificationTarget(target_type="email", value=str(email))
    return NotificationTarget(target_type="webhook", value=str(webhook))


def _json_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    return json.loads(body)


def _json_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
