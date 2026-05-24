"""macOS CGEvent keystroke sender (#59 / ADR-0004) — manual QA only.

The macOS analogue of ``win32_keystroke.py``: implements the ``KeystrokeSender``
Protocol via synthetic ``CGEvent``s posted to the session event tap.

- ``send_paste`` posts the platform paste shortcut — **Cmd+V** on macOS (the
  Protocol names it "Ctrl+V" for the Windows shape; the contract is "the OS paste
  chord").
- ``send_backspaces`` posts N Delete (backspace) key presses for the Trigger Fire
  replacement.
- ``send_text`` types text directly by posting key events carrying the literal
  Unicode via ``CGEventKeyboardSetUnicodeString`` — the typed Trigger Fire path
  (ADR-0004) that bypasses the clipboard, mirroring the Windows ``KEYEVENTF_UNICODE``
  approach so it works for arbitrary characters without per-character keycodes.

Synthetic events require the **Accessibility** grant (#57 / ADR-0014).

This module imports PyObjC (Quartz) and only works on macOS. It is NEVER imported
at module top level (lazy-imported in ``daemon._start_macos_daemon``;
``tests/test_import_safety.py``) and is excluded from pyright/tests
(``pyproject.toml`` ``[tool.pyright] exclude``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# macOS Carbon virtual keycodes.
_KEYCODE_V = 0x09
_KEYCODE_DELETE = 0x33  # Delete == Backspace on macOS


class CGEventKeystrokeSender:
    """KeystrokeSender backed by synthetic CGEvents (needs Accessibility)."""

    def send_paste(self) -> None:
        import Quartz  # type: ignore[import-not-found]

        # Cmd down (as a flag on the V events), V down, V up. Posting the
        # Command flag on the key events is the reliable way to deliver a chord.
        down = Quartz.CGEventCreateKeyboardEvent(None, _KEYCODE_V, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        up = Quartz.CGEventCreateKeyboardEvent(None, _KEYCODE_V, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, down)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, up)

    def send_backspaces(self, n: int) -> None:
        if n <= 0:
            return
        import Quartz  # type: ignore[import-not-found]

        for _ in range(n):
            down = Quartz.CGEventCreateKeyboardEvent(None, _KEYCODE_DELETE, True)
            up = Quartz.CGEventCreateKeyboardEvent(None, _KEYCODE_DELETE, False)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, down)
            Quartz.CGEventPost(Quartz.kCGSessionEventTap, up)

    def send_text(self, text: str) -> None:
        if not text:
            return
        import Quartz  # type: ignore[import-not-found]

        # Type the whole string by attaching its UTF-16 units to a key event via
        # CGEventKeyboardSetUnicodeString — keycode 0 with an attached string
        # types the literal characters regardless of layout (the macOS analogue
        # of Windows KEYEVENTF_UNICODE). Send the down event with the string and
        # a matching up event.
        units = text.encode("utf-16-le")
        n_units = len(units) // 2
        codepoints = [
            int.from_bytes(units[2 * i : 2 * i + 2], "little") for i in range(n_units)
        ]

        down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, n_units, codepoints)
        up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, n_units, codepoints)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, down)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, up)
