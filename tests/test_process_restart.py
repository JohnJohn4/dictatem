"""Tests for the Windows tray-Restart relauncher's pure core (#212)."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from dictatem.process.restart import (
    CREATE_BREAKAWAY_FROM_JOB,
    CREATE_NEW_PROCESS_GROUP,
    DETACHED_PROCESS,
    RESTART_ENV_VAR,
    RESTART_LOCK_WAIT_MS,
    creationflag_attempts,
    relaunch_argv,
    relaunch_env,
    spawn_restart,
    take_restart_lock_wait_ms,
    windowless_interpreter,
)

if TYPE_CHECKING:
    import pytest

TOOL_SCRIPTS = r"C:\Users\u\AppData\Roaming\uv\tools\dictatem\Scripts"


def _exists_only(*paths: str) -> Any:
    wanted = set(paths)
    return lambda p: p in wanted


class TestWindowlessInterpreter:
    def test_python_exe_maps_to_existing_pythonw_sibling(self) -> None:
        exe = TOOL_SCRIPTS + r"\python.exe"
        pythonw = TOOL_SCRIPTS + r"\pythonw.exe"
        assert windowless_interpreter(exe, exists=_exists_only(pythonw)) == pythonw

    def test_versioned_and_uppercase_names_keep_their_suffix(self) -> None:
        exe = r"C:\Py\Python3.12.EXE"
        pythonw = r"C:\Py\pythonw3.12.EXE"
        assert windowless_interpreter(exe, exists=_exists_only(pythonw)) == pythonw

    def test_already_windowless_is_unchanged(self) -> None:
        exe = TOOL_SCRIPTS + r"\pythonw.exe"
        assert windowless_interpreter(exe, exists=lambda _p: True) == exe

    def test_missing_sibling_falls_back_to_the_console_interpreter(self) -> None:
        # Spawned DETACHED_PROCESS, so even a console python shows no window.
        exe = r"C:\Py\python.exe"
        assert windowless_interpreter(exe, exists=lambda _p: False) == exe

    def test_non_python_executable_is_unchanged(self) -> None:
        exe = r"C:\Tools\dictatem.exe"
        assert windowless_interpreter(exe, exists=lambda _p: True) == exe


class TestRelaunchArgv:
    def test_installed_daemon_relaunches_the_tool_venv_pythonw(self) -> None:
        # The installed daemon's sys.executable is the tool venv's launcher
        # stub, so the replacement is matched by the uninstall/upgrade stopper.
        exe = TOOL_SCRIPTS + r"\pythonw.exe"
        assert relaunch_argv(exe, exists=lambda _p: True) == [exe, "-m", "dictatem"]

    def test_dev_run_relaunches_the_checkout_venv_windowless(self) -> None:
        exe = r"C:\Code\dictatem\.venv\Scripts\python.exe"
        pythonw = r"C:\Code\dictatem\.venv\Scripts\pythonw.exe"
        assert relaunch_argv(exe, exists=_exists_only(pythonw)) == [
            pythonw,
            "-m",
            "dictatem",
        ]


class TestRelaunchEnv:
    def test_adds_the_restart_marker_without_mutating_the_source(self) -> None:
        source = {"PATH": r"C:\bin"}
        env = relaunch_env(source)
        assert env == {"PATH": r"C:\bin", RESTART_ENV_VAR: "1"}
        assert RESTART_ENV_VAR not in source


class TestTakeRestartLockWait:
    def test_normal_launch_fails_fast(self) -> None:
        assert take_restart_lock_wait_ms({}) == 0

    def test_restart_launch_waits_and_clears_the_marker(self) -> None:
        environ = {RESTART_ENV_VAR: "1", "PATH": "x"}
        assert take_restart_lock_wait_ms(environ) == RESTART_LOCK_WAIT_MS
        # Cleared, so nothing this daemon spawns later inherits it.
        assert environ == {"PATH": "x"}

    def test_empty_marker_is_a_normal_launch(self) -> None:
        environ = {RESTART_ENV_VAR: ""}
        assert take_restart_lock_wait_ms(environ) == 0
        assert environ == {}


class TestCreationflagAttempts:
    def test_detached_first_with_breakaway_then_without(self) -> None:
        base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        assert creationflag_attempts() == (base | CREATE_BREAKAWAY_FROM_JOB, base)


class _RecordingPopen:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._fail_times = fail_times

    def __call__(self, argv: list[str], **kwargs: Any) -> object:
        self.calls.append((argv, kwargs))
        if len(self.calls) <= self._fail_times:
            raise PermissionError("access denied")
        return object()


class TestSpawnRestart:
    EXE = TOOL_SCRIPTS + r"\pythonw.exe"

    def test_spawns_detached_with_marker_and_no_inherited_stdio(self) -> None:
        popen = _RecordingPopen()
        assert spawn_restart(
            executable=self.EXE,
            environ={"PATH": "x"},
            exists=lambda _p: True,
            popen=popen,
        )
        ((argv, kwargs),) = popen.calls
        assert argv == [self.EXE, "-m", "dictatem"]
        assert kwargs["env"] == {"PATH": "x", RESTART_ENV_VAR: "1"}
        assert kwargs["creationflags"] == creationflag_attempts()[0]
        assert kwargs["creationflags"] & DETACHED_PROCESS
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["close_fds"] is True

    def test_retries_without_breakaway_when_the_job_forbids_it(self) -> None:
        popen = _RecordingPopen(fail_times=1)
        assert spawn_restart(
            executable=self.EXE, environ={}, exists=lambda _p: True, popen=popen
        )
        assert [kw["creationflags"] for _argv, kw in popen.calls] == list(
            creationflag_attempts()
        )

    def test_returns_false_when_nothing_could_be_spawned(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        popen = _RecordingPopen(fail_times=99)
        assert not spawn_restart(
            executable=self.EXE, environ={}, exists=lambda _p: True, popen=popen
        )
        assert len(popen.calls) == len(creationflag_attempts())
        assert "Restart unavailable" in caplog.text

    def test_logs_the_restart(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("INFO", logger="dictatem.process.restart")
        spawn_restart(
            executable=self.EXE,
            environ={},
            exists=lambda _p: True,
            popen=_RecordingPopen(),
        )
        assert "Restarting: spawned" in caplog.text
