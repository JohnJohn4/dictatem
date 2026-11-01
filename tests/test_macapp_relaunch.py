"""Unit tests for the macOS launchd relaunch behind the tray Restart item (#95).

The argv and the spawn decision are pure, with ``run``/``popen``/``uid``
injected, so they run on any OS; only the real ``launchctl`` spawn is manual-QA.
"""

from __future__ import annotations

import subprocess
from typing import Any

from dictatem.macapp.plist import BUNDLE_ID
from dictatem.macapp.relaunch import (
    LAUNCHCTL,
    MANUAL_RELAUNCH_HINT,
    launchd_service_target,
    relaunch_helper_argv,
    service_loaded_argv,
    spawn_launchd_relaunch,
)


class _Recorder:
    def __init__(self, *, returncode: int = 0, raises: bool = False) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._returncode = returncode
        self._raises = raises

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((argv, kwargs))
        if self._raises:
            raise OSError("boom")
        return subprocess.CompletedProcess(argv, self._returncode)


class TestArgv:
    def test_service_target_uses_the_gui_domain_and_bundle_label(self) -> None:
        assert launchd_service_target(501) == f"gui/501/{BUNDLE_ID}"

    def test_loaded_probe_is_launchctl_print(self) -> None:
        assert service_loaded_argv(501) == [LAUNCHCTL, "print", f"gui/501/{BUNDLE_ID}"]

    def test_helper_waits_then_kickstarts_with_kill(self) -> None:
        argv = relaunch_helper_argv(501)
        assert argv[:2] == ["/bin/sh", "-c"]
        script = argv[2]
        # Wait first (this daemon must quit and free its lock), then -k so a
        # still-running instance is killed and launchd starts a fresh one.
        assert script.startswith("sleep ")
        assert f"{LAUNCHCTL} kickstart -k gui/501/{BUNDLE_ID}" in script

    def test_never_relaunches_via_open_or_the_bare_launcher(self) -> None:
        # A .app/open launch loses the menu-bar icon and a terminal launch
        # loses the grants (ADR-0012/0014) — only launchd may start it.
        script = relaunch_helper_argv(501)[2]
        assert "open " not in script
        assert "dictatem" not in script.replace(BUNDLE_ID, "")


class TestSpawn:
    def test_spawns_detached_helper_when_service_is_loaded(self) -> None:
        run, popen = _Recorder(returncode=0), _Recorder()
        assert spawn_launchd_relaunch(uid=501, run=run, popen=popen) is True
        assert run.calls[0][0] == service_loaded_argv(501)
        ((argv, kwargs),) = popen.calls
        assert argv == relaunch_helper_argv(501)
        # Own session, so launchd's cleanup of the exiting job spares it.
        assert kwargs["start_new_session"] is True
        assert kwargs["close_fds"] is True

    def test_not_loaded_spawns_nothing(self) -> None:
        run, popen = _Recorder(returncode=113), _Recorder()
        assert spawn_launchd_relaunch(uid=501, run=run, popen=popen) is False
        assert popen.calls == []

    def test_launchctl_missing_is_a_soft_failure(self) -> None:
        run, popen = _Recorder(raises=True), _Recorder()
        assert spawn_launchd_relaunch(uid=501, run=run, popen=popen) is False
        assert popen.calls == []

    def test_spawn_failure_is_a_soft_failure(self) -> None:
        run, popen = _Recorder(returncode=0), _Recorder(raises=True)
        assert spawn_launchd_relaunch(uid=501, run=run, popen=popen) is False


class TestManualHint:
    def test_hint_gives_a_way_forward(self) -> None:
        assert "Start at Login" in MANUAL_RELAUNCH_HINT
        assert "install command" in MANUAL_RELAUNCH_HINT
