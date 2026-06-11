"""Win32 DaemonStopper — terminate the running Dictatem daemon (manual QA only).

Supplies the OS snapshot for the pure :func:`~dictatem.process.daemon_stop.pids_to_stop`
matcher and terminates what it returns, so ``dictatem --uninstall`` (and the tray
Upgrade, #100) can free the ``…\\uv\\tools\\dictatem\\Scripts`` directory before
``uv tool uninstall``/``uv tool install`` runs (Windows otherwise fails with
``Access is denied`` while the interpreter is loaded — #69).

The snapshot comes from **WMI** (``Win32_Process``): it yields each process's
parent PID and creation time as well as its exe path, which the pure matcher needs
to walk from the path-matched roots down to the launcher's re-exec'd base-CPython
child (the real daemon, whose exe is outside the tool dir). This mirrors
``install.ps1``'s ``Stop-DictatemDaemon``; keep the two in sync. (An earlier
version read only exe paths via ``win32process.QueryFullProcessImageName`` — which
is absent in some pywin32 builds and returned ``""`` for every process, so the
stopper silently matched nothing; a real-machine uninstall caught it.)

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

from dictatem.process.daemon_stop import ProcessInfo, pids_to_stop

logger = logging.getLogger(__name__)

# CREATE_NO_WINDOW: keep the `uv tool dir` probe from flashing a console window
# under the windowless gui-scripts launch.
_CREATE_NO_WINDOW = 0x08000000


def _resolve_tool_dir() -> str | None:
    """Locate the uv tools ``dictatem`` directory whose interpreter holds the lock.

    Primary: ``sys.prefix`` — for a uv-tool gui-script the active venv root *is*
    the tool dir (``…\\uv\\tools\\dictatem``), which works windowless with no
    dependency on ``uv`` being on PATH. Fallbacks, in order: the installed
    ``dictatem`` package's own location; ``uv tool dir``; and finally walking up
    from ``sys.executable``. Returns ``None`` if none resolve, in which case we
    stop nothing rather than guess.
    """
    prefix = Path(sys.prefix)
    if prefix.name.lower() == "dictatem" and prefix.parent.name.lower() == "tools":
        return str(prefix)

    try:
        import dictatem

        for parent in Path(dictatem.__file__).resolve().parents:
            if parent.name.lower() == "dictatem" and parent.parent.name.lower() == "tools":
                return str(parent)
    except Exception:
        pass

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
        logger.debug("`uv tool dir` unavailable; falling back to sys.executable")

    for parent in Path(sys.executable).resolve().parents:
        if parent.name.lower() == "dictatem" and parent.parent.name.lower() == "tools":
            return str(parent)
    return None


def _resolve_trampoline() -> str:
    """Full path of the ``dictatem.exe`` launcher trampoline in uv's bin dir.

    Resolved via ``uv tool dir --bin`` so it honours a custom ``UV_TOOL_BIN_DIR``
    (matching how ``install.ps1`` finds it); falls back to uv's documented default
    ``~/.local/bin``. Secondary to the tool-dir match — the running daemon's
    process tree is rooted at the Scripts interpreter under the tool dir too.
    """
    try:
        result = subprocess.run(
            ["uv", "tool", "dir", "--bin"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        bin_dir = result.stdout.strip()
        if result.returncode == 0 and bin_dir:
            return str(Path(bin_dir) / "dictatem.exe")
    except (OSError, subprocess.SubprocessError):
        logger.debug("`uv tool dir --bin` unavailable; using ~/.local/bin")
    return str(Path.home() / ".local" / "bin" / "dictatem.exe")


def _enumerate_processes() -> list[ProcessInfo]:
    """Snapshot every process (pid, parent, exe, create-time) via WMI.

    WMI is what gives us the parent PID and creation time the pure matcher needs
    to follow the launcher's re-exec'd child. ``ExecutablePath`` is ``None`` for
    processes we can't introspect (system/protected) — recorded as ``""``, which
    never path-matches as a root but can still be reached as a descendant.
    """
    import win32com.client

    wmi = win32com.client.GetObject("winmgmts:")
    query = (
        "SELECT ProcessId, ParentProcessId, ExecutablePath, CreationDate "
        "FROM Win32_Process"
    )
    processes: list[ProcessInfo] = []
    for proc in wmi.ExecQuery(query):
        processes.append(
            ProcessInfo(
                pid=int(proc.ProcessId),
                parent_pid=int(proc.ParentProcessId or 0),
                exe_path=proc.ExecutablePath or "",
                create_time=proc.CreationDate or None,
            )
        )
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
    """DaemonStopper backed by a WMI snapshot + the Win32 terminate API."""

    def stop_running_daemons(self) -> list[int]:
        tool_dir = _resolve_tool_dir()
        if tool_dir is None:
            logger.warning(
                "Could not locate the uv tools dictatem dir; skipping daemon stop"
            )
            return []
        try:
            snapshot = _enumerate_processes()
        except Exception:
            logger.error("Could not enumerate processes (WMI); skipping daemon stop",
                         exc_info=True)
            return []
        targets = pids_to_stop(
            snapshot,
            self_pid=os.getpid(),
            tool_dir=tool_dir,
            trampolines=(_resolve_trampoline(),),
        )
        stopped = [pid for pid in targets if _terminate(pid)]
        if stopped:
            logger.info("Stopped running Dictatem daemon process(es): %s", stopped)
        return stopped
