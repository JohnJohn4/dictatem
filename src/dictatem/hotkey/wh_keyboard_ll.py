"""Windows WH_KEYBOARD_LL adapter — bridges SetWindowsHookEx to a thread-safe handler.

This module requires pywin32 and only works on Windows.
It is NOT imported at module level by any pure-core module;
tests run on Linux without touching this file.

The hook callback runs on the hook thread.  Qt widget operations must
happen on the Qt GUI thread, so the handler passed in here must itself
be thread-safe (typically an enqueue-only function that hands work over
to a main-thread poller).
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.hotkey.classifier import KeyAction

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

# On 64-bit Windows, WPARAM/LPARAM are pointer-sized (8 bytes), but
# ctypes.wintypes.WPARAM/LPARAM are c_ulong/c_long (4 bytes). Using the
# wrong types causes OverflowError on every keystroke when l_param holds a
# 64-bit pointer value. c_size_t / c_ssize_t are always pointer-sized.
_WPARAM = ctypes.c_size_t
_LPARAM = ctypes.c_ssize_t

HOOKPROC = ctypes.CFUNCTYPE(
    _LPARAM,
    ctypes.c_int,
    _WPARAM,
    _LPARAM,
)

user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,  # hhk
    ctypes.c_int,     # nCode
    _WPARAM,          # wParam
    _LPARAM,          # lParam
]
user32.CallNextHookEx.restype = _LPARAM


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class WHKeyboardLLHook:
    """Low-level keyboard hook that forwards events to a thread-safe handler."""

    def __init__(
        self, on_key_event: Callable[[int, KeyAction, int], None]
    ) -> None:
        self._on_key_event = on_key_event
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
        from dictatem.hotkey.classifier import KeyAction

        def _ll_callback(
            n_code: int, w_param: int, l_param: int
        ) -> int:
            # SAFETY: always call through to the next hook, even on errors.
            # Returning without calling CallNextHookEx swallows the key
            # system-wide, rendering the keyboard unusable until the process
            # exits.
            try:
                if n_code >= 0:
                    kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = kb.vkCode
                    is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    action = KeyAction.KEY_DOWN if is_down else KeyAction.KEY_UP
                    # Use time.monotonic, not kb.time. kb.time is
                    # GetTickCount-derived; the Qt tick that drives
                    # HOLD_START detection passes time.monotonic. If the two
                    # clocks have a non-zero offset, a single tap fires a
                    # spurious HOLD_START → PTT_REC → instant stop.
                    timestamp_ms = int(time.monotonic() * 1000)
                    self._on_key_event(vk, action, timestamp_ms)
            except Exception:
                logger.error("Error in keyboard hook callback", exc_info=True)

            return user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        self._proc = HOOKPROC(_ll_callback)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, None, 0
        )

        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
