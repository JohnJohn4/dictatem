"""macOS foreground tracker — NSWorkspace/NSRunningApplication via PyObjC (manual QA only).

This module requires pyobjc-framework-Cocoa and only works on macOS; it is
never imported at module level by any pure-core module, and the paste
pipeline is exercised against an in-memory fake in tests. Excluded from
pyright (see ``pyproject.toml`` ``[tool.pyright] exclude``) because AppKit
is unresolvable off-macOS.

``target_id`` here is the frontmost application's PID — app-granular, not
window-granular, by design (ADR-0018): a per-window identity (CGWindowID)
would require the Screen Recording TCC permission, a fourth grant for a
marginal safety gain. The Last Paste rail only compares two ints for
equality, and a PID is enough for that token.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac_foreground requires macOS")

from AppKit import (
    NSApplicationActivateIgnoringOtherApps,
    NSRunningApplication,
    NSWorkspace,
)


class MacForegroundTracker:
    def capture(self) -> int:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            # Possible in headless/login-window edge states. 0 is never a
            # real PID, so the rail's equality check simply won't match.
            logger.warning("No frontmost application; capturing target_id=0")
            return 0
        return int(app.processIdentifier())

    def restore(self, target_id: int) -> None:
        # On macOS the target_id is the frontmost-app PID (ADR-0018).
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(target_id)
        if app is None:
            logger.warning(
                "Cannot restore focus: no running application with pid %d", target_id
            )
            return
        # Soft-deprecated in macOS 14 (in favour of NSWorkspace's async
        # activate), but it remains the correct PyObjC-reachable call here.
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
