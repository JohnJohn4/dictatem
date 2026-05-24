"""Win32 AutostartRegistrar — native HKCU Run-key adapter (manual QA only).

Writes/removes the per-user autostart entry under
``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``, pointing at the
installed ``dictatem`` gui-scripts launcher (ADR-0011) so login runs the same
windowless command as a manual launch. The daemon owns autostart and reconciles
this entry to ``config.startup.autostart`` on launch (ADR-0012).

Excluded from pyright/tests (see ``pyproject.toml`` ``[tool.pyright] exclude``);
its behaviour is exercised through ``FakeAutostartRegistrar`` in the unit suite
and the pure :func:`~dictatem.autostart.reconcile.reconcile_autostart` decision.
"""

from __future__ import annotations

import logging
import shutil
import sys
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Dictatem"


def _launch_command() -> str:
    """Return the command string to register for autostart.

    Prefer the installed ``dictatem`` gui-scripts launcher on PATH (no console
    pop, per ADR-0011). Fall back to ``pythonw -m dictatem`` when the launcher
    can't be located (e.g. a dev checkout) so the entry still runs windowless.
    Quoted so paths with spaces survive.
    """
    launcher = shutil.which("dictatem")
    if launcher:
        return f'"{launcher}"'

    # Fall back to the windowless interpreter so no console window flashes.
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    return f'"{interpreter}" -m dictatem'


class Win32AutostartRegistrar:
    """AutostartRegistrar backed by the HKCU Run key."""

    def enable(self) -> None:
        command = _launch_command()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)
        logger.info("Registered autostart entry -> %s", command)

    def disable(self) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, _VALUE_NAME)
            logger.info("Removed autostart entry")
        except FileNotFoundError:
            # Entry (or the Run key) already absent — disable is idempotent.
            pass

    def is_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, _VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
