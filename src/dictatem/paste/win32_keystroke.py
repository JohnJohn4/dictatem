"""Win32 keystroke sender — uses ctypes."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

logger = logging.getLogger(__name__)

VK_CONTROL = 0x11
VK_V = 0x56
VK_BACK = 0x08
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


def _key_input(vk: int, flags: int = 0, scan: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    return inp


class Win32KeystrokeSender:
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

    def send_modifier_release_mask(self) -> None:
        """Inject a no-op Ctrl tap to neutralize a lone Win/Alt key-up (#171).

        A lone Alt release activates the menu bar and a lone Win release pops the
        Start menu, which can move the caret and misfire the next paste. Injecting
        an innocuous Ctrl down+up while another combo modifier is still held marks
        that modifier's key session as "not lone", so its eventual release no
        longer triggers the OS side-effect. Ctrl is the masking key because a lone
        Ctrl tap has no UI effect of its own (the same trick AutoHotkey uses).

        MUST stay the *generic* ``VK_CONTROL`` (0x11), never side-specific
        ``VK_LCONTROL``/``VK_RCONTROL`` (0xA2/0xA3): this injected tap re-enters
        the low-level keyboard hook, and only the side-specific codes map to a real
        ``Key`` — generic 0x11 maps to ``Key.OTHER`` (inert), so the classifier can
        never mistake our own mask for a combo key, even in a Ctrl-containing combo
        (the same reason the paste rail's injected Ctrl+V is harmless). See
        ``hotkey/win32_keymap.py`` and ``HotkeyClassifier.pending_mask``.
        """
        inputs = (_INPUT * 2)(
            _key_input(VK_CONTROL),
            _key_input(VK_CONTROL, KEYEVENTF_KEYUP),
        )
        sent = ctypes.windll.user32.SendInput(
            2, ctypes.byref(inputs), ctypes.sizeof(_INPUT)
        )
        if sent != 2:
            err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "SendInput dispatched %d/2 neutralizing-mask events (GetLastError=%d)",
                sent,
                err,
            )

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
