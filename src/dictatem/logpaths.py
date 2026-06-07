"""Per-platform daemon.log location — a pure path decision, no I/O.

The daemon writes a rotating ``daemon.log`` (``daemon._add_rotating_log_file``)
and the tray "Open log" menu opens the same file, so the path decision lives
here once. Platform, env, and home arrive as parameters so every branch is
unit-testable on any OS (see ``tests/test_logpaths.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def daemon_log_path(platform: str, env: Mapping[str, str], home: Path) -> Path | None:
    """Return the daemon.log path for *platform*, or None when there is none.

    Windows: ``%APPDATA%\\Dictatem\\logs\\daemon.log`` (None if APPDATA is
    unset). macOS: ``~/Library/Logs/Dictatem/daemon.log`` — the standard user
    log location, browsable in Console.app. Other platforms have no daemon and
    hence no log path.
    """
    if platform == "win32":
        appdata = env.get("APPDATA")
        if not appdata:
            return None
        return Path(appdata) / "Dictatem" / "logs" / "daemon.log"
    if platform == "darwin":
        return home / "Library" / "Logs" / "Dictatem" / "daemon.log"
    return None
