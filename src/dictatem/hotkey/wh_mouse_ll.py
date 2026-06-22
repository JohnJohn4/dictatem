"""Windows WH_MOUSE_LL adapter — bridges SetWindowsHookEx to a thread-safe handler.

This module requires pywin32-style ctypes access and only works on Windows.
It is NOT imported at module level by any pure-core module; tests run on
Linux without touching this file.

It mirrors :mod:`dictatem.hotkey.wh_keyboard_ll` — own hook thread, own message
loop, native codes translated by a pure keymap (:mod:`win32_mouse_keymap`) — with
one difference that the mouse side buttons force (ADR-0020): a trigger button
usually has a normal OS action (Mouse4 = browser-back), so the hook must
**suppress** the event while it is completing the combo. A low-level hook can
only swallow an event by returning non-zero from its proc *on the hook thread*,
so the injected handler returns a :class:`~dictatem.hotkey.classifier.HookDecision`
synchronously rather than ``None``. All Tap/Hold and suppress/pass-through
*logic* still lives in the pure classifier; this adapter is the thin
SetWindowsHookEx plumbing that applies the decision.

The hook callback runs on the hook thread. Qt widget operations must happen on
the Qt GUI thread, so the handler must itself be thread-safe — it advances the
shared classifier under a lock and hands the resulting state-machine work to a
main-thread poller (see ``_HotkeyBridge.process_mouse_event``).
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

    from dictatem.hotkey.classifier import HookDecision, Key, KeyAction

if sys.platform != "win32":
    raise ImportError("wh_mouse_ll requires Windows")

import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32  # type: ignore[attr-defined]

WH_MOUSE_LL = 14

# On 64-bit Windows, WPARAM/LPARAM are pointer-sized (8 bytes), but
# ctypes.wintypes.WPARAM/LPARAM are c_ulong/c_long (4 bytes). Using the wrong
# types causes OverflowError on every event when l_param holds a 64-bit pointer.
# c_size_t / c_ssize_t are always pointer-sized. (Mirrors wh_keyboard_ll.)
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


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", ctypes.wintypes.POINT),
        # For the X buttons, the high word of ``mouseData`` says which side
        # button (XBUTTON1 = Mouse4, XBUTTON2 = Mouse5).
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class WHMouseLLHook:
    """Low-level mouse hook that forwards events to a thread-safe handler.

    ``on_mouse_event`` receives ``(key, action, timestamp_ms)`` and returns a
    ``HookDecision``: ``SUPPRESS`` swallows the event (the trigger button is
    completing the combo), ``PASS_THROUGH`` lets it reach the rest of the system.
    """

    def __init__(
        self, on_mouse_event: Callable[[Key, KeyAction, int], HookDecision]
    ) -> None:
        self._on_mouse_event = on_mouse_event
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
        from dictatem.hotkey.classifier import HookDecision
        from dictatem.hotkey.win32_mouse_keymap import mouse_event_to_key

        def _ll_callback(n_code: int, w_param: int, l_param: int) -> int:
            # SAFETY: a thrown exception must never escape the hook proc, and we
            # must only ever swallow an event we *decided* to suppress — any
            # error path falls through to CallNextHookEx so a bug can never make
            # the mouse unusable system-wide.
            suppress = False
            try:
                if n_code >= 0:
                    ms = ctypes.cast(
                        l_param, ctypes.POINTER(MSLLHOOKSTRUCT)
                    ).contents
                    x_button = (ms.mouseData >> 16) & 0xFFFF
                    mapped = mouse_event_to_key(w_param, x_button)
                    if mapped is not None:
                        key, action = mapped
                        # Use time.monotonic, not ms.time. ms.time is
                        # GetTickCount-derived; the Qt tick that drives
                        # HOLD_START detection passes time.monotonic. A non-zero
                        # offset between the clocks would make a single click
                        # fire a spurious HOLD_START. (Mirrors wh_keyboard_ll.)
                        timestamp_ms = int(time.monotonic() * 1000)
                        decision = self._on_mouse_event(key, action, timestamp_ms)
                        suppress = decision is HookDecision.SUPPRESS
            except Exception:
                logger.error("Error in mouse hook callback", exc_info=True)

            if suppress:
                # Returning non-zero without chaining swallows the event, so the
                # button's normal OS action (e.g. browser-back) does not fire.
                return 1
            return user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        self._proc = HOOKPROC(_ll_callback)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._proc, None, 0
        )

        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
