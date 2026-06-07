"""Tests for daemon platform dispatch (#54).

``main()`` must route ``win32`` → ``_start_windows_daemon``, ``darwin`` →
``_start_macos_daemon``, and raise PlatformNotSupportedError elsewhere. The
starters are stubbed and ``sys.platform`` is monkeypatched, so every branch
runs on every CI OS without starting a Qt event loop.
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

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


class TestMainInstallMacosAppFlag:
    def test_install_macos_app_runs_glue_not_daemon(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            daemon, "_run_install_macos_app", lambda: calls.append("install")
        )
        monkeypatch.setattr(
            daemon, "_start_macos_daemon", lambda: calls.append("daemon")
        )
        daemon.main(argv=["--install-macos-app"])
        assert calls == ["install"]

    def test_errors_off_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # parser.error → SystemExit(2): the flag generates a macOS-only
        # artifact, so on Windows it must refuse rather than no-op.
        monkeypatch.setattr(sys, "platform", "win32")
        with pytest.raises(SystemExit):
            daemon.main(argv=["--install-macos-app"])

    def test_glue_generates_bundle_under_home(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The glue itself is OS-independent file I/O (the darwin gate lives in
        # main), so the whole flow runs against a monkeypatched home on any OS.
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        daemon._run_install_macos_app()

        bundle = tmp_path / "Applications" / "Dictatem.app"
        assert (bundle / "Contents" / "Info.plist").is_file()
        assert (bundle / "Contents" / "MacOS" / "Dictatem").is_file()
        assert (bundle / "Contents" / "Resources" / "app.icns").is_file()
        out = capsys.readouterr().out
        assert "Generated" in out
        # No LaunchAgent existed, so none is created (ADR-0012: the daemon
        # reconciles autostart; the installer never preempts the config).
        assert not (
            tmp_path / "Library" / "LaunchAgents" / "com.dictatem.daemon.plist"
        ).exists()
        assert "LaunchAgent" not in out

    def test_glue_refreshes_an_existing_launch_agent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The stale-launch-command heal rides the upgrade path (PR #86 note):
        # an existing plist is rewritten with the current launch command.
        from dictatem.autostart.launch_agent import LaunchAgentRegistrar

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        agents_dir = tmp_path / "Library" / "LaunchAgents"
        LaunchAgentRegistrar(
            agents_dir=agents_dir, program_arguments=["/stale/command"]
        ).enable()

        daemon._run_install_macos_app()

        agent = plistlib.loads(
            (agents_dir / "com.dictatem.daemon.plist").read_bytes()
        )
        bundle = tmp_path / "Applications" / "Dictatem.app"
        assert agent["ProgramArguments"] == ["/usr/bin/open", "-g", bundle.as_posix()]
        assert "Refreshed the start-at-login LaunchAgent" in capsys.readouterr().out


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
        # The CGPreflight permission check (#57) — passed as a reference,
        # never called here (this runs on a headless TCC-less runner).
        assert adapters.check_permissions is not None
        # No ~/Applications/Dictatem.app on a CI runner, so the registrar is
        # guarded off (#61) — absent, not faked: the reconcile is skipped and
        # the tray hides the toggle rather than registering a LaunchAgent
        # that points at a missing bundle.
        assert adapters.autostart_registrar is None

    @pytest.mark.skipif(
        sys.platform != "darwin", reason="lazy-imports the PyObjC native adapters"
    )
    def test_macos_starter_wires_registrar_when_app_exists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from dictatem.autostart.launch_agent import LaunchAgentRegistrar

        bundle = tmp_path / "Dictatem.app"
        bundle.mkdir()
        monkeypatch.setattr(
            "dictatem.macapp.bundle.default_app_bundle_path", lambda: bundle
        )
        captured: list[daemon._PlatformAdapters] = []
        monkeypatch.setattr(daemon, "_run_daemon", captured.append)
        daemon._start_macos_daemon()
        (adapters,) = captured
        assert isinstance(adapters.autostart_registrar, LaunchAgentRegistrar)

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
        # Windows has no guided permission UX — the mic permission surfaces
        # in-flow when capture fails.
        assert adapters.check_permissions is None
