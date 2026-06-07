"""No-op autostart registrar — macOS Phase-1 stand-in (#54).

Satisfies the AutostartRegistrar Protocol so the daemon's launch reconcile
(ADR-0012) and the tray "Start at login" toggle wire unchanged before the
LaunchAgent registrar exists (#61). enable() logs a warning: the config flag
still persists, but no OS entry is written until #61 lands.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NoopAutostartRegistrar:
    """AutostartRegistrar that registers nothing (real adapter: #61)."""

    def enable(self) -> None:
        logger.warning(
            "Start-at-login is not implemented on this platform yet (#61); "
            "the config flag was saved but no autostart entry was written"
        )

    def disable(self) -> None: ...

    def is_enabled(self) -> bool:
        return False
