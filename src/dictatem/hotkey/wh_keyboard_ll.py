"""Windows WH_KEYBOARD_LL adapter — bridges SetWindowsHookEx to HotkeyClassifier.

This module requires pywin32 and only works on Windows.
It is NOT imported at module level by any pure-core module;
tests run on Linux without touching this file.
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:

    from dictatem.hotkey.classifier import HotkeyClassifier

if sys.platform != "win32":
    raise ImportError("wh_keyboard_ll requires Windows")

import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32  # type: ignore[attr-defined]

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.wintypes.LPARAM,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class WHKeyboardLLHook:
    """Low-level keyboard hook that feeds events to a HotkeyClassifier."""

    def __init__(self, classifier: HotkeyClassifier) -> None:
        self._classifier = classifier
        self._hook_handle: int | None = None
        self._hook_thread: threading.Thread | None = None
        self._proc: ctypes.CFUNCTYPE | None = None  # type: ignore[type-arg]

    def install(self) -> None:
        self._hook_thread = threading.Thread(target=self._run_hook, daemon=True)
        self._hook_thread.start()

    def uninstall(self) -> None:
        if self._hook_handle is not None:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None

    def _run_hook(self) -> None:
        from dictatem.hotkey.classifier import HookDecision, KeyAction

        def _ll_callback(
            n_code: int, w_param: int, l_param: int
        ) -> int:
            if n_code >= 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                action = KeyAction.KEY_DOWN if is_down else KeyAction.KEY_UP
                timestamp_ms = kb.time
                decision, _event = self._classifier.process_event(vk, action, timestamp_ms)

                if decision is HookDecision.SUPPRESS:
                    return 1

            return user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        self._proc = HOOKPROC(_ll_callback)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, None, 0
        )

        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
