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
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.hotkey.classifier import Key

if sys.platform != "win32":
    raise ImportError("wh_keyboard_ll requires Windows")

import ctypes
import ctypes.wintypes

from dictatem.hotkey.classifier import KeyAction
from dictatem.hotkey.win32_keymap import vk_to_key

# The pointer-sized WPARAM/LPARAM, HOOKPROC and the hook thread live in the
# shared plumbing module (#245); _WPARAM/_LPARAM are re-exported for tests.
from dictatem.hotkey.win32_ll_hook import (
    _LPARAM,  # noqa: F401
    _WPARAM,  # noqa: F401
    HOOKPROC,
    LowLevelHookThread,
    call_next_hook,
)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class WHKeyboardLLHook:
    """Low-level keyboard hook that forwards events to a thread-safe handler.

    ``on_install_failed`` is called ON THE HOOK THREAD with the OS error code
    when Windows refuses the hook (the failure is also logged) — it must be
    thread-safe (the daemon enqueues, #245).
    """

    def __init__(
        self,
        on_key_event: Callable[[Key, KeyAction, int], bool],
        inject_mask: Callable[[], None] | None = None,
        *,
        on_install_failed: Callable[[int], None] | None = None,
    ) -> None:
        self._on_key_event = on_key_event
        # Optional neutralizing-keystroke injector (#171): called after a key-up
        # for which the handler returns True, so a lone Win/Alt release on a chord
        # cannot activate the menu bar / Start menu. None disables masking.
        self._inject_mask = inject_mask
        self._runner = LowLevelHookThread(
            WH_KEYBOARD_LL, label="keyboard", on_install_failed=on_install_failed
        )

    def install(self) -> None:
        self._runner.start(HOOKPROC(self._ll_callback))

    def uninstall(self) -> None:
        """Remove the hook and wait for the hook thread to exit."""
        self._runner.stop()

    def is_running(self) -> bool:
        return self._runner.is_running()

    def _ll_callback(self, n_code: int, w_param: int, l_param: int) -> int:
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
                mask = self._on_key_event(vk_to_key(vk), action, timestamp_ms)
                # Neutralizing keystroke for a lone Win/Alt chord release
                # (#171). Injected here (the other combo modifier is still
                # down, so the injected key lands within its key session) and
                # passed through to the system below. Best-effort: an injection
                # hiccup must never block the real key from reaching the app.
                if mask and self._inject_mask is not None:
                    self._inject_mask()
        except Exception:
            logger.error("Error in keyboard hook callback", exc_info=True)

        return call_next_hook(n_code, w_param, l_param)
