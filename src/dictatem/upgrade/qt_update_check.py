"""Qt glue for the tray "Check for Updates" action (manual QA only).

Runs the GitHub release check on a worker thread so a menu click never freezes
the tray/overlay, then marshals the pure :class:`~dictatem.upgrade.core.UpgradeDecision`
back to the Qt main thread (via a queued ``Signal``) to show a notification and,
when a newer release exists, ask "Install update?" and launch the upgrade only on
an explicit yes (#200).

The *decision* and the confirm-then-start flow are pure and unit-tested
(``upgrade.core``); the threading/marshal, the dialog, and the notify/spawn side
effects are manual-QA, so this module is pyright/test
excluded like the other Qt adapters.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox

from dictatem.upgrade.core import apply_upgrade_decision, decide_upgrade

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.upgrade.core import UpgradeConfirmation, UpgradeDecision

logger = logging.getLogger(__name__)


def ask_install_confirmation(confirmation: UpgradeConfirmation) -> bool:
    """Modal "Install update?" box (Qt main thread). ``True`` only on Install.

    "Not now" is the default and the Esc/close result, so a stray Enter (or a
    dictation landing while the box has focus) can never consent by accident.
    ``exec()`` spins a nested event loop, so the daemon keeps ticking meanwhile.
    """
    box = QMessageBox()
    box.setWindowTitle(confirmation.title)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(confirmation.text)
    install = box.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
    not_now = box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(not_now)
    box.setEscapeButton(not_now)
    # A tray app has no main window; keep the question in front of whatever the
    # user was doing when they clicked the tray item.
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    box.raise_()
    box.activateWindow()
    box.exec()
    return box.clickedButton() is install


class UpdateChecker(QObject):
    """Drives one tray update check at a time, off the Qt main thread.

    Construct on the Qt main thread; wire :meth:`check` to the tray Upgrade item.
    The injected callables keep the network and OS work testable/replaceable:
    *fetch_latest_tag* returns the latest tag (or raises), *notify* shows a tray
    balloon, *confirm* asks the user before anything is installed (default: the
    :func:`ask_install_confirmation` dialog), *start_upgrade* launches the
    installer for a tag.
    """

    _finished = Signal(object)  # carries an UpgradeDecision across threads

    def __init__(
        self,
        *,
        current_version: str,
        fetch_latest_tag: Callable[[], str | None],
        notify: Callable[[str, str], None],
        start_upgrade: Callable[[str], None],
        confirm: Callable[[UpgradeConfirmation], bool] = ask_install_confirmation,
    ) -> None:
        super().__init__()
        self._current_version = current_version
        self._fetch_latest_tag = fetch_latest_tag
        self._notify = notify
        self._start_upgrade = start_upgrade
        self._confirm = confirm
        self._busy = False
        self._finished.connect(self._on_finished)

    def check(self) -> None:
        """Begin a check (Qt main thread). Ignores re-entry while one is running."""
        if self._busy:
            return
        self._busy = True
        self._notify("Dictatem", "Checking for updates…")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        # Worker thread: the blocking network call lives here, never on the UI.
        try:
            latest = self._fetch_latest_tag()
            decision = decide_upgrade(self._current_version, latest)
        except Exception:
            logger.error("Update check failed", exc_info=True)
            decision = decide_upgrade(self._current_version, None)
        self._finished.emit(decision)

    def _on_finished(self, decision: UpgradeDecision) -> None:
        # Back on the Qt main thread (queued signal): safe to touch the tray and
        # show the confirm dialog. Still busy while the dialog is up, so a second
        # tray click can't stack a second prompt.
        try:
            started = apply_upgrade_decision(
                decision,
                current_version=self._current_version,
                confirm=self._confirm,
                notify=self._notify,
                start_upgrade=self._start_upgrade,
            )
        except Exception:
            # A dialog/spawn failure must not wedge the tray item forever.
            logger.error("Update confirm/launch failed", exc_info=True)
            started = False
        if started:
            # Stay busy: the installer will stop and replace this daemon shortly;
            # a second check would only race a second installer on the locked dir.
            return
        self._busy = False
