"""Pure Windows virtual-key-code → neutral ``Key`` translation.

Kept separate from the WH_KEYBOARD_LL hook (which is Windows-only and
import-guarded) so the mapping is importable and unit-testable on any
platform. The macOS hook supplies its own analogous map (see ADR-0018).
"""

from __future__ import annotations

from dictatem.hotkey.classifier import Key

# Windows virtual-key codes the classifier cares about. The low-level hook
# reports side-specific codes (e.g. 0xA0/0xA1 for left/right shift).
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_ESCAPE = 0x1B
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28

_VK_TO_KEY: dict[int, Key] = {
    VK_LWIN: Key.LEFT_META,
    VK_RWIN: Key.RIGHT_META,
    VK_LMENU: Key.LEFT_ALT,
    VK_RMENU: Key.RIGHT_ALT,
    VK_LCONTROL: Key.LEFT_CTRL,
    VK_RCONTROL: Key.RIGHT_CTRL,
    VK_LSHIFT: Key.LEFT_SHIFT,
    VK_RSHIFT: Key.RIGHT_SHIFT,
    VK_ESCAPE: Key.ESCAPE,
    VK_LEFT: Key.LEFT,
    VK_UP: Key.UP,
    VK_RIGHT: Key.RIGHT,
    VK_DOWN: Key.DOWN,
}


def vk_to_key(vk: int) -> Key:
    """Translate a Windows virtual-key code to a neutral ``Key``.

    Unrecognised codes map to ``Key.OTHER`` — tracked by the classifier but
    inert (never part of a modifier combo, an arrow, or escape).
    """
    return _VK_TO_KEY.get(vk, Key.OTHER)
