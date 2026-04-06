from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import boto3

from src.keyword_generation.models import KeywordRow

from .core import JobEvaluationInput, PerUrlEvaluationInput


def fetch_job_status(*, api_base: str, job_id: str, timeout: int = 30) -> dict[str, Any]:
    base = api_base.rstrip("/") + "/"
    url = urljoin(base, f"jobs/{job_id}")
    payload = _load_json_via_http(url, timeout=timeout)
    if "job_id" not in payload:
        raise ValueError("job status payload missing job_id")
    return payload


def load_combined_payload_from_job(
    *,
    api_base: str,
    job_id: str,
    timeout: int = 30,
    region_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    status_payload = fetch_job_status(api_base=api_base, job_id=job_id, timeout=timeout)
    artifacts = status_payload.get("artifacts") or {}
    combined_json_url = artifacts.get("combined_json_url")
    if combined_json_url:
        try:
            combined = load_json_from_source(
                combined_json_url,
                api_base=api_base,
                timeout=timeout,
                region_name=region_name,
            )
            return status_payload, combined
        except Exception:
            pass

    manifest_url = artifacts.get("result_manifest_url")
    if not manifest_url:
        raise ValueError("job status payload has no combined_json_url or result_manifest_url")
    manifest = load_json_from_source(manifest_url, api_base=api_base, timeout=timeout, region_name=region_name)
    combined = _build_combined_from_manifest(
        manifest=manifest,
        requested_platform_mode=status_payload.get("requested_platform_mode", "both"),
        api_base=api_base,
        timeout=timeout,
        region_name=region_name,
    )
    return status_payload, combined


def load_json_from_source(
    source: str,
    *,
    api_base: str | None = None,
    timeout: int = 30,
    region_name: str | None = None,
) -> dict[str, Any]:
    if source.startswith("s3://"):
        return _load_json_from_s3(source, region_name=region_name)
    if source.startswith("http://") or source.startswith("https://"):
        return _load_json_via_http(source, timeout=timeout)
    if source.startswith("/"):
        if not api_base:
            raise ValueError("relative artifact URL requires api_base")
        return _load_json_via_http(urljoin(api_base.rstrip("/") + "/", source.lstrip("/")), timeout=timeout)
    path = Path(source)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_job_input_from_combined_payload(payload: dict[str, Any]) -> JobEvaluationInput:
    successes: list[PerUrlEvaluationInput] = []
    for success in payload.get("successes", []):
        report = success.get("validation_report") or {}
        successes.append(
            PerUrlEvaluationInput(
                url_task_id=str(success.get("url_task_id") or ""),
                raw_url=str(success.get("raw_url") or ""),
                page_class=str(success.get("page_class") or ""),
                requested_platform_mode=str(success.get("requested_platform_mode") or payload.get("requested_platform_mode") or "both"),
                quality_warning=bool(report.get("quality_warning", False)),
                rows=[KeywordRow(**row) for row in success.get("rows", [])],
                status=str(success.get("status") or "COMPLETED"),
            )
        )

    return JobEvaluationInput(
        job_id=str(payload.get("job_id") or ""),
        requested_platform_mode=str(payload.get("requested_platform_mode") or "both"),
        successes=successes,
        failures=list(payload.get("failures", [])),
    )


def _build_combined_from_manifest(
    *,
    manifest: dict[str, Any],
    requested_platform_mode: str,
    api_base: str,
    timeout: int,
    region_name: str | None,
) -> dict[str, Any]:
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in manifest.get("items", []):
        artifact = item.get("artifact")
        if not artifact:
            continue
        payload = load_json_from_source(artifact, api_base=api_base, timeout=timeout, region_name=region_name)
        status = str(item.get("status") or payload.get("status") or "")
        if status in {"COMPLETED", "COMPLETED_CACHED"}:
            successes.append(payload)
        else:
            failures.append(payload)

    return {
        "job_id": manifest.get("job_id"),
        "requested_platform_mode": requested_platform_mode,
        "successes": successes,
        "failures": failures,
    }


def _load_json_via_http(url: str, *, timeout: int) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_json_from_s3(source: str, *, region_name: str | None) -> dict[str, Any]:
    parsed = urlparse(source)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    client = boto3.client("s3", region_name=region_name)
    response = client.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read().decode("utf-8"))
