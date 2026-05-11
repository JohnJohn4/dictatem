"""Win32 keystroke sender — requires pywin32."""

from __future__ import annotations

import ctypes
import ctypes.wintypes

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT(ctypes.Structure):
    class _UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]

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
        ctypes.windll.user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(_INPUT))
