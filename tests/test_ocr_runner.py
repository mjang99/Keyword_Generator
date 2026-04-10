from __future__ import annotations

import subprocess
from types import SimpleNamespace

from src.ocr.runner import _decode_subprocess_stream, _plan_candidate_passes, _run_paddleocr_subprocess


def test_plan_candidate_passes_uses_tiling_for_long_detail_banners() -> None:
    passes = _plan_candidate_passes(
        candidate={"src": "https://cdn.example.com/detail-banner.jpg", "alt": "detail banner"},
        requested_pipeline="plain_text",
        candidate_type="long_detail_banner",
        structured_enabled=False,
        multipass_enabled=True,
        tiling_enabled=True,
        language_routing_enabled=False,
    )

    assert passes[0]["tile_mode"] == "vertical"
    assert any(item["preprocessing_variant"] == "enhance_contrast" for item in passes)


def test_plan_candidate_passes_adds_upscale_for_front_label_closeup() -> None:
    passes = _plan_candidate_passes(
        candidate={"src": "https://cdn.example.com/front-label.jpg", "alt": "front label"},
        requested_pipeline="plain_text",
        candidate_type="front_label_closeup",
        structured_enabled=False,
        multipass_enabled=True,
        tiling_enabled=True,
        language_routing_enabled=False,
    )

    assert any(item["preprocessing_variant"] == "upscale_x2" for item in passes)


def test_plan_candidate_passes_keeps_structured_then_plain_fallback_for_tables() -> None:
    passes = _plan_candidate_passes(
        candidate={"src": "https://cdn.example.com/spec-table.png", "alt": "comparison table"},
        requested_pipeline="structured_table",
        candidate_type="table_like_image",
        structured_enabled=True,
        multipass_enabled=True,
        tiling_enabled=True,
        language_routing_enabled=False,
    )

    assert passes[0]["pipeline_type"] == "structured_table"
    assert any(item["pipeline_type"] == "plain_text" for item in passes[1:])


def test_decode_subprocess_stream_handles_utf8_bytes() -> None:
    assert _decode_subprocess_stream("테스트".encode("utf-8")) == "테스트"


def test_run_paddleocr_subprocess_decodes_utf8_stdout_without_windows_codec_failure(monkeypatch) -> None:
    captured = {}

    def fake_run(*args, **kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout='{"engine_ok": true, "blocks": [], "runtime_ms": 12, "note": "테스트"}'.encode("utf-8"),
            stderr=b"",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    payload = _run_paddleocr_subprocess(
        ocr_python="python",
        site_packages_path=None,
        image_source="https://example.com/image.jpg",
        timeout_seconds=1,
        pipeline_type="plain_text",
        rectify_enabled=False,
        preprocessing_variant="original",
        ocr_lang="korean",
        tile_mode="none",
    )

    assert captured["kwargs"]["text"] is False
    assert captured["kwargs"]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert payload["engine_ok"] is True
    assert payload["note"] == "테스트"


def test_run_paddleocr_subprocess_returns_error_payload_on_timeout(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["python"], timeout=7, output="부분출력".encode("utf-8"), stderr=b"stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)

    payload = _run_paddleocr_subprocess(
        ocr_python="python",
        site_packages_path=None,
        image_source="https://example.com/image.jpg",
        timeout_seconds=7,
        pipeline_type="plain_text",
        rectify_enabled=False,
        preprocessing_variant="original",
        ocr_lang="korean",
        tile_mode="none",
    )

    assert payload["engine_ok"] is False
    assert payload["runtime_ms"] == 7000
    assert payload["stdout"] == "부분출력"
    assert payload["stderr"] == "stderr"
    assert "timed out" in payload["error"]
