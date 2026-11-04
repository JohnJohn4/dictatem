"""The per-user Start-menu shortcut ("Dictatem") that install.ps1 creates.

After **Quit** there was no discoverable way to start Dictatem again (only
Win+R → ``dictatem``, or signing in again with Start at login on). The
installer now adds ``Dictatem.lnk`` to the user's Start-menu Programs folder,
pointing at the windowless ``dictatem.exe`` launcher, so searching "Dictatem"
in Start works like any other app. ``dictatem --uninstall`` removes it here.

Per-user (``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs``): no admin
needed, which matters on managed machines.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SHORTCUT_NAME = "Dictatem.lnk"


def start_menu_shortcut_path(appdata: str | None = None) -> Path | None:
    """``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Dictatem.lnk``, or None."""
    base = appdata if appdata is not None else os.environ.get("APPDATA")
    if not base:
        return None
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / SHORTCUT_NAME


def remove_start_menu_shortcut(path: Path | None) -> bool:
    """Delete the shortcut if present; True if one was removed. Never raises."""
    if path is None or not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        logger.warning("Could not remove the Start-menu shortcut %s", path, exc_info=True)
        return False
    return True
