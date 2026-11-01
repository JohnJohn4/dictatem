"""Win32 keystroke sender — uses ctypes."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

from dictatem.hotkey.win32_keymap import (
    DICTATEM_INJECTION_TAG,
    LLKHF_EXTENDED,
    VK_MENU_MASK,
)
from dictatem.paste.modifier_wait import held_modifier_names

logger = logging.getLogger(__name__)

VK_CONTROL = 0x11
VK_V = 0x56
VK_BACK = 0x08
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT(ctypes.Structure):
    # Win32 INPUT is a union of mouse, keyboard, and hardware inputs.
    # The union must include all three so sizeof(_INPUT) matches what
    # SendInput expects; otherwise SendInput's cbSize check fails and the
    # call silently returns 0 with no input dispatched.
    class _UNION(ctypes.Union):
        _fields_ = [
            ("mi", _MOUSEINPUT),
            ("ki", _KEYBDINPUT),
            ("hi", _HARDWAREINPUT),
        ]

    _anonymous_ = ("_union",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_union", _UNION),
    ]


# Tag every injected event so our own keyboard hook can ignore it (see
# ``hotkey/win32_keymap.is_own_injection``).
_EXTRA_INFO = ctypes.cast(DICTATEM_INJECTION_TAG, ctypes.POINTER(ctypes.c_ulong))

_user32 = ctypes.WinDLL("user32", use_last_error=False)
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def _key_input(vk: int, flags: int = 0, scan: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(
        wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=_EXTRA_INFO
    )
    return inp


def _is_vk_down(vk: int) -> bool:
    # High bit set = the key is down right now (logical async state, which is
    # what an injected Ctrl+V combines with in the target).
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


class Win32KeystrokeSender:
    def held_modifiers(self) -> frozenset[str]:
        """Alt / Win / Shift / Ctrl currently down, via ``GetAsyncKeyState`` (#269)."""
        return held_modifier_names(_is_vk_down)

    def send_paste(self) -> None:
        inputs = (_INPUT * 4)(
            _key_input(VK_CONTROL),
            _key_input(VK_V),
            _key_input(VK_V, KEYEVENTF_KEYUP),
            _key_input(VK_CONTROL, KEYEVENTF_KEYUP),
        )
        sent = ctypes.windll.user32.SendInput(
            4, ctypes.byref(inputs), ctypes.sizeof(_INPUT)
        )
        if sent != 4:
            err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "SendInput dispatched %d/4 events (GetLastError=%d)", sent, err
            )

    def send_backspaces(self, n: int) -> None:
        if n <= 0:
            return
        count = n * 2  # one keydown + one keyup per backspace
        inputs_array = _INPUT * count
        inputs = inputs_array()
        for i in range(n):
            inputs[2 * i] = _key_input(VK_BACK)
            inputs[2 * i + 1] = _key_input(VK_BACK, KEYEVENTF_KEYUP)
        sent = ctypes.windll.user32.SendInput(
            count, ctypes.byref(inputs), ctypes.sizeof(_INPUT)
        )
        if sent != count:
            err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "SendInput dispatched %d/%d backspace events (GetLastError=%d)",
                sent,
                count,
                err,
            )

    def send_masked_release(self, vk: int, scan: int, hook_flags: int) -> bool:
        """Re-emit a swallowed lone Alt/Win key-up behind the menu mask key (#171/#177).

        Called from the keyboard hook for the key-up it is about to swallow:
        injects ``[VK_MENU_MASK down, VK_MENU_MASK up, <vk> up]`` as ONE batch,
        so the OS sees a key between the Alt/Win press and its release (not
        lone: no menu bar / Start menu) and the key still ends up released.
        The mask is the unassigned 0xE8 (AutoHotkey's default), not Ctrl: an
        injected generic Ctrl reaches the low-level hook as ``VK_LCONTROL``
        (verified on Windows 11) and would perturb a Ctrl-containing combo.

        Every event carries ``DICTATEM_INJECTION_TAG`` so the hook passes the
        replay through without feeding it to the classifier. Returns True only
        when all three events were dispatched; on False the hook passes the
        original key-up through instead, so a key can never be left stuck.
        """
        keyup_flags = KEYEVENTF_KEYUP
        if hook_flags & LLKHF_EXTENDED:
            keyup_flags |= KEYEVENTF_EXTENDEDKEY
        inputs = (_INPUT * 3)(
            _key_input(VK_MENU_MASK),
            _key_input(VK_MENU_MASK, KEYEVENTF_KEYUP),
            _key_input(vk, keyup_flags, scan=scan),
        )
        sent = ctypes.windll.user32.SendInput(
            3, ctypes.byref(inputs), ctypes.sizeof(_INPUT)
        )
        if sent != 3:
            err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "SendInput dispatched %d/3 masked-release events (GetLastError=%d)",
                sent,
                err,
            )
            return False
        return True

    def send_text(self, text: str) -> None:
        if not text:
            return
        # Encode to UTF-16 LE so supplementary-plane code points are split
        # into surrogate pairs — each 16-bit unit becomes one keystroke.
        units_bytes = text.encode("utf-16-le")
        n_units = len(units_bytes) // 2
        count = n_units * 2  # one keydown + one keyup per unit
        inputs_array = _INPUT * count
        inputs = inputs_array()
        for i in range(n_units):
            unit = int.from_bytes(units_bytes[2 * i : 2 * i + 2], "little")
            inputs[2 * i] = _key_input(0, KEYEVENTF_UNICODE, scan=unit)
            inputs[2 * i + 1] = _key_input(
                0, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, scan=unit
            )
        sent = ctypes.windll.user32.SendInput(
            count, ctypes.byref(inputs), ctypes.sizeof(_INPUT)
        )
        if sent != count:
            err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "SendInput dispatched %d/%d unicode events (GetLastError=%d)",
                sent,
                count,
                err,
            )
