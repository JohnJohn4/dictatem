"""Tests for daemon platform dispatch (#54).

``main()`` must route ``win32`` → ``_start_windows_daemon``, ``darwin`` →
``_start_macos_daemon``, and raise PlatformNotSupportedError elsewhere. The
starters are stubbed and ``sys.platform`` is monkeypatched, so every branch
runs on every CI OS without starting a Qt event loop.
"""

from __future__ import annotations

import sys

import pytest

from dictatem import daemon
from dictatem.exceptions import PlatformNotSupportedError


class TestMainPlatformDispatch:
    def test_win32_dispatches_to_windows_starter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(
            daemon, "_start_windows_daemon", lambda: calls.append("windows")
        )
        daemon.main(argv=[])
        assert calls == ["windows"]

    def test_darwin_dispatches_to_macos_starter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            daemon, "_start_macos_daemon", lambda: calls.append("macos")
        )
        daemon.main(argv=[])
        assert calls == ["macos"]

    def test_unknown_platform_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(PlatformNotSupportedError, match="linux"):
            daemon.main(argv=[])

    def test_gate_fires_before_uninstall_on_unknown_platform(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(PlatformNotSupportedError):
            daemon.main(argv=["--uninstall"])


class TestMainUninstallFlag:
    def test_uninstall_runs_cleanup_not_daemon(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(daemon, "_run_uninstall", lambda: calls.append("uninstall"))
        monkeypatch.setattr(
            daemon, "_start_windows_daemon", lambda: calls.append("daemon")
        )
        daemon.main(argv=["--uninstall"])
        assert calls == ["uninstall"]

    def test_unknown_flag_errors(self) -> None:
        # argparse exits (SystemExit) on an unrecognized flag.
        with pytest.raises(SystemExit):
            daemon.main(argv=["--bogus"])
