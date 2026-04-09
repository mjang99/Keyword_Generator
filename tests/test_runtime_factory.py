from __future__ import annotations

import sys

from src.handlers.runtime_factory import ensure_utf8_stdio


class _FakeStream:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def reconfigure(self, *, encoding: str, errors: str) -> None:
        self.calls.append((encoding, errors))


def test_ensure_utf8_stdio_reconfigures_stdout_and_stderr(monkeypatch) -> None:
    fake_stdout = _FakeStream()
    fake_stderr = _FakeStream()
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    ensure_utf8_stdio()

    assert fake_stdout.calls == [("utf-8", "backslashreplace")]
    assert fake_stderr.calls == [("utf-8", "backslashreplace")]
