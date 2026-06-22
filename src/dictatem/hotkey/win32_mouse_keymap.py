"""Pure Windows mouse-message → neutral ``(Key, KeyAction)`` translation.

The companion to :mod:`dictatem.hotkey.win32_keymap` for the mouse side
buttons and wheel click (ADR-0020). Kept separate from the WH_MOUSE_LL hook
(which is Windows-only and import-guarded) so the mapping is importable and
unit-testable on any platform — the macOS hook supplies its own analogous map
(ADR-0018, #121).

A low-level mouse hook delivers the event kind in the message code (the hook
``wParam``) and, for the two side buttons, *which* button in the high word of
``MSLLHOOKSTRUCT.mouseData``. Only the wheel click and the X1/X2 side buttons
are trigger inputs; left/right click are primary interaction and movement /
wheel scrolling are never triggers, so they map to ``None`` (pass through).
"""

from __future__ import annotations

from dictatem.hotkey.classifier import Key, KeyAction

# WH_MOUSE_LL message codes (WinUser.h) the classifier cares about. The left /
# right button and movement / wheel codes are deliberately absent — they are
# never trigger inputs, so they fall through to ``None``.
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C

# High word of ``mouseData`` for the two side buttons (X1 = Mouse4, X2 = Mouse5).
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002

_MIDDLE_EVENTS: dict[int, tuple[Key, KeyAction]] = {
    WM_MBUTTONDOWN: (Key.MOUSE_MIDDLE, KeyAction.KEY_DOWN),
    WM_MBUTTONUP: (Key.MOUSE_MIDDLE, KeyAction.KEY_UP),
}

_XBUTTON_KEYS: dict[int, Key] = {
    XBUTTON1: Key.MOUSE_4,
    XBUTTON2: Key.MOUSE_5,
}


def mouse_event_to_key(message: int, x_button: int) -> tuple[Key, KeyAction] | None:
    """Translate a low-level mouse event to a neutral ``(Key, KeyAction)``.

    *message* is the hook ``wParam`` (a ``WM_*`` code); *x_button* is the high
    word of ``MSLLHOOKSTRUCT.mouseData`` — which side button — and is only
    consulted for the ``WM_XBUTTON*`` messages, ignored otherwise.

    Returns ``None`` for every mouse event Dictatem never triggers on (movement,
    wheel, left/right click, and any unrecognised X button), so the hook passes
    it straight through with ``CallNextHookEx``.
    """
    middle = _MIDDLE_EVENTS.get(message)
    if middle is not None:
        return middle
    if message in (WM_XBUTTONDOWN, WM_XBUTTONUP):
        key = _XBUTTON_KEYS.get(x_button)
        if key is None:
            return None
        action = KeyAction.KEY_DOWN if message == WM_XBUTTONDOWN else KeyAction.KEY_UP
        return key, action
    return None
