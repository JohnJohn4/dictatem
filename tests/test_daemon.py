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


class TestStarterAdapterSets:
    """Execute the real starter bodies with _run_daemon stubbed (#54).

    The dispatch tests above stub the starters away, so without these the
    starters' lazy imports and _PlatformAdapters construction would never run
    in CI — a wrong import path or keyword mismatch would only surface at a
    real launch.
    """

    @pytest.mark.skipif(
        sys.platform != "darwin", reason="lazy-imports the PyObjC native adapters"
    )
    def test_macos_starter_builds_cpu_adapter_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dictatem.hardware.mac_probe import MacHardwareProbe

        captured: list[daemon._PlatformAdapters] = []
        monkeypatch.setattr(daemon, "_run_daemon", captured.append)
        daemon._start_macos_daemon()
        (adapters,) = captured
        assert isinstance(adapters.probe, MacHardwareProbe)
        assert adapters.clipboard is not None
        assert adapters.keystroke is not None
        assert adapters.foreground is not None
        assert adapters.install_keyboard_hook is not None
        # The LaunchAgent registrar arrives with the .app (#61) — absent, not
        # faked: the reconcile is skipped and the tray hides the toggle.
        assert adapters.autostart_registrar is None

    @pytest.mark.skipif(
        sys.platform != "win32", reason="lazy-imports the win32 native adapters"
    )
    def test_windows_starter_builds_win32_adapter_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dictatem.hardware.nvidia_probe import NvidiaHardwareProbe

        captured: list[daemon._PlatformAdapters] = []
        monkeypatch.setattr(daemon, "_run_daemon", captured.append)
        daemon._start_windows_daemon()
        (adapters,) = captured
        assert isinstance(adapters.probe, NvidiaHardwareProbe)
        assert adapters.clipboard is not None
        assert adapters.keystroke is not None
        assert adapters.foreground is not None
        assert adapters.autostart_registrar is not None
        assert adapters.install_keyboard_hook is not None
