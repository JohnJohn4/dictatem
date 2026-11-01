"""Win32 keystroke sender — uses ctypes."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import dataclasses
import logging
import threading
import time

from dictatem.hotkey.win32_keymap import (
    DICTATEM_INJECTION_TAG,
    LLKHF_EXTENDED,
    VK_MENU_MASK,
)
from dictatem.paste.injection_diagnostics import (
    DIAGNOSTIC_VKS,
    InjectionSnapshot,
    format_injection_diagnostics,
    keys_down,
)
from dictatem.paste.input_timeline import (
    InputTimeline,
    ms_since,
    replayed_recently,
    wait_for_input_settle,
)
from dictatem.paste.modifier_wait import held_modifier_names
from dictatem.paste.win32_clipboard_formats import STANDARD_FORMAT_NAMES

logger = logging.getLogger(__name__)

VK_CONTROL = 0x11
VK_V = 0x56
VK_BACK = 0x08
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
PM_NOREMOVE = 0x0000
ERROR_INSUFFICIENT_BUFFER = 122

# How long after the SendInput the diagnostics read the target thread's key
# state (see ``_read_thread_keys`` for why it is deferred and off-thread).
THREAD_KEYS_DELAY_S = 0.25


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


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("hwndActive", ctypes.wintypes.HWND),
        ("hwndFocus", ctypes.wintypes.HWND),
        ("hwndCapture", ctypes.wintypes.HWND),
        ("hwndMenuOwner", ctypes.wintypes.HWND),
        ("hwndMoveSize", ctypes.wintypes.HWND),
        ("hwndCaret", ctypes.wintypes.HWND),
        ("rcCaret", ctypes.wintypes.RECT),
    ]


# Tag every injected event so our own keyboard hook can ignore it (see
# ``hotkey/win32_keymap.is_own_injection``).
_EXTRA_INFO = ctypes.cast(DICTATEM_INJECTION_TAG, ctypes.POINTER(ctypes.c_ulong))

# A private user32 instance, so these prototypes never clobber the ones other
# modules set on ``ctypes.windll.user32``.
_user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetKeyState.argtypes = [ctypes.c_int]
_user32.GetKeyState.restype = ctypes.c_short
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.POINTER(ctypes.wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
_user32.GetGUIThreadInfo.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.POINTER(_GUITHREADINFO),
]
_user32.GetGUIThreadInfo.restype = ctypes.wintypes.BOOL
_user32.GetClassNameW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPWSTR,
    ctypes.c_int,
]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.AttachThreadInput.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.BOOL,
]
_user32.AttachThreadInput.restype = ctypes.wintypes.BOOL
_user32.GetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_user32.GetKeyboardState.restype = ctypes.wintypes.BOOL
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(ctypes.wintypes.MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
_user32.PeekMessageW.restype = ctypes.wintypes.BOOL
_user32.GetUpdatedClipboardFormats.argtypes = [
    ctypes.POINTER(ctypes.wintypes.UINT),
    ctypes.wintypes.UINT,
    ctypes.POINTER(ctypes.wintypes.UINT),
]
_user32.GetUpdatedClipboardFormats.restype = ctypes.wintypes.BOOL
_user32.GetClipboardFormatNameW.argtypes = [
    ctypes.wintypes.UINT,
    ctypes.wintypes.LPWSTR,
    ctypes.c_int,
]
_user32.GetClipboardFormatNameW.restype = ctypes.c_int
_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD


def _key_input(vk: int, flags: int = 0, scan: int = 0) -> _INPUT:
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(
        wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=_EXTRA_INFO
    )
    return inp


def _send_input(inputs: ctypes.Array[_INPUT]) -> int:
    """Dispatch *inputs* as ONE SendInput batch; return the dispatched count."""
    return ctypes.windll.user32.SendInput(
        len(inputs), ctypes.byref(inputs), ctypes.sizeof(_INPUT)
    )


def _is_vk_down(vk: int) -> bool:
    # High bit set = the key is down right now (logical async state, which is
    # what an injected Ctrl+V combines with in the target).
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def paste_batch() -> ctypes.Array[_INPUT]:
    """The Ctrl+V batch, led by a signed no-op key (#269 hardening).

    ``[0xE8 down, 0xE8 up, Ctrl down, V down, V up, Ctrl up]`` in ONE batch: the
    target's thread dequeues a neutral key first, so its thread key state is
    brought up to date (e.g. a modifier release it missed while it wasn't the
    input owner) before it sees Ctrl+V. 0xE8 is unassigned (the menu mask key),
    so it can't form a shortcut, and like every Dictatem injection it carries
    the tag the hook skips.
    """
    return (_INPUT * 6)(
        _key_input(VK_MENU_MASK),
        _key_input(VK_MENU_MASK, KEYEVENTF_KEYUP),
        _key_input(VK_CONTROL),
        _key_input(VK_V),
        _key_input(VK_V, KEYEVENTF_KEYUP),
        _key_input(VK_CONTROL, KEYEVENTF_KEYUP),
    )


def _u32(hwnd: int | None) -> int:
    # HWNDs are 32-bit significant; the foreground tracker's default-restype
    # capture may hand back a sign-extended c_int.
    return (hwnd or 0) & 0xFFFFFFFF


def _window_class(hwnd: int | None) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    n = _user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value if n > 0 else "?"


def _gui_thread_info(thread_id: int) -> tuple[int | None, str | None]:
    """(flags, focus window class) of *thread_id*'s GUI state — no attaching."""
    info = _GUITHREADINFO(cbSize=ctypes.sizeof(_GUITHREADINFO))
    if not thread_id or not _user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return None, None
    return int(info.flags), _window_class(info.hwndFocus)


def _async_keys() -> tuple[str, ...]:
    return keys_down({vk: _is_vk_down(vk) for _, vk in DIAGNOSTIC_VKS})


def _read_thread_keys(target_thread_id: int) -> tuple[str, ...] | None:
    """The target GUI thread's key state, read via a brief AttachThreadInput.

    Why this runs on a short-lived worker thread, THREAD_KEYS_DELAY_S after the
    SendInput, rather than inline on the Qt GUI thread at paste time:

    * Attaching shares one input queue and key state between the two threads,
      and Windows documents that the key state is reset by the attach. Doing
      that while our Ctrl+V is still sitting in the target's queue could alter
      the very paste being diagnosed; by +250 ms the target has processed it.
    * If the target thread is hung, anything synchronised with its input state
      can stall. A worker thread can stall harmlessly; the GUI thread must not.

    The attach is undone in ``finally`` — it is never left in place. Returns
    None when the state could not be read (no queue, attach refused, ...).
    """
    msg = ctypes.wintypes.MSG()
    # AttachThreadInput needs both threads to own a message queue.
    _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
    me = _kernel32.GetCurrentThreadId()
    if not target_thread_id or target_thread_id == me:
        return None
    if not _user32.AttachThreadInput(me, target_thread_id, True):
        return None
    try:
        _user32.GetKeyState(0)  # sync this thread's view of the shared key state
        state = (ctypes.c_ubyte * 256)()
        ok = _user32.GetKeyboardState(state)
    finally:
        _user32.AttachThreadInput(me, target_thread_id, False)
    if not ok:
        return None
    return keys_down({vk: bool(state[vk] & 0x80) for _, vk in DIAGNOSTIC_VKS})


def _clipboard_format_names() -> list[str]:
    """Formats on the clipboard now, by name. Needs no OpenClipboard."""
    count = ctypes.wintypes.UINT(0)
    size = 64
    buf = (ctypes.wintypes.UINT * size)()
    attempts = 0
    while not _user32.GetUpdatedClipboardFormats(buf, size, ctypes.byref(count)):
        attempts += 1
        if attempts >= 3 or ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER:
            return ["?"]
        size = max(size * 2, int(count.value))
        buf = (ctypes.wintypes.UINT * size)()
    names: list[str] = []
    for fid in buf[: count.value]:
        name = STANDARD_FORMAT_NAMES.get(fid)
        if name is None:
            nbuf = ctypes.create_unicode_buffer(128)
            n = _user32.GetClipboardFormatNameW(fid, nbuf, len(nbuf))
            name = nbuf.value if n > 0 else f"0x{fid:X}"
        names.append(name)
    return names


class Win32KeystrokeSender:
    def __init__(self) -> None:
        # Fed by the keyboard hook (observe_hook_key / send_masked_release),
        # read before each injection (settle) and by the diagnostics (#269).
        self.timeline = InputTimeline()
        # (dispatched, requested) per SendInput since the injection began; only
        # touched on the GUI thread (the paste rail), never by the hook.
        self._sends: list[tuple[int, int]] = []
        self._settle_ms = 0

    # --- hook-side bookkeeping (runs on the keyboard-hook thread) ---

    def observe_hook_key(self, vk: int, is_down: bool, own_injection: bool) -> None:
        """Record a hooked key event in the input timeline (cheap, never raises)."""
        try:
            self.timeline.note_key(vk, is_down, own_injection, time.monotonic())
        except Exception:
            logger.debug("Input timeline update failed", exc_info=True)

    def held_modifiers(self) -> frozenset[str]:
        """Alt / Win / Shift / Ctrl currently down, via ``GetAsyncKeyState`` (#269)."""
        return held_modifier_names(_is_vk_down)

    # --- injection ---

    def _settle_before_injection(self) -> None:
        """Bounded wait for the hook's key-up replay / last release to settle."""
        self._settle_ms = 0
        try:
            result = wait_for_input_settle(
                self.timeline.view, clock=time.monotonic, sleep=time.sleep
            )
        except Exception:
            logger.debug("Input settle wait failed", exc_info=True)
            return
        if not result.needed:
            return
        self._settle_ms = round(result.waited_s * 1000)
        logger.info(
            "Paste: waited %d ms for input to settle (%s)%s",
            self._settle_ms,
            ", ".join(sorted(result.reasons)),
            "; replayed key-up never observed" if result.replay_unobserved else "",
        )

    def _dispatch(self, inputs: ctypes.Array[_INPUT], label: str) -> int:
        count = len(inputs)
        sent = _send_input(inputs)
        self._sends.append((int(sent), count))
        if sent != count:
            err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "SendInput dispatched %d/%d %s events (GetLastError=%d)",
                sent,
                count,
                label,
                err,
            )
        return sent

    def send_paste(self) -> None:
        self._sends = []
        self._settle_before_injection()
        if logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug(
                    "Paste: clipboard formats before Ctrl+V: %s",
                    ", ".join(_clipboard_format_names()) or "none",
                )
            except Exception:
                logger.debug("Could not list clipboard formats", exc_info=True)
        self._dispatch(paste_batch(), "paste")

    def send_backspaces(self, n: int) -> None:
        self._sends = []
        if n <= 0:
            return
        self._settle_before_injection()
        count = n * 2  # one keydown + one keyup per backspace
        inputs_array = _INPUT * count
        inputs = inputs_array()
        for i in range(n):
            inputs[2 * i] = _key_input(VK_BACK)
            inputs[2 * i + 1] = _key_input(VK_BACK, KEYEVENTF_KEYUP)
        self._dispatch(inputs, "backspace")

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

        The replay is noted in the input timeline (before SendInput — the hook
        sees the replayed key-up only after this callback returns), so the
        paste rail can wait until it has come back through the hook (#269).
        """
        keyup_flags = KEYEVENTF_KEYUP
        if hook_flags & LLKHF_EXTENDED:
            keyup_flags |= KEYEVENTF_EXTENDEDKEY
        inputs = (_INPUT * 3)(
            _key_input(VK_MENU_MASK),
            _key_input(VK_MENU_MASK, KEYEVENTF_KEYUP),
            _key_input(vk, keyup_flags, scan=scan),
        )
        self.timeline.note_replay_sent(vk, time.monotonic())
        sent = _send_input(inputs)
        if sent != 3:
            self.timeline.note_replay_failed()
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
        self._dispatch(inputs, "unicode")

    # --- diagnostics (#269) ---

    def report_injection(self, target_id: int, kind: str) -> None:
        """Log one ``Paste diag`` INFO line for the injection just sent.

        The immediate state (foreground, GUI-thread flags, focus class, async
        keys, timeline) is read now, on the calling thread, right after the
        SendInput; the target thread's key state is read THREAD_KEYS_DELAY_S
        later on a worker (see ``_read_thread_keys``), which then logs the line.
        Never raises; failures are logged at DEBUG. Logs no dictated text.
        """
        try:
            self._report_injection(target_id, kind)
        except Exception:
            logger.debug("Paste diagnostics gather failed", exc_info=True)

    def _report_injection(self, target_id: int, kind: str) -> None:
        sends = tuple(self._sends)
        self._sends = []
        now = time.monotonic()
        target = _u32(target_id)
        fg = _user32.GetForegroundWindow()
        thread_id = int(_user32.GetWindowThreadProcessId(target, None)) if target else 0
        flags, focus_class = _gui_thread_info(thread_id)
        view = self.timeline.view()
        partial = InjectionSnapshot(
            kind=kind,
            target_hwnd=target,
            foreground_after_hwnd=_u32(fg),
            gui_flags=flags,
            focus_class=focus_class,
            thread_keys=None,
            thread_keys_delay_ms=round(THREAD_KEYS_DELAY_S * 1000),
            async_keys=_async_keys(),
            since_modifier_up_ms=ms_since(view.last_modifier_up_s, now),
            replay_within_1s=replayed_recently(view, now),
            sends=sends,
            settle_ms=self._settle_ms,
        )
        worker = threading.Thread(
            target=_finish_report,
            args=(partial, thread_id),
            name="dictatem-paste-diag",
            daemon=True,
        )
        worker.start()


def _finish_report(partial: InjectionSnapshot, thread_id: int) -> None:
    """Worker: read the target thread's key state, then log the line."""
    try:
        time.sleep(THREAD_KEYS_DELAY_S)
        try:
            thread_keys = _read_thread_keys(thread_id)
        except Exception:
            logger.debug("Target thread key state read failed", exc_info=True)
            thread_keys = None
        snap = dataclasses.replace(partial, thread_keys=thread_keys)
        logger.info("%s", format_injection_diagnostics(snap))
    except Exception:
        logger.debug("Paste diagnostics report failed", exc_info=True)
