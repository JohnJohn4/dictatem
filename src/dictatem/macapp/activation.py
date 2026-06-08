"""macOS activation policy — NSApplication via PyObjC (manual QA only).

This module requires pyobjc-framework-Cocoa and only works on macOS; it is
imported lazily from ``daemon._run_daemon`` behind a ``sys.platform`` guard,
never at module level by any pure-core module. Excluded from pyright (see
``pyproject.toml`` ``[tool.pyright] exclude``) because AppKit is unresolvable
off-macOS.

Why this exists: the generated ``.app``'s ``Info.plist`` sets ``LSUIElement``
to make Dictatem a menu-bar accessory (no Dock icon, a top-right status item).
But real-Mac QA (#61) showed the daemon process runs as the uv-managed
``python3.12`` the shim execs into — not as the bundle — so the bundle's
``LSUIElement`` never applies to it: launched via the ``.app`` the process got
a Dock icon and NO menu-bar status item, while a Terminal launch (different
default policy) showed the status item. Setting the policy on the running
``NSApplication`` is launch-independent and fixes both symptoms. It does not
fix the TCC identity label (that needs a signed bundle, #91) — only the
Dock-icon / missing-status-item behaviour.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac activation policy requires macOS")

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
)


def set_accessory_activation_policy() -> None:
    """Make the running process a menu-bar accessory app (no Dock icon).

    Called once right after the ``QApplication`` (hence the ``NSApplication``)
    exists. Best-effort: a failure here must never kill daemon startup — the
    daemon is fully functional via the hotkey even if the policy call fails.
    """
    try:
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        logger.warning(
            "Could not set macOS accessory activation policy", exc_info=True
        )


def activate_app() -> None:
    """Bring the accessory app to the front so a modal dialog grabs focus.

    Accessory apps (see :func:`set_accessory_activation_policy`) are never
    auto-activated, so a ``QMessageBox`` — our guided permission prompts —
    can open behind the frontmost app and be dismissed on the first click
    elsewhere (observed in QA, #57). Call this right before showing one.
    Best-effort. ``activateIgnoringOtherApps_`` is soft-deprecated but remains
    the working way to front an accessory app on current macOS.
    """
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        logger.warning("Could not bring the app to the front", exc_info=True)
