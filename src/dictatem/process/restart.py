"""Relaunch the Windows daemon in place — the tray "Restart" item (#212).

The Usage Guide and README send the user to **Restart** after editing
``config.toml``; config is read once at startup, so Restart is how an edit
takes effect. The relaunch has to get past the single-instance guard (#92): the
old daemon holds ``~/.dictatem/daemon.lock`` until it exits, and a new daemon
normally refuses to start (``tryLock(0)``) while the lock is held.

So Restart spawns the new daemon **first**, fully detached, with
:data:`RESTART_ENV_VAR` set; then the old daemon quits gracefully. The new
daemon sees the variable and waits up to :data:`RESTART_LOCK_WAIT_MS` for the
lock instead of exiting at once — it takes over the moment the old process has
gone (``QLockFile`` also steals the lock of an owner that is no longer
running). If the old daemon somehow never exits, the new one gives up after the
wait and exits as a redundant instance: never two hooked daemons at once.

The relaunch command is the **same interpreter** the daemon is running under,
as ``-m dictatem``. For a uv-tool install ``sys.executable`` is the tool venv's
``Scripts\\pythonw.exe`` (the launcher stub that re-execs the base CPython,
#43), so the new daemon is matched by the uninstall/upgrade stopper exactly
like an autostarted one; for a dev ``uv run`` it is the checkout's
``.venv\\Scripts\\python.exe``, so the restart re-imports the same working tree.
``python.exe`` is swapped for its windowless ``pythonw.exe`` sibling, and the
process is created ``DETACHED_PROCESS`` so a console interpreter (the fallback
when no ``pythonw.exe`` exists) can never flash a console window either.

macOS restarts through launchd instead (#95) — it plugs into the same
``_PlatformAdapters.relaunch`` seam with its own relauncher; nothing here is
macOS-aware.

The argv/env/flag decisions are pure and the spawn takes an injected ``popen``,
so all of it unit-tests on any OS; only the real detached spawn is manual QA.
Importable everywhere (stdlib only).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

logger = logging.getLogger(__name__)

# Set (to "1") in the relaunched daemon's environment; read-and-cleared by the
# daemon at startup so it is not inherited by anything the daemon spawns later.
RESTART_ENV_VAR = "DICTATEM_RESTARTED"

# How long a relaunched daemon waits for the old one to release the
# single-instance lock. The old daemon unloads its model and exits within a
# second or two; the generous ceiling covers a slow unload on a loaded machine.
RESTART_LOCK_WAIT_MS = 30_000

# Win32 process-creation flags (subprocess exposes them only on Windows).
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# Notification copy for when the relaunch could not be spawned.
RESTART_FAILED_HINT = (
    "Dictatem couldn't restart itself. Choose Quit from this menu, then start "
    "Dictatem again."
)


def windowless_interpreter(
    executable: str, *, exists: Callable[[str], bool] = os.path.exists
) -> str:
    """Return *executable*'s ``pythonw.exe`` sibling if it has one, else itself.

    ``python.exe`` / ``python3.exe`` / ``python3.12.exe`` (any case) map to the
    ``pythonw`` of the same name in the same directory; anything already
    windowless, or with no such sibling on disk, is returned unchanged.
    """
    path = PureWindowsPath(executable)
    stem = path.stem
    if not stem.lower().startswith("python") or stem.lower().startswith("pythonw"):
        return executable
    candidate = str(path.with_name(f"pythonw{stem[len('python'):]}{path.suffix}"))
    return candidate if exists(candidate) else executable


def relaunch_argv(
    executable: str, *, exists: Callable[[str], bool] = os.path.exists
) -> list[str]:
    """The command that starts a fresh daemon under the same interpreter.

    ``-m dictatem`` (not the original ``argv[0]``): the uv trampoline's
    ``dictatem.exe`` argv and a ``python path\\to\\__main__.py`` run would each
    need special-casing, while ``-m`` resolves the same installed (or editable
    dev) package from the same venv in every case.
    """
    return [windowless_interpreter(executable, exists=exists), "-m", "dictatem"]


def relaunch_env(environ: Mapping[str, str]) -> dict[str, str]:
    """The relaunched daemon's environment: ours plus :data:`RESTART_ENV_VAR`."""
    return {**environ, RESTART_ENV_VAR: "1"}


def creationflag_attempts() -> tuple[int, ...]:
    """Process-creation flag sets to try, most-detached first.

    Breaking away from any job object keeps the new daemon alive if a job the
    old one runs in is closed when it exits; a job that forbids breakaway makes
    ``CreateProcess`` fail with access denied, so retry without it (uv's and
    CPython's launchers mark their jobs silent-breakaway anyway).
    """
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return (base | CREATE_BREAKAWAY_FROM_JOB, base)


def take_restart_lock_wait_ms(environ: MutableMapping[str, str]) -> int:
    """How long this daemon should wait for the single-instance lock.

    :data:`RESTART_LOCK_WAIT_MS` when it was launched by a tray Restart, else
    ``0`` (a normal launch refuses at once if a daemon is already running).
    Removes :data:`RESTART_ENV_VAR` from *environ* so it isn't inherited by
    processes this daemon spawns later (an upgrade's installer, say).
    """
    return RESTART_LOCK_WAIT_MS if environ.pop(RESTART_ENV_VAR, "") else 0


def spawn_restart(
    *,
    executable: str | None = None,
    environ: Mapping[str, str] | None = None,
    exists: Callable[[str], bool] = os.path.exists,
    popen: Callable[..., object] = subprocess.Popen,
) -> bool:
    """Spawn the detached replacement daemon; ``True`` if it was started.

    On ``True`` the caller must quit this daemon promptly so the new one can
    take the single-instance lock. ``False`` means nothing was spawned: keep
    running and show :data:`RESTART_FAILED_HINT`.
    """
    argv = relaunch_argv(sys.executable if executable is None else executable, exists=exists)
    env = relaunch_env(os.environ if environ is None else environ)
    for flags in creationflag_attempts():
        try:
            popen(
                argv,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=flags,
            )
        except OSError:
            logger.warning(
                "Restart spawn failed with creationflags=%#x", flags, exc_info=True
            )
            continue
        logger.info("Restarting: spawned %s", argv)
        return True
    logger.error("Restart unavailable: could not spawn %s", argv)
    return False
