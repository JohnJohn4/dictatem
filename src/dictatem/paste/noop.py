"""No-op paste adapters — macOS Phase-1 stand-ins (#54).

The macOS daemon boots before its native paste adapters exist. These typed
no-ops satisfy the ClipboardIO / KeystrokeSender / ForegroundTracker Protocols
so the DaemonCore wiring is unchanged: a tray-driven recording completes
transcription but delivers nothing, and each delivery attempt logs a warning
so manual QA sees why. Replaced by the NSPasteboard/CGEvent adapters in #59.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NoopClipboardIO:
    """ClipboardIO that holds nothing — save() always sees an empty clipboard."""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def save(self) -> str | None:
        return None

    def set_text(self, text: str) -> None: ...

    def restore(self, saved: str | None) -> None: ...


class NoopKeystrokeSender:
    """KeystrokeSender that drops everything, loudly (real adapter: #59)."""

    def send_paste(self) -> None:
        logger.warning(
            "Paste is not implemented on this platform yet (#59); nothing was pasted"
        )

    def send_backspaces(self, n: int) -> None:
        logger.warning(
            "Keystrokes are not implemented on this platform yet (#59); "
            "dropped %d backspaces",
            n,
        )

    def send_text(self, text: str) -> None:
        logger.warning(
            "Keystrokes are not implemented on this platform yet (#59); "
            "dropped %d characters",
            len(text),
        )


class NoopForegroundTracker:
    """ForegroundTracker with a constant identity — every capture returns 0."""

    def capture(self) -> int:
        return 0

    def restore(self, target_id: int) -> None: ...
