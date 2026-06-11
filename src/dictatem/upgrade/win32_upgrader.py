"""Launch the in-place upgrade on Windows (manual QA only).

Spawns the documented ``install.ps1`` one-liner (ADR-0011/0015) at the new tag in
a **detached** PowerShell, so it survives the daemon being stopped and relaunched
mid-upgrade. Re-running the installer — rather than calling ``uv tool install``
directly here — reuses the verified upgrade path: it re-detects the GPU/CPU extra
(a bare reinstall would drop ``runtime-gpu`` and break the install), stops the
running daemon to free the ``…\\Scripts`` file lock (the same fix as #98),
installs the tag's tarball, and relaunches the new version.

Excluded from pyright/tests (see ``pyproject.toml``); the tag→URL mapping is
unit-tested in :mod:`dictatem.upgrade.core`, and the spawn is verified by manual
QA on Windows.
"""

from __future__ import annotations

import logging
import subprocess

from dictatem.upgrade.core import install_one_liner_url

logger = logging.getLogger(__name__)

# Give the installer its own console (so the user sees progress and the relaunch)
# and its own process group, so it is fully independent of the daemon it is about
# to stop and replace.
_CREATE_NEW_CONSOLE = 0x00000010
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def spawn_upgrade(tag: str) -> None:
    """Detach a PowerShell that re-runs ``install.ps1`` pinned to *tag*."""
    url = install_one_liner_url(tag)
    # Mirror the README one-liner: clear the policy for this process, then
    # download-and-run the pinned installer.
    inline = f"Set-ExecutionPolicy -Scope Process Bypass -Force; irm {url} | iex"
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            inline,
        ],
        creationflags=_CREATE_NEW_CONSOLE | _CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    logger.info("Launched upgrade to %s via install.ps1", tag)
