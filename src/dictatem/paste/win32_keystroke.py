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


def _key_input(vk: int, flags: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
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
