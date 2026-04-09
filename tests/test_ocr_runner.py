from __future__ import annotations

import sys

from src.ocr.runner import SubprocessOcrRunner, create_subprocess_ocr_runner_from_env


def test_create_subprocess_ocr_runner_reads_env_controls(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_ENABLED", "1")
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_PYTHON", sys.executable)
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_MAX_IMAGES", "8")
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_STRUCTURED_ENABLED", "1")
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_RECTIFY_ENABLED", "1")

    runner = create_subprocess_ocr_runner_from_env()

    assert isinstance(runner, SubprocessOcrRunner)
    assert runner.max_images == 8
    assert runner.timeout_seconds == 180
    assert runner.structured_enabled is True
    assert runner.rectify_enabled is True


def test_create_subprocess_ocr_runner_falls_back_on_invalid_env(monkeypatch) -> None:
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_ENABLED", "1")
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_PYTHON", sys.executable)
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_MAX_IMAGES", "oops")
    monkeypatch.setenv("KEYWORD_GENERATOR_OCR_TIMEOUT_SECONDS", "oops")

    runner = create_subprocess_ocr_runner_from_env()

    assert isinstance(runner, SubprocessOcrRunner)
    assert runner.max_images == 24
    assert runner.timeout_seconds == 120
