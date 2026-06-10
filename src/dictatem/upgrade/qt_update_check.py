"""Qt glue for the tray "Check for Updates" action (manual QA only).

Runs the GitHub release check on a worker thread so a menu click never freezes
the tray/overlay, then marshals the pure :class:`~dictatem.upgrade.core.UpgradeDecision`
back to the Qt main thread (via a queued ``Signal``) to show a notification and,
when a newer release exists, launch the upgrade.

The *decision* is pure and unit-tested (``upgrade.core``); the threading/marshal
and the notify/spawn side effects are manual-QA, so this module is pyright/test
excluded like the other Qt adapters.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from dictatem.upgrade.core import UpgradeKind, decide_upgrade

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.upgrade.core import UpgradeDecision

logger = logging.getLogger(__name__)


class UpdateChecker(QObject):
    """Drives one tray update check at a time, off the Qt main thread.

    Construct on the Qt main thread; wire :meth:`check` to the tray Upgrade item.
    The injected callables keep the network and OS work testable/replaceable:
    *fetch_latest_tag* returns the latest tag (or raises), *notify* shows a tray
    balloon, *start_upgrade* launches the installer for a tag.
    """

    _finished = Signal(object)  # carries an UpgradeDecision across threads

    def __init__(
        self,
        *,
        current_version: str,
        fetch_latest_tag: Callable[[], str | None],
        notify: Callable[[str, str], None],
        start_upgrade: Callable[[str], None],
    ) -> None:
        super().__init__()
        self._current_version = current_version
        self._fetch_latest_tag = fetch_latest_tag
        self._notify = notify
        self._start_upgrade = start_upgrade
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
        # Back on the Qt main thread (queued signal): safe to touch the tray.
        self._busy = False
        self._notify("Dictatem", decision.message)
        if decision.kind is UpgradeKind.UPGRADE_AVAILABLE and decision.tag:
            self._start_upgrade(decision.tag)
