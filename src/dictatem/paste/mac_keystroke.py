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
CGEventPost is silently dropped by the system (no error surfaces here).
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac_keystroke requires macOS")

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventKeyboardSetUnicodeString,
    CGEventPost,
    CGEventSetFlags,
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
    def send_paste(self) -> None:
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
