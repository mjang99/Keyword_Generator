from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from src.collection import Crawl4AiPageFetcher, HttpPageFetcher
from src.exporting import (
    JobArtifactUrls,
    NotificationTarget,
    UrlExportResult,
    UrlFailureResult,
    aggregate_job_status,
    build_combined_json_payload,
    build_failures_manifest,
    build_notification_payload,
    build_per_url_json_payload,
    flatten_rows_for_csv,
)
from src.keyword_generation.models import GenerationRequest
from src.keyword_generation.service import generate_keywords
from src.ocr import create_subprocess_ocr_runner_from_env

from .models import LocalResolvedFailure, LocalResolvedSuccess, RuntimeNotificationRecord
from .pipeline import HtmlCollectionPipeline

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "src",
    "_hsenc",
    "_hsmi",
}


@dataclass(slots=True)
class RuntimeResources:
    bucket_name: str
    table_name: str
    collection_queue_url: str
    aggregation_queue_url: str
    notification_queue_url: str


def load_runtime_resources_from_env() -> RuntimeResources:
    bucket_name = os.environ["KEYWORD_GENERATOR_BUCKET"]
    table_name = os.environ["KEYWORD_GENERATOR_TABLE"]
    collection_queue_url = os.environ["KEYWORD_GENERATOR_COLLECTION_QUEUE_URL"]
    aggregation_queue_url = os.environ["KEYWORD_GENERATOR_AGGREGATION_QUEUE_URL"]
    notification_queue_url = os.environ["KEYWORD_GENERATOR_NOTIFICATION_QUEUE_URL"]
    return RuntimeResources(
        bucket_name=bucket_name,
        table_name=table_name,
        collection_queue_url=collection_queue_url,
        aggregation_queue_url=aggregation_queue_url,
        notification_queue_url=notification_queue_url,
    )


def create_runtime_resources(
    *,
    s3_client: Any,
    dynamodb_client: Any,
    sqs_client: Any,
    bucket_name: str = "keyword-generator-runtime",
    table_name: str = "keyword-generator-runtime",
    collection_queue_name: str = "keyword-generator-collection",
    aggregation_queue_name: str = "keyword-generator-aggregation",
    notification_queue_name: str = "keyword-generator-notification",
) -> RuntimeResources:
    region = s3_client.meta.region_name or "ap-northeast-2"
    create_bucket_kwargs: dict[str, Any] = {"Bucket": bucket_name}
    if region != "us-east-1":
        create_bucket_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3_client.create_bucket(**create_bucket_kwargs)

    dynamodb_client.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    collection_queue_url = sqs_client.create_queue(QueueName=collection_queue_name)["QueueUrl"]
    aggregation_queue_url = sqs_client.create_queue(QueueName=aggregation_queue_name)["QueueUrl"]
    notification_queue_url = sqs_client.create_queue(QueueName=notification_queue_name)["QueueUrl"]
    return RuntimeResources(
        bucket_name=bucket_name,
        table_name=table_name,
        collection_queue_url=collection_queue_url,
        aggregation_queue_url=aggregation_queue_url,
        notification_queue_url=notification_queue_url,
    )


def create_html_collection_runtime(
    *,
    s3_client: Any,
    dynamodb_client: Any,
    sqs_client: Any,
    resources: RuntimeResources,
    fetcher: Any | None = None,
    fallback_fetcher: Any | None = None,
    ocr_runner: Any | None = None,
    allow_ocr_for_unsupported: bool = False,
    policy_version: str = "policy_v1",
    taxonomy_version: str = "tax_v2026_04_03",
    generator_version: str = "gen_v3",
) -> "LocalPipelineRuntime":
    return LocalPipelineRuntime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=resources,
        resolver=HtmlCollectionPipeline(
            fetcher=fetcher or HttpPageFetcher(),
            fallback_fetcher=fallback_fetcher,
            ocr_runner=ocr_runner,
            allow_ocr_for_unsupported=allow_ocr_for_unsupported,
        ).resolve,
        policy_version=policy_version,
        taxonomy_version=taxonomy_version,
        generator_version=generator_version,
    )


def create_html_collection_runtime_from_env(
    *,
    fetcher: Any | None = None,
    fallback_fetcher: Any | None = None,
    ocr_runner: Any | None = None,
    region_name: str | None = None,
) -> "LocalPipelineRuntime":
    resolved_region = region_name or os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2")
    s3_client = boto3.client("s3", region_name=resolved_region)
    dynamodb_client = boto3.client("dynamodb", region_name=resolved_region)
    sqs_client = boto3.client("sqs", region_name=resolved_region)
    return create_html_collection_runtime(
        s3_client=s3_client,
        dynamodb_client=dynamodb_client,
        sqs_client=sqs_client,
        resources=load_runtime_resources_from_env(),
        fetcher=fetcher,
        fallback_fetcher=fallback_fetcher or _build_crawl4ai_fallback_fetcher_from_env(),
        ocr_runner=ocr_runner or create_subprocess_ocr_runner_from_env(),
        allow_ocr_for_unsupported=os.environ.get("KEYWORD_GENERATOR_OCR_ALLOW_UNSUPPORTED", "").strip().lower()
        in {"1", "true", "yes", "on"},
        policy_version=os.environ.get("KEYWORD_GENERATOR_POLICY_VERSION", "policy_v1"),
        taxonomy_version=os.environ.get("KEYWORD_GENERATOR_TAXONOMY_VERSION", "tax_v2026_04_03"),
        generator_version=os.environ.get("KEYWORD_GENERATOR_GENERATOR_VERSION", "gen_v3"),
    )


def _build_crawl4ai_fallback_fetcher_from_env() -> Any | None:
    enabled = os.environ.get("KEYWORD_GENERATOR_COLLECTION_CRAWL4AI_FALLBACK_ENABLED", "").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None
    return Crawl4AiPageFetcher(
        wait_for_images=os.environ.get("KEYWORD_GENERATOR_CRAWL4AI_WAIT_FOR_IMAGES", "").strip().lower()
        in {"1", "true", "yes", "on"},
        simulate_user=os.environ.get("KEYWORD_GENERATOR_CRAWL4AI_SIMULATE_USER", "").strip().lower()
        in {"1", "true", "yes", "on"},
        remove_overlay_elements=os.environ.get("KEYWORD_GENERATOR_CRAWL4AI_REMOVE_OVERLAYS", "").strip().lower()
        in {"1", "true", "yes", "on"},
        magic=os.environ.get("KEYWORD_GENERATOR_CRAWL4AI_MAGIC", "").strip().lower() in {"1", "true", "yes", "on"},
        enable_stealth=os.environ.get("KEYWORD_GENERATOR_CRAWL4AI_ENABLE_STEALTH", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )


class LocalPipelineRuntime:
    def __init__(
        self,
        *,
        s3_client: Any,
        dynamodb_client: Any,
        sqs_client: Any,
        resources: RuntimeResources,
        resolver: Callable[[str], LocalResolvedSuccess | LocalResolvedFailure],
        policy_version: str = "policy_v1",
        taxonomy_version: str = "tax_v2026_04_03",
        generator_version: str = "gen_v3",
    ) -> None:
        self.s3_client = s3_client
        self.dynamodb_client = dynamodb_client
        self.sqs_client = sqs_client
        self.resources = resources
        self.resolver = resolver
        self.policy_version = policy_version
        self.taxonomy_version = taxonomy_version
        self.generator_version = generator_version
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()
        self._job_sequence = 0

    def submit_job(
        self,
        *,
        urls: list[str],
        requested_platform_mode: str,
        notification_target: NotificationTarget | None = None,
    ) -> str:
        self._job_sequence += 1
        job_id = f"job_{self._job_sequence:04d}"
        created_at = self._now()
        self._put_item(
            {
                "pk": f"JOB#{job_id}",
                "sk": "META",
                "entity_type": "job",
                "job_id": job_id,
                "status": "RECEIVED",
                "requested_platform_mode": requested_platform_mode,
                "submitted_count": len(urls),
                "succeeded_count": 0,
                "failed_count": 0,
                "created_at": created_at,
                "notification_target": asdict(notification_target) if notification_target else None,
            }
        )

        _kv = dict(
            policy_version=self.policy_version,
            taxonomy_version=self.taxonomy_version,
            generator_version=self.generator_version,
        )
        misses = 0
        for index, raw_url in enumerate(urls, start=1):
            url_task_id = f"ut_{job_id}_{index:02d}"
            canonical_url = canonicalize_url(raw_url)
            naver_key = build_cache_key(canonical_url=canonical_url, platform_component="naver_sa", **_kv)
            google_key = build_cache_key(canonical_url=canonical_url, platform_component="google_sa", **_kv)

            base_task = {
                "pk": f"JOB#{job_id}",
                "sk": f"URL#{url_task_id}",
                "entity_type": "url_task",
                "job_id": job_id,
                "url_task_id": url_task_id,
                "raw_url": raw_url,
                "canonical_url": canonical_url,
                "requested_platform_mode": requested_platform_mode,
                "naver_cache_key": naver_key,
                "google_cache_key": google_key,
                "created_at": created_at,
            }

            # --- cache lookup ---
            if requested_platform_mode == "naver_sa":
                cache_payload = self._load_cached_payload(naver_key)
                hit_payload = cache_payload
            elif requested_platform_mode == "google_sa":
                cache_payload = self._load_cached_payload(google_key)
                hit_payload = cache_payload
            else:  # both
                naver_payload = self._load_cached_payload(naver_key)
                google_payload = self._load_cached_payload(google_key)
                if naver_payload is not None and google_payload is not None:
                    hit_payload = _merge_platform_components(naver_payload, google_payload)
                    hit_payload["url_task_id"] = url_task_id
                    hit_payload["raw_url"] = raw_url
                elif naver_payload is not None or google_payload is not None:
                    # Partial cache hit — store cached component, queue only the missing one
                    partial_cached_platform = "naver_sa" if naver_payload is not None else "google_sa"
                    partial_payload = naver_payload if naver_payload is not None else google_payload
                    partial_key = self._partial_cache_s3_key(job_id, url_task_id)
                    self._write_json(partial_key, partial_payload)
                    misses += 1
                    self._put_item({**base_task, "status": "RECEIVED", "cache_hit": False})
                    self._send_queue_message(
                        self.resources.collection_queue_url,
                        {
                            "job_id": job_id,
                            "url_task_id": url_task_id,
                            "raw_url": raw_url,
                            "partial_cached_platform": partial_cached_platform,
                            "partial_cache_s3_key": partial_key,
                        },
                    )
                    continue
                else:
                    hit_payload = None

            if hit_payload is not None:
                result_key = self._job_result_key(job_id, url_task_id)
                cached_copy = {**hit_payload, "cache_hit": True}
                self._write_json(result_key, cached_copy)
                self._put_item(
                    {
                        **base_task,
                        "status": "COMPLETED_CACHED",
                        "page_class": cached_copy.get("page_class"),
                        "cache_hit": True,
                        "fallback_used": bool(cached_copy.get("fallback_used")),
                        "fallback_reason": _optional_str(cached_copy.get("fallback_reason")),
                        "preprocessing_source": _optional_str(cached_copy.get("preprocessing_source")),
                        "result_s3_key": result_key,
                    }
                )
                self._send_queue_message(
                    self.resources.aggregation_queue_url,
                    {"job_id": job_id, "url_task_id": url_task_id, "status": "COMPLETED_CACHED"},
                )
            else:
                misses += 1
                self._put_item({**base_task, "status": "RECEIVED", "cache_hit": False})
                self._send_queue_message(
                    self.resources.collection_queue_url,
                    {"job_id": job_id, "url_task_id": url_task_id, "raw_url": raw_url},
                )

        if misses:
            self._update_job(job_id, {"status": "PROCESSING"})
        return job_id

    def drain_all(self) -> None:
        while True:
            progressed = False
            progressed = self._drain_collection_queue() or progressed
            progressed = self._drain_aggregation_queue() or progressed
            progressed = self._drain_notification_queue() or progressed
            if not progressed:
                break

    def get_job(self, job_id: str) -> dict[str, Any]:
        item = self._get_item(f"JOB#{job_id}", "META")
        if item is None:
            raise KeyError(job_id)
        return item

    def get_url_tasks(self, job_id: str) -> list[dict[str, Any]]:
        items = self._query_job_items(job_id)
        return sorted(
            [item for item in items if item["entity_type"] == "url_task"],
            key=lambda item: item["url_task_id"],
        )

    def read_json_artifact(self, key: str) -> Any:
        return self._read_json(key)

    def list_notification_records(self, job_id: str) -> list[RuntimeNotificationRecord]:
        items = self._query_job_items(job_id)
        records: list[RuntimeNotificationRecord] = []
        for item in items:
            if item.get("entity_type") != "notification_outbox":
                continue
            records.append(
                RuntimeNotificationRecord(
                    job_id=item["job_id"],
                    status=item["status"],
                    payload=item["payload"],
                    target=NotificationTarget(**item["notification_target"]),
                )
            )
        return records

    def process_collection_records(self, records: list[dict[str, Any]]) -> int:
        processed = 0
        for record in records:
            body = json.loads(record["body"]) if isinstance(record.get("body"), str) else record["body"]
            self._handle_collection_message(body)
            processed += 1
        return processed

    def process_aggregation_records(self, records: list[dict[str, Any]]) -> int:
        processed = 0
        for record in records:
            body = json.loads(record["body"]) if isinstance(record.get("body"), str) else record["body"]
            self._finalize_job_if_terminal(body["job_id"])
            processed += 1
        return processed

    def process_notification_records(self, records: list[dict[str, Any]]) -> int:
        processed = 0
        for record in records:
            body = json.loads(record["body"]) if isinstance(record.get("body"), str) else record["body"]
            self._deliver_notification(body["job_id"])
            processed += 1
        return processed

    def build_job_status_payload(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        url_tasks = self.get_url_tasks(job_id)
        cached_count = sum(1 for task in url_tasks if task["status"] == "COMPLETED_CACHED")
        artifacts = job.get("artifacts") or {}
        notification_target = job.get("notification_target")
        return {
            "job_id": job_id,
            "status": job["status"],
            "requested_platform_mode": job["requested_platform_mode"],
            "counts": {
                "submitted": job["submitted_count"],
                "cached": cached_count,
                "succeeded": job.get("succeeded_count", 0),
                "failed": job.get("failed_count", 0),
            },
            "artifacts": {
                "result_manifest_url": artifacts.get("result_manifest_url"),
                "combined_json_url": artifacts.get("combined_json_url"),
                "combined_csv_url": artifacts.get("combined_csv_url"),
                "failures_json_url": artifacts.get("failures_json_url"),
            },
            "url_tasks": [
                {
                    "url_task_id": task["url_task_id"],
                    "raw_url": task["raw_url"],
                    "status": task["status"],
                    "page_class": task.get("page_class"),
                    "failure_code": task.get("failure_code"),
                    "failure_detail": task.get("failure_detail"),
                    "failure_reason_hints": task.get("failure_reason_hints", []),
                    "fallback_used": bool(task.get("fallback_used")),
                    "fallback_reason": task.get("fallback_reason"),
                    "preprocessing_source": task.get("preprocessing_source"),
                    "cache_hit": bool(task.get("cache_hit")),
                }
                for task in url_tasks
            ],
            "notification": {
                "target_type": notification_target.get("target_type"),
                "value": notification_target.get("value"),
                "sent": bool(job.get("notification_sent_at")),
            }
            if notification_target
            else None,
        }

    def _drain_collection_queue(self) -> bool:
        messages = self._receive_messages(self.resources.collection_queue_url)
        if not messages:
            return False
        for message in messages:
            body = json.loads(message["Body"])
            self._handle_collection_message(body)
            self.sqs_client.delete_message(
                QueueUrl=self.resources.collection_queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        return True

    def _drain_aggregation_queue(self) -> bool:
        messages = self._receive_messages(self.resources.aggregation_queue_url)
        if not messages:
            return False
        for message in messages:
            body = json.loads(message["Body"])
            self._finalize_job_if_terminal(body["job_id"])
            self.sqs_client.delete_message(
                QueueUrl=self.resources.aggregation_queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        return True

    def _drain_notification_queue(self) -> bool:
        messages = self._receive_messages(self.resources.notification_queue_url)
        if not messages:
            return False
        for message in messages:
            body = json.loads(message["Body"])
            self._deliver_notification(body["job_id"])
            self.sqs_client.delete_message(
                QueueUrl=self.resources.notification_queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        return True

    def _handle_collection_message(self, body: dict[str, Any]) -> None:
        job_id = body["job_id"]
        url_task_id = body["url_task_id"]
        raw_url = body["raw_url"]
        task = self._get_item(f"JOB#{job_id}", f"URL#{url_task_id}")
        if task is None:
            return

        resolved = self.resolver(raw_url)
        if isinstance(resolved, LocalResolvedFailure):
            if resolved.snapshot is not None:
                self._write_json(self._job_snapshot_key(job_id, url_task_id), resolved.snapshot)
            if resolved.classification is not None:
                self._write_json(self._job_classification_key(job_id, url_task_id), resolved.classification)
            if resolved.ocr_result is not None:
                self._write_json(self._job_ocr_key(job_id, url_task_id), resolved.ocr_result)
            failure = UrlFailureResult(
                url_task_id=url_task_id,
                raw_url=raw_url,
                page_class=resolved.page_class,
                requested_platform_mode=task["requested_platform_mode"],
                failure_code=resolved.failure_code,
                failure_detail=resolved.failure_detail,
                failure_reason_hints=list(resolved.failure_reason_hints or []),
                quality_warning=resolved.quality_warning,
                fallback_used=bool((resolved.snapshot or {}).get("fallback_used")),
                fallback_reason=(resolved.snapshot or {}).get("fallback_reason"),
                preprocessing_source=(resolved.snapshot or {}).get("preprocessing_source"),
            )
            failure_key = self._job_failure_key(job_id, url_task_id)
            self._write_json(failure_key, asdict(failure))
            self._put_item(
                {
                    **task,
                    "status": "FAILED_COLLECTION",
                    "page_class": resolved.page_class,
                    "failure_code": resolved.failure_code,
                    "failure_detail": resolved.failure_detail,
                    "failure_reason_hints": list(resolved.failure_reason_hints or []),
                    "quality_warning": resolved.quality_warning,
                    "fallback_used": bool((resolved.snapshot or {}).get("fallback_used")),
                    "fallback_reason": (resolved.snapshot or {}).get("fallback_reason"),
                    "preprocessing_source": (resolved.snapshot or {}).get("preprocessing_source"),
                    "collection_snapshot_s3_key": self._job_snapshot_key(job_id, url_task_id)
                    if resolved.snapshot is not None
                    else None,
                    "classification_s3_key": self._job_classification_key(job_id, url_task_id)
                    if resolved.classification is not None
                    else None,
                    "ocr_s3_key": self._job_ocr_key(job_id, url_task_id)
                    if resolved.ocr_result is not None
                    else None,
                    "failure_s3_key": failure_key,
                }
            )
            self._send_queue_message(
                self.resources.aggregation_queue_url,
                {"job_id": job_id, "url_task_id": url_task_id, "status": "FAILED_COLLECTION"},
            )
            return

        evidence_pack = dict(resolved.evidence_pack)
        evidence_pack.setdefault("raw_url", raw_url)
        evidence_pack.setdefault("canonical_url", task["canonical_url"])
        if resolved.snapshot is not None:
            self._write_json(self._job_snapshot_key(job_id, url_task_id), resolved.snapshot)
        if resolved.classification is not None:
            self._write_json(self._job_classification_key(job_id, url_task_id), resolved.classification)
        if resolved.ocr_result is not None:
            self._write_json(self._job_ocr_key(job_id, url_task_id), resolved.ocr_result)
        self._write_json(self._job_evidence_key(job_id, url_task_id), evidence_pack)

        # Partial cache hit: generate only the missing platform component
        partial_cached_platform = body.get("partial_cached_platform")
        partial_cache_s3_key = body.get("partial_cache_s3_key")
        requested_platform_mode = task["requested_platform_mode"]
        if partial_cached_platform and requested_platform_mode == "both":
            generation_platform = "google_sa" if partial_cached_platform == "naver_sa" else "naver_sa"
        else:
            generation_platform = requested_platform_mode

        generation_result = generate_keywords(
            GenerationRequest(
                evidence_pack=evidence_pack,
                requested_platform_mode=generation_platform,
            )
        )
        if generation_result.status == "COMPLETED":
            success = UrlExportResult(
                url_task_id=url_task_id,
                raw_url=raw_url,
                page_class=str(evidence_pack.get("page_class")),
                requested_platform_mode=generation_platform,
                generation_result=generation_result,
                cache_hit=False,
                fallback_used=bool(evidence_pack.get("fallback_used")),
                fallback_reason=_optional_str(evidence_pack.get("fallback_reason")),
                preprocessing_source=_optional_str(evidence_pack.get("preprocessing_source")),
            )
            payload = build_per_url_json_payload(success)

            # Merge with cached component if partial hit
            if partial_cached_platform and partial_cache_s3_key:
                partial_payload = self._read_json(partial_cache_s3_key)
                if partial_cached_platform == "naver_sa":
                    payload = _merge_platform_components(partial_payload, payload)
                else:
                    payload = _merge_platform_components(payload, partial_payload)
                payload["url_task_id"] = url_task_id
                payload["raw_url"] = raw_url

            result_key = self._job_result_key(job_id, url_task_id)
            self._write_json(result_key, payload)

            # Write per-component cache keys
            if requested_platform_mode == "both":
                self._write_json(
                    self._cache_object_key(task["naver_cache_key"]),
                    _extract_platform_component(payload, "naver_sa"),
                )
                self._write_json(
                    self._cache_object_key(task["google_cache_key"]),
                    _extract_platform_component(payload, "google_sa"),
                )
            elif requested_platform_mode == "naver_sa":
                self._write_json(self._cache_object_key(task["naver_cache_key"]), payload)
            else:
                self._write_json(self._cache_object_key(task["google_cache_key"]), payload)
            self._put_item(
                {
                    **task,
                    "status": "COMPLETED",
                    "page_class": success.page_class,
                    "quality_warning": payload["validation_report"]["quality_warning"],
                    "fallback_used": success.fallback_used,
                    "fallback_reason": success.fallback_reason,
                    "preprocessing_source": success.preprocessing_source,
                    "collection_snapshot_s3_key": self._job_snapshot_key(job_id, url_task_id)
                    if resolved.snapshot is not None
                    else None,
                    "classification_s3_key": self._job_classification_key(job_id, url_task_id)
                    if resolved.classification is not None
                    else None,
                    "ocr_s3_key": self._job_ocr_key(job_id, url_task_id)
                    if resolved.ocr_result is not None
                    else None,
                    "evidence_s3_key": self._job_evidence_key(job_id, url_task_id),
                    "result_s3_key": result_key,
                }
            )
            self._send_queue_message(
                self.resources.aggregation_queue_url,
                {"job_id": job_id, "url_task_id": url_task_id, "status": "COMPLETED"},
            )
            return

        failure = UrlFailureResult(
            url_task_id=url_task_id,
            raw_url=raw_url,
            page_class=str(evidence_pack.get("page_class")),
            requested_platform_mode=task["requested_platform_mode"],
            failure_code=generation_result.validation_report.failure_code or "generation_failed",
            failure_detail=generation_result.validation_report.failure_detail or "generation failed",
            quality_warning=generation_result.validation_report.quality_warning,
            fallback_used=bool(evidence_pack.get("fallback_used")),
            fallback_reason=_optional_str(evidence_pack.get("fallback_reason")),
            preprocessing_source=_optional_str(evidence_pack.get("preprocessing_source")),
        )
        failed_result = UrlExportResult(
            url_task_id=url_task_id,
            raw_url=raw_url,
            page_class=failure.page_class or "",
            requested_platform_mode=generation_platform,
            generation_result=generation_result,
            cache_hit=False,
            fallback_used=failure.fallback_used,
            fallback_reason=failure.fallback_reason,
            preprocessing_source=failure.preprocessing_source,
        )
        result_key = self._job_result_key(job_id, url_task_id)
        self._write_json(result_key, build_per_url_json_payload(failed_result))
        failure_key = self._job_failure_key(job_id, url_task_id)
        self._write_json(failure_key, asdict(failure))
        self._put_item(
            {
                **task,
                "status": "FAILED_GENERATION",
                "page_class": failure.page_class,
                "failure_code": failure.failure_code,
                "failure_detail": failure.failure_detail,
                "quality_warning": failure.quality_warning,
                "fallback_used": failure.fallback_used,
                "fallback_reason": failure.fallback_reason,
                "preprocessing_source": failure.preprocessing_source,
                "collection_snapshot_s3_key": self._job_snapshot_key(job_id, url_task_id)
                if resolved.snapshot is not None
                else None,
                "classification_s3_key": self._job_classification_key(job_id, url_task_id)
                if resolved.classification is not None
                else None,
                "ocr_s3_key": self._job_ocr_key(job_id, url_task_id)
                if resolved.ocr_result is not None
                else None,
                "evidence_s3_key": self._job_evidence_key(job_id, url_task_id),
                "result_s3_key": result_key,
                "failure_s3_key": failure_key,
            }
        )
        self._send_queue_message(
            self.resources.aggregation_queue_url,
            {"job_id": job_id, "url_task_id": url_task_id, "status": "FAILED_GENERATION"},
        )

    def _finalize_job_if_terminal(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job["status"] in {"COMPLETED", "PARTIAL_COMPLETED", "FAILED"}:
            return

        tasks = self.get_url_tasks(job_id)
        if not tasks or any(task["status"] == "RECEIVED" for task in tasks):
            return

        successes: list[UrlExportResult] = []
        failures: list[UrlFailureResult] = []
        manifest_entries: list[dict[str, Any]] = []

        for task in tasks:
            if task["status"] in {"COMPLETED", "COMPLETED_CACHED"}:
                payload = self._read_json(task["result_s3_key"])
                manifest_entries.append(
                    {
                        "url_task_id": task["url_task_id"],
                        "status": task["status"],
                        "artifact": self._s3_uri(task["result_s3_key"]),
                    }
                )
                successes.append(
                    UrlExportResult(
                        url_task_id=task["url_task_id"],
                        raw_url=task["raw_url"],
                        page_class=payload["page_class"],
                        requested_platform_mode=task["requested_platform_mode"],
                        generation_result=_generation_result_from_payload(payload),
                        cache_hit=bool(payload["cache_hit"]),
                        fallback_used=bool(payload.get("fallback_used")),
                        fallback_reason=_optional_str(payload.get("fallback_reason")),
                        preprocessing_source=_optional_str(payload.get("preprocessing_source")),
                    )
                )
                continue

            payload = self._read_json(task["failure_s3_key"])
            failure_artifact_key = task.get("result_s3_key") or task["failure_s3_key"]
            manifest_entries.append(
                {
                    "url_task_id": task["url_task_id"],
                    "status": task["status"],
                    "artifact": self._s3_uri(failure_artifact_key),
                }
            )
            failures.append(UrlFailureResult(**payload))

        artifacts = self._write_job_summary_artifacts(
            job_id=job_id,
            requested_platform_mode=job["requested_platform_mode"],
            successes=successes,
            failures=failures,
            manifest_entries=manifest_entries,
        )
        job_status = aggregate_job_status(successes=successes, failures=failures)
        self._update_job(
            job_id,
            {
                "status": job_status,
                "succeeded_count": len(successes),
                "failed_count": len(failures),
                "artifacts": asdict(artifacts),
            },
        )

        if job.get("notification_target") and not job.get("notification_enqueued"):
            self._send_queue_message(self.resources.notification_queue_url, {"job_id": job_id})
            self._update_job(job_id, {"notification_enqueued": True})

    def _deliver_notification(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job.get("notification_sent_at") or not job.get("notification_target"):
            return

        tasks = self.get_url_tasks(job_id)
        successes: list[UrlExportResult] = []
        failures: list[UrlFailureResult] = []
        for task in tasks:
            if task["status"] in {"COMPLETED", "COMPLETED_CACHED"}:
                payload = self._read_json(task["result_s3_key"])
                successes.append(
                    UrlExportResult(
                        url_task_id=task["url_task_id"],
                        raw_url=task["raw_url"],
                        page_class=payload["page_class"],
                        requested_platform_mode=task["requested_platform_mode"],
                        generation_result=_generation_result_from_payload(payload),
                        cache_hit=bool(payload["cache_hit"]),
                        fallback_used=bool(payload.get("fallback_used")),
                        fallback_reason=_optional_str(payload.get("fallback_reason")),
                        preprocessing_source=_optional_str(payload.get("preprocessing_source")),
                    )
                )
                continue
            failures.append(UrlFailureResult(**self._read_json(task["failure_s3_key"])))

        target = NotificationTarget(**job["notification_target"])
        artifacts = JobArtifactUrls(**job["artifacts"])
        payload = build_notification_payload(
            job_id=job_id,
            requested_platform_mode=job["requested_platform_mode"],
            notification_target=target,
            artifacts=artifacts,
            successes=successes,
            failures=failures,
        )
        outbox_item = {
            "pk": f"JOB#{job_id}",
            "sk": "OUTBOX#notification",
            "entity_type": "notification_outbox",
            "job_id": job_id,
            "status": payload["status"],
            "payload": payload,
            "notification_target": job["notification_target"],
            "sent_at": self._now(),
        }
        self._put_item(outbox_item)
        self._update_job(job_id, {"notification_sent_at": outbox_item["sent_at"]})

    def _write_job_summary_artifacts(
        self,
        *,
        job_id: str,
        requested_platform_mode: str,
        successes: list[UrlExportResult],
        failures: list[UrlFailureResult],
        manifest_entries: list[dict[str, Any]],
    ) -> JobArtifactUrls:
        manifest_key = f"jobs/{job_id}/summary/per_url_manifest.json"
        combined_json_key = f"jobs/{job_id}/summary/combined.json"
        combined_csv_key = f"jobs/{job_id}/summary/combined.csv"
        failures_key = f"jobs/{job_id}/summary/failures.json"

        self._write_json(
            manifest_key,
            {
                "job_id": job_id,
                "requested_platform_mode": requested_platform_mode,
                "items": manifest_entries,
            },
        )
        self._write_json(
            combined_json_key,
            build_combined_json_payload(
                job_id=job_id,
                requested_platform_mode=requested_platform_mode,
                successes=successes,
                failures=failures,
            ),
        )
        self._write_text(combined_csv_key, _csv_from_rows(flatten_rows_for_csv(successes)))
        self._write_json(failures_key, build_failures_manifest(failures))
        return JobArtifactUrls(
            result_manifest_url=self._s3_uri(manifest_key),
            combined_json_url=self._s3_uri(combined_json_key),
            combined_csv_url=self._s3_uri(combined_csv_key),
            failures_json_url=self._s3_uri(failures_key),
        )

    def _load_cached_payload(self, cache_key: str) -> dict[str, Any] | None:
        key = self._cache_object_key(cache_key)
        try:
            return self._read_json(key)
        except self.s3_client.exceptions.NoSuchKey:
            return None
        except Exception:
            return None

    def _cache_object_key(self, cache_key: str) -> str:
        return (
            f"cache/policy={self.policy_version}/taxonomy={self.taxonomy_version}/"
            f"generator={self.generator_version}/{cache_key}.json"
        )

    def _partial_cache_s3_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/partial_cache/component.json"

    def _job_result_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/result/per_url.json"

    def _job_failure_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/result/failure.json"

    def _job_snapshot_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/collection/normalized_snapshot.json"

    def _job_classification_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/collection/page_classification.json"

    def _job_ocr_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/ocr/ocr_result.json"

    def _job_evidence_key(self, job_id: str, url_task_id: str) -> str:
        return f"jobs/{job_id}/urls/{url_task_id}/evidence/evidence_pack.json"

    def _s3_uri(self, key: str) -> str:
        return f"s3://{self.resources.bucket_name}/{key}"

    def _write_json(self, key: str, payload: Any) -> None:
        self.s3_client.put_object(
            Bucket=self.resources.bucket_name,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )

    def _write_text(self, key: str, text: str) -> None:
        self.s3_client.put_object(
            Bucket=self.resources.bucket_name,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/csv",
        )

    def _read_json(self, key: str) -> Any:
        response = self.s3_client.get_object(Bucket=self.resources.bucket_name, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))

    def _send_queue_message(self, queue_url: str, payload: dict[str, Any]) -> None:
        self.sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))

    def _receive_messages(self, queue_url: str) -> list[dict[str, Any]]:
        response = self.sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=0,
        )
        return response.get("Messages", [])

    def _put_item(self, item: dict[str, Any]) -> None:
        self.dynamodb_client.put_item(
            TableName=self.resources.table_name,
            Item={key: self._serializer.serialize(value) for key, value in item.items() if value is not None},
        )

    def _get_item(self, pk: str, sk: str) -> dict[str, Any] | None:
        response = self.dynamodb_client.get_item(
            TableName=self.resources.table_name,
            Key={
                "pk": self._serializer.serialize(pk),
                "sk": self._serializer.serialize(sk),
            },
        )
        item = response.get("Item")
        if not item:
            return None
        return {key: self._deserializer.deserialize(value) for key, value in item.items()}

    def _update_job(self, job_id: str, updates: dict[str, Any]) -> None:
        job = self.get_job(job_id)
        merged = {**job, **updates}
        self._put_item(merged)

    def _query_job_items(self, job_id: str) -> list[dict[str, Any]]:
        response = self.dynamodb_client.query(
            TableName=self.resources.table_name,
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": self._serializer.serialize(f"JOB#{job_id}")},
        )
        items = response.get("Items", [])
        return [{key: self._deserializer.deserialize(value) for key, value in item.items()} for item in items]

    def run_cache_validity_sweep(self, *, min_age_days: int = 7) -> dict[str, int]:
        """Scan cache/ prefix, HEAD-check each cached URL, delete objects for dead URLs.

        Returns a summary dict with keys 'scanned', 'deleted', 'errors'.
        Only objects older than min_age_days (by S3 LastModified) are checked.
        """
        import urllib.request
        from datetime import timedelta

        cutoff = datetime.now(tz=UTC) - timedelta(days=min_age_days)
        scanned = deleted = errors = 0
        cache_prefix = f"cache/policy={self.policy_version}/taxonomy={self.taxonomy_version}/generator={self.generator_version}/"

        paginator_kwargs: dict[str, Any] = {
            "Bucket": self.resources.bucket_name,
            "Prefix": cache_prefix,
        }
        continuation_token: str | None = None

        while True:
            if continuation_token:
                paginator_kwargs["ContinuationToken"] = continuation_token
            response = self.s3_client.list_objects_v2(**paginator_kwargs)
            for obj in response.get("Contents", []):
                key = obj["Key"]
                last_modified = obj["LastModified"]
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=UTC)
                if last_modified > cutoff:
                    continue  # Too recent — skip

                scanned += 1
                try:
                    payload = self._read_json(key)
                    canonical_url = payload.get("raw_url") or payload.get("canonical_url", "")
                    if not canonical_url:
                        continue
                    req = urllib.request.Request(canonical_url, method="HEAD")
                    req.add_header("User-Agent", "KeywordGenerator-CacheValidityWorker/1.0")
                    try:
                        urllib.request.urlopen(req, timeout=10)
                    except urllib.error.HTTPError as exc:
                        if exc.code in (404, 410):
                            self.s3_client.delete_object(Bucket=self.resources.bucket_name, Key=key)
                            deleted += 1
                    except Exception:
                        pass  # Network errors: keep the cache object
                except Exception:
                    errors += 1

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        return {"scanned": scanned, "deleted": deleted, "errors": errors}

    @staticmethod
    def _now() -> str:
        return datetime.now(tz=UTC).isoformat()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def canonicalize_url(raw_url: str) -> str:
    split = urlsplit(raw_url)
    scheme = split.scheme.lower()
    host = split.hostname.lower() if split.hostname else ""
    port = split.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = split.path or "/"
    while "//" in path:
        path = path.replace("//", "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    filtered_query = []
    for key, value in parse_qsl(split.query, keep_blank_values=False):
        if key in TRACKING_QUERY_KEYS or key.startswith("utm_"):
            continue
        filtered_query.append((key, value))
    filtered_query.sort(key=lambda item: (item[0], item[1]))
    return urlunsplit((scheme, netloc, path, urlencode(filtered_query), ""))


def build_cache_key(
    *,
    canonical_url: str,
    platform_component: str,
    policy_version: str,
    taxonomy_version: str,
    generator_version: str,
) -> str:
    """Build a cache key for a single platform component (naver_sa or google_sa).

    'both' is not a valid platform_component — callers must build two separate keys.
    """
    url_hash = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return (
        f"kwg:{url_hash}:platform:{platform_component}:policy:{policy_version}:"
        f"taxonomy:{taxonomy_version}:generator:{generator_version}"
    )


def _extract_platform_component(payload: dict[str, Any], platform: str) -> dict[str, Any]:
    """Extract single-platform rows from a both-mode payload for per-component caching."""
    component = {k: v for k, v in payload.items() if k != "rows"}
    component["requested_platform_mode"] = platform
    if platform == "naver_sa":
        component["rows"] = [r for r in payload.get("rows", []) if r.get("naver_match")]
    else:
        component["rows"] = [r for r in payload.get("rows", []) if r.get("google_match")]
    return component


def _merge_platform_components(naver_payload: dict[str, Any], google_payload: dict[str, Any]) -> dict[str, Any]:
    """Merge naver_sa and google_sa cached component payloads into a both-mode payload."""
    merged = {k: v for k, v in naver_payload.items() if k not in ("rows", "validation_report", "requested_platform_mode")}
    merged["requested_platform_mode"] = "both"
    merged["rows"] = naver_payload.get("rows", []) + google_payload.get("rows", [])
    nr = naver_payload.get("validation_report") or {}
    gr = google_payload.get("validation_report") or {}
    both_status = (
        "COMPLETED"
        if nr.get("status") == "COMPLETED" and gr.get("status") == "COMPLETED"
        else "FAILED_GENERATION"
    )
    merged["validation_report"] = {
        "status": both_status,
        "positive_keyword_counts": {**nr.get("positive_keyword_counts", {}), **gr.get("positive_keyword_counts", {})},
        "category_counts": {**nr.get("category_counts", {}), **gr.get("category_counts", {})},
        "weak_tier_ratio_by_platform": {**nr.get("weak_tier_ratio_by_platform", {}), **gr.get("weak_tier_ratio_by_platform", {})},
        "quality_warning": nr.get("quality_warning", False) or gr.get("quality_warning", False),
        "failure_code": None,
        "failure_detail": None,
    }
    return merged


def _csv_from_rows(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "url",
            "product_name",
            "category",
            "keyword",
            "naver_match",
            "google_match",
            "reason",
            "quality_warning",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _generation_result_from_payload(payload: dict[str, Any]) -> Any:
    from src.keyword_generation.models import GenerationResult, KeywordRow, ValidationReport

    report = payload["validation_report"]
    return GenerationResult(
        status=payload["status"],
        requested_platform_mode=payload["requested_platform_mode"],
        rows=[KeywordRow(**row) for row in payload["rows"]],
        supplementation_attempts=0,
        debug_payload=payload.get("debug") or {},
        validation_report=ValidationReport(
            status=report["status"],
            requested_platform_mode=payload["requested_platform_mode"],
            positive_keyword_counts=report["positive_keyword_counts"],
            category_counts=report["category_counts"],
            weak_tier_ratio_by_platform=report["weak_tier_ratio_by_platform"],
            failure_code=report["failure_code"],
            failure_detail=report["failure_detail"],
            quality_warning=bool(report["quality_warning"]),
        ),
    )
