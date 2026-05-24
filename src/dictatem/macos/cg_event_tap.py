"""macOS CGEventTap keyboard hook (#56 / ADR-0013) — manual QA only.

The macOS analogue of ``hotkey/wh_keyboard_ll.py``: installs a session-level
``CGEventTap`` on a background thread with its own ``CFRunLoop`` and forwards each
key event to a thread-safe handler (the same enqueue-only ``_HotkeyBridge`` the
Windows hook uses). The pure ``HotkeyClassifier`` then runs Tap/Hold/Esc exactly
as on Windows — this adapter's only job is to turn macOS key events into the
``(vk, KeyAction, timestamp_ms)`` triples the classifier expects.

**Key translation.** The classifier keys off Windows virtual-key codes. So this
adapter maps the macOS modifiers to the *Windows* VK codes the classifier groups
on, choosing the natural Mac equivalents (ADR-0010 makes the combo configurable;
the default "win"+"alt" combo becomes Command+Option on a Mac):

    Command (⌘) -> VK_LWIN / VK_RWIN   ("win" group)
    Option  (⌥) -> VK_LMENU / VK_RMENU ("alt" group)
    Control (⌃) -> VK_LCONTROL / VK_RCONTROL
    Shift   (⇧) -> VK_LSHIFT / VK_RSHIFT
    Escape      -> VK_ESCAPE

Modifier presses/releases arrive as ``kCGEventFlagsChanged`` (not key down/up), so
we diff the flags mask against the previous event to synthesise KEY_DOWN/KEY_UP
per modifier. Escape arrives as a normal ``kCGEventKeyDown`` keycode (53).

This module imports PyObjC (Quartz) and only works on macOS. It is NEVER imported
at module top level (lazy-imported in ``daemon._start_macos_daemon``;
``tests/test_import_safety.py``) and is excluded from pyright/tests
(``pyproject.toml`` ``[tool.pyright] exclude``).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.hotkey.classifier import KeyAction

# Windows VK codes the pure classifier groups on (kept in sync with
# hotkey/classifier.py). Command->win, Option->alt by Mac convention.
_VK_LWIN = 0x5B
_VK_LMENU = 0xA4
_VK_LCONTROL = 0xA2
_VK_LSHIFT = 0xA0
_VK_ESCAPE = 0x1B

# macOS Carbon virtual keycode for Escape.
_KEYCODE_ESCAPE = 53

# CGEventFlags mask bits -> the VK code we report to the classifier. Read at
# import time inside _install so Quartz is only imported on macOS.
_FLAG_TO_VK: dict[int, int] = {}


class CGEventTapKeyboardHook:
    """Global keyboard hook backed by a CGEventTap, mirroring WHKeyboardLLHook."""

    def __init__(
        self, on_key_event: Callable[[int, KeyAction, int], None]
    ) -> None:
        self._on_key_event = on_key_event
        self._thread: threading.Thread | None = None
        self._run_loop = None
        self._tap = None
        self._prev_flags = 0

    def install(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="cg-event-tap")
        self._thread.start()

    def uninstall(self) -> None:
        import CoreFoundation  # type: ignore[import-not-found]
        import Quartz  # type: ignore[import-not-found]

        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
            CoreFoundation.CFMachPortInvalidate(self._tap)
            self._tap = None
        if self._run_loop is not None:
            CoreFoundation.CFRunLoopStop(self._run_loop)
            self._run_loop = None

    def _run(self) -> None:
        import CoreFoundation  # type: ignore[import-not-found]
        import Quartz  # type: ignore[import-not-found]

        self._init_flag_map(Quartz)

        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            # No Input Monitoring grant — the permission dialog (#57) guides the
            # user; the hook simply stays dormant until they grant + relaunch.
            logger.warning(
                "CGEventTapCreate returned NULL — Input Monitoring not granted; "
                "the global hotkey is inactive until granted and relaunched"
            )
            return

        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._run_loop = CoreFoundation.CFRunLoopGetCurrent()
        CoreFoundation.CFRunLoopAddSource(
            self._run_loop, source, CoreFoundation.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(self._tap, True)
        CoreFoundation.CFRunLoopRun()

    @staticmethod
    def _init_flag_map(Quartz) -> None:  # noqa: ANN001, N803
        if _FLAG_TO_VK:
            return
        _FLAG_TO_VK.update(
            {
                Quartz.kCGEventFlagMaskCommand: _VK_LWIN,
                Quartz.kCGEventFlagMaskAlternate: _VK_LMENU,
                Quartz.kCGEventFlagMaskControl: _VK_LCONTROL,
                Quartz.kCGEventFlagMaskShift: _VK_LSHIFT,
            }
        )

    def _callback(self, proxy, type_, event, refcon):  # noqa: ANN001, ANN202, ARG002
        # SAFETY: always return the event so the keystroke is not swallowed
        # system-wide, even on error (mirrors the Windows CallNextHookEx rule).
        try:
            import Quartz  # type: ignore[import-not-found]

            from dictatem.hotkey.classifier import KeyAction

            timestamp_ms = int(time.monotonic() * 1000)

            if type_ == Quartz.kCGEventFlagsChanged:
                self._handle_flags_changed(Quartz, event, timestamp_ms, KeyAction)
            elif type_ in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                if keycode == _KEYCODE_ESCAPE:
                    action = (
                        KeyAction.KEY_DOWN
                        if type_ == Quartz.kCGEventKeyDown
                        else KeyAction.KEY_UP
                    )
                    self._on_key_event(_VK_ESCAPE, action, timestamp_ms)
        except Exception:
            logger.error("Error in CGEventTap callback", exc_info=True)
        return event

    def _handle_flags_changed(self, Quartz, event, timestamp_ms, KeyAction) -> None:  # noqa: ANN001, N803
        """Diff the modifier flags mask to synthesise per-modifier KEY_DOWN/UP."""
        flags = Quartz.CGEventGetFlags(event)
        for mask, vk in _FLAG_TO_VK.items():
            was_down = bool(self._prev_flags & mask)
            is_down = bool(flags & mask)
            if is_down and not was_down:
                self._on_key_event(vk, KeyAction.KEY_DOWN, timestamp_ms)
            elif was_down and not is_down:
                self._on_key_event(vk, KeyAction.KEY_UP, timestamp_ms)
        self._prev_flags = flags
