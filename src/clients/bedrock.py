from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import boto3
from botocore.config import Config

DEFAULT_REGION = "ap-northeast-2"
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.95
DEFAULT_MODEL_CANDIDATES = (
    "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "apac.anthropic.claude-3-5-sonnet-20240620-v1:0",
)


@dataclass(slots=True)
class BedrockRuntimeSettings:
    region_name: str = DEFAULT_REGION
    model_candidates: tuple[str, ...] = DEFAULT_MODEL_CANDIDATES
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    retry_max_attempts: int = 3
    read_timeout: int = 60
    connect_timeout: int = 10
    extra_request_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "BedrockRuntimeSettings":
        explicit_profile = os.environ.get("BEDROCK_INFERENCE_PROFILE_ID")
        explicit_model = os.environ.get("BEDROCK_MODEL_ID")
        if explicit_profile:
            model_candidates = (explicit_profile,)
        elif explicit_model:
            model_candidates = (explicit_model,)
        else:
            model_candidates = DEFAULT_MODEL_CANDIDATES

        return cls(
            region_name=os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION),
            model_candidates=model_candidates,
            max_tokens=int(os.environ.get("BEDROCK_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
        )


def build_bedrock_runtime_client(
    settings: BedrockRuntimeSettings | None = None,
) -> Any:
    resolved = settings or BedrockRuntimeSettings.from_env()
    return boto3.client(
        "bedrock-runtime",
        region_name=resolved.region_name,
        config=Config(
            retries={"max_attempts": resolved.retry_max_attempts, "mode": "standard"},
            read_timeout=resolved.read_timeout,
            connect_timeout=resolved.connect_timeout,
        ),
    )


def is_cross_region_model_id(model_id: str) -> bool:
    return model_id.startswith(("us.", "eu.", "apac.", "global."))


def build_converse_payload(
    user_prompt: str,
    *,
    settings: BedrockRuntimeSettings | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    resolved = settings or BedrockRuntimeSettings.from_env()
    payload: dict[str, Any] = {
        "messages": [
            {
                "role": "user",
                "content": [{"text": user_prompt}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": resolved.max_tokens,
            "temperature": resolved.temperature,
            "topP": resolved.top_p,
        },
    }
    if system_prompt:
        payload["system"] = [{"text": system_prompt}]
    if resolved.extra_request_headers:
        payload["additionalModelRequestFields"] = resolved.extra_request_headers
    return payload


def extract_text(response: dict[str, Any]) -> str:
    output = response.get("output", {})
    message = output.get("message", {})
    parts = message.get("content", [])
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            text_parts.append(str(part["text"]))
    return "".join(text_parts).strip()


def converse_text(
    user_prompt: str,
    *,
    settings: BedrockRuntimeSettings | None = None,
    system_prompt: str | None = None,
    client: Any | None = None,
) -> tuple[str, str]:
    resolved = settings or BedrockRuntimeSettings.from_env()
    runtime_client = client or build_bedrock_runtime_client(resolved)
    last_error: Exception | None = None

    for model_id in resolved.model_candidates:
        try:
            response = runtime_client.converse(
                modelId=model_id,
                **build_converse_payload(
                    user_prompt,
                    settings=resolved,
                    system_prompt=system_prompt,
                ),
            )
            return model_id, extract_text(response)
        except Exception as exc:  # pragma: no cover - boto errors vary by env
            last_error = exc
            continue

    if last_error is None:
        raise RuntimeError("No Bedrock model candidates configured")
    raise last_error


def settings_summary(settings: BedrockRuntimeSettings | None = None) -> dict[str, Any]:
    resolved = settings or BedrockRuntimeSettings.from_env()
    return {
        "region_name": resolved.region_name,
        "model_candidates": list(resolved.model_candidates),
        "max_tokens": resolved.max_tokens,
        "cross_region": [is_cross_region_model_id(model_id) for model_id in resolved.model_candidates],
    }


def settings_summary_json(settings: BedrockRuntimeSettings | None = None) -> str:
    return json.dumps(settings_summary(settings), ensure_ascii=False, indent=2)
