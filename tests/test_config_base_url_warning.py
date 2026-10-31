"""S-3 / #202: warn when [transform].base_url would send text off this machine."""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from dictatem.config import is_loopback_url, load_config

if TYPE_CHECKING:
    from pathlib import Path


class TestIsLoopbackUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434",
            "http://LOCALHOST:11434/",
            "http://127.0.0.1:11434",
            "http://127.1.2.3",
            "http://[::1]:11434",
            "https://localhost",
            "  http://localhost:11434  ",
        ],
    )
    def test_loopback(self, url: str) -> None:
        assert is_loopback_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://192.168.1.20:11434",  # LAN box — still leaves this machine
            "http://ollama.example.com",
            "http://localhost.evil.com",  # prefix trick
            "http://127.0.0.1.nip.io",
            "http://0.0.0.0:11434",
            "localhost:11434",  # no scheme: urlsplit finds no host
            "",
            "not a url",
            "http://[::1",  # malformed IPv6 -> ValueError
            None,
            11434,
        ],
    )
    def test_not_loopback(self, url: object) -> None:
        assert is_loopback_url(url) is False


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(dedent(body), encoding="utf-8")
    return path


def _base_url_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "base_url" in r.getMessage()
    ]


class TestLoadConfigWarning:
    def test_remote_base_url_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write(tmp_path, """
            [transform]
            base_url = "http://10.0.0.5:11434"
        """)
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        # Warn only — the value is kept, never rewritten.
        assert cfg.transform.base_url == "http://10.0.0.5:11434"
        assert len(_base_url_warnings(caplog)) == 1

    def test_default_base_url_is_silent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write(tmp_path, """
            [transform]
            model_name = "gemma4:e2b"
        """)
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            load_config(path)
        assert _base_url_warnings(caplog) == []

    def test_disabled_transform_is_silent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write(tmp_path, """
            [transform]
            enabled = false
            base_url = "http://10.0.0.5:11434"
        """)
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            load_config(path)
        assert _base_url_warnings(caplog) == []
