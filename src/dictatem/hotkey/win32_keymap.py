"""Pure Windows virtual-key-code → neutral ``Key`` translation.

Kept separate from the WH_KEYBOARD_LL hook (which is Windows-only and
import-guarded) so the mapping is importable and unit-testable on any
platform. The macOS hook supplies its own analogous map (see ADR-0018).
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from dictatem.hotkey.classifier import Key

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

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


# --- Dictatem's own injected input (#269 follow-up) ---
# KBDLLHOOKSTRUCT.flags bit set for any SendInput-injected event.
LLKHF_INJECTED = 0x10
# Every SendInput event Dictatem emits (Ctrl+V, the #171 neutralizing Ctrl tap,
# Trigger Fire backspaces/text) carries this tag in dwExtraInfo ("DICT"), so the
# keyboard hook can tell our own injections from the user's keys. Needed because
# Windows reports an injected *generic* VK_CONTROL to the low-level hook as the
# side-specific VK_LCONTROL (verified on Windows 11) — so without the tag, with
# Ctrl in the combo, our own Ctrl tap / Ctrl+V looks like the user pressing or
# releasing the hotkey.
DICTATEM_INJECTION_TAG = 0x44494354


def is_own_injection(flags: int, extra_info: int | None) -> bool:
    """True if a hooked key event was injected by Dictatem itself.

    Only OUR tagged injections are ignored: input injected by other tools (an
    on-screen keyboard, AutoHotkey remaps) still reaches the classifier, so a
    hotkey driven by such a tool keeps working.
    """
    return bool(flags & LLKHF_INJECTED) and extra_info == DICTATEM_INJECTION_TAG


# KBDLLHOOKSTRUCT.flags bit for an extended key (RAlt, LWin/RWin, ...): the
# replayed key-up must carry KEYEVENTF_EXTENDEDKEY to be the same key.
LLKHF_EXTENDED = 0x01
# The menu mask key (#171/#177): an unassigned virtual-key (AutoHotkey's default
# #MenuMaskKey). Injected between a lone Alt/Win press and its release so the OS
# sees the session as "not lone" — and, unlike Ctrl, it can never complete or
# break a hotkey combo or form a shortcut in the target app.
VK_MENU_MASK = 0xE8


def swallow_after_masked_replay(replay: Callable[[], bool]) -> bool:
    """Run *replay* (re-emit ``[mask down, mask up, key-up]``) and return whether
    the hook may swallow the ORIGINAL key-up.

    Never-stuck invariant: the original key-up is swallowed ONLY when *replay*
    reports that the full sequence — including the replayed key-up — was
    injected. Any failure (a short SendInput count, an exception) returns False
    so the hook passes the original key-up through instead; a modifier is never
    left logically held.
    """
    try:
        return replay() is True
    except Exception:
        logger.error("Masked key-up replay failed; passing key-up through", exc_info=True)
        return False


def vk_to_key(vk: int) -> Key:
    """Translate a Windows virtual-key code to a neutral ``Key``.

    Unrecognised codes map to ``Key.OTHER`` — tracked by the classifier but
    inert (never part of a modifier combo, an arrow, or escape).
    """
    return _VK_TO_KEY.get(vk, Key.OTHER)


# Virtual-key codes GetAsyncKeyState understands for each combo-relevant Key
# (mouse buttons included: VK_MBUTTON / VK_XBUTTON1 / VK_XBUTTON2).
_KEY_TO_VK: dict[Key, int] = {
    Key.LEFT_META: VK_LWIN,
    Key.RIGHT_META: VK_RWIN,
    Key.LEFT_ALT: VK_LMENU,
    Key.RIGHT_ALT: VK_RMENU,
    Key.LEFT_CTRL: VK_LCONTROL,
    Key.RIGHT_CTRL: VK_RCONTROL,
    Key.LEFT_SHIFT: VK_LSHIFT,
    Key.RIGHT_SHIFT: VK_RSHIFT,
    Key.MOUSE_MIDDLE: 0x04,
    Key.MOUSE_4: 0x05,
    Key.MOUSE_5: 0x06,
}


def physical_key_state(
    key: Key, get_async_key_state: Callable[[int], int] | None = None
) -> bool | None:
    """Whether *key* is physically down right now (Windows), or None if unknown.

    Backs the classifier's stale-modifier check. ``GetAsyncKeyState``'s high
    bit is the live physical state. *get_async_key_state* is injectable for
    tests; by default it calls user32.
    """
    vk = _KEY_TO_VK.get(key)
    if vk is None:
        return None
    if get_async_key_state is None:
        if sys.platform != "win32":
            return None
        import ctypes

        get_async_key_state = ctypes.windll.user32.GetAsyncKeyState  # type: ignore[attr-defined]
    try:
        return bool(int(get_async_key_state(vk)) & 0x8000)
    except Exception:
        return None
