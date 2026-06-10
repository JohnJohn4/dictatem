"""Win32 DaemonStopper — terminate running Dictatem daemons (manual QA only).

Supplies the OS snapshot for the pure :func:`~dictatem.process.daemon_stop.pids_to_stop`
matcher and terminates what it returns, so ``dictatem --uninstall`` (and the tray
Upgrade, #100) can free the ``…\\uv\\tools\\dictatem\\Scripts`` directory before
``uv tool uninstall``/``uv tool install`` runs (Windows otherwise fails with
``Access is denied`` while the interpreter is loaded — #69).

Excluded from pyright/tests (see ``pyproject.toml`` ``[tool.pyright] exclude``);
the *decision* is unit-tested through the pure matcher and ``FakeDaemonStopper``,
and the native enumerate/terminate behaviour is verified by manual QA on Windows.
Best-effort throughout: a process we cannot open or kill is skipped, never raised,
so the uninstall/upgrade always reaches its final step.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32process

from dictatem.process.daemon_stop import ProcessInfo, pids_to_stop

logger = logging.getLogger(__name__)

# CREATE_NO_WINDOW: keep the `uv tool dir` probe from flashing a console window
# under the windowless gui-scripts launch.
_CREATE_NO_WINDOW = 0x08000000


def _resolve_tool_dir() -> str | None:
    """Locate the uv tools ``dictatem`` directory whose interpreter holds the lock.

    Primary: ``uv tool dir`` names uv's tools root; Dictatem lives in its
    ``dictatem`` subdir. Fallback: derive it from our own interpreter, which runs
    from ``…\\uv\\tools\\dictatem\\Scripts\\python.exe`` — walk up to the
    ``dictatem`` directory that sits directly under a ``tools`` directory. Returns
    ``None`` if neither resolves, in which case we stop nothing rather than guess.
    """
    try:
        result = subprocess.run(
            ["uv", "tool", "dir"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        base = result.stdout.strip()
        if result.returncode == 0 and base:
            return str(Path(base) / "dictatem")
    except (OSError, subprocess.SubprocessError):
        logger.debug("`uv tool dir` unavailable; deriving tool dir from sys.executable")

    for parent in Path(sys.executable).resolve().parents:
        if parent.name.lower() == "dictatem" and parent.parent.name.lower() == "tools":
            return str(parent)
    return None


def _process_image_path(pid: int) -> str:
    """Full executable path for *pid*, or ``""`` if it can't be read.

    Uses ``QueryFullProcessImageName`` via ``PROCESS_QUERY_LIMITED_INFORMATION``
    (works without ``PROCESS_VM_READ`` and across integrity levels). An empty
    string signals "unreadable" to the pure matcher, which never matches it.
    """
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
    except pywintypes.error:
        return ""
    try:
        return win32process.QueryFullProcessImageName(handle, 0)
    except (pywintypes.error, AttributeError):
        return ""
    finally:
        win32api.CloseHandle(handle)


def _enumerate_processes() -> list[ProcessInfo]:
    """Snapshot every running process as ``ProcessInfo(pid, exe_path)``."""
    processes: list[ProcessInfo] = []
    for pid in win32process.EnumProcesses():
        if pid == 0:
            continue
        processes.append(ProcessInfo(pid=pid, exe_path=_process_image_path(pid)))
    return processes


def _terminate(pid: int) -> bool:
    """Best-effort ``TerminateProcess`` for *pid*; return whether it succeeded."""
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
    except pywintypes.error:
        return False
    try:
        win32api.TerminateProcess(handle, 1)
        return True
    except pywintypes.error:
        return False
    finally:
        win32api.CloseHandle(handle)


class Win32DaemonStopper:
    """DaemonStopper backed by the Win32 process APIs."""

    def stop_running_daemons(self) -> list[int]:
        tool_dir = _resolve_tool_dir()
        if tool_dir is None:
            logger.warning(
                "Could not locate the uv tools dictatem dir; skipping daemon stop"
            )
            return []
        trampoline = str(Path.home() / ".local" / "bin" / "dictatem.exe")
        targets = pids_to_stop(
            _enumerate_processes(),
            self_pid=os.getpid(),
            tool_dir=tool_dir,
            extra_exes=(trampoline,),
        )
        stopped = [pid for pid in targets if _terminate(pid)]
        if stopped:
            logger.info("Stopped running Dictatem daemon process(es): %s", stopped)
        return stopped
