"""Guided permission dialogs — the Qt half of the macOS permission UX (#57).

One message box per missing permission, built from the pure mapper's guidance:
the copy explains why Dictatem needs the permission, that only the *user* can
grant it in System Settings, and the one-time relaunch — and the [Open System
Settings] button deep-links straight into the right Privacy & Security pane.

Deep links open via ``/usr/bin/open`` rather than ``QDesktopServices.openUrl``
so the ``x-apple.systempreferences:`` scheme never depends on Qt's URL
handling — ``open`` hands any registered scheme to LaunchServices.

Like the other Qt modules (``qt_tray``, ``qt_widget``) this is excluded from
pyright and carries no unit tests; everything decidable — which permissions map
to which pane and copy, including the show-no-dialog case — is pure and tested
in ``permissions.mapper``.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dictatem.permissions.mapper import PermissionGuidance

logger = logging.getLogger(__name__)


def _open_settings(url: str) -> None:
    """Open a System Settings deep link via LaunchServices."""
    try:
        subprocess.Popen(["/usr/bin/open", url])
    except OSError:
        logger.error("Could not open System Settings link %s", url, exc_info=True)


def show_permission_dialogs(guidances: Sequence[PermissionGuidance]) -> None:
    """Show one guided dialog per missing permission, in mapper order.

    Must run on the Qt GUI thread. Each ``exec()`` spins a nested event loop,
    so the daemon's timers keep ticking while a dialog is up — recording from
    the tray still works mid-dialog.
    """
    for guidance in guidances:
        box = QMessageBox()
        box.setWindowTitle("Dictatem needs a permission")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(guidance.message)
        open_button = box.addButton(
            "Open System Settings", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        if sys.platform == "darwin":
            # The daemon is a menu-bar accessory app, which macOS never
            # auto-activates — without this the dialog opens behind the
            # frontmost app and vanishes on the first click elsewhere (#57).
            from dictatem.macapp.activation import activate_app

            activate_app()
        box.raise_()
        box.activateWindow()
        box.exec()
        if box.clickedButton() is open_button:
            _open_settings(guidance.settings_url)
