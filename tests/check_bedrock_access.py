from __future__ import annotations

import json
import os
import sys
from typing import Any

DEFAULT_REGION = "ap-northeast-2"
DEFAULT_MODEL_CANDIDATES = [
    "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "apac.anthropic.claude-3-5-sonnet-20240620-v1:0",
]


def build_client() -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ModuleNotFoundError as exc:
        print(
            "Missing Python dependency: boto3/botocore. Install the project test "
            "dependencies or run this script from the project environment.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    region = os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION)
    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(
            retries={"max_attempts": 3, "mode": "standard"},
            read_timeout=60,
            connect_timeout=10,
        ),
    )


def resolve_model_candidates() -> list[str]:
    explicit_profile = os.environ.get("BEDROCK_INFERENCE_PROFILE_ID")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if explicit_profile:
        return [explicit_profile]
    if model_id:
        return [model_id]
    return DEFAULT_MODEL_CANDIDATES.copy()


def is_cross_region(model_id: str) -> bool:
    return model_id.startswith(("us.", "eu.", "apac.", "global."))


def extract_text(response: dict[str, Any]) -> str:
    output = response.get("output", {})
    message = output.get("message", {})
    parts = message.get("content", [])
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            texts.append(str(part["text"]))
    return "".join(texts).strip()


def ping() -> int:
    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ModuleNotFoundError as exc:
        print(
            "Missing Python dependency: boto3/botocore. Install the project test "
            "dependencies or run this script from the project environment.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    region = os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION)
    model_candidates = resolve_model_candidates()
    client = build_client()

    print(f"region={region}")
    print(f"model_candidates={json.dumps(model_candidates, ensure_ascii=False)}")
    print(
        "model_source="
        + ("env" if os.environ.get("BEDROCK_INFERENCE_PROFILE_ID") or os.environ.get("BEDROCK_MODEL_ID") else "default")
    )
    print("max_tokens=16")

    last_failure: tuple[str, str] | None = None

    for model_id in model_candidates:
        print(f"trying_model_id={model_id}")
        print(f"cross_region={'yes' if is_cross_region(model_id) else 'no'}")
        try:
            response = client.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": "Reply with exactly: OK"}],
                    }
                ],
                inferenceConfig={
                    "maxTokens": 16,
                    "temperature": 0.0,
                    "topP": 1.0,
                },
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            message = exc.response.get("Error", {}).get("Message", str(exc))
            last_failure = (code, message)
            print(f"Bedrock access failed for {model_id}: {code}: {message}", file=sys.stderr)
            if code in {
                "ThrottlingException",
                "TooManyRequestsException",
                "ProvisionedThroughputExceededException",
            }:
                print(
                    "Throttled. Use a Geo cross-region inference profile or endpoint, "
                    "and lower concurrency if you are hitting on-demand limits.",
                    file=sys.stderr,
                )
            if code == "ValidationException":
                continue
            return 1
        except BotoCoreError as exc:
            print(f"Bedrock access failed for {model_id}: {exc}", file=sys.stderr)
            return 1

        text = extract_text(response)
        if text:
            print(f"response={text}")
        print(f"resolved_model_id={model_id}")
        print("Bedrock access OK")
        return 0

    if last_failure is not None:
        code, message = last_failure
        print(f"Bedrock access failed: {code}: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(ping())
