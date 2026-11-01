"""Windows app identity (AppUserModelID) for toast attribution — pure decisions.

Without an explicit AppUserModelID, Windows attributes the tray's
``showMessage`` balloons/toasts (e.g. "Silence detected — transcribing…") to
the host interpreter: they appear as "Python" with the Python icon. At startup
the daemon sets a stable process AUMID and registers it for unpackaged-app
toasts under ``HKCU\\Software\\Classes\\AppUserModelId\\<ID>`` with a display
name and icon, so they read "Dictatem" with our icon. ``--uninstall`` removes
the key.

This module holds only the decisions (ID, key path, values) and the
never-fatal orchestration; the OS calls are injected so it is testable on any
platform. The ctypes/winreg glue is ``process/win32_app_identity.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

logger = logging.getLogger(__name__)

APP_USER_MODEL_ID = "Matavex.Dictatem"
DISPLAY_NAME = "Dictatem"
# A PNG, not the .ico: IconUri is documented for image files and PNG renders
# crisply at the toast's logo size; 256 px downsamples cleanly at any DPI.
ICON_ASSET = "icon-256.png"


def aumid_registry_subkey(app_id: str = APP_USER_MODEL_ID) -> str:
    """The HKCU-relative registry key Windows reads an unpackaged AUMID from."""
    return rf"Software\Classes\AppUserModelId\{app_id}"


def aumid_registry_values(icon_path: Path) -> dict[str, str]:
    """Values to write under :func:`aumid_registry_subkey` (all string-typed)."""
    return {"DisplayName": DISPLAY_NAME, "IconUri": str(icon_path)}


def apply_app_identity(
    *,
    set_process_app_id: Callable[[str], None],
    write_registration: Callable[[str, Mapping[str, str]], None],
    icon_path: Path | None,
) -> None:
    """Set the process AUMID and (re)write its registration. Never raises.

    Idempotent: rewriting the same values on every start keeps ``IconUri``
    pointing at the currently installed package even after an upgrade moved
    it. Each step is attempted independently — a registry failure still leaves
    the process ID set (and vice versa) — and failures are only logged.
    """
    try:
        set_process_app_id(APP_USER_MODEL_ID)
    except Exception:
        logger.warning("Could not set the process AppUserModelID", exc_info=True)
    if icon_path is None:
        logger.warning("App icon not found; skipping AppUserModelID registration")
        return
    try:
        write_registration(aumid_registry_subkey(), aumid_registry_values(icon_path))
    except Exception:
        logger.warning("Could not register the AppUserModelID", exc_info=True)


def remove_app_identity(*, delete_registration: Callable[[str], None]) -> None:
    """Remove the AUMID registration (``--uninstall``). Never raises."""
    try:
        delete_registration(aumid_registry_subkey())
    except Exception:
        logger.warning("Could not remove the AppUserModelID registration", exc_info=True)
