"""macOS CGEventTap adapter — bridges a Quartz event tap to a thread-safe handler.

This module requires PyObjC (Quartz + CoreFoundation) and only works on
macOS. It is NOT imported at module level by any pure-core module; tests run
on Windows/Linux without touching this file. Like the other native adapters
it is manual-QA only and excluded from pyright (the PyObjC bindings resolve
only on macOS): all decision logic lives in the pure ``mac_keymap`` and
``classifier`` modules, which carry the unit tests.

The tap callback runs on the hook thread (a daemon thread spun up by
``install`` that owns the tap's CFRunLoop).  Qt widget operations must
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

    from dictatem.hotkey.classifier import Key, KeyAction

if sys.platform != "darwin":
    raise ImportError("mac_hook requires macOS")

# The CFRunLoop/CFMachPort symbols are imported from the CoreFoundation
# binding (shipped by pyobjc-framework-Cocoa, already a darwin dependency)
# rather than relying on Quartz's re-exports of them — the CG* symbols below
# are the ones Quartz canonically owns.
from CoreFoundation import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
    kCFRunLoopCommonModes,
)
from Quartz import (
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGEventTapOptionListenOnly,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)


class CGEventTapHook:
    """CGEventTap keyboard hook that forwards events to a thread-safe handler."""

    def __init__(
        self, on_key_event: Callable[[Key, KeyAction, int], None]
    ) -> None:
        self._on_key_event = on_key_event
        self._tap: object | None = None  # CFMachPortRef while the tap is live
        self._run_loop: object | None = None  # the hook thread's CFRunLoopRef

    def install(self) -> None:
        threading.Thread(target=self._run_tap, daemon=True).start()

    def uninstall(self) -> None:
        if self._tap is not None:
            CGEventTapEnable(self._tap, False)
            self._tap = None
        if self._run_loop is not None:
            # CFRunLoopStop is documented as callable from any thread; the
            # ref was captured inside the hook thread (run loops are
            # per-thread), so exactly that thread's loop exits.
            CFRunLoopStop(self._run_loop)
            self._run_loop = None

    def _run_tap(self) -> None:
        from dictatem.hotkey.classifier import KeyAction
        from dictatem.hotkey.mac_keymap import flags_changed_action, keycode_to_key

        def _tap_callback(
            _proxy: object, event_type: int, event: object, _refcon: object
        ) -> object:
            # SAFETY: an exception must never escape a CGEventTap callback —
            # always swallow, log, and return the event.
            try:
                if event_type in (
                    kCGEventTapDisabledByTimeout,
                    kCGEventTapDisabledByUserInput,
                ):
                    # macOS disables a tap whose callback runs too slowly (or
                    # while secure input is active). Without re-enabling here
                    # the hotkey would stay dead for the rest of the session.
                    if self._tap is not None:
                        CGEventTapEnable(self._tap, True)
                    return event

                keycode = CGEventGetIntegerValueField(
                    event, kCGKeyboardEventKeycode
                )
                if event_type == kCGEventFlagsChanged:
                    # Modifier keys never produce keyDown/keyUp through a
                    # tap; press vs release is derived from the event's flags
                    # by the pure helper (see mac_keymap.flags_changed_action).
                    action = flags_changed_action(keycode, CGEventGetFlags(event))
                    if action is None:
                        return event  # caps lock / fn — not combo modifiers
                elif event_type == kCGEventKeyDown:
                    action = KeyAction.KEY_DOWN
                elif event_type == kCGEventKeyUp:
                    action = KeyAction.KEY_UP
                else:
                    return event

                # Use time.monotonic, not the CGEvent timestamp. The CGEvent
                # clock is mach_absolute_time-derived; the Qt tick that
                # drives HOLD_START detection passes time.monotonic. If the
                # two clocks have a non-zero offset, a single tap fires a
                # spurious HOLD_START → PTT_REC → instant stop.
                timestamp_ms = int(time.monotonic() * 1000)
                self._on_key_event(keycode_to_key(keycode), action, timestamp_ms)
            except Exception:
                logger.error("Error in event tap callback", exc_info=True)
            return event

        mask = (
            CGEventMaskBit(kCGEventKeyDown)
            | CGEventMaskBit(kCGEventKeyUp)
            | CGEventMaskBit(kCGEventFlagsChanged)
        )
        # Listen-only: Dictatem never suppresses keys here (the Windows hook
        # always calls CallNextHookEx too), and a listen-only tap needs only
        # the Input Monitoring TCC permission — not Accessibility.
        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            _tap_callback,
            None,
        )
        if tap is None:
            # Tap creation failing IS the "Input Monitoring not granted"
            # detection signal (#57 / ADR-0014). This phase is detection and
            # logging only — no dialog UI. The daemon stays up; recording
            # still works from the tray menu.
            from dictatem.permissions.mapper import (
                MacPermission,
                map_missing_permissions,
            )

            (guidance,) = map_missing_permissions({MacPermission.INPUT_MONITORING})
            logger.error(
                "Global-hotkey event tap could not be created — the Input "
                "Monitoring permission is missing. %s Settings: %s",
                guidance.message,
                guidance.settings_url,
            )
            return

        self._tap = tap
        # Capture the run loop ref from INSIDE this thread — run loops are
        # per-thread — so uninstall (called from another thread) stops
        # exactly this loop.
        self._run_loop = CFRunLoopGetCurrent()
        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(self._run_loop, source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)
        CFRunLoopRun()
