"""Qt "update available" dialog for the manual (macOS) update path (#193).

Shows the pure :class:`~dictatem.upgrade.prompt.UpdatePrompt`: a headline, what
to do, and the pinned ``install.sh`` one-liner as selectable text. The
affirmative button **copies** the command to the clipboard — nothing is ever
executed on the user's behalf on macOS (phase 1 of #193). A second button opens
the README "Updating" section.

Like the other Qt modules this is excluded from pyright and carries no unit
tests; the prompt content and the platform → update-path decision are pure and
tested in ``upgrade.prompt``.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QMessageBox

from dictatem.upgrade.prompt import COMMAND_COPIED_NOTIFICATION

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.upgrade.prompt import UpdatePrompt

logger = logging.getLogger(__name__)


def _open_url(url: str) -> None:
    if sys.platform == "darwin":
        # Same route as the permission deep links: LaunchServices via `open`.
        try:
            subprocess.Popen(["/usr/bin/open", url])
            return
        except OSError:
            logger.error("Could not open %s via /usr/bin/open", url, exc_info=True)
    QDesktopServices.openUrl(QUrl(url))


def show_manual_update_prompt(
    prompt: UpdatePrompt, *, notify: Callable[[str, str], None]
) -> None:
    """Show the update prompt (Qt GUI thread; blocks in a nested event loop)."""
    box = QMessageBox()
    box.setWindowTitle("Dictatem")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(prompt.title)
    # Plain text (not rich): on macOS Qt may render QMessageBox as a native
    # NSAlert, which would show markup literally. The command sits on its own
    # line; the Copy button is the primary path, selection is a bonus.
    body = prompt.text
    if prompt.command:
        body += "\n\n" + prompt.command
    box.setInformativeText(body)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    copy_button = (
        box.addButton(prompt.accept_label, QMessageBox.ButtonRole.AcceptRole)
        if prompt.command
        else None
    )
    docs_button = box.addButton("Open Instructions", QMessageBox.ButtonRole.HelpRole)
    box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
    if copy_button is not None:
        box.setDefaultButton(copy_button)
    if sys.platform == "darwin":
        # A menu-bar accessory app is never auto-activated; without this the
        # dialog opens behind the frontmost app (same fix as #57's dialogs).
        from dictatem.macapp.activation import activate_app

        activate_app()
    box.raise_()
    box.activateWindow()
    box.exec()
    clicked = box.clickedButton()
    if copy_button is not None and clicked is copy_button and prompt.command:
        QGuiApplication.clipboard().setText(prompt.command)
        logger.info("Copied the update command to the clipboard")
        notify(*COMMAND_COPIED_NOTIFICATION)
    elif clicked is docs_button:
        _open_url(prompt.docs_url)
