"""macOS keystroke sender — CGEvent via PyObjC Quartz (manual QA only).

This module requires pyobjc-framework-Quartz and only works on macOS; it is
never imported at module level by any pure-core module, and the paste
pipeline is exercised against an in-memory fake in tests. Excluded from
pyright (see ``pyproject.toml`` ``[tool.pyright] exclude``) because Quartz
is unresolvable off-macOS.

``send_text`` types the text directly via ``CGEventKeyboardSetUnicodeString``
— never clipboard + Cmd+V. Trigger Fire uses TYPED input by design
(ADR-0004, #23): typing removes the clipboard from the trigger-fire critical
path entirely, so there is no restore race with the target's paste handler
and the user's clipboard is left untouched.

Posting synthetic events requires the Accessibility TCC grant; without it
CGEventPost is silently dropped by the system (no error surfaces from the
post). So every send first preflights the grant (``CGPreflightPostEventAccess``,
ADR-0014) and, when it is missing, calls ``on_access_blocked`` — the daemon's
re-prompt-on-use hook (#95) — so a paste never fails silently. The events are
still posted (a stale preflight must never block a paste that would land).
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac_keystroke requires macOS")

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventKeyboardSetUnicodeString,
    CGEventPost,
    CGEventSetFlags,
    CGPreflightPostEventAccess,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

# macOS virtual key codes (HIToolbox Events.h kVK_* constants).
KVK_ANSI_V = 0x09
KVK_DELETE = 0x33  # the Backspace key, despite the name

# Note on dispatch checking: Win32 SendInput returns a dispatched-event count
# the win32 adapter compares and logs shortfalls against; CGEventPost returns
# None, so there is nothing equivalent to verify here.


class MacKeystrokeSender:
    def __init__(self) -> None:
        # Set by the daemon after construction (the tray/dialog machinery it
        # reports to doesn't exist yet when the adapter set is built). Called
        # on the calling (Qt) thread; must be cheap and must not raise.
        self.on_access_blocked: Callable[[], None] | None = None

    def _check_access(self) -> None:
        try:
            if CGPreflightPostEventAccess():
                return
            logger.warning(
                "Accessibility permission is missing — macOS will drop this "
                "synthetic paste/keystroke"
            )
            if self.on_access_blocked is not None:
                self.on_access_blocked()
        except Exception:
            logger.error("Error checking the Accessibility grant", exc_info=True)

    def held_modifiers(self) -> frozenset[str]:
        """Always "none held" on macOS (#269).

        Unlike Win32 SendInput, every CGEvent this adapter posts carries an
        EXPLICIT flag set (``CGEventSetFlags``: Command only for the paste,
        0 for backspaces/text), so a physically held Option/Control/Shift does
        not leak into the injected keystroke. Polling
        ``CGEventSourceFlagsState`` would only add a wait (and an untested
        PyObjC call on the paste path) for no correctness gain, so the paste
        pipeline's release wait is a deliberate no-op here.
        """
        return frozenset()

    def send_paste(self) -> None:
        self._check_access()
        # Synthetic Cmd+V. The Command flag must be set on BOTH the down and
        # the up event — omitting it on the up can leave a stuck modifier in
        # some apps.
        for is_down in (True, False):
            event = CGEventCreateKeyboardEvent(None, KVK_ANSI_V, is_down)
            CGEventSetFlags(event, kCGEventFlagMaskCommand)
            CGEventPost(kCGHIDEventTap, event)

    def send_backspaces(self, n: int) -> None:
        if n <= 0:
            return
        self._check_access()
        for _ in range(n):
            for is_down in (True, False):
                event = CGEventCreateKeyboardEvent(None, KVK_DELETE, is_down)
                # Explicitly clear flags so no modifier state is inherited
                # (the hotkey chord may still be physically held).
                CGEventSetFlags(event, 0)
                CGEventPost(kCGHIDEventTap, event)

    def send_text(self, text: str) -> None:
        if not text:
            return
        self._check_access()
        for ch in text:
            # CGEventKeyboardSetUnicodeString takes the length in UTF-16 code
            # units: 2 for supplementary-plane characters (emoji etc.), which
            # PyObjC marshals into the surrogate pair for us — mirroring the
            # win32 adapter's UTF-16 LE encoding.
            n_units = len(ch.encode("utf-16-le")) // 2
            for is_down in (True, False):
                # Keycode 0 is a placeholder — the unicode string attached to
                # the event determines what the target inserts, like
                # KEYEVENTF_UNICODE on Windows.
                event = CGEventCreateKeyboardEvent(None, 0, is_down)
                CGEventSetFlags(event, 0)
                CGEventKeyboardSetUnicodeString(event, n_units, ch)
                CGEventPost(kCGHIDEventTap, event)
