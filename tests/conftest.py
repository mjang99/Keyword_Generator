from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Iterator

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-2")


def fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def load_evidence_fixture(name: str) -> dict[str, Any]:
    fixture_file = fixture_path() / name
    with fixture_file.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="function")
def evidence_fixture_loader() -> Callable[[str], dict[str, Any]]:
    return load_evidence_fixture


@pytest.fixture(scope="function")
def fixtures_dir() -> Path:
    return fixture_path()


@pytest.fixture(scope="function", autouse=True)
def aws_default_region_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    yield


@pytest.fixture(scope="function")
def aws_moto() -> Iterator[None]:
    with mock_aws():
        yield


@pytest.fixture(scope="function")
def s3_client(aws_moto: None) -> Any:
    return boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"))


@pytest.fixture(scope="function")
def dynamodb_client(aws_moto: None) -> Any:
    return boto3.client("dynamodb", region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"))


@pytest.fixture(scope="function")
def sqs_client(aws_moto: None) -> Any:
    return boto3.client("sqs", region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"))


@pytest.fixture(scope="function")
def bedrock_client() -> Any:
    return boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"),
    )
