"""macOS activation/process-type — PyObjC + Carbon via ctypes (manual QA only).

This module only works on macOS; it is imported lazily from
``daemon._run_daemon`` (and ``permissions.qt_dialog``) behind a ``sys.platform``
guard, never at module level by any pure-core module. Excluded from pyright
(see ``pyproject.toml`` ``[tool.pyright] exclude``) because AppKit /
ApplicationServices are unresolvable off-macOS.

Why this exists: the generated ``.app``'s ``Info.plist`` sets ``LSUIElement``,
but real-Mac QA (#61) showed the daemon runs as the uv-managed ``python3.12``
the shim execs into — not as the bundle — so ``LSUIElement`` never applies.
We make the *running process* a menu-bar accessory instead. The status item
not appearing under a LaunchServices/``.app`` launch (while working from a
Terminal launch) is under active diagnosis (#54); this module also carries the
diagnostic helpers for that.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

if sys.platform != "darwin":
    raise ImportError("mac activation policy requires macOS")

from AppKit import (
    NSApplication,
    NSRunningApplication,
    NSStatusBar,
    NSVariableStatusItemLength,
)

# Carbon ProcessManager constants (ApplicationServices). kCurrentProcess goes in
# the low long of the PSN; UIElement == 4 (the menu-bar accessory transform).
_K_CURRENT_PROCESS = 2
_K_PROCESS_TRANSFORM_TO_UI_ELEMENT_APPLICATION = 4

# Retains the diagnostic native status item so it is not garbage-collected (an
# NSStatusItem disappears the moment its last reference drops).
_test_status_item: object | None = None


class _ProcessSerialNumber(ctypes.Structure):
    _fields_ = [
        ("highLongOfPSN", ctypes.c_uint32),
        ("lowLongOfPSN", ctypes.c_uint32),
    ]


def set_accessory_activation_policy() -> None:
    """Transform the running process into a menu-bar accessory (no Dock icon).

    Uses ``TransformProcessType`` so a LaunchServices-launched process registers
    with the status bar (a plain ``setActivationPolicy_`` does not — QA
    #54/#61). Logs the OSStatus for diagnosis. Best-effort.
    """
    try:
        app_services = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework"
            "/ApplicationServices"
        )
        app_services.TransformProcessType.restype = ctypes.c_int32
        app_services.TransformProcessType.argtypes = [
            ctypes.POINTER(_ProcessSerialNumber),
            ctypes.c_uint32,
        ]
        psn = _ProcessSerialNumber(0, _K_CURRENT_PROCESS)
        status = app_services.TransformProcessType(
            ctypes.byref(psn),
            ctypes.c_uint32(_K_PROCESS_TRANSFORM_TO_UI_ELEMENT_APPLICATION),
        )
        logger.info("diag: TransformProcessType(UIElement) -> OSStatus=%s", status)
    except Exception:
        logger.warning(
            "Could not transform process to a menu-bar accessory", exc_info=True
        )


def log_activation_diagnostics() -> None:
    """Log the running process's GUI/app identity for the missing-icon hunt."""
    try:
        app = NSApplication.sharedApplication()
        running = NSRunningApplication.currentApplication()
        bundle_url = running.bundleURL()
        logger.info(
            "diag: activationPolicy=%s isActive=%s finishedLaunching=%s",
            app.activationPolicy(),
            app.isActive(),
            app.isRunning(),
        )
        logger.info(
            "diag: running bundleId=%s name=%s bundleURL=%s",
            running.bundleIdentifier(),
            running.localizedName(),
            bundle_url.path() if bundle_url is not None else None,
        )
        logger.info(
            "diag: systemStatusBar thickness=%s",
            NSStatusBar.systemStatusBar().thickness(),
        )
    except Exception:
        logger.warning("diag: activation diagnostics failed", exc_info=True)


def create_native_test_status_item() -> None:
    """Create a *native* (non-Qt) NSStatusItem titled ``DCTM`` as a diagnostic.

    If ``DCTM`` text appears in the menu bar but the Qt waveform icon does not,
    the problem is Qt-specific. If neither appears, it is a process/bundle-level
    problem (the process not truly being the bundle) — pointing at #91.
    """
    global _test_status_item
    try:
        bar = NSStatusBar.systemStatusBar()
        item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        button = item.button()
        if button is not None:
            button.setTitle_("DCTM")
        _test_status_item = item  # retain
        logger.info(
            "diag: native test status item created button=%s visible=%s",
            button is not None,
            item.isVisible() if hasattr(item, "isVisible") else "n/a",
        )
    except Exception:
        logger.warning("diag: native test status item failed", exc_info=True)


def activate_app() -> None:
    """Bring the accessory app to the front so a modal dialog grabs focus.

    Accessory apps are never auto-activated, so a ``QMessageBox`` — our guided
    permission prompts — can open behind the frontmost app and be dismissed on
    the first click elsewhere (observed in QA, #57). Best-effort.
    """
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        logger.warning("Could not bring the app to the front", exc_info=True)
