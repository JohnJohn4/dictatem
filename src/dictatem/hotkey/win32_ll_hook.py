"""Shared ctypes plumbing for the Windows low-level hooks (#245).

Both :mod:`wh_keyboard_ll` and :mod:`wh_mouse_ll` run a ``WH_*_LL`` hook on a
dedicated thread with its own message loop. This module owns that part once,
so the two hooks are hardened together:

* **Correct prototypes.** ``SetWindowsHookExW`` returns a pointer-sized
  ``HHOOK`` (``c_void_p`` — a ``c_int`` default would truncate it), so a NULL
  result arrives as ``None`` and is detectable.
* **Install failures are reported**, not silent: the OS error
  (``GetLastError``) is logged and handed to an ``on_install_failed`` callback,
  which the daemon turns into a tray notification (review F-15).
* **Uninstall makes the thread exit**: it posts ``WM_QUIT`` to the hook
  thread, whose ``GetMessageW`` loop then returns; the thread unhooks itself
  (the thread that installed the hook removes it) and is joined.
* **No first-event handle race**: the hook procs pass ``NULL`` as the
  ``hhk`` to ``CallNextHookEx`` (the parameter is ignored), so a proc never
  reads a handle that the installing thread may not have stored yet.

A private ``WinDLL`` instance with ``use_last_error`` is used so these
prototypes never clobber the ones other modules set on ``ctypes.windll.user32``.

Windows-only and not imported by any pure-core module.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

if sys.platform != "win32":
    raise ImportError("win32_ll_hook requires Windows")

import ctypes
import ctypes.wintypes

logger = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000

# On 64-bit Windows, WPARAM/LPARAM are pointer-sized (8 bytes), but
# ctypes.wintypes.WPARAM/LPARAM are c_ulong/c_long (4 bytes). Using the wrong
# types causes OverflowError on every event when l_param holds a 64-bit
# pointer value. c_size_t / c_ssize_t are always pointer-sized.
_WPARAM = ctypes.c_size_t
_LPARAM = ctypes.c_ssize_t

HOOKPROC = ctypes.CFUNCTYPE(_LPARAM, ctypes.c_int, _WPARAM, _LPARAM)

_LPMSG = ctypes.POINTER(ctypes.wintypes.MSG)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,  # idHook
    HOOKPROC,  # lpfn
    ctypes.c_void_p,  # hmod (HINSTANCE)
    ctypes.wintypes.DWORD,  # dwThreadId
]
user32.SetWindowsHookExW.restype = ctypes.c_void_p  # HHOOK; NULL -> None
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,  # hhk (ignored by Windows; pass None)
    ctypes.c_int,  # nCode
    _WPARAM,  # wParam
    _LPARAM,  # lParam
]
user32.CallNextHookEx.restype = _LPARAM
user32.GetMessageW.argtypes = [
    _LPMSG,
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.wintypes.BOOL  # -1 on error
user32.PeekMessageW.argtypes = [
    _LPMSG,
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
user32.PeekMessageW.restype = ctypes.wintypes.BOOL
user32.TranslateMessage.argtypes = [_LPMSG]
user32.TranslateMessage.restype = ctypes.wintypes.BOOL
user32.DispatchMessageW.argtypes = [_LPMSG]
user32.DispatchMessageW.restype = _LPARAM
user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.UINT,
    _WPARAM,
    _LPARAM,
]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD

# How long uninstall waits for the hook thread to come up / wind down.
_STOP_TIMEOUT_S = 2.0


def _last_error() -> int:
    """The calling thread's last Win32 error (captured by ``use_last_error``)."""
    return ctypes.get_last_error()


def call_next_hook(n_code: int, w_param: int, l_param: int) -> int:
    """Chain to the next hook. ``hhk`` is ignored by Windows, so pass NULL."""
    return user32.CallNextHookEx(None, n_code, w_param, l_param)


class LowLevelHookThread:
    """Runs one ``WH_*_LL`` hook on its own thread with its own message loop."""

    def __init__(
        self,
        hook_id: int,
        *,
        label: str,
        on_install_failed: Callable[[int], None] | None = None,
    ) -> None:
        self._hook_id = hook_id
        self._label = label
        self._on_install_failed = on_install_failed
        self._proc: object | None = None  # kept alive while the hook is live
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()

    def start(self, proc: object) -> None:
        """Install *proc* (a ``HOOKPROC`` instance) on a new hook thread."""
        self._proc = proc
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"dictatem-{self._label}-hook", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Quit the hook thread's message loop and wait for it to exit."""
        thread = self._thread
        if thread is None:
            return
        # Wait for the thread to own a message queue (or to have failed), so
        # the WM_QUIT below can't be posted into the void.
        self._ready.wait(_STOP_TIMEOUT_S)
        thread_id = self._thread_id
        posted = (
            thread_id is None
            or not thread.is_alive()
            or user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        )
        if not posted:
            logger.warning(
                "Could not post WM_QUIT to the %s hook thread (OS error %d)",
                self._label,
                _last_error(),
            )
        if thread is not threading.current_thread():
            thread.join(_STOP_TIMEOUT_S)
            if thread.is_alive():
                logger.warning("The %s hook thread did not exit", self._label)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        msg = ctypes.wintypes.MSG()
        try:
            # Force this thread's message queue into existence before anyone
            # can post WM_QUIT to it.
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
            self._thread_id = kernel32.GetCurrentThreadId()
            handle = user32.SetWindowsHookExW(self._hook_id, self._proc, None, 0)
            if not handle:
                error_code = _last_error()
                self._thread_id = None  # nothing to post WM_QUIT to
                self._report_install_failure(error_code)
                return
        finally:
            self._ready.set()

        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:  # WM_QUIT
                    break
                if result == -1:
                    logger.error(
                        "The %s hook message loop failed (OS error %d)",
                        self._label,
                        _last_error(),
                    )
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if not user32.UnhookWindowsHookEx(handle):
                logger.warning(
                    "UnhookWindowsHookEx failed for the %s hook (OS error %d)",
                    self._label,
                    _last_error(),
                )
            self._thread_id = None

    def _report_install_failure(self, error_code: int) -> None:
        logger.error(
            "The %s hotkey hook could not be installed: SetWindowsHookExW "
            "failed (OS error %d: %s). The hotkey is off; dictate from the "
            "tray menu.",
            self._label,
            error_code,
            ctypes.FormatError(error_code).strip(),  # type: ignore[attr-defined]
        )
        if self._on_install_failed is None:
            return
        try:
            self._on_install_failed(error_code)
        except Exception:
            logger.error("Error reporting the %s hook failure", self._label, exc_info=True)
