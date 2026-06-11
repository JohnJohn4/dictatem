"""Smoke tests for the Windows native process adapter (Windows CI only).

Unlike the pure-matcher tests, these exercise the *real* OS primitives the
``win32_stopper`` adapter wraps — the class of bug the pyright-exclude / manual-QA
convention otherwise hides, even though CI runs on Windows. The original #69
stopper called ``win32process.QueryFullProcessImageName`` (absent in pywin32 312),
which returned ``""`` for every process, so the matcher matched nothing; the
``test_current_process_has_a_readable_exe_path`` case below would have failed
instantly in CI. The pattern generalises: any native adapter wrapping a
version/platform-sensitive OS API deserves one "does this primitive actually work
here" smoke test on its CI OS.

These are read-only or self-cleaning (a process we spawn ourselves), so they have
no side effects on the runner.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("win32 process adapter is Windows-only", allow_module_level=True)

from dictatem.process.win32_stopper import (  # noqa: E402
    _enumerate_processes,
    _resolve_trampoline,
    _terminate,
)


class TestEnumerateProcesses:
    """The WMI snapshot must return real exe paths + parent links."""

    def test_snapshot_is_non_empty(self) -> None:
        assert _enumerate_processes(), "WMI process snapshot was empty"

    def test_current_process_has_a_readable_exe_path(self) -> None:
        # THE #69 regression guard: the OS image-path read must yield a real
        # path, not "" (which silently makes the matcher match nothing).
        snapshot = _enumerate_processes()
        me = next((p for p in snapshot if p.pid == os.getpid()), None)
        assert me is not None, "current process missing from the WMI snapshot"
        assert me.exe_path, "exe_path empty — the OS image-path API is broken"
        assert me.exe_path.lower().endswith(".exe")

    def test_snapshot_carries_parent_links(self) -> None:
        # The tree walk reaches the launcher's re-exec'd child only via parent
        # PIDs, so the snapshot must populate them.
        snapshot = _enumerate_processes()
        me = next(p for p in snapshot if p.pid == os.getpid())
        assert me.parent_pid > 0
        assert any(p.pid == me.parent_pid for p in snapshot), (
            "current process's parent missing from the snapshot"
        )

    def test_snapshot_carries_creation_times(self) -> None:
        # The recycled-PID guard compares creation times; they must be present.
        me = next(p for p in _enumerate_processes() if p.pid == os.getpid())
        assert me.create_time, "create_time empty — the recycled-PID guard is blind"


class TestTerminatePrimitive:
    """OpenProcess(PROCESS_TERMINATE) + TerminateProcess must actually work."""

    def test_terminate_kills_a_process_we_spawned(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        try:
            assert _terminate(child.pid) is True
            child.wait(timeout=5)  # raises TimeoutExpired if the kill didn't land
            assert child.poll() is not None
        finally:
            if child.poll() is None:
                child.kill()


class TestTrampolineResolution:
    def test_trampoline_path_is_well_formed(self) -> None:
        # Pure path-building over `uv tool dir --bin`; should always name the exe.
        assert _resolve_trampoline().lower().endswith("dictatem.exe")
