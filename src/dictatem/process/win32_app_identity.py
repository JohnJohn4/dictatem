"""Win32 glue for the app identity (AppUserModelID) — ctypes + winreg only.

The decisions (ID, key path, values) and the never-fatal orchestration live in
the pure ``process.app_identity``; these are the thin OS calls it injects.
"""

from __future__ import annotations

import ctypes
import logging
import winreg
from typing import TYPE_CHECKING

from dictatem.process.app_identity import apply_app_identity, remove_app_identity

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

logger = logging.getLogger(__name__)


def set_process_app_id(app_id: str) -> None:
    """``SetCurrentProcessExplicitAppUserModelID``; raises ``OSError`` on failure.

    Must run before any window or tray icon is created so the shell attributes
    them (and their toasts) to this ID.
    """
    shell32 = ctypes.WinDLL("shell32")
    fn = shell32.SetCurrentProcessExplicitAppUserModelID
    fn.argtypes = [ctypes.c_wchar_p]
    fn.restype = ctypes.c_long  # HRESULT
    hr = fn(app_id)
    if hr != 0:
        raise OSError(f"SetCurrentProcessExplicitAppUserModelID failed: HRESULT {hr:#x}")


def write_registration(subkey: str, values: Mapping[str, str]) -> None:
    """Create/overwrite ``HKCU\\<subkey>`` with *values* (idempotent)."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def delete_registration(subkey: str) -> None:
    """Delete ``HKCU\\<subkey>``; already absent is not an error."""
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        logger.info("Removed AppUserModelID registration")
    except FileNotFoundError:
        pass


def register_app_identity(icon_path: Path | None) -> None:
    """Daemon startup: set the process AUMID + register it. Never raises."""
    apply_app_identity(
        set_process_app_id=set_process_app_id,
        write_registration=write_registration,
        icon_path=icon_path,
    )


def unregister_app_identity() -> None:
    """``--uninstall``: remove the AUMID registration. Never raises."""
    remove_app_identity(delete_registration=delete_registration)
