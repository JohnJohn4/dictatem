"""macOS foreground-app tracker (#59 / ADR-0014) — manual QA only.

The macOS analogue of ``win32_foreground.py``: implements the ``ForegroundTracker``
Protocol. The Protocol's ``int`` handle is a Windows HWND on Windows; on macOS the
closest stable identity for "the window the user is typing into" is the **frontmost
application's process id (PID)**, which is what we return from ``capture`` and
re-activate in ``restore``.

This is exactly what the Trigger Fire safety rail needs (CONTEXT.md#trigger-fire):
it only checks that the foreground identity is unchanged between the paste and the
trigger. App-level PID identity is the right granularity — switching apps (the case
the rail guards against) changes the PID; staying in the same app keeps it.

``restore`` re-activates the captured app via ``NSRunningApplication`` so the
synthetic Cmd+V lands in the same app the dictation targeted. (Per-window focus
within an app would need AXUIElement; app-level activation is sufficient for the
rail and the paste, and avoids fragile AX window matching.)

This module imports PyObjC (AppKit) and only works on macOS. It is NEVER imported
at module top level (lazy-imported in ``daemon._start_macos_daemon``;
``tests/test_import_safety.py``) and is excluded from pyright/tests
(``pyproject.toml`` ``[tool.pyright] exclude``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AXForegroundTracker:
    """ForegroundTracker keyed on the frontmost application's PID."""

    def capture(self) -> int:
        try:
            from AppKit import NSWorkspace  # type: ignore[import-not-found]

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return 0
            return int(app.processIdentifier())
        except Exception:  # pragma: no cover - native/PyObjC dependent
            logger.warning("Failed to capture frontmost application", exc_info=True)
            return 0

    def restore(self, hwnd: int) -> None:
        if hwnd <= 0:
            return
        try:
            from AppKit import (  # type: ignore[import-not-found]
                NSApplicationActivateIgnoringOtherApps,
                NSRunningApplication,
            )

            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(hwnd)
            if app is not None:
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        except Exception:  # pragma: no cover - native/PyObjC dependent
            logger.warning("Failed to restore foreground app pid=%s", hwnd, exc_info=True)
