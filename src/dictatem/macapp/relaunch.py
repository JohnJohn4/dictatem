"""Relaunch the macOS daemon through launchd — the tray "Restart" item (#95).

A newly granted Accessibility / Input Monitoring permission only takes effect
once the daemon relaunches (ADR-0014), and the permission dialogs tell the user
to choose **Restart** from the menu-bar menu. The relaunch must go back through
**launchd**: a Terminal-started daemon gets its permission-gated actions
attributed to Terminal (the hotkey and paste then silently die), and a
``.app``/``open`` launch loses the menu-bar icon (ADR-0012/0014, #54/#56/#59).

So "Restart" spawns a fully detached ``sh`` that waits a beat — while this
daemon quits gracefully and releases its single-instance lock — then runs
``launchctl kickstart -k`` on the LaunchAgent service: ``-k`` kills a
still-running instance first, and either way launchd starts a fresh one. The
helper runs in its own session (``start_new_session``) so launchd's
process-group cleanup of the exiting job doesn't take it down too.

If the LaunchAgent service isn't loaded (Start at Login off, or the daemon was
started some other way) there is no launchd job to restart, and the caller
tells the user how to relaunch instead of faking it.

The argv/plan decisions are pure and take injected ``run``/``popen``/``uid`` so
they unit-test on any OS; only the real spawn is manual-QA. Importable
everywhere (stdlib only) — ``os.getuid`` is read lazily, inside the call.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import TYPE_CHECKING

from dictatem.macapp.plist import BUNDLE_ID

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

LAUNCHCTL = "/bin/launchctl"

# How long the detached helper waits before kickstarting, so this daemon has
# quit (and released ~/.dictatem/daemon.lock) before the new one checks it.
RELAUNCH_DELAY_S = 1


def launchd_service_target(uid: int, label: str = BUNDLE_ID) -> str:
    """The ``gui/<uid>/<label>`` service target ``print``/``kickstart`` take."""
    return f"gui/{uid}/{label}"


def service_loaded_argv(uid: int, label: str = BUNDLE_ID) -> list[str]:
    """``launchctl print`` the service — exit 0 iff launchd has it loaded."""
    return [LAUNCHCTL, "print", launchd_service_target(uid, label)]


def relaunch_helper_argv(uid: int, label: str = BUNDLE_ID) -> list[str]:
    """The detached helper: wait, then kill-if-running + start under launchd."""
    target = launchd_service_target(uid, label)
    return [
        "/bin/sh",
        "-c",
        f"sleep {RELAUNCH_DELAY_S}; {LAUNCHCTL} kickstart -k {target}",
    ]


# Notification copy for when no launchd job exists to restart.
MANUAL_RELAUNCH_HINT = (
    "Dictatem can't restart itself because it isn't running as its login item. "
    "Turn on Start at Login and log out and back in, or re-run the install command."
)


def spawn_launchd_relaunch(
    *,
    uid: int | None = None,
    label: str = BUNDLE_ID,
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    popen: Callable[..., object] = subprocess.Popen,
) -> bool:
    """Spawn the detached relaunch helper if the LaunchAgent service is loaded.

    Returns ``True`` when the helper was spawned — the caller must then quit
    this daemon so the new one can take the single-instance lock. ``False``
    means there is no loaded launchd job (or ``launchctl`` failed): nothing was
    spawned, so the caller should keep running and show
    ``MANUAL_RELAUNCH_HINT``.
    """
    resolved_uid = os.getuid() if uid is None else uid  # type: ignore[attr-defined]
    try:
        probe = run(
            service_loaded_argv(resolved_uid, label),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        logger.error("Could not run launchctl to check the service", exc_info=True)
        return False
    if probe.returncode != 0:
        logger.warning(
            "Restart unavailable: launchd service %s is not loaded",
            launchd_service_target(resolved_uid, label),
        )
        return False
    try:
        popen(
            relaunch_helper_argv(resolved_uid, label),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        logger.error("Could not spawn the relaunch helper", exc_info=True)
        return False
    logger.info("Restarting via launchd (%s)", launchd_service_target(resolved_uid, label))
    return True
